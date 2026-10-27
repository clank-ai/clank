"""Design 0004 §1 and §4: making a workspace's agent ready writes the program's configuration into the workspace's
running container (the gateway at the edge, the running preset's limits, or modest ones said when no model runs) and
answers the command that starts it there; a workspace that is not there, or whose container does not run, is refused
saying how to open it. `clank work` starts Docker when it is stopped, opens the folder's workspace,
loads the slot's last configuration that worked when no model runs, and runs the agent in this terminal.

Design 0004 §5 (revised 2026-10-26): preparing asks Docker for the container once, writes every file in one go and
reads Docker's limits once in a while, since a VS Code window waits for it before OpenCode starts.

Design 0018 §8.1: `clank code` over SSH gets the folder ready and opens nothing on the PC's screen, saying the command
for the other computer; in a terminal of VS Code's Remote-SSH it opens the other computer's VS Code."""

from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import pytest
from click.testing import CliRunner, Result
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common, follow
from clank.cli.main import main
from clank.client import Client
from clank.components.agents import cli as agents_cli
from clank.components.agents import vscode
from clank.components.agents.service import Agents
from clank.components.runtime.state import LastGood
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import names
from clank.components.workspaces.service import WorkspaceUnavailable
from clank.kernel import where
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import Answer
from tests.fakes.platform import FakePlatform
from tests.support.vscode import asked, fake_vscode

