"""Design 0018 §8.1 and §8.2: VS Code on another computer. VS Code's remote command, which a client in a terminal of
VS Code's Remote-SSH sends with its window's pipe, is run by the operation `agents.vscode` as its `code.cmd` runs it on
Windows (the server's Node with its `server-cli.js`, never through cmd.exe), the pipe in its environment; only the
remote command of the service's own user's VS Code server is run. Opening sets the PC's side up first, each step only
when needed: Clank's extension installed in VS Code's server when that version is not, each extension of the settings'
list that is missing, Clank's settings added to the server's machine settings where missing (the owner's own kept);
then the folder opens in a new window of the other computer's VS Code. An extension that cannot be installed is said,
and the folder opens all the same; a remote command that does not answer fails the opening, saying why."""

import json
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank import registry
from clank.components.agents import vscode
from clank.components.agents.remotecode import machine_settings, remote_argv, remote_command, server_root
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.operations import Operation
from clank.kernel.processes import Answer
from tests.fakes.platform import FakePlatform

YOU = Actor(kind="user", via="console")
COMMIT = "6d62b1d5dace93a33b3a6d3eca1317bd5e15bcb1"
CMD = (  # VS Code's own, as its server 1.142.0 has it
    "@echo off\nsetlocal\nset ROOT_DIR=%~dp0..\\..\n"
    f'call "%ROOT_DIR%\\node.exe" "%ROOT_DIR%\\out\\server-cli.js" "code" "1.142.0" "{COMMIT}" "code.cmd" %*\n'
    "endlocal\n"
)
HOOK = r"\\.\pipe\vscode-ipc-0f3a.sock"


def remote_server(home: Path) -> Path:
    """VS Code's server as Remote-SSH leaves it on a Windows PC, in `home`: its remote command."""
    cli = home / ".vscode-server" / "cli" / "servers" / f"Stable-{COMMIT}" / "server" / "bin" / "remote-cli"
    cli.mkdir(parents=True)
    (cli / "code.cmd").write_text(CMD, encoding="utf-8")
    return cli / "code.cmd"


def test_the_remote_command_runs_as_its_cmd_runs_it_and_its_server_is_found(tmp_path: Path) -> None:
    code = remote_server(tmp_path)
    server = code.parents[2]
    assert remote_argv(str(code)) == [str(server / "node.exe"), str(server / "out" / "server-cli.js"), "code",
                                      "1.142.0", COMMIT, "code.cmd"]  # fmt: skip
    elsewhere = "/srv/vscode/.vscode-server/bin/abc/bin/remote-cli/code"
    assert remote_argv(elsewhere) == [elsewhere], "elsewhere the command itself"
    assert server_root(str(code)) == tmp_path / ".vscode-server"
    assert machine_settings(str(code)) == tmp_path / ".vscode-server" / "data" / "Machine" / "settings.json"
    assert server_root(str(tmp_path / "elsewhere" / "code.cmd")) is None


def test_only_the_remote_command_of_the_services_own_vs_code_server_is_run(tmp_path: Path) -> None:
    code = remote_server(tmp_path)
    assert remote_command(str(code), tmp_path) == remote_argv(str(code))
    other = tmp_path / "other"
    assert remote_command(str(code), other) is None, "another user's server"
    tool = code.parent / "tool.exe"
    assert remote_command(str(tool), tmp_path) is None, "another program of the server"
    climbed = tmp_path / ".vscode-server" / ".." / "elsewhere" / "remote-cli" / "code.cmd"
    assert remote_command(str(climbed), tmp_path) is None, "a path that climbs out with .."
    assert remote_command("code.cmd", tmp_path) is None, "named whole, never found on the service's PATH"


