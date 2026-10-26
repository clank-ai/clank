"""Compiled LaTeX on a board (design 0022 §6): what KaTeX cannot draw (TikZ, pgfplots, a `tabular`, a package of the
owner's) is built in the folder's container with the TeX layer (design 0020): `snippet` makes the item a `standalone`
document with the board's preamble, `build` runs pdfLaTeX and `pdftocairo -svg` on it in a scratch folder of the
container (never in the folder), and `flatten` makes cairo's SVG markup a board can put in its page: each glyph's
`<use>` becomes the glyph's own paths moved into place, every id is made the item's own (two drawings on a board
never share a clip path), black becomes the text's color (`currentColor`, so the drawing takes the board's theme), and
only drawing elements are kept. A build that fails says LaTeX's error line; a container without TeX says how to add
it. `Boards.compile_latex` keeps what is built by its source's and preamble's hash, so each is built once.
"""

import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from typing import Any

SECONDS = 60.0  # a drawing's build limit
POINT = 4 / 3  # CSS pixels in a TeX point (96 and 72 to the inch)
PACKAGES = ("amsmath", "amssymb", "tikz")
NO_TEX = "TeX is not in {workspace}'s container, so this LaTeX could not be compiled: `clank latex setup` adds it"
SVG = "{http://www.w3.org/2000/svg}"
XLINK = "{http://www.w3.org/1999/xlink}href"
BLACK = re.compile(r"rgb\(0%,\s*0%,\s*0%\)")
REFERENCE = re.compile(r"url\(#([^)]+)\)")
DRAWING = {"svg", "g", "path", "defs", "clipPath", "mask", "use", "rect", "image", "pattern", "symbol",
           "linearGradient", "radialGradient", "stop"}  # fmt: skip
# Built in a scratch folder of the container, the document on standard input: the SVG on standard output, or LaTeX's
# log on standard error. 127 when there is no TeX.
BUILD = """command -v pdflatex >/dev/null 2>&1 && command -v pdftocairo >/dev/null 2>&1 || exit 127
d=$(mktemp -d) && cd "$d" && cat > item.tex || exit 2
if pdflatex -interaction=nonstopmode -halt-on-error item.tex >/dev/null 2>&1 && pdftocairo -svg item.pdf item.svg
then cat item.svg; s=0; else cat item.log >&2; s=3; fi
cd / && rm -rf "$d"; exit $s"""


def snippet(source: str, preamble: str) -> str:
    """An item's LaTeX as a document of its own, cropped to what it draws."""
    packages = "".join(f"\\usepackage{{{name}}}\n" for name in PACKAGES)
    return (
        f"\\documentclass[border=2pt]{{standalone}}\n{packages}{preamble.strip()}\n"
        f"\\begin{{document}}\n{source.strip()}\n\\end{{document}}\n"
    )


def error_of(log: str) -> str:
    """LaTeX's first error in a log, with the line it names; the log's end when there is none."""
    lines = log.splitlines()
    for at, line in enumerate(lines):
        if line.startswith("! "):
            where = next((each.strip() for each in lines[at + 1 : at + 8] if re.match(r"l\.\d+", each)), "")
            return f"{line[2:].strip()} ({where})" if where else line[2:].strip()
    return log.strip()[-300:] or "it did not build, and LaTeX said nothing"


def build(run: Callable[..., Any], workspace: str, source: str, preamble: str) -> tuple[str, str]:
    """The item built in `workspace`'s container (`run` is the workspaces' `run_in`): cairo's SVG, or why not."""
    try:
        answer = run(workspace, ["sh", "-c", BUILD], input=snippet(source, preamble).encode(), timeout=SECONDS)
    except Exception as error:  # the workspace's own words: its container does not run
        return "", str(error)
    if answer.status == 127:
        return "", NO_TEX.format(workspace=workspace)
    if answer.status is None:
        return "", f"it took longer than {SECONDS:g} seconds to build"
    if answer.status != 0 or "<svg" not in answer.output:
        return "", error_of(answer.errors or answer.output)
    return answer.output, ""


def _name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _attributes(element: ET.Element, prefix: str) -> str:
    said = []
    for key, value in element.attrib.items():
        key = "href" if key == XLINK else _name(key)
        if key.lower().startswith("on") or key in ("width", "height", "viewBox", "version"):
            continue
        if key == "id":
            value = f"{prefix}-{value}"
        elif key == "href" and value.startswith("#"):
            value = f"#{prefix}-{value[1:]}"
        value = REFERENCE.sub(lambda found: f"url(#{prefix}-{found[1]})", value)
        if key in ("fill", "stroke"):
            value = BLACK.sub("currentColor", value)
        said.append(f' {key}="{html.escape(value, quote=True)}"')
    return "".join(said)


def _markup(element: ET.Element, glyphs: dict[str, ET.Element], prefix: str) -> str:
    tag = _name(element.tag)
    if tag not in DRAWING or element.get("id") in glyphs:
        return ""  # not drawing, or a glyph (drawn where it is used)
    if tag == "use":
        glyph = glyphs.get((element.get(XLINK) or element.get("href") or "").lstrip("#"))
        if glyph is not None:
            paths = "".join(
                f'<path d="{html.escape(each.get("d", ""), quote=True)}"></path>' for each in glyph.iter(f"{SVG}path")
            )
            return f'<g transform="translate({element.get("x", "0")} {element.get("y", "0")})">{paths}</g>'
    inner = "".join(_markup(child, glyphs, prefix) for child in element)
    return f"<{tag}{_attributes(element, prefix)}>{inner}</{tag}>"


def _pixels(length: str | None) -> str:
    """Cairo's length (in points, whether it says `pt` or nothing) in CSS pixels."""
    number = float(re.sub(r"[a-z]+$", "", length or "0") or 0)
    return f"{round(number if (length or '').endswith('px') else number * POINT, 2):g}"


def flatten(svg: str, prefix: str) -> str:
    """Cairo's SVG as markup of the item's own (`prefix` makes its ids), sized in CSS pixels."""
    root = ET.fromstring(svg.encode())
    glyphs = {
        str(each.get("id")): each
        for each in root.iter()
        if _name(each.tag) in ("g", "symbol") and str(each.get("id") or "").startswith("glyph")
    }
    inner = "".join(_markup(child, glyphs, prefix) for child in root)
    view = html.escape(root.get("viewBox") or "", quote=True)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_pixels(root.get("width"))}" '
        f'height="{_pixels(root.get("height"))}" viewBox="{view}">{inner}</svg>'
    )
