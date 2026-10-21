"""Design 0013 §6 and §10 (decisions 0061 and 0065): the runner's routes, `/flows/<workspace>/<name>/run|pause|stop`
and `/runs`, each recorded with the client that asked; and a gate answered from the phone, as the phone page sends it
(an option, no words), lets the flow go on. The service runs in the test (its routes, its operations, the flows'
runner), against the fake bridge and a synthetic folder."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.remote import tailnet
from clank.components.remote.app import create_phone_app
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.components.flows.rig import Rig, make_rig, question, study

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "cli"}
LOGIN = "owner@example.com"
THROUGH_TAILSCALE = {"Tailscale-User-Login": LOGIN}
YOU = Actor(kind="user", via="console")


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, study())
    monkeypatch.setattr(made.kernel.parts["remote"], "owner_login", lambda: LOGIN)
    monkeypatch.setattr(tailnet, "read", lambda: tailnet.Tailnet("desk.tail0.ts.net", LOGIN))
    yield made
    made.kernel.close()


@pytest.fixture
def http(rig: Rig) -> Iterator[TestClient]:
    app = create_app(rig.kernel, token="t", port=7720, background=[rig.kernel.parts["flows"].run])
    with TestClient(app, base_url="http://127.0.0.1:7720") as client:
        yield client


def call(http: TestClient, method: str, path: str, status: int = 200, body: dict[str, Any] | None = None) -> Any:
    answer = http.request(method, f"/api/v1/{path}", headers=AUTH, json=(body or {}) if method == "POST" else None)
    assert answer.status_code == status, answer.text
    return answer.json()


def waits_for(found: Any, seconds: float = 10) -> Any:
    """What `found` gives once it gives something truthy, waiting in this thread while the service runs in its own."""
    import time

    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = found()
        if value:
            return value
        time.sleep(0.02)
    raise AssertionError("it did not happen in time")


def test_a_gate_answered_from_the_phone_lets_the_flow_go_on(rig: Rig, http: TestClient) -> None:
    started = call(http, "POST", "flows/myproject/study/run")
    assert (started["did"], started["run"]["status"]) == ("started", "running")
    assert started["order"] == ["brief", "plan", "approve", "T1"]
    brief = waits_for(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "The brief.\n")
    call(http, "POST", f"questions/{brief.id}/answer", body={"option": "done"})
    plan = waits_for(lambda: rig.bridge.prompted("Study · plan · try 1"))
    rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
    gate = waits_for(lambda: question(rig, "You approve the plan"))

    code = rig.kernel.parts["remote"].pair("my phone", actor=YOU)["code"]
    phone_app = create_phone_app(rig.kernel.parts["remote"])
    with TestClient(phone_app, base_url="https://desk.tail0.ts.net:8445", client=("127.0.0.1", 50000)) as phone:
        acting = {**THROUGH_TAILSCALE, "X-Clank-Phone": "1"}
        assert phone.post("/api/pair", json={"code": code}, headers=acting).status_code == 200
        listed = phone.get("/api/overview", headers=THROUGH_TAILSCALE).json()
        assert [each["id"] for each in listed["questions"]] == [gate.id], "the phone lists the gate"
        answered = phone.post(f"/api/clank-questions/{gate.id}", json={"option": "approve"}, headers=acting)
        assert answered.status_code == 200, answered.text
    waits_for(lambda: rig.bridge.prompted("Study · T1 · try 1"))
    settled = rig.kernel.questions.get(gate.id)
    assert settled.answer is not None
    assert settled.answer.by.kind == "device"
    [ended] = [event for event in rig.events("flows.box_ended") if event.data["box"] == "approve"]
    assert ended.actor.kind == "device"


def test_the_routes_start_pause_resume_stop_and_run_from_a_box_each_recorded_with_its_client(
    rig: Rig, http: TestClient
) -> None:
    assert call(http, "POST", "flows/myproject/study/run")["did"] == "started"
    refused = call(http, "POST", "flows/myproject/study/run", 409)
    assert "already runs" in refused["error"]["message"]
    assert call(http, "POST", "flows/myproject/study/pause")["run"]["paused"] is True
    assert call(http, "POST", "flows/myproject/study/run")["did"] == "resumed"
    stopped = call(http, "POST", "flows/myproject/study/stop")
    assert stopped["run"]["status"] == "stopped"
    again = call(http, "POST", "flows/myproject/study/run", body={"from": "brief"})
    assert (again["did"], again["run"]["number"], again["run"]["at"]) == ("from", 1, "brief")
    assert call(http, "POST", "flows/myproject/nothing/run", 404)["error"]["code"] == "not_found"
    nowhere = call(http, "POST", "flows/myproject/study/run", 409, {"from": "nowhere"})
    assert "has no box nowhere" in nowhere["error"]["message"]
    runs = call(http, "GET", "flows/myproject/study/runs")
    assert [run["number"] for run in runs["runs"]] == [1]
    assert runs["order"] == ["brief", "plan", "approve", "T1"]
    actors = {(event.type, event.actor.via) for event in rig.events("flows.run_started", "flows.run_steered",
                                                                    "flows.run_ended")}  # fmt: skip
    assert actors == {("flows.run_started", "cli"), ("flows.run_steered", "cli"), ("flows.run_ended", "cli")}
