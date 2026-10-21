"""Design 0013 §2, §6, §9 and §10 (decisions 0061 and 0064): a DECOMPOSE ends by submitting its proposals
(`flow_submit`), which asks the owner one question about them, saying each one's mode of its own (in Auto, its changes
are accepted without review); one that ends without submitting fails and waits at a gate. The run waits after the
DECOMPOSE until each proposal is decided: the owner accepts, edits then accepts, or rejects each, or all at once, from
the command line first, or answers the question from any client (the phone accepts or rejects them all). Accepting all
puts T1-T4 in order between the DECOMPOSE and the INTEGRATE in the flow's file, each marked with its run and the
DECOMPOSE, and they run one at a time in that order; a rejected proposal never runs; an edited prompt is the one sent.
The agent cannot accept. Each decision is an event with its actor. Run against the fake bridge and a synthetic folder.
"""

from collections.abc import Iterator
from functools import partial
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank.components.flows.kinds import Flow
from clank.components.flows.runner import RunError
from clank.components.flows.verdicts import AGENT
from clank.kernel.events import Actor
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
PHONE = Actor(kind="user", via="phone")
TASKS = ["T1", "T2", "T3", "T4"]


@pytest.fixture
def rig(home: Any, clock: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, decomposing())
    yield made
    made.kernel.close()


async def to_the_split(rig: Rig) -> Any:
    """The run started, its brief done, its plan written; the DECOMPOSE's first message sent."""
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "About 60 grid points, at most 48 CPU-hours.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
    rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n\n1. The grid.\n2. The estimates.\n"})
    return await at_work(rig, "split")


async def proposed(rig: Rig, count: int = 4, summary: str = "Four tasks, one per step of the plan.") -> Any:
    """The DECOMPOSE proposed `count` tasks, submitted them and ended; the question that asks about them."""
    split = await to_the_split(rig)
    for number in range(1, count + 1):
        rig.runner.proposing.propose(WORKSPACE, task(number), actor=AGENT)
    rig.runner.proposing.submit(WORKSPACE, summary, actor=AGENT)
    rig.bridge.finish(split.session)
    return await until(lambda: question(rig, "proposed"))


def flow_of(rig: Rig) -> Flow:
    record = rig.kernel.settings.get(Flow.KIND, FLOW).record
    assert isinstance(record, Flow)
    return record


async def run_tasks(rig: Rig, names: list[str]) -> list[str]:
    """Each task's session finished with its deliverable as it is prompted; the tasks prompted, in order."""
    seen = []
    for name in names:
        prompt = await until(partial(rig.bridge.prompted, f"Study · {name} · try 1"))
        seen.append(name)
        number = name.removeprefix("T")
        rig.bridge.finish(prompt.session, {f"out/t{number}.md": f"Task {number}'s work.\n"})
    return seen


async def test_a_decompose_that_ends_without_submitting_fails_and_waits_at_a_gate(rig: Rig) -> None:
    async with running(rig.kernel):
        split = await to_the_split(rig)
        rig.runner.proposing.propose(WORKSPACE, task(1), actor=AGENT)
        rig.bridge.finish(split.session)
        failed = await until(lambda: question(rig, "Break it into tasks failed"))
        assert "it ended without submitting its tasks: a DECOMPOSE proposes each with flow_propose_box, then calls " \
               "flow_submit" in failed.title  # fmt: skip
        await anyio.sleep(0.1)
        assert question(rig, "proposed") is None, "nothing submitted is asked about while the box failed"
    assert rig.run().box("split").state == "failed"


async def test_submitting_asks_the_owner_one_question_about_the_proposals(rig: Rig) -> None:
    async with running(rig.kernel):
        split = await to_the_split(rig)
        with pytest.raises(RunError, match="you have proposed no box: propose each with flow_propose_box first"):
            rig.runner.proposing.submit(WORKSPACE, "None.", actor=AGENT)
        rig.runner.proposing.propose(WORKSPACE, task(1), actor=AGENT)
        rig.runner.proposing.propose(WORKSPACE, task(2, mode="auto"), actor=AGENT)
        said = rig.runner.proposing.submit(WORKSPACE, "Two tasks.", actor=AGENT)
        assert said["said"].startswith("Submitted 2 proposals (T1, T2): they wait for the user")
        assert "Stop now" in said["said"]
        asked = await until(lambda: question(rig, "proposed"))
        rig.bridge.finish(split.session)
        await until(lambda: rig.run().waiting is not None)
    assert asked.title == "Study: Break it into tasks proposed 2 boxes"
    assert asked.about is not None
    assert (asked.about.kind, asked.about.id) == ("flow", FLOW)
    assert [(option.id, option.key) for option in asked.options] == [("accept", "a"), ("reject", "r")]
    assert asked.detail.startswith("Two tasks.\n\n1 · TASK T1 · Task 1 · writes out/t1.md\n   why: The plan's step 1.")
    auto = "\n2 · TASK T2 · Task 2 · writes out/t2.md · in Auto: its changes are accepted without review\n"
    assert auto in asked.detail, "a proposal's mode is said where you decide it"
    assert "clank flow accept" in asked.detail
    assert [each.title for each in rig.waiting()] == [asked.title], "one question, asked once"
    waiting = rig.run().waiting
    assert waiting is not None
    assert (waiting.kind, waiting.box, waiting.question) == ("proposals", "split", asked.id)
    batch = rig.runner.proposing.batches.load(rig.run(), "split", 1)
    assert batch is not None
    assert (batch.summary, batch.question, batch.asked) == ("Two tasks.", asked.id, ["T1", "T2"])
    assert rig.run().box("split").state == "done"


