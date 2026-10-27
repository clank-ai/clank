"""Design 0023 §4 (decision 0140) and design 0007 §4: the service's request channel to a workspace's watcher, run
against the real bridge on this machine and a fake OpenCode server. A request written on the watcher's input is answered
with its id, its answer the bridge's own (a refusal included), and the review never hears it. The watch names each
server it follows (`server`), and the watcher asks its bridge `hello` once it synced: a bridge from before the channel
(in a container made before Clank's programs were mounted) never answers, so its requests go through a process of
their own at once, never after the request's wait, the watcher is left as it is, and the log says so once. The bridge
answers each request within its deadline, in words when OpenCode does not answer, and a slow request holds up no
other; a request for a server that ended is answered at once that it is gone. A watcher whose bridge answered `hello`
and then does not answer within `REQUEST_SECONDS` is ended, so it is started again, and the request raises
`Unanswered`; a workspace without a watcher alive and synced raises `NoChannel`, so the caller sends the request
through a process of its own; so does a request made from the watcher's own reader thread (a line heard), which could
never see its answer. A workspace whose watcher cannot start leaves the others watched, and is said once."""

import logging
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from clank import registry
from clank.components.agents import watch
from clank.components.agents.watch import NoChannel, Unanswered, Watcher, Watchers
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import image_folder, names
from clank.components.workspaces.service import WorkspaceUnavailable
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import background_flags
from tests.fakes.opencode import FakeOpenCode
from tests.fakes.platform import FakePlatform, container
from tests.support.served import free_port

BRIDGE = image_folder() / "bridge.py"
OWNER = Actor(kind="user", via="console")
SYNCED_AND_DEAF = (
    "import sys, json; print(json.dumps({'type': 'synced', 'ports': []}), flush=True)\n"
    "for _ in sys.stdin: pass\n"
)  # a bridge from before the channel: it says it is synced, then answers nothing until its input closes
ANSWERS_ONCE = (
    "import sys, json\n"
    "print(json.dumps({'type': 'synced', 'ports': []}), flush=True)\n"
    "for raw in sys.stdin:\n"
    "    told = json.loads(raw)\n"
    "    if told.get('action') == 'hello':\n"
    "        print(json.dumps({'type': 'answer', 'id': told['id'], 'ok': True, 'within': 7}), flush=True)\n"
)  # a bridge that answers `hello`, then hangs: no request after it is answered
NEVER_SYNCED = "import sys\nfor _ in sys.stdin: pass\n"


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


