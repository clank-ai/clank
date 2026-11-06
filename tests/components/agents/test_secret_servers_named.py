"""Design 0004 §10 and design 0002 §2.8 (decision 0168): one of your MCP servers that carries secret values (an
environment variable or a header) goes only to the workspaces you name for it, kept in the workspace's record
(`mcp_secrets`, readable in its settings file) and set by `clank mcp allow` and `clank mcp hold`; your servers without
secrets go to every workspace unless held back, as before. Giving one to a workspace that may use a cloud model asks
first, in the service's words: its agent can read the values, and a model at a provider will be able to read what the
agent reads. The service refuses it without that confirmation (409 `unconfirmed`); `clank mcp allow` asks in the
terminal, `--yes` answering it."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.agents.service import Agents, Unconfirmed
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import names
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform, container

YOU = Actor(kind="user", via="console")
CONFIG = "/home/agent/.config/opencode/opencode.json"
READS = "a model at a provider will be able to read what the agent reads"


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    kernel.parts["tools"].add("notes", {"command": "notes-mcp", "env": {"KEY": "k1-value"}}, scope="user",
                              folder="", actor=YOU)  # fmt: skip
    kernel.parts["tools"].add("plain", {"command": "plain-mcp"}, scope="user", folder="", actor=YOU)
    yield kernel
    kernel.close()


def opened(kernel: Kernel, platform: FakePlatform, folder: Path, name: str = "paper", **values: object) -> str:
    """The folder's workspace, its container running."""
    folder.mkdir(exist_ok=True)
    kernel.settings.write("workspace", name, {"path": str(folder), **values}, base=None, actor=YOU)
    box = names(kernel.home.id).container(name)
    platform.containers.append(container(box, labels={"clank.home": kernel.home.id}))
    return box


def row(kernel: Kernel, workspace: str, name: str) -> dict[str, object]:
    agents: Agents = kernel.parts["agents"]
    return next(each for each in agents.servers(workspace) if each["name"] == name)


def test_a_server_of_yours_with_secrets_goes_only_to_the_workspaces_that_name_it(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    paper = opened(kernel, platform, tmp_path / "paper")
    other = opened(kernel, platform, tmp_path / "other", name="other")
    agents: Agents = kernel.parts["agents"]
    notes = row(kernel, "paper", "notes")
    assert notes["given"] is False
    assert notes["why"] == (
        "it carries secret values (KEY): only the workspaces you name get it, and their agent can read them "
        "(m gives it)"
    )
    assert row(kernel, "paper", "plain")["given"] is True, "one without secrets goes to every workspace, as before"

    agents.allow("paper", "notes", True, actor=YOU)
    assert kernel.settings.get("workspace", "paper").record.model_dump()["mcp_secrets"] == ["notes"]
    written = json.loads((kernel.home.config / "workspaces" / "paper.json").read_text(encoding="utf-8"))
    assert written["mcp_secrets"] == ["notes"], "readable in the workspace's settings file"
    assert row(kernel, "paper", "notes")["given"] is True
    assert row(kernel, "other", "notes")["given"] is False, "named for paper alone"
    agents.prepare("paper")
    assert "notes" in json.loads(platform.files[(paper, CONFIG)])["mcp"]
    prepared = agents.prepare("other")
    assert "notes" not in json.loads(platform.files[(other, CONFIG)])["mcp"]
    assert not any(key.startswith("CLANK_MCP_NOTES") for key in prepared["env"]), "nor its values"

    agents.allow("paper", "notes", False, actor=YOU)
    assert kernel.settings.get("workspace", "paper").record.model_dump()["mcp_secrets"] == []
    assert row(kernel, "paper", "notes")["given"] is False


def test_giving_one_to_a_workspace_that_may_use_a_cloud_model_asks_first(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    opened(kernel, platform, tmp_path / "paper", models="cloud")
    agents: Agents = kernel.parts["agents"]
    confirm = str(row(kernel, "paper", "notes")["confirm"])
    assert "paper's agent can read them" in confirm
    assert READS in confirm
    with pytest.raises(Unconfirmed, match=READS):
        agents.allow("paper", "notes", True, actor=YOU)
    assert kernel.settings.get("workspace", "paper").record.model_dump()["mcp_secrets"] == [], "nothing changed"
    agents.allow("paper", "notes", True, actor=YOU, confirm=True)
    assert row(kernel, "paper", "notes")["given"] is True
    assert row(kernel, "paper", "notes")["confirm"] == "", "given already: nothing more to ask"
    assert row(kernel, "paper", "plain")["confirm"] == "", "a server without secrets is not asked about"


def test_the_service_refuses_it_unconfirmed_and_clank_mcp_allow_asks_in_the_terminal(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "paper"
    opened(kernel, platform, folder, models="cloud")
    monkeypatch.chdir(folder)
    with TestClient(create_app(kernel, token="t", port=7728), base_url="http://127.0.0.1:7728") as http:
        headers = {"Authorization": "Bearer t"}
        refused = http.post("/api/v1/agents/servers", json={"workspace": "paper", "name": "notes"}, headers=headers)
        assert refused.status_code == 409
        assert refused.json()["error"]["code"] == "unconfirmed"
        assert READS in refused.json()["error"]["message"]

        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7728", "t", name="cli", http=http))
        kept = CliRunner().invoke(main, ["mcp", "allow", "notes"], input="n\n")
        assert kept.exit_code == 1, kept.output
        assert READS in kept.output
        assert "paper's agent does not get notes" in kept.output
        assert row(kernel, "paper", "notes")["given"] is False

        given = CliRunner().invoke(main, ["mcp", "allow", "notes"], input="y\n")
        assert given.exit_code == 0, given.output
        assert "paper's agent gets notes (notes-mcp) when it next starts; it can read its secret values (KEY)" in (
            given.output
        )
        CliRunner().invoke(main, ["mcp", "hold", "notes"])
        assert row(kernel, "paper", "notes")["given"] is False
        unasked = CliRunner().invoke(main, ["mcp", "allow", "notes", "--yes"])
        assert unasked.exit_code == 0, unasked.output
        assert READS not in unasked.output, "--yes answers it"
        assert row(kernel, "paper", "notes")["given"] is True


def test_a_server_removed_is_named_by_no_workspace_so_one_added_again_under_its_name_goes_nowhere_unasked(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    opened(kernel, platform, tmp_path / "paper")
    opened(kernel, platform, tmp_path / "other", name="other")
    agents: Agents = kernel.parts["agents"]
    tools = kernel.parts["tools"]
    agents.allow("paper", "notes", True, actor=YOU)
    agents.allow("other", "notes", True, actor=YOU)
    agents.allow("other", "plain", False, actor=YOU)
    tools.remove("notes", scope="user", folder="", actor=YOU)
    for workspace in ("paper", "other"):
        assert kernel.settings.get("workspace", workspace).record.model_dump()["mcp_secrets"] == []
    tools.add("notes", {"command": "other-mcp", "env": {"KEY": "k2-value"}}, scope="user", folder="", actor=YOU)
    assert row(kernel, "paper", "notes")["given"] is False, "a new server: given to no workspace until you give it"
    assert row(kernel, "other", "notes")["given"] is False
    assert kernel.settings.get("workspace", "other").record.model_dump()["mcp_off"] == ["plain"], "a hold stays"
