"""A box's deliverables as Clank sees them (design 0013 §8): their fingerprints, and a plan's progress kept apart.

A deliverable is files in the workspace's folder. Each is fingerprinted (`fingerprint`: its content's SHA-256, its
size, when it was last written), so the runner can tell that a file was **written during its try** (`written`: it
exists now and its fingerprint differs from the one it had when the try started; a file left by an earlier try or by
another box does not count), and that a finished box's deliverable **no longer matches** what it delivered (the owner
edited it, or a later box rewrote it), which makes the boxes after it stale.

A plan (a Markdown file whose header says `kind: plan`) is also fingerprinted in two halves (`split`): its
**progress**, each step's tick in its checklist, its Log's lines and its header's `status`, which the run's own TASK
boxes change as they work (design 0009 §5.1); and **the rest**, every other line, the steps' own words included (a tick
read as unticked). The runner takes a TASK's own progress as no change, and any other change as one.
"""

import hashlib
import re
from pathlib import Path

from clank.components.agents.service import is_plan
from clank.components.flows.runs import Kept

CHECKLIST = re.compile(r"^(\s*[-*+]\s+\[)([ xX])(\].*)$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
STATUS = re.compile(r"^status\s*:", re.IGNORECASE)
LARGEST_PLAN = 1_000_000  # bytes of a Markdown file read to split a plan's progress from the rest


def fingerprint(folder: Path, path: str) -> Kept:
    """A file of the folder (named from it with '/') as it is now; an empty fingerprint when it does not exist."""
    file = folder.joinpath(*path.split("/"))
    try:
        stat = file.stat()
        if not file.is_file():
            return Kept(path=path)
        digest = hashlib.sha256()
        with file.open("rb") as reading:
            for chunk in iter(lambda: reading.read(1 << 20), b""):
                digest.update(chunk)
    except OSError:
        return Kept(path=path)
    rest = progress = ""
    if path.lower().endswith(".md") and stat.st_size <= LARGEST_PLAN:
        try:
            text = file.read_bytes().decode("utf-8-sig", errors="replace").replace("\r\n", "\n")
        except OSError:
            text = ""
        if is_plan(text):
            rest_text, progress_text = split(text)
            rest, progress = _digest(rest_text), _digest(progress_text)
    return Kept(
        path=path,
        sha256=digest.hexdigest(),
        size=stat.st_size,
        modified=stat.st_mtime_ns,
        rest=rest,
        progress=progress,
    )


def written(before: Kept | None, now: Kept) -> bool:
    """Whether a file was written between two fingerprints: it exists now, and did not before, or differs."""
    if not now.sha256:
        return False
    if before is None or not before.sha256:
        return True
    return (before.sha256, before.size, before.modified) != (now.sha256, now.size, now.modified)


def split(text: str) -> tuple[str, str]:
    """A plan's text in two: the rest (a tick read as unticked, no Log lines, no `status`) and its progress (the
    `status` line, each step's tick in order, the Log's lines)."""
    rest: list[str] = []
    progress: list[str] = []
    lines = text.replace("\r\n", "\n").split("\n")
    header = bool(lines) and lines[0].rstrip() == "---"
    log_level = 0
    for index, line in enumerate(lines):
        if header and index > 0 and line.rstrip() == "---":
            header = False
            rest.append(line)
            continue
        if header and index > 0:
            (progress if STATUS.match(line) else rest).append(line)
            continue
        heading = HEADING.match(line)
        if heading is not None:
            level = len(heading.group(1))
            if log_level and level <= log_level:
                log_level = 0
            if not log_level and heading.group(2).strip().lower() == "log":
                log_level = level
            rest.append(line)
            continue
        if log_level:
            if line.strip():
                progress.append(f"log: {line.rstrip()}")
            continue
        step = CHECKLIST.match(line)
        if step is not None:
            rest.append(f"{step.group(1)} {step.group(3)}")
            progress.append(f"tick: {step.group(2).lower()}")
            continue
        rest.append(line)
    return "\n".join(rest), "\n".join(progress)


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
