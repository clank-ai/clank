"""Design 0022 §4 and §7: Clank's own MCP server gives the agent the board as tools, each a request to the gateway's
`/agents/boards` routes naming the workspace the server serves: `board_new(name, folder, title)`, `board_read(board)`
(read-only: the board in words), `board_add(board, kind, ..., at)` (the item's fields as the model gave them, placed by
`at`), `board_update(board, id, ..., at)`, `board_remove(board, id)` and `board_export(board, frame or ids, format,
file, keep)`. The descriptions say to place by where, never by pixels; each answer is the service's words, a refusal
the tool's error in its words."""

import json
import threading
import urllib.parse
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from tests.components.agents.test_flow_tools import called, session
from tests.support.served import free_port


class Gateway(BaseHTTPRequestHandler):
    """The gateway's `/agents/boards` routes as the service answers them, and what was asked."""

    asked: ClassVar[list[tuple[str, str, Any]]] = []

    def do_GET(self) -> None:
        url = urllib.parse.urlparse(self.path)
        Gateway.asked.append(("GET", url.path, dict(urllib.parse.parse_qsl(url.query))))
        self._json(
            {"board": "figures/fig3.board", "said": "The board figures/fig3.board: 1 items\nfig-1: figure a.png"}
        )

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        Gateway.asked.append(("POST", self.path, body))
        if body.get("id") == "fig-9":
            self._json({"error": {"code": "refused", "message": "there is no item fig-9 on the board"}}, 409)
        else:
            self._json({"board": "figures/fig3.board", "id": "fig-2", "said": f"done: {self.path}"})

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


def test_the_board_tools_are_listed_and_say_to_place_by_where(tmp_path: Path, gateway: str) -> None:
    [listed] = session(tmp_path, gateway, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    assert {"board_new", "board_read", "board_add", "board_update", "board_remove"} <= set(tools)
    assert tools["board_read"]["annotations"]["readOnlyHint"] is True
    add = tools["board_add"]
    assert add["inputSchema"]["required"] == ["board", "kind"]
    assert add["inputSchema"]["properties"]["kind"]["enum"] == ["figure", "latex", "note", "slot", "frame", "arrow"]
    for needed in ("right_of", "below", "slot", "never pixels"):
        assert needed in json.dumps(add), needed


def test_each_tool_asks_the_gateway_naming_its_workspace_and_answers_the_services_words(
    tmp_path: Path, gateway: str
) -> None:
    replies = session(tmp_path, gateway, [
        called("board_new", {"name": "fig3", "folder": "figures", "title": "Figure 3"}, 1),
        called("board_read", {"board": "fig3"}, 2),
        called("board_add", {"board": "fig3", "kind": "figure", "file": "figures/phase.png", "caption": "(c) Phase",
                             "at": {"slot": "slot-3"}}, 3),
        called("board_update", {"board": "fig3", "id": "fig-2", "caption": "(c) Phase lag",
                                "at": {"below": "fig-1"}}, 4),
        called("board_remove", {"board": "fig3", "id": "fig-9"}, 5),
    ])  # fmt: skip
    assert Gateway.asked == [
        ("POST", "/agents/boards", {"workspace": "myproject", "name": "fig3", "folder": "figures",
                                    "title": "Figure 3"}),
        ("GET", "/agents/boards/read", {"workspace": "myproject", "board": "fig3"}),
        ("POST", "/agents/boards/add", {"workspace": "myproject", "board": "fig3", "kind": "figure",
                                        "fields": {"file": "figures/phase.png", "caption": "(c) Phase"},
                                        "at": {"slot": "slot-3"}}),
        ("POST", "/agents/boards/update", {"workspace": "myproject", "board": "fig3", "id": "fig-2",
                                           "changes": {"caption": "(c) Phase lag"}, "at": {"below": "fig-1"}}),
        ("POST", "/agents/boards/remove", {"workspace": "myproject", "board": "fig3", "id": "fig-9"}),
    ]  # fmt: skip
    assert replies[0]["result"]["content"][0]["text"] == "done: /agents/boards"
    assert "fig-1: figure a.png" in replies[1]["result"]["content"][0]["text"]
    assert replies[2]["result"]["isError"] is False
    assert replies[4]["result"] == {"content": [{"type": "text", "text": "there is no item fig-9 on the board"}],
                                    "isError": True}  # fmt: skip


def test_board_export_asks_for_a_frame_as_a_figure_file(tmp_path: Path, gateway: str) -> None:
    [listed, reply] = session(tmp_path, gateway, [
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        called("board_export", {"board": "fig3", "frame": "frame-4", "format": "pdf", "keep": True}, 2),
    ])  # fmt: skip
    export = next(tool for tool in listed["result"]["tools"] if tool["name"] == "board_export")
    assert export["inputSchema"]["properties"]["format"]["enum"] == ["pdf", "png", "svg"]
    assert "includegraphics" in export["description"]
    assert Gateway.asked == [("POST", "/agents/boards/export", {"workspace": "myproject", "board": "fig3",
                              "frame": "frame-4", "ids": [], "format": "pdf", "file": "", "keep": True})]  # fmt: skip
    assert reply["result"]["content"][0]["text"] == "done: /agents/boards/export"
