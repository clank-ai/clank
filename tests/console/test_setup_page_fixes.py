"""Design 0028 §4 and §5: the Setup page does the next step on one key. `s` starts Docker Desktop through its own
command, the service's start; `t` runs the command shown, one that needs administrator rights, in this terminal, asked
first in a window that names it: the console steps aside for it (headless, it runs at once), sudo asks for the password
itself, and the console says how it ended and what the person does next; Esc in the window runs nothing. A key that has
nothing to do says why."""

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest
from textual.widgets import Label

from clank.client import Client
from clank.components.agents import checklist, vscode
from clank.components.workspaces.adapters.platform import PlatformSetup
from clank.console.app import ClankConsole
from clank.console.confirm import ConfirmScreen
from clank.console.snapshot import render_text
from clank.kernel.home import Home
from tests.console.frames import FOLDER, assert_frame, frame_when, settle
from tests.fakes.platform import FakePlatform

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
START = ("sudo", "systemctl", "start", "docker")
ENABLE = ("sudo", "systemctl", "enable", "docker")
JOIN = ("sudo", "usermod", "-aG", "docker", "ada")
TITLE = "Clank's setup"


class Terminal:
    """The console's terminal in a test: each program it was handed, and what it answers."""

    def __init__(self) -> None:
        self.ran: list[list[str]] = []

    def __call__(self, argv: Sequence[str]) -> int:
        self.ran.append(list(argv))
        return 0


@pytest.fixture(autouse=True)
def this_computer(monkeypatch: pytest.MonkeyPatch) -> None:
    """No VS Code and no installer's tool found, whatever this machine has."""
    monkeypatch.setattr(vscode, "which", lambda name: None)
    monkeypatch.setattr(checklist, "found_tools", lambda: frozenset())


def make(client: Client, home: Home, ran: Terminal) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page="setup", terminal=ran)
    app.folder = FOLDER
    return app


def window_said(app: ClankConsole) -> str:
    """What the window over the page says, its lines joined: words a narrow window wraps are found whole."""
    return " ".join(" ".join(str(label.content).split()) for label in app.screen.query(Label).results(Label))


def engine(platform: FakePlatform, state: str, setup: PlatformSetup) -> None:
    """The fake platform as Docker Engine is: the system's, which Clank never starts, with its owner's commands."""
    platform.state = state
    platform.starts = False
    platform.setup = setup
    platform.detail = "start it with `sudo systemctl start docker`"


async def test_s_starts_docker_desktop_through_its_own_start(
    client: Client, home: Home, platform: FakePlatform
) -> None:
    platform.state = "stopped"
    ran = Terminal()
    app = make(client, home, ran)
    async with app.run_test(size=(120, 40)) as pilot:
        frame = await frame_when(pilot, app, TITLE, "press s")
        assert "Next:  s start Docker" in frame
        await pilot.press("s")
        await settle(pilot, lambda: "start" in platform.calls)
        assert ran.ran == [], "Docker Desktop's own start: no command in the terminal"


async def test_t_asks_first_naming_the_command_then_runs_it_in_this_terminal(
    client: Client, home: Home, platform: FakePlatform
) -> None:
    engine(platform, "stopped", PlatformSetup(at_boot=True, in_group=True, start=START, boot=ENABLE, join=JOIN))
    ran = Terminal()
    app = make(client, home, ran)
    async with app.run_test(size=(120, 40)) as pilot:
        frame = await frame_when(pilot, app, TITLE, "press t")
        assert "t run `sudo systemctl start docker` in this terminal" in frame
        assert_frame(frame, "setup-engine-stopped")
        await pilot.press("t")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        assert "Run `sudo systemctl start docker` in this terminal?" in render_text(app)
        assert "sudo asks for your password there itself" in window_said(app)
        assert ran.ran == [], "nothing before the yes"
        await pilot.pause(0.1)
        await pilot.press("enter")
        await settle(pilot, lambda: ran.ran == [list(START)])
        await settle(pilot, lambda: "`sudo systemctl start docker` is done" in render_text(app))


async def test_esc_in_the_window_runs_nothing(client: Client, home: Home, platform: FakePlatform) -> None:
    engine(platform, "stopped", PlatformSetup(at_boot=True, in_group=True, start=START, boot=ENABLE, join=JOIN))
    ran = Terminal()
    app = make(client, home, ran)
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, TITLE, "press t")
        await pilot.press("t")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.pause(0.1)
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, ConfirmScreen))
        await pilot.pause(0.2)
        assert ran.ran == []


async def test_after_joining_the_docker_group_the_console_says_to_log_out_and_in_once(
    client: Client, home: Home, platform: FakePlatform
) -> None:
    engine(platform, "no access", PlatformSetup(at_boot=True, in_group=False, start=START, boot=ENABLE, join=JOIN))
    ran = Terminal()
    app = make(client, home, ran)
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, TITLE, "press t")
        await pilot.press("t")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        assert "root's rights" in window_said(app), "Docker's own warning, before the yes"
        await pilot.pause(0.1)
        await pilot.press("enter")
        await settle(pilot, lambda: ran.ran == [list(JOIN)])
        await settle(pilot, lambda: "Next: log out and in once" in render_text(app))


async def test_a_key_with_nothing_to_do_says_why(client: Client, home: Home) -> None:
    ran = Terminal()
    app = make(client, home, ran)
    async with app.run_test(size=(120, 40)) as pilot:
        await frame_when(pilot, app, TITLE, "Next:")
        await pilot.press("t")
        await settle(pilot, lambda: "no command waits to run in this terminal" in render_text(app))
        await pilot.press("s")
        await settle(pilot, lambda: "Docker needs no start from here" in render_text(app))
        assert ran.ran == []
