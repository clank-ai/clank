"""Design 0004 §10 and design 0002 §2.8 (decision 0168): one of your MCP servers that carries secret values is started
in a workspace's container, for its check, only when that workspace gets it (its record names it, `mcp_secrets`): its
values go only to the workspaces you give it to. Checked in another workspace, the check is refused before any value is
read, saying how to check it (on this computer, or after giving it to the workspace), and nothing is started; `clank
mcp check NAME --workspace` prints it. On this computer it is checked as before, and one without secrets is checked in
any workspace's container."""

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
VALUE = "k1-secret-value"


class Runner:
    """In place of the check that starts a server: each server it was given, and the same answer."""

    def __init__(self) -> None:
        self.started: list[Server] = []

    def __call__(self, server: Server, seconds: float = 30.0) -> Checked:
        self.started.append(server)
        return Checked("notes-mcp", "0.1", "2025-06-18", [Tool("read", "Reads a note.")])


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
    kernel.parts["tools"].add("notes", {"command": "notes-mcp", "env": {"KEY": VALUE}}, scope="user", folder="",
                              actor=YOU)  # fmt: skip
    kernel.parts["tools"].add("plain", {"command": "plain-mcp"}, scope="user", folder="", actor=YOU)
    yield kernel
    kernel.close()


def opened(kernel: Kernel, platform: FakePlatform, folder: Path, name: str = "paper") -> str:
    """The folder's workspace, its container running; the container's name."""
    folder.mkdir(exist_ok=True)
    kernel.settings.write("workspace", name, {"path": str(folder)}, base=None, actor=YOU)
    found = names(kernel.home.id).container(name)
    platform.containers.append(container(found, labels={"clank.home": kernel.home.id}))
    return found


async def checked(kernel: Kernel, name: str, **params: str) -> Any:
    """A check, followed to its end."""
    async with kernel.operations.running():
        started = await kernel.operations.start("mcp.check", {"name": name, **params}, actor=YOU)
        with anyio.fail_after(30):
            return await kernel.operations.wait(started.id)


def read_for_a_check(kernel: Kernel) -> list[str]:
    """The secret values read for a check, by name."""
    used = kernel.events.latest(1000, types=["secret.used"])
    return [str(event.data["name"]) for event in used if event.data.get("why") == "a check"]


@pytest.mark.anyio
async def test_one_of_yours_with_secrets_is_not_started_in_a_workspace_that_does_not_get_it(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path, runner: Runner
) -> None:
    opened(kernel, platform, tmp_path / "paper")
    opened(kernel, platform, tmp_path / "other", name="other")
    kernel.parts["agents"].allow("other", "notes", True, actor=YOU)
    done = await checked(kernel, "notes", workspace="paper")
    assert done.status == "failed"
    assert "notes carries secret values (KEY), which go only to the workspaces you give it to" in done.error
    assert "paper does not get it" in done.error
    assert "check it on this computer" in done.error
    assert "`clank mcp allow notes`" in done.error
    assert runner.started == [], "nothing was started"
    assert read_for_a_check(kernel) == [], "no value was read"


@pytest.mark.anyio
async def test_it_is_checked_in_the_containers_of_the_workspaces_given_it_and_on_this_computer(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path, runner: Runner
) -> None:
    box = opened(kernel, platform, tmp_path / "paper")
    kernel.parts["agents"].allow("paper", "notes", True, actor=YOU)
    given = await checked(kernel, "notes", workspace="paper")
    assert given.status == "done", given.error
    [inside] = runner.started
    assert (inside.command, inside.args[-2:]) == ("docker", [box, "notes-mcp"])
    assert inside.args[inside.args.index("KEY") - 1] == "--env", "named alone (design 0002 §2.8)"
    assert inside.env["KEY"] == VALUE
    here = await checked(kernel, "notes")
    assert here.status == "done", here.error
    assert runner.started[-1] == Server("stdio", command="notes-mcp", env={"KEY": VALUE}), "on this computer"
    plain = await checked(kernel, "plain", workspace="paper")
    assert plain.status == "done", "one without secrets is checked in any workspace's container"


def test_clank_mcp_check_with_workspace_says_why_it_is_refused(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path, runner: Runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "paper"
    opened(kernel, platform, folder)
    monkeypatch.setattr(follow, "POLL_SECONDS", 0.005)
    monkeypatch.chdir(folder)
    with TestClient(create_app(kernel, token="t", port=7731), base_url="http://127.0.0.1:7731") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7731", "t", name="cli", http=http))
        refused = CliRunner().invoke(main, ["mcp", "check", "notes", "--workspace"])
        assert refused.exit_code == 1
        assert "paper does not get it" in refused.output
        assert runner.started == [], "nothing was started"
        here = CliRunner().invoke(main, ["mcp", "check", "notes"])
        assert here.exit_code == 0, here.output
        assert "notes: notes-mcp 0.1, protocol 2025-06-18, 1 tools" in here.output
