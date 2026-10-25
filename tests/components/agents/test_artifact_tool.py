"""Design 0021 §5: Clank's own MCP server gives the agent `make_artifact(name, title, kind, files, note)`: a request to
the gateway's `POST /agents/artifacts` naming the workspace the server serves, the files as the model gave them (one
given as a string is a list of one). Its description says when to make one, that its page uses only its own files and
Clank's libraries (named `clank-lib/...`), and how a new version is made; the answer is the service's words, a refusal
the tool's error in its words."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from tests.components.agents.test_flow_tools import called, session
from tests.support.served import free_port

MADE = "Artifact Sweep results (sweep), version 1, made: it opens in the owner's VS Code window, beside you."


class Gateway(BaseHTTPRequestHandler):
    """The gateway's `/agents/artifacts` as the service answers it, and what was asked."""

    asked: ClassVar[list[tuple[str, Any]]] = []

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        Gateway.asked.append((self.path, body))
        if "online.html" in body.get("files", []):
            self._json({"error": {"code": "refused", "message": "online.html names the network"}}, 409)
        else:
            self._json({"name": body["name"], "version": 1, "said": MADE})

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


def test_make_artifact_is_listed_and_says_what_a_page_may_use(tmp_path: Path, gateway: str) -> None:
    [listed] = session(tmp_path, gateway, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    made = tools["make_artifact"]
    assert made["inputSchema"]["required"] == ["name", "title", "files"]
    assert made["inputSchema"]["properties"]["kind"]["enum"] == ["html", "markdown", "svg"]
    described = made["description"]
    for needed in ("clank-lib/plotly.min.js", "no network", "same name", "next version"):
        assert needed in described, needed


def test_make_artifact_asks_the_gateway_naming_its_workspace_and_answers_the_services_words(
    tmp_path: Path, gateway: str
) -> None:
    arguments = {"name": "sweep", "title": "Sweep results", "kind": "html",
                 "files": ["report/index.html", "results/sweep.json"], "note": "first look"}  # fmt: skip
    [reply] = session(tmp_path, gateway, [called("make_artifact", arguments)])
    assert Gateway.asked == [("/agents/artifacts", {"workspace": "myproject", **arguments})]
    assert reply["result"] == {"content": [{"type": "text", "text": MADE}], "isError": False}
    [one] = session(tmp_path, gateway, [called("make_artifact", {"name": "n", "title": "N", "files": "notes.md"})])
    assert Gateway.asked[-1][1]["files"] == ["notes.md"]
    assert Gateway.asked[-1][1]["kind"] == "html", "the kind the model gave, or html"
    assert one["result"]["isError"] is False
    [refused] = session(tmp_path, gateway, [called("make_artifact", {"name": "o", "title": "O",
                                                                      "files": ["online.html"]})])  # fmt: skip
    assert refused["result"]["isError"] is True
    assert refused["result"]["content"][0]["text"] == "online.html names the network"
