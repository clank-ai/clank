"""Design 0002 §2.8 and §2.11, and the M8.0 plan, task 1: an MCP server added for the user is a settings record holding
how to start or reach it, the values of its environment and headers kept as secrets, never in a record or an event; a
project's servers are its `.mcp.json`, written as other harnesses write it, the rest of the file left as it was; a name
is a plain word, new in its place, and one used in both places is asked about; removing a server removes its secrets; a
check starts the server with its secrets, asks it for its tools, and ends it."""

import json
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "cli"}
FAKE = str(Path(__file__).resolve().parents[2] / "fakes" / "mcp_server.py")
SECRET = "sk-secret-value-1234"
YOU = Actor(kind="user", via="cli")


@pytest.fixture
def kernel(home: Home) -> Iterator[Kernel]:
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 13, 18, 0, tzinfo=UTC)), registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def http(kernel: Kernel) -> Iterator[TestClient]:
    with TestClient(create_app(kernel, token="t", port=7725), base_url="http://127.0.0.1:7725") as client:
        yield client


def call(http: TestClient, method: str, path: str, status: int = 200, **body: Any) -> Any:
    answer = http.request(method, f"/api/v1/{path}", headers=AUTH, json=body or None)
    assert answer.status_code == status, answer.text
    return answer.json()


def written(home: Home) -> str:
    """Everything Clank wrote outside its secrets folder."""
    return "\n".join(
        path.read_bytes().decode("utf-8", errors="replace")
        for path in home.root.rglob("*")
        if path.is_file() and home.secrets not in path.parents
    )


def test_a_server_added_for_you_is_a_record_and_its_secrets_are_kept_apart(
    kernel: Kernel, http: TestClient, tmp_path: Path
) -> None:
    entry = {"command": "myproject-mcp", "args": ["--quiet"], "env": {"API_KEY": SECRET}}
    added = call(http, "POST", "mcp/servers", name="myproject", scope="user", folder=str(tmp_path), entry=entry)
    assert (added["name"], added["scope"], added["transport"], added["command"]) == (
        "myproject", "user", "stdio", "myproject-mcp"
    )  # fmt: skip
    assert (added["args"], added["env"]) == (["--quiet"], ["API_KEY"])
    assert added["secrets"] == [{"name": "env.API_KEY", "set": "2026-10-13T18:00:00.000Z", "ends": "1234"}]
    record = kernel.home.config / "mcp-servers" / "myproject.json"
    assert "API_KEY" in record.read_text(encoding="utf-8")
    assert SECRET not in written(kernel.home)
    listed = call(http, "GET", f"mcp/servers?folder={tmp_path}")["servers"]
    assert [(server["name"], server["scope"]) for server in listed] == [("myproject", "user")]
    assert call(http, "GET", f"mcp/servers/myproject?folder={tmp_path}")["env"] == ["API_KEY"]


def test_an_http_servers_headers_are_secrets_too(kernel: Kernel, http: TestClient, tmp_path: Path) -> None:
    entry = {"type": "http", "url": "https://mcp.example.test/mcp", "headers": {"Authorization": f"Bearer {SECRET}"}}
    added = call(http, "POST", "mcp/servers", name="remote", folder=str(tmp_path), entry=entry)
    assert (added["transport"], added["url"], added["headers"]) == (
        "http",
        "https://mcp.example.test/mcp",
        ["Authorization"],
    )
    assert SECRET not in written(kernel.home)


def test_a_projects_servers_are_its_mcp_json_as_other_harnesses_write_it(http: TestClient, tmp_path: Path) -> None:
    standard = tmp_path / ".mcp.json"
    standard.write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}, "note": "kept"}), encoding="utf-8")
    entry = {"command": "myproject-mcp", "env": {"MODE": "fast"}}
    added = call(http, "POST", "mcp/servers", name="myproject", scope="project", folder=str(tmp_path), entry=entry)
    assert (added["scope"], added["file"]) == ("project", str(standard))
    file = json.loads(standard.read_text(encoding="utf-8"))
    assert file["note"] == "kept"
    assert file["mcpServers"]["other"] == {"command": "x"}
    assert file["mcpServers"]["myproject"] == {
        "type": "stdio",
        "command": "myproject-mcp",
        "args": [],
        "env": {"MODE": "fast"},
    }
    listed = call(http, "GET", f"mcp/servers?folder={tmp_path}")["servers"]
    assert [(server["name"], server["scope"]) for server in listed] == [("myproject", "project"), ("other", "project")]
    call(http, "DELETE", f"mcp/servers/myproject?scope=project&folder={tmp_path}")
    assert list(json.loads(standard.read_text(encoding="utf-8"))["mcpServers"]) == ["other"]


