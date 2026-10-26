"""Design 0025 §6 (design 0013 §12 and §14 step 7): the phone's Flows screens, on the listener's flow routes. The list
is the service's summaries, each flow with its state in words and the question it waits for, with the plannings open
and a planning's flow listed as building before its file is written; a flow's screen is the Flow view's JSON, as the
console draws it; run, pause and stop from the phone are recorded as the device's; a batch of proposals accepted from
the phone joins the flow; a planning opened from the phone goes to Clank's VS Code window on the PC and waits for it
when none runs there; the kernel's refusals reach the phone with their words. Run against the fake bridge and a
synthetic folder."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio.to_thread
import httpx2
import pytest
from fastapi.testclient import TestClient

from clank.components.flows.kinds import Flow
from clank.components.flows.verdicts import AGENT
from clank.components.remote import tailnet
from clank.components.remote.app import create_phone_app
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
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
    study,
    task,
    until,
)

pytestmark = pytest.mark.anyio
LOGIN = "owner@example.com"
THROUGH_TAILSCALE = {"Tailscale-User-Login": LOGIN}
ACT = {**THROUGH_TAILSCALE, "X-Clank-Phone": "1"}
BASE = "https://desk.tail0.ts.net:8445"
LOOPBACK = ("127.0.0.1", 50000)


def rigged(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flow: dict[str, Any]) -> Rig:
    made = make_rig(home, clock, tmp_path, monkeypatch, flow)
    monkeypatch.setattr(made.kernel.parts["remote"], "owner_login", lambda: LOGIN)
    monkeypatch.setattr(tailnet, "read", lambda: tailnet.Tailnet("desk.tail0.ts.net", LOGIN))
    return made


def paired(rig: Rig) -> TestClient:
    app = create_phone_app(rig.kernel.parts["remote"])
    client = TestClient(app, base_url=BASE, client=LOOPBACK)
    client.__enter__()
    code = rig.kernel.parts["remote"].pair("my phone", actor=OWNER)["code"]
    assert client.post("/api/pair", json={"code": code}, headers=ACT).status_code == 200
    return client


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = rigged(home, clock, tmp_path, monkeypatch, study())
    yield made
    made.kernel.close()


@pytest.fixture
def phone(rig: Rig) -> Iterator[TestClient]:
    client = paired(rig)
    yield client
    client.__exit__(None, None, None)


async def call(phone: TestClient, method: str, path: str, **asked: Any) -> httpx2.Response:
    """The phone's request, made off the test's event loop: the flows' runner runs on it."""
    headers = ACT if method == "POST" else THROUGH_TAILSCALE
    answer: httpx2.Response = await anyio.to_thread.run_sync(
        lambda: phone.request(method, path, headers=headers, **asked)
    )
    return answer


async def test_the_list_says_each_flows_state_and_the_question_it_waits_for(rig: Rig, phone: TestClient) -> None:
    async with running(rig.kernel):
        listed = (await call(phone, "GET", "/api/flows")).json()
        assert [(each["id"], each["state"], each["words"]) for each in listed["flows"]] == [
            (FLOW, "never", "not run yet")
        ]
        assert listed["plannings"] == {}
        started = await call(phone, "POST", f"/api/flows/{WORKSPACE}/study/run", json={})
        assert started.status_code == 200, started.text
        brief = await until(lambda: question(rig, "Brief"))
        [line] = (await call(phone, "GET", "/api/flows")).json()["flows"]
        assert (line["state"], line["words"]) == ("waits", "waits for you: your part · Brief")
        assert (line["question"], line["position"]) == (brief.id, {"done": 0, "of": 4})
    assert rig.run().started_by.kind == "device", "a run started from the phone is the device's"


async def test_a_flows_screen_is_the_flow_views_json_and_a_missing_flow_is_said(rig: Rig, phone: TestClient) -> None:
    shown = (await call(phone, "GET", f"/api/flows/{WORKSPACE}/study")).json()
    assert shown["flow"] == FLOW
    assert shown["run"] is None, "never run"
    assert [box["id"] for box in shown["boxes"]] == ["brief", "plan", "approve", "T1"]
    assert "version" in shown
    missing = await call(phone, "GET", f"/api/flows/{WORKSPACE}/nope")
    assert missing.status_code == 404
    assert "nope" in missing.json()["error"]


