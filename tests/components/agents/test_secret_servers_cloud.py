"""Design 0016 §9 and design 0002 §2.8 (decision 0168): allowing a workspace the cloud model names first each of your
MCP servers with secrets its agent gets, and says its agent can read their values and a model at a provider will be
able to read them too: in the words said before the bound is changed (`cloud_confirm`, which `clank workspace allow
--cloud` and the console's `u` show) and in the question asked once. A server marked local only (which never goes with
the cloud) or held back is not named. Giving such a server to a workspace while its cloud question waits asks first,
as for a workspace that may use a cloud model, so either order asks the owner before the values can reach a cloud
model."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.agents.service import Agents, Unconfirmed
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.service import Workspaces
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

YOU = Actor(kind="user", via="console")
READS = "a model at a provider will be able to read"
CLOUD_MAIN = {"status": "ready", "provider": "endpoint", "endpoint": "openrouter", "title": "cloud: Example Coder",
              "preset": "cloud-example-coder"}  # fmt: skip


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    tools = kernel.parts["tools"]
    tools.add("notes", {"command": "notes-mcp", "env": {"KEY": "k1"}}, scope="user", folder="", actor=YOU)
    tools.add("db", {"command": "db-mcp", "env": {"PASSWORD": "p1", "USER": "u1"}}, scope="user", folder="", actor=YOU)
    tools.add("plain", {"command": "plain-mcp"}, scope="user", folder="", actor=YOU)
    tools.add("diary", {"command": "diary-mcp", "env": {"TOKEN": "t1"}}, scope="user", folder="", actor=YOU,
              local_only=True)  # fmt: skip
    yield kernel
    kernel.close()


def opened(kernel: Kernel, folder: Path, name: str = "paper") -> None:
    folder.mkdir(exist_ok=True)
    kernel.settings.write("workspace", name, {"path": str(folder)}, base=None, actor=YOU)


def allow_words(kernel: Kernel, workspace: str) -> str:
    found: Workspaces = kernel.parts["workspaces"]
    return str(found.cloud_view(workspace)["cloud_confirm"]["allow"])


def main_runs_a_cloud_model(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = kernel.parts["gateway"]
    real = gateway.routes

    def routes() -> dict[str, Any]:
        return {**real(), "slots": {"main": CLOUD_MAIN}}

    monkeypatch.setattr(gateway, "routes", routes)


def row(kernel: Kernel, workspace: str, name: str) -> dict[str, Any]:
    agents: Agents = kernel.parts["agents"]
    return next(each for each in agents.servers(workspace) if each["name"] == name)


def test_allowing_the_cloud_names_the_servers_with_secrets_its_agent_gets(kernel: Kernel, tmp_path: Path) -> None:
    opened(kernel, tmp_path / "paper")
    opened(kernel, tmp_path / "other", "other")
    agents: Agents = kernel.parts["agents"]
    for name in ("notes", "db", "diary"):
        agents.allow("paper", name, True, actor=YOU)  # on this machine: nothing asked yet
    words = allow_words(kernel, "paper")
    assert "paper's agent gets your MCP servers with secrets db (PASSWORD, USER) and notes (KEY)" in words
    assert "and can read their values: with the cloud model" in words
    assert READS in words
    assert "diary" not in words, "marked local only: it never goes with the cloud"
    assert "plain" not in words, "no secrets"
    assert "with secrets" not in allow_words(kernel, "other"), "nothing given to it, nothing said"
    agents.allow("paper", "db", False, actor=YOU)
    assert "your MCP server with secrets notes (KEY)" in allow_words(kernel, "paper"), "held back: not named"
    assert "db" not in allow_words(kernel, "paper")


def test_clank_workspace_allow_cloud_says_so_before_it_changes_anything(
    kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "paper"
    opened(kernel, folder)
    kernel.parts["agents"].allow("paper", "notes", True, actor=YOU)
    with TestClient(create_app(kernel, token="t", port=7732), base_url="http://127.0.0.1:7732") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7732", "t", name="cli", http=http))
        kept = CliRunner().invoke(main, ["workspace", "allow", str(folder), "--cloud"], input="n\n")
    assert kept.exit_code == 1
    assert "your MCP server with secrets notes (KEY)" in kept.output
    assert READS in kept.output
    assert kernel.settings.get("workspace", "paper").record.model_dump()["models"] == "this-machine"


def test_the_cloud_question_names_them_too(kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    opened(kernel, tmp_path / "paper")
    kernel.parts["agents"].allow("paper", "notes", True, actor=YOU)
    main_runs_a_cloud_model(kernel, monkeypatch)
    workspaces: Workspaces = kernel.parts["workspaces"]
    asked = workspaces.ask_cloud("paper")
    question = kernel.questions.get(asked["question"])
    assert "paper's agent gets your MCP server with secrets notes (KEY)" in question.detail
    assert READS in question.detail
    assert "k1" not in question.detail


def test_giving_one_while_the_cloud_question_waits_asks_first(
    kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened(kernel, tmp_path / "paper")
    main_runs_a_cloud_model(kernel, monkeypatch)
    workspaces: Workspaces = kernel.parts["workspaces"]
    asked = workspaces.ask_cloud("paper")
    assert asked["needed"] is True
    confirm = str(row(kernel, "paper", "notes")["confirm"])
    assert "paper's agent can read them" in confirm
    assert "paper is asked whether it may use a cloud model" in confirm
    assert READS in confirm
    agents: Agents = kernel.parts["agents"]
    with pytest.raises(Unconfirmed):
        agents.allow("paper", "notes", True, actor=YOU)
    assert row(kernel, "paper", "diary")["confirm"] == "", "local only: it would not go with the cloud"
    agents.allow("paper", "notes", True, actor=YOU, confirm=True)
    assert row(kernel, "paper", "notes")["given"] is True
    kernel.questions.answer(asked["question"], by=YOU, option="local")
    agents.allow("paper", "db", True, actor=YOU)  # kept on this machine now: nothing to ask
    assert row(kernel, "paper", "db")["given"] is True
