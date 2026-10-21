"""Handoff notes (design 0013 §5, decision 0086): what a box hands on to the boxes after it, a few lines of its own.

Each box a model runs starts afresh, with none of the history of the boxes before it. So PLAN, TASK and INTEGRATE end by
writing a short note in the folder, `.clank/handoff/<flow>/<box>.md` (`path`; `<flow>` the flow's name in its
workspace): what it did, the decisions it made and why, and what is still open. `.clank/` is where Clank and the agent
already exchange files, kept out of git; `.clank/handoff/` gets a `.gitignore` of its own (`keep_out_of_git`). A
VERIFY's verdict and a DECOMPOSE's summary (`flow_submit`) stand for theirs: they write no note (`writes_note`). The
note is not the box's deliverable: nothing checks it, and a box whose deliverable is right is done without it.

`notes_before` reads what the boxes before a box handed on, in the order they ran, each from its latest try in the run:
a note from the copy kept beside its try (`handoff.md`, so a later run's note in the folder never changes it), a
VERIFY's verdict, a DECOMPOSE's summary; that a box left none, or has not run yet (a preview). A box skipped is left
out, and a VERIFY is handed none: it is handed only the brief and the deliverable it checks, never the sessions that
made them (design 0013 §2). `first.py` quotes each, cut at the flow's `note_up_to`.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from clank.components.flows.kinds import Box, Flow
from clank.components.flows.proposals import Batches
from clank.components.flows.runs import Run, Runs, Try, order

if TYPE_CHECKING:
    from clank.components.flows.verdicts import Verdict

log = logging.getLogger(__name__)
FOLDER = ".clank/handoff"
IGNORE = "# Clank's own: the handoff notes of flows' boxes, a copy of each kept beside its try (design 0013 §5)\n*\n"
WRITERS = ("plan", "task", "integrate")  # the types that write a note; a VERIFY's verdict and a DECOMPOSE's summary
HANDING = (*WRITERS, "verify", "decompose")  # the types whose boxes hand something on: every box a model runs
NOT_RUN = "It has not run yet in this run: its note comes once it has."


@dataclass(frozen=True)
class Note:
    """What a box before this one handed on: its words (`text`), or what is said instead (`said`); where it came from
    (`where`: its note's file, its verdict, its summary), the try it is from, and the folder's file that holds it whole,
    named when its words are cut."""

    box: str
    type: str
    attempt: int | None
    where: str
    text: str = ""
    said: str = ""
    whole: str = ""


def path(flow: str, box: str) -> str:
    """Where a box writes its note, from the folder: `.clank/handoff/<flow>/<box>.md`; `flow` the flow's name in its
    workspace, or its id `<workspace>/<name>`."""
    return f"{FOLDER}/{_name(flow)}/{box}.md"


def _name(flow: str) -> str:
    return flow.split("/", 1)[-1] or "flow"


def writes_note(box: Box) -> bool:
    """Whether a box ends by writing a note: PLAN, TASK and INTEGRATE do."""
    return box.type in WRITERS


def keep_out_of_git(folder: Path, flow: str) -> None:
    """Make the folder's `.clank/handoff/<flow>/` ready for a note, `.clank/handoff/` kept out of git by a `.gitignore`
    of its own when it has none (one there is left as it is); a folder that cannot be written is said in the log, and
    the box goes on (its model writes the note, or says why it cannot)."""
    kept = folder.joinpath(*FOLDER.split("/"))
    try:
        kept.joinpath(_name(flow)).mkdir(parents=True, exist_ok=True)
        ignore = kept / ".gitignore"
        if not ignore.exists():
            ignore.write_bytes(IGNORE.encode("utf-8"))
    except OSError as error:
        log.warning("the handoff notes' folder %s cannot be made ready: %s", kept, error)


def notes_before(runs: Runs, run: Run | None, flow: str, made: Flow, box: Box) -> list[Note]:
    """What the boxes before `box` handed on, in the order they ran (none for a VERIFY); `run` the run it is sent in
    (none: a preview with no run), `flow` the flow's id."""
    names = order(made)
    if box.type == "verify" or box.id not in names:
        return []
    by_id = {each.id: each for each in made.boxes}
    found = []
    for name in names[: names.index(box.id)]:
        before = by_id[name]
        if before.type not in HANDING:
            continue
        state = run.boxes.get(name) if run is not None else None
        if state is not None and state.state == "skipped":
            continue
        if run is None or state is None or not state.tries:
            found.append(Note(box=name, type=before.type, attempt=None, where="not run yet", said=NOT_RUN))
            continue
        found.append(_handed_on(runs, run, flow, before, state.tries[-1]))
    return found


def _handed_on(runs: Runs, run: Run, flow: str, box: Box, last: Try) -> Note:
    """What one box handed on from its latest try."""
    if box.type == "verify":
        if last.verdict is None:
            return Note(box=box.id, type=box.type, attempt=last.number, where="no verdict", said="It gave no verdict.")
        text = verdict_words(last.verdict, box.checks)
        return Note(box=box.id, type=box.type, attempt=last.number, where="its verdict", text=text)
    if box.type == "decompose":
        batch = Batches(runs).load(run, box.id, last.number)
        summary = batch.summary.strip() if batch is not None else ""
        if not summary:
            return Note(box=box.id, type=box.type, attempt=last.number, where="no summary", said="It gave no summary.")
        where = "its summary when it submitted its tasks"
        return Note(box=box.id, type=box.type, attempt=last.number, where=where, text=summary)
    note = path(flow, box.id)
    kept = _copy(runs, run, box, last)
    if kept is None:
        return Note(box=box.id, type=box.type, attempt=last.number, where="no note", said="It left no handoff note.")
    return Note(box=box.id, type=box.type, attempt=last.number, where=f"its note, `{note}`", text=kept, whole=note)


def _copy(runs: Runs, run: Run, box: Box, last: Try) -> str | None:
    """A try's note, from the copy beside it; None when it left none, or none was kept."""
    if last.handoff is None or not last.handoff.copied:
        return None
    try:
        raw = (runs.try_folder(run, box.id, last.number) / "handoff.md").read_bytes()
    except OSError:
        return None
    return raw.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").strip() or None


def verdict_words(verdict: "Verdict", checks: str) -> str:
    """A verdict handed on: its result, on which try, and its findings (a pass's remarks)."""
    on = f"{checks}'s try {verdict.checked}" if verdict.checked else checks
    lines = [f"Its verdict on {on}: {verdict.result}."]
    if verdict.findings:
        lines.append("Findings:" if verdict.result == "fail" else "Remarks:")
        lines += [f"{number}. {finding}" for number, finding in enumerate(verdict.findings, start=1)]
    return "\n".join(lines)
