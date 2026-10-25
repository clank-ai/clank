"""Design 0018 §7.1: Clank's own MCP server in the container gives the agent `show_files(paths, why)`, which opens
files of the folder in the owner's VS Code window: a request to the gateway's `POST /agents/show` naming the
workspace the server serves, the paths as the model gave them (one path given as a string is a list of one) and why.
Its description is an order: when the owner asks to see a file, open it and stop, without reading or checking it. The
answer is what the service said; a refusal is the tool's error, in the service's words; a server that does not know its
workspace asks nothing. It writes nothing in the folder, so it is marked read-only."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from tests.components.agents.test_flow_tools import called, session
from tests.support.served import free_port

OPENED = "Opened plots/residual.png in the owner's VS Code window, on the left. The owner looks at it themselves."


class Gateway(BaseHTTPRequestHandler):
    """The gateway's `/agents/show` as the service answers it, and what was asked."""

    asked: ClassVar[list[tuple[str, Any]]] = []

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        Gateway.asked.append((self.path, body))
        if "missing.png" in body.get("paths", []):
            self._json({"error": {"code": "refused", "message": "missing.png is not a file of the folder"}}, 409)
        else:
            self._json({"files": body.get("paths"), "said": OPENED})

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


def test_show_files_is_listed_read_only_and_its_description_tells_the_model_to_open_and_stop(
    tmp_path: Path, gateway: str
) -> None:
    [listed] = session(tmp_path, gateway, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    show = tools["show_files"]
    assert show["annotations"]["readOnlyHint"] is True, "it changes no file, so the planner may use it"
    assert show["inputSchema"]["required"] == ["paths"]
    assert set(show["inputSchema"]["properties"]) == {"paths", "why"}
    assert show["inputSchema"]["properties"]["paths"]["type"] == "array"
    described = show["description"]
    assert "the user asks to see, open, show or pull up" in described
    assert "do not read, describe or check" in described
    assert "look_at_figure" in described, "it says the model does not look at it for them"
    assert "Returns" in described


def test_show_files_asks_the_gateway_naming_its_workspace_and_answers_what_the_service_said(
    tmp_path: Path, gateway: str
) -> None:
    arguments = {"paths": ["plots/residual.png"], "why": "The residual plot you asked for."}
    [reply] = session(tmp_path, gateway, [called("show_files", arguments)])
    assert Gateway.asked == [("/agents/show", {"workspace": "myproject", **arguments})]
    assert reply["result"] == {"content": [{"type": "text", "text": OPENED}], "isError": False}
    assert list(tmp_path.iterdir()) == [], "it writes nothing in the folder"


def test_one_path_given_as_a_string_is_sent_as_a_list_of_one(tmp_path: Path, gateway: str) -> None:
    session(tmp_path, gateway, [called("show_files", {"paths": "/workspace/notes.md"})])
    assert Gateway.asked == [("/agents/show", {"workspace": "myproject", "paths": ["/workspace/notes.md"], "why": ""})]


def test_a_refusal_is_the_tools_error_and_a_server_that_does_not_know_its_workspace_asks_nothing(
    tmp_path: Path, gateway: str
) -> None:
    [refused] = session(tmp_path, gateway, [called("show_files", {"paths": ["missing.png"]})])
    assert refused["result"]["isError"] is True
    assert refused["result"]["content"][0]["text"] == "missing.png is not a file of the folder"
    [unknown] = session(tmp_path, gateway, [called("show_files", {"paths": ["a.png"]})], workspace="")
    assert unknown["result"]["isError"] is True
    assert "does not know its workspace" in unknown["result"]["content"][0]["text"]
    assert len(Gateway.asked) == 1, "the one that knew its workspace asked"
