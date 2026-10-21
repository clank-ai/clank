"""Clank's VS Code window (design 0004 §5): a separate instance of the VS Code program on this machine, its settings and
extensions under CLANK_HOME/vscode (`--user-data-dir`, `--extensions-dir`), so the main one's extensions, settings and
profiles are untouched. Opening a folder in it is the operation `agents.vscode` {folder}, under the lock `vscode`:

- settings: VS Code's program is found (`config/vscode.json` names it, else `code` on the PATH; on Windows the program
  its code.cmd runs, Code.exe running VS Code's command line as Node, so no folder's name ever goes through cmd.exe,
  which would read `&` or `%` in it). The instance's user settings get Clank's: telemetry off, VS Code's own AI
  features off (the agent is Clank's), extensions checked for updates but not updated unasked, no welcome page, a
  title that says Clank, the agent opened beside the files, no restricted mode (workspace trust off: the window
  opens only folders the owner chose, and the agent's container sees nothing else), no Python environment
  activated in new terminals (the agent's terminal would get it as a prompt), and the editors' actions shown in every
  group (a change to review keeps its Accept and Reject while the agent's terminal has the keyboard), figures
  opened in Clank's annotator, and long lines wrapped (in a change's diff too); each only when missing, so a
  value the owner changed stays, and a settings file that is not plain JSON (comments) is left as it is.
- extensions: Clank's own (`vscode/clank-<version>.vsix`, built from Clank's folder) when that version is not the one
  installed, and each of the settings' extensions that is missing, from VS Code's marketplace. One that cannot be
  installed is said and tried again the next time, and the folder opens all the same.
- open: the folder, in a window of the instance, started on its own and not waited for. In it, Clank's extension opens
  OpenCode in a terminal beside the files (the setting `clank.agent.openOnStart`).
"""

import json
import re
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from clank.components.agents.kinds import VsCodeSettings
from clank.kernel.core import Kernel
from clank.kernel.operations import OperationContext, OperationType, StepSpec
from clank.kernel.processes import Answer, launch_program, run_answer

which = shutil.which
CLANK = "clank.clank"  # Clank's extension: its publisher and name
LIST_SECONDS = 60.0
INSTALL_SECONDS = 300.0  # an extension from the marketplace, downloaded and unpacked
SETTINGS: dict[str, Any] = {
    "telemetry.telemetryLevel": "off",
    "chat.disableAIFeatures": True,
    "extensions.autoUpdate": False,
    "extensions.autoCheckUpdates": True,
    "workbench.startupEditor": "none",
    "window.title": "Clank · ${rootName}${separator}${activeEditorShort}",
    "clank.agent.openOnStart": True,
    # The window opens only folders the owner chose, and the agent works in a container that sees nothing else; in
    # restricted mode VS Code would turn off every extension that is not declared safe there, Clank's agent included.
    "security.workspace.trust.enabled": False,
    # The agent's terminal runs OpenCode in the container: the Python extensions' activation of the folder's own
    # environment (a Windows .venv) would be typed into it, and OpenCode would send it to the model as a prompt (seen on
    # 2026-10-14). The agent's environment is the container's (~/.venv, design 0004 §10).
    "python.terminal.activateEnvironment": False,
    "python-envs.terminal.autoActivationType": "off",
    # A change the agent asks for opens beside the files while the agent's terminal keeps the keyboard; VS Code shows
    # the actions of an editor group only while it has the focus, so the change's Accept and Reject would be hidden
    # (seen on 2026-10-15, design 0007 §6).
    "workbench.editor.alwaysShowEditorActions": True,
    # A figure opens in Clank's annotator, to mark it up for the agent (design 0008 §6); "Open With" shows the image as
    # VS Code shows it.
    "workbench.editorAssociations": {"*.png": "clank.figure", "*.jpg": "clank.figure", "*.jpeg": "clank.figure"},
    # Long lines wrap, in every editor and in a change's diff (the owner, 2026-10-16: "for showing the file changes (and
    # anything in general), please be sure that we are using word wrap").
    "editor.wordWrap": "on",
    "diffEditor.wordWrap": "on",
}
CLI_JS = re.compile(r'"%~dp0\.\.\\([^"]*cli\.js)"')  # what code.cmd runs, under VS Code's folder
VSIX = re.compile(r"clank-(\d+\.\d+\.\d+)\.vsix")


