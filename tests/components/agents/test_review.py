"""Design 0007 §3-§7 and design 0009 §5: reviewing the agent's changes, run on this machine against a fake OpenCode
server. A change to a plan is accepted at once in review mode too, and shown afterwards.

The bridge's `watch` follows each OpenCode server's event stream and writes a JSON line for each thing the service
needs: an ask (those waiting when a server is first followed too; a change with its tool call's input), an answer, a
file, a server gone, `synced` once the servers running at its start were read; it ends when its input closes. A reject
can carry a note for the model.

The service (`Review`, with its watchers running the bridge on this machine) turns each change into a question in review
mode and answers OpenCode with the owner's answer (a reject with its note); in auto mode it answers at once. An answer
given in the agent's terminal withdraws the question; a reply from the phone answers it; a server gone, or a change no
server waits for any more, withdraws it. Each step is an event; the file as written is kept. A container whose bridge
cannot watch is said to need reopening, and is not tried again. The routes give a folder's mode, switch it, list the
changes and give one with its files.
"""

import json
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.client import Client, ClientError
from clank.components.agents.review import Review, ReviewError
from clank.components.agents.watch import OLDER
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import image_folder, names
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import Answer, background_flags
from clank.kernel.questions import Question
from tests.fakes.platform import FakePlatform, container
from tests.support.served import free_port

BRIDGE = image_folder() / "bridge.py"
EDIT = {"filePath": "/workspace/a.py", "oldString": "x = 1", "newString": "x = 2"}
ASK = {
    "id": "per_1", "sessionID": "ses_1", "permission": "edit", "patterns": ["a.py"], "always": ["*"],
    "metadata": {"filepath": "/workspace/a.py", "diff": "@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n"},
    "tool": {"messageID": "msg_1", "callID": "call_1"},
}  # fmt: skip
SKIPPED = {
    "alive",
    "status",
    "session",
    "message",
    "part",
    "removed",
    "todo",
    "compacted",
    "error",
    "server",
}  # the Monitor's


class OpenCode(BaseHTTPRequestHandler):
    """OpenCode's server as the watcher and the replies use it: its event stream (fed by the test), the permissions
    waiting, a message with its tool call, and what was sent."""

    events: ClassVar[list[dict[str, Any]]] = []
    waiting: ClassVar[list[dict[str, Any]]] = []
    sent: ClassVar[list[tuple[str, Any]]] = []
    messages: ClassVar[dict[str, Any]] = {}  # more messages with their tool calls, by path
    fed: ClassVar[threading.Condition] = threading.Condition()
    closing: ClassVar[threading.Event] = threading.Event()

    def do_GET(self) -> None:
        if self.path == "/event":
            self._stream()
            return
        answers: dict[str, Any] = {
            "/permission": OpenCode.waiting,
            "/session/ses_1/message/msg_1": {"info": {"id": "msg_1"}, "parts": [
                {"type": "text", "text": "changing it"},
                {"type": "tool", "callID": "call_1", "tool": "edit", "state": {"status": "running", "input": EDIT}},
            ]},
        }  # fmt: skip
        answers.update(OpenCode.messages)
        self._json(answers.get(self.path, {"error": "no"}), 200 if self.path in answers else 404)

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"null")
        OpenCode.sent.append((self.path, body))
        self._json(True)

    def _stream(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        self.wfile.write(b'data: {"type":"server.connected","properties":{}}\n\n')
        self.wfile.flush()
        seen = len(OpenCode.events)
        while not OpenCode.closing.is_set():
            with OpenCode.fed:
                OpenCode.fed.wait(0.1)
                fresh, seen = OpenCode.events[seen:], len(OpenCode.events)
            for event in fresh:
                self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                self.wfile.flush()

    def log_message(self, format: str, *args: Any) -> None:
        """Quiet."""

    def _json(self, value: Any, status: int = 200) -> None:
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def feed(event_type: str, properties: dict[str, Any]) -> None:
    """An event on the fake server's stream."""
    with OpenCode.fed:
        OpenCode.events.append({"type": event_type, "properties": properties})
        OpenCode.fed.notify_all()


@pytest.fixture
def served() -> Iterator[tuple[int, ThreadingHTTPServer]]:
    OpenCode.events, OpenCode.waiting, OpenCode.sent, OpenCode.messages = [], [], [], {}
    OpenCode.closing = threading.Event()
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), OpenCode)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield port, server
    OpenCode.closing.set()
    server.shutdown()
    server.server_close()


