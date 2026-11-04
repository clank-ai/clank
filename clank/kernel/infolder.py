"""Files in a workspace's folder that Clank reads or writes as the owner (decision 0159).

The agent writes the folder (it is mounted into the agent's container), so it can put a link anywhere in it, `.clank/`
included, where Clank keeps the artifacts' versions and exports, the boards' history, the jobs' records and logs and
the figures' copies. Clank follows no link there: `inside` gives the path of a file below the folder only when its name
stays below it (not absolute, no `..`) and nothing on the way to it, the file itself included, is a link (a symbolic
link; on Windows also a junction, or any other reparse point that names another place). A name not there yet is fine:
Clank is about to make it. Anything else is `Outside`, a `ValueError`, whose words name the path.
"""

import os
import stat
import sys
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

NAME_SURROGATE = 0x20000000  # a reparse point that stands for another name: a symbolic link, a junction, WSL's links


class Outside(ValueError):
    """A path of the folder that leaves it, or passes through a link."""


def linked(path: Path) -> bool:
    """Whether `path` is itself a link: a symbolic link, or on Windows a reparse point that names another place. False
    when it is not there."""
    try:
        found = os.lstat(path)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(found.st_mode):
        return True
    if sys.platform == "win32":
        tag = getattr(found, "st_reparse_tag", 0)
        return bool(found.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT) and bool(tag & NAME_SURROGATE)
    return False


def inside(folder: Path, relative: str | PurePath) -> Path:
    """`folder` joined with `relative` (its parts parted by either slash), when the name stays below the folder and
    nothing on the way to it is a link (the module's docstring); `Outside` otherwise."""
    text = str(relative).replace("\\", "/")
    parts = [part for part in PurePosixPath(text).parts if part not in ("", ".")]
    climbs = ".." in parts or any(":" in part for part in parts)  # a drive, or a Windows file's other stream
    if not parts or text.startswith("/") or PureWindowsPath(text).drive or climbs:
        raise Outside(f"{relative} is not a path inside the folder")
    path = folder
    for part in parts:
        path = path / part
        if linked(path):
            raise Outside(f"{path.relative_to(folder).as_posix()} is a link: Clank follows no link in the folder")
    return path