class WindowError(Exception):
    """VS Code that cannot be found or started, and why."""


@dataclass(frozen=True)
class Program:
    """How VS Code is run: its command line (for its extensions), what that needs in its environment, and the program
    that opens a window."""

    cli: list[str]
    gui: list[str]
    env: dict[str, str] = field(default_factory=dict)


def find_program(
    configured: Sequence[str], look: Callable[[str], str | None] | None = None, windows: bool = sys.platform == "win32"
) -> Program | None:
    """VS Code's program: the one the settings name, else `code` on the PATH; None when there is none."""
    if configured:
        return Program(list(configured), list(configured))
    found = (look or which)("code")
    if found is None:
        return None
    if not windows:
        return Program([found], [found])
    script = Path(found).parent / "code.cmd"
    try:
        match = CLI_JS.search(script.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    if match is None:
        return None
    folder = script.parent.parent
    executable = str(folder / "Code.exe")
    return Program(
        [executable, str(folder.joinpath(*match.group(1).split("\\")))], [executable], {"ELECTRON_RUN_AS_NODE": "1"}
    )


def settings_text(existing: str | None) -> str | None:
    """The instance's user settings with Clank's added where missing; None when there is nothing to write (each is
    there already, or the file is not plain JSON, so it is left as the owner wrote it)."""
    values: Any = {}
    if existing is not None and existing.strip():
        try:
            values = json.loads(existing)
        except ValueError:
            return None
    if not isinstance(values, dict):
        return None
    missing = {key: value for key, value in SETTINGS.items() if key not in values}
    if existing is not None and existing.strip() and not missing:
        return None
    return json.dumps({**values, **missing}, indent=2, ensure_ascii=False) + "\n"


def clank_vsix() -> Path | None:
    """Clank's own extension as built from Clank's folder (`vscode/clank-<version>.vsix`, the version its package.json
    says); None when it is not built."""
    folder = Path(__file__).resolve().parents[3] / "vscode"
    try:
        version = json.loads((folder / "package.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return None
    found = folder / f"clank-{version}.vsix"
    return found if found.is_file() else None


def installed_versions(output: str) -> dict[str, str]:
    """The extensions `--list-extensions --show-versions` lists: each id (lowercase) and its version."""
    found = {}
    for line in output.splitlines():
        name, _, version = line.strip().partition("@")
        if name:
            found[name.lower()] = version
    return found


def operation_types(kernel: Kernel) -> list[OperationType]:
    """Opening a folder in Clank's VS Code window."""
    window = Window(kernel)
    steps = tuple(StepSpec(step) for step in ("settings", "extensions", "open"))
    return [OperationType("agents.vscode", "Open VS Code", steps, window.open, locks=_lock, owner="agents")]


def _lock(params: Mapping[str, Any]) -> list[str]:
    return ["vscode"]


class Window:
    """What opening a folder in Clank's VS Code window does."""

    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel

    @property
    def folder(self) -> Path:
        """Where the instance keeps its settings (`data`) and its extensions (`extensions`)."""
        return self.kernel.home.root / "vscode"

    def own(self, *arguments: str) -> list[str]:
        """VS Code's arguments for the instance, before the rest."""
        data, extensions = self.folder / "data", self.folder / "extensions"
        return ["--user-data-dir", str(data), "--extensions-dir", str(extensions), *arguments]

    async def open(self, context: OperationContext) -> dict[str, Any]:
        """Its settings, its extensions, then the folder in a window, and a file of it when one is named (`file`,
        from the folder: a gate's *edit, then approve*, design 0013 §10)."""
        folder = str(context.params["folder"])
        named = str(context.params.get("file") or "")
        file = Path(folder).joinpath(*named.split("/")) if named else None
        settings = VsCodeSettings.model_validate(self.kernel.settings.get("vscode", "vscode").record.model_dump())
        async with context.step("settings"):
            if not Path(folder).is_dir():
                raise WindowError(f"{folder} is not a folder")
            if named and not _in_the_folder(named):
                raise WindowError(f"{named} is not a file of {folder}: name it from the folder, as in PLAN.md")
            program = find_program(settings.program)
            if program is None:
                raise WindowError(
                    "VS Code was not found: install it (code.visualstudio.com), or name its `code` command in "
                    "config/vscode.json (program)"
                )
            self._write_settings(context)
        async with context.step("extensions"):
            installed, failed = await self._extensions(context, program, settings.extensions)
        async with context.step("open"):
            opened = self.own(folder, str(file)) if file is not None else self.own(folder)
            if not await context.run_blocking(launch_program, [*program.gui, *opened]):
                raise WindowError(f"VS Code did not start: {program.gui[0]}")
            context.log(f"{folder} opened in Clank's VS Code window; OpenCode opens beside the files")
            if file is not None:
                context.log(f"{named} opened in it")
        found: dict[str, Any] = {"folder": folder, "installed": installed, "failed": failed}
        return {**found, "file": str(file)} if file is not None else found

    def _write_settings(self, context: OperationContext) -> None:
        file = self.folder / "data" / "User" / "settings.json"
        text = settings_text(file.read_text(encoding="utf-8") if file.is_file() else None)
        if text is None:
            return
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text, encoding="utf-8")
        context.log(f"its settings: {file}")

    async def _extensions(
        self, context: OperationContext, program: Program, extensions: list[str]
    ) -> tuple[list[str], list[str]]:
        """Install what is missing; the extensions installed and those that could not be."""
        listed = await context.run_blocking(self._run, program, ["--list-extensions", "--show-versions"], LIST_SECONDS)
        if not listed.ok:
            raise WindowError(f"VS Code did not list its extensions: {(listed.errors or listed.output).strip()}")
        have = installed_versions(listed.output)
        wanted: list[tuple[list[str], str]] = []
        vsix = clank_vsix()
        if vsix is None:
            context.log(
                "Clank's extension is not built (`uv run python -m tools.vsix` in Clank's folder builds it): the "
                "window opens without the agent beside the files"
            )
        elif (found := VSIX.fullmatch(vsix.name)) is None or have.get(CLANK) != found.group(1):
            wanted.append((["--install-extension", str(vsix), "--force"], CLANK))
        wanted += [(["--install-extension", name], name) for name in extensions if name.lower() not in have]
        installed, failed = [], []
        for arguments, name in wanted:
            answer = await context.run_blocking(self._run, program, arguments, INSTALL_SECONDS)
            if answer.ok:
                installed.append(name)
                context.log(f"{name} installed")
            else:
                failed.append(name)
                why = (answer.errors or answer.output).strip().splitlines()
                context.log(
                    f"{name} could not be installed ({why[-1] if why else answer.status}); tried again next time"
                )
        if not wanted:
            context.log("every extension is installed")
        return installed, failed

    def _run(self, program: Program, arguments: list[str], timeout: float) -> Answer:
        return run_answer([*program.cli, *self.own(*arguments)], timeout, env=program.env or None)


def _in_the_folder(named: str) -> bool:
    """Whether a file is named from the folder: with '/', no drive (`C:x.md` is relative to a drive's own folder on
    Windows), no root, no '..'."""
    windows, posix = PureWindowsPath(named), PurePosixPath(named)
    return not (windows.drive or windows.root or posix.is_absolute() or "\\" in named or ".." in posix.parts)
