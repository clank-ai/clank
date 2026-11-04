"""The files the agents sent to the phone (design 0005 §3): each workspace's `.clank/outbox/`, where Clank's own MCP
server (`send_to_phone`) puts a copy of the file with a `.json` beside it (its caption, where it came from, when).

The folders are on this machine, so the service reads them directly. A file is served only from an outbox, by its
name as listed (no path), and never its note. Only an inert kind of file is served to be seen in place, by its name's
ending (`SEEN`: raster images, PDF, plain text); any other is served as a download (`SAVED`), since a file the agent
wrote must never run as the phone's app (decision 0157).
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from clank.kernel.clock import to_text

OUTBOX = Path(".clank") / "outbox"
SEEN = {  # the kinds of file served to be seen in place, by their names' endings: none of them runs anything
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
    ".pdf": "application/pdf", ".txt": "text/plain",
}  # fmt: skip
SAVED = "application/octet-stream"  # any other file: a download, never shown as its own kind


def served_type(file: str) -> str:
    """The type a sent file is served as: its own when it is of a kind seen in place, else a download's."""
    return SEEN.get(Path(file).suffix.lower(), SAVED)


def files(workspaces: list[tuple[str, str]], limit: int = 100) -> list[dict[str, Any]]:
    """The files sent from these workspaces (name, folder), the newest first."""
    found: list[dict[str, Any]] = []
    for name, folder in workspaces:
        box = Path(folder) / OUTBOX
        if not box.is_dir():
            continue
        for note in box.glob("*.json"):
            try:
                said = json.loads(note.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            sent = box / str(said.get("file") or "")
            if not isinstance(said, dict) or not sent.is_file() or sent.parent != box:
                continue
            when = float(said.get("sent") or 0.0)
            found.append({
                "workspace": name, "file": sent.name, "caption": str(said.get("caption") or ""),
                "from": str(said.get("from") or ""), "sent": when, "time": to_text(datetime.fromtimestamp(when, UTC)),
                "size": sent.stat().st_size, "mime": served_type(sent.name),
            })  # fmt: skip
    return sorted(found, key=lambda each: -each["sent"])[:limit]


def path_of(folder: str, file: str) -> Path | None:
    """The sent file of this name in a workspace's outbox; None when there is none (or the name is not a plain one)."""
    box = Path(folder) / OUTBOX
    if not file or Path(file).name != file or file.endswith(".json"):
        return None
    path = box / file
    return path if path.is_file() and path.resolve().parent == box.resolve() else None