async def test_accept_all_puts_t1_to_t4_in_order_between_decompose_and_integrate_and_they_run_one_at_a_time(
    rig: Rig,
) -> None:
    async with running(rig.kernel):
        await proposed(rig)
        await anyio.sleep(0.1)
        assert rig.bridge.prompted("Study · join · try 1") is None, "the run waits for the proposals"
        assert rig.bridge.prompted("Study · T1 · try 1") is None
        said = rig.runner.proposing.decide(FLOW, "accept", None, actor=OWNER)
        assert said["decided"] == TASKS
        assert await run_tasks(rig, TASKS) == TASKS
        await until(lambda: rig.bridge.prompted("Study · join · try 1"))
        assert question(rig, "proposed") is None, "the question is closed once each is decided"
    flow = flow_of(rig)
    assert [box.id for box in flow.boxes] == ["brief", "plan", "split", *TASKS, "join", "review"]
    for box in flow.boxes[3:7]:
        assert box.proposed is not None
        assert (box.proposed.run, box.proposed.by, box.proposed.accepted) == (1, "split", "owner")
    prompts = [rig.bridge.prompted(f"Study · {name} · try 1") for name in TASKS]
    assert [prompt.agent for prompt in prompts if prompt is not None] == ["build"] * 4, "a TASK's mode: the workspace's"
    batch = rig.runner.proposing.batches.load(rig.run(), "split", 1)
    assert batch is not None
    assert [(each.state, each.decided_by) for each in batch.proposals] == [("accepted", OWNER)] * 4


async def test_a_rejected_proposal_never_runs(rig: Rig) -> None:
    async with running(rig.kernel):
        await proposed(rig, count=3)
        rig.runner.proposing.decide(FLOW, "reject", ["T2"], actor=OWNER)
        await anyio.sleep(0.1)
        assert rig.bridge.prompted("Study · T1 · try 1") is None, "T1 and T3 still wait"
        rig.runner.proposing.decide(FLOW, "accept", ["T3", "T1"], actor=OWNER)
        assert await run_tasks(rig, ["T1", "T3"]) == ["T1", "T3"]
        await until(lambda: rig.bridge.prompted("Study · join · try 1"))
    assert [box.id for box in flow_of(rig).boxes] == ["brief", "plan", "split", "T1", "T3", "join", "review"]
    assert rig.bridge.prompted("Study · T2 · try 1") is None
    assert "T2" not in rig.run().boxes


async def test_an_edited_prompt_is_the_one_sent(rig: Rig) -> None:
    async with running(rig.kernel):
        await proposed(rig, count=1)
        changes = {"prompt": "Write out/t1.md: the 64 grid points, each with a fixed seed."}
        rig.runner.proposing.decide(FLOW, "accept", ["T1"], actor=OWNER, changes=changes)
        prompt = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
    assert "the 64 grid points, each with a fixed seed" in prompt.text
    assert "Write out/t1.md.\n" not in prompt.text
    [kept] = rig.runner.proposing.batches.load(rig.run(), "split", 1).proposals  # type: ignore[union-attr]
    assert kept.original is not None
    assert (kept.original.prompt, kept.box.prompt) == ("Write out/t1.md.", changes["prompt"])
    assert flow_of(rig).boxes[3].prompt == changes["prompt"]


async def test_an_edit_is_checked_as_a_proposal_is(rig: Rig) -> None:
    async with running(rig.kernel):
        await proposed(rig, count=1)
        with pytest.raises(RunError, match=r"deliverable \.\./out\.md climbs out of the folder"):
            rig.runner.proposing.decide(FLOW, "accept", ["T1"], actor=OWNER, changes={"writes": ["../out.md"]})
        with pytest.raises(RunError, match="a TASK writes a deliverable: name the files it writes in the folder"):
            rig.runner.proposing.decide(FLOW, "accept", ["T1"], actor=OWNER, changes={"writes": []})
        with pytest.raises(RunError, match="a PLAN writes a deliverable"):
            rig.runner.proposing.edit(FLOW, "T1", {"type": "plan", "writes": []}, actor=OWNER)
        with pytest.raises(RunError, match="an edit names one proposal"):
            rig.runner.proposing.decide(FLOW, "accept", ["T1", "T2"], actor=OWNER, changes={"title": "Both"})
        with pytest.raises(RunError, match="T9 is no proposal of Study's run 1 that waits for you: T1 waits"):
            rig.runner.proposing.decide(FLOW, "accept", ["T9"], actor=OWNER)
        edited = rig.runner.proposing.edit(FLOW, "T1", {"title": "The grid", "mode": "auto"}, actor=OWNER)
    assert edited["proposal"]["box"]["title"] == "The grid"
    batch = rig.runner.proposing.batches.load(rig.run(), "split", 1)
    assert batch is not None
    assert (batch.proposals[0].state, batch.proposals[0].box.mode) == ("proposed", "auto"), "edited, still waiting"
    assert [box.id for box in flow_of(rig).boxes] == ["brief", "plan", "split", "join", "review"]


