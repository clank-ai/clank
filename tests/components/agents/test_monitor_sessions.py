"""Design 0012 §3, §6.1 and §9 (§11 step 4) and design 0013 §5: the service knows which server runs each session from
its watcher's lines, and every action on a session goes to that server, run against two fake OpenCode servers in one
workspace's container (`tests/fakes/opencode.py`) with the bridge on this machine.

Two OpenCode servers in one container list the same sessions (their storage is the container's home) while only one
runs each; a note, a stop, a reject, a compaction, a clear, a revert and an unrevert reach the server whose stream
carried the session's run and no other, each recorded as `agents.acted`; a session no watcher saw goes to the port a
client names; a server gone leaves its sessions unplaced, and so does a watcher started again that no longer follows
it; listeners hear every line, once the review has handled it; the sessions shown are told to the watch, and told again
to a watch started again. Design 0023 §2: the sessions followed are told the same way. Design 0023 §4: the actions
the owner waits on go through the watcher's own process, and through a process of their own when it does not answer.
"""

import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from clank import registry
from clank.components.agents import watch
from clank.components.agents.sessions import Sessions
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import image_folder, names
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import Answer, background_flags
from tests.fakes.opencode import FakeOpenCode
from tests.fakes.platform import FakePlatform, container

BRIDGE = image_folder() / "bridge.py"
OWNER = Actor(kind="user", via="console")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    platform = FakePlatform(state="running")
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.parts["agents"].review.watchers.stop()
    kernel.close()


@pytest.fixture
def servers() -> Iterator[list[FakeOpenCode]]:
    """The OpenCode window's server and a flow's, in one container."""
    made = FakeOpenCode.several(2)
    yield made
    for each in made:
        each.close()


