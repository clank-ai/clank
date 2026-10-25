"""Clank's LaTeX helper, in the TeX layer (design 0020 §8-§10, decision 0134): run in a workspace's container, it reads
one JSON request on its standard input and answers one JSON object on its standard output. Python's standard library
only.

- `build` {root, file, text, engine, seconds, keep}: the document `root` (from the folder) built with latexmk, the file
  `file` as `text` (null: as it is), in a scratch tree that never writes into the folder (`placed`: LaTeX's sources
  copied, what TeX only reads linked, what a build writes left out, so no build writes through a link). Answers whether
  it built, latexmk's status, the log and BibTeX's or biber's, and the time; with `keep` (a folder under `.clank/`),
  the PDF and its SyncTeX file are kept there, SyncTeX's paths made the folder's (`/workspace/...`).
- `diff` {root, file, before, after, engine, seconds, keep}: the document with `file` as `before` and as `after`,
  marked by latexdiff (`--flatten`, so `\\input` files are followed), built, and its PDF kept in `keep` as `diff.pdf`.
- `pages` {pdf, keep, dpi}: a PDF of the folder's pages as PNG images (`pdftoppm`) in `keep`, and each page's words
  with their boxes in points (`pdftotext -bbox-layout`) in `keep/words.json`.
- `where` {pdf, points: [{page, x, y}]}: for each point of a page (in points, from the page's top left), the source
  file and line SyncTeX gives, from the PDF's SyncTeX file.

With no latexmk (no TeX layer) every mode answers `missing`.
"""

import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any

WORKSPACE = os.environ.get("CLANK_WORKSPACE", "/workspace")
SKIPPED = {".git", ".clank", "node_modules", ".venv", "venv", "__pycache__", ".ipynb_checkpoints", ".lake", ".cache"}
SOURCES = {".tex", ".bib", ".sty", ".cls", ".bst", ".bbx", ".cbx", ".def", ".cfg", ".clo", ".fd", ".ltx", ".dtx"}
WRITTEN = {
    ".aux", ".log", ".out", ".toc", ".lof", ".lot", ".bbl", ".blg", ".fls", ".fdb_latexmk", ".bcf", ".xdv", ".dvi",
    ".nav", ".snm", ".vrb", ".idx", ".ind", ".ilg", ".glo", ".gls", ".glg", ".ist", ".acn", ".acr", ".alg", ".thm",
    ".loa", ".brf", ".auxlock", ".ptc", ".synctex", ".run.xml", ".synctex.gz", ".synctex(busy)",
}  # fmt: skip
ENGINES = {"pdf": "-pdf", "lualatex": "-lualatex", "xelatex": "-xelatex"}
MOST_FILES = 200_000
LOG_KEPT = 200_000  # characters of a log answered
WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', re.S)
PAGE = re.compile(r'<page width="([\d.]+)" height="([\d.]+)">(.*?)</page>', re.S)


def placed(relative: str, stems: dict[str, set[str]]) -> str:
    """How a file of the folder is in a build's scratch tree: `copy` (LaTeX's sources), `link` (what TeX only reads),
    or `skip` (what a build writes); `stems` names, for each folder, the stems of its `.tex` files."""
    name = relative.rsplit("/", 1)[-1]
    folder = relative.rsplit("/", 1)[0] if "/" in relative else ""
    lower = name.lower()
    if any(lower.endswith(suffix) for suffix in WRITTEN):
        return "skip"
    stem, _, suffix = name.rpartition(".")
    if f".{suffix.lower()}" in SOURCES:
        return "copy"
    if suffix.lower() == "pdf" and stem in stems.get(folder, set()):
        return "skip"  # a document's own PDF beside its .tex
    return "link"


def engine_argument(engine: str) -> str:
    """latexmk's argument for an engine."""
    return ENGINES.get(engine, "-pdf")


def synctex_place(said: str) -> dict[str, object] | None:
    """The file and line of SyncTeX's first answer; None when it gives none."""
    found = re.search(r"^Input:(.+)$", said, re.M)
    line = re.search(r"^Line:(-?\d+)$", said, re.M)
    if not found or not line:
        return None
    return {"input": os.path.normpath(found.group(1).strip()).replace(os.sep, "/"), "line": int(line.group(1))}


def word_boxes(text: str) -> list[dict[str, object]]:
    """Each page of `pdftotext -bbox-layout`'s answer: its size in points and its words with their boxes."""
    pages: list[dict[str, object]] = []
    for page in PAGE.finditer(text):
        words = [[float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)), html.unescape(m.group(5))]
                 for m in WORD.finditer(page.group(3))]  # fmt: skip
        pages.append({"width": float(page.group(1)), "height": float(page.group(2)), "words": words})
    return pages