class Watching:
    """The bridge's `watch`, run on this machine; the lines it writes, read as they come."""

    def __init__(self, port: int) -> None:
        self.process = subprocess.Popen(
            [sys.executable, str(BRIDGE), "watch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, creationflags=background_flags(),
            env={**os.environ, "CLANK_BRIDGE_PORTS": f"{port}-{port}"},
        )  # fmt: skip
        self.lines: queue.Queue[dict[str, Any]] = queue.Queue()
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self) -> None:
        assert self.process.stdout is not None
        for raw in self.process.stdout:
            self.lines.put(json.loads(raw))

    def next(self, kind: str) -> dict[str, Any]:
        """The next line of this type (the alive ones and the Monitor's skipped); fails after ten seconds."""
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                line = self.lines.get(timeout=max(deadline - time.monotonic(), 0.01))
            except queue.Empty:
                break
            if line["type"] == kind:
                return line
            assert line["type"] in SKIPPED, f"expected {kind}, the watcher said {line}"
        raise AssertionError(f"the watcher said no {kind} line")

    def end(self) -> int:
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.close()
        ended = self.process.wait(timeout=10)
        self.reader.join(timeout=10)
        self.process.stdout.close()
        return ended


def test_the_watcher_says_each_ask_with_its_tool_call_each_answer_and_each_written_file(
    served: tuple[int, ThreadingHTTPServer],
) -> None:
    port, _ = served
    OpenCode.waiting = [{**ASK, "id": "per_0"}]
    watching = Watching(port)
    try:
        waiting = watching.next("asked")
        assert (waiting["port"], waiting["request"]["id"], waiting["input"]) == (port, "per_0", EDIT)
        assert watching.next("synced")["ports"] == [port]
        feed("session.status", {"sessionID": "ses_1", "status": {"type": "busy"}})
        feed("permission.asked", ASK)
        asked = watching.next("asked")
        assert asked["request"]["metadata"]["filepath"] == "/workspace/a.py"
        assert asked["input"] == EDIT, "the edit's old and new text, from the tool call the ask names"
        feed("permission.asked", {**ASK, "id": "per_2", "permission": "doom_loop", "tool": None})
        assert watching.next("asked")["input"] is None, "only a change carries its tool call"
        feed("permission.replied", {"sessionID": "ses_1", "requestID": "per_1", "reply": "once"})
        assert watching.next("replied") == {
            "type": "replied", "port": port, "request": "per_1", "session": "ses_1", "reply": "once",
        }  # fmt: skip
        feed("file.edited", {"file": "/workspace/a.py"})
        assert watching.next("edited") == {"type": "edited", "port": port, "file": "/workspace/a.py"}
    finally:
        assert watching.end() == 0, "it ends when its input closes"


def test_the_watcher_says_the_agent_each_message_was_sent_to_once(served: tuple[int, ThreadingHTTPServer]) -> None:
    """Design 0009 §7: a user's message, once it names its agent; never twice, never the model's own."""
    port, _ = served
    watching = Watching(port)
    watching.next("synced")
    user = {"id": "msg_7", "role": "user", "sessionID": "ses_1"}
    feed("message.updated", {"sessionID": "ses_1", "info": user})
    feed("message.updated", {"sessionID": "ses_1", "info": {**user, "agent": "planner"}})
    feed("message.updated", {"sessionID": "ses_1", "info": {**user, "agent": "planner"}})
    feed("message.updated", {"sessionID": "ses_1", "info": {"id": "msg_8", "role": "assistant", "agent": "planner"}})
    feed("message.updated", {"sessionID": "ses_1", "info": {**user, "id": "msg_9", "agent": "build"}})
    first, second = watching.next("agent"), watching.next("agent")
    assert first == {"type": "agent", "port": port, "session": "ses_1", "agent": "planner", "terminal": False}
    assert second["agent"] == "build"
    assert watching.end() == 0


def test_the_watcher_says_a_server_that_stopped_is_gone(served: tuple[int, ThreadingHTTPServer]) -> None:
    port, server = served
    watching = Watching(port)
    try:
        watching.next("synced")
        OpenCode.closing.set()
        server.shutdown()
        server.server_close()
        assert watching.next("gone") == {"type": "gone", "port": port}
    finally:
        watching.end()