async def test_pause_and_stop_from_the_phone_are_recorded_as_the_devices(rig: Rig, phone: TestClient) -> None:
    async with running(rig.kernel):
        assert (await call(phone, "POST", f"/api/flows/{WORKSPACE}/study/run", json={})).status_code == 200
        await until(lambda: question(rig, "Brief"))
        paused = await call(phone, "POST", f"/api/flows/{WORKSPACE}/study/pause", json={})
        assert paused.status_code == 200, paused.text
        assert rig.run().paused is True
        [line] = (await call(phone, "GET", "/api/flows")).json()["flows"]
        assert line["state"] == "waits", "a paused run still waits for your part"
        stopped = await call(phone, "POST", f"/api/flows/{WORKSPACE}/study/stop", json={})
        assert stopped.status_code == 200, stopped.text
        await until(lambda: rig.run().status == "stopped")
    steered = rig.events("flows.run_steered")
    assert steered, "pausing is a steer"
    assert {event.actor.kind for event in steered} == {"device"}
    [line] = (await call(phone, "GET", "/api/flows")).json()["flows"]
    assert line["state"] == "stopped"
    refused = await call(phone, "POST", f"/api/flows/{WORKSPACE}/study/pause", json={})
    assert refused.status_code == 409, "nothing runs to pause"
    assert refused.json()["error"]


async def test_proposals_accepted_from_the_phone_join_the_flow(
    home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rig = rigged(home, clock, tmp_path, monkeypatch, decomposing())
    phone = paired(rig)
    try:
        async with running(rig.kernel):
            rig.runner.start(FLOW, actor=OWNER)
            brief = await until(lambda: question(rig, "Brief"))
            rig.write("BRIEF.md", "About 60 grid points, at most 48 CPU-hours.\n")
            rig.kernel.questions.answer(brief.id, by=OWNER, option="done")
            plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
            rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n\n1. The grid.\n2. The estimates.\n"})
            await at_work(rig, "split")
            rig.runner.proposing.propose(WORKSPACE, task(1), actor=AGENT)
            rig.runner.proposing.propose(WORKSPACE, task(2), actor=AGENT)
            shown = (await call(phone, "GET", f"/api/flows/{WORKSPACE}/study")).json()
            assert [each["id"] for each in shown["proposals"]["items"]] == ["T1", "T2"]
            assert [each["state"] for each in shown["proposals"]["items"]] == ["proposed", "proposed"]
            decided = await call(phone, "POST", f"/api/flows/{WORKSPACE}/study/proposals/accept", json={"all": True})
            assert decided.status_code == 200, decided.text
            wrong = await call(phone, "POST", f"/api/flows/{WORKSPACE}/study/proposals/keep", json={"all": True})
            assert wrong.status_code == 404
        record = rig.kernel.settings.get(Flow.KIND, FLOW).record
        assert isinstance(record, Flow)
        assert {"T1", "T2"} <= {box.id for box in record.boxes}, "accepted proposals join the flow's file"
        decided_events = rig.events("flows.proposal_decided")
        assert {event.actor.kind for event in decided_events} == {"device"}
    finally:
        phone.__exit__(None, None, None)
        rig.kernel.close()


async def test_a_planning_opened_from_the_phone_waits_for_clanks_vscode_window_and_is_listed_as_building(
    rig: Rig, phone: TestClient
) -> None:
    opened = await call(phone, "POST", "/api/flows/new", json={"workspace": WORKSPACE, "name": "survey"})
    assert opened.status_code == 200, opened.text
    assert (opened.json()["where"], opened.json()["window"]) == ("vscode", "waits")
    listed = (await call(phone, "GET", "/api/flows")).json()
    assert listed["plannings"][WORKSPACE]["planning"]["flow"] == f"{WORKSPACE}/survey"
    survey = [each for each in listed["flows"] if each["id"] == f"{WORKSPACE}/survey"]
    assert [(each["state"], each["words"], each["title"]) for each in survey] == [
        ("building", "building: waits for its OpenCode window", "survey")
    ]
    assert [each["id"] for each in listed["flows"]] == [f"{WORKSPACE}/survey", FLOW], (
        "what is built before what never ran"
    )
    shown = (await call(phone, "GET", f"/api/flows/{WORKSPACE}/survey")).json()
    assert shown["title"] == "survey", "the planning's view stands in for the flow's until its file is written"
    assert (shown["planning"]["status"], shown["planning"]["where"]) == ("waiting", "vscode")
    assert shown["planning"]["steps"][0]["kind"] == "started"
    assert shown["boxes"] == [], "no draft yet"
    refused = await call(phone, "POST", "/api/flows/new", json={"workspace": "nowhere", "name": "x"})
    assert refused.status_code == 409
    assert "nowhere" in refused.json()["error"]
