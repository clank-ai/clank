"""Design 0004 §5: one OpenCode window per workspace. Opening OpenCode in a terminal (VS Code's, or the console's) first
closes every OpenCode window open in the workspace's container, so there is only ever one and the mode switches reach
it (found live, 2026-10-16: five windows, two of them relaunched by VS Code with a port another already had, so Clank
could not reach the one in front of the owner). OpenCode without a terminal (`opencode serve`, the phone's) is left
alone; a window that does not end when asked is ended. The workspace's record turns it off; the review view says which
it is."""

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest

from clank import registry
from clank.components.agents import sessions as agents_sessions
from clank.components.agents.service import Agents
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import BRIDGE_PROGRAM, names
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import Answer
from tests.fakes.platform import FakePlatform, container

YOU = Actor(kind="user", via="console")
WINDOW = "opencode --port {} --hostname 127.0.0.1"
HEADLESS = "opencode serve --port 4099 --hostname 127.0.0.1"


class Inside:
    """What runs in the workspace's container: processes by their command lines, with `pgrep -f` and `pkill -f` over
    them as procps has them (an extended regular expression searched in each line), and the bridge's free port."""

    def __init__(self, *lines: str, stubborn: str = "") -> None:
        self.running = {100 + index: line for index, line in enumerate(lines)}
        self.stubborn = stubborn  # a command line that a TERM does not end
        self.signals: list[str] = []

    def __call__(self, argv: list[str], given: bytes | None) -> Answer:
        if argv[:3] == ["python3", BRIDGE_PROGRAM, "free-port"]:
            taken = " ".join(self.running.values()) + " "
            port = next(port for port in range(4096, 4128) if f"--port {port} " not in taken)
            return Answer(0, json.dumps({"ok": True, "port": port}), "")
        if argv[0] not in ("pgrep", "pkill"):
            return Answer(1, "", f"the fake container does not run {argv[0]}")
        found = {pid: line for pid, line in self.running.items() if re.search(argv[-1], line)}
        if argv[0] == "pgrep":
            return Answer(0 if found else 1, "".join(f"{pid}\n" for pid in found), "")
        self.signals.append(argv[1])
        for pid, line in found.items():
            if argv[1] == "-KILL" or line != self.stubborn:
                del self.running[pid]
        return Answer(0 if found else 1, "", "")


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def opened(kernel: Kernel, platform: FakePlatform, folder: Path, **values: object) -> None:
    """The folder's workspace, its container running."""
    kernel.settings.write("workspace", "paper", {"path": str(folder), **values}, base=None, actor=YOU)
    name = names(kernel.home.id).container("paper")
    platform.containers.append(container(name, labels={"clank.home": kernel.home.id}))


def test_opening_opencode_in_a_terminal_first_closes_the_windows_open_in_its_workspace_but_not_one_without(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    inside = Inside(WINDOW.format(4096), WINDOW.format(4096), WINDOW.format(4097), HEADLESS)
    platform.inside = inside
    opened(kernel, platform, tmp_path)
    agents: Agents = kernel.parts["agents"]
    assert kernel.settings.get("workspace", "paper").record.model_dump()["one_window"] is True, "on unless turned off"
    assert agents.review.view("paper")["one_window"] is True

    prepared = agents.prepare("paper")
    assert list(inside.running.values()) == [HEADLESS], "the phone's OpenCode, which has no terminal, is left"
    assert inside.signals == ["-TERM"]
    assert (prepared["one_window"], prepared["closed"], prepared["port"]) == (True, 3, 4096), "its port is free again"
    assert prepared["argv"][-4:-2] == ["--port", "4096"]
    assert any("closed the 3 OpenCode windows open in paper first" in note for note in prepared["notes"])


def test_a_window_that_does_not_end_when_asked_is_ended(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agents_sessions, "CLOSE_SECONDS", 0.2)
    inside = Inside(WINDOW.format(4096), stubborn=WINDOW.format(4096))
    platform.inside = inside
    opened(kernel, platform, tmp_path)
    prepared = kernel.parts["agents"].prepare("paper")
    assert (inside.signals, inside.running, prepared["closed"]) == (["-TERM", "-KILL"], {}, 1)


def test_with_one_window_turned_off_opening_opencode_adds_a_window_and_closes_none(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    inside = Inside(WINDOW.format(4096))
    platform.inside = inside
    opened(kernel, platform, tmp_path, one_window=False)
    agents: Agents = kernel.parts["agents"]
    prepared = agents.prepare("paper")
    assert (inside.signals, len(inside.running)) == ([], 1)
    assert (prepared["one_window"], prepared["closed"], prepared["port"]) == (False, 0, 4097)
    assert agents.review.view("paper")["one_window"] is False
