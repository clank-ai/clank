"""A PDF's pages, marked up and said in words (design 0020 §10).

`PageMarks.render` turns a PDF of the folder into page images for the figure annotator: a PDF beside the `.tex` file of
its name is built by Clank first (kept under `.clank/latex/build/<key>/`, with its SyncTeX file, its paths made the
folder's), so each mark can be traced to its source; another PDF is rendered as it is, its own SyncTeX file used when it
has one. The pages are rendered in the container by the TeX layer's helper (`pdftoppm`) with each page's words in boxes
(`pdftotext -bbox-layout`), kept under `.clank/latex/pages/<key>/` with `pages.json`, which says what they are of.

`PageMarks.describe` says each mark the owner drew on a page: its kind and color, the page, the source file and line
SyncTeX gives for the mark's spot (its middle; a note's or an insertion's pin; an arrow's tip), and the words under it:
over them (a highlight, a drawing), through them (a strike, the words its line crosses), around them (a box, a circle;
none: a figure, or an equation's image), after the word to the left of an insertion's caret, at the word under a note's
pin, or pointed at by an arrow's tip.
"""

import json
import re
from collections.abc import Callable
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from clank.components.agents.figures import COLORS
from clank.components.agents.latex.building import HELPER, engine_of

PAGES = ".clank/latex/pages"
BUILDS = ".clank/latex/build"
DPI = 110
KINDS = {"pen": "drawing", "box": "box", "circle": "circle", "arrow": "arrow", "text": "note", "highlight": "highlight",
         "strike": "strike", "insert": "insertion"}  # fmt: skip
QUOTED = 200  # characters of the words under a mark said
Run = Callable[[str, list[str], bytes, float], Any]  # (workspace, argv, input, timeout) -> an Answer


class PageError(Exception):
    """A PDF whose pages cannot be shown, and why."""


def key_of(pdf: str) -> str:
    """The folder name a PDF's pages and build are kept under: its path, without `.pdf`, `/` as `-`."""
    stem = pdf[: -len(".pdf")] if pdf.lower().endswith(".pdf") else pdf
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip("-") or "pdf"