def test_a_name_used_in_both_places_is_asked_about(http: TestClient, tmp_path: Path) -> None:
    for scope in ("user", "project"):
        call(http, "POST", "mcp/servers", name="twice", scope=scope, folder=str(tmp_path), entry={"command": "x"})
    asked = call(http, "GET", f"mcp/servers/twice?folder={tmp_path}", status=409)
    assert "both" in asked["error"]["message"]
    assert call(http, "GET", f"mcp/servers/twice?folder={tmp_path}&scope=project")["scope"] == "project"


def test_a_name_is_a_plain_word_new_in_its_place_and_an_entry_must_be_one(http: TestClient, tmp_path: Path) -> None:
    for name in ("../x", "my project", "-x", ""):
        call(http, "POST", "mcp/servers", status=400, name=name, folder=str(tmp_path), entry={"command": "x"})
    call(http, "POST", "mcp/servers", name="myproject", folder=str(tmp_path), entry={"command": "x"})
    for name in ("myproject", "MyProject"):
        taken = call(http, "POST", "mcp/servers", status=409, name=name, folder=str(tmp_path), entry={"command": "x"})
        assert "already" in taken["error"]["message"]
    wrong = call(http, "POST", "mcp/servers", status=400, name="remote", folder=str(tmp_path), entry={"type": "http"})
    assert "url" in wrong["error"]["message"]


def test_removing_a_server_removes_its_secrets(kernel: Kernel, http: TestClient, tmp_path: Path) -> None:
    entry = {"command": "x", "env": {"API_KEY": SECRET}}
    call(http, "POST", "mcp/servers", name="gone", folder=str(tmp_path), entry=entry)
    call(http, "DELETE", f"mcp/servers/gone?folder={tmp_path}")
    assert not (kernel.home.config / "mcp-servers" / "gone.json").exists()
    assert kernel.secrets.shown("mcp-server/gone") == []
    call(http, "GET", f"mcp/servers/gone?folder={tmp_path}", status=404)


@pytest.mark.anyio
async def test_a_check_starts_the_server_with_its_secrets_asks_for_its_tools_and_ends_it(
    kernel: Kernel, http: TestClient, tmp_path: Path
) -> None:
    entry = {"command": sys.executable, "args": [FAKE], "env": {"FAKE_MCP_TOKEN": SECRET}}
    call(http, "POST", "mcp/servers", name="fake", folder=str(tmp_path), entry=entry)
    async with kernel.operations.running():
        started = await kernel.operations.start("mcp.check", {"name": "fake", "folder": str(tmp_path)}, actor=YOU)
        with anyio.fail_after(60):
            done = await kernel.operations.wait(started.id)
    assert done.status == "done", done.error
    result = done.result or {}
    assert (result["name"], [tool["name"] for tool in result["tools"]]) == ("fake-mcp", ["add", "echo"])
    assert "the token reached it" in result["tools"][0]["description"]
    assert result["tools"][0]["parameters"] == [
        {"name": "a", "type": "number", "required": True, "description": "The first."},
        {"name": "b", "type": "number or null", "required": False, "description": ""},
    ]
    assert [tool["read_only"] for tool in result["tools"]] == [False, True], "the server's marks are kept (design 0009)"
    assert any(event.type == "secret.used" for event in kernel.events.latest(20))
    assert SECRET not in written(kernel.home)
    tools = kernel.parts["tools"]
    remembered = tools.checked("fake", "user", str(tmp_path))
    assert remembered is not None
    assert (remembered["where"], remembered["tools"]) == ("this computer", result["tools"])
    call(http, "DELETE", "mcp/servers/fake", folder=str(tmp_path))
    call(http, "POST", "mcp/servers", name="fake", folder=str(tmp_path), entry={**entry, "args": [FAKE, "--other"]})
    assert tools.checked("fake", "user", str(tmp_path)) is None, "a server started another way is checked again"
