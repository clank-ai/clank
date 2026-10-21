"""Design 0013 §9 (decision 0064): a box's model proposes boxes with `flow_propose_box`, which the service gives to the
box at work in the workspace its MCP server names, while its try runs. Each proposal is checked when staged and refused
with its reason, so the model can fix it: a deliverable outside the folder, or one agents load as settings or
instructions, an unknown type, an `after` naming no box, an unknown preset, an empty prompt, and one that would break
the flow's rules (in the rule's words). A proposal that passes is kept in its try's batch with an id of its own, waiting
for the owner: it is not in the flow. A proposal while no box works, or from another workspace's server, is refused, and
reaches no flow. Each proposal is an event with its actor, which says its mode of its own. Run against the fake bridge
and a synthetic folder."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from clank.components.flows.kinds import Flow
from clank.components.flows.runner import RunError
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
    rig.write("BRIEF.md", "About 60 grid points, at most 48 CPU-hours.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
    rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n\n1. The grid.\n2. The estimates.\n"})
    return await at_work(rig, "split")


def propose(rig: Rig, given: dict[str, Any], workspace: str = WORKSPACE) -> dict[str, Any]:
    return rig.runner.proposing.propose(workspace, given, actor=AGENT)


def flow_boxes(rig: Rig) -> list[str]:
    record = rig.kernel.settings.get(Flow.KIND, FLOW).record
    assert isinstance(record, Flow)
    return [box.id for box in record.boxes]


async def test_a_decomposes_proposal_is_staged_in_its_trys_batch_with_an_id_of_its_own_not_in_the_flow(
    rig: Rig,
) -> None:
    async with running(rig.kernel):
        split = await to_the_split(rig)
        assert split.agent == "planner", "a DECOMPOSE runs in Plan mode by default"
        first = propose(rig, task(1, mode="auto", accept_when="every point has a seed\nabout 60 points"))
        second = propose(rig, task(2, sees=["PLAN.md", "out/t1.md"]))
    assert (first["proposal"], first["number"], first["state"]) == ("T1", 1, "proposed")
    assert "it waits for the user" in first["said"]
    assert "flow_submit" in first["said"]
    assert second["proposal"] == "T2"
    batch = rig.runner.proposing.batches.load(rig.run(), "split", 1)
    assert batch is not None
    assert rig.runner.proposing.batches.path(rig.run(), "split", 1).name == "proposals.json"
    t1, t2 = batch.proposals
    assert (t1.after, t1.state, t1.by, t1.why) == ("split", "proposed", AGENT, "The plan's step 1.")
    assert (t1.box.id, t1.box.type, t1.box.writes, t1.box.mode) == ("T1", "task", ["out/t1.md"], "auto")
    assert t1.box.accept_when == ["every point has a seed", "about 60 points"]
    assert t2.box.sees == ["PLAN.md", "out/t1.md"]
    assert flow_boxes(rig) == ["brief", "plan", "split", "join", "review"], "nothing joins the flow until accepted"


async def test_a_proposal_outside_the_folder_is_refused_with_its_reason(rig: Rig) -> None:
    async with running(rig.kernel):
        await to_the_split(rig)
        with pytest.raises(RunError, match=r"deliverable \.\./grid\.json climbs out of the folder \('\.\.'\)"):
            propose(rig, task(1, deliverable="../grid.json"))
        with pytest.raises(RunError, match=r"deliverable /etc/grid\.json is not in the folder"):
            propose(rig, task(1, deliverable=["out/a.md", "/etc/grid.json"]))
        with pytest.raises(RunError, match=r"sees C:/data/grid\.json is not in the folder"):
            propose(rig, task(1, sees=["C:/data/grid.json"]))
        with pytest.raises(RunError, match=r"deliverable out\\grid\.json is written with '\\'"):
            propose(rig, task(1, deliverable="out\\grid.json"))
    assert rig.runner.proposing.batches.load(rig.run(), "split", 1) is None, "nothing refused is kept"


async def test_a_deliverable_agents_load_as_settings_or_instructions_is_refused(rig: Rig) -> None:
    async with running(rig.kernel):
        await to_the_split(rig)
        with pytest.raises(RunError, match=r"\.opencode/agent/planner\.md is in \.opencode, a folder agents"):
            propose(rig, task(1, deliverable=".opencode/agent/planner.md"))
        with pytest.raises(RunError, match=r"\.GitHub/workflows/x\.yml is in \.GitHub"):
            propose(rig, task(1, deliverable=".GitHub/workflows/x.yml", mode="auto"))
        with pytest.raises(RunError, match=r"deliverable docs/agents\.md instructs agents and assistants"):
            propose(rig, task(1, deliverable="docs/agents.md"))


async def test_an_unknown_type_an_after_naming_no_box_an_unknown_preset_or_an_empty_prompt_is_refused_saying_why(
    rig: Rig,
) -> None:
    async with running(rig.kernel):
        await to_the_split(rig)
        with pytest.raises(RunError, match="type is one of you, plan, verify, decompose, task, integrate, gate, not "
                                           "'subtask'"):  # fmt: skip
            propose(rig, task(1, type="subtask"))
        with pytest.raises(RunError, match="after names no box of the flow: T9; name the box it comes after, one of "
                                           "brief, plan, split, join, review"):  # fmt: skip
            propose(rig, task(1, after="T9"))
        with pytest.raises(RunError, match="model names the preset 'huge 1M', which does not exist; the main slot's "
                                           "are: daily 262K"):  # fmt: skip
            propose(rig, task(1, model="huge 1M"))
        with pytest.raises(RunError, match="the prompt is empty: write everything the box's model must know"):
            propose(rig, task(1, prompt="  "))
        with pytest.raises(RunError, match="the title is empty"):
            propose(rig, task(1, title=""))
        with pytest.raises(RunError, match="a TASK writes a deliverable: name the files it writes in the folder"):
            propose(rig, task(1, deliverable=[]))
        with pytest.raises(RunError, match="mode is one of plan, review, auto"):
            propose(rig, task(1, mode="yolo"))
        kept = propose(rig, task(1, model="daily 262k"))
    assert kept["proposal"] == "T1", "a preset by its title, in any case"


async def test_a_proposal_that_would_break_the_flows_rules_is_refused_in_the_rules_words(rig: Rig) -> None:
    async with running(rig.kernel):
        await to_the_split(rig)
        with pytest.raises(RunError, match=r"T1 would break the flow's rules: T1: grid\.json is not Markdown, and T1 "
                                           "runs in Plan mode"):  # fmt: skip
            propose(rig, task(1, deliverable="grid.json", mode="plan"))
        with pytest.raises(RunError, match="G1: a GATE is done by you: it has no model"):
            propose(rig, task(1, type="gate", model="daily 262K", deliverable=[]))
        with pytest.raises(RunError, match="after names no box of the flow: T1"):
            propose(rig, task(2, after="T1"))  # T1 is not proposed yet, nor ever a box before it is accepted
        kept = propose(rig, task(1))
    assert kept["proposal"] == "T1", "a refused proposal takes no id"
    batch = rig.runner.proposing.batches.load(rig.run(), "split", 1)
    assert batch is not None
    assert [each.id for each in batch.proposals] == ["T1"], "a refused proposal is not kept"


async def test_a_proposal_while_no_box_works_is_refused(rig: Rig) -> None:
    with pytest.raises(RunError, match="no box of a flow works in myproject now: only a box of a running flow"):
        propose(rig, task(1))
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        asked = await until(lambda: question(rig, "Brief"))
        with pytest.raises(RunError, match="no box of a flow works in myproject now"):
            propose(rig, task(1))  # a YOU box: the owner's
        rig.write("BRIEF.md", "The brief.\n")
        rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        split = await until(lambda: rig.bridge.prompted("Study · split · try 1"))
        rig.bridge.finish(split.session)
        await until(lambda: question(rig, "Break it into tasks failed"))
        with pytest.raises(RunError, match="no box of a flow works in myproject now"):
            propose(rig, task(1))


async def test_a_proposal_from_one_workspaces_server_reaches_only_that_workspaces_flow(rig: Rig) -> None:
    async with running(rig.kernel):
        await to_the_split(rig)
        with pytest.raises(RunError, match="no box of a flow works in elsewhere now"):
            propose(rig, task(1), workspace="elsewhere")
        with pytest.raises(RunError, match="split works in the flow study, not another: a box proposes boxes for "
                                           "its own flow"):  # fmt: skip
            propose(rig, task(1, flow="another"))
        assert rig.runner.proposing.batches.load(rig.run(), "split", 1) is None
        kept = propose(rig, task(1, flow="study"))
    assert (kept["flow"], kept["proposal"]) == (FLOW, "T1")


async def test_each_proposal_is_an_event_with_its_actor(rig: Rig) -> None:
    async with running(rig.kernel):
        await to_the_split(rig)
        propose(rig, task(1))
        propose(rig, task(2, after="split", type="Task", mode="auto"))
    first, second = rig.events("flows.proposed")
    assert first.actor == AGENT
    assert first.summary == "Break it into tasks proposed T1 (Task 1) after split"
    assert second.summary == (
        "Break it into tasks proposed T2 (Task 2) after split, in Auto: its changes are accepted without review"
    )
    assert first.data == {
        "flow": FLOW, "run": 1, "box": "split", "try": 1, "proposal": "T1", "type": "task", "after": "split",
        "state": "proposed",
    }  # fmt: skip
    assert second.data["proposal"] == "T2"
    assert "Write out/t1.md" not in str(first.data), "no event holds a prompt's text"