def page_image(folder: Path, image: str) -> tuple[dict[str, Any], int] | None:
    """What a page image Clank rendered is of (its `pages.json`) and its page number; None for any other image."""
    pure = PurePosixPath(image.replace("\\", "/"))
    if not pure.as_posix().startswith(PAGES + "/") or not re.fullmatch(r"page-\d+\.png", pure.name):
        return None
    try:
        meta: dict[str, Any] = json.loads(folder.joinpath(*pure.parent.parts, "pages.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return meta, int(re.sub(r"\D", "", pure.name))


class PageMarks:
    """Pages to mark up, and the marks on them in words, through the TeX layer's helper (`run`)."""

    def __init__(self, run: Run, dpi: int = DPI) -> None:
        self.run = run
        self.dpi = dpi

    def render(self, workspace: str, folder: Path, pdf: str) -> dict[str, Any]:
        """The PDF's pages as images (built first when its `.tex` is beside it); what they are."""
        pure = PurePosixPath(pdf.replace("\\", "/"))
        if pure.suffix.lower() != ".pdf" or pure.is_absolute() or ".." in pure.parts:
            raise PageError(f"{pdf} is not a PDF of the folder")
        if not folder.joinpath(*pure.parts).is_file():
            raise PageError(f"{pdf} is not a file of the folder")
        key = key_of(pure.as_posix())
        source = pure.with_suffix(".tex")
        shown, built = pure.as_posix(), False
        tex = folder.joinpath(*source.parts)
        if tex.is_file():
            keep = f"{BUILDS}/{key}"
            engine = engine_of(tex.read_text(encoding="utf-8", errors="replace"))
            said = self._ask(workspace, {"mode": "build", "root": source.as_posix(), "file": source.as_posix(),
                                         "text": None, "engine": engine, "seconds": 120, "keep": keep})  # fmt: skip
            if said.get("built") and (said.get("kept") or {}).get("pdf"):
                shown, built = str(said["kept"]["pdf"]), True
        keep = f"{PAGES}/{key}"
        said = self._ask(workspace, {"mode": "pages", "pdf": shown, "keep": keep, "dpi": self.dpi})
        if said.get("error") or "pages" not in said:
            raise PageError(f"the pages of {pdf} could not be rendered: {said.get('error') or said}")
        meta = {"pdf": pure.as_posix(), "built": shown, "dpi": int(said.get("dpi") or self.dpi),
                "words": str(said.get("words") or f"{keep}/words.json"), "pages": said["pages"]}  # fmt: skip
        out = folder.joinpath(*keep.split("/"))
        out.mkdir(parents=True, exist_ok=True)
        (out / "pages.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
        pages = [{"number": number, "image": str(page["image"])} for number, page in enumerate(said["pages"], start=1)]
        return {"pdf": pure.as_posix(), "built": built, "pages": pages}

    def describe(self, workspace: str, folder: Path, image: str, marks: list[dict[str, Any]]) -> list[str]:
        """A sentence for each mark on a page image Clank rendered."""
        found = page_image(folder, image)
        if found is None:
            raise PageError(f"{image} is not a page Clank rendered")
        meta, number = found
        scale = 72.0 / float(meta.get("dpi") or DPI)  # points a pixel
        try:
            pages = json.loads(folder.joinpath(*str(meta["words"]).split("/")).read_text(encoding="utf-8"))
        except (OSError, ValueError, KeyError):
            pages = []
        words = pages[number - 1]["words"] if number - 1 < len(pages) else []
        spots = [_spot(mark, scale) for mark in marks]
        points = [{"page": number, "x": round(x, 2), "y": round(y, 2)} for x, y in spots]
        said = self._ask(workspace, {"mode": "where", "pdf": meta.get("built") or meta["pdf"], "points": points})
        places = said.get("places") or [None] * len(marks)
        return [
            _sentence(mark, number, _place(place, folder), _under(mark, words, scale, spot))
            for mark, place, spot in zip(marks, places, spots, strict=False)
        ]

    def _ask(self, workspace: str, asked: dict[str, Any]) -> dict[str, Any]:
        answer = self.run(workspace, ["python3", HELPER], json.dumps(asked).encode(), 300.0)
        try:
            said: dict[str, Any] = json.loads(answer.output)
        except ValueError as error:
            why = (answer.errors or answer.output).strip()[-300:] or "it said nothing"
            raise PageError(f"the TeX layer's helper did not answer ({why}): `clank latex setup` adds it") from error
        if said.get("missing"):
            raise PageError("TeX is not in this workspace's container: `clank latex setup` adds it")
        return said


def _points(mark: dict[str, Any], scale: float) -> list[tuple[float, float]]:
    return [(float(x) * scale, float(y) * scale) for x, y in mark.get("points") or []]


def _spot(mark: dict[str, Any], scale: float) -> tuple[float, float]:
    """Where SyncTeX is asked about a mark: its middle, a pin, an arrow's tip; in points."""
    points = _points(mark, scale) or [(0.0, 0.0)]
    if mark.get("kind") in ("text", "insert"):
        return points[0]
    if mark.get("kind") == "arrow":
        return points[-1]
    xs, ys = [x for x, _ in points], [y for _, y in points]
    return (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2


def _under(mark: dict[str, Any], words: list[list[Any]], scale: float, spot: tuple[float, float]) -> str:
    """The words a mark is about, said as what it does to them."""
    kind = str(mark.get("kind") or "pen")
    points = _points(mark, scale)
    if kind in ("text", "arrow"):
        word = _at(words, spot)
        verb = "at" if kind == "text" else "pointing at"
        return f"{verb} {_quoted([word])}" if word else f"{verb} no word"
    if kind == "insert":
        word = _before(words, spot)
        return f"after {_quoted([word])}" if word else "at the start of a line"
    if not points:
        return "on the page"
    left, right = min(x for x, _ in points), max(x for x, _ in points)
    top, bottom = min(y for _, y in points), max(y for _, y in points)
    if kind == "strike":
        level = (top + bottom) / 2
        crossed = [word for word in words if word[1] <= level <= word[3] and left <= _middle(word)[0] <= right]
        return f"through {_quoted(crossed)}" if crossed else "through no word"
    inside = [word for word in words if left <= _middle(word)[0] <= right and top <= _middle(word)[1] <= bottom]
    verb = "over" if kind in ("highlight", "pen") else "around"
    return f"{verb} {_quoted(inside)}" if inside else f"{verb} no text (a figure, or an equation's image)"


def _sentence(mark: dict[str, Any], page: int, place: str, under: str) -> str:
    kind = str(mark.get("kind") or "pen")
    color = COLORS.get(str(mark.get("color") or "").lower(), str(mark.get("color") or ""))
    head = f"Mark {mark.get('n')} ({color} {KINDS.get(kind, kind)})".replace("( ", "(")
    if kind in ("text", "insert") and mark.get("text"):
        head += f' "{mark["text"]}"'
    where = f"on page {page}" + (f", from {place}" if place else "")
    return f"{head} {where}: {under}."


def _place(place: Any, folder: Path) -> str:
    """SyncTeX's file and line, from the folder: its path in the container (`/workspace/...`), or on this machine."""
    if not isinstance(place, dict) or not place.get("input"):
        return ""
    named = str(place["input"])
    if named.startswith("/workspace/"):
        relative = named[len("/workspace/") :]
    else:
        try:
            relative = PureWindowsPath(named).relative_to(PureWindowsPath(str(folder))).as_posix()
        except ValueError:
            relative = PurePosixPath(named.replace("\\", "/")).name
    return f"{relative} line {place.get('line')}"


def _middle(word: list[Any]) -> tuple[float, float]:
    return (float(word[0]) + float(word[2])) / 2, (float(word[1]) + float(word[3])) / 2


def _at(words: list[list[Any]], spot: tuple[float, float]) -> list[Any] | None:
    """The word under a point, else the nearest."""
    if not words:
        return None
    for word in words:
        if word[0] <= spot[0] <= word[2] and word[1] <= spot[1] <= word[3]:
            return word
    return min(words, key=lambda word: (_middle(word)[0] - spot[0]) ** 2 + (_middle(word)[1] - spot[1]) ** 2)


def _before(words: list[list[Any]], spot: tuple[float, float]) -> list[Any] | None:
    """The word on a point's line that ends nearest to its left."""
    line = [word for word in words if word[1] <= spot[1] <= word[3] and word[2] <= spot[0] + 1]
    return max(line, key=lambda word: word[2]) if line else None


def _quoted(words: list[Any]) -> str:
    text = " ".join(str(word[4]) for word in words if word)
    return repr(text if len(text) <= QUOTED else text[:QUOTED] + "…")
