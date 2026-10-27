"""Design 0016 §9 and §10 (decisions 0075, 0103, 0112): the gateway checks each cloud request's workspace, by the key
its OpenCode sends (its SHA-256 in the routes), before anything is sent. A request with no known key goes to this
machine only, and to the cloud is refused saying to start OpenCode again; a workspace allowed the cloud goes; one not
yet answered is held, its stream kept alive with comment lines while the service asks the question, and goes on on the
same stream once allowed; one kept local is refused with words that say how to allow it. Notion answers only a known key
whose bound is this machine, and never a request that names none, even while no workspace may use the cloud (a
container started before workspaces had keys is told to start its agent's window again). The activity routes take the
service's local token. While the service does not
answer, a cloud request waits for fresh routes, then is refused `service_silent`. Through the service, a request held
asks the workspace's question once."""

import hashlib
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient

from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import create_gateway
from clank.components.gateway.service import Gateway
from clank.kernel.access import local_token
from clank.kernel.api import create_app
from clank.kernel.events import Actor
from tests.components.gateway.test_cloud_forwarding import ASKS, SESSION, cloud_slot, forwarding, lines
from tests.components.gateway.test_server import engine, table  # noqa: F401  (a fixture, found by its name)
from tests.components.runtime.conftest import Rig
from tests.fakes.openrouter import FakeOpenRouter
from tests.support.agentkeys import EDGE, HERE

NOTES = "clank-ws-made-up-notes-key"
LAB = "clank-ws-made-up-lab-key"
TOKEN = "local-token-of-the-test"
YOU = Actor(kind="user", via="console")


