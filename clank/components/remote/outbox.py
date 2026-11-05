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
from clank.kernel.infolder import place

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
    """Whether `file` is a sent file's own name: no folder, and not a note."""
    folders = "/" in file or "\\" in file
    return bool(file) and not folders and file not in (".", "..") and not file.endswith(".json")


def files(workspaces: list[tuple[str, str]], limit: int = 100) -> list[dict[str, Any]]:
    """The files sent from these workspaces (name, folder), the newest first."""
    found: list[dict[str, Any]] = []
    for name, folder in workspaces:
        with contextlib.suppress(ValueError):  # Outside: a folder whose name leaves it
            box = place(folder, OUTBOX)
            for note, kind in box.entries():  # links left out
                if kind != "file" or not note.endswith(".json"):
                    continue
                with contextlib.suppress(OSError, ValueError, TypeError, OverflowError):  # a note the agent broke
                    said = json.loads((box / note).read_text())
                    file = str(said.get("file") or "")
                    info = (box / file).stat() if _plain(file) else None
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
    (or the name is not a plain one, or it is reached through a link)."""
    if not _plain(file):
        return None
    try:
        return place(folder, f"{OUTBOX}/{file}").read_bytes(most=LARGEST)
    except (OSError, ValueError):  # Outside too, a ValueError
        return None
