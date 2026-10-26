"""Where a new item goes on a board (design 0022 §4): the agent says where ("below fig-2", "in the frame Figure 3", "in
the slot"), never pixels, and this works out the place. Pure: `boards.py` reads the board and writes the result.

- **Beside or under an item** (`right_of`, `left_of`, `below`, `above`): aligned with it (tops beside it, left edges
  under or over it), `GAP` away, on the grid. A place that overlaps another item (each kept `GAP` clear) moves on:
  down when beside, right when under or over, until it overlaps none. An item placed by one inside a frame is in that
  frame: the frame grows to hold it.
- **In a slot** (`slot`): the item fills the slot, its aspect kept, centered in it, and the slot is taken (`taken`).
- **In a frame** (`in`): the first free place inside it, row by row below its name, on the grid; a frame too full for
  it grows (`grown`: the frame's new width and height).
- **At a place** (`{x, y}`): there, on the grid. **Nowhere said**: a new row under everything, at the board's left edge.

Frames are not in the way of items: they hold them. Annotations (pen strokes, arrows, highlights, pins) are never in
the way either.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

GRID = 20
GAP = 2 * GRID
START = 80  # an empty board's first item, from its corner
INSET = GRID  # a frame's items from its sides
TITLE = 2 * GRID  # and from its top, under its name
SOLID = {"figure", "latex", "note", "slot"}  # what a new item may not overlap
TRIES = 500


class PlaceError(Exception):
    """A place that cannot be worked out, and why."""


@dataclass(frozen=True)
class Placed:
    """Where the item goes, the slot it takes, and the frame that grows to hold it."""

    box: tuple[int, int, int, int]
    taken: str | None = None
    grown: tuple[str, int, int] | None = None


def snap(value: float, grid: int = GRID) -> int:
    """A length on the grid: the nearest multiple of its step."""
    return int(round(value / grid) * grid)


def _box(item: Mapping[str, Any]) -> tuple[float, float, float, float]:
    return float(item["x"]), float(item["y"]), float(item["w"]), float(item["h"])


def _overlaps(a: tuple[float, float, float, float], b: tuple[float, float, float, float], clear: float) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw + clear and bx < ax + aw + clear and ay < by + bh + clear and by < ay + ah + clear


def _inside(inner: tuple[float, float, float, float], outer: tuple[float, float, float, float]) -> bool:
    ix, iy, iw, ih = inner
    ox, oy, ow, oh = outer
    return ox <= ix and oy <= iy and ix + iw <= ox + ow and iy + ih <= oy + oh


def frame_of(items: Sequence[Mapping[str, Any]], item: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The smallest frame that holds the item whole, if one does."""
    holding = [each for each in items if each.get("kind") == "frame" and each is not item
               and _inside(_box(item), _box(each))]  # fmt: skip
    return min(holding, key=lambda each: float(each["w"]) * float(each["h"]), default=None)


def place(
    items: Sequence[Mapping[str, Any]], w: float, h: float, at: Mapping[str, Any] | None, grid: int = GRID
) -> Placed:
    """Where an item of `w` by `h` goes on a board holding `items`, as `at` says (module docstring)."""
    by_id = {str(each.get("id")): each for each in items}

    def named(key: str) -> Mapping[str, Any]:
        found = by_id.get(str(at[key])) if at else None
        if found is None:
            raise PlaceError(f"there is no item {at[key] if at else ''} on the board")
        return found

    solid = [_box(each) for each in items if each.get("kind") in SOLID]
    if at and "slot" in at:
        slot = named("slot")
        if slot.get("kind") != "slot":
            raise PlaceError(f"{slot['id']} is not a slot")
        sx, sy, sw, sh = _box(slot)
        width, height = sw, sw * h / w
        if height > sh:
            width, height = sh * w / h, sh
        return Placed((round(sx + (sw - width) / 2), round(sy + (sh - height) / 2), round(width), round(height)),
                      taken=str(slot["id"]))  # fmt: skip
    if at and "in" in at:
        frame = named("in")
        if frame.get("kind") != "frame":
            raise PlaceError(f"{frame['id']} is not a frame")
        return _in_frame(frame, solid, w, h, grid)
    for side in ("right_of", "left_of", "below", "above"):
        if at and side in at:
            return _beside(items, named(side), side, solid, w, h, grid)
    if at and "x" in at and "y" in at:
        return Placed((snap(float(at["x"]), grid), snap(float(at["y"]), grid), round(w), round(h)))
    boxes = [_box(each) for each in items if each.get("kind") in SOLID | {"frame"}]
    if not boxes:
        return Placed((START, START, round(w), round(h)))
    left = min(box[0] for box in boxes)
    bottom = max(box[1] + box[3] for box in boxes)
    return Placed((snap(left, grid), snap(bottom + GAP, grid), round(w), round(h)))


Box = tuple[float, float, float, float]


def _beside(items: Sequence[Mapping[str, Any]], ref: Mapping[str, Any], side: str, solid: list[Box], w: float, h: float,
            grid: int) -> Placed:  # fmt: skip
    rx, ry, rw, rh = _box(ref)
    x = {"right_of": rx + rw + GAP, "left_of": rx - GAP - w}.get(side, rx)
    y = {"below": ry + rh + GAP, "above": ry - GAP - h}.get(side, ry)
    x, y = snap(x, grid), snap(y, grid)
    for _ in range(TRIES):
        hit = next((box for box in solid if _overlaps((x, y, w, h), box, GAP)), None)
        if hit is None:
            break
        if side in ("right_of", "left_of"):
            y = snap(hit[1] + hit[3] + GAP, grid)
        else:
            x = snap(hit[0] + hit[2] + GAP, grid)
    frame = frame_of(items, ref)
    grown = None
    if frame is not None:
        fx, fy, fw, fh = _box(frame)
        right, bottom = max(fx + fw, x + w + INSET), max(fy + fh, y + h + INSET)
        if (right, bottom) != (fx + fw, fy + fh):
            grown = (str(frame["id"]), round(right - fx), round(bottom - fy))
    return Placed((x, y, round(w), round(h)), grown=grown)


def _in_frame(frame: Mapping[str, Any], solid: list[tuple[float, float, float, float]], w: float, h: float,
              grid: int) -> Placed:  # fmt: skip
    fx, fy, fw, fh = _box(frame)
    left, top, right = fx + INSET, fy + TITLE, fx + fw - INSET
    y = top
    for _ in range(TRIES):
        x = left
        while True:
            if not any(_overlaps((x, y, w, h), box, GAP) for box in solid):
                bottom = max(fy + fh, y + h + INSET)
                widest = max(fx + fw, x + w + INSET)
                grown = None if (bottom, widest) == (fy + fh, fx + fw) else (str(frame["id"]), round(widest - fx),
                                                                             round(bottom - fy))  # fmt: skip
                return Placed((round(x), round(y), round(w), round(h)), grown=grown)
            x += grid
            if x + w > right:
                break
        y += grid
    raise PlaceError(f"no free place was found in {frame['id']}")
