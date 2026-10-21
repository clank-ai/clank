"""Design 0013 §9 and §15: Clank's own MCP server in the container gives a box's model its flow's tools, each a request
to the gateway's `/flows/` routes naming the workspace the server serves: `flow_verdict`, a VERIFY's verdict (its
result, its findings and `criteria`, each line of the brief and of what done means that the check touched, met or not,
with its evidence); `flow_read`, the flow as the service tells it, marked read-only; `flow_propose_box`, a box proposed
after a box of the flow, its arguments sent as the model gave them; `flow_submit`, the proposals ready for the owner;
and `flow_draft` (design 0013 §15), a whole flow drafted in a planning session, sent as the model gave it. Each answer
is what the service said; a refusal is the tool's error, in the service's words; a server that does not know its
workspace asks nothing. None writes anything in the folder."""

import json
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from clank.components.workspaces.sandbox import image_folder
from clank.kernel.processes import background_flags
from tests.support.served import free_port

SERVER = image_folder() / "phone_mcp.py"
CRITERION = {"line": "at most 48 CPU-hours", "met": False, "evidence": "PLAN.md's estimate: 61 CPU-hours"}


class Gateway(BaseHTTPRequestHandler):
    """The gateway's /flows/ routes as the service answers them, and what was asked."""

    asked: ClassVar[list[tuple[str, str, Any]]] = []

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        Gateway.asked.append(("POST", self.path, body))
        if body.get("result") == "fail" and not body.get("findings"):
            message = "a fail lists its findings, each one thing to fix: give your verdict again with them"
            self._json({"error": {"code": "refused", "message": message}}, 409)
        elif self.path == "/flows/propose" and body.get("type") == "subtask":
            message = "type is one of you, plan, verify, decompose, task, integrate, gate, not 'subtask'"
            self._json({"error": {"code": "refused", "message": message}}, 409)
        elif self.path == "/flows/propose":
            self._json({"proposal": "T1", "said": "Proposed T1 (The grid) after split: it waits for the user."})
        elif self.path == "/flows/draft" and not (body.get("flow") or {}).get("boxes"):
            message = "Not written. Fix each, then call flow_draft again:\n- boxes: field required"
            self._json({"error": {"code": "refused", "message": message}}, 409)
        elif self.path == "/flows/draft":
            self._json({"flow": "myproject/flow", "said": "Written as myproject/flow."})
        elif self.path == "/flows/submit":
            self._json({"waiting": ["T1"], "said": "Submitted 1 proposal (T1): it waits for the user."})
        else:
            self._json({"result": body.get("result"), "said": "Your verdict on plan's try 1 is kept: pass."})

    def do_GET(self) -> None:
        Gateway.asked.append(("GET", self.path, None))
        self._json({"flow": "myproject/study", "you_are": "split", "boxes": [], "said": "This is read-only."})

    def log_message(self, format: str, *args: Any) -> None:
        """Quiet."""

    def _json(self, value: Any, status: int = 200) -> None:
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def gateway() -> Iterator[str]:
    Gateway.asked = []
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Gateway)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/v1"
    server.shutdown()
    server.server_close()


def session(folder: Path, gateway: str, messages: list[dict[str, Any]], workspace: str = "myproject") -> list[Any]:
    """Messages sent to the server through its standard input; its replies."""
    opening = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
    env = {"CLANK_WORKSPACE": str(folder), "CLANK_GATEWAY": gateway, "SYSTEMROOT": "C:\\Windows", "PATH": ""}
    if workspace:
        env["CLANK_WORKSPACE_NAME"] = workspace
    done = subprocess.run(
        [sys.executable, str(SERVER)], input="".join(json.dumps(each) + "\n" for each in [opening, *messages]),
        capture_output=True, text=True, timeout=120, creationflags=background_flags(), env=env,
    )  # fmt: skip
    return [json.loads(line) for line in done.stdout.splitlines()][1:]


