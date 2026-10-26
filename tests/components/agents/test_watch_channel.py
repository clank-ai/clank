"""Design 0023 §4 (decision 0140): the service's request channel to a workspace's watcher, run against the real bridge
on this machine and a fake OpenCode server. A request written on the watcher's input is answered with its id, its
answer the bridge's own (a refusal included), and the review never hears it; a watcher that does not answer within
`REQUEST_SECONDS` is ended, so it is started again, and the request raises `Unanswered`; a workspace without a watcher
alive and synced raises `NoChannel`, so the caller sends the request through a process of its own; so does a
request made from the watcher's own reader thread (a line heard), which could never see its answer."""

import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

from clank import registry
from clank.components.agents import watch
from clank.components.agents.watch import NoChannel, Unanswered, Watcher, Watchers
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import image_folder, names
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import background_flags
from tests.fakes.opencode import FakeOpenCode
from tests.fakes.platform import FakePlatform, container

BRIDGE = image_folder() / "bridge.py"
OWNER = Actor(kind="user", via="console")
SYNCED_AND_DEAF = (
    "import sys, json; print(json.dumps({'type': 'synced', 'ports': []}), flush=True)\n"
    "for _ in sys.stdin: pass\n"
)  # a watcher that says it is synced, then answers nothing until its input closes
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


def bridge_watch(ports: str) -> "subprocess.Popen[bytes]":
    """The real bridge's watch, on this machine, reaching the fake servers on `ports`."""
    import os

    return subprocess.Popen(
        [sys.executable, str(BRIDGE), "watch"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, creationflags=background_flags(), env={**os.environ, "CLANK_BRIDGE_PORTS": ports},
    )  # fmt: skip


def script(source: str) -> "subprocess.Popen[bytes]":
    return subprocess.Popen(
        [sys.executable, "-c", source], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        creationflags=background_flags(),
    )  # fmt: skip


def running(kernel: Kernel, folder: Path) -> None:
    """Workspace paper on `folder`, its container running (the fake platform)."""
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=OWNER)
    platform: FakePlatform = kernel.parts["workspaces"].platform
    platform.containers.append(container(names(kernel.home.id).container("paper")))
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


def test_a_watcher_that_does_not_answer_is_ended_and_started_again_and_the_request_says_so(
    kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    running(kernel, tmp_path)
    monkeypatch.setattr(watch, "REQUEST_SECONDS", 0.3)
    monkeypatch.setattr(watch, "RETRY_SECONDS", (0.2,))
    started: list[str] = []

    def spawn(workspace: str) -> "subprocess.Popen[bytes]":
        started.append(workspace)
        return script(SYNCED_AND_DEAF)

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
