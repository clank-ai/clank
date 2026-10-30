"""Design 0028 §4 and design 0002 §2.15: `clank setup --check` prints the checklist, each item with its state and what
to do about it, and changes nothing; it exits 0 when everything required is done, else 1. It works with or without the
service: with it, the checklist is the service's (`GET /setup`); without it, Docker is read here through the platform,
as the doctor reads it, and the model and the folder are said to be told once the service runs. The folder it was
started in is checked as a workspace's would be. `--json` prints the checklist as the API gives it."""

import json
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
from clank.components.agents import checklist, vscode
from clank.components.runtime.state import LastGood
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import image_tag
from clank.kernel.access import client_actor
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
YOU = client_actor("cli")


@pytest.fixture
def platform() -> FakePlatform:
    """Docker running, nothing of Clank's built yet."""
    return FakePlatform()


@pytest.fixture(autouse=True)
def this_computer(platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> None:
    """The platform the settings choose is the fake one; no VS Code and no installer's tool are found."""
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    monkeypatch.setattr(workspaces_service, "WAIT_SECONDS", 0.001)
    monkeypatch.setattr(vscode, "which", lambda name: None)
    monkeypatch.setattr(checklist, "found_tools", lambda: frozenset())
    monkeypatch.setattr(follow, "POLL_SECONDS", 0.005)


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The folder `clank setup` is started in: a project's folder."""
    folder = tmp_path / "paper"
    folder.mkdir()
    monkeypatch.chdir(folder)
    return folder


@pytest.fixture
def kernel(home: Home, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    """The service, served in the test; the commands its clients."""
    kernel = open_kernel(home, FakeClock(NOW), registry.components())
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7720", "t", name="cli", http=http))
        yield kernel
    kernel.close()


def run(home: Home, *arguments: str, input: str | None = None, columns: int = 200) -> Result:
    environ = {"CLANK_HOME": str(home.root), "COLUMNS": str(columns)}
    return CliRunner().invoke(main, ["setup", *arguments], input=input, env=environ)


def lines_of(shown: Result) -> dict[str, str]:
    """Each item's line, by its title, as printed."""
    titles = ["Docker installed", "Docker running", "Docker usable by this account", "Clank's service",
              "The sandbox image", "A model", "A folder", "Clank's VS Code window"]  # fmt: skip
    found = {}
    for line in shown.output.splitlines():
        for title in titles:
            if title in line and title not in found:
                found[title] = line
    return found


def everything_done(kernel: Kernel, platform: FakePlatform, folder: Path) -> None:
    """The image built, a preset that answered a test request, and a workspace."""
    platform.images.add(image_tag())
    kernel.parts["runtime"].state.remember_good("main", LastGood(preset="daily-262k", time=NOW))
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)


def test_without_the_service_it_reads_docker_itself_and_says_what_only_the_service_can_tell(
    home: Home, project: Path
) -> None:
    shown = run(home, "--check")
    assert shown.exit_code == 1, shown.output
    lines = lines_of(shown)
    assert lines["Docker installed"].split()[:2] == ["✓", "done"]
    assert "Fake Docker 4.85.0" in lines["Docker installed"]
    assert lines["Clank's service"].split()[:3] == ["•", "to", "do"]
    for title in ("A model", "A folder"):
        assert lines[title].split()[:2] == ["?", "unknown"]
        assert "Clank's service tells this once it runs" in lines[title]
    assert "→ start it: `clank serve --background`" in shown.output
    assert "Nothing was changed." in shown.output


def test_check_changes_nothing(home: Home, project: Path, platform: FakePlatform) -> None:
    platform.state = "stopped"
    before = sorted(path.relative_to(home.root) for path in home.root.rglob("*"))
    shown = run(home, "--check")
    assert shown.exit_code == 1, shown.output
    assert platform.calls == [], "nothing is started, built or run"
    assert sorted(path.relative_to(home.root) for path in home.root.rglob("*")) == before, "no file is written"
    assert "Fake Docker is not running" in shown.output


def test_with_the_service_the_checklist_is_the_services(
    home: Home, project: Path, kernel: Kernel, platform: FakePlatform
) -> None:
    shown = run(home, "--check")
    assert shown.exit_code == 1, shown.output
    lines = lines_of(shown)
    assert lines["Clank's service"].split()[:2] == ["✓", "done"]
    assert lines["The sandbox image"].split()[:3] == ["•", "to", "do"]
    assert "no model has answered a test request yet" in lines["A model"]
    assert "no folder is a workspace yet" in lines["A folder"]
    assert f"open {project} as a workspace" in shown.output
    assert lines["Clank's VS Code window"].split()[:2] == ["○", "optional"]


def test_it_exits_0_when_everything_required_is_done(
    home: Home, project: Path, kernel: Kernel, platform: FakePlatform
) -> None:
    everything_done(kernel, platform, project)
    shown = run(home, "--check")
    assert shown.exit_code == 0, shown.output
    assert "Ready: everything Clank needs is set up." in shown.output
    assert "Your workspaces: paper." in shown.output


def test_json_prints_the_checklist_as_the_api_gives_it(home: Home, project: Path, kernel: Kernel) -> None:
    shown = run(home, "--check", "--json")
    found = json.loads(shown.output)
    assert found["ready"] is False
    assert [item["id"] for item in found["items"]][:2] == ["docker_installed", "docker_running"]
    assert shown.exit_code == 1


def test_the_folder_it_was_started_in_is_checked_as_a_workspaces_would_be(
    home: Home, kernel: Kernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    inside = home.config
    monkeypatch.chdir(inside)
    shown = run(home, "--check")
    said = " ".join(shown.output.split())
    assert "is inside Clank's own folder" in said
    assert "Open a terminal in a project's folder and type `clank` there" in said


def test_at_eighty_columns_what_an_item_is_now_goes_under_its_title_and_every_line_fits(
    home: Home, project: Path
) -> None:
    shown = run(home, "--check", columns=80)
    lines = shown.output.splitlines()
    assert all(len(line) <= 80 for line in lines), [line for line in lines if len(line) > 80]
    title = lines.index("  • to do     Clank's service")
    assert lines[title + 1].startswith("                not running.")
