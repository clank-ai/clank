"""Finding the figures of a folder by words (design 0018 §7.4), for Clank's own MCP server's `find_figures`.

Run in the container, over the folder as it sees it (`/workspace`), with Python's standard library only, reading only.
A figure is an image or a PDF (`FIGURES`) anywhere in the folder but the folders of tools and environments (`SKIPPED`).
What is known of each, and searched: its name and folder; what Matplotlib recorded when it saved it
(`.clank/figures/<path>.json`, design 0008 §3: the figure's and each plot's title, the axis labels, the legend and the
lines' labels, and the script that saved it); the `\\caption` and `\\label` of a LaTeX figure environment that includes
it (`\\includegraphics`, its extension left out or not, from the `.tex` file's folder or the folder's root); a script
that names it in a string (`plt.savefig("figs/phases.pdf")`); and when it was last written.

A query's words are matched against each field's words (a word matches the same word, or one it begins or that begins
it, four letters at least, with a plural's s left out), each field with its weight (`WEIGHTS`); its date words (today,
yesterday, this week, last week, a weekday) keep the figures of that time first, and latest (newest, most recent) puts
the newest first. The answer lists the best figures, each with what is known of it and the words it matched; with none,
it says so and names the newest.
"""

import json
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import PurePosixPath

FIGURES = {".png", ".jpg", ".jpeg", ".pdf", ".svg", ".eps", ".gif", ".webp"}
SCRIPTS = {".py", ".ipynb", ".jl", ".m", ".r", ".gp", ".sh"}
SKIPPED = {
    ".git", ".hg", ".svn", ".clank", "node_modules", ".venv", "venv", "__pycache__", ".ipynb_checkpoints",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".lake", ".cache", "site-packages",
}  # fmt: skip
MOST_FILES = 50_000  # files looked at in a walk
LARGEST_TEXT = 2 << 20  # a .tex file or a script read whole, at most
WEIGHTS = {"name": 3.0, "caption": 3.0, "title": 2.5, "label": 2.0, "axes": 2.0, "legend": 1.5, "folder": 1.0,
           "script": 1.0}  # fmt: skip
