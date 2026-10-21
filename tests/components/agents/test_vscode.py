"""Design 0004 §5: Clank's VS Code window is a separate instance of the same program, its settings and extensions under
CLANK_HOME/vscode, so the main one is untouched. Opening a folder in it sets it up the first time (its settings:
telemetry and VS Code's own AI features off, a title that says Clank, the agent opened beside the files; Clank's
extension and the curated ones), installs only what is missing afterward, says an extension that cannot be installed
and opens the folder all the same; without VS Code it fails saying how to name it. On Windows VS Code's own program is
run, never its `code.cmd`, so no folder's name goes through cmd.exe."""

import json
from collections.abc import Iterator
from pathlib import Path

import anyio
import pytest

from clank import registry
from clank.components.agents.kinds import EXTENSIONS
from clank.components.agents.vscode import find_program, settings_text
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.operations import Operation
from tests.fakes.platform import FakePlatform
from tests.support.vscode import asked, fake_vscode

YOU = Actor(kind="user", via="console")
CODE_CMD = """@echo off
setlocal
set VSCODE_DEV=
set ELECTRON_RUN_AS_NODE=1
"%~dp0..\\Code.exe" "%~dp0..\\7baac39ec3\\resources\\app\\out\\cli.js" %*
IF %ERRORLEVEL% NEQ 0 EXIT /b %ERRORLEVEL%
endlocal
"""


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def code(kernel: Kernel, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The fake VS Code, and Clank's extension as if built; the file that keeps what the fake was asked."""
    return fake_vscode(kernel, tmp_path, monkeypatch)


async def open_folder(kernel: Kernel, folder: Path) -> Operation:
    started = await kernel.operations.start("agents.vscode", {"folder": str(folder)}, actor=YOU)
    with anyio.fail_after(60):
        return await kernel.operations.wait(started.id)


def test_the_instances_settings_are_added_once_and_the_owners_own_are_kept() -> None:
    written = json.loads(settings_text(None) or "")
    assert (written["telemetry.telemetryLevel"], written["chat.disableAIFeatures"]) == ("off", True)
    assert written["clank.agent.openOnStart"] is True
    assert written["security.workspace.trust.enabled"] is False, "a folder the owner opened is not in restricted mode"
    # The agent's terminal is OpenCode in the container: an activation typed into it would reach the model as a prompt.
    assert written["python.terminal.activateEnvironment"] is False
    assert written["python-envs.terminal.autoActivationType"] == "off"
    assert written["workbench.editor.alwaysShowEditorActions"] is True, "a change keeps Accept and Reject (design 0007)"
    assert written["window.title"].startswith("Clank")
    changed = json.loads(settings_text(json.dumps({"telemetry.telemetryLevel": "error", "editor.fontSize": 15})) or "")
    assert (changed["telemetry.telemetryLevel"], changed["editor.fontSize"]) == ("error", 15)
    assert changed["clank.agent.openOnStart"] is True
    assert settings_text(json.dumps(written)) is None, "nothing to add: the file is left as it is"
    assert settings_text('{\n  // a note\n  "editor.fontSize": 15\n}') is None, "not plain JSON: left as written"


def test_long_lines_wrap_in_every_editor_and_in_a_changes_diff_unless_the_owner_chose_otherwise() -> None:
    written = json.loads(settings_text(None) or "")
    assert (written["editor.wordWrap"], written["diffEditor.wordWrap"]) == ("on", "on")
    kept = json.loads(settings_text(json.dumps({"editor.wordWrap": "off"})) or "")
    assert (kept["editor.wordWrap"], kept["diffEditor.wordWrap"]) == ("off", "on")


def test_on_windows_vs_codes_own_program_is_run_never_its_cmd_file(tmp_path: Path) -> None:
    install = tmp_path / "Microsoft VS Code"
    (install / "bin").mkdir(parents=True)
    (install / "bin" / "code.cmd").write_text(CODE_CMD, encoding="utf-8")
    found = find_program([], lambda name: str(install / "bin" / "code"), windows=True)
    assert found is not None
    executable = str(install / "Code.exe")
    assert found.cli == [executable, str(install / "7baac39ec3" / "resources" / "app" / "out" / "cli.js")]
    assert (found.env, found.gui) == ({"ELECTRON_RUN_AS_NODE": "1"}, [executable])
    elsewhere = find_program([], lambda name: "/usr/bin/code", windows=False)
    assert elsewhere is not None
    assert (elsewhere.cli, elsewhere.gui, elsewhere.env) == (["/usr/bin/code"], ["/usr/bin/code"], {})
    assert find_program(["/opt/code", "--x"], lambda name: None).cli == ["/opt/code", "--x"]  # type: ignore[union-attr]
    assert find_program([], lambda name: None) is None


@pytest.mark.anyio
async def test_opening_a_folder_sets_the_instance_up_once_then_opens_the_folder(
    kernel: Kernel, code: Path, tmp_path: Path
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    async with kernel.operations.running():
        done = await open_folder(kernel, folder)
        assert done.status == "done", done.error
        first = asked(code)
        again = await open_folder(kernel, folder)
        assert again.status == "done", again.error
        second = asked(code, 2)
    instance = kernel.home.root / "vscode"
    prefix = ["--user-data-dir", str(instance / "data"), "--extensions-dir", str(instance / "extensions")]
    assert all(call[:4] == prefix for call in second["calls"]), "every call is the separate instance's"
    assert first["opened"] == [str(folder)]
    assert sorted(first["installed"]) == sorted(["clank.clank", *EXTENSIONS])
    settings = json.loads((instance / "data" / "User" / "settings.json").read_text(encoding="utf-8"))
    assert settings["clank.agent.openOnStart"] is True
    installs = [call for call in second["calls"] if "--install-extension" in call]
    assert len(installs) == 1 + len(EXTENSIONS), "the second time nothing is installed again"
    assert done.result == {"folder": str(folder), "installed": ["clank.clank", *EXTENSIONS], "failed": []}


@pytest.mark.anyio
async def test_an_extension_that_cannot_be_installed_is_said_and_the_folder_opens_all_the_same(
    kernel: Kernel, code: Path, tmp_path: Path
) -> None:
    code.write_text(json.dumps({"refuse": ["leanprover.lean4"]}), encoding="utf-8")
    async with kernel.operations.running():
        done = await open_folder(kernel, tmp_path)
    assert done.status == "done", done.error
    assert done.result is not None
    assert done.result["failed"] == ["leanprover.lean4"]
    lines = [line.text for line in kernel.operations.log_lines(done.id)]
    assert any("leanprover.lean4 could not be installed" in line for line in lines), lines
    assert asked(code)["opened"] == [str(tmp_path)]


@pytest.mark.anyio
async def test_without_vs_code_opening_fails_saying_how_to_name_it(kernel: Kernel, tmp_path: Path) -> None:
    async with kernel.operations.running():
        done = await open_folder(kernel, tmp_path)
    assert done.status == "failed"
    assert "VS Code was not found" in (done.error or "")
    assert "config/vscode.json" in (done.error or "")


@pytest.mark.anyio
async def test_clanks_vs_code_window_opens_a_file_of_the_folder(kernel: Kernel, code: Path, tmp_path: Path) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    (folder / "PLAN.md").write_text("# The plan\n", encoding="utf-8")
    async with kernel.operations.running():
        started = await kernel.operations.start("agents.vscode", {"folder": str(folder), "file": "PLAN.md"}, actor=YOU)
        with anyio.fail_after(60):
            done = await kernel.operations.wait(started.id)
        assert done.status == "done", done.error
        found = asked(code)
    assert found["calls"][-1][-2:] == [str(folder), str(folder / "PLAN.md")], "the folder, then the file in it"
    assert done.result is not None
    assert done.result["file"] == str(folder / "PLAN.md")


@pytest.mark.anyio
@pytest.mark.parametrize("named", ["C:x.md", "C:\\x.md", "/etc/x.md", "../x.md", "\\x.md"])
async def test_a_file_named_with_a_drive_or_a_root_or_out_of_the_folder_is_refused(
    kernel: Kernel, code: Path, tmp_path: Path, named: str
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    async with kernel.operations.running():
        started = await kernel.operations.start("agents.vscode", {"folder": str(folder), "file": named}, actor=YOU)
        with anyio.fail_after(60):
            done = await kernel.operations.wait(started.id)
    assert done.status == "failed", named
    assert "is not a file of" in str(done.error), done.error
