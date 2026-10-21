"""MCP servers as other harnesses define them, and a check that talks to one (the Model Context Protocol, revision
2025-06-18; the M8.0 plan).

A `Server` is what other harnesses keep for one: its transport, and the command that starts it (`stdio`) or the
address it listens at (`http`, the streamable HTTP transport; `sse`, the older one), with its environment or headers.
`entry()` gives it as `.mcp.json`'s `mcpServers` hold it, and `parse_entry` reads one back the way those files write it
(no `type` and a command: stdio; `streamable-http` is http).

`check` asks a server what it is: it starts a stdio server like everything Clank starts (`background_flags()`: no
window), its environment added to the service's, and talks over its input and output, one JSON message a line; it
reaches an http server with POSTs, keeping the session id the server gives and reading an answer sent as JSON or as
server-sent events; `through` makes a stdio server one started inside a workspace's container (design 0004 §10), so it
is checked where the agent will run it. Either way it sends `initialize`, then `notifications/initialized`, then
`tools/list`, and gives back the server's name, version, protocol revision and tools, each with its parameters (read
from its input schema: name, type, whether it is required, and what it is) and whether the server marks it read-only
(`annotations.readOnlyHint`; the planner may use only those, design 0009 §3). A stdio server is then ended with every
process it started (its input closed first, as the protocol asks); one that does not answer within the time limit is
ended and the check says which question it left unanswered, with the last lines it wrote to its errors. A check of an
`sse` server is not built yet: such a server is kept, and its check says so.
"""

import contextlib
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx2

from clank import __version__
from clank.kernel.processes import _end, background_flags

PROTOCOL = "2025-06-18"
Transport = Literal["stdio", "http", "sse"]
TRANSPORTS: dict[str, Transport] = {"stdio": "stdio", "http": "http", "streamable-http": "http", "sse": "sse"}


class McpError(Exception):
    """A server entry that is not one, or a server that cannot be reached or does not answer."""


@dataclass(frozen=True)
class Server:
    """How to start or reach an MCP server."""

    transport: Transport
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)

    def entry(self) -> dict[str, Any]:
        """Its entry as `.mcp.json` holds it."""
        if self.transport == "stdio":
            return {"type": "stdio", "command": self.command, "args": list(self.args), "env": dict(self.env)}
        return {"type": self.transport, "url": self.url, "headers": dict(self.headers)}


@dataclass(frozen=True)
class Parameter:
    """One parameter of a tool, from its input schema."""

    name: str
    type: str
    required: bool
    description: str


@dataclass(frozen=True)
class Tool:
    """One tool a server offers."""

    name: str
    description: str
    parameters: tuple[Parameter, ...] = ()
    read_only: bool = False  # its server marks it so (`annotations.readOnlyHint`): it changes nothing


@dataclass(frozen=True)
class Checked:
    """What a server said it is."""

    name: str
    version: str
    protocol: str
    tools: list[Tool]


def parse_entry(raw: Mapping[str, Any]) -> Server:
    """A server from its standard entry; McpError when it is not one."""
    if not isinstance(raw, Mapping):
        raise McpError("a server's entry is a JSON object")
    named = raw.get("type") or ("stdio" if "command" in raw else "http" if "url" in raw else "")
    transport = TRANSPORTS.get(str(named))
    if transport is None:
        raise McpError(
            f"unknown transport {named!r}: stdio, http or sse" if named else "an entry needs a command or a url"
        )
    if transport == "stdio":
        command = raw.get("command")
        if not isinstance(command, str) or not command:
            raise McpError("a stdio server's entry needs its command")
        return Server(transport, command=command, args=_texts(raw.get("args", []), "args"), env=_pairs(raw, "env"))
    url = raw.get("url")
    if not isinstance(url, str) or not url:
        raise McpError(f"an {transport} server's entry needs its url")
    return Server(transport, url=url, headers=_pairs(raw, "headers"))


def through(server: Server, argv: Callable[[list[str], dict[str, str]], list[str]]) -> Server:
    """A stdio server started through another command that runs it elsewhere (a workspace's container: `argv` gives
    that command for the server's own and its environment), so a check talks to it where an agent would."""
    if server.transport != "stdio":
        raise McpError("only a server started by a command runs in a workspace; one reached by address does not")
    command, *args = argv([server.command, *server.args], dict(server.env))
    return Server("stdio", command=command, args=args)


def check(server: Server, seconds: float = 30.0) -> Checked:
    """Ask a server what it is and what tools it has; it is ended afterwards if Clank started it."""
    if server.transport == "stdio":
        return _check_stdio(server, seconds)
    if server.transport == "http":
        return _check_http(server, seconds)
    raise McpError("checking an sse server is not built yet; it is kept, and an agent will reach it")


def _texts(value: Any, key: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise McpError(f"{key} is a list of strings")
    return list(value)


def _pairs(raw: Mapping[str, Any], key: str) -> dict[str, str]:
    value = raw.get(key, {})
    if not isinstance(value, Mapping) or not all(isinstance(v, str) for v in value.values()):
        raise McpError(f"{key} maps names to strings")
    return {str(name): str(text) for name, text in value.items()}


def _initialize() -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": PROTOCOL,
            "capabilities": {},
            "clientInfo": {"name": "clank", "version": __version__},
        },
    }


INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
TOOLS = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}


def _checked(initialized: dict[str, Any], listed: dict[str, Any]) -> Checked:
    for asked, reply in (("initialize", initialized), ("tools/list", listed)):
        if "error" in reply:
            raise McpError(f"it refused {asked}: {reply['error'].get('message', reply['error'])}")
    info = initialized.get("result", {})
    tools = [
        Tool(
            str(tool.get("name", "")),
            str(tool.get("description") or "").strip(),
            _parameters(tool),
            _read_only(tool),
        )
        for tool in listed.get("result", {}).get("tools", [])
    ]
    server = info.get("serverInfo") or {}
    name, version = str(server.get("name", "")), str(server.get("version", ""))
    return Checked(name, version, str(info.get("protocolVersion", "")), tools)


