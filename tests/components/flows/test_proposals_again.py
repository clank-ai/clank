"""Design 0013 §9 (decision 0064): a DECOMPOSE that runs again proposes anew. Its new proposals replace the tasks it
added that have not started in the run, when the first of them joins the flow; those that ran stay. The proposals of
its earlier try still waiting are set aside (replaced) when its next try begins, their question withdrawn, as are those
of a box skipped. A run that ends withdraws its batches' questions and leaves their proposals to decide from the
command line; accepted then, they join the flow's file for its next run. Run against the fake bridge and a synthetic
folder."""

from collections.abc import Iterator
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from clank.components.flows.kinds import Flow
from clank.components.flows.runner import RUNNER
from clank.components.flows.verdicts import AGENT
from tests.components.flows.rig import (
    FLOW,
    OWNER,
    WORKSPACE,
    Rig,
    at_work,
    decomposing,
    make_rig,
    question,
    running,
    task,
    until,
)

pytestmark = pytest.mark.anyio


@pytest.fixture
def rig(home: Any, clock: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, decomposing())
    yield made
    made.kernel.close()


async def to_the_split(rig: Rig) -> Any:
    """The run started, its brief done, its plan written; the DECOMPOSE's first message sent."""
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "About 60 grid points.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
    rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
    return await at_work(rig, "split")


def propose(rig: Rig, *numbers: int) -> None:
    for number in numbers:
        rig.runner.proposing.propose(WORKSPACE, task(number), actor=AGENT)


def boxes(rig: Rig) -> list[str]:
    record = rig.kernel.settings.get(Flow.KIND, FLOW).record
    assert isinstance(record, Flow)
    return [box.id for box in record.boxes]


async def test_a_decompose_run_again_replaces_only_its_tasks_that_have_not_started(rig: Rig) -> None:
    async with running(rig.kernel):
        split = await to_the_split(rig)
        propose(rig, 1, 2, 3)
        rig.runner.proposing.submit(WORKSPACE, "Three tasks.", actor=AGENT)
        rig.bridge.finish(split.session)
        await until(lambda: question(rig, "proposed"))
        rig.runner.proposing.decide(FLOW, "accept", None, actor=OWNER)
        await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
        rig.runner.stop(FLOW, actor=OWNER)  # T1 started; T2 and T3 did not
        await until(lambda: rig.run().status == "stopped" and not rig.run().operation)
        rig.runner.run_from(FLOW, "split", actor=OWNER)
        again = await at_work(rig, "split", 2)
        rig.runner.proposing.propose(WORKSPACE, task(4), actor=AGENT)
        rig.runner.proposing.propose(WORKSPACE, task(5), actor=AGENT)
        assert boxes(rig)[2:6] == ["split", "T1", "T2", "T3"], "nothing replaced before a new one joins"
        rig.runner.proposing.submit(WORKSPACE, "Two tasks, anew.", actor=AGENT)
        rig.bridge.finish(again.session)
        await until(lambda: question(rig, "proposed"))
        rig.runner.proposing.decide(FLOW, "accept", None, actor=OWNER)
        for name in ("T1", "T4", "T5"):
            title = f"Study · {name} · try {2 if name == 'T1' else 1}"
            prompt = await until(partial(rig.bridge.prompted, title))
            rig.bridge.finish(prompt.session, {f"out/t{name[1:]}.md": "Done.\n"})
        await until(lambda: rig.bridge.prompted("Study · join · try 1"))
    assert boxes(rig) == ["brief", "plan", "split", "T1", "T4", "T5", "join", "review"], "T1 ran: it stays"
    batch = rig.runner.proposing.batches.load(rig.run(), "split", 2)
    assert batch is not None
    assert batch.replaced == ["T2", "T3"]
    assert rig.bridge.prompted("Study · T2 · try 1") is None


