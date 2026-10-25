"""Design 0018 §7.1: the agent asks the service to open files in the owner's VS Code window through the gateway, which
forwards `POST /agents/show` to the service as the client `agent`, and refuses everything else under `/agents/`
(403), forwarding none of it: opening the window, the review, the sessions, the annotations, the mode. A refusal of
the service comes back with its words, and a service that does not answer is said so."""

from typing import Any

from fastapi.testclient import TestClient

from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import create_gateway

SHOW = {"workspace": "myproject", "paths": ["plots/residual.png"], "why": "asked for"}
REFUSED = [
    ("GET", "/agents/show"),
    ("POST", "/agents/vscode"),
    ("POST", "/agents/review"),
    ("POST", "/agents/mode"),
    ("POST", "/agents/implement"),
    ("POST", "/agents/annotations"),
    ("POST", "/agents/servers"),
    ("POST", "/agents/sessions/myproject/start"),
    ("POST", "/agents/show/../vscode"),
    ("GET", "/agents/changes"),
]


def gateway(forward: Any) -> TestClient:
    return TestClient(create_gateway(Routes(), GatewaySettings(), None, agents=forward))


def test_showing_files_is_forwarded_and_nothing_else_under_agents() -> None:
    asked: list[tuple[str, str, Any, dict[str, str]]] = []

    async def forward(method: str, path: str, body: Any, params: dict[str, str]) -> tuple[int, Any]:
        asked.append((method, path, body, params))
        return 200, {"forwarded": path}

    with gateway(forward) as http:
        answer = http.post("/agents/show", json=SHOW)
        assert (answer.status_code, answer.json()) == (200, {"forwarded": "show"})
        assert asked == [("POST", "show", SHOW, {})]
        for method, url in REFUSED:
            answer = http.request(method, url, json={})
            assert answer.status_code in (403, 404), url
            if answer.status_code == 403:
                assert "the agent opens files for the owner to see; nothing else" in answer.json()["error"]["message"]
        assert len(asked) == 1, "nothing refused was forwarded"


def test_a_refusal_comes_back_with_its_words_and_a_silent_service_is_said_so() -> None:
    async def refusing(method: str, path: str, body: Any, params: dict[str, str]) -> tuple[int, Any]:
        return 409, {"error": {"code": "refused", "message": "no VS Code window follows Clank now"}}

    with gateway(refusing) as http:
        answer = http.post("/agents/show", json=SHOW)
        assert answer.status_code == 409
        assert answer.json()["error"]["message"] == "no VS Code window follows Clank now"
    with gateway(None) as http:
        answer = http.post("/agents/show", json=SHOW)
        assert answer.status_code == 503
        assert "Showing files is reached through the Clank service" in answer.json()["error"]["message"]
