"""Design 0004 §10 and the M8.0 plan, task 3: the console's MCP servers page lists every server this folder's agent can
use, one row each with where it comes from, its state and its tools; the highlighted one's details show what starts it
and its secrets by name and last four characters only; `a` adds one in a form (its command line split as a shell
would); `c` checks one (one of yours on this computer when the folder is not a workspace), after which its row counts
its tools and Enter lists them with their parameters; `s` asks for a workspace first; `d` removes one after a question.
A folder's own server (its `.mcp.json`) is checked only in the folder's workspace container: with no workspace, `c`
says so and starts nothing; in the workspace, the page and the check's message say when its entry changed since it was
allowed. Design 0011 §4 and §8 (board E14): the details' panel is titled with the highlighted server's name."""

import json
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.widgets import Input, Label, ListView

from clank import registry
from clank.client import Client
from clank.components.tools import service as tools_service
from clank.components.tools.console.servers import McpServersPage, ToolsScreen
from clank.components.tools.mcp import Checked, Server, Tool
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import names
from clank.console.app import ClankConsole
from clank.console.form import FormScreen
from clank.console.panel import Panel
from clank.console.pick import PickScreen
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.console.frames import focus_on, settle
from tests.fakes.platform import FakePlatform, container
from tests.support.live import live_service

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 13, 18, 0, tzinfo=UTC)
FAKE = str(Path(__file__).resolve().parents[2] / "fakes" / "mcp_server.py")
SECRET = "sk-secret-value-1234"
YOU = Actor(kind="user", via="console")


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, tmp_path: Path, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.chdir(project)
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, FakeClock(NOW), registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[Server]:
    """In place of the check that starts a server: each server it was given (it answers with one tool)."""
    found: list[Server] = []

    def check(server: Server, seconds: float = 30.0) -> Checked:
        found.append(server)
        return Checked("myproject-mcp", "0.1", "2025-06-18", [Tool("run", "Runs it.")])

    monkeypatch.setattr(tools_service, "check", check)
    return found


def declare(entry: dict[str, object]) -> None:
    """This folder's .mcp.json, declaring `myproject` with this entry."""
    (Path.cwd() / ".mcp.json").write_text(json.dumps({"mcpServers": {"myproject": entry}}), encoding="utf-8")


def message(app: ClankConsole) -> str:
    return str(app.query_one("#message", Label).content)


@pytest.fixture
def served(kernel: Kernel) -> Iterator[Client]:
    with live_service(kernel) as client:
        yield client


def page_text(app: ClankConsole) -> str:
    return "\n".join(str(label.content) for label in app.query("#page-tools Label").results(Label))


def rows(app: ClankConsole) -> list[str]:
    return [row["name"] for row in app.query_one(McpServersPage).rows]


