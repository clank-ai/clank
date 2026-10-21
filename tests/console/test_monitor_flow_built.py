"""Design 0013 §12 and §15 (decisions 0098, 0099 and 0100): a flow built with the model, in the Monitor's Flow view.
The view follows it once built; Waiting for you says it was built with the model, to look, then press `r`, and lists
the check's warnings of its last draft whole, wrapped, never cut; frames at 128 and 88 columns and below 70. `r` on a
flow that has not run starts it at its first box, once confirmed. `n` opens a planning beside the console, never in its
terminal, even in a workspace with no flow yet, and the view becomes the flow once the model's draft is written; `N`
opens it in Clank's VS Code window, but over SSH nothing opens on the PC's own screen, the message saying how to
attach. `clank console --page monitor --view flow` opens on the Flow view, for a terminal that keeps F10 for itself,
and `n` and `r` act there. Everything runs against a service served in the test; nothing runs OpenCode."""

import re
from collections.abc import Sequence
from datetime import UTC
from pathlib import Path
from typing import Any

import pytest
from textual.pilot import Pilot
from textual.widgets import Label

from clank.client import Client
from clank.components.agents.console.flowpanels import LinesView
from clank.components.agents.console.monitor import MonitorPage
from clank.components.flows.verdicts import AGENT
from clank.console.app import ClankConsole
from clank.console.confirm import ConfirmScreen
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.components.flows.test_flow_built import drafted
from tests.console.frames import assert_frame, frame_when, settle
from tests.support.flowshapes import BRIEF, NOW, OWNER, WORKSPACE

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]
FLOW = f"{WORKSPACE}/study"
WARNING = "plan sees data/grid.csv, which is not in the folder, and neither plan nor a box before it writes it"
ARGV = ["docker", "exec", "-it", "clank-myproject", "opencode", "--port", "4096"]


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """The folder the console is started in: named `paper`, as in every frame."""
    return tmp_path / "paper"


@pytest.fixture(autouse=True)
def owner_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The console's terminal is neither VS Code's, Windows Terminal's nor reached over SSH, unless a test says so."""
    for name in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY", "TERM_PROGRAM", "WT_SESSION"):
        monkeypatch.delenv(name, raising=False)


def workspace_on(kernel: Kernel, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    kernel.settings.write("workspace", WORKSPACE, {"path": str(folder)}, base=None, actor=OWNER)


def install_built(kernel: Kernel, clock: FakeClock, folder: Path) -> None:
    """The flow "A new simulation study", built with the model and not run yet; its plan sees a file nothing gives it,
    which the check warns of."""
    clock.set(NOW)
    workspace_on(kernel, folder)
    building = kernel.parts["flows"].building
    building.begin(WORKSPACE, "study", "here", actor=OWNER)
    (folder / "BRIEF.md").write_bytes(BRIEF.encode("utf-8"))  # written with the model
    draft = drafted(title="A new simulation study")
    draft["boxes"][1]["sees"] = ["BRIEF.md", "data/grid.csv"]
    building.draft(WORKSPACE, draft, actor=AGENT)


def opening(kernel: Kernel, folder: Path) -> list[dict[str, Any]]:
    """The service's planning opened as it would be, the window's command made up (no container runs): each opening's
    arguments, kept."""
    building = kernel.parts["flows"].building
    opened: list[dict[str, Any]] = []

    def opens(workspace: str, name: str, where: str, *, actor: Actor, aside: bool = False) -> dict[str, Any]:
        planning = building.begin(workspace, name, where, actor=actor, aside=aside)
        opened.append({"workspace": workspace, "name": name, "where": where})
        said = {"flow": planning.flow, "name": planning.name, "where": where, "folder": str(folder),
                "first_message": "first-message.md"}  # fmt: skip
        if where == "here":
            return {**said, "window": "started", "argv": ARGV, "program": "OpenCode", "port": 4096,
                    "model": "frontier 262K", "notes": []}  # fmt: skip
        if where == "attach":
            return {**said, "window": "waits", "port": None, "attach": f"cd {folder} then clank flow attach"}
        return {**said, "window": "waits", "port": None}

    building.open = opens
    return opened


def make(client: Client, home: Home, folder: Path, **kwargs: Any) -> ClankConsole:
    return ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, folder=str(folder), **kwargs)


async def flow_view(pilot: Pilot[Any], app: ClankConsole) -> MonitorPage:
    """The Monitor, on its Flow view."""
    await frame_when(pilot, app, "Fake Docker")
    await pilot.press("f10")
    page = app.query_one("#page-monitor", MonitorPage)
    await settle(pilot, lambda: page.display)
    page.show_view("flow")
    return page


def waiting_lines(app: ClankConsole) -> list[str]:
    view = app.query_one("#monitor-flow-waiting-lines", LinesView)
    return [line.rstrip() for line in str(view.render()).splitlines()]


