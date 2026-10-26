"""A board's figure out (design 0022 §7): a frame, or a selection, made one SVG that a paper or slides can use.

`chosen` is what is exported: the figures and the LaTeX in the frame (or chosen; a chosen frame brings what it holds),
and the arrows between them; the working layer (notes, slots, pins, pen strokes, highlights, the frame itself) is left
out, so a frame exports as the figure it frames. `art_of_svg` makes a figure's SVG something to nest in the export:
its ids (and what names them: `url(#…)`, `href`, its style's selectors) made its own, so two figures never share a clip
path, and nothing that runs or is not drawing kept; nested `<svg>` stays vector in the PDF librsvg makes, where an SVG
given as an `<image>` would be made pixels (found 2026-10-26). `art_of_picture` embeds a PNG, JPEG, GIF or WebP as it
is. `compose` places each part in its box as the board shows it: a figure in its box above its caption, math centered
and at most twice its size, compiled LaTeX fitted to its box, an arrow from edge to edge; cropped to what it shows,
with `MARGIN` around. `tex_text` writes a caption's words for TeX, its `$…$` math kept. `Boards.export` builds the
LaTeX and the captions with TeX and makes the PDF or PNG with librsvg, both in the folder's container.
"""

import base64
import html
import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

MARGIN = 8  # around what is exported
CAPTION = 28  # a figure's caption line, under it (as the board draws it)
EXPORTED = {"figure", "latex"}
DROPPED = {"script", "foreignObject", "metadata", "title", "desc"}
SVG_NS = "http://www.w3.org/2000/svg"
XLINK = "{http://www.w3.org/1999/xlink}href"
XML_NS = "{http://www.w3.org/XML/1998/namespace}"
UNITS = {"px": 1.0, "": 1.0, "pt": 4 / 3, "pc": 16.0, "in": 96.0, "cm": 96 / 2.54, "mm": 96 / 25.4}
REFERENCE = re.compile(r"url\(#([^)]+)\)")
SPECIAL = {"\\": "\\textbackslash{}", "{": "\\{", "}": "\\}", "%": "\\%", "&": "\\&", "#": "\\#", "_": "\\_",
           "^": "\\^{}", "~": "\\~{}"}  # fmt: skip
ARROW = (
    '<marker id="board-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">'
    '<path d="M 0 0 L 10 5 L 0 10 Z" fill="#000"></path></marker>'
)


class ExportError(Exception):
    """Nothing to export, or a frame that is not there."""


@dataclass(frozen=True)
class Art:
    """A part of an export: its viewBox, its markup inside, and its own size in pixels."""

    view: str
    inner: str
    w: float
    h: float


def _box(item: Mapping[str, Any]) -> tuple[float, float, float, float]:
    return float(item.get("x", 0)), float(item.get("y", 0)), float(item.get("w", 0)), float(item.get("h", 0))


def _inside(item: Mapping[str, Any], frame: Mapping[str, Any]) -> bool:
    x, y, w, h = _box(item)
    fx, fy, fw, fh = _box(frame)
    return x >= fx and y >= fy and x + w <= fx + fw and y + h <= fy + fh


def chosen(board: Mapping[str, Any], frame: str | None = None, ids: Sequence[str] = ()) -> list[dict[str, Any]]:
    """What a frame (or the items `ids`) exports, in the board's order."""
    items: list[dict[str, Any]] = list(board.get("items") or [])
    by_id = {str(each.get("id")): each for each in items}
    named = set() if frame else {str(each) for each in ids}
    if frame and by_id.get(frame, {}).get("kind") != "frame":
        raise ExportError(f"there is no frame {frame} on the board")
    frames = [by_id[frame]] if frame else [by_id[each] for each in named if by_id.get(each, {}).get("kind") == "frame"]
    picked = {
        str(each["id"])
        for each in items
        if each.get("kind") in EXPORTED and (str(each.get("id")) in named or any(_inside(each, f) for f in frames))
    }
    if not picked:
        raise ExportError("nothing to export: a figure shows the figures and the LaTeX in a frame, or chosen")

    def kept_end(end: Any) -> bool:
        if isinstance(end, Mapping) and "item" in end:
            return str(end["item"]) in picked
        point = (
            {"x": float(end.get("x", 0)), "y": float(end.get("y", 0)), "w": 0, "h": 0}
            if isinstance(end, Mapping)
            else {}
        )
        return bool(point) and any(_inside(point, f) for f in frames)

    return [
        each
        for each in items
        if str(each.get("id")) in picked
        or (each.get("kind") == "arrow" and kept_end(each.get("from")) and kept_end(each.get("to")))
    ]


