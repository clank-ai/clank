"""Boards (design 0022): a canvas the owner and the agent share, a `.board` file of the folder (JSON: its title, its
settings and its items, drawn in order). The owner changes it in VS Code's board editor; the agent through Clank's
tools, which come here: `new`, `list`, `read` and `describe` (the board in words for the model), `add`, `update` and
`remove`. The agent places things by where (`boardplace.py`), never by pixels.

**The file is the board.** Each change of the agent's reads it fresh, changes it, keeps the board as it was in its
history (`.clank/boards/<board's path>/history/`, the newest `HISTORY` kept) and writes it whole, so the owner's latest
moves are never lost and any change of the agent's can be taken back; then `agents.board_changed` is recorded and the
owner's window draws it. Figures name their file and are sized from it (`image_size`: PNG, JPEG, GIF, WebP, SVG),
360 wide by default at their aspect, a caption's line under them. What a frame holds, and what an annotation is over,
follow from where they are: an item inside a frame's rectangle is in it, a pen stroke or pin over an item is on it.

**The agent adds** figures, LaTeX (math, drawn at once, or compiled), notes, slots, frames (around items it names) and
arrows between items; the owner's own marks (pen strokes, highlights, pins) are the owner's. A figure placed in a slot
takes the slot. Refused, saying why: a board that is not there or not a board, a figure not a file of the folder, a
kind the agent does not add, an item not on the board.
"""

import json
import math
import os
import re
import shutil
import struct
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from clank.components.agents.boardplace import GRID, INSET, TITLE, PlaceError, frame_of, place
from clank.kernel.events import CLANK, EventType, Subject

if TYPE_CHECKING:
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel

SUFFIX = ".board"
CONTAINER = "/workspace/"
FOLDER = ".clank/boards"
HISTORY = 50
CAPTION = 28  # a figure's caption line, under it
FIGURE_WIDTH = 360
ASPECT = 4 / 3  # a figure whose file cannot be measured
PREFIX = {"figure": "fig", "latex": "latex", "note": "note", "slot": "slot", "frame": "frame", "arrow": "arrow",
          "pen": "pen", "highlight": "mark", "pin": "pin"}  # fmt: skip
AGENT_KINDS = ("figure", "latex", "note", "slot", "frame", "arrow")
BOXED = ("figure", "latex", "note", "slot")
SKIPPED = {".clank", ".git", "node_modules", "__pycache__", ".venv"}
NAME = re.compile(r"[^a-z0-9]+")
EVENT_TYPES = [
    EventType(
        "agents.board_changed",
        "A board changed: made, or an item added, changed or taken away by the agent (design 0022).",
        {
            "workspace": "The workspace.", "board": "The board, from the folder.",
            "change": "new, add, update or remove.", "id": "The item.", "said": "The change in words.",
        },
    ),
]  # fmt: skip


class BoardError(Exception):
    """A board that cannot be read or changed as asked, and why."""


def image_size(path: Path) -> tuple[int, int] | None:
    """An image's width and height in pixels, from its file's head (PNG, JPEG, GIF, WebP) or an SVG's size or
    viewBox; None for a file that is not one of those."""
    try:
        head = path.read_bytes()[: 1 << 16] if path.suffix.lower() != ".svg" else b""
    except OSError:
        return None
    if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
        width, height = struct.unpack(">II", head[16:24])
        return int(width), int(height)
    if head[:6] in (b"GIF87a", b"GIF89a"):
        width, height = struct.unpack("<HH", head[6:10])
        return int(width), int(height)
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return _webp(head)
    if head[:2] == b"\xff\xd8":
        return _jpeg(head)
    if path.suffix.lower() == ".svg":
        return _svg(path)
    return None


