"""Design 0028 §4 and §5: `clank setup`, without `--check`, asks about each item that is not done, in order, showing
its fix and its exact command first, and does it on a yes; nothing runs without its yes, and without a terminal to
answer in the answer is no. A command that needs administrator rights (`sudo systemctl start docker`, `sudo systemctl
enable docker`, `sudo usermod -aG docker <account>`, the installer's Docker step) runs attached to the terminal, so
sudo asks for the password itself and nothing it says is captured; after joining the docker group it says to log out
and in once, and stops there. Docker Desktop is started through its own start, by the service when it runs, else here.
Clank's service is started on a yes, the folder `clank setup` was started in is opened as a workspace on a yes, and the
model's step asks once: in the cloud, on this computer's GPU, or both, the terminal handed to Add a model's command for
each, the cloud first. The sandbox image is built by the service in the background on a yes while the setup goes on, and
the folder opens once the build ended (S4). `--yes` does every fix that needs no
administrator rights without asking and lists the others with their commands."""

import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner, Result
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common, follow
from clank.cli.main import main
from clank.client import Client
from clank.components.agents import checklist, setupcli, vscode
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.adapters.platform import PlatformSetup
from clank.components.workspaces.sandbox import image_tag
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

NOW = datetime(2026, 10, 27, 9, 0, tzinfo=UTC)
START = ("sudo", "systemctl", "start", "docker")
ENABLE = ("sudo", "systemctl", "enable", "docker")
JOIN = ("sudo", "usermod", "-aG", "docker", "ada")
OWNER = PlatformSetup(at_boot=True, in_group=False, start=START, boot=ENABLE, join=JOIN)


class Terminal:
    """The terminal a fix runs in: each command it was given, and the exit status it answers."""

    def __init__(self, status: int = 0) -> None:
        self.ran: list[list[str]] = []
        self.status = status

    def __call__(self, argv: Sequence[str]) -> int | str:
        self.ran.append(list(argv))
        return self.status


@pytest.fixture
def platform() -> FakePlatform:
    """Docker running, nothing of Clank's built yet."""
    return FakePlatform()


@pytest.fixture
def terminal(monkeypatch: pytest.MonkeyPatch) -> Terminal:
    found = Terminal()
    monkeypatch.setattr(setupcli, "attached", found)
    return found


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[Home]:
    """The homes whose service `clank setup` started (none really starts)."""
    found: list[Home] = []
    monkeypatch.setattr(setupcli, "start_detached", lambda home: found.append(home))
    return found


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


def engine(platform: FakePlatform, state: str, setup: PlatformSetup = OWNER) -> None:
    """The fake platform as Docker Engine is: the system's, which Clank never starts, with its owner's commands."""
    platform.state = state
    platform.starts = False
    platform.setup = setup
    platform.detail = "start it with `sudo systemctl start docker`" if state == "stopped" else "..."


def run(home: Home, *arguments: str, input: str | None = None) -> Result:
    environ = {"CLANK_HOME": str(home.root), "COLUMNS": "200"}
    return CliRunner().invoke(main, ["setup", *arguments], input=input, env=environ)


def said(shown: Result) -> str:
    return " ".join(shown.output.split())


def test_nothing_runs_without_its_yes(home: Home, project: Path, platform: FakePlatform, terminal: Terminal,
                                      started: list[Home]) -> None:  # fmt: skip
    engine(platform, "stopped")
    shown = run(home, input="n\nn\n")
    assert terminal.ran == [], "no command ran"
    assert started == [], "no service started"
    assert platform.calls == []
    assert "`sudo systemctl start docker`" in shown.output, "the exact command is shown before the question"
    assert "Do it now?" in shown.output
    assert shown.exit_code == 1


def test_without_a_terminal_to_answer_in_the_answer_is_no(
    home: Home, project: Path, platform: FakePlatform, terminal: Terminal, started: list[Home]
) -> None:
    engine(platform, "stopped")
    shown = run(home, input="")
    assert (terminal.ran, started) == ([], [])
    assert shown.exit_code == 1


def test_an_administrator_command_runs_attached_to_the_terminal_on_a_yes(
    home: Home, project: Path, platform: FakePlatform, terminal: Terminal, started: list[Home]
) -> None:
    engine(platform, "stopped")
    shown = run(home, input="y\nn\n")
    assert terminal.ran == [list(START)]
    assert "> sudo systemctl start docker" in shown.output


def test_the_terminal_runner_inherits_the_terminal_so_sudo_asks_itself_and_nothing_is_captured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def call(argv: list[str], **options: Any) -> int:
        calls.append((argv, options))
        return 0

    monkeypatch.setattr(subprocess, "call", call)
    assert setupcli.attached(list(START)) == 0
    assert calls == [(list(START), {})], "no stdin, stdout, stderr or capture: the terminal's own"


def test_after_joining_the_docker_group_it_says_to_log_out_and_in_once_and_stops_there(
    home: Home, project: Path, platform: FakePlatform, terminal: Terminal, started: list[Home]
) -> None:
    engine(platform, "no access")
    shown = run(home, input="y\ny\n")
    assert terminal.ran == [list(JOIN)]
    assert "root's rights" in said(shown), "Docker's own warning, said before the yes"
    assert "log out and in once" in said(shown)
    assert started == [], "nothing more: the group takes effect at the next login"
    assert shown.exit_code == 1