def test_a_rejected_change_carries_the_note_for_the_model(served: tuple[int, ThreadingHTTPServer]) -> None:
    port, _ = served
    for reply, given in (
        ("reject", {"message": " keep the old name "}),
        ("once", {"message": "ignored"}),
        ("once", {}),
    ):
        done = subprocess.run(
            [sys.executable, str(BRIDGE), "permission", str(port), "per_1", reply], input=json.dumps(given),
            capture_output=True, text=True, timeout=60, creationflags=background_flags(),
            env={**os.environ, "CLANK_BRIDGE_PORTS": f"{port}-{port}"},
        )  # fmt: skip
        assert json.loads(done.stdout) == {"ok": True, "replied": True}
    assert OpenCode.sent == [
        ("/permission/per_1/reply", {"reply": "reject", "message": "keep the old name"}),
        ("/permission/per_1/reply", {"reply": "once"}),
        ("/permission/per_1/reply", {"reply": "once"}),
    ]


USER = Actor(kind="user", via="vscode")
PHONE = Actor(kind="device", via="phone")
CHANGES = ["agents.change_proposed", "agents.change_answered", "agents.change_made", "agents.review_switched"]


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    platform = FakePlatform(state="running")
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.parts["agents"].review.watchers.stop()
    kernel.close()


