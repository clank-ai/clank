"""The checks on every LaTeX change (design 0020 §4 and §5), as the review asks them.

`kind_of` says which LaTeX files a path is: `tex`, `bib`, or `style` (class, style and bibliography style files).
`LatexChecks.forced` is §4's rule: a `.tex` file the owner had, a `.bib` file and a style file are always asked about,
in auto mode too; a `.tex` file the agent created (`Created`, kept in the home's state once it is written) follows the
workspace's mode. `LatexChecks.check` checks a change before anyone is asked or answered, the cheapest first: for a
`.tex` file its citations (§6) and its values' sources (§7), then, when they pass, its document's build in the container
(§8); for a `.bib` file its new and changed entries against their records (§6). Its `Verdict` holds the refusals (the
model fixes them), what could not be checked (the owner decides), what passed, and how many claims are marked
`% UNVERIFIED`.
"""

import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

from clank.components.agents.latex.building import SKIPPED, Builder, compile_problems, engine_of, root_of
from clank.components.agents.latex.citations import Lookup, bib_entries, bibliographies, cite_keys, entry_problems
from clank.components.agents.latex.citations import missing_citations as missing
from clank.components.agents.latex.sources import source_problems, unverified, values
from clank.kernel.events import Actor, EventType, Subject

if TYPE_CHECKING:
    from clank.kernel.core import Kernel

ACTOR = Actor(kind="clank", via="LaTeX checks")
KINDS = {".tex": "tex", ".bib": "bib", ".cls": "style", ".sty": "style", ".bst": "style"}
LARGEST = 2 << 20  # bytes of a .tex or .bib file read
MOST_TEX = 500  # .tex files read to find a document's root
EVENT_TYPES = [
    EventType(
        "agents.latex_diff",
        "The PDF of a LaTeX change waiting for your review (design 0020 §9): its document marked by latexdiff (removed "
        "text struck in red, new text in blue), or a new document as built; VS Code opens it beside the diff.",
        {
            "workspace": "The workspace.", "folder": "Its folder.", "change": "The change's id.",
            "file": "The file changed.", "pdf": "The PDF, from the folder (under .clank/latex/).",
            "marked": "Whether the changes are marked (false: a new document, as built).",
        },
    ),
    EventType(
        "agents.change_checked",
        "Clank checked a change the agent asked to make to a LaTeX file (design 0020 §5): its citations, its values' "
        "sources and its document's build; a change that fails is rejected with its reasons, the model told why.",
        {
            "workspace": "The workspace.", "change": "The change's id.", "file": "The file, in its folder.",
            "passed": "Whether it passed.", "refusals": "Why it was refused, each a sentence.",
            "unchecked": "What could not be checked, for you.", "refused_in_a_row": "Refusals of this file in a row.",
        },
    )
]  # fmt: skip


class BuildError(Exception):
    """A document that cannot be built, and why."""


def kind_of(relative: str) -> str | None:
    """Which LaTeX file a path is: tex, bib or style; None for any other file."""
    return KINDS.get(PurePosixPath(relative).suffix.lower())


@dataclass
class Verdict:
    """A check's outcome: refusals, what could not be checked, what passed, and the claims marked UNVERIFIED."""

    refusals: list[str] = field(default_factory=list)
    unchecked: list[str] = field(default_factory=list)
    passed: list[str] = field(default_factory=list)
    unverified: int = 0
    root: str = ""  # the document built, once it was
    engine: str = ""

    def view(self) -> dict[str, Any]:
        """As kept with the change."""
        return {"refusals": self.refusals, "unchecked": self.unchecked, "passed": self.passed,
                "unverified": self.unverified, "root": self.root, "engine": self.engine}  # fmt: skip

    def summary(self) -> str:
        """What the owner reads above the change."""
        lines = []
        if self.passed:
            lines.append(f"Clank's LaTeX checks passed: {', '.join(self.passed)}.")
        lines += [f"NOT CHECKED: {each}" for each in self.unchecked]
        if self.unverified:
            lines.append(f"{self.unverified} claim{'s' if self.unverified != 1 else ''} marked % UNVERIFIED.")
        return "\n".join(lines)


def refusal_message(relative: str, refusals: list[str]) -> str:
    """What the model is told of a refused change."""
    listed = "\n".join(f"- {each}" for each in refusals)
    return (
        f"Clank's LaTeX checks refused this change to {relative}: fix each, then propose the change again "
        f"(design 0020).\n{listed}"
    )