def _number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


def _pixels(length: str | None, unitless: float = 1.0) -> float | None:
    found = re.fullmatch(r"\s*([\d.]+)\s*([a-z]*)\s*", length or "")
    if not found or found[2] not in UNITS:
        return None
    return float(found[1]) * (unitless if found[2] == "" else UNITS[found[2]])


def _name(tag: str) -> tuple[str, str]:
    """An element's namespace and name."""
    return (tag[1:].split("}", 1)[0], tag.rsplit("}", 1)[-1]) if tag.startswith("{") else (SVG_NS, tag)


def _scoped(css: str, prefix: str) -> str:
    """A style sheet whose id selectors name the figure's own ids (its declarations, colors among them, as they are)."""
    parts = []
    for block in css.split("}"):
        selectors, brace, declarations = block.partition("{")
        selectors = re.sub(r"#([A-Za-z_][\w-]*)", lambda found: f"#{prefix}-{found[1]}", selectors)
        parts.append(f"{selectors}{brace}{declarations}")
    return "}".join(parts)


def _attributes(element: ET.Element, prefix: str) -> str:
    said = []
    for key, value in element.attrib.items():
        if key == XLINK:
            key = "href"
        elif key.startswith(XML_NS):
            key = f"xml:{key[len(XML_NS) :]}"
        elif key.startswith("{") or key.lower().startswith("on"):
            continue  # another program's attribute, or something that runs
        if key == "id":
            value = f"{prefix}-{value}"
        elif key == "href" and value.startswith("#"):
            value = f"#{prefix}-{value[1:]}"
        elif key == "href" and not value.startswith("data:image/"):
            continue  # nothing from outside the export
        value = REFERENCE.sub(lambda found: f"url(#{prefix}-{found[1]})", value)
        said.append(f' {key}="{html.escape(value, quote=True)}"')
    return "".join(said)


def _write(element: ET.Element, prefix: str) -> str:
    space, tag = _name(element.tag)
    if space != SVG_NS or tag in DROPPED:
        return ""
    text = element.text or ""
    inner = html.escape(_scoped(text, prefix) if tag == "style" else text, quote=False)
    for child in element:
        inner += _write(child, prefix) + html.escape(child.tail or "", quote=False)
    return f"<{tag}{_attributes(element, prefix)}>{inner}</{tag}>"


def art_of_svg(text: str, prefix: str) -> Art:
    """An SVG file's drawing, to nest in an export."""
    root = ET.fromstring(text.encode())
    numbers = [float(each) for each in re.split(r"[\s,]+", (root.get("viewBox") or "").strip()) if each]
    w = _pixels(root.get("width")) or (numbers[2] if len(numbers) == 4 else 300.0)
    h = _pixels(root.get("height")) or (numbers[3] if len(numbers) == 4 else 150.0)
    view = " ".join(_number(each) for each in numbers) if len(numbers) == 4 else f"0 0 {_number(w)} {_number(h)}"
    inner = "".join(_write(child, prefix) for child in root)
    return Art(view, inner, w, h)


def art_of_picture(data: bytes, mime: str, w: float, h: float) -> Art:
    """A picture (PNG, JPEG, GIF, WebP), embedded as it is."""
    encoded = base64.b64encode(data).decode("ascii")
    return Art(
        f"0 0 {_number(w)} {_number(h)}",
        f'<image width="{_number(w)}" height="{_number(h)}" href="data:{mime};base64,{encoded}"></image>',
        w,
        h,
    )


def tex_text(text: str) -> str:
    """Words for TeX: its special characters written as text, `$…$` left as math."""
    parts = re.split(r"(\$[^$]+\$)", text)
    return "".join(
        part if part.startswith("$") else "".join(SPECIAL.get(char, char) for char in part) for part in parts
    )