async def test_the_page_lists_adds_checks_and_removes_servers(kernel: Kernel, served: Client) -> None:
    entry = {"command": sys.executable, "args": [FAKE], "env": {"FAKE_MCP_TOKEN": SECRET}}
    served.post("mcp/servers", {"name": "fake", "scope": "user", "folder": str(Path.cwd()), "entry": entry})
    app = ClankConsole(served, now=lambda: NOW, zone=UTC, home=kernel.home, page="tools")
    async with app.run_test(size=(140, 44)) as pilot:
        await settle(pilot, lambda: "fake" in page_text(app), seconds=20)
        assert "This folder is not a workspace yet" in page_text(app)
        listed = app.query_one("#mcp-list", ListView)
        await focus_on(pilot, app, listed, 0)
        await settle(pilot, lambda: "FAKE_MCP_TOKEN (ends in 1234)" in page_text(app))
        assert "not checked yet: c checks it" in page_text(app)
        assert SECRET not in page_text(app)
        assert app.query_one("#mcp-detail-panel", Panel).title == "Details · fake"

        await pilot.press("a")
        await settle(pilot, lambda: isinstance(app.screen, FormScreen))
        app.screen.query_one("#form-name", Input).value = "added"
        app.screen.query_one("#form-command", Input).value = "x-mcp --flag 'two words'"
        app.screen.query_one("#form-env", Input).value = "MODE=fast"
        await pilot.press("ctrl+s")
        await settle(pilot, lambda: "added" in rows(app), seconds=20)
        assert kernel.parts["tools"].server("added")["args"] == ["--flag", "two words"]
        await focus_on(pilot, app, listed, rows(app).index("added"))
        await settle(pilot, lambda: "x-mcp --flag 'two words'" in page_text(app))

        await focus_on(pilot, app, listed, rows(app).index("fake"))
        await pilot.press("c")
        await settle(pilot, lambda: "fake-mcp 1.2.3, checked" in page_text(app), seconds=60)
        line = str(listed.highlighted_child.query_one(Label).content) if listed.highlighted_child else ""
        assert line.split()[-1] == "2", "its row counts its tools"
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, ToolsScreen))
        shown = "\n".join(str(label.content) for label in app.screen.query(Label))
        assert "Adds two numbers (the token reached it)." in shown
        assert "a               number, required  The first." in shown
        await pilot.press("escape")

        await pilot.press("s")
        await settle(
            pilot, lambda: "open this folder as a workspace first" in str(app.query_one("#message", Label).content)
        )

        await focus_on(pilot, app, listed, rows(app).index("added"))
        await pilot.press("d")
        await settle(pilot, lambda: isinstance(app.screen, PickScreen))
        await pilot.press("enter")  # the first choice: remove
        await settle(pilot, lambda: rows(app) == ["fake"], seconds=20)


async def test_a_folders_own_server_is_not_checked_on_this_computer_when_the_folder_is_no_workspace(
    kernel: Kernel, served: Client, started: list[Server]
) -> None:
    declare({"command": "myproject-mcp"})
    app = ClankConsole(served, now=lambda: NOW, zone=UTC, home=kernel.home, page="tools")
    async with app.run_test(size=(140, 44)) as pilot:
        await settle(pilot, lambda: "myproject" in rows(app), seconds=20)
        await focus_on(pilot, app, app.query_one("#mcp-list", ListView), rows(app).index("myproject"))
        await pilot.press("c")
        await settle(pilot, lambda: "never on this computer" in message(app))
        assert "myproject is this folder's own (.mcp.json)" in message(app)
        assert "open this folder as a workspace first (F4, then o)" in message(app)
    assert started == [], "nothing was started"


async def test_a_folders_own_server_changed_since_it_was_allowed_says_so_and_is_checked_in_the_container(
    kernel: Kernel, served: Client, platform: FakePlatform, started: list[Server]
) -> None:
    declare({"command": "myproject-mcp"})
    kernel.settings.write("workspace", "project", {"path": str(Path.cwd())}, base=None, actor=YOU)
    box = names(kernel.home.id).container("project")
    platform.containers.append(container(box, labels={"clank.home": kernel.home.id}))
    kernel.parts["agents"].allow("project", "myproject", True, actor=YOU)
    declare({"command": "myproject-mcp", "args": ["--other"]})
    app = ClankConsole(served, now=lambda: NOW, zone=UTC, home=kernel.home, page="tools")
    async with app.run_test(size=(140, 44)) as pilot:
        await settle(pilot, lambda: "myproject" in rows(app), seconds=20)
        await focus_on(pilot, app, app.query_one("#mcp-list", ListView), rows(app).index("myproject"))
        await settle(pilot, lambda: "its entry changed since you allowed it" in page_text(app))
        await pilot.press("c")
        await settle(pilot, lambda: "answers, with 1 tools" in message(app), seconds=30)
        assert "changed since you allowed it" in message(app)
    assert [server.args[-3:] for server in started] == [[box, "myproject-mcp", "--other"]], "in its container"
