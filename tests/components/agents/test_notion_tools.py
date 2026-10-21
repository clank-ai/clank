"""Design 0010 §4-§5: Clank's own MCP server in the container gives the agent Notion's tools, each a request to the
gateway's `/notion/` routes: reading (the shared databases, a query, a page as Markdown with its properties, a search;
marked read-only, so the planner may use them) and proposing (a new entry, a change, a removal, submitting the batch,
each naming the workspace the server serves); a refusal comes back as the tool's error, in the service's words; a
server that does not know its workspace cannot propose."""

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
READERS = ["notion_databases", "notion_query", "notion_page", "notion_search"]
PROPOSERS = ["notion_propose_entry", "notion_propose_change", "notion_propose_removal", "notion_submit", "notion_reply"]
PAGE = {
    "id": "lit-1", "title": "A made-up paper", "database": "Papers (test)", "url": "https://www.notion.so/lit-1",
    "properties": {"Year": "2001", "Keywords": "walks"}, "markdown": "## Summary\n\nA made-up result.",
    "edited": "2026-10-17T12:00:00.000Z",
}  # fmt: skip


class Gateway(BaseHTTPRequestHandler):
    """The gateway's /notion/ routes as the service answers them, and what was asked."""

    asked: ClassVar[list[tuple[str, str, Any]]] = []

    def do_GET(self) -> None:
        Gateway.asked.append(("GET", self.path, None))
        if self.path.startswith("/notion/page/"):
            self._json(PAGE)
        else:
            self._json({"databases": [{"name": "Papers (test)"}]})

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        Gateway.asked.append(("POST", self.path, body))
        if body.get("database") == "Nothing":
            self._json({"error": {"code": "refused", "message": "no shared database is named Nothing"}}, 409)
        else:
            self._json({"batch": "nb-1", "proposal": "p1", "staged": "staged as p1 of batch nb-1"})

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


def session(folder: Path, gateway: str, messages: list[dict[str, Any]], workspace: str = "paper") -> list[Any]:
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


def test_the_notion_tools_are_listed_the_reading_ones_marked_read_only(tmp_path: Path, gateway: str) -> None:
    [listed] = session(tmp_path, gateway, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    assert {*READERS, *PROPOSERS} <= set(tools)
    for name in READERS:
        assert tools[name]["annotations"]["readOnlyHint"] is True, name
        assert "Returns" in tools[name]["description"], name
    for name in PROPOSERS:
        assert tools[name]["annotations"]["readOnlyHint"] is False, name
        assert "the owner" in tools[name]["description"], name
    assert tools["notion_propose_entry"]["inputSchema"]["required"] == ["database", "properties", "why"]


def test_reading_asks_the_gateways_notion_routes_and_a_page_reads_as_markdown(tmp_path: Path, gateway: str) -> None:
    replies = session(tmp_path, gateway, [
        called("notion_databases", {}, 1),
        called("notion_query", {"database": "Papers (test)", "text": "made-up", "limit": 5}, 2),
        called("notion_page", {"page": "notion:lit-1"}, 3),
        called("notion_search", {"text": "made up"}, 4),
    ])  # fmt: skip
    assert [reply["result"]["isError"] for reply in replies] == [False] * 4
    assert Gateway.asked == [
        ("GET", "/notion/databases", None),
        ("POST", "/notion/query", {"database": "Papers (test)", "text": "made-up", "limit": 5}),
        ("GET", "/notion/page/lit-1", None),
        ("GET", "/notion/search?text=made+up", None),
    ]
    page = replies[2]["result"]["content"][0]["text"]
    assert page.startswith("# A made-up paper\n")
    assert "- Year: 2001\n- Keywords: walks" in page
    assert page.endswith("## Summary\n\nA made-up result.")


def test_a_proposal_names_the_servers_workspace_and_a_refusal_is_the_tools_error(tmp_path: Path, gateway: str) -> None:
    replies = session(tmp_path, gateway, [
        called("notion_propose_entry", {"database": "Papers (test)", "properties": {"Title": "A"},
                                        "page_markdown": "## Summary", "why": "a test", "sources": ["plan.md"]}, 1),
        called("notion_propose_entry", {"database": "Nothing", "properties": {"Title": "A"}, "why": "a test"}, 2),
        called("notion_propose_change", {"page": "lit-1", "properties": {"Year": 2002}, "why": "a test"}, 3),
        called("notion_propose_removal", {"page": "lit-2", "why": "a duplicate"}, 4),
        called("notion_submit", {"summary": "Two things."}, 5),
        called("notion_reply", {"comment": "c1", "text": "Changed the year."}, 6),
    ])  # fmt: skip
    assert Gateway.asked[0] == ("POST", "/notion/propose/entry", {
        "workspace": "paper", "database": "Papers (test)", "properties": {"Title": "A"}, "markdown": "## Summary",
        "why": "a test", "sources": ["plan.md"],
    })  # fmt: skip
    assert "staged as p1 of batch nb-1" in replies[0]["result"]["content"][0]["text"]
    assert (replies[1]["result"]["isError"], replies[1]["result"]["content"][0]["text"]) == (
        True, "no shared database is named Nothing"
    )  # fmt: skip
    assert [path for _, path, _ in Gateway.asked[2:]] == [
        "/notion/propose/change", "/notion/propose/removal", "/notion/submit", "/notion/reply",
    ]  # fmt: skip
    assert Gateway.asked[-2][2] == {"workspace": "paper", "summary": "Two things."}
    assert Gateway.asked[-1][2] == {"workspace": "paper", "comment": "c1", "text": "Changed the year."}


def test_a_server_that_does_not_know_its_workspace_cannot_propose(tmp_path: Path, gateway: str) -> None:
    [reply] = session(tmp_path, gateway, [called("notion_submit", {"summary": "x"})], workspace="")
    assert reply["result"]["isError"] is True
    assert "does not know its workspace" in reply["result"]["content"][0]["text"]
    assert Gateway.asked == []
