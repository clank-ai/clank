"""A mark on a figure, in words (design 0008 §4): what an agent is told about each mark the owner drew.

A mark is what the annotator sends: its number, kind (`pen`, `box`, `circle`, `arrow`, `text`), color and points in
the image's pixels (two corners for a box or a circle, tail then tip for an arrow, the stroke for the pen, one point and
words for a text). With the figure's geometry (`.clank/figures/`, written when Matplotlib saved it, design 0008 §3)
it is said in the figure's own terms: the plot it is on, its range on each axis in data coordinates (in the axis's
scale), the lines and points inside it with their labels; for an arrow, the line or element its tip points at (a tip
that stops just short of a legend points at it, unless a line is nearer). Outside any plot, the element under it (a
legend, a title, an axis label); without geometry, its place in the image.
"""

import math
import struct
from typing import Any

COLORS = {"#e5484d": "red", "#3e63dd": "blue", "#30a46c": "green", "#f5a524": "amber"}  # the annotator's colors
KINDS = {"pen": "drawing", "box": "box", "circle": "circle", "arrow": "arrow", "text": "note"}
NEAR = 30.0  # pixels: how far from an arrow's tip a line or a legend still counts as pointed at


def describe(marks: list[dict[str, Any]], geometry: dict[str, Any] | None, size: tuple[int, int]) -> list[str]:
    """A sentence for each mark."""
    return [_sentence(mark, geometry, size) for mark in marks]


def _sentence(mark: dict[str, Any], geometry: dict[str, Any] | None, size: tuple[int, int]) -> str:
    points = [(float(x), float(y)) for x, y in mark.get("points") or []]
    kind = str(mark.get("kind") or "pen")
    color = COLORS.get(str(mark.get("color") or "").lower(), str(mark.get("color") or ""))
    head = f"Mark {mark.get('n')} ({color} {KINDS.get(kind, kind)})".replace("( ", "(")
    if kind == "text" and mark.get("text"):
        head += f' "{mark["text"]}"'
    if not points:
        return head + "."
    left, top = min(x for x, _ in points), min(y for _, y in points)
    right, bottom = max(x for x, _ in points), max(y for _, y in points)
    spot = points[-1] if kind in ("arrow", "text") else ((left + right) / 2, (top + bottom) / 2)
    plots = (geometry or {}).get("axes") or []
    legend = next((each for each in plots if each.get("legend") and _inside(spot, each["legend"]["box"])), None)
    if legend is not None:  # a legend lies over its plot: what is marked is the legend
        return f"{head} on {_legend(legend, plots)}."
    plot = next((each for each in plots if _inside(spot, each["box"]) and not each.get("colorbar")), None)
    near = next((each for each in plots if each.get("legend") and _distance(spot, each["legend"]["box"]) <= NEAR), None)
    if plot is None:
        if kind == "arrow" and near is not None:
            return f"{head} pointing at {_legend(near, plots)}."
        return head + " " + _outside(spot, plots, size) + "."
    where = f"on {_name(plot, plots)}"
    if kind == "arrow":
        pointed = _pointed(plot, spot)
        if not pointed and near is not None:
            pointed = f", pointing at {_legend(near, plots, own=near is plot)}"
        return f"{head} {where}: its tip at {_point(plot, spot)}{pointed}."
    if kind == "text":
        return f"{head} {where}, at {_point(plot, spot)}."
    box = _clip((left, top, right, bottom), plot["box"])
    return f"{head} {where}: {_range(plot, box)}{_within(plot, box, kind)}."


def _inside(point: tuple[float, float], box: list[float]) -> bool:
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def _distance(point: tuple[float, float], box: list[float]) -> float:
    """How far a point is from a box (0 inside it)."""
    across = max(box[0] - point[0], 0.0, point[0] - box[2])
    down = max(box[1] - point[1], 0.0, point[1] - box[3])
    return math.hypot(across, down)


def _clip(region: tuple[float, float, float, float], box: list[float]) -> tuple[float, float, float, float]:
    return max(region[0], box[0]), max(region[1], box[1]), min(region[2], box[2]), min(region[3], box[3])


