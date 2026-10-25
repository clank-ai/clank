"""Design 0020 §3: `clank latex setup [FOLDER]` gives a folder's workspace the TeX layer: the workspace is opened (made
the first time), the layer added to its record, its image built on the sandbox image (asked first unless `--yes`). A
container already running the image before keeps running it, and the command says how to move it; with `--restart` it
is stopped and opened again on the new image."""

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
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import image_tag, layered_tag, names
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    monkeypatch.setattr(follow, "POLL_SECONDS", 0.005)
    kernel = open_kernel(home, FakeClock(datetime(2026, 10, 25, 9, 0, tzinfo=UTC)), registry.components())
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7720", "t", name="cli", http=http))
        yield kernel
    kernel.close()


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    found = tmp_path / "work" / "paper"
    found.mkdir(parents=True)
    return found


def run(*arguments: str, input: str | None = None) -> Result:
    return CliRunner().invoke(main, list(arguments), input=input)


def test_setup_opens_the_workspace_adds_the_tex_layer_and_builds_its_image(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    done = run("latex", "setup", str(folder), "--yes")
    assert done.exit_code == 0, done.output
    tex = layered_tag(["tex"])
    assert f"build {image_tag()}" in platform.calls
    assert f"build {tex}" in platform.calls
    assert kernel.settings.get("workspace", "paper").record.model_dump()["layers"] == ["tex"]
    assert f"TeX is in paper's image ({tex})" in done.output
    assert "its container runs it" in done.output


def test_a_running_container_keeps_its_image_until_restart_moves_it(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    assert run("workspace", "open", str(folder), "--yes").exit_code == 0
    container = names(kernel.home.id).container("paper")
    kept = run("latex", "setup", str(folder), "--yes")
    assert kept.exit_code == 0, kept.output
    assert platform.specs[container].image == image_tag(), "a running container is not made again"
    assert "clank latex setup --restart" in kept.output
    moved = run("latex", "setup", str(folder), "--yes", "--restart")
    assert moved.exit_code == 0, moved.output
    assert platform.specs[container].image == layered_tag(["tex"])
    assert "its container runs it" in moved.output