def until(found: Callable[[], Any], seconds: float = 10) -> Any:
    """What `found` gives once it gives something; fails after `seconds`."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = found()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError("it did not happen in time")


def watched(kernel: Kernel, folder: Path, ports: str, monkeypatch: pytest.MonkeyPatch) -> Sessions:
    """Workspace paper on `folder`, its container running, its bridge (run on this machine) reaching the fake servers,
    and its watcher started and synced."""
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=OWNER)
    platform: FakePlatform = kernel.parts["workspaces"].platform
    platform.containers.append(container(names(kernel.home.id).container("paper")))
    monkeypatch.setenv("CLANK_BRIDGE_PORTS", ports)

    def inside(argv: list[str], given: bytes | None) -> Answer:
        done = subprocess.run([sys.executable, str(BRIDGE), *argv[2:]], input=given or b"", capture_output=True,
                              timeout=60, creationflags=background_flags())  # fmt: skip
        return Answer(done.returncode, done.stdout.decode(), done.stderr.decode())

    platform.inside = inside
    kernel.parts["workspaces"].docker(refresh=True)
    review = kernel.parts["agents"].review
    review.watchers.spawn = lambda workspace: subprocess.Popen(
        [sys.executable, str(BRIDGE), "watch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, creationflags=background_flags(),
    )  # fmt: skip
    review.watchers.keep()
    until(lambda: review.watchers.state("paper")["watching"])
    sessions: Sessions = kernel.parts["agents"].sessions
    return sessions


def test_every_action_reaches_the_server_that_runs_the_session_and_no_other(
    kernel: Kernel, servers: list[FakeOpenCode], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window, flow = servers
    sessions = watched(kernel, tmp_path, f"{window.port}-{flow.port}", monkeypatch)
    flow.feed({"type": "session.status", "properties": {"sessionID": "ses_plan", "status": {"type": "busy"}}})
    until(lambda: sessions.runs("paper", "ses_plan") == flow.port)
    [listed] = [each for each in sessions.seen("paper") if each["session"] == "ses_plan"]
    assert (listed["port"], listed["status"]) == (flow.port, "busy")
    named = window.port  # what a client listing the window's server would name: both list the session
    sessions.send("paper", named, "ses_plan", "About step 3: skip it.", actor=OWNER)
    sessions.send("paper", named, "ses_plan", "Go on.", actor=OWNER, agent="build",
                  model={"providerID": "clank", "modelID": "fast"})  # fmt: skip
    sessions.stop("paper", named, "ses_plan", actor=OWNER)
    flow.asks = [{"id": "per_1", "sessionID": "ses_plan", "permission": "bash", "patterns": ["rm runs"]}]
    assert sessions.reject("paper", named, "ses_plan", actor=OWNER) == {"rejected": ["per_1"], "questions": []}
    assert sessions.compact("paper", named, "ses_plan", actor=OWNER)["asked"] is True
    assert sessions.clear("paper", named, "ses_plan", "msg_02", "prt_02c", actor=OWNER)["cleared"] is True
    sessions.revert("paper", named, "ses_plan", "msg_03", "prt_03e", actor=OWNER)
    sessions.unrevert("paper", named, "ses_plan", actor=OWNER)
    assert sessions.page("paper", named, "ses_plan", limit=1)["messages"][0]["info"]["role"] == "user"
    assert window.sent == [], "nothing reached the server that does not run the session"
    assert "/session/ses_plan/message" not in window.read, "nor was the session's history read there"
    assert "/session/ses_plan/message" in flow.read
    paths = [path for _, path, _ in flow.sent]
    assert paths == [
        "/session/ses_plan/prompt_async", "/session/ses_plan/prompt_async", "/session/ses_plan/abort",
        "/permission/per_1/reply", "/session/ses_plan/summarize", "/session/ses_plan/message/msg_02/part/prt_02c",
        "/session/ses_plan/revert", "/session/ses_plan/unrevert",
    ]  # fmt: skip
    first, second = flow.sent_to("/session/ses_plan/prompt_async")
    assert (first["agent"], second["agent"], second["model"]["modelID"]) == ("planner", "build", "fast")
    acted = kernel.events.after(0, types=["agents.acted"])
    assert [event.data["action"] for event in acted] == [
        "message", "message", "stop", "reject", "compact", "clear", "undo", "redo",
    ]  # fmt: skip
    assert {event.data["port"] for event in acted} == {flow.port}
    sessions.send("paper", named, "ses_other", "Tidy it.", actor=OWNER)
    assert [path for _, path, _ in window.sent] == ["/session/ses_other/prompt_async"], "no watcher saw it: as named"
    flow.release.set()


def test_a_server_gone_leaves_its_sessions_unplaced_and_listeners_hear_every_line(kernel: Kernel) -> None:
    """The watcher's lines, given directly: where each session runs, its status and its parent."""
    sessions: Sessions = kernel.parts["agents"].sessions
    heard: list[tuple[str, dict[str, Any]]] = []
    sessions.listen(lambda workspace, line: heard.append((workspace, line)))
    lines = [
        {"type": "session", "port": 4096, "session": {"id": "ses_1", "parent": None, "title": "Plot tau"}},
        {"type": "session", "port": 4097, "session": {"id": "ses_2", "parent": "ses_1", "title": "a subagent"}},
        {"type": "status", "port": 4097, "session": "ses_1", "status": "busy"},
        {"type": "part", "port": 4097, "session": "ses_2", "part": {"id": "prt_1"}},
    ]
    for line in lines:
        sessions.heard("paper", line)
    assert heard == [("paper", line) for line in lines]
    assert (sessions.runs("paper", "ses_1"), sessions.runs("paper", "ses_2")) == (4097, 4097)
    assert sessions.seen("paper") == [
        {"session": "ses_1", "port": 4097, "status": "busy", "parent": None, "title": "Plot tau"},
        {"session": "ses_2", "port": 4097, "status": "idle", "parent": "ses_1", "title": "a subagent"},
    ]
    sessions.heard("paper", {"type": "started"})
    assert sessions.seen("paper")[0]["status"] == "idle", "a watcher started again says again what runs"
    sessions.heard("paper", {"type": "gone", "port": 4097})
    assert sessions.runs("paper", "ses_1") is None
    assert sessions.runs("other", "ses_1") is None
    sessions.heard("paper", {"type": "session", "port": 4096, "session": {"id": "ses_2"}, "deleted": True})
    assert [each["session"] for each in sessions.seen("paper")] == ["ses_1"]