def _name(plot: dict[str, Any], plots: list[dict[str, Any]]) -> str:
    """A plot as the owner would name it: its title, and where it is when there are several."""
    title = f'"{plot["title"]}"' if plot.get("title") else f"plot {plot['index'] + 1}"
    shown = [each for each in plots if not each.get("colorbar")]
    if len(shown) < 2:
        return title
    centers = {each["index"]: ((each["box"][0] + each["box"][2]) / 2, (each["box"][1] + each["box"][3]) / 2)
               for each in shown}  # fmt: skip
    xs, ys = sorted({round(x) for x, _ in centers.values()}), sorted({round(y) for _, y in centers.values()})
    x, y = centers[plot["index"]]
    across = "" if len(xs) < 2 else ("left" if round(x) == xs[0] else "right" if round(x) == xs[-1] else "middle")
    down = "" if len(ys) < 2 else ("top" if round(y) == ys[0] else "bottom" if round(y) == ys[-1] else "middle")
    place = " ".join(part for part in (down, across) if part)
    return f"{title} ({place} plot)" if place else title


def _value(plot: dict[str, Any], axis: str, pixel: float) -> float:
    """The data value at a pixel along an axis, in the axis's scale."""
    left, top, right, bottom = plot["box"]
    low, high = plot[f"{axis}lim"]
    fraction = (pixel - left) / (right - left) if axis == "x" else (bottom - pixel) / (bottom - top)
    if plot[f"{axis}scale"] == "log" and low > 0 and high > 0:
        return float(10 ** (math.log10(low) + fraction * (math.log10(high) - math.log10(low))))
    return float(low + fraction * (high - low))


def _pixel(plot: dict[str, Any], axis: str, value: float) -> float | None:
    """Where a data value falls along an axis, in the image's pixels; None for one the scale cannot show."""
    left, top, right, bottom = plot["box"]
    low, high = plot[f"{axis}lim"]
    if plot[f"{axis}scale"] == "log":
        if value <= 0 or low <= 0 or high <= 0:
            return None
        fraction = (math.log10(value) - math.log10(low)) / (math.log10(high) - math.log10(low))
    else:
        fraction = (value - low) / (high - low)
    return float(left + fraction * (right - left) if axis == "x" else bottom - fraction * (bottom - top))


def _number(value: float) -> str:
    if value == 0:
        return "0"
    if abs(value) >= 1e5 or abs(value) < 1e-3:
        return f"{value:.3g}"
    return f"{value:.4g}"


def _axis(plot: dict[str, Any], axis: str) -> str:
    return str(plot.get(f"{axis}label") or axis)


def _range(plot: dict[str, Any], box: tuple[float, float, float, float]) -> str:
    x0, x1 = sorted((_value(plot, "x", box[0]), _value(plot, "x", box[2])))
    y0, y1 = sorted((_value(plot, "y", box[3]), _value(plot, "y", box[1])))
    return (f"{_axis(plot, 'x')} {_number(x0)} to {_number(x1)}, "
            f"{_axis(plot, 'y')} {_number(y0)} to {_number(y1)}")  # fmt: skip


def _point(plot: dict[str, Any], spot: tuple[float, float]) -> str:
    return (f"{_axis(plot, 'x')} {_number(_value(plot, 'x', spot[0]))}, "
            f"{_axis(plot, 'y')} {_number(_value(plot, 'y', spot[1]))}")  # fmt: skip


def _series(plot: dict[str, Any]) -> list[dict[str, Any]]:
    return [*plot.get("lines", []), *plot.get("scatters", [])]


def _placed(plot: dict[str, Any], series: dict[str, Any]) -> list[tuple[float, float, float, float]]:
    """A line's points with their pixels: (x, y, pixel x, pixel y)."""
    found = []
    for x, y in zip(series.get("x") or [], series.get("y") or [], strict=False):
        if x is None or y is None or x != x or y != y:
            continue
        px, py = _pixel(plot, "x", x), _pixel(plot, "y", y)
        if px is not None and py is not None:
            found.append((x, y, px, py))
    return found