class Created:
    """The `.tex` files each workspace's agent created, once written: kept in a JSON file of the home's state."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def has(self, workspace: str, relative: str) -> bool:
        """Whether the agent created this `.tex` file of the workspace."""
        return relative in self._read().get(workspace, [])

    def add(self, workspace: str, relative: str) -> None:
        """Keep that the agent created this `.tex` file of the workspace."""
        with self._lock:
            known = self._read()
            if relative not in known.setdefault(workspace, []):
                known[workspace].append(relative)
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(known, indent=1), encoding="utf-8")

    def _read(self) -> dict[str, list[str]]:
        try:
            found: dict[str, list[str]] = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return found


class LatexChecks:
    """The rule and the checks for the agent's LaTeX changes."""

    ACTOR = ACTOR

    def __init__(self, kernel: "Kernel") -> None:
        self.kernel = kernel
        self.builder = Builder(self.run)
        self.lookup = Lookup()
        self.created = Created(kernel.home.state / "latex-created.json")

    def forced(self, workspace: str, relative: str, created: bool) -> bool:
        """Whether a change to this file is asked about whatever the mode (§4)."""
        kind = kind_of(relative)
        if kind in ("bib", "style"):
            return True
        if kind == "tex":
            return not created and not self.created.has(workspace, relative)
        return False

    def check(self, change: dict[str, Any]) -> Verdict:
        """A LaTeX change checked before anyone is asked or answered."""
        relative, folder = str(change["relative"]), Path(change["folder"])
        before, after = change.get("before"), change.get("after")
        kind = kind_of(relative)
        verdict = Verdict()
        if after is None:
            verdict.unchecked.append("what the file would be after the change could not be worked out")
            return verdict
        if kind == "bib":
            problems, unchecked = entry_problems(before, after, self.lookup)
            verdict.refusals += problems
            verdict.unchecked += unchecked
            if not problems:
                added = len(set(bib_entries(after)) - set(bib_entries(before or "")))
                verdict.passed.append(f"entries ({added} added, each matching its record)" if added else "entries")
            return verdict
        if kind != "tex":
            return verdict
        texts = self._texts(folder, relative, after)
        root = root_of(relative, texts)
        known, loaded, where = self._bibliography(folder, root or relative, texts)
        cited = missing(before, after, known, loaded=loaded)
        verdict.refusals += cited
        here = str(PurePosixPath(relative).parent)
        sourced = source_problems(before, after, folder=folder, here="" if here == "." else here, keys=known)
        verdict.refusals += sourced
        verdict.unverified = len(unverified(after))
        if verdict.refusals:
            return verdict
        new_keys = {each.key for each in cite_keys(after)} - {each.key for each in cite_keys(before or "")}
        verdict.passed.append(f"citations ({len(new_keys)} added, each in {where})" if new_keys else
                              "citations (none added)")  # fmt: skip
        verdict.passed.append("sources (each value's given)" if any(values(after)) else "sources (no value stated)")
        if root is None:
            verdict.unchecked.append(f"no document includes {relative}, so it was not built")
            return verdict
        self._build(change, root, texts, verdict)
        return verdict

    def _build(self, change: dict[str, Any], root: str, texts: dict[str, str], verdict: Verdict) -> None:
        workspace, relative = str(change["workspace"]), str(change["relative"])
        engine = engine_of(texts.get(root, ""))
        after = self.builder.build(workspace, root, relative, str(change["after"]), engine)
        if after.unbuilt:
            verdict.unchecked.append(after.unbuilt)
            return
        before = None
        if not (change.get("created") and root == relative):
            built = self.builder.before(workspace, str(change["folder"]), root, engine)
            if built.unbuilt:
                verdict.unchecked.append(built.unbuilt)
                return
            if not built.built and not after.built:
                verdict.unchecked.append(f"{root} did not build before this change either, so the build is not checked")
                return
            before = built.log if built.built else None
        problems = compile_problems(before, after.log, built=after.built)
        if problems:
            verdict.refusals += problems
        else:
            verdict.passed.append(f"the build ({'as clean as before' if before else 'clean'}, {after.seconds:g} s)")
            verdict.root, verdict.engine = root, engine

    def _bibliography(self, folder: Path, root: str, texts: dict[str, str]) -> tuple[set[str], bool, str]:
        """The keys of the bibliographies the document loads, whether it loads one, and where they are (said)."""
        here = PurePosixPath(root).parent
        named = bibliographies(texts.get(root, ""))
        keys: set[str] = set()
        found = []
        for name in named:
            path = folder.joinpath(*(here / name).parts)
            text = _read(path)
            if text is not None:
                keys |= set(bib_entries(text))
                found.append((here / name).as_posix())
        return keys, bool(found), ", ".join(found) or "the bibliography"

    def _texts(self, folder: Path, relative: str, after: str) -> dict[str, str]:
        """The folder's `.tex` files, from the folder, with the changed file as it would be."""
        texts: dict[str, str] = {}
        for top, folders, files in os.walk(folder):
            folders[:] = sorted(each for each in folders if each not in SKIPPED)
            for name in sorted(files):
                if name.endswith(".tex") and len(texts) < MOST_TEX:
                    path = Path(top, name)
                    text = _read(path)
                    if text is not None:
                        texts[path.relative_to(folder).as_posix()] = text
        texts[relative] = after
        return texts

    def build_file(self, file: str) -> dict[str, Any]:
        """Build the document a `.tex` file of a workspace belongs to, in its container, its PDF, log and SyncTeX file
        kept beside its root's `.tex` (LaTeX Workshop's build, design 0020 §3): whether it built, the PDF on this
        machine, its errors and its warnings."""
        path = Path(file)
        if path.suffix.lower() != ".tex":
            raise BuildError(f"{file} is not a .tex file")
        workspace, folder = self._workspace_of(path)
        relative = path.resolve().relative_to(folder.resolve()).as_posix()
        texts = self._texts(folder, relative, _read(path) or "")
        root = root_of(relative, texts) or relative
        built = self.builder.output(workspace, root, engine_of(texts.get(root, "")), folder.as_posix())
        if built.unbuilt:
            raise BuildError(built.unbuilt)
        warnings = [f"undefined reference {each}" for each in sorted(built.log.references)]
        warnings += [f"undefined citation {each}" for each in sorted(built.log.citations)]
        warnings += [f"label defined twice {each}" for each in sorted(built.log.labels)]
        pdf = str(folder.joinpath(*built.pdf.split("/"))) if built.pdf else ""
        return {"workspace": workspace, "root": root, "built": built.built, "pdf": pdf, "seconds": built.seconds,
                "errors": built.log.errors, "warnings": warnings}  # fmt: skip

    def _workspace_of(self, path: Path) -> tuple[str, Path]:
        """The workspace whose folder holds a file, and its folder."""
        for record in self.kernel.parts["workspaces"].records():
            folder = Path(record["path"])
            try:
                path.resolve().relative_to(folder.resolve())
            except ValueError:
                continue
            return str(record["name"]), folder
        raise BuildError(f"{path} is in no Clank workspace: run `clank` in its folder first")

    def marked(self, change: dict[str, Any]) -> None:
        """Build the PDF of a change asked about (§9) and say where it is (`agents.latex_diff`); nothing when its
        document was not built by the checks, or when the PDF cannot be made."""
        checks = change.get("checks") or {}
        if not checks.get("root") or change.get("after") is None:
            return
        keep = f".clank/latex/{change['id']}"
        pdf, marked = self.builder.marked(
            str(change["workspace"]), checks["root"], str(change["relative"]), change.get("before"),
            str(change["after"]), checks.get("engine") or "pdf", keep,
        )  # fmt: skip
        if not pdf:
            return
        self.kernel.events.record(
            "agents.latex_diff",
            summary=f"the PDF of the change to {change['relative']} in {change['workspace']}: {pdf}",
            actor=ACTOR,
            subject=Subject(kind="change", id=str(change["id"])),
            data={"workspace": change["workspace"], "folder": change["folder"], "change": change["id"],
                  "file": change["relative"], "pdf": pdf, "marked": marked == "marked"},
        )  # fmt: skip

    def run(self, workspace: str, argv: list[str], given: bytes, timeout: float) -> Any:
        """Run a command in the workspace's container (the TeX layer's helper)."""
        return self.kernel.parts["workspaces"].run_in(workspace, argv, input=given, timeout=timeout)


def _read(path: Path) -> str | None:
    try:
        if path.stat().st_size > LARGEST:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
