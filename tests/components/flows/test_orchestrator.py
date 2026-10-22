"""Design 0013 §16 (decisions 0123-0124): the orchestrator. While a flow's orchestrator is on, a checkpoint follows each
box a model ran, and each question the run asks: a fresh Plan-mode session titled `<flow> · orchestrator · <n>`,
handed the box's report, the question with its answers, the run so far, the budget left and the ledger, which decides
with `flow_decide`. Its answer to a question is given through the questions API, by the orchestrator, and the run goes
on as it would for the owner's; after a box it may go on with a note for the next box, change a box not yet run, or
stop. Clank keeps the ledger beside the run (`orchestrator.md`): the facts and plan, then each decision. A decision is
refused, saying why, when no checkpoint works in the workspace, when its choice is not one it may make, when it needs
more changes than are left, and when the run has stalled and it would go on. The owner may answer a question first;
the last gate is the owner's when the flow says so; a checkpoint that ends without deciding leaves the question to the
owner. Run against the fake bridge and a synthetic folder."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.flows.orchestrating import ORCHESTRATOR, failure_class
from clank.components.flows.runner import RunError
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import (
    FLOW,
    OWNER,
    WORKSPACE,
    Rig,
    at_work,
    make_rig,
    question,
    running,
    study,
    until,
)

pytestmark = pytest.mark.anyio


def steered(**orchestrator: Any) -> dict[str, Any]:
    """The study (YOU, PLAN, a gate that is not the last, TASK) with its orchestrator on."""
    return study(orchestrator={"on": True, **orchestrator})


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, steered())
    yield made
    made.kernel.close()


def decision(choice: str, **more: Any) -> dict[str, Any]:
    """A decision as `flow_decide` sends it: the five answers, the facts and plan, the choice."""
    return {
        "choice": choice, "why": more.pop("why", "the plan answers the brief"), "met": [], "unmet": ["a grid"],
        "looping": False, "progressing": True, "facts": "The plan has an 8 x 8 grid.", "plan": "Approve it, then T1.",
        **more,
    }  # fmt: skip


async def to_the_first_checkpoint(rig: Rig) -> Any:
    """The run started, its brief done by the owner, its plan written: the orchestrator's first checkpoint at work."""
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "About 60 grid points, at most 48 CPU-hours.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    plan = await at_work(rig, "plan")
    rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n\nAn 8 x 8 grid, 41.5 CPU-hours.\n"})
    return await until(lambda: rig.bridge.prompted("Study · orchestrator · 1"))


async def test_a_checkpoint_follows_a_box_handed_its_report_the_question_none_the_budget_and_the_ledger(
    rig: Rig,
) -> None:
    async with running(rig.kernel):
        first = await to_the_first_checkpoint(rig)
        assert first.agent == "planner", "a checkpoint runs in Plan mode: it changes no file"
        for words in ("flow_decide", "PLAN.md", "Write the plan", "done", "About 60 grid points", "12 changes left",
                      "stall 0 of 3", "go on", "change", "back", "stop"):  # fmt: skip
            assert words in first.text, words
        said = rig.runner.decide(WORKSPACE, decision("go on", note="Keep the grid at 8 x 8."), actor=ORCHESTRATOR)
        assert "kept" in said["said"]
        rig.bridge.finish(first.session)
        await until(lambda: rig.bridge.prompted("Study · orchestrator · 2"))  # the gate's question, decided next

    ledger = (rig.runner.runs.run_folder(rig.run()) / "orchestrator.md").read_text(encoding="utf-8")
    assert "The plan has an 8 x 8 grid." in ledger
    assert "Approve it, then T1." in ledger
    assert "1. after plan: go on" in ledger


