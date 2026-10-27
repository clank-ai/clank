"""Design 0016 §9, design 0010 §3, design 0013 §9 and design 0018 §7.1: an agent's call through the gateway (to Notion,
to its flow, to the agents' part) acts for the workspace its key names, and for no other. A call without a key the
gateway's routes know (none, `local`, a key no workspace has) is refused (401), saying to start the agent's window
again; one whose key names a workspace and whose body or query names another is refused (403); with its workspace's
key it passes, the workspace filled in where the call left it out; a body that is not a JSON object is refused (400).
Nothing refused is forwarded."""

import hashlib
from typing import Any

from fastapi.testclient import TestClient

from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import create_gateway

PAPER = "clank-ws-made-up-paper-key"  # the key Clank's MCP server in paper's container sends
LAB = "clank-ws-made-up-lab-key"
EDGE = f"http://edge:{GatewaySettings().port}"  # where a workspace's container reaches the gateway
Asked = list[tuple[str, str, Any, dict[str, str]]]
POSTS = [
    ("/agents/jobs", {"workspace": "paper", "command": "python3 sweep.py", "title": "sweep", "minutes": 60}),
    ("/agents/show", {"workspace": "paper", "paths": ["plots/residual.png"], "why": "asked for"}),
    ("/agents/boards/add", {"workspace": "paper", "board": "fig3", "kind": "note"}),
    ("/flows/verdict", {"workspace": "paper", "result": "pass", "findings": []}),
    ("/flows/job", {"workspace": "paper", "command": "python3 anneal.py", "minutes": 30}),
    ("/notion/propose/removal", {"workspace": "paper", "page": "lit-2", "why": "a test"}),
    ("/notion/reply", {"workspace": "paper", "comment": "c1", "text": "Done."}),
]
GETS = [("/agents/boards/read", {"board": "fig3"}), ("/flows/read", {"flow": "study"}), ("/notion/databases", {}),
        ("/notion/search", {"text": "quantity"})]  # fmt: skip


def bound(workspace: str) -> dict[str, Any]:
    return {"workspace": workspace, "models": "this-machine", "answered": False, "question": None}


def gateway(asked: Asked) -> TestClient:
    """The gateway, reached through the edge, its routes naming the workspaces paper and lab by their keys; each call
    it forwards is kept in `asked`."""

    async def forward(method: str, path: str, body: Any, params: dict[str, str]) -> tuple[int, Any]:
        asked.append((method, path, body, params))
        return 200, {"forwarded": path}

    keys = {hashlib.sha256(key.encode()).hexdigest(): bound(name) for key, name in ((PAPER, "paper"), (LAB, "lab"))}
    routes = Routes()
    routes.update({"slots": {}, "roles": {}, "workspaces": keys})
    app = create_gateway(routes, GatewaySettings(), None, notion=forward, flows=forward, agents=forward)
    return TestClient(app, base_url=EDGE)


def key(value: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {value}"}


def test_a_call_without_a_known_key_is_refused_saying_to_start_the_agents_window_again() -> None:
    asked: Asked = []
    unknown = [{}, key("local"), key("clank-ws-no-workspace-has-it"), key(""), {"Authorization": PAPER}]
    with gateway(asked) as http:
        for headers in unknown:
            for path, body in POSTS:
                answer = http.post(path, json=body, headers=headers)
                assert answer.status_code == 401, (headers, path)
                error = answer.json()["error"]
                assert error["code"] == "unauthorized"
                assert "close the agent's window and start it again from Clank" in error["message"]
            for path, query in GETS:
                answer = http.get(path, params={**query, "workspace": "paper"}, headers=headers)
                assert answer.status_code == 401, (headers, path)
    assert asked == [], "nothing refused was forwarded"


def test_a_key_of_one_workspace_naming_another_is_refused() -> None:
    asked: Asked = []
    with gateway(asked) as http:
        for path, body in POSTS:
            answer = http.post(path, json=body, headers=key(LAB))
            assert answer.status_code == 403, path
            error = answer.json()["error"]
            assert error["code"] == "wrong_workspace"
            assert error["message"] == (
                "this agent works for lab, and this request names paper: an agent acts for its own workspace only"
            )
        for path, query in GETS:
            answer = http.get(path, params={**query, "workspace": "paper"}, headers=key(LAB))
            assert (answer.status_code, answer.json()["error"]["code"]) == (403, "wrong_workspace"), path
        twice = http.get("/flows/read?workspace=lab&workspace=paper", headers=key(LAB))
        assert twice.status_code == 403, "each workspace a query names must be its own"
        queried = http.post("/agents/jobs?workspace=paper", json={"command": "true"}, headers=key(LAB))
        assert queried.status_code == 403, "a POST's query too"
        listed = http.post("/agents/show", json={"workspace": ["paper"], "paths": ["a.png"]}, headers=key(LAB))
        assert listed.status_code == 403, "a workspace that is not a name"
    assert asked == [], "nothing refused was forwarded"


def test_with_its_workspaces_key_a_call_passes_with_its_workspace_bound() -> None:
    asked: Asked = []
    with gateway(asked) as http:
        for path, body in POSTS:
            answer = http.post(path, json=body, headers=key(PAPER))
            forwarded = path.split("/", 2)[2]
            assert (answer.status_code, answer.json()) == (200, {"forwarded": forwarded}), path
            assert asked[-1] == ("POST", forwarded, body, {}), "forwarded as it came"
        for path, query in GETS:
            answer = http.get(path, params={**query, "workspace": "paper"}, headers=key(PAPER))
            assert answer.status_code == 200, path
            assert asked[-1] == ("GET", path.split("/", 2)[2], None, {**query, "workspace": "paper"})
        left_out = [({"command": "python3 sweep.py"}, {"command": "python3 sweep.py", "workspace": "paper"}),
                    ({"workspace": "", "summary": "Two."}, {"workspace": "paper", "summary": "Two."}),
                    ({"workspace": None, "summary": "Two."}, {"workspace": "paper", "summary": "Two."})]  # fmt: skip
        for sent, filled in left_out:
            assert http.post("/flows/submit", json=sent, headers=key(PAPER)).status_code == 200
            assert asked[-1][2] == filled, "the workspace its key names, filled in"
        assert http.post("/notion/submit", headers=key(PAPER)).status_code == 200
        assert asked[-1][2] == {"workspace": "paper"}, "a call with no body names its workspace too"
        for path, query in GETS:
            assert http.get(path, params=query, headers=key(PAPER)).status_code == 200, path
            assert asked[-1][3] == {**query, "workspace": "paper"}, path
        lab = http.post("/agents/show", json={"workspace": "lab", "paths": ["b.png"]}, headers=key(LAB))
        assert lab.status_code == 200
        assert asked[-1][2]["workspace"] == "lab", "each key its own workspace"


def test_a_body_that_is_not_a_json_object_is_refused() -> None:
    asked: Asked = []
    with gateway(asked) as http:
        for content in (b"[1, 2]", b'"paper"', b"not json", b"{"):
            headers = {**key(PAPER), "Content-Type": "application/json"}
            answer = http.post("/agents/show", content=content, headers=headers)
            assert (answer.status_code, answer.json()["error"]["code"]) == (400, "invalid_request"), content
    assert asked == [], "nothing refused was forwarded"