def main() -> int:
    """Answer the one request on standard input."""
    try:
        asked = json.loads(sys.stdin.read() or "{}")
        answer = handle(asked)
    except Exception as error:  # noqa: BLE001: whatever happened, said as JSON
        answer = {"error": f"{type(error).__name__}: {error}"}
    sys.stdout.write(json.dumps(answer))
    return 0


def handle(asked: dict[str, Any]) -> dict[str, object]:
    """The answer to one request, by its mode."""
    if shutil.which("latexmk") is None:
        return {"missing": "latexmk: the TeX layer is not in this container"}
    mode = asked.get("mode")
    if mode == "build":
        return build(asked)
    if mode == "diff":
        return diff(asked)
    if mode == "pages":
        return pages(asked)
    if mode == "where":
        return where(asked)
    return {"error": f"no mode {mode!r}"}


def build(asked: dict[str, Any]) -> dict[str, object]:
    """The document built with the changed file as given, in a scratch tree; its PDF kept when asked."""
    root, file = str(asked["root"]), str(asked["file"])
    text = asked.get("text")
    scratch = tempfile.mkdtemp(prefix="clank-latex-")
    try:
        farm(scratch, {file: text} if isinstance(text, str) else {})
        done = latexmk(scratch, root, str(asked.get("engine") or "pdf"), float(asked.get("seconds") or 120))
        if done.get("built") and asked.get("keep"):
            done["kept"] = keep(scratch, root, str(asked["keep"]))
        return done
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def diff(asked: dict[str, Any]) -> dict[str, object]:
    """The document marked by latexdiff between the changed file before and after, built, its PDF kept."""
    root, file = str(asked["root"]), str(asked["file"])
    old_tree, new_tree = tempfile.mkdtemp(prefix="clank-latex-"), tempfile.mkdtemp(prefix="clank-latex-")
    seconds = float(asked.get("seconds") or 120)
    try:
        farm(old_tree, {file: str(asked.get("before") or "")})
        farm(new_tree, {file: str(asked.get("after") or "")})
        folder, name = os.path.split(root)
        stem = os.path.splitext(name)[0]
        marked = f"{stem}-clank-diff.tex"
        started = time.monotonic()
        made = subprocess.run(
            ["latexdiff", "--flatten", os.path.join(old_tree, root), os.path.join(new_tree, root)],
            cwd=os.path.join(new_tree, folder), capture_output=True, text=True, timeout=seconds, check=False,
        )  # fmt: skip
        if made.returncode != 0:
            return {"built": False, "status": made.returncode, "log": made.stderr[-LOG_KEPT:], "latexdiff": True}
        with open(os.path.join(new_tree, folder, marked), "w", encoding="utf-8") as written:
            written.write(made.stdout)
        left = max(10.0, seconds - (time.monotonic() - started))
        done = latexmk(new_tree, f"{folder}/{marked}" if folder else marked, str(asked.get("engine") or "pdf"), left)
        if done.get("built"):
            kept = keep(new_tree, f"{folder}/{marked}" if folder else marked, str(asked["keep"]))
            final = os.path.join(WORKSPACE, str(asked["keep"]), "diff.pdf")
            os.replace(os.path.join(WORKSPACE, str(kept["pdf"])), final)
            done["pdf"] = f"{asked['keep']}/diff.pdf"
        return done
    finally:
        shutil.rmtree(old_tree, ignore_errors=True)
        shutil.rmtree(new_tree, ignore_errors=True)


def pages(asked: dict[str, Any]) -> dict[str, object]:
    """A PDF's pages as images, and its words with their boxes."""
    pdf = os.path.join(WORKSPACE, str(asked["pdf"]))
    out = os.path.join(WORKSPACE, str(asked["keep"]))
    os.makedirs(out, exist_ok=True)
    _ignore(out)
    dpi = int(asked.get("dpi") or 110)
    rendered = subprocess.run(["pdftoppm", "-r", str(dpi), "-png", pdf, os.path.join(out, "page")],
                              capture_output=True, text=True, timeout=300, check=False)  # fmt: skip
    if rendered.returncode != 0:
        return {"error": f"pdftoppm: {rendered.stderr.strip()[-500:]}"}
    words = subprocess.run(["pdftotext", "-bbox-layout", pdf, "-"], capture_output=True, text=True, timeout=300,
                           check=False)  # fmt: skip
    boxes = word_boxes(words.stdout) if words.returncode == 0 else []
    with open(os.path.join(out, "words.json"), "w", encoding="utf-8") as written:
        json.dump(boxes, written)
    images = sorted((name for name in os.listdir(out) if name.startswith("page-") and name.endswith(".png")),
                    key=lambda name: int(re.sub(r"\D", "", name) or 0))  # fmt: skip
    shown = []
    for number, image in enumerate(images):
        size = boxes[number] if number < len(boxes) else {"width": 0.0, "height": 0.0}
        shown.append({"image": f"{asked['keep']}/{image}", "width": size["width"], "height": size["height"]})
    return {"pages": shown, "dpi": dpi, "words": f"{asked['keep']}/words.json"}


