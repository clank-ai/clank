"""Design 0013 §9 (decisions 0020 and 0064), end to end through the service's routes and the gateway: a DECOMPOSE's
model reads its flow (`GET /flows/read`: the flow, the box it is, each box's state, its proposals), proposes boxes and
submits them through the gateway, each refusal in the service's words; its acceptance through the gateway is refused,
and so is one the service hears from the client `agent`; the owner's acceptance through the API (`POST
/api/v1/flows/<workspace>/<name>/proposals/accept`) joins the tasks to the flow, and `GET .../proposals` lists each
batch and what waits. Run against the fake bridge and a synthetic folder."""

import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.client import Client
from clank.components.flows.kinds import Flow
from clank.components.flows.verdicts import AGENT
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import create_gateway, flows_forwarder
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import FLOW, Rig, decomposing, is_sent, make_rig, question, task

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
AS_AGENT = {"Authorization": "Bearer t", "X-Clank-Client": "agent"}
ROUTE = "/api/v1/flows/myproject/study"


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, decomposing())
    yield made
    made.kernel.close()


def waits_for(found: Callable[[], Any], seconds: float = 10) -> Any:
    """What `found` gives once it gives something truthy, waiting in this thread while the service runs in its own."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = found()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("it did not happen in time")


def test_a_decompose_proposes_through_the_gateway_and_only_the_owner_accepts(rig: Rig) -> None:
    app = create_app(rig.kernel, token="t", port=7720, background=[rig.kernel.parts["flows"].run])
    with TestClient(app, base_url="http://127.0.0.1:7720") as service:
        forward = flows_forwarder(lambda: Client("http://127.0.0.1:7720", "t", name="agent", http=service), close=False)
        with TestClient(create_gateway(Routes(), GatewaySettings(), None, flows=forward)) as gateway:
            assert service.post(f"{ROUTE}/run", headers=AUTH, json={}).status_code == 200
            brief = waits_for(lambda: question(rig, "Brief"))
            rig.write("BRIEF.md", "About 60 grid points.\n")
            service.post(f"/api/v1/questions/{brief.id}/answer", headers=AUTH, json={"option": "done"})
            plan = waits_for(lambda: rig.bridge.prompted("Study · plan · try 1"))
            rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
            split = waits_for(lambda: rig.bridge.prompted("Study · split · try 1"))
            waits_for(lambda: is_sent(rig, "split"))

            read = gateway.get("/flows/read", params={"workspace": "myproject"})
            assert read.status_code == 200, read.text
            flow = read.json()
            assert (flow["flow"], flow["run"], flow["you_are"]) == (FLOW, 1, "split")
            assert [box["id"] for box in flow["boxes"]] == ["brief", "plan", "split", "join", "review"]
            assert [box["state"] for box in flow["boxes"]][:3] == ["done", "done", "running"]
            assert flow["boxes"][2]["next"] == ["join"]
            assert "only by proposals" in flow["said"]

            refused = gateway.post("/flows/propose", json={"workspace": "myproject", **task(1, deliverable="../x.md")})
            assert refused.status_code == 409
            assert refused.json()["error"]["message"].startswith("deliverable ../x.md climbs out of the folder")
            for number in (1, 2):
                proposed = gateway.post("/flows/propose", json={"workspace": "myproject", **task(number)})
                assert proposed.status_code == 200, proposed.text
                assert proposed.json()["proposal"] == f"T{number}"
            submitted = gateway.post("/flows/submit", json={"workspace": "myproject", "summary": "Two tasks."})
            assert submitted.status_code == 200, submitted.text
            assert gateway.get("/flows/read", params={"workspace": "myproject"}).json()["proposals"] == [
                {"id": "T1", "after": "split", "type": "task", "title": "Task 1", "state": "proposed", "by": "split"},
                {"id": "T2", "after": "split", "type": "task", "title": "Task 2", "state": "proposed", "by": "split"},
            ]

            through = gateway.post("/flows/myproject/study/proposals/accept", json={"all": True})
            assert through.status_code == 403, "the gateway forwards no decision"
            as_agent = service.post(f"{ROUTE}/proposals/accept", headers=AS_AGENT, json={"all": True})
            assert as_agent.status_code == 403, as_agent.text
            assert "only the user decides them" in as_agent.json()["error"]["message"]

            rig.bridge.finish(split.session)
            waits_for(lambda: rig.run().waiting is not None)
            listed = service.get(f"{ROUTE}/proposals", headers=AUTH).json()
            assert (listed["run"], listed["waiting"]) == (1, ["T1", "T2"])
            assert [batch["box"] for batch in listed["batches"]] == ["split"]
            accepted = service.post(f"{ROUTE}/proposals/accept", headers=AUTH, json={"all": True})
            assert accepted.status_code == 200, accepted.text
            assert accepted.json()["decided"] == ["T1", "T2"]
            waits_for(lambda: rig.bridge.prompted("Study · T1 · try 1"))

    record = rig.kernel.settings.get(Flow.KIND, FLOW).record
    assert isinstance(record, Flow)
    assert [box.id for box in record.boxes] == ["brief", "plan", "split", "T1", "T2", "join", "review"]
    [decided, _] = rig.events("flows.proposal_decided")
    assert (decided.actor.kind, decided.actor.via) == ("user", "console")


def test_the_owners_routes_reject_and_edit_a_proposal(rig: Rig) -> None:
    app = create_app(rig.kernel, token="t", port=7720, background=[rig.kernel.parts["flows"].run])
    with TestClient(app, base_url="http://127.0.0.1:7720") as service:
        service.post(f"{ROUTE}/run", headers=AUTH, json={})
        brief = waits_for(lambda: question(rig, "Brief"))
        rig.write("BRIEF.md", "About 60 grid points.\n")
        service.post(f"/api/v1/questions/{brief.id}/answer", headers=AUTH, json={"option": "done"})
        plan = waits_for(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        waits_for(lambda: rig.bridge.prompted("Study · split · try 1"))
        waits_for(lambda: is_sent(rig, "split"))
        for number in (1, 2):
            rig.runner.proposing.propose("myproject", task(number), actor=AGENT)
        edited = service.post(
            f"{ROUTE}/proposals/edit", headers=AUTH, json={"proposal": "T1", "changes": {"title": "The grid"}}
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["proposal"]["box"]["title"] == "The grid"
        wrong = service.post(f"{ROUTE}/proposals/edit", headers=AUTH, json={"proposal": "T1", "changes": {"id": "X"}})
        assert wrong.status_code == 409
        assert wrong.json()["error"]["message"].startswith("id: not a setting of a box you may change")
        rejected = service.post(f"{ROUTE}/proposals/reject", headers=AUTH, json={"proposals": ["T2"]})
        assert rejected.status_code == 200, rejected.text
        unknown = service.post(f"{ROUTE}/proposals/reject", headers=AUTH, json={"proposals": ["T2"]})
        assert unknown.status_code == 409
        nothing = service.post(f"{ROUTE}/proposals/accept", headers=AUTH, json={})
        assert nothing.status_code == 400, "name the proposals, or all of them"
    batch = rig.runner.proposing.batches.load(rig.run(), "split", 1)
    assert batch is not None
    assert [(each.state, each.box.title) for each in batch.proposals] == [
        ("proposed", "The grid"),
        ("rejected", "Task 2"),
    ]