def test_a_watcher_started_again_forgets_a_server_its_sync_no_longer_follows(
    kernel: Kernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A container reopened: the server that ran a session ended without a `gone` said, so an action on the session
    goes to the port a client names, not to a port where nothing listens; a session still running keeps its server."""
    sessions: Sessions = kernel.parts["agents"].sessions
    asked: list[list[str]] = []

    def bridge(workspace: str, argv: list[str], given: Any = None, timeout: float = 0) -> dict[str, Any]:
        asked.append(argv)
        return {"ok": True}

    monkeypatch.setattr(sessions, "_bridge", bridge)
    for line in (
        {"type": "started"},
        {"type": "synced", "ports": [4096, 4097, 4098]},
        {"type": "status", "port": 4097, "session": "ses_plan", "status": "busy"},
        {"type": "part", "port": 4098, "session": "ses_flow", "part": {"id": "prt_1"}},
        {"type": "started"},
        {"type": "status", "port": 4098, "session": "ses_flow", "status": "busy"},
        {"type": "synced", "ports": [4096, 4098]},
    ):
        sessions.heard("paper", line)
    assert (sessions.runs("paper", "ses_plan"), sessions.runs("paper", "ses_flow")) == (None, 4098)
    assert {each["session"]: each["status"] for each in sessions.seen("paper")} == {"ses_plan": "idle",
                                                                                     "ses_flow": "busy"}  # fmt: skip
    sessions.send("paper", 4096, "ses_plan", "Go on.", actor=OWNER)
    sessions.stop("paper", 4096, "ses_flow", actor=OWNER)
    assert asked == [["prompt", "4096", "ses_plan"], ["abort", "4098", "ses_flow"]]


def test_listeners_hear_a_line_once_the_review_has_handled_it(kernel: Kernel, tmp_path: Path) -> None:
    """Design 0013 §5: a flow that hears an ask finds the review's question already asked."""
    kernel.settings.write("workspace", "paper", {"path": str(tmp_path)}, base=None, actor=OWNER)
    (tmp_path / "a.py").write_bytes(b"x = 1\n")
    review = kernel.parts["agents"].review
    heard: list[tuple[str, bool]] = []
    review.sessions.listen(lambda workspace, line: heard.append((line["type"], review.questioned("per_1"))))
    ask = {"id": "per_1", "sessionID": "ses_plan", "permission": "edit", "patterns": ["a.py"],
           "metadata": {"filepath": "/workspace/a.py", "diff": "@@ -1,1 +1,1 @@\n-x = 1\n+x = 2\n"}}  # fmt: skip
    review.heard("paper", {"type": "asked", "port": 4096, "request": ask, "input": None})
    assert heard == [("asked", True)]


def test_the_sessions_shown_are_told_to_the_watch_and_told_again_when_it_starts_again(
    kernel: Kernel, servers: list[FakeOpenCode], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    window, flow = servers
    sessions = watched(kernel, tmp_path, f"{window.port}-{flow.port}", monkeypatch)
    heard: list[dict[str, Any]] = []
    sessions.listen(lambda workspace, line: heard.append(line))
    watchers = kernel.parts["agents"].review.watchers
    watchers.show("paper", ["ses_plan"])
    until(lambda: {"type": "shown", "sessions": ["ses_plan"]} in heard)
    flow.replay("a step")
    deltas = until(lambda: [line for line in heard if line["type"] == "delta" and line["part"] == "prt_06d"])
    assert deltas[0]["port"] == flow.port
    heard.clear()
    watchers._watching["paper"].stop()  # the watch ends, as when its exec breaks off
    until(lambda: (watchers.keep(), {"type": "shown", "sessions": ["ses_plan"]} in heard)[1], seconds=20)


def test_the_sessions_followed_are_told_to_the_watch_and_told_again_when_it_starts_again(
    kernel: Kernel, servers: list[FakeOpenCode], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design 0023 §2: a followed session's parts come whole; the watch is told as it is told the sessions shown."""
    window, flow = servers
    sessions = watched(kernel, tmp_path, f"{window.port}-{flow.port}", monkeypatch)
    heard: list[dict[str, Any]] = []
    sessions.listen(lambda workspace, line: heard.append(line))
    watchers = kernel.parts["agents"].review.watchers
    watchers.follow("paper", ["ses_plan"])
    until(lambda: {"type": "followed", "sessions": ["ses_plan"]} in heard)
    flow.replay("a step")
    parts = until(lambda: [line for line in heard if line["type"] == "part" and line["part"].get("whole")])
    assert parts[0]["session"] == "ses_plan"
    heard.clear()
    watchers._watching["paper"].stop()  # the watch ends, as when its exec breaks off
    until(lambda: (watchers.keep(), {"type": "followed", "sessions": ["ses_plan"]} in heard)[1], seconds=20)


def test_the_actions_the_owner_waits_on_go_through_the_watcher_and_start_no_process(
    kernel: Kernel, servers: list[FakeOpenCode], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design 0023 §4 (decision 0140): a message, a stop, an answer to a permission or a question, a page and the
    servers go through the watcher's own process, with no `docker exec` of their own."""
    window, flow = servers
    sessions = watched(kernel, tmp_path, f"{window.port}-{flow.port}", monkeypatch)
    platform: FakePlatform = kernel.parts["workspaces"].platform
    flow.feed({"type": "session.status", "properties": {"sessionID": "ses_plan", "status": {"type": "busy"}}})
    until(lambda: sessions.runs("paper", "ses_plan") == flow.port)
    flow.asks = [{"id": "per_1", "sessionID": "ses_plan", "permission": "bash", "patterns": ["rm runs"]}]
    flow.questions = [{"id": "que_1", "sessionID": "ses_plan", "questions": [{"question": "Which?", "options": []}]}]
    before = len(platform.calls)
    sessions.send("paper", window.port, "ses_plan", "About step 3: skip it.", actor=OWNER)
    sessions.stop("paper", window.port, "ses_plan", actor=OWNER)
    sessions.permission("paper", flow.port, "per_1", "once", actor=OWNER)
    sessions.question("paper", flow.port, "que_1", [["the first"]], actor=OWNER)
    assert sessions.page("paper", window.port, "ses_plan", limit=1)["messages"][0]["info"]["role"] == "user"
    assert {int(each["port"]) for each in sessions.servers("paper")} == {window.port, flow.port}
    assert [path for _, path, _ in flow.sent] == [
        "/session/ses_plan/prompt_async", "/session/ses_plan/abort", "/permission/per_1/reply",
        "/question/que_1/reply",
    ]  # fmt: skip
    assert not [call for call in platform.calls[before:] if "bridge.py" in call], "no process of their own"
    assert [event.data["action"] for event in kernel.events.after(0, types=["agents.acted"])] == [
        "message", "stop", "permission", "question",
    ]  # fmt: skip


def test_a_request_the_watcher_does_not_answer_goes_through_a_process_of_its_own_and_the_watcher_starts_again(
    kernel: Kernel, servers: list[FakeOpenCode], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design 0023 §4: nothing the owner asked is lost when the watcher is deaf."""
    window, flow = servers
    sessions = watched(kernel, tmp_path, f"{window.port}-{flow.port}", monkeypatch)
    platform: FakePlatform = kernel.parts["workspaces"].platform
    flow.feed({"type": "session.status", "properties": {"sessionID": "ses_plan", "status": {"type": "busy"}}})
    until(lambda: sessions.runs("paper", "ses_plan") == flow.port)
    watchers = kernel.parts["agents"].review.watchers
    monkeypatch.setattr(watch, "REQUEST_SECONDS", 0.3)
    monkeypatch.setattr(watch, "RETRY_SECONDS", (0.2,))
    deaf = (
        f"import sys, json; print(json.dumps({{'type': 'synced', 'ports': [{window.port}, {flow.port}]}}), flush=True)"
        "\nfor line in sys.stdin:\n"
        "    asked = json.loads(line) if line.strip().startswith('{') else {}\n"
        "    if asked.get('action') == 'hello':\n"
        "        print(json.dumps({'type': 'answer', 'id': asked['id'], 'ok': True}), flush=True)\n"
    )  # a watcher that says it is synced and answers its hello (it reads requests), then answers nothing
    spawned: list[str] = []

    def spawn(workspace: str) -> "subprocess.Popen[bytes]":
        spawned.append(workspace)
        return subprocess.Popen([sys.executable, "-c", deaf], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, creationflags=background_flags())  # fmt: skip

    watchers.spawn = spawn
    watchers.stop()
    watchers.keep()
    until(lambda: watchers.state("paper")["watching"])
    before = len(platform.calls)
    sessions.send("paper", window.port, "ses_plan", "Go on.", actor=OWNER)
    assert [path for _, path, _ in flow.sent] == ["/session/ses_plan/prompt_async"], "it reached OpenCode"
    assert [call for call in platform.calls[before:] if "bridge.py prompt" in call], "through a process of its own"

    def started_again() -> bool:
        watchers.keep()
        return len(spawned) == 2

    until(started_again)