async def test_the_proposals_of_its_earlier_try_still_waiting_are_set_aside_when_it_tries_again(rig: Rig) -> None:
    async with running(rig.kernel):
        split = await to_the_split(rig)
        propose(rig, 1, 2)
        rig.bridge.finish(split.session)  # without submitting: it failed
        failed = await until(lambda: question(rig, "Break it into tasks failed"))
        rig.kernel.questions.answer(failed.id, by=OWNER, option="retry")
        again = await at_work(rig, "split", 2)
        said = rig.runner.proposing.propose(WORKSPACE, task(3), actor=AGENT)
    first = rig.runner.proposing.batches.load(rig.run(), "split", 1)
    assert first is not None
    assert [(each.state, each.decided_by) for each in first.proposals] == [("replaced", RUNNER)] * 2
    assert "split runs again" in first.proposals[0].said
    assert said["proposal"] == "T3", "an id is never used twice in a run"
    replaced = [event for event in rig.events("flows.proposal_decided") if event.data["decision"] == "replaced"]
    assert [event.data["proposal"] for event in replaced] == ["T1", "T2"]
    assert again is not None


async def test_a_decompose_run_again_from_its_box_while_its_proposals_wait_withdraws_their_question(rig: Rig) -> None:
    async with running(rig.kernel):
        split = await to_the_split(rig)
        propose(rig, 1, 2)
        rig.runner.proposing.submit(WORKSPACE, "Two tasks.", actor=AGENT)
        rig.bridge.finish(split.session)
        asked = await until(lambda: question(rig, "proposed"))
        await until(lambda: rig.run().waiting is not None)  # the run waits for them, its box's work done
        rig.runner.run_from(FLOW, "split", actor=OWNER)
        await until(lambda: rig.bridge.prompted("Study · split · try 2"))
        assert question(rig, "proposed") is None
    assert rig.kernel.questions.get(asked.id).status == "withdrawn"
    first = rig.runner.proposing.batches.load(rig.run(), "split", 1)
    assert first is not None
    assert [each.state for each in first.proposals] == ["replaced", "replaced"]


async def test_skipping_a_decompose_sets_its_proposals_aside_and_the_flow_goes_on_without_them(rig: Rig) -> None:
    async with running(rig.kernel):
        split = await to_the_split(rig)
        propose(rig, 1)
        rig.bridge.finish(split.session)
        failed = await until(lambda: question(rig, "Break it into tasks failed"))
        rig.kernel.questions.answer(failed.id, by=OWNER, option="skip")
        await until(lambda: rig.bridge.prompted("Study · join · try 1"))
    first = rig.runner.proposing.batches.load(rig.run(), "split", 1)
    assert first is not None
    assert first.proposals[0].state == "replaced"
    assert boxes(rig) == ["brief", "plan", "split", "join", "review"]


async def test_taking_a_failed_decompose_as_it_is_asks_about_what_it_proposed(rig: Rig) -> None:
    async with running(rig.kernel):
        split = await to_the_split(rig)
        propose(rig, 1)
        rig.bridge.finish(split.session)
        failed = await until(lambda: question(rig, "Break it into tasks failed"))
        rig.kernel.questions.answer(failed.id, by=OWNER, option="take")
        asked = await until(lambda: question(rig, "proposed"))
        rig.kernel.questions.answer(asked.id, by=OWNER, option="accept")
        await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
    assert boxes(rig)[2:4] == ["split", "T1"]


async def test_a_run_that_ends_withdraws_its_batchs_question_and_leaves_its_proposals_to_decide(rig: Rig) -> None:
    async with running(rig.kernel):
        await to_the_split(rig)
        propose(rig, 1, 2)
        rig.runner.proposing.submit(WORKSPACE, "Two tasks.", actor=AGENT)
        asked = await until(lambda: question(rig, "proposed"))
        rig.runner.stop(FLOW, actor=OWNER)
        await until(lambda: rig.run().status == "stopped" and not rig.run().operation)
    assert rig.kernel.questions.get(asked.id).status == "withdrawn"
    batch = rig.runner.proposing.batches.load(rig.run(), "split", 1)
    assert batch is not None
    assert [each.state for each in batch.proposals] == ["proposed", "proposed"]
    rig.runner.proposing.decide(FLOW, "accept", ["T2"], actor=OWNER)
    assert boxes(rig) == ["brief", "plan", "split", "T2", "join", "review"], "it joins the flow for its next run"
