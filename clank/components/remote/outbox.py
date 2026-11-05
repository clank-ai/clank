"""The files the agents sent to the phone (design 0005 §3): each workspace's `.clank/outbox/`, where Clank's own MCP
server (`send_to_phone`) puts a copy of the file with a `.json` beside it (its caption, where it came from, when).

The folders are on this machine, so the service reads them directly, through no link (`kernel/infolder.py`, decision
0164). A file is served only from an outbox, by its name as listed (no path), and never its note. Only an inert kind of
file is served to be seen in place, by its name's ending (`SEEN`: raster images, PDF, plain text); any other is served
as a download (`SAVED`), since a file the agent wrote must never run as the phone's app (decision 0157).
"""

import contextlib
import json
import stat
from datetime import UTC, datetime
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

from clank.kernel.clock import to_text
from clank.kernel.infolder import Place, place

OUTBOX = ".clank/outbox"
LARGEST = 50 << 20  # what Clank's MCP server sends at most (`phone_mcp.LARGEST`)
SEEN = {  # the kinds of file served to be seen in place, by their names' endings: none of them runs anything
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".pdf": "application/pdf", ".txt": "text/plain",
}  # fmt: skip
SAVED = "application/octet-stream"  # any other file: a download, never shown as its own kind


def served_type(file: str) -> str:
    """The type a sent file is served as: its own when it is of a kind seen in place, else a download's."""
    return SEEN.get(PurePosixPath(file).suffix.lower(), SAVED)


def disposition(shown: str, file: str) -> str:
    """A sent file's `Content-Disposition`: `inline` or `attachment`, with its name (RFC 5987 when it is not plain)."""
    quoted = quote(file)
    return f"{shown}; filename*=utf-8''{quoted}" if quoted != file else f'{shown}; filename="{file}"'


def _plain(file: str) -> bool:
    """Whether `file` can be a sent file's own name: no folder in it."""
    folders = "/" in file or "\\" in file
    return bool(file) and not folders and file not in (".", "..")


def _note(box: Place, file: str) -> dict[str, Any] | None:
    """A sent file's note, as Clank's MCP server writes it: `<file>.json` beside it, an object naming that file; None
    for a file no note names (a note itself, a JSON file sent, a stray) or a note the agent broke."""
    try:
        said = json.loads((box / f"{file}.json").read_text())
    except (OSError, ValueError):  # Outside too, a ValueError
        return None
    return said if isinstance(said, dict) and said.get("file") == file else None


def files(workspaces: list[tuple[str, str]], limit: int = 100) -> list[dict[str, Any]]:
    """The files sent from these workspaces (name, folder), the newest first."""
    found: list[dict[str, Any]] = []
    for name, folder in workspaces:
        with contextlib.suppress(ValueError):  # Outside: a folder whose name leaves it
            box = place(folder, OUTBOX)
            present = {entry for entry, kind in box.entries() if kind == "file"}  # links left out
            for file in sorted(present):
                if f"{file}.json" not in present or (said := _note(box, file)) is None:
                    continue  # a note, or a file no note names
                with contextlib.suppress(OSError, ValueError, TypeError, OverflowError):  # a note the agent broke
                    info = (box / file).stat()
                    if info is None or not stat.S_ISREG(info.st_mode):
                        continue
                    when = float(said.get("sent") or 0.0)
                    found.append({
                        "workspace": name, "file": file, "caption": str(said.get("caption") or ""),
                        "from": str(said.get("from") or ""), "sent": when,
                        "time": to_text(datetime.fromtimestamp(when, UTC)), "size": info.st_size,
                        "mime": served_type(file),
                    })  # fmt: skip
    return sorted(found, key=lambda each: -each["sent"])[:limit]


def read_sent(folder: str, file: str) -> bytes | None:
    """The bytes of the sent file of this name in a workspace's outbox, read through no link; None when there is none
    (or the name is not a plain one, no note names it, or it is reached through a link)."""
    if not _plain(file):
        return None
    try:
        box = place(folder, OUTBOX)
        if _note(box, file) is None:
            return None
        return (box / file).read_bytes(most=LARGEST)
    except (OSError, ValueError):  # Outside too, a ValueError
        return None