class Remote:
    """VS Code's remote command as the operation runs it: what it was asked, with which pipe, and its answers."""

    def __init__(self, installed: str) -> None:
        self.installed = installed
        self.asked: list[list[str]] = []
        self.hooks: list[str] = []
        self.failing: set[str] = set()
        self.silent = False

    def __call__(self, argv: list[str], timeout: float = 0, env: Mapping[str, str] | None = None) -> Answer:
        self.asked.append(argv)
        self.hooks.append((env or {}).get("VSCODE_IPC_HOOK_CLI", ""))
        if self.silent:
            return Answer(None, "", "no answer within 60 seconds")
        if "--list-extensions" in argv:
            return Answer(0, self.installed, "")
        if "--install-extension" in argv:
            name = argv[argv.index("--install-extension") + 1]
            if name in self.failing:
                return Answer(1, "", f"Failed Installing Extensions: {name}")
            return Answer(0, f"Extension '{name}' was successfully installed.", "")
        return Answer(0, "", "")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def code(kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """VS Code's server in the service's user's home, Clank's extension as if built, two extensions in the settings."""
    monkeypatch.setattr(vscode, "home", lambda: tmp_path)
    vsix = tmp_path / "clank-0.9.3.vsix"
    vsix.write_bytes(b"PK")
    monkeypatch.setattr(vscode, "clank_vsix", lambda: vsix)
    monkeypatch.setattr(vscode, "which", lambda name: "D:/tools/clank.exe" if name == "clank" else None)
    settings = {"schema": "vscode/1", "extensions": ["ms-python.python", "james-yu.latex-workshop"]}
    (kernel.home.config / "vscode.json").write_text(json.dumps(settings) + "\n", encoding="utf-8")
    kernel.settings.reload_changed()
    return remote_server(tmp_path)


async def open_remote(kernel: Kernel, folder: Path, code: Path, file: str = "") -> Operation:
    params: dict[str, Any] = {"folder": str(folder), "remote": {"code": str(code), "hook": HOOK}}
    started = await kernel.operations.start("agents.vscode", {**params, **({"file": file} if file else {})}, actor=YOU)
    with anyio.fail_after(60):
        return await kernel.operations.wait(started.id)


@pytest.mark.anyio
async def test_opening_sets_the_pcs_side_up_then_opens_the_folder_and_the_next_time_only_opens_it(
    kernel: Kernel, code: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = Remote("clank.clank@0.9.2\nms-python.python@2026.18.0\n")
    monkeypatch.setattr(vscode, "run_answer", remote)
    machine = tmp_path / ".vscode-server" / "data" / "Machine" / "settings.json"
    machine.parent.mkdir(parents=True)
    machine.write_text(json.dumps({"editor.wordWrap": "off"}), encoding="utf-8")
    folder = tmp_path / "paper"
    folder.mkdir()
    async with kernel.operations.running():
        done = await open_remote(kernel, folder, code)
        assert done.status == "done", done.error
        base = remote_argv(str(code))
        assert remote.asked == [
            [*base, "--list-extensions", "--show-versions"],
            [*base, "--install-extension", str(tmp_path / "clank-0.9.3.vsix"), "--force"],
            [*base, "--install-extension", "james-yu.latex-workshop"],
            [*base, "--new-window", str(folder)],
        ], "no instance of its own: the other computer's VS Code, through its window's server"
        assert set(remote.hooks) == {HOOK}, "every call talks back to the window the client sits in"
        written: dict[str, Any] = json.loads(machine.read_text(encoding="utf-8"))
        assert written["editor.wordWrap"] == "off", "the owner's own kept"
        assert written["clank.agent.openOnStart"] is True
        assert written["latex-workshop.latex.tools"][0]["command"] == "D:/tools/clank.exe"
        lines = [line.text for line in kernel.operations.log_lines(done.id)]
        assert any("on your computer, connected to this PC" in line for line in lines), lines
        assert done.result == {
            "folder": str(folder), "installed": ["clank.clank", "james-yu.latex-workshop"], "failed": [],
            "where": "remote",
        }  # fmt: skip
        remote.installed = "clank.clank@0.9.3\nms-python.python@2026.18.0\njames-yu.latex-workshop@10.0.0\n"
        remote.asked.clear()
        again = await open_remote(kernel, folder, code, "PLAN.md")
        assert again.status == "done", again.error
    assert remote.asked == [
        [*base, "--list-extensions", "--show-versions"],
        [*base, "--new-window", str(folder), str(folder / "PLAN.md")],
    ]


@pytest.mark.anyio
async def test_an_extension_that_cannot_be_installed_is_said_and_a_command_that_does_not_answer_fails_the_opening(
    kernel: Kernel, code: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = Remote("clank.clank@0.9.3\n")
    remote.failing.add("james-yu.latex-workshop")
    monkeypatch.setattr(vscode, "run_answer", remote)
    async with kernel.operations.running():
        done = await open_remote(kernel, tmp_path, code)
        assert done.status == "done", done.error
        assert done.result is not None
        assert done.result["failed"] == ["james-yu.latex-workshop"]
        lines = [line.text for line in kernel.operations.log_lines(done.id)]
        assert any("james-yu.latex-workshop could not be installed" in line for line in lines), lines
        assert remote.asked[-1][-2:] == ["--new-window", str(tmp_path)], "the folder opens all the same"
        remote.silent = True
        silent = await open_remote(kernel, tmp_path, code)
    assert silent.status == "failed"
    assert "VS Code's remote command did not answer" in (silent.error or ""), silent.error
    assert "File menu" in (silent.error or "")


@pytest.mark.anyio
async def test_a_remote_command_that_is_not_the_services_own_vs_code_servers_is_refused(
    kernel: Kernel, code: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    remote = Remote("")
    monkeypatch.setattr(vscode, "run_answer", remote)
    async with kernel.operations.running():
        done = await open_remote(kernel, tmp_path, tmp_path / "remote-cli" / "code.cmd")
    assert done.status == "failed"
    assert "is not VS Code's remote command" in (done.error or ""), done.error
    assert remote.asked == [], "nothing was run"
