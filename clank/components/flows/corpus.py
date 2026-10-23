"""The corpus (design 0013 §17, decision 0132): the flow's folder of side notes, `corpus/` in the workspace's folder
(`orchestrator.side.corpus`), each `<run>-<n>-<slug>.md` written by one side task, its first line a one-line summary.

Clank keeps the index, `CORPUS.md` beside the notes, never the model: each note's path and its first line, rewritten
whole after each side task, so a box or a checkpoint handed it reads only the notes it needs. A note is found by its
name; anything else in the folder is left alone.
"""

import re
from pathlib import Path

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


def summary(note: Path) -> str:
    """A note's first line that says anything, without a heading's marks."""
    try:
        lines = note.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    first = next((line.strip().lstrip("#").strip() for line in lines if line.strip().lstrip("#").strip()), "")
    return first[:SUMMARY_LENGTH]


def entries(folder: Path, corpus: str) -> list[tuple[str, str]]:
    """Each note of the corpus, by run and number: its path in the workspace's folder and its summary."""
    found: list[tuple[int, int, str, str]] = []
    where = folder.joinpath(*corpus.split("/"))
    if not where.is_dir():
        return []
    for note in where.iterdir():
        matched = NOTE.match(note.name)
        if matched and note.is_file():
            found.append((int(matched[1]), int(matched[2]), f"{corpus}/{note.name}", summary(note)))
    return [(path, said) for _, _, path, said in sorted(found)]


def index_text(found: list[tuple[str, str]]) -> str:
    """The index's lines: `- <path>: <summary>`."""
    return "\n".join(f"- {path}: {said}" for path, said in found)


def write_index(folder: Path, corpus: str) -> str:
    """Write `CORPUS.md` from the notes as they are; its lines."""
    lines = index_text(entries(folder, corpus))
    where = folder.joinpath(*corpus.split("/"))
    where.mkdir(parents=True, exist_ok=True)
    head = "# Corpus\n\nThe flow's side notes, kept by Clank: each note's path and its first line.\n\n"
    (where / INDEX).write_bytes((head + (lines or "No note yet.") + "\n").encode("utf-8"))
    return lines
