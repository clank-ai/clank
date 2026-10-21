"""Design 0002 §1 (the tools component) and the M8.0 plan: an MCP server's standard entry (`.mcp.json`'s) is read and
written as other harnesses write it; a check starts a stdio server with its environment, asks it to initialize and
for its tools, and ends it; one that never answers is ended at its time limit, saying so; a program that cannot start
is named; an http server is checked over the streamable HTTP transport, its session kept, whether it answers in JSON
or in server-sent events."""

import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import psutil
import pytest

from clank.components.tools.mcp import McpError, Server, check, parse_entry
from tests.support.served import free_port

FAKE = str(Path(__file__).resolve().parents[2] / "fakes" / "mcp_server.py")


def stdio(*extra: str, env: dict[str, str] | None = None) -> Server:
    return Server(transport="stdio", command=sys.executable, args=[FAKE, *extra], env=env or {})


def test_a_servers_standard_entry_is_read_as_other_harnesses_write_it() -> None:
    assert parse_entry({"command": "myproject-mcp"}) == Server(transport="stdio", command="myproject-mcp")
    given = {"type": "stdio", "command": "uvx", "args": ["pkg", "--port", "3"], "env": {"K": "v"}}
    assert parse_entry(given) == Server(transport="stdio", command="uvx", args=["pkg", "--port", "3"], env={"K": "v"})
    assert parse_entry({"type": "http", "url": "https://x.test/mcp", "headers": {"Authorization": "Bearer t"}}) == (
        Server(transport="http", url="https://x.test/mcp", headers={"Authorization": "Bearer t"})
    )
    assert parse_entry({"url": "https://x.test/sse", "type": "sse"}).transport == "sse"
    assert parse_entry({"type": "streamable-http", "url": "https://x.test/mcp"}).transport == "http"
    assert stdio().entry() == {"type": "stdio", "command": sys.executable, "args": [FAKE], "env": {}}
    for wrong in ({}, {"type": "stdio"}, {"type": "http"}, {"type": "smoke", "url": "x"}, {"command": 3}):
        with pytest.raises(McpError):
            parse_entry(wrong)


def test_a_stdio_server_is_started_with_its_environment_asked_for_its_tools_and_ended() -> None:
    before = {child.pid for child in psutil.Process().children(recursive=True)}
    found = check(stdio(env={"FAKE_MCP_TOKEN": "secret-value"}), seconds=30)
    assert (found.name, found.version, found.protocol) == ("fake-mcp", "1.2.3", "2025-06-18")
    assert [tool.name for tool in found.tools] == ["add", "echo"]
    assert "the token reached it" in found.tools[0].description
    assert all(child.pid in before for child in psutil.Process().children(recursive=True)), "it was ended"


def test_a_tool_its_server_marks_read_only_is_known_as_one_and_no_other_is() -> None:
    found = check(stdio(), seconds=30)
    assert [(tool.name, tool.read_only) for tool in found.tools] == [("add", False), ("echo", True)]


def test_a_server_that_never_answers_is_ended_at_its_time_limit_saying_so() -> None:
    started = time.monotonic()
    with pytest.raises(McpError, match=r"did not answer initialize within 2 seconds"):
        check(stdio("--silent"), seconds=2)
    assert time.monotonic() - started < 15


def test_a_program_that_cannot_start_is_named() -> None:
    with pytest.raises(McpError, match="cannot start clank-no-such-server"):
        check(Server(transport="stdio", command="clank-no-such-server"), seconds=5)


@pytest.fixture(params=["json", "events"])
def http_server(request: pytest.FixtureRequest) -> Iterator[str]:
    port = free_port()
    extra = ["--sse-answers"] if request.param == "events" else []
    process = subprocess.Popen([sys.executable, FAKE, "--http", str(port), *extra], stdout=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 20
        while True:
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", port)) == 0:
                    break
            assert time.monotonic() < deadline, "the fake server never listened"
            time.sleep(0.05)
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        process.kill()
        process.wait(10)


def test_an_http_server_is_checked_keeping_its_session(http_server: str) -> None:
    found = check(Server(transport="http", url=http_server, headers={"Authorization": "Bearer t"}), seconds=20)
    assert (found.name, [tool.name for tool in found.tools]) == ("fake-mcp", ["add", "echo"])
