"""Design 0004 §10: a folder's own MCP server (its `.mcp.json`) is checked only in the folder's workspace container,
never on this computer. The service finds the folder's workspace itself; with no workspace for the folder, its
container not running, another folder's workspace named, or a server reached by address, the check is refused, saying
how to check it, and nothing is started. A check of a folder's server says whether the workspace's agent may use it as
it is now: not allowed yet, allowed, or changed since it was allowed (its command, its arguments or its environment),
which counts as not allowed until it is allowed again; `clank mcp check` prints it. Your own servers are checked on this
computer as before.

Design 0002 §2.8: the `docker exec` that starts it names each variable alone, its value in docker's environment."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common, follow
from clank.cli.main import main
from clank.client import Client
from clank.components.tools import service as tools_service
from clank.components.tools.mcp import Checked, Server, Tool
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import names
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform, container

YOU = Actor(kind="user", via="cli")
ENTRY = {"command": "myproject-mcp", "args": ["--quiet"], "env": {"MODE": "fast"}}


class Runner:
    """In place of the check that starts or reaches a server: each server it was given, and the same answer."""

    def __init__(self) -> None:
        self.started: list[Server] = []

    def __call__(self, server: Server, seconds: float = 30.0) -> Checked:
        self.started.append(server)
        return Checked("myproject-mcp", "0.1", "2025-06-18", [Tool("run", "Runs it.")])


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> Runner:
    found = Runner()
    monkeypatch.setattr(tools_service, "check", found)
    return found


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def declare(folder: Path, entry: dict[str, Any]) -> None:
    """The folder's .mcp.json, declaring `myproject` with this entry."""
    (folder / ".mcp.json").write_text(json.dumps({"mcpServers": {"myproject": entry}}), encoding="utf-8")


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    found = tmp_path / "paper"
    found.mkdir()
    declare(found, ENTRY)
    return found


def opened(kernel: Kernel, platform: FakePlatform, folder: Path, name: str = "paper", state: str = "running") -> str:
    """The folder's workspace, with its container in this state; the container's name."""
    kernel.settings.write("workspace", name, {"path": str(folder)}, base=None, actor=YOU)
    found = names(kernel.home.id).container(name)
    platform.containers.append(container(found, state=state, labels={"clank.home": kernel.home.id}))
    return found


async def checked(kernel: Kernel, name: str = "myproject", **params: str) -> Any:
    """A check, followed to its end."""
    async with kernel.operations.running():
        started = await kernel.operations.start("mcp.check", {"name": name, **params}, actor=YOU)
        with anyio.fail_after(30):
            return await kernel.operations.wait(started.id)


@pytest.mark.anyio
async def test_a_folders_server_is_not_checked_on_this_computer_when_the_folder_is_no_workspace(
    kernel: Kernel, folder: Path, runner: Runner
) -> None:
    for scope in ("", "project"):
        done = await checked(kernel, folder=str(folder), scope=scope)
        assert done.status == "failed"
        assert "only in the folder's workspace container, never on this computer" in done.error
        assert "is no workspace yet: `clank workspace open` makes it one" in done.error
    assert runner.started == [], "nothing was started"


@pytest.mark.anyio
async def test_a_folders_server_is_not_checked_while_its_workspaces_container_does_not_run(
    kernel: Kernel, platform: FakePlatform, folder: Path, runner: Runner
) -> None:
    opened(kernel, platform, folder, state="exited")
    done = await checked(kernel, folder=str(folder))
    assert done.status == "failed"
    assert "never on this computer" in done.error
    assert "paper's container does not run: `clank workspace open` starts it" in done.error
    assert runner.started == [], "nothing was started"


@pytest.mark.anyio
async def test_a_folders_server_is_checked_in_its_workspaces_running_container_whether_it_is_named_or_not(
    kernel: Kernel, platform: FakePlatform, folder: Path, runner: Runner
) -> None:
    box = opened(kernel, platform, folder)
    for named in ("", "paper"):
        done = await checked(kernel, folder=str(folder), workspace=named)
        assert done.status == "done", done.error
    assert len(runner.started) == 2
    for server in runner.started:
        assert (server.command, server.args[:2]) == ("docker", ["exec", "--interactive"])
        assert server.args[-3:] == [box, "myproject-mcp", "--quiet"], "its own command, in the container"
        assert server.args[server.args.index("MODE") - 1] == "--env", "its environment named for the container"
        assert server.env["MODE"] == "fast", "design 0002 §2.8: the value in docker's environment, not its arguments"
        assert not any("fast" in part for part in server.args)
    remembered = kernel.parts["tools"].checked("myproject", "project", str(folder))
    assert remembered is not None
    assert remembered["where"] == "paper's container"


