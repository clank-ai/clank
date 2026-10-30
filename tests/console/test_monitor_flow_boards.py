"""Design 0013 §9, §10, §12 and §14 step 6 (boards D2, D3 and D4): the Flow view's boards beside board D1, each shown
in place of D1's panels, Esc going back to it. Board D4, proposals (`Enter` on a DECOMPOSE while its proposals wait,
revised 2026-10-18 at the owner's comment: cards, not a list): the flow so far with the proposals dashed; the
proposals as cards side by side in the order they will run, each with its state, its settings and its own answers;
the highlighted card's whole prompt below them; how the model proposed them. Its decisions (accept, edit, reject and
accept all) reach the service, and the cards say what became of each; at any width, no card touches another. Against a
service served in the test, on runs written as the runner writes them."""

from datetime import UTC
from pathlib import Path
from typing import Any

import pytest
from textual.pilot import Pilot
from textual.widgets import Input, Label, TextArea

from clank.client import Client
from clank.components.agents.console.boxpanel import BoxChart, CardsView
from clank.components.agents.console.flowboards import cards
from clank.components.agents.console.monitor import MonitorPage
from clank.components.flows.kinds import Flow
from clank.console.app import ClankConsole
from clank.console.details import DetailsScreen
from clank.console.editor import EditScreen
from clank.console.form import FormScreen
from clank.console.pick import PickScreen
from clank.console.snapshot import render_text
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.console.frames import assert_frame, frame_when, settle
from tests.support.flowshapes import (
    FLOW,
    NOW,
    d1_values,
    generated,
    install_d1,
    install_gate,
    install_proposals,
    touching,
    write_flow,
)

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    """The folder the console is started in: named `paper`, as in every frame."""
    return tmp_path / "paper"


def make(client: Client, home: Home, folder: Path) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = str(folder)
    return app


def chart(app: ClankConsole) -> BoxChart:
    return app.query_one("#monitor-flow-chart-boxes", BoxChart)


def shown_cards(app: ClankConsole) -> CardsView:
    return app.query_one("#monitor-flow-d4-cards-view", CardsView)


def states(app: ClankConsole) -> dict[str, str]:
    view = app.query_one("#page-monitor", MonitorPage).flows.view or {}
    return {str(each["id"]): str(each["state"]) for each in (view.get("proposals") or {}).get("items") or []}


async def board_d4(pilot: Pilot[Any], app: ClankConsole) -> MonitorPage:
    """The Monitor's Flow view, Enter on the DECOMPOSE whose proposals wait: board D4."""
    await frame_when(pilot, app, "Fake Docker")
    await pilot.press("f10")
    page = app.query_one("#page-monitor", MonitorPage)
    await settle(pilot, lambda: page.display)
    page.show_view("flow")
    await settle(pilot, lambda: chart(app).selected == "split")
    chart(app).focus()
    await pilot.press("enter")
    await settle(pilot, lambda: page.has_class("-board-d4") and bool(shown_cards(app).chart.boxes))
    return page


def flow_boxes(kernel: Kernel) -> list[str]:
    record = kernel.settings.get("flow", FLOW).record
    assert isinstance(record, Flow)
    return [box.id for box in record.boxes]


