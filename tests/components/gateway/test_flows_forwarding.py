"""Design 0013 §9, §15 and §16 (decisions 0020, 0064, 0097 and 0123): a box's model reaches its flow through the
gateway, which forwards to the service only what the agent may ask (reading its flow, `GET /flows/read`; proposing a box
and submitting its proposals, `POST /flows/propose` and `/flows/submit`; a VERIFY's verdict, `POST /flows/verdict`; a
planning's draft of a whole flow, `POST /flows/draft`, design 0013 §15; an orchestrator's decision, `POST
/flows/decide`, §16; a box's job, `POST /flows/job`, §17), each with its workspace's key, as the client `agent`, and
refuses everything else under
`/flows/` (403), forwarding none of it: running, pausing or stopping a flow, its runs, checking it, changing it,
deciding proposals, and opening a planning. A refusal of the service comes back with its words, and a service that does
not answer is said so. End to end, a verdict given through the gateway is kept as the agent's session's, a criterion not
as `flow_verdict` takes it is refused naming its field, and a flow cannot be run, paused or stopped through the
gateway."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.client import Client
from clank.components.flows.verdicts import AGENT
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.server import create_gateway, flows_forwarder
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import Rig, checked_study, is_sent, make_rig, question
from tests.support.agentkeys import EDGE, agent_headers, keyed

FORWARDED = [
    ("POST", "/flows/verdict", {"workspace": "myproject", "result": "pass", "findings": []}, "verdict"),
    ("POST", "/flows/propose", {"workspace": "myproject", "after": "split", "type": "task"}, "propose"),
    ("POST", "/flows/submit", {"workspace": "myproject", "summary": "Four tasks."}, "submit"),
    ("POST", "/flows/draft", {"workspace": "myproject", "flow": {"title": "A study"}}, "draft"),
    ("POST", "/flows/decide", {"workspace": "myproject", "choice": "go on", "why": "PLAN.md passed"}, "decide"),
    ("POST", "/flows/job", {"workspace": "myproject", "command": "python3 anneal.py", "minutes": 30}, "job"),
]
REFUSED = [
    ("GET", "/flows/"),
    ("GET", "/flows/myproject/study"),
    ("GET", "/flows/myproject/study/runs"),
    ("POST", "/flows/myproject/study/run"),
    ("POST", "/flows/myproject/study/pause"),
    ("POST", "/flows/myproject/study/stop"),
    ("POST", "/flows/check"),
    ("GET", "/flows/verdict"),
    ("PUT", "/flows/myproject/study"),
    ("DELETE", "/flows/myproject/study"),
    ("POST", "/flows/verdict/../myproject/study/run"),
    ("GET", "/flows/myproject/study/proposals"),
    ("POST", "/flows/myproject/study/proposals/accept"),
    ("POST", "/flows/myproject/study/proposals/reject"),
    ("POST", "/flows/myproject/study/proposals/edit"),
    ("POST", "/flows/read"),
    ("GET", "/flows/propose"),
    ("GET", "/flows/draft"),
    ("POST", "/flows/new"),
    ("GET", "/flows/building"),
    ("GET", "/flows/job"),
]
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "cli"}


def gateway(forward: Any) -> TestClient:
    """The gateway as myproject's container reaches it, with its workspace's key."""
    app = create_gateway(keyed("myproject"), GatewaySettings(), None, flows=forward)
    return TestClient(app, base_url=EDGE, headers=agent_headers("myproject"))


def test_the_agents_verdict_is_forwarded_and_nothing_else_under_flows() -> None:
    asked: list[tuple[str, str, Any, dict[str, str]]] = []

    async def forward(method: str, path: str, body: Any, params: dict[str, str]) -> tuple[int, Any]:
        asked.append((method, path, body, params))
        return 200, {"forwarded": path}

    with gateway(forward) as http:
        for method, url, body, path in FORWARDED:
            answer = http.request(method, url, json=body)
            assert (answer.status_code, answer.json()) == (200, {"forwarded": path}), url
            assert asked[-1] == (method, path, body, {})
        count = len(asked)
        for method, url in REFUSED:
            answer = http.request(method, url, json={})
            assert answer.status_code in (403, 404), url
            if answer.status_code == 403:
                said = answer.json()["error"]["message"]
                assert (
                    "reads its flow, proposes boxes, gives a VERIFY's verdict, drafts a flow, gives an "
                    "orchestrator's decision and starts a box's job; nothing else" in said
                )
        assert http.post("/flows/myproject/study/run", json={}).status_code == 403
        assert len(asked) == count, "nothing refused was forwarded"
        read = http.get("/flows/read", params={"workspace": "myproject"})
        assert (read.status_code, read.json()) == (200, {"forwarded": "read"})
        assert asked[-1] == ("GET", "read", None, {"workspace": "myproject"}), "its query passed on"


def test_a_refusal_comes_back_with_its_words_and_a_silent_service_is_said_so() -> None:
    async def refusing(method: str, path: str, body: Any, params: dict[str, str]) -> tuple[int, Any]:
        return 409, {"error": {"code": "refused", "message": "no box of a flow works in myproject now"}}

    with gateway(refusing) as http:
        answer = http.post("/flows/verdict", json={"workspace": "myproject", "result": "pass"})
        assert answer.status_code == 409
        assert answer.json()["error"]["message"] == "no box of a flow works in myproject now"
    with gateway(None) as http:
        answer = http.post("/flows/verdict", json={"workspace": "myproject", "result": "pass"})
        assert answer.status_code == 503
        assert "Flows are reached through the Clank service" in answer.json()["error"]["message"]


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, checked_study())
    yield made
    made.kernel.close()


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


def test_a_verdict_through_the_gateway_is_the_agents_and_the_agent_cannot_run_pause_or_stop_a_flow(rig: Rig) -> None:
    app = create_app(rig.kernel, token="t", port=7720, background=[rig.kernel.parts["flows"].run])
    with TestClient(app, base_url="http://127.0.0.1:7720") as service:
        forward = flows_forwarder(lambda: Client("http://127.0.0.1:7720", "t", name="agent", http=service), close=False)
        with gateway(forward) as http:
            assert service.post("/api/v1/flows/myproject/study/run", headers=AUTH, json={}).status_code == 200
            brief = waits_for(lambda: question(rig, "Brief"))
            rig.write("BRIEF.md", "About 60 grid points.\n")
            answered = service.post(f"/api/v1/questions/{brief.id}/answer", headers=AUTH, json={"option": "done"})
            assert answered.status_code == 200, answered.text
            plan = waits_for(lambda: rig.bridge.prompted("Study · plan · try 1"))

            early = http.post("/flows/verdict", json={"workspace": "myproject", "result": "pass"})
            assert early.status_code == 409, "plan is no VERIFY"
            assert "only a VERIFY gives a verdict" in early.json()["error"]["message"]

            rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
            check = waits_for(lambda: rig.bridge.prompted("Study · check · try 1"))
            waits_for(lambda: is_sent(rig, "check"))
            body = {
                "workspace": "myproject", "result": "fail", "findings": ["Seeds not fixed."],
                "criteria": [{"line": "about 60 grid points", "met": True, "evidence": "64 in PLAN.md"}],
            }  # fmt: skip
            wrong = {**body, "criteria": [{"line": "about 60 grid points", "met": True, "file": "PLAN.md"}]}
            refused = http.post("/flows/verdict", json=wrong)
            assert refused.status_code == 409, refused.text
            said = refused.json()["error"]["message"]
            assert said.startswith("criterion 1 has file, which a criterion does not take"), "it names what to fix"
            given = http.post("/flows/verdict", json=body)
            assert given.status_code == 200, given.text
            assert given.json()["said"].startswith("Your verdict on plan's try 1 is kept: fail, with 1 finding.")
            for action in ("run", "pause", "stop"):
                assert http.post(f"/flows/myproject/study/{action}", json={}).status_code == 403
            rig.bridge.finish(check.session)
            waits_for(lambda: rig.bridge.prompted("Study · plan · try 2"))

    [event] = rig.events("flows.verdict")
    assert event.actor == AGENT
    verdict = rig.run().box("check").tries[0].verdict
    assert verdict is not None
    assert (verdict.result, verdict.findings) == ("fail", ["Seeds not fixed."])
    assert verdict.criteria[0].evidence == "64 in PLAN.md"
    assert [event.data.get("action") for event in rig.events("flows.run_steered")] == [], "the agent steered nothing"