def hashed(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def bounds(notes: dict[str, Any], lab: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        hashed(NOTES): {"workspace": "notes", "models": "this-machine", "answered": False, "question": None, **notes},
        hashed(LAB): {"workspace": "lab", "models": "cloud", "answered": True, "question": None, **(lab or {})},
    }


def routed(slot: dict[str, Any], notes: dict[str, Any]) -> dict[str, Any]:
    return {"slots": {"main": slot}, "roles": {"agent": "main"}, "default_slot": "main", "workspaces": bounds(notes)}


def sent(url: str, key: str, body: dict[str, Any] | None = None) -> httpx2.Response:
    headers = {"Authorization": f"Bearer {key}", "X-Session-Id": SESSION}
    return httpx2.post(f"{url}/v1/chat/completions", json=body or ASKS, headers=headers, timeout=30)


@pytest.fixture
def held(openrouter: FakeOpenRouter, tmp_path: Path) -> Iterator[tuple[Routes, str, list[tuple[str, str]]]]:
    """A gateway whose routes say notes is not answered; what it asked of the service."""
    asked: list[tuple[str, str]] = []

    async def ask(workspace: str, session: str) -> dict[str, Any]:
        asked.append((workspace, session))
        return {"question": "q-1a2b"}

    with forwarding(cloud_slot(openrouter.url), tmp_path, ask_cloud=ask) as (url, routes):
        routes.update(routed(cloud_slot(openrouter.url), {}))
        yield routes, url, asked


def test_a_workspace_allowed_the_cloud_goes(held: tuple[Routes, str, list[Any]], openrouter: FakeOpenRouter) -> None:
    _, url, asked = held
    answer = sent(url, LAB)
    assert answer.status_code == 200
    assert lines(answer) == openrouter.exchange("stream")["response"]["stream"]
    assert asked == []


def test_a_request_with_no_known_key_is_refused_for_the_cloud(
    held: tuple[Routes, str, list[Any]], openrouter: FakeOpenRouter
) -> None:
    _, url, _ = held
    answer = sent(url, "local")
    assert answer.status_code == 403
    error = answer.json()["error"]
    assert error["code"] == "model_send_denied"
    assert "started before Clank named workspaces to the gateway: leave it, and start it again here" in error["message"]
    assert openrouter.chats() == []


def test_a_request_with_no_known_key_is_served_by_an_engine(engine: tuple[int, Path], tmp_path: Path) -> None:  # noqa: F811
    with forwarding(table(engine[0])["slots"]["main"], tmp_path) as (url, _):
        assert sent(url, "local", {**ASKS, "stream": False, "max_tokens": 3}).status_code == 200


def test_an_unanswered_workspaces_stream_is_held_then_goes_on_once_allowed(
    held: tuple[Routes, str, list[Any]], openrouter: FakeOpenRouter
) -> None:
    routes, url, asked = held
    with httpx2.stream("POST", f"{url}/v1/chat/completions", json=ASKS, timeout=30,
                       headers={"Authorization": f"Bearer {NOTES}", "X-Session-Id": SESSION}) as answer:  # fmt: skip
        assert answer.status_code == 200
        got: list[str] = []
        for line in answer.iter_lines():
            got.append(line)
            if line.startswith(": held by Clank") and len(got) == 1:
                routes.update(routed(cloud_slot(openrouter.url), {"question": "q-1a2b"}))
                time.sleep(0.3)
                routes.update(routed(cloud_slot(openrouter.url), {"models": "cloud", "answered": True}))
    assert got[0] == ": held by Clank: waiting for your answer: may notes use the cloud model?"
    assert [line for line in got if line.startswith("data:")] == openrouter.exchange("stream")["response"]["stream"]
    assert asked == [("notes", SESSION)]
    assert len(openrouter.chats()) == 1


def test_a_workspace_kept_local_is_refused_with_words_that_say_how_to_allow_it(
    held: tuple[Routes, str, list[Any]], openrouter: FakeOpenRouter
) -> None:
    routes, url, asked = held
    routes.update(routed(cloud_slot(openrouter.url), {"answered": True}))
    answer = sent(url, NOTES, {**ASKS, "stream": False})
    assert answer.status_code == 403
    error = answer.json()["error"]
    assert error["code"] == "model_send_denied"
    assert error["message"].startswith("notes is kept on this machine. Allow the cloud for it on This folder (u)")
    assert "clank workspace allow FOLDER --cloud" in error["message"]
    assert (asked, openrouter.chats()) == ([], [])


def test_a_withdrawn_agreement_stops_the_next_cloud_request(
    held: tuple[Routes, str, list[Any]], openrouter: FakeOpenRouter
) -> None:
    routes, url, _ = held
    routes.update({**routed({**cloud_slot(openrouter.url), "agreed": False}, {})})
    answer = sent(url, LAB, {**ASKS, "stream": False})
    assert (answer.status_code, answer.json()["error"]["code"]) == (403, "model_send_denied")
    assert "agreement" in answer.json()["error"]["message"]
    assert openrouter.chats() == []


def test_notion_answers_only_a_known_key_kept_on_this_machine() -> None:
    forwarded: list[str] = []

    async def forward(method: str, path: str, body: Any, params: dict[str, str]) -> tuple[int, Any]:
        forwarded.append(path)
        return 200, {"forwarded": path}

    routes = Routes()
    routes.update({"slots": {}, "roles": {}, "workspaces": bounds({})})
    with TestClient(create_gateway(routes, GatewaySettings(), None, notion=forward), base_url=EDGE) as http:
        mine = http.get("/notion/databases", headers={"Authorization": f"Bearer {NOTES}"})
        assert (mine.status_code, mine.json()) == (200, {"forwarded": "databases"})
        cloud = http.get("/notion/databases", headers={"Authorization": f"Bearer {LAB}"})
        assert (cloud.status_code, cloud.json()["error"]["code"]) == (403, "notion_denied"), "lab may use the cloud"
        unknown = http.get("/notion/databases", headers={"Authorization": "Bearer local"})
        assert (unknown.status_code, unknown.json()["error"]["code"]) == (401, "unauthorized")
    assert forwarded == ["databases"]


def test_even_while_no_workspace_may_use_the_cloud_notion_refuses_a_request_that_names_none() -> None:
    async def forward(method: str, path: str, body: Any, params: dict[str, str]) -> tuple[int, Any]:
        return 200, {"forwarded": path}

    routes = Routes()
    routes.update({"slots": {}, "roles": {}, "workspaces": bounds({}, {"models": "this-machine"})})
    with TestClient(create_gateway(routes, GatewaySettings(), None, notion=forward), base_url=EDGE) as http:
        for headers in ({}, {"Authorization": "Bearer local"}):  # Clank's server in a container started before keys
            answer = http.get("/notion/databases", headers=headers)
            assert (answer.status_code, answer.json()["error"]["code"]) == (401, "unauthorized"), headers
            assert "start it again from Clank" in answer.json()["error"]["message"]


def test_the_activity_routes_take_the_services_local_token() -> None:
    with TestClient(create_gateway(Routes(), GatewaySettings(), None, token=TOKEN), base_url=HERE) as http:
        for path in ("/activity", "/activity/live", "/completion"):
            assert http.get(path).status_code == 401, path
            assert http.get(path, headers={"Authorization": f"Bearer {TOKEN}"}).status_code == 200, path


def test_with_the_service_silent_a_cloud_request_waits_then_is_refused_service_silent(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    with forwarding(cloud_slot(openrouter.url), tmp_path, hold_seconds=1) as (url, routes):
        routes.update(routed(cloud_slot(openrouter.url), {}))
        routes.followed = True
        routes.updated = time.monotonic() - 10
        began = time.monotonic()
        answer = sent(url, LAB, {**ASKS, "stream": False})
    assert (answer.status_code, answer.json()["error"]["code"]) == (503, "service_silent")
    assert time.monotonic() - began >= 1
    assert openrouter.chats() == []


@pytest.mark.anyio
async def test_a_held_request_asks_the_workspaces_question_through_the_service(
    rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "notes"
    folder.mkdir()
    rig.kernel.settings.write("workspace", "notes", {"path": str(folder)}, base=None, actor=YOU)
    gateway: Gateway = rig.kernel.parts["gateway"]
    real = gateway.routes
    main = {"status": "ready", "provider": "endpoint", "endpoint": "openrouter", "title": "cloud: Example Coder"}
    monkeypatch.setattr(gateway, "routes", lambda: {**real(), "slots": {"main": main}})
    with TestClient(create_app(rig.kernel, token="t", port=7725), base_url="http://127.0.0.1:7725") as http:
        auth = {"Authorization": "Bearer t", "X-Clank-Client": "gateway"}
        first = http.post("/api/v1/gateway/cloud-wanted", json={"workspace": "notes", "session": SESSION}, headers=auth)
        again = http.post("/api/v1/gateway/cloud-wanted", json={"workspace": "notes", "session": SESSION}, headers=auth)
    assert first.status_code == 200, first.text
    question = first.json()["question"]
    assert question is not None
    assert again.json() == {"question": question}
    [wanted, *_] = rig.kernel.events.latest(types=["gateway.cloud_wanted"])
    assert wanted.data == {"workspace": "notes", "session": SESSION}
    assert [each.id for each in rig.kernel.questions.waiting()] == [question]


def test_the_service_asks_the_gateways_activity_with_its_token(
    rig: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.components.gateway.test_cloud_keys import gateway_served

    gateway: Gateway = rig.kernel.parts["gateway"]
    with gateway_served(Routes(), tmp_path, token=local_token(rig.kernel.home)) as url:
        port = int(url.rsplit(":", 1)[1])
        monkeypatch.setattr(gateway, "status", lambda: {"state": "running", "port": port, "problem": ""})
        assert gateway.activity()["problem"] == ""
        assert gateway.live()["problem"] == ""
        assert gateway.completion()["problem"] == ""
