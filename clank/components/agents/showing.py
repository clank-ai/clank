"""Showing files to the owner (design 0018 §7.1): the agent names files of a workspace's folder, and Clank's VS Code
window opens them on the left, beside OpenCode.

`show` takes the paths as the model gave them, each named from the folder or under `/workspace` (the folder as the
container sees it). The files of the folder are opened: the event `agents.shown` (the workspace, its folder on this
machine, the files from the folder, and why), which the window on that folder follows (`vscode/src/core/show.ts`).
Each path that is not a file of the folder (outside it, or missing) is named in the answer and the rest are opened;
with none left, too many, or no VS Code window following the service (`windows`), nothing is opened and the error says
why, so the model tells the owner the paths instead. The answer tells the model the owner looks at the files
themselves: when the owner asks to see something, the model opens it and stops.
"""

from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import TYPE_CHECKING, Any

from clank.kernel.events import Actor, EventType, Subject

if TYPE_CHECKING:
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel

AGENT = Actor(kind="session", via="the agent")  # who asks, through the gateway
MOST = 12  # files opened at once
CONTAINER = "/workspace/"  # the folder, as the container sees it
EVENT_TYPES = [
    EventType(
        "agents.shown",
        "The agent opened files of a folder for you in Clank's VS Code window (design 0018 §7).",
        {
            "workspace": "The workspace.", "folder": "Its folder, on this machine.",
            "files": "The files opened, from the folder.", "why": "Why, in the agent's words.",
        },
    )
]  # fmt: skip


class ShowError(Exception):
    """Files that cannot be opened for the owner, and why."""


class Showing:
    """The files the agents open for the owner."""

    def __init__(self, kernel: "Kernel") -> None:
        self.kernel = kernel

    def show(self, workspace: str, paths: list[str], why: str, *, windows: bool) -> dict[str, Any]:
        """Open the files of the workspace's folder among `paths` in the owner's VS Code window; what was opened, what
        was not a file of the folder, and the words for the model."""
        if not paths:
            raise ShowError("name the files to open, from the folder (plots/residual.png)")
        if len(paths) > MOST:
            raise ShowError(f"at most {MOST} files at once: open the ones the owner asked for")
        root = self._folder(workspace)
        files: list[str] = []
        missing: list[str] = []
        for path in paths:
            found = _in_folder(root, path)
            if found is None:
                missing.append(path)
            elif found not in files:
                files.append(found)
        if not files:
            raise ShowError(f"none of these is a file of the folder: {', '.join(missing)}")
        if not windows:
            raise ShowError(
                "No VS Code window follows Clank now, so nothing was opened: tell the owner where the files are "
                f"({', '.join(files)})."
            )
        self.kernel.events.record(
            "agents.shown",
            summary=f"the agent opened {', '.join(files)} in {workspace}'s VS Code window",
            actor=AGENT,
            subject=Subject(kind="workspace", id=workspace),
            data={"workspace": workspace, "folder": str(root), "files": files, "why": why.strip()},
        )
        them = "it" if len(files) == 1 else "them"
        said = (
            f"Opened {_listed(files)} in the owner's VS Code window, on the left. The owner looks at {them} themselves:"
            f" say in a line what you opened, and do not read, describe or check {them} unless the owner asks."
        )
        if missing:
            said += f" Not opened, not files of the folder: {', '.join(missing)}."
        return {"workspace": workspace, "files": files, "missing": missing, "said": said}

    def _folder(self, workspace: str) -> Path:
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        for record in workspaces.records():
            if record["name"] == workspace:
                return Path(record["path"])
        raise ShowError(f"there is no workspace {workspace!r}")


def _in_folder(root: Path, path: str) -> str | None:
    """The path from the folder when it names a file of it (from the folder, or under `/workspace`); else None."""
    named = path.strip()
    if named.startswith(CONTAINER):
        named = named[len(CONTAINER) :]
    windows, posix = PureWindowsPath(named), PurePosixPath(named)
    if not named or windows.drive or windows.root or posix.is_absolute() or "\\" in named or ".." in posix.parts:
        return None
    file = root.joinpath(*posix.parts)
    try:
        inside = file.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return inside.as_posix() if file.is_file() else None


def _listed(files: list[str]) -> str:
    return files[0] if len(files) == 1 else f"{', '.join(files[:-1])} and {files[-1]}"
