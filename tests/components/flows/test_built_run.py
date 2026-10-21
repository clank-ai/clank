"""Design 0013 §2, §10 and §15 (decision 0098): a flow built with the model runs on its own until its final review. Its
first box, a YOU, is done by itself when the brief written with the model is in the folder, at each run, its event
saying so; without the brief, or with the brief as it was before the planning began, it asks, as any YOU; a flow not
built asks for its brief as before. A built flow runs from its brief to its last gate asking nothing else: its VERIFY
passes on, the tasks its DECOMPOSE proposes are accepted on their own, every one whatever the flow's cap, and run in
auto mode, each change they ask to make answered at once while the workspace stays in review, the INTEGRATE, and only
then the owner's review. Run against the fake bridge and a synthetic folder."""

from collections.abc import Iterator
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from clank.components.flows.deliverables import fingerprint
from clank.components.flows.kinds import Flow
from clank.components.flows.verdicts import AGENT
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
    task,
    until,
)
from tests.components.flows.test_flow_built import built_flow

pytestmark = pytest.mark.anyio
BRIEF = "# A new simulation study\n\n- at most 48 CPU-hours\n"


def built(**changes: Any) -> dict[str, Any]:
    """The built flow, titled Study (the rig's helpers name its sessions so), on what the main slot runs."""
    return built_flow(title="Study", defaults={}, **changes)


@pytest.fixture
def rig(home: Any, clock: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, built())
    yield made
    made.kernel.close()


def flow_of(rig: Rig) -> Flow:
    record = rig.kernel.settings.get(Flow.KIND, FLOW).record
    assert isinstance(record, Flow)
    return record


def asked(rig: Rig) -> list[str]:
    """The title of every question asked, in order."""
    return [event.summary for event in rig.events("question.asked")]


async def test_a_built_flows_run_starts_past_its_you_box_when_its_brief_is_in_the_folder(rig: Rig) -> None:
    rig.write("BRIEF.md", BRIEF)
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await at_work(rig, "plan")
    assert question(rig, "Your brief") is None
    assert asked(rig) == [], "nothing asked of the owner"
    brief = rig.run().box("brief")
    assert brief.state == "done"
    assert [kept.path for kept in brief.kept] == ["BRIEF.md"]
    [ended] = [event for event in rig.events("flows.box_ended") if event.data["box"] == "brief"]
    assert ended.data["outcome"] == "done"
    assert "BRIEF.md, the brief written with the model" in ended.summary


async def test_a_brief_left_as_it_was_before_the_planning_does_not_pass_and_the_you_box_asks(rig: Rig) -> None:
    rig.write("BRIEF.md", BRIEF)
    flow = built()
    flow["built"]["before"] = fingerprint(rig.folder, "BRIEF.md").sha256  # the brief, as the planning found it
    rig.write_flow(flow)
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await until(lambda: question(rig, "Your brief"))


async def test_without_its_brief_a_built_flows_you_box_asks(rig: Rig) -> None:
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        waiting = await until(lambda: question(rig, "Your brief"))
    assert "write BRIEF.md, then say it is done" in waiting.title


async def test_a_flow_not_built_asks_for_its_brief_as_before(rig: Rig) -> None:
    rig.write_flow(study(), "plain")
    rig.write("BRIEF.md", BRIEF)
    async with running(rig.kernel):
        rig.runner.start(f"{WORKSPACE}/plain", actor=OWNER)
        await until(lambda: question(rig, "Study: Brief"))


async def test_a_built_flow_accepts_every_task_its_decompose_proposes_whatever_its_cap(rig: Rig) -> None:
    rig.write_flow(built(auto_accept_cap=1))
    rig.write("BRIEF.md", BRIEF)
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        plan = await at_work(rig, "plan")
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        check = await at_work(rig, "check")
        rig.runner.verdict(WORKSPACE, "pass", [], [], actor=AGENT)
        rig.bridge.finish(check.session)
        await at_work(rig, "split")
        states = [rig.runner.proposing.propose(WORKSPACE, task(n), actor=AGENT)["state"] for n in (1, 2, 3)]
    assert states == ["accepted", "accepted", "accepted"], "a cap would stop a built flow in its middle"


async def test_a_built_flow_runs_from_its_brief_to_its_last_gate_asking_nothing_else(rig: Rig) -> None:
    rig.write("BRIEF.md", BRIEF)
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        plan = await at_work(rig, "plan")
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n\n1. The grid\n2. The sweep\n"})
        check = await at_work(rig, "check")
        rig.runner.verdict(WORKSPACE, "pass", [], [], actor=AGENT)
        rig.bridge.finish(check.session)
        split = await at_work(rig, "split")
        states = [rig.runner.proposing.propose(WORKSPACE, task(n), actor=AGENT)["state"] for n in (1, 2)]
        assert states == ["accepted", "accepted"], "accepted on their own: auto-accept is on in a built flow"
        rig.runner.proposing.submit(WORKSPACE, "Two tasks.", actor=AGENT)
        rig.bridge.finish(split.session)
        for name in ("T1", "T2"):
            prompt = await until(partial(rig.bridge.prompted, f"Study · {name} · try 1"))
            assert prompt.agent == "build"
            edits = f"/workspace/out/t{name[1:]}.md"
            rig.bridge.say({
                "type": "asked", "port": prompt.port, "input": {"filePath": edits, "content": "Done."},
                "request": {"id": f"per_{name}", "sessionID": prompt.session, "permission": "edit",
                            "patterns": [edits[len("/workspace/"):]],
                            "metadata": {"filepath": edits, "diff": "+Done."}},
            })  # fmt: skip
            assert [str(prompt.port), f"per_{name}", "once"] in rig.bridge.done("permission"), "answered at once"
            rig.bridge.finish(prompt.session, {f"out/t{name[1:]}.md": "Done.\n"})
        join = await at_work(rig, "join")
        rig.bridge.finish(join.session, {"SUMMARY.md": "# What was done\n", "NEXT.md": "# Run the study\n"})
        review = await until(lambda: question(rig, "You review the whole"))
    assert asked(rig) == [f"Clank (flow runner) asks: {review.title}"], "the owner was asked one thing: the review"
    assert rig.kernel.parts["agents"].review.mode(WORKSPACE) == "review", "the workspace's own mode stays as it was"
    tasks = [box for box in flow_of(rig).boxes if box.type == "task"]
    assert [(box.id, box.mode) for box in tasks] == [("T1", "auto"), ("T2", "auto")], "accepted into a built flow"
    order = [event.data["box"] for event in rig.events("flows.box_started")]
    assert order == ["plan", "check", "split", "T1", "T2", "join", "review"]
