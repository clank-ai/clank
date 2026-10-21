"""A fake MCP server for the tools component's tests: it speaks the Model Context Protocol (revision 2025-06-18) over
its input and output (stdio), or, with `--http PORT`, over the streamable HTTP transport (answers as JSON or as
server-sent events, `--sse-answers`), answering `initialize` and `tools/list`. Its one tool's description says whether
the variable FAKE_MCP_TOKEN reached it (never its value). `--silent` makes it read and never answer. Standard library
only, so it runs wherever the tests do.
"""

import argparse
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

SERVER = {"name": "fake-mcp", "version": "1.2.3"}


def answer(message: dict[str, Any]) -> dict[str, Any] | None:
    """The answer to one JSON-RPC message, or None for a notification."""
    if "id" not in message:
        return None
    if message.get("method") == "initialize":
        result: dict[str, Any] = {
            "protocolVersion": message["params"]["protocolVersion"],
            "capabilities": {"tools": {}},
            "serverInfo": SERVER,
        }
    elif message.get("method") == "tools/list":
        token = "the token reached it" if os.environ.get("FAKE_MCP_TOKEN") else "no token"
        result = {
            "tools": [
                {
                    "name": "add",
                    "description": f"Adds two numbers ({token}).",
                    "inputSchema": {
                        "type": "object",
                        "required": ["a"],
                        "properties": {
                            "a": {"type": "number", "description": "The first."},
                            "b": {"type": ["number", "null"]},
                        },
                    },
                },
                {
                    "name": "echo",
                    "description": "Says it back.",
                    "inputSchema": {"type": "object"},
                    "annotations": {"readOnlyHint": True, "openWorldHint": False},
                },
            ]
        }
    else:
        return {"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "no such method"}}
    return {"jsonrpc": "2.0", "id": message["id"], "result": result}


def stdio(silent: bool) -> None:
    print("fake MCP server started", file=sys.stderr, flush=True)
    for line in sys.stdin:
        if silent or not line.strip():
            continue
        reply = answer(json.loads(line))
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


class Handler(BaseHTTPRequestHandler):
    """The streamable HTTP transport, as far as a check uses it."""

    events = False

    def do_POST(self) -> None:
        message = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        reply = answer(message)
        if reply is None:
            self.send_response(202)
            self.end_headers()
            return
        if message.get("method") != "initialize" and self.headers.get("Mcp-Session-Id") != "session-1":
            self.send_response(400)
            self.end_headers()
            return
        body = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Mcp-Session-Id", "session-1")
        if self.events:
            body = b"event: message\ndata: " + body + b"\n\n"
            self.send_header("Content-Type", "text/event-stream")
        else:
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        """Quiet."""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--silent", action="store_true")
    parser.add_argument("--http", type=int)
    parser.add_argument("--sse-answers", action="store_true")
    options = parser.parse_args()
    if options.http is None:
        stdio(options.silent)
        return
    Handler.events = options.sse_answers
    server = ThreadingHTTPServer(("127.0.0.1", options.http), Handler)
    print(f"listening on {options.http}", flush=True)
    try:
        server.serve_forever()
    finally:
        time.sleep(0)


if __name__ == "__main__":
    main()