async def test_d4_shows_each_proposal_as_a_card_in_the_order_they_will_run(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    install_proposals(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await board_d4(pilot, app)
        assert shown_cards(app).chart.order == ["T1", "T2", "T3", "T4"]
        assert shown_cards(app).selected == "T1", "the first card highlighted"
        frame = await frame_when(pilot, app, "1 · TASK T1?", "Do step 1 of PLAN.md")
        assert "runs after T1" in frame
        assert "flow_propose_box(after=split, type=TASK, title=…) → T1" in frame
        assert not app.query_one("#monitor-flow-boxes").display, "board D1's panels hidden meanwhile"
        assert_frame(frame, "monitor-flow-d4-128")
        await pilot.press("right")
        await settle(pilot, lambda: "Do step 2 of PLAN.md" in render_text(app))  # the highlighted card's prompt
        await pilot.press("escape")
        await settle(pilot, lambda: not page.has_class("-board-d4"))
        assert app.query_one("#monitor-flow-boxes").display


async def test_d4s_decisions_accept_edit_reject_and_accept_all_reach_the_service(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    install_proposals(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await board_d4(pilot, app)
        await pilot.press("a")
        await settle(pilot, lambda: states(app).get("T1") == "accepted")
        assert "T1" in flow_boxes(kernel), "accepted: it joins the flow's file"
        await pilot.press("right", "r")
        await settle(pilot, lambda: states(app).get("T2") == "rejected")
        await pilot.press("right", "e")
        await settle(pilot, lambda: isinstance(app.screen, EditScreen))
        app.screen.query_one(TextArea).text = "Do step 3 of PLAN.md, with the seeds fixed."
        await pilot.press("ctrl+s")
        await settle(pilot, lambda: "with the seeds fixed" in render_text(app))
        assert states(app).get("T3") == "proposed", "an edited card still waits"
        await pilot.press("A")
        await settle(pilot, lambda: states(app) == {"T1": "accepted", "T2": "rejected", "T3": "accepted",
                                                   "T4": "accepted"})  # fmt: skip
        boxes = flow_boxes(kernel)
        assert [id for id in boxes if id.startswith("T")] == ["T1", "T3", "T4"], "T2 never runs"
        record = kernel.settings.get("flow", FLOW).record
        assert isinstance(record, Flow)
        assert next(box for box in record.boxes if box.id == "T3").prompt.endswith("with the seeds fixed.")


@pytest.mark.parametrize("width", [40, 60, 79, 81, 100, 126])
def test_d4s_cards_never_touch_at_any_width(width: int) -> None:
    for tasks in (1, 2, 4, 7, 12):
        shown = generated(tasks, proposals=True, long=tasks % 2 == 1)
        laid = cards(shown, width, "T2")
        assert touching(laid) == [], f"{tasks} cards at {width} columns"
        assert laid.order == [f"T{number}" for number in range(1, tasks + 1)]


async def board_d3(pilot: Pilot[Any], app: ClankConsole) -> MonitorPage:
    """The Monitor's Flow view, Enter on the gate that asks: board D3."""
    await frame_when(pilot, app, "Fake Docker")
    await pilot.press("f10")
    page = app.query_one("#page-monitor", MonitorPage)
    await settle(pilot, lambda: page.display)
    page.show_view("flow")
    await settle(pilot, lambda: chart(app).selected == "approve")
    chart(app).focus()
    await pilot.press("enter")
    await settle(pilot, lambda: page.has_class("-board-d3"))
    await settle(pilot, lambda: "The seeds: 1 to 60." in render_text(app))
    return page


async def test_d3_shows_the_gate_what_it_shows_the_verifys_report_and_the_brief_against_the_plan(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    install_gate(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await board_d3(pilot, app)
        frame = await frame_when(pilot, app, "Where the flow is", "VERIFY's report", "Your decision")
        assert "changed since try 1:" in frame
        assert "no CPU-hour budget" in frame, "try 1's findings"
        assert "Send back to PLAN with a note" in frame
        assert_frame(frame, "monitor-flow-d3-128")


@pytest.mark.parametrize(("keys", "option", "text"), [
    (("a",), "approve", ""), (("s",), "back", "Keep the seeds fixed."), (("x", "enter"), "stop", ""),
])  # fmt: skip
async def test_d3s_answers_approve_send_back_with_a_note_and_stop_answer_its_question(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path, keys: tuple[str, ...], option: str,
    text: str,
) -> None:  # fmt: skip
    question = install_gate(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await board_d3(pilot, app)
        await pilot.press(*keys)
        if text:
            await settle(pilot, lambda: isinstance(app.screen, FormScreen))
            app.screen.query_one(Input).value = text
            await pilot.press("ctrl+s")
        await settle(pilot, lambda: kernel.questions.get(question).status == "answered")
    answered = kernel.questions.get(question).answer
    assert answered is not None
    assert (answered.option, answered.text) == (option, text)
    assert answered.by.via == "console"


async def test_d3_offers_the_answers_of_the_question_the_gate_waits_for_go_on_after_every_box(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    question = install_gate(kernel, clock, folder, kind="done")
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await board_d3(pilot, app)
        frame = await frame_when(pilot, app, "Your decision", "Go on")
        assert "Approve and go on" not in frame, "the question asks go on or stop, not an approval"
        assert "Send back" not in frame
        await pilot.press("s")
        await settle(pilot, lambda: "! " in str(app.query_one("#message", Label).content))
        assert kernel.questions.get(question).status == "waiting", "no answer the question does not offer"
        await pilot.press("a")
        await settle(pilot, lambda: kernel.questions.get(question).status == "answered")
    answered = kernel.questions.get(question).answer
    assert answered is not None
    assert answered.option == "go"


async def test_e_opens_the_file_in_clanks_vs_code_window_and_d_diffs_the_last_two_tries(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    install_gate(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await board_d3(pilot, app)
        await pilot.press("e")
        await settle(pilot, lambda: any(each.type == "agents.vscode" for each in kernel.operations.find(None, 10)))
        opened = next(each for each in kernel.operations.find(None, 10) if each.type == "agents.vscode")
        assert (opened.params["folder"], opened.params["file"]) == (str(folder), "PLAN.md")
        await pilot.press("d")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        shown = render_text(app)
        assert "-The grid: 240 points." in shown
        assert "+The grid: 60 points." in shown


async def board_d2(pilot: Pilot[Any], app: ClankConsole, box: str = "T2") -> MonitorPage:
    """The Monitor's Flow view, `e` on a box: board D2, its settings."""
    await frame_when(pilot, app, "Fake Docker")
    await pilot.press("f10")
    page = app.query_one("#page-monitor", MonitorPage)
    await settle(pilot, lambda: page.display)
    page.show_view("flow")
    await settle(pilot, lambda: chart(app).selected == "T2")
    chart(app).focus()
    if box != "T2":
        chart(app).choose(box)
    await pilot.press("e")
    await settle(pilot, lambda: page.has_class("-board-d2"))
    await settle(pilot, lambda: "w  Network" in render_text(app))
    return page


def setting(kernel: Kernel, box: str, field: str) -> Any:
    record = kernel.settings.get("flow", FLOW).record
    assert isinstance(record, Flow)
    return getattr(next(each for each in record.boxes if each.id == box), field)


async def test_d2_shows_each_field_with_its_key_and_the_flow_as_a_list(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    install_d1(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await board_d2(pilot, app)
        frame = await frame_when(pilot, app, "T2 · Estimate run times · settings")
        for key, field in [("t", "Type"), ("m", "Model"), ("o", "Mode"), ("i", "Sees"), ("p", "Prompt"),
                           ("d", "Deliverable"), ("a", "Accept when"), ("n", "When done"), ("r", "Tries"),
                           ("l", "Limits"), ("u", "Tools"), ("w", "Network")]:  # fmt: skip
            assert f"{key}  {field}" in frame, field
        assert "It is running: a change here applies from its next try." in frame
        assert "The parameter grid" in frame, "the flow as a list beside it"
        assert "e edit the field" not in frame, "each field has its own key"
        assert_frame(frame, "monitor-flow-d2-128")


async def test_a_change_is_marked_not_saved_until_s_saves_it_into_the_flows_file(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    install_d1(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        page = await board_d2(pilot, app)
        await pilot.press("n")
        await settle(pilot, lambda: isinstance(app.screen, PickScreen))
        await pilot.press("down", "enter")
        await settle(pilot, lambda: "1 change not saved" in render_text(app))
        assert "not saved" in next(line for line in render_text(app).splitlines() if "n  When done" in line)
        assert setting(kernel, "T2", "when_done") == "go on", "nothing saved yet"
        before = kernel.settings.get("flow", FLOW).record.model_dump(mode="json")
        await pilot.press("s")
        await settle(pilot, lambda: setting(kernel, "T2", "when_done") == "wait")
        await settle(pilot, lambda: "not saved" not in render_text(app))
        assert page.has_class("-board-d2"), "it stays on the box's settings"
    after = kernel.settings.get("flow", FLOW).record.model_dump(mode="json")
    wanted = before | {"boxes": [box | {"when_done": "wait"} if box["id"] == "T2" else box for box in before["boxes"]]}
    assert after == wanted, "the whole record round-trips: only the field changed differs"


async def test_d2_on_a_proposed_box_saves_its_changes_into_the_proposal_never_the_flows_file(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    install_proposals(kernel, clock, folder)
    app = make(client, home, folder)
    file_before = kernel.settings.get("flow", FLOW).record.model_dump(mode="json")
    async with app.run_test(size=(160, 50)) as pilot:
        await frame_when(pilot, app, "Fake Docker")
        await pilot.press("f10")
        page = app.query_one("#page-monitor", MonitorPage)
        await settle(pilot, lambda: page.display)
        page.show_view("flow")
        await settle(pilot, lambda: chart(app).selected == "split")
        chart(app).focus()
        chart(app).choose("T1")
        await pilot.press("e")
        await settle(pilot, lambda: page.has_class("-board-d2"))
        await settle(pilot, lambda: "Task 1 of the plan" in render_text(app))
        assert "out/t1.md" in render_text(app), "the proposal's own settings"
        await pilot.press("n")
        await settle(pilot, lambda: isinstance(app.screen, PickScreen))
        await pilot.press("down", "enter")
        await settle(pilot, lambda: "1 change not saved" in render_text(app))
        await pilot.press("s")
        await settle(pilot, lambda: proposal(kernel, "T1").when_done == "wait")
        said = str(app.query_one("#message", Label).content)
        assert "T1" in said
        assert "proposal" in said, said
    assert kernel.settings.get("flow", FLOW).record.model_dump(mode="json") == file_before, "the file is untouched"
    assert proposal(kernel, "T1").when_done == "wait", "the edit is the proposal's, still waiting for you"


def proposal(kernel: Kernel, id: str) -> Any:
    runs = kernel.parts["flows"].runner.runs
    run = runs.latest(FLOW)
    batch = kernel.parts["flows"].runner.proposing.batches.last(run, "split")
    return next(each.box for each in batch.proposals if each.id == id)


async def test_a_save_on_a_flow_changed_meanwhile_is_refused_and_said(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    install_d1(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await board_d2(pilot, app)
        await pilot.press("n")
        await settle(pilot, lambda: isinstance(app.screen, PickScreen))
        await pilot.press("down", "enter")
        await settle(pilot, lambda: "1 change not saved" in render_text(app))
        write_flow(kernel, d1_values() | {"title": "A study edited elsewhere"})
        await pilot.press("s")
        await settle(pilot, lambda: "! " in str(app.query_one("#message", Label).content))
        said = str(app.query_one("#message", Label).content)
        assert "changed" in said or "revision" in said, said
        assert setting(kernel, "T2", "when_done") == "go on", "the newer file stands"
        assert "1 change not saved" in render_text(app), "the change is kept, to save again on the new version"


async def test_v_shows_the_boxs_whole_first_message(
    kernel: Kernel, client: Client, home: Home, clock: FakeClock, folder: Path
) -> None:
    install_d1(kernel, clock, folder)
    app = make(client, home, folder)
    async with app.run_test(size=(160, 50)) as pilot:
        await board_d2(pilot, app)
        await pilot.press("v")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        window = app.screen
        assert isinstance(window, DetailsScreen)
        assert window.heading.startswith("T2's first message, as it would be sent now")
        assert any("Estimate the run time of each grid point" in line for line in window.lines), "its prompt, whole"
