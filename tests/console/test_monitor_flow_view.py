"""Design 0013 §12 and §14 step 6 (board D1), with design 0012 §2 (the page, its keys, its room, its redraws): the
Monitor's Flow view shows the flow its folder follows, read from the service (`GET /flows/view`) once a second while
the view is on screen: the heading names the flow, its workspace, its run and its start; Flow draws its boxes and
lines, its note how many boxes are done, running and waiting; Selected says the box chosen (the running one until the
arrows choose another) with a Live panel while it runs; Models in this flow, Waiting for you, The brief, checked,
Deliverables and Ahead say theirs. Frames: board D1's moment at 128 and 88 columns and below 70 (the list). Without a
flow, the view says why. Nothing redraws while nothing changes; a running box redraws at most four times a second, and
only its lines. Enter on a running box opens the Session view on its session, and Esc comes back to the box; Enter on a
finished box shows its deliverable, `h` the run log; `p` pauses the flow, `r` runs it again from the box once
confirmed. Everything runs against a service served in the test, on runs written as the runner writes them."""

import time
from datetime import UTC
from pathlib import Path
from typing import Any

import pytest
from textual.pilot import Pilot
from textual.widgets import Label, ListView

from clank.client import Client
from clank.components.agents.console import flowpanels
from clank.components.agents.console.boxpanel import BoxChart
from clank.components.agents.console.flowpanels import LinesView
from clank.components.agents.console.monitor import MonitorPage, heading
from clank.components.flows.runs import BoxRun, Try
from clank.console.app import ClankConsole
from clank.console.confirm import ConfirmScreen
from clank.console.details import DetailsScreen
from clank.console.panel import Panel
from clank.console.snapshot import render_text
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.console.frames import assert_frame, focus_on, frame_when, settle, steady_frame
from tests.support.flowshapes import NOW, OWNER, T2_SESSION, d1_run, install_d1, write_run

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """The folder the console is started in: named `paper`, as in every frame."""
    return tmp_path / "paper"


def make(client: Client, home: Home, folder: Path) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = str(folder)
    return app


def d1(kernel: Kernel, clock: FakeClock, folder: Path) -> None:
    """Board D1's moment, the main slot running the flow's preset."""
    install_d1(kernel, clock, folder)
    kernel.parts["runtime"].state.set_slot("main", "ready", "a test", actor=OWNER, preset="daily-262k")


def chart(app: ClankConsole) -> BoxChart:
    return app.query_one("#monitor-flow-chart-boxes", BoxChart)


async def flow_view(pilot: Pilot[Any], app: ClankConsole) -> MonitorPage:
    """The Monitor, on its Flow view."""
    await frame_when(pilot, app, "Fake Docker")
    await pilot.press("f10")
    page = app.query_one("#page-monitor", MonitorPage)
    await settle(pilot, lambda: page.display)
    page.show_view("flow")
    return page


def drawn(app: ClankConsole) -> str:
    return "\n".join(line.plain for line in chart(app).chart.lines)


@pytest.mark.parametrize(
    ("size", "f5", "name"),
    [((160, 50), False, "monitor-flow-d1-128"), ((160, 50), True, "monitor-flow-d1-88"),
     ((82, 60), False, "monitor-flow-d1-60")],
)  # fmt: skip
async def test_the_flow_view_shows_board_d1s_moment_at_128_88_and_60_columns(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path, size: tuple[int, int], f5: bool,
    name: str,
) -> None:  # fmt: skip
    d1(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=size) as pilot:
        page = await flow_view(pilot, app)
        if f5:
            await pilot.press("f5")
        await settle(pilot, lambda: "Estimate run times" in drawn(app))
        selected = app.query_one("#monitor-flow-selected-lines", LinesView)
        await settle(pilot, lambda: "next    TASK T3 The sweep script" in str(selected.render()))
        await settle(pilot, lambda: page.flows.now is not None)  # what the running box's session does, read
        await settle(pilot, lambda: page.flows.context is not None)  # and its context window, read a second later
        frame = await frame_when(pilot, app, "A new simulation study")
        assert chart(app).selected == "T2", "the box running, until the arrows choose another"
        heading = str(app.query_one("#monitor-heading", Label).content)
        assert heading.startswith("flow “A new simulation study” · workspace myproject · run 1 · started 12:02")
        assert page.query_one("#monitor-flow-boxes", Panel).note == "6 done · 1 running · 4 waiting"
    assert_frame(frame, name)