def test_what_is_the_persons_to_do_is_said_and_listed_again_at_the_end(
    home: Home, project: Path, platform: FakePlatform, terminal: Terminal, started: list[Home]
) -> None:
    engine(platform, "no access", setup=PlatformSetup(at_boot=True, in_group=True, start=START, boot=ENABLE, join=JOIN))
    shown = run(home, input="")
    assert terminal.ran == [], "a log out and in is the person's: Clank runs nothing for it"
    left = shown.output[shown.output.index("Left to do:") :]
    assert "Docker usable by this account: log out and in again" in " ".join(left.split())
    assert started == [], "the service waits until this account can use Docker"


def test_a_command_that_fails_says_so_and_the_setup_goes_on(
    home: Home, project: Path, platform: FakePlatform, started: list[Home], monkeypatch: pytest.MonkeyPatch
) -> None:
    engine(platform, "running", setup=PlatformSetup(at_boot=False, in_group=True, start=START, boot=ENABLE, join=JOIN))
    failing = Terminal(status=1)
    monkeypatch.setattr(setupcli, "attached", failing)
    shown = run(home, input="y\ny\n")
    assert failing.ran == [list(ENABLE)]
    assert "did not work" in shown.output
    assert started == [home], "the service, asked next, is started"


def test_docker_desktop_stopped_is_started_through_its_own_start_without_the_service(
    home: Home, project: Path, platform: FakePlatform, terminal: Terminal, started: list[Home]
) -> None:
    platform.state = "stopped"
    shown = run(home, input="y\nn\n")
    assert platform.calls[:2] == ["start", "after start"]
    assert terminal.ran == [], "Docker Desktop's own start: no command of the person's"
    assert "Do it now?" in shown.output


def test_with_the_service_docker_desktop_is_started_by_the_services_operation(
    home: Home, project: Path, platform: FakePlatform, kernel: Kernel, terminal: Terminal
) -> None:
    platform.state = "stopped"
    shown = run(home, input="y\nn\nn\nn\n")
    assert platform.calls[:2] == ["start", "after start"]
    assert "Start Docker" in shown.output, "the operation, followed"


def test_clanks_service_is_started_on_a_yes(home: Home, project: Path, terminal: Terminal, started: list[Home]) -> None:
    shown = run(home, input="y\n")
    assert started == [home]
    assert "`clank stop` ends it" in shown.output


def test_the_folder_it_was_started_in_is_opened_as_a_workspace_on_a_yes(
    home: Home, project: Path, platform: FakePlatform, kernel: Kernel, terminal: Terminal
) -> None:
    platform.images.add(image_tag())
    shown = run(home, input="\ny\n")  # not the model now; the folder, yes
    assert kernel.settings.records("workspace")[0].record.model_dump()["path"] == str(project)
    assert "Open a workspace" in shown.output


@pytest.mark.parametrize(("answer", "paths"), [("c", ["cloud"]), ("l", ["local"]), ("b", ["cloud", "local"]),
                                               ("", [])])  # fmt: skip
def test_the_models_step_asks_once_cloud_local_or_both_and_hands_the_terminal_to_add_a_model(
    home: Home, project: Path, platform: FakePlatform, kernel: Kernel, terminal: Terminal, answer: str, paths: list[str]
) -> None:
    platform.images.add(image_tag())
    shown = run(home, input=f"{answer}\nn\n")
    add = [sys.executable, "-m", "clank", "model", "add"]
    assert terminal.ran == [[*add, f"--{path}"] for path in paths], "the cloud first, then local"
    assert "in the cloud through OpenRouter (c), on this computer's GPU (l), or both (b)" in said(shown)


def test_yes_does_every_fix_without_administrator_rights_and_lists_the_others(
    home: Home, project: Path, platform: FakePlatform, terminal: Terminal, started: list[Home]
) -> None:
    engine(platform, "running", setup=PlatformSetup(at_boot=False, in_group=True, start=START, boot=ENABLE, join=JOIN))
    shown = run(home, "--yes")
    assert terminal.ran == [], "no administrator command without its yes"
    assert started == [home], "the service needs none"
    assert "Do it now?" not in shown.output
    assert "sudo systemctl enable docker" in shown.output, "listed with its command"


def test_yes_starts_docker_desktop_through_its_own_start(
    home: Home, project: Path, platform: FakePlatform, terminal: Terminal, started: list[Home]
) -> None:
    platform.state = "stopped"
    run(home, "--yes")
    assert platform.calls[:2] == ["start", "after start"]


def test_the_sandbox_image_is_built_in_the_background_and_the_folder_waits_for_it(
    home: Home, project: Path, platform: FakePlatform, kernel: Kernel, terminal: Terminal
) -> None:
    """Design 0028 §4 (S4): on a yes the image is built by the service in the background while the setup goes on (the
    model is asked meanwhile), and the folder opens once the build ended, on the image it built."""
    building = platform.build_image

    def slow(*args: Any, **kwargs: Any) -> int | None:
        time.sleep(1.0)  # long enough for the setup to reach the folder while it builds
        return building(*args, **kwargs)

    platform.build_image = slow  # type: ignore[method-assign]
    shown = run(home, input="y\n\ny\n")  # the image, yes; the model, not now; the folder, yes
    assert platform.calls.count(f"build {image_tag()}") == 1, "built once, by the setup's operation"
    assert "Building it in the background (op-" in shown.output
    waited = shown.output.index("First the sandbox image's build ends")
    assert waited < shown.output.index("Open a workspace"), "the folder opens once the build ended"
    assert kernel.settings.records("workspace"), "the folder opened"
    assert any(each.type == "workspaces.image" for each in kernel.operations.find())


def test_yes_builds_the_sandbox_image_too(home: Home, project: Path, platform: FakePlatform, kernel: Kernel,
                                          terminal: Terminal) -> None:  # fmt: skip
    run(home, "--yes")
    assert f"build {image_tag()}" in platform.calls