def _placed(art: Art, x: float, y: float, w: float, h: float) -> str:
    return (
        f'<svg x="{_number(x)}" y="{_number(y)}" width="{_number(w)}" height="{_number(h)}" viewBox="{art.view}" '
        f'preserveAspectRatio="xMidYMid meet">{art.inner}</svg>'
    )


def _centered(art: Art, box: tuple[float, float, float, float], most: float) -> str:
    """`art` at its size (at most `most` times it), made smaller to fit `box`, centered in it."""
    x, y, w, h = box
    scale = min(most, w / max(art.w, 1e-9), h / max(art.h, 1e-9))
    width, height = art.w * scale, art.h * scale
    return _placed(art, x + (w - width) / 2, y + (h - height) / 2, width, height)


def _edge(box: tuple[float, float, float, float], toward: tuple[float, float]) -> tuple[float, float]:
    """Where a line from the box's center toward a point leaves the box."""
    x, y, w, h = box
    cx, cy = x + w / 2, y + h / 2
    dx, dy = toward[0] - cx, toward[1] - cy
    t = min(w / 2 / abs(dx) if dx else math.inf, h / 2 / abs(dy) if dy else math.inf, 1.0)
    return cx + dx * t, cy + dy * t


def _end(end: Any, by_id: Mapping[str, Mapping[str, Any]]) -> tuple[float, float, float, float]:
    if isinstance(end, Mapping) and str(end.get("item")) in by_id:
        return _box(by_id[str(end["item"])])
    return float(end.get("x", 0)), float(end.get("y", 0)), 0.0, 0.0


def compose(items: Sequence[Mapping[str, Any]], arts: Mapping[str, Art], background: str = "") -> str:
    """The export as one SVG (board pixels), each part in its box; `arts` by id (a caption's as `<id>:caption`)."""
    boxes = [_box(each) for each in items if each.get("kind") != "arrow"]
    left, top = min(b[0] for b in boxes) - MARGIN, min(b[1] for b in boxes) - MARGIN
    width = max(b[0] + b[2] for b in boxes) + MARGIN - left
    height = max(b[1] + b[3] for b in boxes) + MARGIN - top
    by_id = {str(each.get("id")): each for each in items}
    parts = [f'<rect x="{_number(left)}" y="{_number(top)}" width="{_number(width)}" height="{_number(height)}" '
             f'fill="{html.escape(background, quote=True)}"></rect>'] if background else []  # fmt: skip
    arrows = False
    for item in items:
        id, kind = str(item.get("id")), item.get("kind")
        x, y, w, h = _box(item)
        if kind == "figure":
            caption = arts.get(f"{id}:caption")
            picture_h = h - CAPTION if item.get("caption") else h
            if id in arts:
                parts.append(_placed(arts[id], x, y, w, picture_h))
            if caption:
                parts.append(_centered(caption, (x, y + picture_h, w, CAPTION), 1.0))
        elif kind == "latex" and id in arts:
            inset = (x + 8, y + 6, w - 16, h - 12) if item.get("mode") != "compiled" else (x + 8, y + 8, w - 16, h - 16)
            parts.append(_centered(arts[id], inset, 2.0 if item.get("mode") != "compiled" else math.inf))
        elif kind == "arrow":
            start, end = _end(item.get("from"), by_id), _end(item.get("to"), by_id)
            x1, y1 = _edge(start, (end[0] + end[2] / 2, end[1] + end[3] / 2))
            x2, y2 = _edge(end, (start[0] + start[2] / 2, start[1] + start[3] / 2))
            parts.append(f'<line x1="{_number(x1)}" y1="{_number(y1)}" x2="{_number(x2)}" y2="{_number(y2)}" '
                         'stroke="#000" stroke-width="1.5" marker-end="url(#board-arrow)"></line>')  # fmt: skip
            arrows = True
    defs = f"<defs>{ARROW}</defs>" if arrows else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_number(width)}" height="{_number(height)}" '
        f'viewBox="{_number(left)} {_number(top)} {_number(width)} {_number(height)}" color="#000">'
        f"{defs}{''.join(parts)}</svg>\n"
    )
