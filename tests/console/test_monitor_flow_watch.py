"""Design 0013 §12 and §15 (decisions 0100 and 0101): building a flow with the model, watched from the console. `n` on
the Flow view opens a planning and the console keeps its terminal (with a planning open, asked first whether to set it
aside, Esc leaving it untouched; a second `n` while one starts does nothing): over SSH the view says to run
`clank flow attach` in another terminal; in Windows Terminal its window is split for it (the command checked, `wt` never
run); when the split cannot run, the message; in VS Code's terminal, Clank's VS Code window. The Flow view draws the
planning: the heading says it is being built and which draft it shows, Selected becomes "Building it with the model"
with its steps and a Live box for the planning session, the keys bar shows the keys that act while it is built, Waiting
for you says how to talk with the model, the latest draft is drawn even when refused; for a planning that failed, how to
try it again; Enter opens the Session view on the planning session, Esc comes back. Frames at 128, 88 and 60 columns.
Everything runs against a service served in the test; nothing runs OpenCode or Windows Terminal."""

import os
import re
import sys
import threading
from collections.abc import Sequence
from datetime import UTC, timedelta
from pathlib import Path
from typing import Any

import pytest
from textual.pilot import Pilot
from textual.widgets import Label

from clank.client import Client
from clank.components.agents.console import flowpanels
from clank.components.agents.console.flowpanels import LinesView
from clank.components.agents.console.monitor import MonitorPage
from clank.components.flows.building import BuildError
from clank.components.flows.verdicts import AGENT
from clank.console.app import ClankConsole
from clank.console.confirm import ConfirmScreen
from clank.console.panel import Panel
from clank.console.snapshot import render_text
from clank.kernel import where
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.components.flows.test_flow_built import drafted
from tests.console.frames import assert_frame, frame_when, settle
from tests.support.flowshapes import BRIEF, NOW, OWNER, WORKSPACE

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]
FLOW = f"{WORKSPACE}/flow"


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


def make(client: Client, home: Home, folder: Path, **kwargs: Any) -> ClankConsole:
    return ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, folder=str(folder), **kwargs)


async def flow_view(pilot: Pilot[Any], app: ClankConsole) -> MonitorPage:
    await frame_when(pilot, app, "Fake Docker")
    await pilot.press("f10")
    page = app.query_one("#page-monitor", MonitorPage)
    await settle(pilot, lambda: page.display)
    page.show_view("flow")
    return page


def message(app: ClankConsole) -> str:
    return str(app.query_one("#message", Label).content)


def heading_of(app: ClankConsole) -> str:
    return str(app.query_one("#monitor-heading", Label).content)


def lines_of(app: ClankConsole, id: str) -> str:
    """A panel's lines, joined, its wraps undone."""
    text = str(app.query_one(id, LinesView).render())
    return re.sub(r"\s+", " ", " ".join(line.strip() for line in text.splitlines()))


def not_handed(argv: Sequence[str]) -> int:
    raise AssertionError(f"the console handed its terminal to {list(argv)[:3]}")