@pytest.mark.anyio
async def test_a_folders_server_is_checked_in_its_own_folders_workspace_alone(
    kernel: Kernel, platform: FakePlatform, folder: Path, tmp_path: Path, runner: Runner
) -> None:
    opened(kernel, platform, folder)
    other = tmp_path / "other"
    other.mkdir()
    opened(kernel, platform, other, name="other")
    done = await checked(kernel, folder=str(folder), workspace="other")
    assert done.status == "failed"
    assert "other is not this folder's workspace: check it in paper" in done.error
    assert runner.started == [], "nothing was started"


@pytest.mark.anyio
async def test_a_folders_server_reached_by_address_is_not_checked(
    kernel: Kernel, platform: FakePlatform, folder: Path, runner: Runner
) -> None:
    declare(folder, {"type": "http", "url": "http://127.0.0.1:9/mcp"})
    opened(kernel, platform, folder)
    done = await checked(kernel, folder=str(folder))
    assert done.status == "failed"
    assert "reached by address" in done.error
    assert runner.started == [], "nothing was reached"


@pytest.mark.anyio
async def test_a_check_says_whether_the_workspaces_agent_may_use_a_folders_server_as_it_is_now(
    kernel: Kernel, platform: FakePlatform, folder: Path, runner: Runner
) -> None:
    opened(kernel, platform, folder)
    agents = kernel.parts["agents"]
    first = (await checked(kernel, folder=str(folder))).result
    assert first["allowed"] is False
    assert first["allowed_said"].startswith("not allowed for paper's agent yet")
    agents.allow("paper", "myproject", True, actor=YOU)
    allowed = (await checked(kernel, folder=str(folder))).result
    assert (allowed["allowed"], allowed["allowed_said"]) == (True, "allowed for paper's agent as it is now")
    for changed in ({**ENTRY, "command": "other-mcp"}, {**ENTRY, "args": ["--loud"]}, {**ENTRY, "env": {"MODE": "x"}}):
        declare(folder, changed)
        result = (await checked(kernel, folder=str(folder))).result
        assert result["allowed"] is False, changed
        assert "changed since you allowed it" in result["allowed_said"]
        row = next(row for row in agents.servers("paper") if row["name"] == "myproject")
        assert row["given"] is False, "the agent does not get it either"
    agents.allow("paper", "myproject", True, actor=YOU)
    assert (await checked(kernel, folder=str(folder))).result["allowed"] is True, "allowed again, as it is now"


@pytest.mark.anyio
async def test_your_own_servers_are_still_checked_on_this_computer(
    kernel: Kernel, folder: Path, runner: Runner
) -> None:
    kernel.parts["tools"].add("notes", {"command": "notes-mcp"}, scope="user", folder="", actor=YOU)
    done = await checked(kernel, name="notes", folder=str(folder))
    assert done.status == "done", done.error
    assert runner.started == [Server("stdio", command="notes-mcp")]
    assert "allowed" not in (done.result or {}), "yours need no allowing"


def test_clank_mcp_check_refuses_a_folders_server_without_its_workspace_and_says_whether_it_is_allowed(
    kernel: Kernel, platform: FakePlatform, folder: Path, runner: Runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(follow, "POLL_SECONDS", 0.005)
    monkeypatch.chdir(folder)
    with TestClient(create_app(kernel, token="t", port=7729), base_url="http://127.0.0.1:7729") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7729", "t", name="cli", http=http))
        refused = CliRunner().invoke(main, ["mcp", "check", "myproject"])
        assert refused.exit_code == 1
        assert "never on this computer" in refused.output
        assert "`clank workspace open` makes it one" in refused.output
        assert runner.started == [], "nothing was started"
        opened(kernel, platform, folder)
        done = CliRunner().invoke(main, ["mcp", "check", "myproject"])
        assert done.exit_code == 0, done.output
        assert "myproject: myproject-mcp 0.1, protocol 2025-06-18, 1 tools" in done.output
        assert "myproject: not allowed for paper's agent yet: `clank mcp allow myproject`" in done.output
