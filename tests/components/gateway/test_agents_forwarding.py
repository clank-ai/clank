"""Design 0018 §7.1: the agent asks the service to open files in the owner's VS Code window through the gateway, which
forwards `POST /agents/show` to the service as the client `agent`, and refuses everything else under `/agents/`
(403), forwarding none of it: opening the window, the review, the sessions, the annotations, the mode. A refusal of
the service comes back with its words, and a service that does not answer is said so.

Design 0021 §6: the agent's jobs are forwarded the same way: starting one, its status, stopping it; listing every
workspace's jobs is the owner's. Design 0021 §5: so is making an artifact; commenting on one is the owner's."""

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
    ("GET", "/agents/jobs"),
    ("POST", "/agents/jobs/1/stop"),
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
                assert (
                    "the agent opens files for the owner to see, runs its jobs, makes its artifacts and works on boards"
                    in answer.json()["error"]["message"]
                )
        assert len(asked) == 1, "nothing refused was forwarded"
        job = {"workspace": "myproject", "command": "python sweep.py", "title": "sweep", "minutes": 60}
        for path, body in (("jobs", job), ("jobs/status", {"workspace": "myproject", "job": 1}),
                           ("jobs/stop", {"workspace": "myproject", "job": 1})):  # fmt: skip
            answer = http.post(f"/agents/{path}", json=body)
            assert (answer.status_code, answer.json()) == (200, {"forwarded": path})
        assert [each[1] for each in asked[1:]] == ["jobs", "jobs/status", "jobs/stop"]
        made = http.post("/agents/artifacts", json={"workspace": "myproject", "name": "sweep", "files": ["a.html"]})
        assert (made.status_code, made.json()) == (200, {"forwarded": "artifacts"})
        commented = http.post("/agents/artifacts/myproject/sweep/comment", json={"version": 1, "text": "hi"})
        assert commented.status_code == 403, "commenting is the owner's"


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
        assert "Showing files and jobs are reached through the Clank service" in answer.json()["error"]["message"]


def test_the_agents_work_on_boards_is_forwarded() -> None:
    """Design 0022 §4: making a board, listing the folder's, reading one, and adding, changing and taking away items."""
    asked: list[tuple[str, str, Any, dict[str, str]]] = []

    async def forward(method: str, path: str, body: Any, params: dict[str, str]) -> tuple[int, Any]:
        asked.append((method, path, body, params))
        return 200, {"forwarded": path}

    calls = [("POST", "boards"), ("GET", "boards"), ("GET", "boards/read"), ("POST", "boards/add"),
             ("POST", "boards/update"), ("POST", "boards/remove")]  # fmt: skip
    with gateway(forward) as http:
        for method, path in calls:
            if method == "GET":
                answer = http.get(f"/agents/{path}", params={"workspace": "myproject", "board": "fig3"})
            else:
                answer = http.post(f"/agents/{path}", json={"workspace": "myproject", "board": "fig3"})
            assert (answer.status_code, answer.json()) == (200, {"forwarded": path}), path
    assert [(each[0], each[1]) for each in asked] == calls
    assert asked[2][3] == {"workspace": "myproject", "board": "fig3"}, "a read's query is forwarded with it"