async def test_n_over_ssh_opens_a_planning_keeps_the_terminal_and_says_how_to_attach(
    kernel: Kernel, client: Client, home: Home, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_on(kernel, folder)
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.2 51022 10.0.0.9 22")
    monkeypatch.setenv("WT_SESSION", "0f3a")  # set too, and no split over SSH
    app = make(client, home, folder, terminal=not_handed)
    attach = f"cd {folder} then clank flow attach"
    async with app.run_test(size=(160, 50)) as pilot:
        await flow_view(pilot, app)
        await settle(pilot, lambda: "has no flow yet" in heading_of(app))
        await pilot.press("n")
        await settle(pilot, lambda: f"talk with the model: in another terminal, {attach}" in message(app))
        await settle(pilot, lambda: "building with the model · no draft yet" in heading_of(app))
        await frame_when(pilot, app, "the model has drafted no flow yet")
        bare = attach.replace(" ", "")  # a long folder wraps anywhere
        await settle(pilot, lambda: bare in lines_of(app, "#monitor-flow-waiting-lines").replace(" ", ""))
    planning = kernel.parts["flows"].building.planning(FLOW)
    assert planning is not None
    assert (planning.where, planning.status) == ("attach", "waiting")


async def test_n_in_windows_terminal_splits_its_window_for_clank_flow_attach_else_says_how(
    kernel: Kernel, client: Client, home: Home, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_on(kernel, folder)
    monkeypatch.setenv("WT_SESSION", "0f3a")
    split: list[list[str]] = []
    answers = iter(["", "wt refused the split (exit 1)"])

    def launched(argv: Sequence[str]) -> str:
        split.append(list(argv))
        return next(answers)

    monkeypatch.setattr(where, "launch_split", launched)
    app = make(client, home, folder, terminal=not_handed)
    async with app.run_test(size=(160, 50)) as pilot:
        await flow_view(pilot, app)
        await pilot.press("n")
        await settle(pilot, lambda: "OpenCode opens in a pane on the right" in message(app))
        await pilot.press("n")  # a planning is open: asked first
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("enter")
        await settle(pilot, lambda: "wt refused the split" in message(app))
        assert "clank flow attach" in message(app), "the message instead"
    assert split[0] == where.split_argv(str(folder), WORKSPACE, sys.executable, os.environ)
    assert split[0][:7] == ["wt", "-w", "0", "split-pane", "-V", "-d", str(folder)]
    older = kernel.parts["flows"].building.planning(FLOW)
    assert older is not None
    assert older.status == "set aside"
    assert len(split) == 2


async def test_n_with_a_planning_open_asks_first_and_esc_leaves_it_open_untouched(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    watched(kernel, clock, folder, monkeypatch)
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.2 51022 10.0.0.9 22")
    app = make(client, home, folder, terminal=not_handed)
    async with app.run_test(size=(160, 50)) as pilot:
        await flow_view(pilot, app)
        await settle(pilot, lambda: "building with the model" in heading_of(app))
        await pilot.press("n")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        asked = render_text(app)
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, ConfirmScreen))
    assert "a planning is open: myproject/flow, talking" in asked
    assert "Start a new one and set it aside?" in asked
    building = kernel.parts["flows"].building
    planning = building.planning(FLOW)
    assert planning is not None
    assert (planning.status, planning.session) == ("talking", "ses_plan"), "untouched"
    assert [each.flow for each in building.plannings.all()] == [FLOW], "no other started"


async def test_a_second_n_while_a_planning_starts_does_nothing(
    kernel: Kernel, client: Client, home: Home, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_on(kernel, folder)
    monkeypatch.setenv("WT_SESSION", "0f3a")
    pressed, split = threading.Event(), []

    def launched(argv: Sequence[str]) -> str:
        split.append(list(argv))
        pressed.wait(5)  # the split still in flight when n is pressed again
        return ""

    monkeypatch.setattr(where, "launch_split", launched)
    app = make(client, home, folder, terminal=not_handed)
    async with app.run_test(size=(160, 50)) as pilot:
        await flow_view(pilot, app)
        await pilot.press("n")
        await settle(pilot, lambda: len(split) == 1)
        await pilot.press("n", "N")
        pressed.set()
        await settle(pilot, lambda: "OpenCode opens in a pane on the right" in message(app))
        await pilot.pause(0.3)
        assert not isinstance(app.screen, ConfirmScreen), "nothing asked: the second n did nothing"
    assert len(split) == 1
    assert [each.flow for each in kernel.parts["flows"].building.plannings.all()] == [FLOW]
    assert not any(each.type == "agents.vscode" for each in kernel.operations.find(None, 10))


async def test_n_in_vs_codes_terminal_opens_clanks_vs_code_window(
    kernel: Kernel, client: Client, home: Home, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_on(kernel, folder)
    monkeypatch.setenv("TERM_PROGRAM", "vscode")
    app = make(client, home, folder, terminal=not_handed)
    async with app.run_test(size=(160, 50)) as pilot:
        await flow_view(pilot, app)
        await pilot.press("n")
        await settle(pilot, lambda: any(each.type == "agents.vscode" for each in kernel.operations.find(None, 10)))
    [opened] = [each for each in kernel.operations.find(None, 10) if each.type == "agents.vscode"]
    assert opened.params["folder"] == str(folder)


def watched(kernel: Kernel, clock: FakeClock, folder: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A planning beside the console, its session talking, its brief written, its first draft refused."""
    clock.set(NOW)
    workspace_on(kernel, folder)
    building = kernel.parts["flows"].building
    building.open(WORKSPACE, "", "attach", actor=OWNER)
    building._change(FLOW, status="talking", session="ses_plan", port=4096)
    (folder / "BRIEF.md").write_bytes(BRIEF.encode("utf-8"))
    written = (NOW + timedelta(minutes=3)).timestamp()
    os.utime(folder / "BRIEF.md", (written, written))  # its time, in the frames
    draft = drafted(title="A new simulation study")
    draft["boxes"][1]["when_done"] = "wait"
    with pytest.raises(BuildError):
        building.draft(WORKSPACE, draft, actor=AGENT)
    agents = kernel.parts["agents"]
    step = {
        "id": "msg_plan_3",
        "kind": "step",
        "at": [0, "msg_plan_3", 0],
        "n": 3,
        "finish": "tool-calls",
        "ended": "finished",
        "together": 2,
    }  # shaped as the session flow's, the Guide reads it too
    monkeypatch.setattr(
        agents.flows,
        "view",
        lambda workspace, session: (
            {"head": {"status": "busy", "calls": 7, "steps": 3}, "nodes": [step]} if session == "ses_plan" else None
        ),
    )
    monkeypatch.setattr(agents, "now", lambda workspace, session: {
        "session": session, "state": "answering", "phase": "answering", "working": True, "step": 4,
        "speed": {"now": 41.0, "steps": [44.0, 48.0]}, "guard": {"on": True}})  # fmt: skip


@pytest.mark.parametrize(
    ("size", "f5", "name"),
    [((160, 50), False, "monitor-flow-watch-128"), ((160, 50), True, "monitor-flow-watch-88"),
     ((82, 60), False, "monitor-flow-watch-60")],
)  # fmt: skip
async def test_the_flow_view_draws_the_planning_its_steps_its_live_session_and_the_refused_draft(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path, monkeypatch: pytest.MonkeyPatch,
    size: tuple[int, int], f5: bool, name: str,
) -> None:  # fmt: skip
    watched(kernel, clock, folder, monkeypatch)
    app = make(client, home, folder)
    async with app.run_test(size=size) as pilot:
        page = await flow_view(pilot, app)
        if f5:
            await pilot.press("f5")
        await settle(pilot, lambda: "reading the folder: 7 tool calls so far" in lines_of(
            app, "#monitor-flow-selected-lines"))  # fmt: skip
        await settle(pilot, lambda: page.flows.now is not None)
        await settle(pilot, lambda: page.flows.context is not None)  # its context read: drawn the same however late
        frame = await frame_when(pilot, app, "Building it with the model", "context no model runs")
        steps = lines_of(app, "#monitor-flow-selected-lines")
        drawn = str(app.query_one("#monitor-flow-selected-lines", LinesView).render())
        heading = heading_of(app)
        note = page.query_one("#monitor-flow-boxes", Panel).note
        live = app.query_one("#monitor-flow-live").display
    assert heading == "flow “A new simulation study” · building with the model · DRAFT 1, refused · workspace myproject"
    assert note.startswith("DRAFT 1 · refused")
    assert "BRIEF.md written" in steps
    assert "draft 1" in steps
    assert "boxes.1.when_done: a built flow waits only at its end: leave" in steps, "whole, wrapped"
    assert "…" not in drawn, drawn
    assert live, "the planning session's Live box"
    keys = frame.splitlines()[-1]
    assert "n new flow" in keys, "the keys that act while it is built, at every width"
    for refused in ("p pause", "e edit", "r run", "o open", "h run log"):
        assert refused not in keys, refused
    assert_frame(frame, name)


def test_waiting_for_you_says_how_to_try_a_planning_that_failed_again() -> None:
    planning = {"status": "failed", "why": "no OpenCode window answered in 60 seconds",
                "attach": "cd /work/paper then clank flow attach"}  # fmt: skip
    said = " ".join(line.plain.strip() for line in flowpanels.talking(planning, 200))
    assert said.startswith("✗ the planning failed: no OpenCode window answered in 60 seconds")
    assert "to try it again, in another terminal, cd /work/paper then clank flow attach; or n opens another" in said


def test_waiting_for_you_says_to_wait_while_the_planning_session_starts_on_its_window() -> None:
    planning = {"status": "opening", "why": "", "attach": "cd /work/paper then clank flow attach", "session": None}
    said = " ".join(line.plain.strip() for line in flowpanels.talking(planning, 200))
    assert "its session starts on the OpenCode window it was attached to: wait for it there" in said
    assert "in another terminal" not in said


def test_waiting_for_you_says_a_vs_code_planning_talks_in_clanks_vs_code_window() -> None:
    planning = {"status": "waiting", "where": "vscode", "why": "", "session": None,
                "attach": "cd /work/paper then clank flow attach"}  # fmt: skip
    said = " ".join(line.plain.strip() for line in flowpanels.talking(planning, 200))
    assert "OpenCode opens in Clank's VS Code window, on this planning: talk with the model there" in said
    assert "in another terminal" not in said
    said = " ".join(line.plain.strip() for line in flowpanels.talking({**planning, "status": "opening"}, 200))
    assert "its session starts on OpenCode in Clank's VS Code window: wait for it there" in said
    assert "attached" not in said


def test_building_it_says_how_to_try_a_planning_that_failed_again_where_a_stacked_page_shows_it() -> None:
    view = {
        "planning": {
            "status": "failed",
            "why": "no OpenCode window answered in 60 seconds",
            "attach": "cd /work/paper then clank flow attach",
            "steps": [{"kind": "failed", "said": "failed: no OpenCode window answered in 60 seconds"}],
        }
    }
    said = " ".join(line.plain.strip() for line in flowpanels.building(view, 200, None))
    assert "failed: no OpenCode window answered in 60 seconds" in said
    assert "to try it again, in another terminal, cd /work/paper then clank flow attach; or n opens another" in said


async def test_enter_opens_the_session_view_on_the_planning_session_and_backspace_comes_back(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    watched(kernel, clock, folder, monkeypatch)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await flow_view(pilot, app)
        await settle(pilot, lambda: "Building it with the model" in str(
            page.query_one("#monitor-flow-selected", Panel).title))  # fmt: skip
        await pilot.press("enter")
        await settle(pilot, lambda: page.view == "session")
        await settle(pilot, lambda: page.flows.opened_from == "planning")
        await pilot.press("backspace")
        await settle(pilot, lambda: page.view == "flow")


async def test_help_says_n_starts_the_planning_beside_the_console(
    kernel: Kernel, client: Client, home: Home, folder: Path
) -> None:
    workspace_on(kernel, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await flow_view(pilot, app)
        explained = " ".join(page.explain()[1])
    keys = {key.key: key.help for key in MonitorPage.KEYS}
    for said in (keys["n"], keys["N"]):
        assert "this terminal" not in said, said
    assert "beside the console" in keys["n"]
    assert "over SSH, talk with the model from another terminal: `clank flow attach`" in keys["n"]
    assert "in Windows Terminal, a pane split off on the right" in keys["n"]
    assert "asked first" in keys["n"]
    assert "the console steps aside" not in explained
    assert "over SSH, always this terminal" not in explained
    assert "n starts a planning beside the console" in explained
