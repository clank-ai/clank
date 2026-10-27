"""Design 0010 §3: the agent reaches Notion through the gateway, which forwards to the service the reading and proposing
routes only (the shared databases, a query, a page, a search; a new entry, a change, a removal, submitting the batch)
as the client `agent`, each naming the workspace whose key it carries, and refuses every other (approving, rejecting,
connecting, the status, the batches); a refusal of the service comes back with its words, and a service that does not
answer is said so. End to end, a proposal made through the gateway is staged as the agent's session's, and the agent
cannot approve it."""

import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.client import Client
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import create_gateway, notion_forwarder
from clank.components.notion.service import Notion
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.notion import SECRET, FakeNotion
from tests.support.agentkeys import EDGE

FORWARDED = [
    ("GET", "/notion/databases", None, "databases", {}),
    ("POST", "/notion/query", {"database": "Papers"}, "query", {}),
    ("GET", "/notion/page/lit-1", None, "page/lit-1", {}),
    ("GET", "/notion/search?text=quantity", None, "search", {"text": "quantity"}),
    ("POST", "/notion/propose/entry", {"workspace": "paper"}, "propose/entry", {}),
    ("POST", "/notion/propose/change", {"workspace": "paper"}, "propose/change", {}),
    ("POST", "/notion/propose/removal", {"workspace": "paper"}, "propose/removal", {}),
    ("POST", "/notion/submit", {"workspace": "paper"}, "submit", {}),
    ("POST", "/notion/reply", {"workspace": "paper", "comment": "c1", "text": "Done."}, "reply", {}),
]
REFUSED = [
    ("POST", "/notion/batches/nb-1/approve"),
    ("POST", "/notion/batches/nb-1/reject"),
    ("POST", "/notion/batches/nb-1/comments"),
    ("POST", "/notion/batches/nb-1/return"),
    ("POST", "/notion/connect"),
    ("GET", "/notion/status"),
    ("GET", "/notion/batches"),
    ("GET", "/notion/../gateway/routes"),
]


AGENTS_KEY = "clank-ws-made-up-paper-key"  # the workspace's own key, which its agent's Clank server sends


def known() -> Routes:
    """Routes that name the workspace `paper`, kept on this machine (design 0016 §10: Notion answers only its key)."""
    found = Routes()
    bound = {"workspace": "paper", "models": "this-machine", "answered": False, "question": None}
    found.update({"slots": {}, "roles": {}, "workspaces": {hashlib.sha256(AGENTS_KEY.encode()).hexdigest(): bound}})
    return found


def gateway(forward: Any) -> TestClient:
    return TestClient(
        create_gateway(known(), GatewaySettings(), None, notion=forward),
        base_url=EDGE,
        headers={"Authorization": f"Bearer {AGENTS_KEY}"},
    )


def test_the_agents_reading_and_proposing_are_forwarded_and_nothing_else() -> None:
    asked: list[tuple[str, str, Any, dict[str, str]]] = []

    async def forward(method: str, path: str, body: Any, params: dict[str, str]) -> tuple[int, Any]:
        asked.append((method, path, body, params))
        return 200, {"forwarded": path}

    with gateway(forward) as http:
        for method, url, body, path, params in FORWARDED:
            answer = http.request(method, url, json=body)
            assert (answer.status_code, answer.json()) == (200, {"forwarded": path}), url
            if method == "GET":  # each names the workspace its key names: a GET in its query, a POST in its body
                assert asked[-1] == (method, path, None, {**params, "workspace": "paper"})
            else:
                assert asked[-1] == (method, path, {**(body or {}), "workspace": "paper"}, params)
        count = len(asked)
        for method, url in REFUSED:
            answer = http.request(method, url, json={})
            assert answer.status_code in (403, 404), url
            if answer.status_code == 403:
                assert "reads Notion and proposes changes; nothing else" in answer.json()["error"]["message"]
        assert len(asked) == count, "nothing refused was forwarded"


def test_a_refusal_comes_back_with_its_words_and_a_silent_service_is_said_so() -> None:
    async def refusing(method: str, path: str, body: Any, params: dict[str, str]) -> tuple[int, Any]:
        return 409, {"error": {"code": "refused", "message": "no shared database is named Nothing"}}

    with gateway(refusing) as http:
        answer = http.post("/notion/query", json={"database": "Nothing"})
        assert answer.status_code == 409
        assert answer.json()["error"]["message"] == "no shared database is named Nothing"
    with gateway(None) as http:
        answer = http.get("/notion/databases")
        assert answer.status_code == 503
        assert "Notion is reached through the Clank service" in answer.json()["error"]["message"]


@pytest.fixture
def kernel(home: Home) -> Iterator[Kernel]:
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 17, 18, 0, tzinfo=UTC)), registry.components())
    notion = FakeNotion()
    part: Notion = kernel.parts["notion"]
    part.transport = notion.transport
    part.sleep = notion.wait
    part.connect(SECRET, actor=Actor(kind="user", via="cli"))
    yield kernel
    kernel.close()


def test_a_proposal_through_the_gateway_is_the_agents_and_the_agent_cannot_approve_it(kernel: Kernel) -> None:
    with TestClient(create_app(kernel, token="t", port=7736), base_url="http://127.0.0.1:7736") as service:
        forward = notion_forwarder(
            lambda: Client("http://127.0.0.1:7736", "t", name="agent", http=service), close=False
        )
        with gateway(forward) as http:
            staged = http.post("/notion/propose/removal", json={"workspace": "paper", "page": "lit-2", "why": "a test"})
            assert staged.status_code == 200, staged.text
            assert http.post("/notion/submit", json={"workspace": "paper", "summary": "One."}).status_code == 200
            assert http.post(f"/notion/batches/{staged.json()['batch']}/approve", json={}).status_code == 403
        [event] = kernel.events.after(0, types=["notion.staged"])
        assert event.actor == Actor(kind="session", via="the agent")
        assert kernel.parts["notion"].batch(staged.json()["batch"])["state"] == "ready", "not approved"