def _within(plot: dict[str, Any], box: tuple[float, float, float, float], kind: str) -> str:
    """The lines with points inside the mark (an ellipse for a circle), each with how many and their values there."""
    said = []
    for index, series in enumerate(_series(plot)):
        inside = [(x, y) for x, y, px, py in _placed(plot, series) if _covered(box, px, py, kind)]
        if not inside:
            continue
        name = f'"{series["label"]}"' if series.get("label") else f"an unlabeled line ({index + 1})"
        ys = [y for _, y in inside]
        count = "1 point" if len(inside) == 1 else f"{len(inside)} points"
        said.append(f"{name} ({count}, {_axis(plot, 'y')} {_number(min(ys))} to {_number(max(ys))})")
    return "; inside it: " + ", ".join(said) if said else ""


def _covered(box: tuple[float, float, float, float], px: float, py: float, kind: str) -> bool:
    left, top, right, bottom = box
    if not (left <= px <= right and top <= py <= bottom):
        return False
    if kind != "circle" or right == left or bottom == top:
        return True
    cx, cy, rx, ry = (left + right) / 2, (top + bottom) / 2, (right - left) / 2, (bottom - top) / 2
    return ((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2 <= 1.0


def _pointed(plot: dict[str, Any], spot: tuple[float, float]) -> str:
    """What an arrow's tip points at: the nearest line within `NEAR` pixels, with its value there."""
    best: tuple[float, str, float, float] | None = None
    for index, series in enumerate(_series(plot)):
        for x, y, px, py in _placed(plot, series):
            distance = math.hypot(px - spot[0], py - spot[1])
            if distance <= NEAR and (best is None or distance < best[0]):
                name = f'"{series["label"]}"' if series.get("label") else f"an unlabeled line ({index + 1})"
                best = (distance, name, x, y)
    if best is None:
        return ""
    return f", pointing at {best[1]} near {_axis(plot, 'x')} {_number(best[2])}, {_axis(plot, 'y')} {_number(best[3])}"


def _outside(spot: tuple[float, float], plots: list[dict[str, Any]], size: tuple[int, int]) -> str:
    """Where a mark outside every plot is: on a title or an axis label, else its place in the image."""
    for plot in plots:
        for name, box in (plot.get("labels") or {}).items():
            if _inside(spot, box):
                label = {"title": "the title", "xlabel": "the x-axis label", "ylabel": "the y-axis label"}[name]
                text = plot.get(name) or ""
                return f'on {label} "{text}" of {_name(plot, plots)}'
    across, down = spot[0] / max(size[0], 1), spot[1] / max(size[1], 1)
    vertical = "top" if down < 1 / 3 else "bottom" if down > 2 / 3 else "middle"
    horizontal = "left" if across < 1 / 3 else "right" if across > 2 / 3 else "center"
    place = "center" if (vertical, horizontal) == ("middle", "center") else f"{vertical} {horizontal}"
    where = "outside the plots, " if plots else ""
    return f"{where}in the {place} of the image ({round(100 * across)}% across, {round(100 * down)}% down)"


def _legend(plot: dict[str, Any], plots: list[dict[str, Any]], *, own: bool = False) -> str:
    """A plot's legend with its entries ("its legend" for the plot a mark is on)."""
    entries = ", ".join(f'"{entry}"' for entry in plot["legend"]["entries"])
    return f"{'its legend' if own else f'the legend of {_name(plot, plots)}'} ({entries})"


def image_size(data: bytes) -> tuple[int, int] | None:
    """A PNG's or a JPEG's width and height, from its header; None for anything else."""
    if data[:8] == bytes([137, 80, 78, 71, 13, 10, 26, 10]):
        width, height = struct.unpack(">II", data[16:24])
        return width, height
    if data[:2] == bytes([255, 216]):
        at = 2
        while at + 9 < len(data):
            if data[at] != 255:
                return None
            marker = data[at + 1]
            length = struct.unpack(">H", data[at + 2 : at + 4])[0]
            if marker in (192, 193, 194):
                height, width = struct.unpack(">HH", data[at + 5 : at + 9])
                return width, height
            at += 2 + length
    return None
