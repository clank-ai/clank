"""Compiling clean (design 0020 §8): a change to a LaTeX file must leave its document building, with no undefined
reference or citation and no label defined twice that the document did not have before.

`root_of` finds the document a file belongs to: its `% !TEX root` magic comment, the file itself when it has
`\\documentclass`, else the file that includes it (`\\input`, `\\include`, `\\subfile`, named from the including file's
folder or the folder's root, `.tex` left out or not), two levels up at most; None for a fragment no document includes.
`engine_of` is its engine: `% !TEX program`, LuaLaTeX for a document that loads `fontspec` or `unicode-math`, else
pdfLaTeX. `parse_log` reads a build's log (and BibTeX's): its errors, with their file and line under
`-file-line-error`; its undefined references and citations (LaTeX's own warnings, natbib's, biblatex's, BibTeX's
missing entries); its labels defined twice. `compile_problems` turns a build after a change, against the build before
it, into refusals.

`Builder` builds in the workspace's container, through the build helper the TeX layer puts there
(`/opt/clank/latex_build.py`): the document with the changed file as it would be, in a scratch tree of links to the
folder's files, never writing in the folder. The document as it is now is built once and kept until a LaTeX file of
the folder changes (`fingerprint`). A container without the helper has no TeX: the build says so, for the owner.
"""

import hashlib
import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Any

from clank.components.agents.latex.citations import uncommented

HELPER = "/opt/clank/latex_build.py"  # the build helper, in the TeX layer
SECONDS = 120.0  # a build's limit
NO_TEX = "TeX is not in {workspace}'s container, so the document could not be built: `clank latex setup` adds it"
MAGIC_ROOT = re.compile(r"%\s*!\s*TEX\s+root\s*=\s*(\S.*?)\s*$", re.I | re.M)
MAGIC_PROGRAM = re.compile(r"%\s*!\s*TEX\s+(?:TS-)?program\s*=\s*(\w+)", re.I)
INCLUDES = re.compile(r"\\(?:input|include|subfile)\s*\{([^}]+)\}")
FILE_LINE = re.compile(r"^(?:\./)?(.+?\.(?:tex|sty|cls|bbl)):(\d+): (.+)$")
REFERENCE = re.compile(r"LaTeX Warning: Reference [`']([^']+)' on page")
CITATION = re.compile(r"Citation [`']([^']+)' (?:on page .*?)?undefined")
LABEL = re.compile(r"LaTeX Warning: Label [`']([^']+)' multiply defined")
BIBTEX_MISSING = re.compile(r"I didn't find a database entry for \"([^\"]+)\"")
BIBER_MISSING = re.compile(r"WARN - I didn't find a database entry for '([^']+)'")
LATEX_FILES = {".tex", ".bib", ".sty", ".cls", ".bst", ".bbx", ".cbx", ".def"}
SKIPPED = {".git", ".clank", "node_modules", ".venv", "venv", "__pycache__", ".ipynb_checkpoints", ".lake"}
Run = Callable[[str, list[str], bytes, float], Any]  # (workspace, argv, input, timeout) -> an Answer


@dataclass
class BuildLog:
    """What a build's log says: its errors, its undefined references and citations, its labels defined twice."""

    errors: list[str] = field(default_factory=list)
    references: set[str] = field(default_factory=set)
    citations: set[str] = field(default_factory=set)
    labels: set[str] = field(default_factory=set)


@dataclass
class Built:
    """A build in the container: whether it built, its log read, and why it could not be made at all (`unbuilt`)."""

    built: bool
    log: BuildLog
    unbuilt: str = ""
    seconds: float = 0.0