async def test_the_arrows_move_between_boxes_and_selected_says_the_box_chosen(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    d1(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await flow_view(pilot, app)
        await settle(pilot, lambda: chart(app).selected == "T2")
        chart(app).focus()
        await pilot.press("up")
        await settle(pilot, lambda: chart(app).selected == "T1")
        await settle(pilot, lambda: "The parameter grid" in render_text(app).split("Selected")[1])
        await pilot.press("left")
        await settle(pilot, lambda: chart(app).selected == "split")
        await pilot.press("end")
        await settle(pilot, lambda: chart(app).selected == "T2")  # End: back to the box running
        assert chart(app).following


async def test_without_a_flow_the_view_says_why(client: Client, home: Home, folder: Path) -> None:
    app = make(client, home, folder)
    async with app.run_test(size=(160, 40)) as pilot:
        await flow_view(pilot, app)
        frame = await frame_when(pilot, app, "this folder has no workspace")
        assert "No flow yet · this folder has no workspace: This folder (F4) opens one" in frame


def stepping(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """What T2's session does now, as the service says it: a step further and a little faster at each look while it
    works (the state the test changes: `working` False makes it rest)."""
    state: dict[str, Any] = {"looks": 0, "working": True}

    def now(workspace: str, session: str) -> dict[str, Any]:
        state["looks"] += 1
        looks = state["looks"] if state["working"] else 0
        return {
            "session": session, "state": "answering" if state["working"] else "idle", "phase": "answering",
            "working": state["working"], "step": 14 + looks, "speed": {"now": 40.0 + looks, "steps": [44.0, 48.0]},
            "guard": {"on": True},
        }  # fmt: skip

    monkeypatch.setattr(kernel.parts["agents"], "now", now)
    return state


async def test_nothing_redraws_while_nothing_changes(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d1(kernel, clock, folder)
    stepping(kernel, monkeypatch)["working"] = False
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await flow_view(pilot, app)
        await settle(pilot, lambda: "Estimate run times" in drawn(app))
        await steady_frame(pilot, app)
        await pilot.pause(1.2)
        lines = [view.draws for view in app.query(LinesView)]
        redraws, laid_out = page.flows.redraws, chart(app).laid_out
        await pilot.pause(2.5)
        assert page.flows.redraws == redraws, "the flow read again, the same: nothing drawn"
        assert chart(app).laid_out == laid_out, "no line of the flow laid out again"
        assert [view.draws for view in app.query(LinesView)] == lines, "no panel drawn again"


async def test_a_running_box_redraws_at_most_four_times_a_second_and_only_its_rows(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d1(kernel, clock, folder)
    stepping(kernel, monkeypatch)
    app = make(client, home, folder)
    refreshed: list[int] = []
    async with app.run_test(size=(160, 50)) as pilot:
        page = await flow_view(pilot, app)
        await settle(pilot, lambda: "step" in drawn(app))
        rect = chart(app).chart.boxes["T2"]
        original = BoxChart.refresh_line

        def counted(self: BoxChart, y: int) -> None:
            refreshed.append(y)
            original(self, y)

        monkeypatch.setattr(BoxChart, "refresh_line", counted)
        redraws, began = page.flows.redraws, time.monotonic()
        await pilot.pause(3.0)
        seconds = time.monotonic() - began
        assert page.flows.redraws - redraws <= 4 * seconds + 1, "at most four redraws a second"
        assert page.flows.redraws - redraws >= 2 * seconds, "its step and speed read and drawn while it works"
        assert refreshed, "the running box's lines drawn again"
        assert set(refreshed) <= set(range(rect.y, rect.y + rect.h)), "only the running box's lines"


async def test_enter_on_a_running_box_opens_the_session_view_on_its_session_and_esc_comes_back_to_the_box(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    d1(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await flow_view(pilot, app)
        await settle(pilot, lambda: chart(app).selected == "T2")
        chart(app).focus()
        await pilot.press("enter")
        await settle(pilot, lambda: page.view == "session")
        await settle(pilot, lambda: page.seen is not None and (page.seen.head or {}).get("session") == T2_SESSION)
        said = heading("session", page.seen, UTC).plain
        assert said.endswith("the flow's box A new simulation study · T2 · try 1 (Esc goes back to it)"), said
        moved = d1_run()  # meanwhile the flow moves on: T2 done, T3 at work
        moved.at, moved.boxes["T2"].state = "T3", "done"
        moved.boxes["T2"].tries[0].ended = moved.boxes["T2"].tries[0].started
        moved.boxes["T3"] = BoxRun(state="running", tries=[Try(number=1, started=NOW, session="ses_t3", port=4097)])
        write_run(kernel.parts["flows"].runner.runs, moved)
        await pilot.press("escape")
        await settle(pilot, lambda: page.view == "flow")
        await settle(pilot, lambda: chart(app).now == "T3")  # the flow read again: at T3 now
        await pilot.pause(0.3)
        assert chart(app).selected == "T2", "back to the box the session was opened on, not the box at work now"
        assert not chart(app).following
        page.show_view("session")
        await settle(pilot, lambda: page.seen is not None and (page.seen.head or {}).get("session") != T2_SESSION)


async def test_enter_on_a_finished_box_shows_its_deliverable_and_h_the_run_log(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    d1(kernel, clock, folder)
    copies = kernel.parts["flows"].runner.runs.try_folder(d1_run(), "T1", 1) / "deliverables"
    copies.mkdir(parents=True)
    (copies / "grid.json").write_text('[{"size": 64, "rate": 0.1}]\n', encoding="utf-8")
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await flow_view(pilot, app)
        await settle(pilot, lambda: chart(app).selected == "T2")
        chart(app).focus()
        await pilot.press("up", "enter")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        assert '[{"size": 64, "rate": 0.1}]' in render_text(app), "T1's grid.json, as its try kept it"
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, DetailsScreen))
        await pilot.press("h")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        log = render_text(app)
        assert "12:02" in log
        assert "you started A new simulation study" in log
        assert log.index("you approved") < log.index("Estimate run times started"), "oldest first"


async def test_p_pauses_the_flow_and_r_runs_it_again_from_the_box_once_confirmed(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d1(kernel, clock, folder)
    asked: list[tuple[str, Any]] = []
    flows = kernel.parts["flows"]

    def pause(workspace: str, name: str, actor: Any) -> dict[str, Any]:
        asked.append(("pause", name))
        return {"run": {}}

    def go(workspace: str, name: str, actor: Any, start_from: str = "") -> dict[str, Any]:
        asked.append(("go", start_from))
        return {"did": "from", "run": {}}

    monkeypatch.setattr(flows, "pause", pause)
    monkeypatch.setattr(flows, "go", go)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await flow_view(pilot, app)
        await settle(pilot, lambda: chart(app).selected == "T2")
        chart(app).focus()
        await pilot.press("p")
        await settle(pilot, lambda: ("pause", "study") in asked)
        await pilot.press("up", "r")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        assert "T1" in render_text(app)
        await pilot.press("enter")
        await settle(pilot, lambda: ("go", "T1") in asked)


async def test_enter_on_a_deliverable_shows_it_and_o_opens_it_in_clanks_vs_code_window(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    d1(kernel, clock, folder)
    copies = kernel.parts["flows"].runner.runs.try_folder(d1_run(), "T1", 1) / "deliverables"
    copies.mkdir(parents=True)
    (copies / "grid.json").write_text('[{"size": 64, "rate": 0.1}]\n', encoding="utf-8")
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await flow_view(pilot, app)
        listed = app.query_one("#monitor-flow-deliverables-list", ListView)
        await settle(pilot, lambda: len(listed.children) == 3)
        await focus_on(pilot, app, listed, 2)
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        assert '[{"size": 64, "rate": 0.1}]' in render_text(app), "grid.json, as T1's try kept it"
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, DetailsScreen))
        await focus_on(pilot, app, listed, 2)
        await pilot.press("o")
        await settle(pilot, lambda: any(each.type == "agents.vscode" for each in kernel.operations.find(None, 10)))
        opened = next(each for each in kernel.operations.find(None, 10) if each.type == "agents.vscode")
        assert (opened.params["folder"], opened.params["file"]) == (str(folder), "grid.json")


def test_the_live_box_says_its_context_is_not_read_yet_before_it_is_never_that_no_model_runs() -> None:
    box = {"id": "T2", "type": "TASK", "state": "running", "title": "The sweep script"}
    said = [line.plain for line in flowpanels.live(box, None, None, 60)]
    assert any(line.startswith("context not read yet") for line in said), said
    nothing = [line.plain for line in flowpanels.live(box, None, {"window": None}, 60)]
    assert any(line.startswith("context no model runs") for line in nothing)
    waiting = [line.plain for line in flowpanels.live(box, None, {"window": 262_144, "used": None}, 60)]
    assert any(line.startswith("context no step has ended yet") for line in waiting)


async def test_plus_and_minus_make_the_flows_boxes_larger_or_smaller_kept_in_the_consoles_settings(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    """The owner (2026-10-22, the console full screen over SSH): the boxes should be larger and "a bit more fleshed
    out". They are medium unless the console's settings say otherwise; + and - pick another size, kept there."""
    d1(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(200, 60)) as pilot:
        await flow_view(pilot, app)
        await settle(pilot, lambda: "T2" in chart(app).chart.boxes)
        assert chart(app).box_size == "medium"
        assert chart(app).chart.boxes["T2"].h == 8
        await pilot.press("plus")
        await settle(pilot, lambda: chart(app).chart.boxes["T2"].h == 10)
        await settle(pilot, lambda: '"flow_boxes": "large"' in (home.config / "console.json").read_text("utf-8")
                     if (home.config / "console.json").is_file() else False)  # fmt: skip
        await pilot.press("minus", "minus")
        await settle(pilot, lambda: chart(app).chart.boxes["T2"].h == 6)


async def test_under_the_flow_the_running_boxs_thinking_calls_and_context_then_the_orchestrator_and_waiting(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    """The owner (2026-10-23, watching a run): "move the 'waiting for you' and 'Models in this flow' boxes down so that
    we can include boxes for the thinking and the tool calls/context viewer". Under the flow: Selected beside Thinking
    (the running box's model as it writes), Tool calls beside Context window (its session's), then the Orchestrator
    beside Waiting for you, then Models in this flow."""
    d1(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 60)) as pilot:
        page = await flow_view(pilot, app)
        order = [panel.id for panel in page.query(Panel).results(Panel) if panel.has_class("board-d1")]
        assert order[:9] == [
            "monitor-flow-boxes", "monitor-flow-selected", "monitor-flow-thinking", "monitor-flow-calls",
            "monitor-flow-context", "monitor-flow-orchestrator", "monitor-flow-waiting", "monitor-flow-side",
            "monitor-flow-models",
        ]  # fmt: skip
        await settle(pilot, lambda: page.flows.box_seen is not None)
        seen = page.flows.box_seen
        assert seen is not None
        assert (seen.head or {}).get("session") == T2_SESSION, "the running box's session"
        for id in ("monitor-flow-thinking", "monitor-flow-calls", "monitor-flow-context"):
            assert "T2" in page.query_one(f"#{id}", Panel).note, f"{id} names the box it shows"