def _read_only(tool: Mapping[str, Any]) -> bool:
    """Whether the server marks the tool read-only; a mark not given, or given as anything but true, is not one."""
    annotations = tool.get("annotations")
    return isinstance(annotations, Mapping) and annotations.get("readOnlyHint") is True


def _parameters(tool: Mapping[str, Any]) -> tuple[Parameter, ...]:
    """A tool's parameters from its input schema's properties, in the schema's order."""
    schema = tool.get("inputSchema") or {}
    properties = schema.get("properties") if isinstance(schema, Mapping) else None
    if not isinstance(properties, Mapping):
        return ()
    required = set(schema.get("required") or [])
    found = []
    for name, spec in properties.items():
        spec = spec if isinstance(spec, Mapping) else {}
        kind = spec.get("type") or ("one of several" if "anyOf" in spec or "oneOf" in spec else "")
        kind = " or ".join(str(each) for each in kind) if isinstance(kind, list) else str(kind)
        description = " ".join(str(spec.get("description") or "").split())
        found.append(Parameter(str(name), kind, name in required, description))
    return tuple(found)


def _check_stdio(server: Server, seconds: float) -> Checked:
    program = shutil.which(server.command) or server.command
    try:
        process = subprocess.Popen(
            [program, *server.args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **server.env},
            creationflags=background_flags(),
            start_new_session=sys.platform != "win32",
        )
    except OSError as error:
        raise McpError(f"cannot start {server.command}: {error.strerror or error}") from error
    lines: queue.Queue[bytes | None] = queue.Queue()
    errors: list[str] = []
    threading.Thread(target=_pump, args=(process.stdout, lines), daemon=True).start()
    threading.Thread(target=_keep, args=(process.stderr, errors), daemon=True).start()
    deadline = time.monotonic() + seconds
    try:
        _send(process, _initialize())
        initialized = _await(lines, 1, "initialize", deadline, seconds, errors)
        _send(process, INITIALIZED)
        _send(process, TOOLS)
        listed = _await(lines, 2, "tools/list", deadline, seconds, errors)
        return _checked(initialized, listed)
    finally:
        with contextlib.suppress(OSError, ValueError):
            if process.stdin:
                process.stdin.close()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(2)
        _end(process)
        for pipe in (process.stdout, process.stderr):
            with contextlib.suppress(OSError, ValueError):
                if pipe:
                    pipe.close()


def _send(process: "subprocess.Popen[bytes]", message: dict[str, Any]) -> None:
    assert process.stdin is not None
    try:
        process.stdin.write((json.dumps(message) + "\n").encode("utf-8"))
        process.stdin.flush()
    except OSError as error:
        raise McpError(f"it ended before it was asked {message.get('method')}") from error


def _pump(stream: Any, lines: "queue.Queue[bytes | None]") -> None:
    with contextlib.suppress(OSError, ValueError):
        for raw in stream:
            lines.put(raw)
    lines.put(None)


def _keep(stream: Any, errors: list[str]) -> None:
    with contextlib.suppress(OSError, ValueError):
        for raw in stream:
            errors.append(raw.decode("utf-8", errors="replace").rstrip())
            del errors[:-5]


def _await(
    lines: "queue.Queue[bytes | None]", id: int, asked: str, deadline: float, seconds: float, errors: list[str]
) -> dict[str, Any]:
    while True:
        left = deadline - time.monotonic()
        try:
            raw = lines.get(timeout=max(left, 0.01))
        except queue.Empty:
            raise McpError(f"it did not answer {asked} within {seconds:g} seconds{_said(errors)}") from None
        if raw is None:
            raise McpError(f"it ended before it answered {asked}{_said(errors)}")
        with contextlib.suppress(ValueError):
            message = json.loads(raw)
            if isinstance(message, dict) and message.get("id") == id:
                return message


def _said(errors: list[str]) -> str:
    return f"; it wrote: {' / '.join(errors[-3:])}" if errors else ""


def _check_http(server: Server, seconds: float) -> Checked:
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", **server.headers}
    try:
        with httpx2.Client(timeout=seconds) as client:
            first = client.post(server.url, json=_initialize(), headers=headers)
            initialized = _http_answer(first, 1, "initialize")
            session = first.headers.get("Mcp-Session-Id")
            following = {**headers, "MCP-Protocol-Version": str(initialized.get("result", {}).get("protocolVersion"))}
            if session:
                following["Mcp-Session-Id"] = session
            client.post(server.url, json=INITIALIZED, headers=following)
            listed = _http_answer(client.post(server.url, json=TOOLS, headers=following), 2, "tools/list")
    except httpx2.HTTPError as error:
        raise McpError(f"cannot reach {server.url}: {error}") from error
    return _checked(initialized, listed)


def _http_answer(response: Any, id: int, asked: str) -> dict[str, Any]:
    if response.status_code >= 400:
        raise McpError(f"it answered {asked} with HTTP {response.status_code}")
    if response.headers.get("content-type", "").startswith("text/event-stream"):
        for line in response.text.splitlines():
            if line.startswith("data:"):
                with contextlib.suppress(ValueError):
                    message = json.loads(line[5:].strip())
                    if isinstance(message, dict) and message.get("id") == id:
                        return message
        raise McpError(f"its events held no answer to {asked}")
    try:
        found = response.json()
    except ValueError as error:
        raise McpError(f"its answer to {asked} is not JSON") from error
    if not isinstance(found, dict):
        raise McpError(f"its answer to {asked} is not one message")
    return found