def called(name: str, arguments: dict[str, Any], id: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


def test_flow_verdict_is_listed_with_its_result_findings_and_criteria(tmp_path: Path, gateway: str) -> None:
    [listed] = session(tmp_path, gateway, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    verdict = tools["flow_verdict"]
    assert verdict["annotations"]["readOnlyHint"] is False, "it changes Clank's state, though no file"
    assert verdict["inputSchema"]["required"] == ["result", "findings"]
    assert verdict["inputSchema"]["properties"]["result"]["enum"] == ["pass", "fail"]
    criterion = verdict["inputSchema"]["properties"]["criteria"]["items"]
    assert criterion["required"] == ["line", "met"]
    assert set(criterion["properties"]) == {"line", "met", "evidence"}
    assert "Returns" in verdict["description"]


def test_flow_verdict_asks_the_gateways_flows_route_naming_its_workspace_and_answers_what_the_service_said(
    tmp_path: Path, gateway: str
) -> None:
    [reply] = session(tmp_path, gateway, [called("flow_verdict", {"result": "pass", "findings": [],
                                                                  "criteria": [CRITERION]})])  # fmt: skip
    body = {"workspace": "myproject", "result": "pass", "findings": [], "criteria": [CRITERION]}
    assert Gateway.asked == [("POST", "/flows/verdict", body)]
    assert reply["result"] == {
        "content": [{"type": "text", "text": "Your verdict on plan's try 1 is kept: pass."}],
        "isError": False,
    }
    assert list(tmp_path.iterdir()) == [], "it writes nothing in the folder"


def test_flow_verdict_sends_the_criteria_as_the_model_gave_them_so_the_services_refusal_names_what_to_fix(
    tmp_path: Path, gateway: str
) -> None:
    criteria = [{**CRITERION, "file": "PLAN.md"}, "about 60 grid points"]
    session(tmp_path, gateway, [called("flow_verdict", {"result": "pass", "findings": [], "criteria": criteria})])
    [(_, _, body)] = Gateway.asked
    assert body["criteria"] == criteria
    session(tmp_path, gateway, [called("flow_verdict", {"result": "pass", "findings": [], "criteria": CRITERION})])
    assert Gateway.asked[-1][2]["criteria"] == [CRITERION], "one criterion, not in a list, is sent as one"


def test_a_refusal_is_the_tools_error_and_a_server_that_does_not_know_its_workspace_gives_none(
    tmp_path: Path, gateway: str
) -> None:
    [refused] = session(tmp_path, gateway, [called("flow_verdict", {"result": "fail", "findings": []})])
    assert refused["result"]["isError"] is True
    assert refused["result"]["content"][0]["text"].startswith("a fail lists its findings, each one thing to fix")
    [unknown] = session(tmp_path, gateway, [called("flow_verdict", {"result": "pass", "findings": []})], workspace="")
    assert unknown["result"]["isError"] is True
    assert "does not know its workspace" in unknown["result"]["content"][0]["text"]
    assert len(Gateway.asked) == 1, "the one that knew its workspace asked"


def test_the_tools_of_a_flow_are_listed_and_flow_read_is_marked_read_only(tmp_path: Path, gateway: str) -> None:
    [listed] = session(tmp_path, gateway, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    assert tools["flow_read"]["annotations"]["readOnlyHint"] is True, "the planner may read its flow"
    propose = tools["flow_propose_box"]
    assert propose["annotations"]["readOnlyHint"] is False, "it changes Clank's state, though no file"
    assert propose["inputSchema"]["required"] == ["after", "type", "title", "prompt", "deliverable"]
    assert set(propose["inputSchema"]["properties"]) == {
        "after", "type", "title", "prompt", "deliverable", "accept_when", "model", "mode", "sees", "why", "flow",
    }  # fmt: skip
    assert tools["flow_submit"]["inputSchema"]["required"] == ["summary"]
    for name in ("flow_read", "flow_propose_box", "flow_submit"):
        assert "Returns" in tools[name]["description"], name


def test_flow_propose_box_sends_its_arguments_with_its_workspace_and_answers_what_the_service_said(
    tmp_path: Path, gateway: str
) -> None:
    arguments = {
        "after": "split", "type": "task", "title": "The grid", "prompt": "Write grid.json.", "deliverable": "grid.json",
        "accept_when": ["about 60 points"], "sees": ["PLAN.md"], "why": "The plan's first step.",
    }  # fmt: skip
    [reply] = session(tmp_path, gateway, [called("flow_propose_box", arguments)])
    assert Gateway.asked == [("POST", "/flows/propose", {"workspace": "myproject", **arguments})]
    assert reply["result"] == {
        "content": [{"type": "text", "text": "Proposed T1 (The grid) after split: it waits for the user."}],
        "isError": False,
    }
    [refused] = session(tmp_path, gateway, [called("flow_propose_box", {**arguments, "type": "subtask"})])
    assert refused["result"]["isError"] is True
    assert refused["result"]["content"][0]["text"].startswith("type is one of you, plan, verify")
    assert list(tmp_path.iterdir()) == [], "it writes nothing in the folder"


def test_flow_submit_sends_its_summary_and_flow_read_asks_with_its_workspace(tmp_path: Path, gateway: str) -> None:
    submitted, read = session(
        tmp_path, gateway, [called("flow_submit", {"summary": "One task."}), called("flow_read", {}, id=2)]
    )
    assert Gateway.asked[0] == ("POST", "/flows/submit", {"workspace": "myproject", "summary": "One task."})
    assert submitted["result"]["content"][0]["text"] == "Submitted 1 proposal (T1): it waits for the user."
    assert Gateway.asked[1] == ("GET", "/flows/read?workspace=myproject", None)
    assert json.loads(read["result"]["content"][0]["text"])["you_are"] == "split", "the flow, as JSON"
    session(tmp_path, gateway, [called("flow_read", {"flow": "study"})])
    assert Gateway.asked[2] == ("GET", "/flows/read?workspace=myproject&flow=study", None)
    [unknown] = session(tmp_path, gateway, [called("flow_submit", {"summary": "One task."})], workspace="")
    assert unknown["result"]["isError"] is True
    assert len(Gateway.asked) == 3, "a server that does not know its workspace asks nothing"


def test_flow_draft_sends_the_whole_flow_as_the_model_gave_it_naming_its_workspace(
    tmp_path: Path, gateway: str
) -> None:
    flow = {"title": "A study", "boxes": [{"id": "brief", "type": "you", "title": "Brief", "writes": ["BRIEF.md"]}],
            "lines": []}  # fmt: skip
    [listed] = session(tmp_path, gateway, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    tool = next(tool for tool in listed["result"]["tools"] if tool["name"] == "flow_draft")
    assert tool["inputSchema"]["required"] == ["flow"]
    assert tool["annotations"]["readOnlyHint"] is False
    assert "planning session" in tool["description"]
    [reply] = session(tmp_path, gateway, [called("flow_draft", {"flow": flow})])
    assert Gateway.asked == [("POST", "/flows/draft", {"workspace": "myproject", "flow": flow})]
    assert reply["result"]["content"][0]["text"] == "Written as myproject/flow."
    [refused] = session(tmp_path, gateway, [called("flow_draft", {"flow": {"title": "broken"}})])
    assert refused["result"]["isError"] is True
    assert refused["result"]["content"][0]["text"].startswith("Not written. Fix each")
    assert list(tmp_path.iterdir()) == [], "it writes nothing in the folder"
