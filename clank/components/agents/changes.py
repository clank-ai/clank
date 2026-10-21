"""A change the agent asks to make to a file (design 0007 §5): the file as it would be after it, its diff, and where
each change is kept.

OpenCode's ask names the file and gives a diff, but that diff has the indentation its lines share removed (for its
terminal), so it cannot be applied as it is (design 0007 §2). `proposed` works the file out from the tool call when it
applies exactly (a write's content; an edit whose old text is found once, or everywhere when it replaces all), else from
the diff: its lines placed by their numbers, each kept line checked against the file, the removed indentation taken
from the file's own lines; None when even that does not fit the file (it changed since). `unified` is the diff the
clients show, made from the file before and after, with its counts. `ChangeStore` keeps each change as a JSON file in
`state/changes/` (the newest `KEPT`), so a client reads it again after a restart and the owner can see every one.
"""

import difflib
import json
import re
import threading
from pathlib import Path
from typing import Any

KEPT = 200
NAME = re.compile(r"^[A-Za-z0-9_-]{1,100}$")  # a change's id: OpenCode's permission id (per_...)
HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def proposed(before: str | None, given: dict[str, Any] | None, diff: str) -> tuple[str | None, bool]:
    """The file as the change would leave it, and whether that is exact (from the tool call) or worked out from the
    diff; None when it cannot be worked out."""
    if given is not None:
        exact = _from_tool(before, given)
        if exact is not None:
            return exact, True
    return _from_diff(before, diff), False


def _from_tool(before: str | None, given: dict[str, Any]) -> str | None:
    if isinstance(given.get("content"), str):
        return str(given["content"])
    old, new = given.get("oldString"), given.get("newString")
    if not isinstance(old, str) or not isinstance(new, str):
        return None
    if old == "":
        return new  # OpenCode writes the new text as the whole file
    if before is None:
        return None
    found = before.count(old)
    if given.get("replaceAll") and found:
        return before.replace(old, new)
    return before.replace(old, new, 1) if found == 1 else None


def _from_diff(before: str | None, diff: str) -> str | None:
    """The diff applied to the file by its line numbers; its lines' shared indentation, which OpenCode removed, taken
    back from the file's lines it keeps or removes."""
    text = before or ""
    crlf = "\r\n" in text
    lines = text.replace("\r\n", "\n").split("\n")
    ends = text.endswith("\n") or not text
    if ends:
        lines = lines[:-1]
    hunks = _hunks(diff)
    if not hunks:
        return None
    cut, indent = _indentation(lines, hunks)
    if cut is None:
        return None
    result: list[str] = []
    at = 0  # the next line of the file not yet placed
    for start, body in hunks:
        if start < at:
            return None
        result += lines[at:start]
        at = start
        for sign, said in body:
            if sign == "+":
                result.append(indent + said if said else "")
                continue
            if at >= len(lines) or not _same(lines[at], said, cut):
                return None
            if sign == " ":
                result.append(lines[at])
            at += 1
    result += lines[at:]
    if diff.rstrip("\n").endswith("\\ No newline at end of file") and hunks[-1][1] and hunks[-1][1][-1][0] == "+":
        ends = False
    joined = "\n".join(result) + ("\n" if ends and result else "")
    return joined.replace("\n", "\r\n") if crlf else joined


def _hunks(diff: str) -> list[tuple[int, list[tuple[str, str]]]]:
    """Each hunk of a unified diff: the file's line it starts at (from 0), and its lines (sign and text)."""
    hunks: list[tuple[int, list[tuple[str, str]]]] = []
    for line in diff.replace("\r\n", "\n").split("\n"):
        header = HUNK.match(line)
        if header:
            first, count = int(header.group(1)), header.group(2)
            hunks.append((first if count == "0" else first - 1, []))
        elif hunks and line[:1] in (" ", "-", "+"):
            hunks[-1][1].append((line[0], line[1:]))
    return hunks


def _indentation(lines: list[str], hunks: list[tuple[int, list[tuple[str, str]]]]) -> tuple[int | None, str]:
    """How many characters of indentation OpenCode removed from every line, and those characters as the file has
    them; (None, "") when a kept or removed line does not fit the file."""
    for start, body in hunks:
        at = start
        for sign, said in body:
            if sign == "+":
                continue
            if at >= len(lines):
                return None, ""
            line = lines[at]
            if said.strip() and line.endswith(said):
                cut = len(line) - len(said)
                return (cut, line[:cut]) if not line[:cut].strip() else (None, "")
            at += 1
    return 0, ""


def _same(line: str, said: str, cut: int) -> bool:
    """Whether a line of the file is the diff's line with `cut` characters of indentation removed."""
    if not said.strip():
        return not line.strip()
    return line[cut:] == said and not line[:cut].strip()


def unified(before: str | None, after: str, relative: str) -> tuple[str, int, int]:
    """The diff from the file before to after, as clients show it, and how many lines it adds and removes."""
    old = (before or "").replace("\r\n", "\n").splitlines()
    new = after.replace("\r\n", "\n").splitlines()
    source = f"a/{relative}" if before is not None else "/dev/null"
    lines = list(difflib.unified_diff(old, new, source, f"b/{relative}", lineterm=""))
    added = sum(1 for line in lines[2:] if line.startswith("+"))
    removed = sum(1 for line in lines[2:] if line.startswith("-"))
    return "\n".join(lines) + ("\n" if lines else ""), added, removed


class ChangeStore:
    """The changes, one JSON file each in a folder, the newest `KEPT` kept."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        self._lock = threading.Lock()

    def save(self, change: dict[str, Any]) -> None:
        """Keep a change (replacing what was kept of it), then forget the oldest beyond `KEPT`."""
        with self._lock:
            self.folder.mkdir(parents=True, exist_ok=True)
            path = self._path(change["id"])
            path.with_suffix(".part").write_text(json.dumps(change, ensure_ascii=False), encoding="utf-8")
            path.with_suffix(".part").replace(path)
            kept = sorted(self.folder.glob("*.json"), key=lambda each: each.stat().st_mtime_ns)
            for old in kept[:-KEPT]:
                old.unlink(missing_ok=True)

    def get(self, id: str) -> dict[str, Any] | None:
        """A change, or None when it is not kept (or the id is not a change's)."""
        if not NAME.match(id):
            return None
        try:
            found: dict[str, Any] = json.loads(self._path(id).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return found

    def recent(self, workspace: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """The newest changes first (of one workspace, when named), without the files' contents."""
        found = []
        for path in sorted(self.folder.glob("*.json"), key=lambda each: each.stat().st_mtime_ns, reverse=True):
            change = self.get(path.stem)
            if change is None or (workspace is not None and change["workspace"] != workspace):
                continue
            found.append({key: value for key, value in change.items() if key not in ("before", "after", "made")})
            if len(found) >= limit:
                break
        return found

    def _path(self, id: str) -> Path:
        return self.folder / f"{id}.json"