def bridge_watch(ports: str, **env: str) -> "subprocess.Popen[bytes]":
    """The real bridge's watch, on this machine, reaching the fake servers on `ports`, with the bridge's settings in
    `env` (`CLANK_BRIDGE_ANSWER`: its deadline)."""
    return subprocess.Popen(
        [sys.executable, str(BRIDGE), "watch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, creationflags=background_flags(),
        env={**os.environ, "CLANK_BRIDGE_PORTS": ports, **env},
    )  # fmt: skip


def script(source: str) -> "subprocess.Popen[bytes]":
    return subprocess.Popen(
        [sys.executable, "-c", source], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=background_flags(),
    )  # fmt: skip


@contextmanager
def silent() -> Iterator[int]:
    """A port that takes connections and never answers on them: an OpenCode that hangs."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)
        yield int(listener.getsockname()[1])


def running(kernel: Kernel, folder: Path, workspace: str = "paper") -> None:
    """A workspace on `folder`, its container running (the fake platform)."""
    kernel.settings.write("workspace", workspace, {"path": str(folder)}, base=None, actor=OWNER)
    platform: FakePlatform = kernel.parts["workspaces"].platform
    platform.containers.append(container(names(kernel.home.id).container(workspace)))
    kernel.parts["workspaces"].docker(refresh=True)


def test_a_request_goes_through_the_watcher_and_its_answer_comes_back_with_the_bridges_result() -> None:
    heard: list[dict[str, Any]] = []
    with FakeOpenCode() as fake:
        watcher = Watcher(
            "paper", "c1", bridge_watch(f"{fake.port}-{fake.port}"), lambda workspace, line: heard.append(line)
        )
        try:
            until(lambda: watcher.synced)
            answer = watcher.request("servers", [], {}, 10)
            assert answer["ok"] is True
            assert [int(each["port"]) for each in answer["servers"]] == [fake.port]
            answer = watcher.request("prompt", [str(fake.port), "ses_plan"], {"text": "Go on."}, 10)
            assert (answer["ok"], answer["sent"]) == (True, True)
            [sent] = fake.sent_to("/session/ses_plan/prompt_async")
            assert sent["parts"] == [{"type": "text", "text": "Go on."}]
            answer = watcher.request("bogus", [], {}, 10)
            assert answer["ok"] is False
            assert "no action 'bogus'" in answer["error"], "the bridge's refusal comes back as its answer"
            assert all(line.get("type") != "answer" for line in heard), "the review never hears an answer"
            assert watcher.problem == "", "a refusal is no problem of the watch's"
        finally:
            watcher.stop()


def test_a_watch_names_each_server_it_follows_and_answers_hello_with_its_deadline() -> None:
    heard: list[dict[str, Any]] = []
    with FakeOpenCode() as fake:
        watcher = Watcher(
            "paper", "c1", bridge_watch(f"{fake.port}-{fake.port}"), lambda workspace, line: heard.append(line)
        )
        try:
            until(lambda: watcher.synced)
            kinds = [line.get("type") for line in heard]
            assert {"type": "server", "port": fake.port, "terminal": False} in heard
            assert kinds.index("server") < kinds.index("synced"), "named as it is followed, before the watch synced"
            assert watcher.carries() is True, "it answered the watcher's hello"
            answer = watcher.request("hello", [], {}, 10)
            assert (answer["ok"], answer["within"]) == (True, 7.0)
            assert all(line.get("type") != "answer" for line in heard), "the hello's answer is the watcher's own"
        finally:
            watcher.stop()


def test_a_request_for_a_server_that_ended_is_answered_at_once_that_it_is_gone() -> None:
    with FakeOpenCode() as fake:
        watcher = Watcher("paper", "c1", bridge_watch(f"{fake.port}-{fake.port}"), lambda workspace, line: None)
        try:
            until(lambda: watcher.synced)
            ended = free_port()  # nothing listens there: its OpenCode was closed
            began = time.monotonic()
            answer = watcher.request("page", [str(ended), "ses_plan", "10"], {}, 10)
            assert time.monotonic() - began < 3, "at once, not after a wait"
            assert (answer["ok"], answer["gone"]) == (False, ended)
            assert answer["error"] == f"no OpenCode runs on port {ended} any more: it was closed or it ended"
        finally:
            watcher.stop()


def test_a_request_opencode_does_not_answer_is_answered_within_the_deadline_in_words_and_holds_up_no_other() -> None:
    with FakeOpenCode() as fake, silent() as hung:
        watch_of = bridge_watch(f"{fake.port}-{fake.port}", CLANK_BRIDGE_ANSWER="2")
        watcher = Watcher("paper", "c1", watch_of, lambda workspace, line: None)
        try:
            until(lambda: watcher.synced)
            answers: list[tuple[float, dict[str, Any]]] = []
            began = time.monotonic()

            def slow() -> None:
                answer = watcher.request("page", [str(hung), "ses_plan", "10"], {}, 10)
                answers.append((time.monotonic() - began, answer))

            waiting = threading.Thread(target=slow, daemon=True)
            waiting.start()
            time.sleep(0.2)
            quick = watcher.request("page", [str(fake.port), "ses_plan", "10"], {}, 10)
            assert quick["ok"] is True
            assert time.monotonic() - began < 1.5, "answered while the other waits for its OpenCode"
            waiting.join(10)
            [(took, answer)] = answers
            assert 1.5 <= took < 6, f"within the bridge's deadline, not the service's wait ({took:.1f} s)"
            assert answer == {
                "type": "answer", "id": answer["id"], "ok": False,
                "error": "OpenCode did not answer page within 2 seconds: it may be starting, busy or stuck",
            }  # fmt: skip
            assert watcher.alive(), "the watch itself is well"
        finally:
            watcher.stop()


def test_a_request_from_the_watchers_own_reader_says_there_is_no_channel_since_it_would_wait_for_itself() -> None:
    """The review and the listeners run in the reader's thread (a line heard): a request there could never see its
    answer, which that thread reads; it goes through a process of its own instead, at once."""
    raised: list[str] = []
    watcher: Watcher | None = None

    def heard(workspace: str, line: dict[str, Any]) -> None:
        if line.get("type") == "synced" and watcher is not None:
            began = time.monotonic()
            try:
                watcher.request("servers", [], {}, 5)
            except (NoChannel, Unanswered) as error:
                raised.append(type(error).__name__)
            raised.append("at once" if time.monotonic() - began < 2 else "after the wait")

    with FakeOpenCode() as fake:
        watcher = Watcher("paper", "c1", bridge_watch(f"{fake.port}-{fake.port}"), heard)
        try:
            until(lambda: raised)
            assert raised == ["NoChannel", "at once"]
        finally:
            watcher.stop()


def test_a_watcher_whose_bridge_reads_no_request_sends_none_and_is_left_watching(
    kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A container made before Clank's programs were mounted (decision 0142) runs the bridge its image copied, from
    before the channel: it reads only `shown`, so a request written to it is never answered (110 requests a day waited
    their ten seconds on the owner's machine, 2026-10-26, each ending and starting the watcher again)."""
    running(kernel, tmp_path)
    monkeypatch.setattr(watch, "PROBE_SECONDS", 0.5)
    watchers = Watchers(kernel, lambda workspace, line: None, spawn=lambda workspace: script(SYNCED_AND_DEAF))
    try:
        watchers.keep()
        until(lambda: watchers.state("paper")["watching"])
        with caplog.at_level(logging.WARNING, logger=watch.__name__):
            for _ in range(3):
                began = time.monotonic()
                with pytest.raises(NoChannel):
                    watchers.request("paper", "page", ["4096", "ses_plan", "10"], {})
                assert time.monotonic() - began < 2, "never the request's whole wait"
        assert watchers.state("paper")["watching"] is True, "the watcher is left as it is"
        said = [record.getMessage() for record in caplog.records if "request channel" in record.getMessage()]
        assert len(said) == 1, f"said once: {said}"
        assert said[0].startswith("paper's container runs a bridge from before its request channel")
        assert "stop the workspace and open it again (Workspaces, F6: x, then o)" in said[0]
    finally:
        watchers.stop()


def test_a_watcher_that_stops_answering_is_ended_and_started_again_and_the_request_says_so(
    kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    running(kernel, tmp_path)
    monkeypatch.setattr(watch, "REQUEST_SECONDS", 0.3)
    monkeypatch.setattr(watch, "RETRY_SECONDS", (0.2,))
    started: list[str] = []

    def spawn(workspace: str) -> "subprocess.Popen[bytes]":
        started.append(workspace)
        return script(ANSWERS_ONCE)

    watchers = Watchers(kernel, lambda workspace, line: None, spawn=spawn)
    try:
        watchers.keep()
        until(lambda: watchers.state("paper")["watching"])
        began = time.monotonic()
        with pytest.raises(Unanswered):
            watchers.request("paper", "servers", [], {})
        assert time.monotonic() - began < 5, "it waited REQUEST_SECONDS, not the watcher's whole life"
        assert watchers.state("paper")["watching"] is False, "ended"

        def started_again() -> bool:
            watchers.keep()
            return len(started) == 2

        until(started_again)
        until(lambda: watchers.state("paper")["watching"])
    finally:
        watchers.stop()


def test_without_a_watcher_alive_and_synced_the_request_says_there_is_no_channel(
    kernel: Kernel, tmp_path: Path
) -> None:
    watchers = Watchers(kernel, lambda workspace, line: None, spawn=lambda workspace: script(NEVER_SYNCED))
    try:
        with pytest.raises(NoChannel):
            watchers.request("paper", "servers", [], {})  # no container runs: no watcher at all
        running(kernel, tmp_path)
        watchers.keep()
        until(lambda: watchers._watching["paper"].alive())
        with pytest.raises(NoChannel):
            watchers.request("paper", "servers", [], {})  # a watcher not yet synced carries nothing
    finally:
        watchers.stop()


def test_a_workspace_whose_watcher_cannot_start_leaves_the_others_watched_and_is_said_once(
    kernel: Kernel, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Docker's last reading said its container runs, but it no longer did: the round went on to the others (on the
    owner's machine, 2026-10-26, it raised and no workspace after it got a watcher, its traceback logged every three
    seconds)."""
    running(kernel, tmp_path / "paper", "paper")
    running(kernel, tmp_path / "thesis", "thesis")

    def spawn(workspace: str) -> "subprocess.Popen[bytes]":
        if workspace == "paper":
            raise WorkspaceUnavailable("paper's container does not run: `clank workspace open` starts it")
        return script(NEVER_SYNCED)

    watchers = Watchers(kernel, lambda workspace, line: None, spawn=spawn)
    try:
        with caplog.at_level(logging.WARNING, logger=watch.__name__):
            watchers.keep()
            watchers.keep()
        assert watchers._watching["thesis"].alive(), "the next workspace is watched all the same"
        said = [record.getMessage() for record in caplog.records]
        assert said == [
            "the watcher of paper did not start: paper's container does not run: `clank workspace open` starts it"
        ], "once, without a traceback"
    finally:
        watchers.stop()