def root_of(relative: str, texts: dict[str, str]) -> str | None:
    """The document `relative` belongs to, from the folder; None for a fragment no document includes."""
    text = texts.get(relative, "")
    head = "\n".join(text.split("\n")[:20])
    magic = MAGIC_ROOT.search(head)
    if magic:
        return _joined(str(PurePosixPath(relative).parent), magic.group(1).strip())
    if "\\documentclass" in uncommented(text):
        return relative
    seen = {relative}
    wanted = [relative]
    for _ in range(2):
        found = [name for name, other in texts.items() if name not in seen and _includes(name, other, wanted)]
        for name in found:
            if "\\documentclass" in uncommented(texts[name]):
                return name
        seen.update(found)
        wanted = found
        if not wanted:
            break
    return None


def engine_of(text: str) -> str:
    """latexmk's engine for a document: its magic comment's, LuaLaTeX for its fonts, else pdfLaTeX."""
    magic = MAGIC_PROGRAM.search("\n".join(text.split("\n")[:20]))
    if magic:
        named = magic.group(1).lower()
        return {"pdflatex": "pdf", "xelatex": "xelatex", "lualatex": "lualatex"}.get(named, "pdf")
    plain = uncommented(text)
    return "lualatex" if re.search(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*(?:fontspec|unicode-math)", plain) else "pdf"


def parse_log(log: str, bibliography: str = "") -> BuildLog:
    """A build's log, and its BibTeX's or biber's, read."""
    found = BuildLog()
    lines = log.splitlines()
    for number, line in enumerate(lines):
        located = FILE_LINE.match(line)
        if located and "Fatal error occurred" not in line:
            found.errors.append(f"{PurePosixPath(located.group(1)).name} line {located.group(2)}: {located.group(3)}")
        elif line.startswith("! ") and "Fatal error occurred" not in line and not found.errors:
            found.errors.append(line[2:].strip())
        joined = line + (lines[number + 1] if number + 1 < len(lines) else "")
        for pattern, kept in ((REFERENCE, found.references), (CITATION, found.citations), (LABEL, found.labels)):
            match = pattern.search(joined)
            if match:
                kept.add(match.group(1))
    for pattern in (BIBTEX_MISSING, BIBER_MISSING):
        found.citations.update(match.group(1) for match in pattern.finditer(bibliography))
    return found


def compile_problems(before: BuildLog | None, after: BuildLog, *, built: bool) -> list[str]:
    """The refusals for a build after a change, against the build before it (None: there was none)."""
    if not built:
        first = after.errors[0] if after.errors else "the log says no more (see the build's log)"
        return [f"the document no longer builds: {first}"]
    had = before or BuildLog()
    problems = []
    for what, now, then, more in (
        ("an undefined reference", after.references, had.references, " (a \\ref to no \\label)"),
        ("an undefined citation", after.citations, had.citations, ""),
        ("a label defined twice", after.labels, had.labels, ""),
    ):
        added = sorted(now - then)
        if added:
            problems.append(f"its build has {what}: {', '.join(added)}{more}")
    return problems


def fingerprint(folder: str) -> str:
    """What the folder's LaTeX files are now: their paths, sizes and times, as one checksum."""
    digest = hashlib.sha256()
    for top, folders, files in os.walk(folder):
        folders[:] = sorted(each for each in folders if each not in SKIPPED)
        for name in sorted(files):
            if os.path.splitext(name)[1].lower() in LATEX_FILES:
                path = os.path.join(top, name)
                try:
                    stat = os.stat(path)
                except OSError:
                    continue
                digest.update(f"{os.path.relpath(path, folder)}\0{stat.st_size}\0{stat.st_mtime_ns}\n".encode())
    return digest.hexdigest()


class Builder:
    """Builds in a workspace's container through the TeX layer's helper (`run` is the workspaces' `run_in`)."""

    def __init__(self, run: Run, seconds: float = SECONDS) -> None:
        self.run = run
        self.seconds = seconds
        self._before: dict[tuple[str, str, str], Built] = {}

    def build(self, workspace: str, root: str, file: str, text: str | None, engine: str) -> Built:
        """The document built with `file` as `text` (None: as it is in the folder)."""
        asked = {"mode": "build", "root": root, "file": file, "text": text, "engine": engine,
                 "seconds": self.seconds}  # fmt: skip
        return self._built(workspace, asked)

    def marked(
        self, workspace: str, root: str, file: str, before: str | None, after: str, engine: str, keep: str
    ) -> tuple[str, str]:
        """The PDF of a change (design 0020 §9), kept in `keep` under the folder: the document marked by latexdiff
        between `before` and `after`, or, for a new file (`before` None), the document built as it is after; its path
        from the folder and whether it is marked, or ("", why) when it could not be made."""
        if before is None:
            asked = {"mode": "build", "root": root, "file": file, "text": after, "engine": engine,
                     "seconds": self.seconds, "keep": keep}  # fmt: skip
            said = self._said(workspace, asked)
            kept = said.get("kept") or {}
            return (str(kept.get("pdf") or ""), "") if said.get("built") else ("", str(said.get("unbuilt") or ""))
        asked = {"mode": "diff", "root": root, "file": file, "before": before, "after": after, "engine": engine,
                 "seconds": self.seconds * 1.5, "keep": keep}  # fmt: skip
        said = self._said(workspace, asked)
        return (str(said.get("pdf") or ""), "marked") if said.get("built") else ("", str(said.get("unbuilt") or ""))

    def before(self, workspace: str, folder: str, root: str, engine: str) -> Built:
        """The document as it is now, built once until a LaTeX file of the folder changes."""
        key = (workspace, root, fingerprint(folder))
        if key not in self._before:
            if len(self._before) > 20:
                self._before.clear()
            self._before[key] = self.build(workspace, root, root, None, engine)
        return self._before[key]

    def _built(self, workspace: str, asked: dict[str, Any]) -> Built:
        said = self._said(workspace, asked)
        if said.get("unbuilt"):
            return Built(False, BuildLog(), unbuilt=str(said["unbuilt"]))
        log = parse_log(str(said.get("log") or ""), str(said.get("blg") or ""))
        return Built(bool(said.get("built")), log, seconds=float(said.get("seconds") or 0.0))

    def _said(self, workspace: str, asked: dict[str, Any]) -> dict[str, Any]:
        """The helper's answer to a request; `unbuilt` saying why when there is none to read."""
        try:
            answer = self.run(workspace, ["python3", HELPER], json.dumps(asked).encode(), self.seconds * 2 + 30)
        except Exception as error:  # noqa: BLE001: the workspace's own words (its container does not run)
            return {"unbuilt": str(error)}
        try:
            said: dict[str, Any] = json.loads(answer.output)
        except ValueError:
            missing = "No such file" in answer.errors or "can't open file" in answer.errors
            why = NO_TEX.format(workspace=workspace) if missing else (answer.errors or answer.output).strip()[-400:]
            return {"unbuilt": why or "the build helper said nothing"}
        if said.get("missing"):
            return {"unbuilt": NO_TEX.format(workspace=workspace)}
        if said.get("timeout"):
            return {"unbuilt": f"the build took longer than {self.seconds:g} seconds"}
        if said.get("error"):
            return {"unbuilt": f"the build helper failed: {said['error']}"}
        return said


def _includes(name: str, text: str, wanted: list[str]) -> bool:
    """Whether a LaTeX file includes one of `wanted`, named from its own folder or the folder's root."""
    here = str(PurePosixPath(name).parent)
    for included in INCLUDES.findall(uncommented(text)):
        target = included.strip()
        target = target if target.endswith(".tex") else f"{target}.tex"
        if _joined(here, target) in wanted or _joined("", target) in wanted:
            return True
    return False


def _joined(base: str, named: str) -> str:
    parts: list[str] = []
    for part in [*(base.split("/") if base not in ("", ".") else []), *named.replace("\\", "/").split("/")]:
        if part in ("", "."):
            continue
        if part == "..":
            if parts:
                parts.pop()
            continue
        parts.append(part)
    return "/".join(parts)