def message(app: ClankConsole) -> str:
    return str(app.query_one("#message", Label).content)


@pytest.mark.parametrize(
    ("size", "f5", "name"),
    [((160, 50), False, "monitor-flow-built-128"), ((160, 50), True, "monitor-flow-built-88"),
     ((82, 60), False, "monitor-flow-built-60")],
)  # fmt: skip
async def test_a_built_flow_shows_with_its_boxes_its_models_and_its_warnings_whole(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path, size: tuple[int, int], f5: bool,
    name: str,
) -> None:  # fmt: skip
    install_built(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=size) as pilot:
        await flow_view(pilot, app)
        if f5:
            await pilot.press("f5")
        await settle(pilot, lambda: any("Built with the model" in line for line in waiting_lines(app)))
        frame = await frame_when(pilot, app, "A new simulation study")
        lines = waiting_lines(app)
        heading = str(app.query_one("#monitor-heading", Label).content)
    assert heading.startswith("flow “A new simulation study” · workspace myproject · not run yet")
    assert not any("…" in line for line in lines), "nothing in Waiting for you is cut"
    assert WARNING in re.sub(r"\s+", " ", " ".join(line.strip() for line in lines))
    assert "look, then r to run" in re.sub(r"\s+", " ", " ".join(line.strip() for line in lines))
    assert_frame(frame, name)


async def test_r_starts_a_flow_that_has_not_run_once_confirmed(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    install_built(kernel, clock, folder)
    runner = kernel.parts["flows"].runner
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await flow_view(pilot, app)
        await settle(pilot, lambda: any("Built with the model" in line for line in waiting_lines(app)))
        await pilot.press("r")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("enter")
        await settle(pilot, lambda: runner.runs.latest(FLOW) is not None)
    started = runner.runs.latest(FLOW)
    assert started is not None
    assert started.started_by == Actor(kind="user", via="console")


def never(argv: Sequence[str]) -> int:
    raise AssertionError(f"the console handed its terminal to {list(argv)[:3]}")


async def test_n_opens_a_planning_beside_the_console_even_with_no_flow_yet_and_shows_the_flow_once_built(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    clock.set(NOW)
    workspace_on(kernel, folder)
    opened = opening(kernel, folder)
    app = make(client, home, folder, terminal=never)
    async with app.run_test(size=(160, 50)) as pilot:
        await flow_view(pilot, app)
        await settle(pilot, lambda: "has no flow yet" in str(app.query_one("#monitor-heading", Label).content))
        await pilot.press("n")
        await settle(pilot, lambda: "clank flow attach" in message(app))
        await settle(pilot, lambda: "building with the model" in str(app.query_one("#monitor-heading", Label).content))
        (folder / "BRIEF.md").write_bytes(BRIEF.encode("utf-8"))  # the model writes the brief, then the flow
        kernel.parts["flows"].building.draft(WORKSPACE, drafted(title="A new simulation study"), actor=AGENT)
        await settle(pilot, lambda: any("Built with the model" in line for line in waiting_lines(app)))
        heading = str(app.query_one("#monitor-heading", Label).content)
    assert opened == [{"workspace": WORKSPACE, "name": "", "where": "attach"}]
    assert heading.startswith("flow “A new simulation study” · workspace myproject · not run yet")


async def test_capital_n_opens_clanks_vs_code_window_but_over_ssh_says_how_to_attach(
    kernel: Kernel, client: Client, home: Home, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_on(kernel, folder)
    opened = opening(kernel, folder)
    app = make(client, home, folder, terminal=never)
    async with app.run_test(size=(160, 50)) as pilot:
        await flow_view(pilot, app)
        await pilot.press("N")
        await settle(pilot, lambda: any(each.type == "agents.vscode" for each in kernel.operations.find(None, 10)))
        monkeypatch.setenv("SSH_CONNECTION", "10.0.0.2 51022 10.0.0.9 22")
        await settle(pilot, lambda: "building with the model" in str(app.query_one("#monitor-heading", Label).content))
        await pilot.press("N")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))  # the planning open, set aside once asked
        await pilot.press("enter")
        await settle(pilot, lambda: "in another terminal, cd" in message(app))
    assert [each["where"] for each in opened] == ["vscode", "attach"]
    vscode = [each for each in kernel.operations.find(None, 10) if each.type == "agents.vscode"]
    assert len(vscode) == 1, "over SSH, no window on the PC's own screen"
    assert vscode[0].params["folder"] == str(folder)


async def test_the_console_opens_on_the_flow_view_where_n_and_r_act(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    install_built(kernel, clock, folder)
    app = make(client, home, folder, page="monitor", view="flow")
    async with app.run_test(size=(160, 50)) as pilot:
        page = app.query_one("#page-monitor", MonitorPage)
        await settle(pilot, lambda: page.view == "flow")
        await settle(pilot, lambda: any("Built with the model" in line for line in waiting_lines(app)))
        await pilot.press("r")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