def until(found: Callable[[], Any], seconds: float = 10) -> Any:
    """What `found` gives once it gives something; fails after `seconds`."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = found()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("it did not happen in time")


def watched(kernel: Kernel, folder: Path, port: int, monkeypatch: pytest.MonkeyPatch) -> Review:
    """Workspace paper on `folder`, its container running, its bridge (run on this machine) reaching the fake server,
    and its watcher started and synced."""
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=USER)
    platform: FakePlatform = kernel.parts["workspaces"].platform
    platform.containers.append(container(names(kernel.home.id).container("paper")))
    monkeypatch.setenv("CLANK_BRIDGE_PORTS", f"{port}-{port}")

    def inside(argv: list[str], given: bytes | None) -> Answer:
        done = subprocess.run([sys.executable, str(BRIDGE), *argv[2:]], input=given or b"", capture_output=True,
                              timeout=60, creationflags=background_flags())  # fmt: skip
        return Answer(done.returncode, done.stdout.decode(), done.stderr.decode())

    platform.inside = inside
    kernel.parts["workspaces"].docker(refresh=True)
    review: Review = kernel.parts["agents"].review
    review.watchers.spawn = lambda workspace: subprocess.Popen(
        [sys.executable, str(BRIDGE), "watch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, creationflags=background_flags(),
    )  # fmt: skip
    review.watchers.keep()
    until(lambda: review.watchers.state("paper")["watching"])
    return review


def asked(kernel: Kernel, change: str) -> Question:
    """The question waiting about a change, once it is asked."""
    found: Question = until(lambda: next(
        (each for each in kernel.questions.waiting() if each.about is not None and each.about.id == change), None
    ))  # fmt: skip
    return found


def sent(reply: dict[str, Any], request: str = "per_1") -> bool:
    return (f"/permission/{request}/reply", reply) in OpenCode.sent


def test_in_review_a_change_waits_for_your_answer_and_the_agent_hears_it(
    kernel: Kernel, served: tuple[int, ThreadingHTTPServer], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _ = served
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    review = watched(kernel, tmp_path, port, monkeypatch)
    feed("permission.asked", ASK)
    question = asked(kernel, "per_1")
    assert question.title == "The agent of paper wants to change a.py (+1 -1)"
    assert question.detail.startswith("--- a/a.py\n+++ b/a.py\n")
    assert [option.key for option in question.options] == ["y", "n"]
    change = review.store.get("per_1")
    assert change is not None
    assert (change["before"], change["after"], change["exact"], change["state"]) == ("x = 1\n", "x = 2\n", True,
                                                                                       "waiting")  # fmt: skip
    assert review.view("paper")["waiting"] == 1
    assert not OpenCode.sent, "the agent waits"
    kernel.questions.answer(question.id, by=USER, option="accept")
    assert sent({"reply": "once"})
    (tmp_path / "a.py").write_bytes(b"x = 2\n")
    feed("file.edited", {"file": "/workspace/a.py"})
    until(lambda: (review.store.get("per_1") or {}).get("written"))
    assert review.store.get("per_1")["made"] == "x = 2\n"  # type: ignore[index]
    events = kernel.events.after(0, types=CHANGES)
    assert [event.type for event in events] == CHANGES[:3]
    assert events[1].data["answer"] == "accepted"
    assert events[1].data["by"] == "you (vscode)"
    assert events[2].data["folder"] == str(tmp_path)


def test_a_reject_tells_the_agent_why_an_answer_in_the_terminal_or_from_the_phone_settles_the_question(
    kernel: Kernel, served: tuple[int, ThreadingHTTPServer], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _ = served
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    review = watched(kernel, tmp_path, port, monkeypatch)
    feed("permission.asked", ASK)
    kernel.questions.answer(asked(kernel, "per_1").id, by=USER, option="reject", text="keep x as it is")
    assert sent({"reply": "reject", "message": "keep x as it is"})
    feed("permission.asked", {**ASK, "id": "per_2"})
    terminal = asked(kernel, "per_2")
    feed("permission.replied", {"sessionID": "ses_1", "requestID": "per_2", "reply": "once"})
    until(lambda: kernel.questions.get(terminal.id).status == "withdrawn")
    assert review.store.get("per_2")["by"] == "the agent's terminal"  # type: ignore[index]
    assert not sent({"reply": "once"}, "per_2"), "the terminal answered it"
    feed("permission.asked", {**ASK, "id": "per_3"})
    phone = asked(kernel, "per_3")
    review.reply("paper", port, "per_3", "reject", actor=PHONE, message="no")
    assert kernel.questions.get(phone.id).answer.by == PHONE  # type: ignore[union-attr]
    assert sent({"reply": "reject", "message": "no"}, "per_3")


def test_in_auto_mode_clank_answers_at_once(
    kernel: Kernel, served: tuple[int, ThreadingHTTPServer], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _ = served
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    review = watched(kernel, tmp_path, port, monkeypatch)
    assert review.switch("paper", "auto", actor=USER)["mode"] == "auto"
    with pytest.raises(ReviewError, match="not sometimes"):
        review.switch("paper", "sometimes", actor=USER)
    feed("permission.asked", ASK)
    until(lambda: sent({"reply": "once"}))
    assert not kernel.questions.waiting()
    assert review.store.get("per_1")["by"] == "Clank (auto mode)"  # type: ignore[index]
    switched, proposed, answered = kernel.events.after(0, types=CHANGES)
    assert switched.summary == "you (vscode) set paper to auto: Clank lets the agent change files without asking"
    assert (proposed.data["mode"], answered.data["by"]) == ("auto", "Clank (auto mode)")


PLAN = "---\nkind: plan\nstatus: implementing\n---\n# A study\n\n- [ ] run it\n"


def plan_ask(id: str, relative: str, tool: str, given: dict[str, Any]) -> dict[str, Any]:
    """An ask to change a file, its tool call served by the fake under its own message."""
    message = f"msg_{id}"
    OpenCode.messages[f"/session/ses_1/message/{message}"] = {"info": {"id": message}, "parts": [
        {"type": "tool", "callID": "call_1", "tool": tool, "state": {"status": "running", "input": given}},
    ]}  # fmt: skip
    return {**ASK, "id": id, "patterns": [relative], "metadata": {"filepath": f"/workspace/{relative}", "diff": ""},
            "tool": {"messageID": message, "callID": "call_1"}}  # fmt: skip


def test_in_review_the_implementers_edits_to_a_plan_are_accepted_at_once_and_any_other_change_still_waits(
    kernel: Kernel, served: tuple[int, ThreadingHTTPServer], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _ = served
    (tmp_path / "plan.md").write_bytes(PLAN.encode())
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    review = watched(kernel, tmp_path, port, monkeypatch)
    tick = {"filePath": "/workspace/plan.md", "oldString": "- [ ] run it", "newString": "- [x] run it"}
    created = {"filePath": "/workspace/studies/b/plan.md", "content": "---\nkind: plan\nstatus: draft\n---\n# B\n"}
    dropped = {"filePath": "/workspace/plan.md", "content": "# A study, its header gone\n"}
    for id, relative, tool, given in (
        ("per_10", "plan.md", "edit", tick),
        ("per_11", "studies/b/plan.md", "write", created),
        ("per_12", "plan.md", "write", dropped),
    ):
        feed("permission.asked", plan_ask(id, relative, tool, given))
        until(lambda: sent({"reply": "once"}, id))  # noqa: B023 (waited for here, in its own turn of the loop)
        change = review.store.get(id)
        assert change is not None
        assert (change["mode"], change["plan"], change["by"], change["question"]) == (
            "auto", True, "Clank (a plan's progress)", None,
        )  # fmt: skip
    assert not kernel.questions.waiting()
    feed("permission.asked", ASK)
    asked(kernel, "per_1")
    assert not sent({"reply": "once"}), "a change to anything but a plan waits for the owner"
    header = "---\nkind: plan\n---\n"
    for id, relative in (("per_20", ".opencode/agent/helper.md"), ("per_21", "settings.yml"), ("per_22", "AGENTS.md")):
        feed("permission.asked", plan_ask(id, relative, "write", {"filePath": f"/workspace/{relative}",
                                                                 "content": header}))  # fmt: skip
        asked(kernel, id)
        assert not sent({"reply": "once"}, id), f"{relative} with a plan's header still waits: it is no plan"


def test_changes_nobody_waits_for_any_more_are_withdrawn(
    kernel: Kernel, served: tuple[int, ThreadingHTTPServer], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, server = served
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    review = watched(kernel, tmp_path, port, monkeypatch)
    feed("permission.asked", ASK)
    first = asked(kernel, "per_1")
    review.watchers.stop()
    review.watchers.keep()  # a new watcher: OpenCode no longer lists per_1 as waiting
    until(lambda: kernel.questions.get(first.id).status == "withdrawn")
    assert review.store.get("per_1")["note"] == "the agent no longer waits for it"  # type: ignore[index]
    feed("permission.asked", {**ASK, "id": "per_2"})
    second = asked(kernel, "per_2")
    OpenCode.closing.set()
    server.shutdown()
    server.server_close()
    until(lambda: kernel.questions.get(second.id).status == "withdrawn")
    assert review.store.get("per_2")["note"] == "the agent stopped"  # type: ignore[index]


def test_a_container_whose_bridge_cannot_watch_is_said_to_need_reopening(
    kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    review = watched(kernel, tmp_path, free_port(), monkeypatch)
    review.watchers.stop()
    started = []

    def older(workspace: str) -> "subprocess.Popen[bytes]":
        started.append(workspace)
        said = json.dumps({"ok": False, "error": "no action 'watch'"})
        return subprocess.Popen([sys.executable, "-c", f"print({said!r})"], stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, creationflags=background_flags())  # fmt: skip

    review.watchers.spawn = older
    review.watchers.keep()
    until(lambda: review.watchers._watching["paper"].ended)
    review.watchers.keep()
    assert review.watchers.state("paper") == {"watching": False, "problem": OLDER}
    review.watchers.keep()
    assert started == ["paper"], "not tried again until the container is made again"
    assert review.view_of_folder(str(tmp_path))["problem"] == OLDER
    assert review.view_of_folder(str(tmp_path / "elsewhere"))["workspace"] is None


def test_the_routes_give_a_folders_mode_switch_it_and_give_each_change_with_its_files(
    kernel: Kernel, served: tuple[int, ThreadingHTTPServer], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    port, _ = served
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    watched(kernel, tmp_path, port, monkeypatch)
    feed("permission.asked", ASK)
    asked(kernel, "per_1")
    with TestClient(create_app(kernel, token="t", port=7729), base_url="http://127.0.0.1:7729") as http:
        client = Client("http://127.0.0.1:7729", "t", name="vscode", http=http)
        assert client.get("agents/review", folder=str(tmp_path)) == {
            "workspace": "paper", "mode": "review", "agent": None, "shown": "review", "waiting": 1, "one_window": True,
            "watching": True, "problem": "", "model_changed": None,
        }, "no message seen in a window yet: its agent is not known"  # fmt: skip
        assert client.post("agents/review", {"workspace": "paper", "mode": "auto"})["mode"] == "auto"
        with pytest.raises(ClientError, match="not later"):
            client.post("agents/review", {"workspace": "paper", "mode": "later"})
        with pytest.raises(ClientError, match="no workspace 'nowhere'"):
            client.post("agents/review", {"workspace": "nowhere", "mode": "auto"})
        [listed] = client.get("agents/changes", workspace="paper")["changes"]
        assert (listed["relative"], listed["state"], "before" in listed) == ("a.py", "waiting", False)
        change = client.get("agents/changes/per_1")
        assert (change["before"], change["after"]) == ("x = 1\n", "x = 2\n")
        with pytest.raises(ClientError, match="no change"):
            client.get("agents/changes/per_9")
        client.post(f"agents/permissions/paper/{port}/per_1", {"reply": "once"})
    assert sent({"reply": "once"})
    assert not kernel.questions.waiting(), "the reply answered the change's question"