def where(asked: dict[str, Any]) -> dict[str, object]:
    """The source file and line of each point of a page."""
    pdf = os.path.join(WORKSPACE, str(asked["pdf"]))
    found = []
    for point in asked.get("points") or []:
        place = f"{int(point['page'])}:{float(point['x']):.2f}:{float(point['y']):.2f}:{pdf}"
        said = subprocess.run(["synctex", "edit", "-o", place], capture_output=True, text=True, timeout=30,
                              check=False)  # fmt: skip
        found.append(synctex_place(said.stdout))
    return {"places": found}


def farm(scratch: str, replaced: dict[str, object]) -> None:
    """The scratch tree: each folder made, each file copied, linked or left out (`placed`); the files in `replaced`
    written with their text."""
    stems: dict[str, set[str]] = {}
    listed: list[tuple[str, str]] = []
    for top, folders, files in os.walk(WORKSPACE):
        folders[:] = [each for each in folders if each not in SKIPPED]
        here = os.path.relpath(top, WORKSPACE).replace(os.sep, "/")
        here = "" if here == "." else here
        for name in files:
            if name.endswith(".tex"):
                stems.setdefault(here, set()).add(name[: -len(".tex")])
            listed.append((here, name))
            if len(listed) > MOST_FILES:
                break
    for here, name in listed:
        relative = f"{here}/{name}" if here else name
        if relative in replaced:
            continue
        how = placed(relative, stems)
        if how == "skip":
            continue
        target = os.path.join(scratch, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        source = os.path.join(WORKSPACE, relative)
        if how == "copy":
            shutil.copyfile(source, target)
        else:
            os.symlink(source, target)
    for relative, text in replaced.items():
        target = os.path.join(scratch, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as written:
            written.write(str(text))


def latexmk(scratch: str, root: str, engine: str, seconds: float) -> dict[str, object]:
    """latexmk run on the root in the scratch tree, within `seconds`: whether it built, its log and its time."""
    folder, name = os.path.split(root)
    where_built = os.path.join(scratch, folder)
    argv = ["latexmk", engine_argument(engine), "-interaction=nonstopmode", "-halt-on-error", "-file-line-error",
            "-synctex=1", name]  # fmt: skip
    started = time.monotonic()
    try:
        done = subprocess.run(argv, cwd=where_built, capture_output=True, text=True, timeout=seconds, check=False)
    except subprocess.TimeoutExpired:
        return {"timeout": True, "seconds": round(time.monotonic() - started, 2)}
    stem = os.path.splitext(name)[0]
    log = _read(os.path.join(where_built, f"{stem}.log"))
    bibliography = _read(os.path.join(where_built, f"{stem}.blg"))
    built = done.returncode == 0 and os.path.isfile(os.path.join(where_built, f"{stem}.pdf"))
    return {"built": built, "status": done.returncode, "log": log[-LOG_KEPT:], "blg": bibliography[-50_000:],
            "output": done.stdout[-5000:], "seconds": round(time.monotonic() - started, 2)}  # fmt: skip


def keep(scratch: str, root: str, kept: str) -> dict[str, object]:
    """The built PDF and its SyncTeX file, copied into `kept` (under `.clank/`), SyncTeX's paths made the folder's."""
    folder, name = os.path.split(root)
    stem = os.path.splitext(name)[0]
    out = os.path.join(WORKSPACE, kept)
    os.makedirs(out, exist_ok=True)
    _ignore(out)
    shutil.copyfile(os.path.join(scratch, folder, f"{stem}.pdf"), os.path.join(out, f"{stem}.pdf"))
    synctex = os.path.join(scratch, folder, f"{stem}.synctex.gz")
    if os.path.isfile(synctex):
        import gzip

        with gzip.open(synctex, "rt", encoding="utf-8", errors="replace") as read:
            text = read.read().replace(scratch.rstrip("/") + "/", WORKSPACE.rstrip("/") + "/")
        with gzip.open(os.path.join(out, f"{stem}.synctex.gz"), "wt", encoding="utf-8") as written:
            written.write(text)
    return {"pdf": f"{kept}/{stem}.pdf"}


def _ignore(out: str) -> None:
    """`.clank/` stays out of git."""
    clank = os.path.join(WORKSPACE, ".clank")
    if out.startswith(clank) and not os.path.exists(os.path.join(clank, ".gitignore")):
        os.makedirs(clank, exist_ok=True)
        with open(os.path.join(clank, ".gitignore"), "w", encoding="utf-8") as written:
            written.write("*\n")


def _read(path: str) -> str:
    try:
        with open(path, encoding="utf-8", errors="replace") as read:
            return read.read()
    except OSError:
        return ""


if __name__ == "__main__":
    sys.exit(main())
