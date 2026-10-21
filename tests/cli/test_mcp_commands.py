"""Design 0002 §2.15 and the M8.0 plan, task 2: `clank mcp` adds MCP servers the way other harnesses do (`claude mcp
add`, `codex mcp add`): the server's own command after `--`, its options never taken for Clank's; its first word after
the name without `--`; a URL with `--transport http` (or alone); `-e` and `-H` given as secrets, never printed; `--scope
project` writing the current folder's `.mcp.json`; `add-json` taking an entry as that file holds one. A command that
starts with a dash (the owner's own first try, `clank mcp add myproject --myproject-mcp`) is refused, showing the form
with `--`. `list`, `get` (secrets by name and last four characters), `remove` and `check` (following its operation) do
the rest."""

import json
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from click.testing import CliRunner, Result
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common, follow
from clank.cli.main import main
from clank.client import Client
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home

FAKE = str(Path(__file__).resolve().parents[1] / "fakes" / "mcp_server.py")
SECRET = "sk-secret-value-1234"


@pytest.fixture
def kernel(home: Home, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(follow, "POLL_SECONDS", 0.005)
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 13, 18, 0, tzinfo=UTC)), registry.components())
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7720", "t", name="cli", http=http))
        yield kernel
    kernel.close()


def run(*arguments: str) -> Result:
    return CliRunner().invoke(main, ["mcp", *arguments])


def test_a_server_clank_starts_is_added_with_its_command_after_the_double_dash(kernel: Kernel) -> None:
    added = run("add", "myproject", "--", "myproject-mcp")
    assert added.exit_code == 0, added.output
    assert "Added myproject to your servers (stdio: myproject-mcp)" in added.output
    added = run("add", "-e", f"API_KEY={SECRET}", "uvtool", "--", "uvx", "some-mcp", "--port", "3", "-e", "x")
    assert added.exit_code == 0, added.output
    assert "uvx some-mcp --port 3 -e x" in added.output, "after --, everything is the server's"
    assert SECRET not in added.output
    shown = run("get", "uvtool")
    assert "env.API_KEY: set" in shown.output
    assert "ends in 1234" in shown.output
    assert SECRET not in shown.output


def test_without_the_double_dash_the_first_word_is_the_command_and_unknown_options_go_with_it(kernel: Kernel) -> None:
    added = run("add", "plain", "plain-mcp", "--verbose")
    assert added.exit_code == 0, added.output
    assert "(stdio: plain-mcp --verbose)" in added.output


def test_a_command_starting_with_a_dash_is_refused_showing_the_double_dash(kernel: Kernel) -> None:
    refused = run("add", "myproject", "--myproject-mcp")
    assert refused.exit_code == 2
    assert "clank mcp add myproject -- myproject-mcp" in refused.output
    assert "No MCP servers yet" in run("list").output, "nothing was added"


def test_a_server_at_a_url_is_added_with_its_headers_as_secrets(kernel: Kernel) -> None:
    added = run("add", "--transport", "http", "-H", f"Authorization: Bearer {SECRET}", "notion", "https://x.test/mcp")
    assert added.exit_code == 0, added.output
    assert "(http: https://x.test/mcp)" in added.output
    implied = run("add", "remote", "https://y.test/mcp")
    assert "(http: https://y.test/mcp)" in implied.output, "a URL alone says http"
    assert run("add", "-t", "http", "two", "https://y.test/mcp", "extra").exit_code == 2
    assert run("add", "-e", "K=V", "-t", "http", "three", "https://y.test/mcp").exit_code == 2


def test_a_projects_server_goes_into_the_folders_mcp_json(kernel: Kernel) -> None:
    added = run("add", "--scope", "project", "-e", "MODE=fast", "local", "--", "local-mcp", "--flag")
    assert added.exit_code == 0, added.output
    assert "this project's .mcp.json" in added.output
    written = json.loads(Path(".mcp.json").read_text(encoding="utf-8"))
    assert written["mcpServers"]["local"] == {"type": "stdio", "command": "local-mcp", "args": ["--flag"],
                                              "env": {"MODE": "fast"}}  # fmt: skip


def test_add_json_list_get_and_remove(kernel: Kernel) -> None:
    added = run("add-json", "fromjson", json.dumps({"command": "x-mcp", "args": ["a"]}))
    assert added.exit_code == 0, added.output
    listed = run("list")
    assert "fromjson" in listed.output
    assert "x-mcp a" in listed.output
    as_json = json.loads(run("list", "--json").output)
    assert [server["name"] for server in as_json] == ["fromjson"]
    assert run("add-json", "bad", "{not json").exit_code == 2
    removed = run("remove", "fromjson")
    assert "Removed fromjson from your servers" in removed.output
    assert "No MCP servers yet" in run("list").output


def test_check_follows_its_operation_and_lists_the_tools(kernel: Kernel) -> None:
    run("add", "-e", f"FAKE_MCP_TOKEN={SECRET}", "fake", "--", sys.executable, FAKE)
    checked = run("check", "fake")
    assert checked.exit_code == 0, checked.output
    assert "fake: fake-mcp 1.2.3, protocol 2025-06-18, 2 tools" in checked.output
    assert "add: Adds two numbers (the token reached it)." in checked.output
    assert SECRET not in checked.output