YOU = Actor(kind="user", via="console")
NPMRC = "/home/agent/.config/opencode/.npmrc"  # OpenCode's own installs kept offline
CONFIG = "/home/agent/.config/opencode/opencode.json"


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    monkeypatch.setattr(workspaces_service, "WAIT_SECONDS", 0.001)
    monkeypatch.setattr(follow, "POLL_SECONDS", 0.005)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def http(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with TestClient(create_app(kernel, token="t", port=7727), base_url="http://127.0.0.1:7727") as client:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7727", "t", name="cli", http=client))
        yield client


def ran(platform: FakePlatform, kernel: Kernel, workspace: str, folder: Path) -> None:
    """A workspace whose container runs, as `workspaces.open` leaves it: the edge on its network."""
    kernel.settings.write("workspace", workspace, {"path": str(folder)}, base=None, actor=YOU)
    spec_name = names(kernel.home.id).container(workspace)
    from tests.fakes.platform import container, with_edge

    platform.containers.append(container(spec_name, labels={"clank.home": kernel.home.id}))
    with_edge(platform, kernel.home.id, workspace)


def test_prepare_writes_the_programs_configuration_and_answers_its_command(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    ran(platform, kernel, "paper", tmp_path)
    platform.inside = lambda argv, given: Answer(0, '{"ok": true, "port": 4097}', "")  # the bridge: a free port
    agents: Agents = kernel.parts["agents"]
    prepared = agents.prepare("paper")
    container = names(kernel.home.id).container("paper")
    written = platform.files[(container, CONFIG)]
    assert '"baseURL": "http://edge:18210/v1"' in written
    assert prepared["limits"] == {"context": 24576, "output": 8192, "window": 32768, "margin": 8192}
    assert prepared["notes"] == ["no model runs: its limits are 32,768 and 8,192 tokens until one does"]
    argv = prepared["argv"]
    assert argv[:4] == ["docker", "exec", "--interactive", "--tty"]
    assert "OPENCODE_DISABLE_MODELS_FETCH=1" in argv
    assert argv[-7:] == ["/workspace", container, "opencode", "--port", "4097", "--hostname", "127.0.0.1"], (
        "its API on a port of its own, so its session can be reached (design 0005 §2)"
    )
    assert prepared["port"] == 4097
    platform.inside = None  # a container that cannot say (an image from before the bridge): no port, and why
    told = agents.prepare("paper")
    assert told["argv"][-1] == "opencode"
    assert "its session cannot be followed from other clients" in told["notes"][-1]


def test_prepare_refuses_a_workspace_that_is_not_there_or_does_not_run(kernel: Kernel, tmp_path: Path) -> None:
    agents: Agents = kernel.parts["agents"]
    with pytest.raises(WorkspaceUnavailable, match="there is no workspace 'nope'"):
        agents.prepare("nope")
    kernel.settings.write("workspace", "idle", {"path": str(tmp_path)}, base=None, actor=YOU)
    with pytest.raises(WorkspaceUnavailable, match="idle's container does not run: `clank workspace open` starts it"):
        agents.prepare("idle")


def test_prepare_writes_every_file_in_one_go_and_reads_dockers_limits_once_in_a_while(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran(platform, kernel, "paper", tmp_path)
    platform.inside = lambda argv, given: Answer(1, "", "")  # no OpenCode window to close, no port said
    workspaces = kernel.parts["workspaces"]
    looked: list[str] = []
    written: list[list[str]] = []
    limits: list[int] = []
    find, put, read = workspaces.container_of, platform.put_files, platform.limits

    def looking(name: str) -> str:
        looked.append(name)
        found: str = find(name)
        return found

    def putting(name: str, files: Sequence[tuple[str, str]]) -> None:
        written.append([path for path, _ in files])
        put(name, files)

    def reading() -> tuple[int, int] | None:
        limits.append(1)
        return read()

    monkeypatch.setattr(workspaces, "container_of", looking)
    monkeypatch.setattr(platform, "put_files", putting)
    monkeypatch.setattr(platform, "limits", reading)
    agents: Agents = kernel.parts["agents"]
    agents.prepare("paper")
    assert written == [[*(path for path, _ in workspaces_service.agent_files()), NPMRC, CONFIG]], (
        "Clank's files and OpenCode's configuration in one docker exec: each one took a fifth of a second (2026-10-26)"
    )
    assert len(looked) == 3, "the container is asked of Docker once by prepare, and once by each of the bridge's runs"
    agents.prepare("paper")
    agents.configure("paper")
    assert len(limits) == 1, "Docker's CPUs are read once in a while, not at each start: `docker info` took 0.7 s"
    assert len(written) == 3, "an agent started without a terminal writes them in one go too"
    assert written[2][-1] == CONFIG


def test_clank_work_starts_docker_opens_the_folder_and_runs_the_agent_here(
    kernel: Kernel, http: TestClient, platform: FakePlatform, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    platform.state = "stopped"
    folder = tmp_path / "paper"
    folder.mkdir()
    monkeypatch.chdir(folder)
    kernel.parts["runtime"].state.set_slot("main", "ready", "a test", actor=YOU, preset="daily-262k")
    commands: list[Sequence[str]] = []

    def here(argv: Sequence[str]) -> int:
        commands.append(argv)
        return 0

    monkeypatch.setattr(agents_cli, "terminal", here)
    monkeypatch.setattr(follow, "ask", lambda text, default: "y")  # the first open builds the image: yes
    result = run("work")
    assert result.exit_code == 0, result.output
    assert "Docker is stopped: starting it" in result.output
    assert f"OpenCode in paper ({folder} at /workspace), with daily 262K" in result.output
    [argv] = commands
    assert argv[-3:] == ["/workspace", names(kernel.home.id).container("paper"), "opencode"]
    assert (names(kernel.home.id).container("paper"), CONFIG) in platform.files


def test_with_no_model_running_clank_loads_the_slots_last_good_one_and_says_why_it_cannot(
    kernel: Kernel, http: TestClient, platform: FakePlatform, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "notes"  # not tmp_path itself: it holds the test's CLANK_HOME, which a workspace may not see
    folder.mkdir()
    monkeypatch.chdir(folder)
    good = LastGood(preset="daily-262k", options={}, time=kernel.clock.now())
    kernel.parts["runtime"].state.remember_good("main", good)
    monkeypatch.setattr(agents_cli, "terminal", lambda argv: pytest.fail("the agent ran without a model"))
    result = run("work", "--yes")
    assert "No model runs: loading daily-262k" in result.output
    assert result.exit_code == 1, "a test's home has no engine installed: the load fails, saying so"
    assert "is not installed" in result.output


def test_clank_code_gets_the_folder_ready_then_opens_it_in_clanks_vs_code_window(
    kernel: Kernel, http: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    monkeypatch.chdir(folder)
    kernel.parts["runtime"].state.set_slot("main", "ready", "a test", actor=YOU, preset="daily-262k")
    state = fake_vscode(kernel, tmp_path, monkeypatch)
    monkeypatch.setattr(follow, "ask", lambda text, default: "y")  # the first open builds the image: yes
    result = run("code")
    assert result.exit_code == 0, result.output
    assert f"VS Code opens {folder}: OpenCode opens beside your files" in result.output
    assert asked(state)["opened"] == [str(folder)]
    assert names(kernel.home.id).container("paper") in {c.name for c in kernel.parts["workspaces"].platform.containers}


def test_clank_code_over_ssh_gets_the_folder_ready_and_says_the_command_for_the_other_computer(
    kernel: Kernel, http: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    monkeypatch.chdir(folder)
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.2 51022 10.0.0.9 22")
    set_vscode(kernel, {"ssh_host": "lab-pc"})
    kernel.parts["runtime"].state.set_slot("main", "ready", "a test", actor=YOU, preset="daily-262k")
    monkeypatch.setattr(follow, "ask", lambda text, default: "y")
    result = run("code")
    assert result.exit_code == 0, result.output
    assert "over SSH, VS Code would open on the PC's own screen" in result.output
    assert 'code --folder-uri "vscode-remote://ssh-remote+lab-pc/' in result.output
    assert "Opening" not in result.output, "nothing opened on the PC's screen"
    assert names(kernel.home.id).container("paper") in {c.name for c in kernel.parts["workspaces"].platform.containers}


def test_clank_code_in_a_remote_ssh_terminal_opens_the_other_computers_vs_code(
    kernel: Kernel, http: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    monkeypatch.chdir(folder)
    cli = tmp_path / ".vscode-server" / "bin" / "abc" / "bin" / "remote-cli"
    cli.mkdir(parents=True)
    (cli / "code").write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.2 51022 10.0.0.9 22")
    monkeypatch.setenv("VSCODE_IPC_HOOK_CLI", "/run/vscode-ipc-1.sock")
    monkeypatch.setattr(where, "which", lambda name: str(cli / "code") if name == "code" else None)
    monkeypatch.setattr(vscode, "home", lambda: tmp_path)
    calls: list[list[str]] = []

    def remote(argv: list[str], timeout: float = 0, env: Mapping[str, str] | None = None) -> Answer:
        calls.append(argv)
        assert (env or {}).get("VSCODE_IPC_HOOK_CLI") == "/run/vscode-ipc-1.sock"
        return Answer(0, "clank.clank@9.9.9\n" if "--list-extensions" in argv else "", "")

    monkeypatch.setattr(vscode, "run_answer", remote)
    monkeypatch.setattr(vscode, "clank_vsix", lambda: None)
    set_vscode(kernel, {"extensions": []})
    kernel.parts["runtime"].state.set_slot("main", "ready", "a test", actor=YOU, preset="daily-262k")
    monkeypatch.setattr(follow, "ask", lambda text, default: "y")
    result = run("code")
    assert result.exit_code == 0, result.output
    assert f"VS Code opens {folder} on your computer: OpenCode opens beside your files" in result.output
    assert calls[-1] == [str(cli / "code"), "--new-window", str(folder)]


def set_vscode(kernel: Kernel, values: dict[str, object]) -> None:
    """Clank's VS Code settings, as the owner writes them."""
    current = kernel.settings.get("vscode", "vscode")
    kernel.settings.write("vscode", "vscode", values, base=current.revision, actor=YOU)


def run(*arguments: str) -> Result:
    return CliRunner().invoke(main, list(arguments))