def _jpeg(head: bytes) -> tuple[int, int] | None:
    at = 2
    while at + 9 < len(head):
        if head[at] != 0xFF:
            return None
        marker, length = head[at + 1], struct.unpack(">H", head[at + 2 : at + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            height, width = struct.unpack(">HH", head[at + 5 : at + 9])
            return int(width), int(height)
        at += 2 + length
    return None


def _webp(head: bytes) -> tuple[int, int] | None:
    kind = head[12:16]
    if kind == b"VP8 ":
        width, height = struct.unpack("<HH", head[26:30])
        return int(width & 0x3FFF), int(height & 0x3FFF)
    if kind == b"VP8L":
        bits = int.from_bytes(head[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if kind == b"VP8X":
        return int.from_bytes(head[24:27], "little") + 1, int.from_bytes(head[27:30], "little") + 1
    return None


def _svg(path: Path) -> tuple[int, int] | None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4096]
    except OSError:
        return None
    root = re.search(r"<svg\b[^>]*>", text)
    if not root:
        return None
    sizes = [re.search(rf'\b{name}="([\d.]+)(?:px)?"', root[0]) for name in ("width", "height")]
    if sizes[0] and sizes[1]:
        return round(float(sizes[0][1])), round(float(sizes[1][1]))
    view = re.search(r'viewBox="[\d.\-]+[ ,]+[\d.\-]+[ ,]+([\d.]+)[ ,]+([\d.]+)"', root[0])
    return (round(float(view[1])), round(float(view[2]))) if view else None


def _region(item: dict[str, Any], x: float, y: float) -> str:
    """Where a point is on an item, in words: its upper left ... its center ... its lower right."""
    across = (x - float(item["x"])) / max(float(item["w"]), 1.0)
    down = (y - float(item["y"])) / max(float(item["h"]), 1.0)
    row = "upper" if down < 1 / 3 else "lower" if down > 2 / 3 else "middle"
    column = "left" if across < 1 / 3 else "right" if across > 2 / 3 else "middle"
    return "center" if row == column == "middle" else f"{row} {column}"


class Boards:
    """The boards of the workspaces' folders."""

    def __init__(self, kernel: "Kernel") -> None:
        self.kernel = kernel

    # -- finding boards and files

    def _folder(self, workspace: str) -> Path:
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        try:
            return Path(workspaces.folder_of(workspace))
        except Exception as error:  # the workspaces' own refusal: no such workspace
            raise BoardError(f"there is no workspace {workspace!r}") from error

    @staticmethod
    def _relative(named: str) -> tuple[str, ...]:
        relative = named[len(CONTAINER) :] if named.startswith(CONTAINER) else named
        return PurePosixPath(relative.replace("\\", "/")).parts

    def _inside(self, folder: Path, named: str) -> Path:
        parts = self._relative(named)
        path = folder.joinpath(*parts)
        if (
            not parts
            or ".." in parts
            or parts[:1] == (".clank",)
            or not path.resolve().is_relative_to(folder.resolve())
        ):
            raise BoardError(f"{named} is not a file of the folder")
        return path

    def _board(self, workspace: str, board: str) -> tuple[Path, Path]:
        """The folder and the board's file: a path in the folder (with or without `.board`), or a board's bare name."""
        folder = self._folder(workspace)
        named = board if board.endswith(SUFFIX) else f"{board}{SUFFIX}"
        path = self._inside(folder, named)
        if path.is_file():
            return folder, path
        if "/" not in named.replace("\\", "/"):
            found = sorted(self._all(folder), key=lambda each: (len(each.parts), str(each)))
            matching = [each for each in found if each.name == named]
            if matching:
                return folder, matching[0]
        raise BoardError(f"there is no board {board} in {workspace}")

    @staticmethod
    def _all(folder: Path) -> list[Path]:
        found = []
        for root, dirs, files in os.walk(folder):
            dirs[:] = [each for each in dirs if each not in SKIPPED]
            found += [Path(root) / name for name in files if name.endswith(SUFFIX)]
        return found

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        try:
            board: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise BoardError(f"{path.name} is not a board Clank can read: {error}") from error
        if not isinstance(board.get("items"), list):
            raise BoardError(f"{path.name} is not a board: it has no items")
        return board

    def _save(self, folder: Path, path: Path, board: dict[str, Any], *, keep: bool) -> None:
        if keep and path.is_file():
            kept = folder / FOLDER / path.relative_to(folder).with_suffix("").as_posix().replace("/", "-") / "history"
            kept.mkdir(parents=True, exist_ok=True)
            older = sorted(kept.glob(f"*{SUFFIX}"), key=lambda each: int(each.stem))
            number = int(older[-1].stem) + 1 if older else 1
            shutil.copyfile(path, kept / f"{number}{SUFFIX}")
            for gone in older[: max(0, len(older) + 1 - HISTORY)]:
                gone.unlink(missing_ok=True)
        written = path.with_name(f".{path.name}.writing")
        written.write_text(json.dumps(board, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(written, path)

    def _record(self, workspace: str, board: str, change: str, item: str, said: str) -> None:
        self.kernel.events.record(
            "agents.board_changed", summary=f"{workspace}: {said}", actor=CLANK,
            subject=Subject(kind="workspace", id=workspace),
            data={"workspace": workspace, "board": board, "change": change, "id": item, "said": said},
        )  # fmt: skip

    # -- reading

    def new(self, workspace: str, name: str, *, folder: str = "", title: str = "") -> dict[str, Any]:
        """A new, empty board in the folder (in `folder` under it), named from `name`; its path from the folder."""
        root = self._folder(workspace)
        stem = NAME.sub("-", name.lower()).strip("-") or "board"
        place = self._inside(root, f"{folder.strip('/')}/{stem}{SUFFIX}" if folder.strip("/") else f"{stem}{SUFFIX}")
        if place.exists():
            raise BoardError(f"{place.relative_to(root).as_posix()} is already a board of the folder")
        place.parent.mkdir(parents=True, exist_ok=True)
        board = {"board": 1, "title": title or name, "settings": {"grid": GRID, "preamble": ""}, "items": []}
        self._save(root, place, board, keep=False)
        relative = place.relative_to(root).as_posix()
        self._record(workspace, relative, "new", "", f"the board {relative} made")
        return {"board": relative, "said": f"The board {relative} is made; it opens in the owner's VS Code window."}

    def boards(self, workspace: str) -> list[dict[str, Any]]:
        """The folder's boards, the newest changed first: each one's path, title and how many items it holds."""
        root = self._folder(workspace)
        found = []
        for path in self._all(root):
            try:
                board = self._load(path)
            except BoardError:
                continue
            found.append({"board": path.relative_to(root).as_posix(), "title": str(board.get("title") or path.stem),
                          "items": len(board["items"]), "changed": path.stat().st_mtime})  # fmt: skip
        return sorted(found, key=lambda each: -float(each["changed"]))

    def read(self, workspace: str, board: str) -> dict[str, Any]:
        """A board whole: its path, title, settings and items, and the board in words (`describe`)."""
        root, path = self._board(workspace, board)
        loaded = self._load(path)
        relative = path.relative_to(root).as_posix()
        return {"board": relative, "title": loaded.get("title", ""), "settings": loaded.get("settings", {}),
                "items": loaded["items"], "said": self._words(relative, loaded)}  # fmt: skip

    def describe(self, workspace: str, board: str) -> str:
        """The board in words for the model (module docstring)."""
        return str(self.read(workspace, board)["said"])

    def _words(self, relative: str, board: dict[str, Any]) -> str:
        items = board["items"]
        by_id = {str(each.get("id")): each for each in items}
        lines = [f'The board {relative}, "{board.get("title", "")}": {len(items)} items (x right, y down, in pixels).']
        for item in items:
            line = self._item_words(item, items, by_id)
            if line:
                lines.append(line)
        return "\n".join(lines)

    def _over(self, items: list[dict[str, Any]], x: float, y: float) -> tuple[dict[str, Any], str] | None:
        for item in reversed(items):
            if item.get("kind") in BOXED and float(item["x"]) <= x <= float(item["x"]) + float(item["w"]) \
                    and float(item["y"]) <= y <= float(item["y"]) + float(item["h"]):  # fmt: skip
                return item, _region(item, x, y)
        return None

    def _item_words(self, item: dict[str, Any], items: list[dict[str, Any]], by_id: dict[str, Any]) -> str:
        kind, id = item.get("kind"), item.get("id")
        where = f"at ({item.get('x')}, {item.get('y')}), {item.get('w')} by {item.get('h')}"
        if kind == "figure":
            caption = f', "{item["caption"]}"' if item.get("caption") else ""
            return f"{id}: figure {item.get('file')}{caption}, {where}"
        if kind == "latex":
            return f"{id}: LaTeX ({item.get('mode', 'math')}) {json.dumps(item.get('source', ''))}, {where}"
        if kind == "note":
            return f"{id}: note {json.dumps(item.get('text', ''))}, {where}"
        if kind == "slot":
            return f'{id}: slot "{item.get("label", "")}", open, waits to be filled, {where}'
        if kind == "frame":
            held = [str(each["id"]) for each in items if each is not item and each.get("kind") in BOXED
                    and frame_of(items, each) is item]  # fmt: skip
            return f'{id}: frame "{item.get("name", "")}", holds {", ".join(held) or "nothing"}, {where}'
        if kind == "arrow":
            ends = [self._end(item.get(side) or {}, items) for side in ("from", "to")]
            return f"{id}: an arrow from {ends[0]} to {ends[1]}"
        if kind == "pen":
            points = item.get("points") or []
            if not points:
                return ""
            xs, ys = [float(p[0]) for p in points], [float(p[1]) for p in points]
            closed = len(points) > 2 and math.dist(points[0], points[-1]) < max(24.0, 0.3 * math.dist(
                (min(xs), min(ys)), (max(xs), max(ys))))  # fmt: skip
            over = self._over(items, (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
            shape = "a pen loop around" if closed else "a pen mark on"
            return f"{id}: {shape} the {over[1]} of {over[0]['id']}" if over else f"{id}: a pen mark on the board"
        if kind in ("highlight", "pin"):
            x = float(item.get("x", 0)) + float(item.get("w", 0)) / 2
            y = float(item.get("y", 0)) + float(item.get("h", 0)) / 2
            over = self._over(items, x, y)
            place_said = f"on the {over[1]} of {over[0]['id']}" if over else "on the board"
            if kind == "highlight":
                return f"{id}: a highlight {place_said}"
            state = "open" if item.get("open", True) else "answered"
            return f'{id}: a pin {place_said}, {state}: "{item.get("text", "")}"'
        return ""

    def _end(self, end: dict[str, Any], items: list[dict[str, Any]]) -> str:
        if end.get("item"):
            return str(end["item"])
        over = self._over(items, float(end.get("x", 0)), float(end.get("y", 0)))
        return f"the {over[1]} of {over[0]['id']}" if over else f"({end.get('x')}, {end.get('y')})"

    # -- changing

    def _size(self, root: Path, kind: str, fields: dict[str, Any]) -> tuple[float, float]:
        width = float(fields.get("w") or 0)
        if kind == "figure":
            measured = image_size(self._inside(root, str(fields["file"])))
            aspect = measured[0] / measured[1] if measured and measured[1] else ASPECT
            width = width or FIGURE_WIDTH
            return width, round(width / aspect) + (CAPTION if fields.get("caption") else 0)
        if kind == "latex":
            source = str(fields.get("source", ""))
            if fields.get("mode") == "compiled":
                return width or 360, float(fields.get("h") or 240)
            return width or min(640, max(160, 10 * len(source))), float(fields.get("h") or 80)
        if kind == "note":
            width = width or 280
            lines = sum(max(1, math.ceil(len(line) / 34)) for line in str(fields.get("text", "")).splitlines() or [""])
            return width, float(fields.get("h") or min(600, max(80, 48 + 22 * lines)))
        if kind == "slot":
            return width or 320, float(fields.get("h") or 220)
        return width or 640, float(fields.get("h") or 420)

    def _checked(self, root: Path, kind: str, fields: dict[str, Any]) -> dict[str, Any]:
        if kind not in AGENT_KINDS:
            raise BoardError("the agent adds figures, LaTeX, notes, slots, frames and arrows; the pen, highlights and "
                             "pins are the owner's")  # fmt: skip
        kept = {key: value for key, value in fields.items() if key not in ("x", "y", "w", "h", "around", "id", "kind")}
        if kind == "figure":
            path = self._inside(root, str(fields.get("file") or ""))
            if not path.is_file():
                raise BoardError(f"{fields.get('file')} is not a file of the folder")
            kept["file"] = path.relative_to(root).as_posix()
        if kind == "latex":
            if not str(fields.get("source", "")).strip():
                raise BoardError("LaTeX on a board needs its source")
            kept["mode"] = "compiled" if fields.get("mode") == "compiled" else "math"
        if kind == "note" and not str(fields.get("text", "")).strip():
            raise BoardError("a note needs its text")
        if kind == "slot":
            kept["label"] = str(fields.get("label") or "a figure")
            kept["state"] = "open"
        if kind == "frame":
            kept["name"] = str(fields.get("name") or "Frame")
        return kept

    def add(self, workspace: str, board: str, kind: str, fields: dict[str, Any],
            at: dict[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
        """Add an item, placed by `at` (`boardplace.py`); its id and the change in words."""
        root, path = self._board(workspace, board)
        loaded = self._load(path)
        items: list[dict[str, Any]] = loaded["items"]
        kept = self._checked(root, kind, fields)
        number = 1 + max((int(m[1]) for each in items if (m := re.search(r"-(\d+)$", str(each.get("id"))))), default=0)
        id = f"{PREFIX[kind]}-{number}"
        said = ""
        if kind == "arrow":
            for side in ("from", "to"):
                end = fields.get(side)
                if not (isinstance(end, dict) and (end.get("item") in {str(each.get("id")) for each in items}
                                                   or {"x", "y"} <= end.keys())):  # fmt: skip
                    raise BoardError(f'an arrow\'s {side} is an item of the board ({{"item": "fig-1"}}) or a place')
            items.append({"id": id, "kind": "arrow", "from": fields["from"], "to": fields["to"], "by": "agent"})
            said = f"Drew {id} from {self._end(fields['from'], items)} to {self._end(fields['to'], items)}"
        elif kind == "frame" and fields.get("around"):
            held = [each for each in items if str(each.get("id")) in {str(name) for name in fields["around"]}]
            if not held:
                raise BoardError("a frame is put around items of the board: name them by id")
            left = min(float(each["x"]) for each in held) - INSET
            top = min(float(each["y"]) for each in held) - TITLE
            right = max(float(each["x"]) + float(each["w"]) for each in held) + INSET
            bottom = max(float(each["y"]) + float(each["h"]) for each in held) + INSET
            items.insert(0, {"id": id, "kind": "frame", "x": round(left), "y": round(top), "w": round(right - left),
                             "h": round(bottom - top), **kept, "by": "agent"})  # fmt: skip
            said = f'Framed {", ".join(str(each["id"]) for each in held)} as {id} "{kept["name"]}"'
        else:
            width, height = self._size(root, kind, fields)
            try:
                placed = place(items, width, height, at)
            except PlaceError as error:
                raise BoardError(str(error)) from error
            x, y, w, h = placed.box
            item = {"id": id, "kind": kind, "x": x, "y": y, "w": w, "h": h, **kept, "by": "agent"}
            if placed.taken:
                at_slot = next(index for index, each in enumerate(items) if each.get("id") == placed.taken)
                items[at_slot] = item
            else:
                (items.insert(0, item) if kind == "frame" else items.append(item))
            self._grow(items, placed.grown)
            what = kept.get("file") or kept.get("label") or kept.get("name") or kind
            said = f"Placed {id} ({what})" + (f" in the slot {placed.taken}" if placed.taken else
                                               f" {self._at_words(at)}")  # fmt: skip
        self._save(root, path, loaded, keep=True)
        relative = path.relative_to(root).as_posix()
        self._record(workspace, relative, "add", id, f"{relative}: {said}")
        return {"board": relative, "id": id, "said": f"{said} on {relative}. The owner sees it at once."}

    @staticmethod
    def _at_words(at: dict[str, Any] | None) -> str:
        if not at:
            return "under everything"
        for key, words in (("right_of", "right of"), ("left_of", "left of"), ("below", "below"), ("above", "above"),
                           ("in", "in")):  # fmt: skip
            if key in at:
                return f"{words} {at[key]}"
        return f"at ({at.get('x')}, {at.get('y')})"

    @staticmethod
    def _grow(items: list[dict[str, Any]], grown: tuple[str, int, int] | None) -> None:
        if grown is None:
            return
        for each in items:
            if each.get("id") == grown[0]:
                each["w"], each["h"] = grown[1], grown[2]

    def update(self, workspace: str, board: str, id: str, changes: dict[str, Any],
               at: dict[str, Any] | None = None) -> dict[str, Any]:  # fmt: skip
        """Change an item's words, size or place (`at`, as `add` takes it); the change in words."""
        root, path = self._board(workspace, board)
        loaded = self._load(path)
        items: list[dict[str, Any]] = loaded["items"]
        item = next((each for each in items if each.get("id") == id), None)
        if item is None:
            raise BoardError(f"there is no item {id} on the board")
        allowed = {"caption", "source", "mode", "text", "label", "name", "file", "w", "h"}
        unknown = sorted(set(changes) - allowed)
        if unknown:
            raise BoardError(f"an item's {', '.join(unknown)} cannot be changed: change {', '.join(sorted(allowed))}")
        if "file" in changes:
            changes = {**changes, "file": self._checked(root, "figure", {"file": changes["file"]})["file"]}
        item.update({key: value for key, value in changes.items() if key not in ("w", "h")})
        if item.get("kind") in ("figure", "latex", "note") and (
            {"caption", "file", "text", "source", "w", "h"} & set(changes)
        ):
            width, height = self._size(root, str(item["kind"]), {**item, "w": changes.get("w", item.get("w")),
                                                                 "h": changes.get("h")})  # fmt: skip
            item["w"], item["h"] = round(width), round(height)
        if at:
            others = [each for each in items if each is not item]
            try:
                placed = place(others, float(item["w"]), float(item["h"]), at)
            except PlaceError as error:
                raise BoardError(str(error)) from error
            item["x"], item["y"], item["w"], item["h"] = placed.box
            if placed.taken:
                items.remove(next(each for each in items if each.get("id") == placed.taken))
            self._grow(items, placed.grown)
        self._save(root, path, loaded, keep=True)
        relative = path.relative_to(root).as_posix()
        said = f"Changed {id}" + (f", moved {self._at_words(at)}" if at else "")
        self._record(workspace, relative, "update", id, f"{relative}: {said}")
        return {"board": relative, "id": id, "said": f"{said} on {relative}."}

    def remove(self, workspace: str, board: str, id: str) -> dict[str, Any]:
        """Take an item away; the change in words."""
        root, path = self._board(workspace, board)
        loaded = self._load(path)
        items: list[dict[str, Any]] = loaded["items"]
        if not any(each.get("id") == id for each in items):
            raise BoardError(f"there is no item {id} on the board")
        loaded["items"] = [each for each in items if each.get("id") != id]
        self._save(root, path, loaded, keep=True)
        relative = path.relative_to(root).as_posix()
        self._record(workspace, relative, "remove", id, f"{relative}: took {id} away")
        return {"board": relative, "id": id, "said": f"Took {id} away from {relative}; its history keeps it."}