async def test_the_question_answered_as_the_phone_answers_it_accepts_them_all(rig: Rig) -> None:
    async with running(rig.kernel):
        asked = await proposed(rig, count=2)
        rig.kernel.questions.answer(asked.id, by=PHONE, option="accept")
        assert await run_tasks(rig, ["T1", "T2"]) == ["T1", "T2"]
    batch = rig.runner.proposing.batches.load(rig.run(), "split", 1)
    assert batch is not None
    assert [(each.state, each.decided_by) for each in batch.proposals] == [("accepted", PHONE)] * 2


async def test_the_question_answered_reject_all_lets_the_flow_go_on_without_them(rig: Rig) -> None:
    async with running(rig.kernel):
        asked = await proposed(rig, count=2)
        rig.kernel.questions.answer(asked.id, by=PHONE, option="reject")
        join = await until(lambda: rig.bridge.prompted("Study · join · try 1"))
    assert join is not None
    assert [box.id for box in flow_of(rig).boxes] == ["brief", "plan", "split", "join", "review"]


async def test_the_agent_cannot_accept(rig: Rig) -> None:
    async with running(rig.kernel):
        await proposed(rig, count=1)
        with pytest.raises(RunError, match="the agent proposes boxes; only the user decides them"):
            rig.runner.proposing.decide(FLOW, "accept", None, actor=AGENT)
        with pytest.raises(RunError, match="the agent proposes boxes; only the user decides them"):
            rig.runner.proposing.edit(FLOW, "T1", {"title": "Mine"}, actor=AGENT)
    assert [box.id for box in flow_of(rig).boxes] == ["brief", "plan", "split", "join", "review"]


async def test_each_decision_is_an_event_with_its_actor(rig: Rig) -> None:
    async with running(rig.kernel):
        await proposed(rig, count=2)
        rig.runner.proposing.decide(FLOW, "accept", ["T1"], actor=OWNER, changes={"title": "The grid"})
        rig.runner.proposing.decide(FLOW, "reject", ["T2"], actor=OWNER)
        await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
    accepted, rejected = rig.events("flows.proposal_decided")
    assert accepted.actor == OWNER
    assert accepted.summary == "you (console) accepted T1 (The grid), edited, proposed by Break it into tasks"
    assert accepted.data == {
        "flow": FLOW, "run": 1, "box": "split", "try": 1, "proposal": "T1", "decision": "accepted", "edited": True,
    }  # fmt: skip
    assert (rejected.data["proposal"], rejected.data["decision"], rejected.data["edited"]) == ("T2", "rejected", False)


async def test_proposals_the_flow_no_longer_takes_wait_saying_why_and_are_asked_about_again(rig: Rig) -> None:
    async with running(rig.kernel):
        split = await to_the_split(rig)
        gate = task(1, after="join", type="gate", title="You look at the summary", deliverable=[])
        rig.runner.proposing.propose(WORKSPACE, gate, actor=AGENT)
        rig.runner.proposing.submit(WORKSPACE, "A gate after the summary.", actor=AGENT)
        rig.bridge.finish(split.session)
        asked = await until(lambda: question(rig, "proposed"))
        await until(lambda: rig.run().waiting is not None)
        renamed = decomposing()
        renamed["boxes"][3]["id"] = "merge"  # you renamed the box it was proposed after
        renamed["lines"] = [
            {"from": "brief", "to": "plan"}, {"from": "plan", "to": "split"}, {"from": "split", "to": "merge"},
            {"from": "merge", "to": "review"},
        ]  # fmt: skip
        rig.write_flow(renamed)
        rig.kernel.questions.answer(asked.id, by=PHONE, option="accept")
        again = await until(lambda: next((each for each in rig.waiting() if each.id != asked.id), None))
    assert "G1 cannot join the flow as it is now" in again.detail
    assert "names no box of the flow: join" in again.detail
    batch = rig.runner.proposing.batches.load(rig.run(), "split", 1)
    assert batch is not None
    assert batch.proposals[0].state == "proposed", "it waits for you, saying why"
    assert batch.question == again.id
