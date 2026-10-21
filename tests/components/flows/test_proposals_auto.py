"""Design 0013 §9 (decision 0064) and design 0002 §2.2: auto-accept, a flow's setting off by default. With it on, a
proposal that passes the checks joins the flow's file at once, marked as accepted by the setting, up to its cap in a
run; past the cap, proposals wait for the owner. Auto-accept writes the flow's file through the settings like any
change, so an edit the owner makes on the version it has just replaced is refused, with both versions shown. Run against
the fake bridge and a synthetic folder."""

from collections.abc import Iterator
from functools import partial
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.flows.kinds import Flow
from clank.components.flows.proposing import AUTO_ACCEPT
from clank.components.flows.verdicts import AGENT
from clank.kernel.api import create_app
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
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}


@pytest.fixture
def rig(home: Any, clock: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, decomposing(auto_accept=True, auto_accept_cap=2))
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


def flow_of(rig: Rig) -> Flow:
    record = rig.kernel.settings.get(Flow.KIND, FLOW).record
    assert isinstance(record, Flow)
    return record


async def test_with_auto_accept_on_a_proposal_joins_the_flow_at_once_marked_as_accepted_by_the_setting(
    rig: Rig,
) -> None:
    async with running(rig.kernel):
        await to_the_split(rig)
        said = rig.runner.proposing.propose(WORKSPACE, task(1), actor=AGENT)
        assert said["state"] == "accepted"
        assert "it joined the flow at once: auto-accept is on for this flow" in said["said"]
        flow = flow_of(rig)
        assert [box.id for box in flow.boxes] == ["brief", "plan", "split", "T1", "join", "review"], "while it works"
    t1 = flow.boxes[3]
    assert t1.proposed is not None
    assert (t1.proposed.run, t1.proposed.by, t1.proposed.accepted) == (1, "split", "auto-accept")
    [proposed] = rig.events("flows.proposed")
    assert (proposed.actor, proposed.data["state"]) == (AGENT, "accepted")
    [decided] = rig.events("flows.proposal_decided")
    assert (decided.actor, decided.data["decision"]) == (AUTO_ACCEPT, "accepted")
    changed = [event for event in rig.events("settings.changed") if event.data.get("kind") == "flow"]
    assert changed[-1].actor == AUTO_ACCEPT, "the flow's file written by the setting, as any change"
    batch = rig.runner.proposing.batches.load(rig.run(), "split", 1)
    assert batch is not None
    assert batch.proposals[0].decided_by == AUTO_ACCEPT


async def test_auto_accept_stops_at_its_cap_and_the_rest_wait_for_the_owner(rig: Rig) -> None:
    async with running(rig.kernel):
        split = await to_the_split(rig)
        states = [rig.runner.proposing.propose(WORKSPACE, task(n), actor=AGENT)["state"] for n in range(1, 5)]
        assert states == ["accepted", "accepted", "proposed", "proposed"]
        assert [box.id for box in flow_of(rig).boxes][3:5] == ["T1", "T2"]
        rig.runner.proposing.submit(WORKSPACE, "Four tasks.", actor=AGENT)
        asked = await until(lambda: question(rig, "proposed"))
        assert asked.title == "Study: Break it into tasks proposed 2 boxes", "only those past the cap wait"
        assert "T3" in asked.detail
        assert "T1" not in asked.detail
        rig.bridge.finish(split.session)
        await until(lambda: rig.run().waiting is not None)
        assert rig.bridge.prompted("Study · T1 · try 1") is None, "the run waits for the rest"
        rig.runner.proposing.decide(FLOW, "accept", None, actor=OWNER)
        for name in ("T1", "T2", "T3", "T4"):
            prompt = await until(partial(rig.bridge.prompted, f"Study · {name} · try 1"))
            rig.bridge.finish(prompt.session, {f"out/t{name[1:]}.md": "Done.\n"})
        await until(lambda: rig.bridge.prompted("Study · join · try 1"))
    marks = [(box.id, box.proposed.accepted) for box in flow_of(rig).boxes if box.proposed is not None]
    assert marks == [("T1", "auto-accept"), ("T2", "auto-accept"), ("T3", "owner"), ("T4", "owner")]


async def test_an_owners_edit_made_on_the_version_auto_accept_has_just_replaced_is_refused_with_both_versions_shown(
    rig: Rig,
) -> None:
    read = rig.kernel.settings.get(Flow.KIND, FLOW)
    async with running(rig.kernel):
        await to_the_split(rig)
        rig.runner.proposing.propose(WORKSPACE, task(1), actor=AGENT)
    mine = {**read.record.model_dump(mode="json"), "title": "My study"}
    with TestClient(create_app(rig.kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as service:
        answer = service.put(f"/api/v1/records/flow/{FLOW}", headers=AUTH, json={"values": mine, "base": read.revision})
    assert answer.status_code == 409, answer.text
    error = answer.json()["error"]
    assert "changed since it was read; here is its current version" in error["message"]
    assert [box["id"] for box in error["current"]["values"]["boxes"]][3] == "T1", "the version auto-accept wrote"
    assert error["current"]["values"]["title"] == "Study"
    assert flow_of(rig).title == "Study", "your edit is not written over it"