QUIET = {
    "a", "an", "the", "of", "from", "with", "for", "in", "on", "at", "to", "and", "or", "my", "me", "that", "this",
    "these", "those", "it", "its", "show", "open", "pull", "up", "find", "see", "look", "figure", "figures", "fig",
    "plot", "plots", "graph", "image", "picture", "chart", "file", "one", "made", "we", "i", "you", "please",
}  # fmt: skip
LATEST = {"latest", "newest", "recent"}
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
FIGURE_ENV = re.compile(r"\\begin\{(figure\*?|wrapfigure|subfigure)\}(.*?)\\end\{\1\}", re.S)
INCLUDE = re.compile(r"\\includegraphics\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
LABEL = re.compile(r"\\label\{([^}]*)\}")
NAMED = re.compile(r"[\"']([^\"'\n]+\.(?:png|jpe?g|pdf|svg|eps|gif|webp))[\"']", re.I)


@dataclass
class Figure:
    """A figure of the folder and what is known of it."""

    path: str
    written: float
    fields: dict[str, list[str]] = field(default_factory=dict)  # each field's texts, by name (WEIGHTS)
    script: str = ""  # the script Matplotlib recorded
    named_in: list[str] = field(default_factory=list)  # scripts that name it
    captions: list[str] = field(default_factory=list)  # each caption with where it is, as said


def find(root: str, query: str, limit: int = 5, now: float | None = None) -> str:
    """The figures of the folder best matching the query, in words."""
    moment = time.time() if now is None else now
    figures, texts = _walk(root)
    for figure in figures:
        _recorded(root, figure)
    _latex(root, texts, figures)
    _scripts(root, texts, figures)
    words, window, latest = _query(query, moment)
    newest = sorted(figures, key=lambda each: -each.written)
    scored = []
    for figure in figures:
        score, matched = _score(figure, words)
        dated = window is not None and window[0] <= figure.written < window[1]
        if words and score == 0:
            continue
        if not words and not dated and not latest:
            continue
        scored.append((score + (3.0 if dated else 0.0), dated, figure, matched))
    if window is not None:
        scored = [each for each in scored if each[1]] or ([] if not words else scored)
    if latest:
        scored.sort(key=lambda each: -each[2].written)
    else:
        scored.sort(key=lambda each: (-each[0], -each[2].written))
    if not scored:
        names = ", ".join(each.path for each in newest[:5]) or "none: the folder has no figure"
        return f"No figure of the folder matches {query.strip()!r}. The newest: {names}."
    lines = [_said(number, figure, matched, moment) for number, (_, _, figure, matched) in
             enumerate(scored[: max(1, limit)], start=1)]  # fmt: skip
    return "\n".join([*lines, "", "Open the ones the user wants with show_files."])


def _walk(root: str) -> tuple[list[Figure], list[str]]:
    """The figures of the folder, and its .tex files and scripts, from the folder."""
    figures: list[Figure] = []
    texts: list[str] = []
    seen = 0
    for top, folders, files in os.walk(root):
        folders[:] = sorted(each for each in folders if each not in SKIPPED)
        for name in sorted(files):
            seen += 1
            if seen > MOST_FILES:
                return figures, texts
            full = os.path.join(top, name)
            relative = os.path.relpath(full, root).replace(os.sep, "/")
            suffix = os.path.splitext(name)[1].lower()
            if suffix in FIGURES:
                try:
                    figures.append(Figure(relative, os.path.getmtime(full)))
                except OSError:
                    continue
            elif suffix == ".tex" or suffix in SCRIPTS:
                texts.append(relative)
    return figures, texts


def _recorded(root: str, figure: Figure) -> None:
    """What Matplotlib recorded of the figure when it saved it, and its name and folder."""
    path = PurePosixPath(figure.path)
    figure.fields["name"] = [path.stem.replace("_", " ").replace("-", " ")]
    figure.fields["folder"] = [str(path.parent).replace("/", " ")]
    kept = os.path.join(root, ".clank", "figures", *f"{figure.path}.json".split("/"))
    try:
        with open(kept, encoding="utf-8") as file:
            shape = json.load(file)
    except (OSError, ValueError):
        return
    titles = [shape.get("title") or ""]
    axes: list[str] = []
    legend: list[str] = []
    for plot in shape.get("axes") or []:
        titles.append(plot.get("title") or "")
        axes += [plot.get("xlabel") or "", plot.get("ylabel") or ""]
        series = [*(plot.get("lines") or []), *(plot.get("scatters") or [])]
        legend += [str(line.get("label") or "") for line in series if not str(line.get("label") or "").startswith("_")]
        legend += list((plot.get("legend") or {}).get("entries") or [])
    figure.fields["title"] = [each for each in titles if each]
    figure.fields["axes"] = [each for each in axes if each]
    figure.fields["legend"] = list(dict.fromkeys(each for each in legend if each))
    figure.script = str(shape.get("script") or "")
    if figure.script:
        figure.fields.setdefault("script", []).append(figure.script.replace("/", " ").replace("_", " "))


def _latex(root: str, texts: list[str], figures: list[Figure]) -> None:
    """The captions and labels of the LaTeX figure environments that include each figure."""
    by_stem = {_stem(figure.path): figure for figure in figures}
    for relative in texts:
        if not relative.endswith(".tex"):
            continue
        text = _read(root, relative)
        here = str(PurePosixPath(relative).parent)
        for environment in FIGURE_ENV.finditer(text):
            body = environment.group(2)
            caption = _caption(body)
            labels = LABEL.findall(body)
            for included in INCLUDE.findall(body):
                for base in (here, ""):
                    figure = by_stem.get(_stem(_joined(base, included.strip())))
                    if figure is None:
                        continue
                    figure.fields.setdefault("caption", []).append(caption)
                    figure.fields.setdefault("label", []).extend(label.replace(":", " ") for label in labels)
                    where = ", ".join([relative, *labels])
                    figure.captions.append(f"caption {caption!r} ({where})" if caption else f"in {where}")
                    break


def _scripts(root: str, texts: list[str], figures: list[Figure]) -> None:
    """The scripts that name each figure in a string."""
    by_name: dict[str, list[Figure]] = {}
    for figure in figures:
        by_name.setdefault(PurePosixPath(figure.path).name.lower(), []).append(figure)
    for relative in texts:
        if relative.endswith(".tex"):
            continue
        for named in NAMED.findall(_read(root, relative)):
            for figure in by_name.get(PurePosixPath(named.replace("\\", "/")).name.lower(), []):
                if relative != figure.script and relative not in figure.named_in:
                    figure.named_in.append(relative)
                    figure.fields.setdefault("script", []).append(relative.replace("/", " ").replace("_", " "))


def _query(query: str, now: float) -> tuple[list[str], tuple[float, float] | None, bool]:
    """The query's words to match, the time its date words name (from, to), and whether it asks for the latest."""
    text = query.lower()
    today = datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
    window: tuple[datetime, datetime] | None = None
    monday = today - timedelta(days=today.weekday())
    spans = {
        "last week": (monday - timedelta(days=7), monday),
        "this week": (monday, today + timedelta(days=1)),
        "yesterday": (today - timedelta(days=1), today),
        "today": (today, today + timedelta(days=1)),
    }
    for phrase, span in spans.items():
        if phrase in text:
            window = window or span
            text = text.replace(phrase, " ")
    for number, day in enumerate(WEEKDAYS):
        if re.search(rf"\b{day}\b", text):
            back = (today.weekday() - number) % 7
            window = window or (today - timedelta(days=back), today - timedelta(days=back - 1))
            text = re.sub(rf"\b{day}\b", " ", text)
    raw = re.findall(r"[a-z0-9]+", text)
    latest = any(word in LATEST for word in raw) or "most recent" in text
    words = [_plain(word) for word in raw if word not in QUIET and word not in LATEST and word != "most"]
    between = (window[0].timestamp(), window[1].timestamp()) if window else None
    return list(dict.fromkeys(words)), between, latest


def _score(figure: Figure, words: list[str]) -> tuple[float, list[str]]:
    """How well the figure matches the words, and the words it matched."""
    total = 0.0
    matched = []
    for word in words:
        best = 0.0
        for name, texts in figure.fields.items():
            if any(_matches(word, each) for text in texts for each in re.findall(r"[a-z0-9]+", text.lower())):
                best = max(best, WEIGHTS[name])
        if best:
            total += best
            matched.append(word)
    return total, matched


def _matches(word: str, other: str) -> bool:
    other = _plain(other)
    if word == other:
        return True
    shorter = min(len(word), len(other))
    return shorter >= 4 and (word.startswith(other) or other.startswith(word))


def _said(number: int, figure: Figure, matched: list[str], now: float) -> str:
    """One figure found: its path, when and by what it was made, what is known of it, the words it matched."""
    parts = [f"{number}. {figure.path}", f"written {_when(figure.written, now)}"]
    if figure.script:
        parts.append(f"made by {figure.script}")
    if figure.fields.get("title"):
        parts.append("title " + ", ".join(repr(each) for each in figure.fields["title"]))
    if figure.fields.get("axes"):
        parts.append("axes " + ", ".join(repr(each) for each in figure.fields["axes"]))
    if figure.fields.get("legend"):
        parts.append("legend " + ", ".join(repr(each) for each in figure.fields["legend"]))
    parts += figure.captions
    if figure.named_in:
        parts.append("named in " + ", ".join(figure.named_in))
    if matched:
        parts.append("matched: " + ", ".join(matched))
    return " · ".join(parts)


def _when(written: float, now: float) -> str:
    day = datetime.fromtimestamp(written)
    days = (datetime.fromtimestamp(now).date() - day.date()).days
    named = {0: "today", 1: "yesterday"}.get(days, day.strftime("%Y-%m-%d"))
    return f"{named} {day.strftime('%H:%M')}"


def _caption(body: str) -> str:
    """The text of the first `\\caption` in a figure environment, its braces matched; whitespace collapsed."""
    found = re.search(r"\\caption\s*(?:\[[^\]]*\])?\s*\{", body)
    if found is None:
        return ""
    depth, start = 1, found.end()
    for index in range(start, len(body)):
        if body[index] == "{" and body[index - 1] != "\\":
            depth += 1
        elif body[index] == "}" and body[index - 1] != "\\":
            depth -= 1
            if depth == 0:
                return " ".join(body[start:index].split())
    return " ".join(body[start:].split())


def _joined(base: str, included: str) -> str:
    parts: list[str] = []
    for part in [*(base.split("/") if base and base != "." else []), *included.split("/")]:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)


def _stem(path: str) -> str:
    """A path without its figure extension, for matching `\\includegraphics{figs/phases}` with figs/phases.pdf."""
    pure = PurePosixPath(path)
    return str(pure.with_suffix("")) if pure.suffix.lower() in FIGURES else str(pure)


def _plain(word: str) -> str:
    return word[:-1] if len(word) > 3 and word.endswith("s") and not word.endswith("ss") else word


def _read(root: str, relative: str) -> str:
    full = os.path.join(root, *relative.split("/"))
    try:
        if os.path.getsize(full) > LARGEST_TEXT:
            return ""
        with open(full, encoding="utf-8", errors="replace") as file:
            return file.read()
    except OSError:
        return ""