async def test_its_answer_to_a_gate_is_the_orchestrators_and_the_run_goes_on_with_its_note_told_to_the_next_box(
    rig: Rig,
) -> None:
    async with running(rig.kernel):
        first = await to_the_first_checkpoint(rig)
        rig.runner.decide(WORKSPACE, decision("go on", note="Keep the grid at 8 x 8."), actor=ORCHESTRATOR)
        rig.bridge.finish(first.session)
        second = await until(lambda: rig.bridge.prompted("Study · orchestrator · 2"))
        assert "You approve the plan" in second.text
        assert "`approve`" in second.text, "the question's answers, each by its id"
        rig.runner.decide(WORKSPACE, decision("approve"), actor=ORCHESTRATOR)
        rig.bridge.finish(second.session)
        t1 = await at_work(rig, "T1")
        assert "The orchestrator's note: Keep the grid at 8 x 8." in t1.text

    answered = list(rig.events("question.answered"))
    assert answered
    assert answered[-1].actor == ORCHESTRATOR


async def test_a_change_edits_a_box_not_yet_run_and_counts_against_its_limit(rig: Rig) -> None:
    async with running(rig.kernel):
        first = await to_the_first_checkpoint(rig)
        change = {"box": "T1", "prompt": "Write the grid as 8 x 8 points, seeds 1 to 64."}
        rig.runner.decide(WORKSPACE, decision("change", changes=[change]), actor=ORCHESTRATOR)
        rig.bridge.finish(first.session)
        second = await until(lambda: rig.bridge.prompted("Study · orchestrator · 2"))
        assert "11 changes left" in second.text
        rig.runner.decide(WORKSPACE, decision("approve"), actor=ORCHESTRATOR)
        rig.bridge.finish(second.session)
        t1 = await at_work(rig, "T1")
        assert "seeds 1 to 64" in t1.text


