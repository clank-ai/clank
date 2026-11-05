"""The corpus (design 0013 §17, decision 0132): the flow's folder of side notes, `corpus/` in the workspace's folder
(`orchestrator.side.corpus`), each `<run>-<n>-<slug>.md` written by one side task, its first line a one-line summary.

Clank keeps the index, `CORPUS.md` beside the notes, never the model: each note's path and its first line, rewritten
whole after each side task, so a box or a checkpoint handed it reads only the notes it needs. A note is found by its
name; anything else in the folder is left alone. The notes are the agent's, so they are read, and the index written,
through no link (`kernel/infolder.py`, decision 0164).
"""

import contextlib
import logging
import re
from pathlib import Path

from clank.kernel.infolder import Outside, Place, place

log = logging.getLogger(__name__)

INDEX = "CORPUS.md"
NOTE = re.compile(r"^([1-9][0-9]*)-([1-9][0-9]*)-[a-z0-9-]+\.md$")
SLUG_LENGTH = 40
SUMMARY_LENGTH = 200


def slug(title: str) -> str:
    """A title as a note's name: lower case, words joined by hyphens."""
    words = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return words[:SLUG_LENGTH].rstrip("-") or "note"


def note_path(corpus: str, run: int, number: int, title: str) -> str:
    """A side task's note in the workspace's folder, `/`-separated."""
    return f"{corpus}/{run}-{number}-{slug(title)}.md"


def summary(note: Place) -> str:
    """A note's first line that says anything, without a heading's marks."""
    try:
        lines = note.read_text(errors="replace", most=1 << 16).splitlines()
    except (OSError, ValueError):  # Outside too, a ValueError
        return ""
    first = next((line.strip().lstrip("#").strip() for line in lines if line.strip().lstrip("#").strip()), "")
    return first[:SUMMARY_LENGTH]


def entries(folder: Path, corpus: str) -> list[tuple[str, str]]:
    """Each note of the corpus, by run and number: its path in the workspace's folder and its summary."""
    found: list[tuple[int, int, str, str]] = []
    with contextlib.suppress(Outside):
        where = place(folder, corpus)
        for name, kind in where.entries():  # links left out
            matched = NOTE.match(name)
            if matched and kind == "file":
                found.append((int(matched[1]), int(matched[2]), f"{corpus}/{name}", summary(where / name)))
    return [(path, said) for _, _, path, said in sorted(found)]


def index_text(found: list[tuple[str, str]]) -> str:
    """The index's lines: `- <path>: <summary>`."""
    return "\n".join(f"- {path}: {said}" for path, said in found)


def write_index(folder: Path, corpus: str) -> str:
    """Write `CORPUS.md` from the notes as they are; its lines."""
    lines = index_text(entries(folder, corpus))
    head = "# Corpus\n\nThe flow's side notes, kept by Clank: each note's path and its first line.\n\n"
    try:
        place(folder, f"{corpus}/{INDEX}").write_text(head + (lines or "No note yet.") + "\n")
    except Outside as error:
        log.warning("the corpus's index is not written: %s", error)
    return lines
