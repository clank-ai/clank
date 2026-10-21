"""Design 0004 §1 and design 0002 §2.15: `clank workspace open [FOLDER]` (this folder unless one is named) follows the
operation and says where its container runs; `clank workspace list` shows each workspace with its container's state;
`clank workspace stop [NAME]` (this folder's workspace unless one is named) and `clank workspace remove NAME` follow
theirs; the routes start the operations and list the workspaces."""

from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner, Result
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import names
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def http(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with TestClient(create_app(kernel, token="t", port=7726), base_url="http://127.0.0.1:7726") as client:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7726", "t", name="cli", http=client))
        yield client


def run(*arguments: str) -> Result:
    return CliRunner().invoke(main, list(arguments))


def test_the_workspace_commands_open_list_stop_and_remove(
    kernel: Kernel, http: TestClient, platform: FakePlatform, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    monkeypatch.chdir(folder)
    container = names(kernel.home.id).container("paper")
    opened = run("workspace", "open", "--yes")
    assert opened.exit_code == 0, opened.output
    assert f"paper: its container runs ({container}), with {folder} at /workspace" in opened.output
    listed = run("workspace", "list")
    assert listed.exit_code == 0, listed.output
    assert f"paper  running  {folder}" in listed.output
    stopped = run("workspace", "stop")
    assert stopped.exit_code == 0, stopped.output
    assert f"paper: {container} stopped" in stopped.output
    assert "paper  exited" in run("workspace", "list").output
    removed = run("workspace", "remove", "paper", "--yes")
    assert removed.exit_code == 0, removed.output
    assert f"paper is removed; {folder} is as it was" in removed.output
    assert "No workspace yet" in run("workspace", "list").output
    assert folder.is_dir()


def test_the_setup_command_installs_the_folders_software_and_says_with_what(
    kernel: Kernel, http: TestClient, platform: FakePlatform, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design 0004 §10: `clank workspace setup [FOLDER] [--command TEXT] [--yes]`."""
    folder = tmp_path / "paper"
    folder.mkdir()
    (folder / "requirements.txt").write_text("numpy\n", encoding="utf-8")
    monkeypatch.chdir(folder)
    assert run("workspace", "open", "--yes").exit_code == 0
    installed = run("workspace", "setup", "--yes")
    assert installed.exit_code == 0, installed.output
    assert "paper: installed with python3 -m venv ~/.venv && ~/.venv/bin/python -m pip install -r requirements.txt" in (
        installed.output
    )
    platform.setup_status = 2
    failed = run("workspace", "setup", "--command", "make env", "--yes")
    assert failed.exit_code == 1
    assert "the setup did not finish (exit 2)" in failed.output
    assert kernel.settings.get("workspace", "paper").record.model_dump()["setup"] == "make env"


def test_a_command_on_a_workspace_that_is_not_there_says_which_there_are(http: TestClient, tmp_path: Path) -> None:
    missing = run("workspace", "remove", "nothing-like-it", "--yes")
    assert missing.exit_code == 1
    assert "there is no workspace 'nothing-like-it'" in missing.output
    elsewhere = run("workspace", "open", str(tmp_path / "not-there"), "--yes")
    assert elsewhere.exit_code == 1
    assert "is not a folder" in elsewhere.output


def test_the_routes_list_the_workspaces_with_their_containers_state(
    kernel: Kernel, http: TestClient, platform: FakePlatform, tmp_path: Path
) -> None:
    auth = {"Authorization": "Bearer t", "X-Clank-Client": "test"}
    assert http.get("/api/v1/workspaces", headers=auth).json() == []
    kernel.settings.write(
        "workspace", "notes", {"path": str(tmp_path)}, base=None, actor=Actor(kind="user", via="console")
    )
    [row] = http.get("/api/v1/workspaces", headers=auth).json()
    assert (row["name"], row["path"], row["state"]) == ("notes", str(tmp_path), "not made")
    assert row["container"] == names(kernel.home.id).container("notes")
    platform.state = "stopped"
    assert http.get("/api/v1/workspaces", headers=auth).json()[0]["state"] == "Docker is stopped"