async def test_a_change_to_a_box_that_ran_or_past_the_limit_is_refused_saying_why(
    home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = make_rig(home, clock, tmp_path, monkeypatch, steered(changes=1))
    try:
        async with running(rig.kernel):
            await to_the_first_checkpoint(rig)
            with pytest.raises(RunError, match="plan has run: only a box not run yet changes"):
                rig.runner.decide(WORKSPACE, decision("change", changes=[{"box": "plan", "prompt": "x"}]),
                                  actor=ORCHESTRATOR)  # fmt: skip
            two = [{"box": "T1", "prompt": "a"}, {"box": "T1", "title": "b"}]
            with pytest.raises(RunError, match="1 change left"):
                rig.runner.decide(WORKSPACE, decision("change", changes=two), actor=ORCHESTRATOR)
            with pytest.raises(RunError, match="choose one of: go on, change, back, stop"):
                rig.runner.decide(WORKSPACE, decision("approve"), actor=ORCHESTRATOR)
    finally:
        rig.kernel.close()


async def test_once_stalled_it_may_not_go_on(
    home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = steered(stall=1)
    flow["boxes"].insert(2, {"id": "plan2", "type": "plan", "title": "Plan again", "writes": ["PLAN2.md"],
                             "prompt": "Plan again."})  # fmt: skip
    flow["lines"] = [{"from": "brief", "to": "plan"}, {"from": "plan", "to": "plan2"},
                     {"from": "plan2", "to": "approve"}, {"from": "approve", "to": "T1"}]  # fmt: skip
    rig = make_rig(home, clock, tmp_path, monkeypatch, flow)
    try:
        async with running(rig.kernel):
            first = await to_the_first_checkpoint(rig)
            rig.runner.decide(WORKSPACE, decision("go on", progressing=False), actor=ORCHESTRATOR)
            rig.bridge.finish(first.session)
            again = await at_work(rig, "plan2")
            rig.bridge.finish(again.session, {"PLAN2.md": "# Again\n"})
            second = await until(lambda: rig.bridge.prompted("Study · orchestrator · 2"))
            assert "stalled" in second.text
            with pytest.raises(RunError, match="no progress"):
                rig.runner.decide(WORKSPACE, decision("go on"), actor=ORCHESTRATOR)
            rig.runner.decide(WORKSPACE, decision("stop", why="the plan cannot meet the brief"), actor=ORCHESTRATOR)
            rig.bridge.finish(second.session)
            await until(lambda: rig.run().status == "stopped")
    finally:
        rig.kernel.close()


async def test_the_owner_may_answer_first_and_its_later_answer_is_set_aside(rig: Rig) -> None:
    async with running(rig.kernel):
        first = await to_the_first_checkpoint(rig)
        rig.runner.decide(WORKSPACE, decision("go on"), actor=ORCHESTRATOR)
        rig.bridge.finish(first.session)
        second = await until(lambda: rig.bridge.prompted("Study · orchestrator · 2"))
        asked = await until(lambda: question(rig, "You approve the plan"))
        rig.kernel.questions.answer(asked.id, by=OWNER, option="approve")
        rig.runner.decide(WORKSPACE, decision("stop"), actor=ORCHESTRATOR)
        rig.bridge.finish(second.session)
        await at_work(rig, "T1")
    assert rig.run().status == "running", "the owner's answer counts: the orchestrator's later stop is set aside"


async def test_the_last_gate_is_the_owners_when_the_flow_says_so(
    home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = steered(final_review="owner")
    flow["boxes"] = flow["boxes"][:3]  # YOU, PLAN, the gate: the gate is the last box
    flow["lines"] = flow["lines"][:2]
    rig = make_rig(home, clock, tmp_path, monkeypatch, flow)
    try:
        async with running(rig.kernel):
            first = await to_the_first_checkpoint(rig)
            rig.runner.decide(WORKSPACE, decision("go on"), actor=ORCHESTRATOR)
            rig.bridge.finish(first.session)
            await until(lambda: question(rig, "You approve the plan"))
            assert rig.bridge.prompted("Study · orchestrator · 2") is None, "the last gate waits for the owner"
    finally:
        rig.kernel.close()


async def test_a_checkpoint_that_ends_without_deciding_leaves_the_question_to_the_owner(rig: Rig) -> None:
    async with running(rig.kernel):
        first = await to_the_first_checkpoint(rig)
        rig.runner.decide(WORKSPACE, decision("go on"), actor=ORCHESTRATOR)
        rig.bridge.finish(first.session)
        second = await until(lambda: rig.bridge.prompted("Study · orchestrator · 2"))
        rig.bridge.finish(second.session)  # it never called flow_decide
        await until(lambda: "ended without deciding" in (rig.run().orchestration.owner or ""))
        assert question(rig, "You approve the plan") is not None


def test_a_decision_while_no_checkpoint_works_is_refused(rig: Rig) -> None:
    with pytest.raises(RunError, match="no checkpoint of an orchestrator works in myproject now"):
        rig.runner.decide(WORKSPACE, decision("go on"), actor=ORCHESTRATOR)


def test_the_decide_route_refuses_with_409_saying_why(rig: Rig) -> None:
    app = create_app(rig.kernel, token="t", port=7720, background=[rig.kernel.parts["flows"].run])
    with TestClient(app, base_url="http://127.0.0.1:7720") as http:
        answer = http.post(
            "/api/v1/flows/decide",
            headers={"Authorization": "Bearer t", "X-Clank-Client": "agent"},
            json={"workspace": WORKSPACE, **decision("go on")},
        )
    assert answer.status_code == 409
    assert "no checkpoint of an orchestrator works in myproject now" in answer.json()["error"]["message"]


def test_a_failures_class_says_whether_to_try_again_as_it_was() -> None:
    assert failure_class("its session is gone: its OpenCode server stopped") == "outside the work"
    assert failure_class("it ran past its limit of 30 minutes: Clank stopped its session") == "a limit"
    assert failure_class("it wrote 210,000 tokens, past its limit of 200,000: Clank stopped its session") == "a limit"
    assert failure_class("its accept command failed (exit 1)") == "its result"
    assert failure_class("it ended without a verdict") == "its result"
