"""A box's first message (design 0013 §5; decisions 0060, 0085, 0086): everything its fresh session is handed.

In order: its type's instructions (`prompts/<type>.md`, what it must produce and how it ends); where it sits in the
flow, a map naming the boxes before it with what each delivered as the run says, the box itself with its try, and the
boxes after it with how each uses its deliverable (no prompt, file or session of another box); the flow's brief, the
files its first box (a YOU) writes, handed to every box a model runs whether or not its `sees` lists it, and once; the
box's own prompt; the notes the boxes before it handed on (`handoff.notes_before`), each quoted and cut at the flow's
`note_up_to` characters, none for a VERIFY; the files it sees but the brief's, each with the box it came from (the
latest box before it that writes the file, else the folder): a text file whole up to the flow's `whole_up_to` bytes, a
larger or binary one by its path and size, to read with its tools; what the boxes before it delivered, each by its
path, the box that wrote it and its size (an INTEGRATE: every deliverable before it; a DECOMPOSE's task: those of the
tasks before it that it is not handed whole); its deliverable, what it holds and what it is accepted when (a VERIFY:
what the box it checks is accepted when), and for a PLAN, a TASK or an INTEGRATE the handoff note it writes last
(`handoff.py`, decision 0086); and, on a later try, what happened to the last one (the limit it reached, the
deliverable it left out, the owner's note). The runner keeps the message as a file beside the try
(`first-message.md`), so the owner reads exactly what the model was told.
"""

import re
from collections.abc import Sequence
from importlib import resources
from pathlib import Path

from clank.components.flows import corpus, handoff
from clank.components.flows.handoff import Note, writes_note
from clank.components.flows.kinds import Box, Flow
from clank.components.flows.runs import Run, order

BACKTICKS = re.compile(r"`{3,}")


def instructions(type: str) -> str:
    """Clank's instructions for a type of box a model runs (`prompts/<type>.md`)."""
    return resources.files("clank.components.flows").joinpath("prompts", f"{type}.md").read_text(encoding="utf-8")


def first_message(
    flow: Flow,
    box: Box,
    folder: Path,
    *,
    number: int,
    last: str = "",
    name: str = "",
    run: Run | None = None,
    notes: Sequence[Note] = (),
) -> str:
    """The first message of a box's try `number`, its files read from `folder` now; `last` what happened to the last
    try, for a later one; `name` the flow's name in its workspace; `run` the run it is sent in, whose states the map
    says (none: a preview with no run); `notes` what the boxes before it handed on (`handoff.notes_before`)."""
    sections = [
        instructions(box.type).rstrip(),
        _map(flow, box, number, run),
        _brief(flow, box, folder),
        _task(box),
        _notes(flow, box, notes),
        _corpus(flow, folder),
        _handed(flow, box, folder),
        _delivered(flow, box, folder),
        _deliverable(flow, box, name, folder),
    ]
    if number > 1 and last.strip():
        sections.append(f"## Your last try\n\nThis is try {number}. {last.strip()}")
    elif last.strip():  # a first try told something: the orchestrator's note (design 0013 §16)
        sections.append(f"## Before you start\n\n{last.strip()}")
    return "\n\n".join(section for section in sections if section) + "\n"


def brief(flow: Flow) -> list[str]:
    """The flow's brief: the files its first box writes (a flow starts with a YOU, design 0013 §3)."""
    first = flow.boxes[0]
    return list(first.writes) if first.type == "you" else []


def came_from(flow: Flow, box: Box, path: str) -> str:
    """The box a file a box sees came from: the latest before it that writes the file; "" for the folder's own."""
    found = ""
    by_id = {each.id: each for each in flow.boxes}
    for name in order(flow):
        if name == box.id:
            break
        if path in by_id[name].writes:
            found = name
    return found


def _map(flow: Flow, box: Box, number: int, run: Run | None) -> str:
    """Where the box sits in the flow (decision 0085): the boxes before it, each with what it delivered as the run says
    (with no run: what it delivers); the box, marked, with its try; the boxes after it, each with how it uses this
    box's deliverable. It names; it carries no prompt, file or session of another box."""
    names = order(flow)
    if box.id not in names:
        return ""
    by_id = {each.id: each for each in flow.boxes}
    place = names.index(box.id)
    called = f'the flow "{flow.title}"' if flow.title else "this flow"
    head = (
        f"You are box {place + 1} of {len(names)} in {called}" + (f", run {run.number}" if run is not None else "")
        + ". Its boxes run one after another, each a session of its own: you have none of their history, only what "
        "this message hands you and the folder."
    )  # fmt: skip
    parts = [head]
    if place:
        before = [
            f"{index}. {_named(by_id[name])}: {_did(flow, by_id[name], run)}."
            for index, name in enumerate(names[:place], start=1)
        ]
        parts.append("\n".join(["Before you:", *before]))
    parts.append(f"You: {place + 1}. {_named(box)}, try {number}.")
    if place + 1 < len(names):
        after = []
        for index, name in enumerate(names[place + 1 :], start=place + 2):
            uses = _uses(flow, box, by_id[name])
            after.append(f"{index}. {_named(by_id[name])}" + (f": {uses}." if uses else "."))
        parts.append("\n".join(["After you:", *after]))
    return "\n\n".join(["## Where you are in the flow", *parts])


def _named(box: Box) -> str:
    return f'{box.id} ({box.type.upper()}) "{box.title}"'


def _did(flow: Flow, box: Box, run: Run | None) -> str:
    """What a box before this one delivered, as the run says; with no run, or before it settled, what it delivers."""
    state = run.boxes.get(box.id) if run is not None else None
    if state is not None and state.state == "skipped":
        return "skipped by the user"
    files = ", ".join(box.writes)
    tasks = [each.id for each in flow.boxes if each.type == "task" and fanned_from(flow, each) == box.id]
    if state is None or state.state not in ("done", "stale"):
        return {
            "you": f"the user writes {files}" if files else "the user's part",
            "gate": "the user decides",
            "verify": f"checks {box.checks}'s deliverable",
            "decompose": f"breaks the work into {listed(tasks)}" if tasks else "breaks the work into tasks",
        }.get(box.type, f"delivers {files}" if files else "does its task")
    verdict = next((each.verdict for each in reversed(state.tries) if each.verdict is not None), None)
    checked = f"its verdict on {box.checks}, {verdict.result}" if verdict else f"checked {box.checks}'s deliverable"
    said = {
        "you": f"the user wrote {files}" if files else "the user's part, done",
        "gate": "the user approved",
        "verify": checked,
        "decompose": f"broke the work into {listed(tasks)}" if tasks else "proposed no task",
    }.get(box.type, f"delivered {files}" if files else "done")
    last = state.tries[-1] if state.tries else None
    if last is not None and last.outcome in ("failed", "stopped"):
        said += f", taken as it was after its try {last.number} {last.outcome}"
    if state.state == "stale":
        said += f", now stale ({state.why})" if state.why else ", now stale"
    return said


def _uses(flow: Flow, box: Box, later: Box) -> str:
    """How a box after this one uses its deliverable, in words; "" when it does not."""
    if later.type == "verify" and later.checks == box.id:
        return "checks your deliverable, and a fail sends you back with its findings"
    found = []
    if seen := [path for path in later.sees if path in box.writes]:
        found.append(f"sees your {', '.join(seen)}")
    if shown := [path for path in later.shows if path in box.writes]:
        found.append(f"shows your {', '.join(shown)} to the user")
    if later.type == "integrate" and box.writes:
        found.append("is told of every deliverable, yours included")
    fan = fanned_from(flow, box) if box.type == later.type == "task" else ""
    told = [path for path in box.writes if path not in later.sees]
    if fan and fanned_from(flow, later) == fan and told:
        found.append(f"is told of your {', '.join(told)}")
    return "; ".join(found)


def _brief(flow: Flow, box: Box, folder: Path) -> str:
    """The brief, handed to every box a model runs (decision 0085): the goal and the limits of the whole flow."""
    paths = brief(flow)
    if not paths or box.id == flow.boxes[0].id:
        return ""
    whole, named = _files(flow, box, folder, paths)
    lead = "The goal and the limits of the whole flow, as the user wrote them: keep every limit."
    return "\n\n".join(["## The brief", lead, *whole, *(["\n".join(named)] if named else [])])


def _corpus(flow: Flow, folder: Path) -> str:
    """The corpus's notes, each by its path and first line (design 0013 §17): side work done while jobs ran, read by
    the box as it needs; nothing when there is none."""
    found = corpus.index_text(corpus.entries(folder, flow.orchestrator.side.corpus))
    if not found:
        return ""
    return (
        "## The corpus\n\nSide notes written for this flow while its jobs ran, each by its path and first line. Read "
        "those your task needs; they are notes, not results: check what you rely on.\n\n" + found
    )


def _notes(flow: Flow, box: Box, notes: Sequence[Note]) -> str:
    """What the boxes before it handed on (decision 0086), in the order they ran, each quoted under a heading naming
    its box, its try and where it came from, cut at the flow's `note_up_to` characters; none for a VERIFY."""
    if box.type == "verify" or not notes:
        return ""
    limit = flow.defaults.note_up_to
    parts = ["## Notes from the boxes before you", "What each box before you handed on, in the order they ran, in its "
             "own words:"]  # fmt: skip
    for note in notes:
        tried = f", try {note.attempt}" if note.attempt is not None else ""
        parts.append(f"### {note.box} ({note.type.upper()}){tried}: {note.where}")
        if not note.text:
            parts.append(note.said)
            continue
        words = note.text.strip()
        if len(words) > limit:
            whole = f": the whole note is `{note.whole}`" if note.whole else ""
            words = f"{words[:limit].rstrip()}\n… (cut at {limit:,} characters{whole})"
        parts.append("\n".join(f"> {line}".rstrip() for line in words.splitlines()))
    return "\n\n".join(parts)


def _task(box: Box) -> str:
    words = box.prompt.strip() or "(It has no words of its own: its title says what to do.)"
    return f"## Your task: {box.title}\n\n{words}"


def _delivered(flow: Flow, box: Box, folder: Path) -> str:
    """What the boxes before it delivered, named with the box that wrote each last and its size: for an INTEGRATE,
    every deliverable before it (§2: "a summary of every deliverable"), the tasks accepted from proposals included; for
    a DECOMPOSE's task, those of the tasks before it that it is not handed whole already (§3, §9: "each handed the
    deliverables of those before it")."""
    names = order(flow)
    before = names[: names.index(box.id)] if box.id in names else []
    by_id = {each.id: each for each in flow.boxes}
    if box.type == "integrate":
        boxes = before
        heading = "## Every deliverable before you"
        lead = "The files the boxes before you delivered, in the order they ran; read each with your tools:"
    elif box.type == "task" and (decompose := fanned_from(flow, box)):
        boxes = [name for name in before if by_id[name].type == "task" and fanned_from(flow, by_id[name]) == decompose]
        if not boxes:
            return ""
        heading = "## What the tasks before you delivered"
        lead = (
            f"You run after {listed(boxes)}, broken out of the same work by {decompose}; their files are in the "
            "folder, to read with your tools:"
        )
    else:
        return ""
    writers: dict[str, str] = {}
    for name in boxes:
        for path in by_id[name].writes:
            writers[path] = name  # the latest writer, at the place of the first
    shown = [path for path in writers if box.type == "integrate" or path not in box.sees]
    if not shown:
        return ""
    lines = []
    for path in shown:
        file = folder.joinpath(*path.split("/"))
        said = f"{file.stat().st_size:,} bytes" if file.is_file() else "not in the folder"
        lines.append(f"- `{path}` (from {writers[path]}): {said}")
    return "\n\n".join([heading, lead + "\n" + "\n".join(lines)])


def fanned_from(flow: Flow, box: Box) -> str:
    """The DECOMPOSE a TASK was broken out of: the one its only line comes from; "" for none."""
    into = [line.from_ for line in flow.lines if line.to == box.id and line.when != "fail"]
    source = next((each for each in flow.boxes if into and each.id == into[0]), None)
    return into[0] if len(into) == 1 and source is not None and source.type == "decompose" else ""


def listed(names: list[str]) -> str:
    """Names in words: "T1", "T1 and T2", "T1, T2 and T3"."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _handed(flow: Flow, box: Box, folder: Path) -> str:
    paths = [path for path in box.sees if path not in brief(flow)]  # the brief has its own heading
    if not paths:
        return ""
    whole, named = _files(flow, box, folder, paths)
    parts = ["## The files you are handed", *whole]
    if named:
        parts.append("\n".join(named))
    return "\n\n".join(parts)


def _files(flow: Flow, box: Box, folder: Path, paths: list[str]) -> tuple[list[str], list[str]]:
    """Files handed to a box: each whole (a heading and its text), or named on a line (by its path and size)."""
    whole, named = [], []
    for path in paths:
        source = came_from(flow, box, path)
        where = f"from {source}" if source else "from the folder"
        file = folder.joinpath(*path.split("/"))
        if not file.is_file():
            named.append(f"- `{path}` ({where}): not in the folder yet")
            continue
        size = file.stat().st_size
        if size > flow.defaults.whole_up_to:
            named.append(
                f"- `{path}` ({where}): {size:,} bytes, more than {flow.defaults.whole_up_to:,} handed whole: read it "
                "with your tools if you need it"
            )
            continue
        text = _text(file)
        if text is None:
            named.append(f"- `{path}` ({where}): {size:,} bytes, not text: read it with your tools if you need it")
            continue
        whole.append(f"### {path} ({where})\n\n{fenced(text)}")
    return whole, named


def fenced(text: str) -> str:
    """Text between fences longer than any run of backticks it holds."""
    fence = "`" * max([3, *(len(run) + 1 for run in BACKTICKS.findall(text))])
    return f"{fence}\n{text.rstrip(chr(10))}\n{fence}"


def _deliverable(flow: Flow, box: Box, name: str, folder: Path) -> str:
    parts = ["## Your deliverable"]
    if box.writes:
        parts.append("Write these files in the folder:\n" + "\n".join(f"- {path}" for path in box.writes))
    if there := [path for path in box.writes if folder.joinpath(*path.split("/")).is_file()]:
        one = len(there) == 1
        it, them, each = ("it", "it", "it") if one else ("they", "them", "each")
        parts.append(
            f"{listed(there)} {'is' if one else 'are'} in the folder already, from before: read {them} if it helps, "
            f"but write {each} again during this session, even where you keep what {it} says. A file left as it was "
            "fails your box."
        )
    if box.holds.strip():
        parts.append(f"They hold: {box.holds.strip()}")
    accepted = list(box.accept_when)
    if box.type == "verify" and box.checks:
        checked = next((each for each in flow.boxes if each.id == box.checks), None)
        if checked is not None:
            files = ", ".join(checked.writes) or "its deliverable"
            parts.append(f"You check {box.checks}'s deliverable: {files}.")
            accepted = list(checked.accept_when) + accepted
    if accepted:
        parts.append("It is accepted when:\n" + "\n".join(f"- {each}" for each in accepted))
    if writes_note(box):
        parts.append(
            f"Last, write your handoff note in `{handoff.path(name, box.id)}`: a few lines (at most 15) for the boxes "
            "after you, which start afresh with none of your history: what you did, the decisions you made and why, "
            "and what is still open. It is not part of your deliverable and nothing checks it; each box after you is "
            "handed it."
        )
    if box.writes:
        then = ", then your note," if writes_note(box) else ""
        parts.append(f"You are done when each of these files{then} was written during this session; then stop.")
    elif box.type == "verify":
        parts.append("You write no file: you end by calling `flow_verdict`.")
    elif box.type == "decompose":
        parts.append(
            f"You write no file: propose each task with `flow_propose_box`, `after` set to `{box.id}`, in the order "
            "they should run; then call `flow_submit` with a short summary, which the boxes after you are handed as "
            "your note (the tasks, why in this order, what is still open), and stop."
        )
    return "\n\n".join(parts)


def _text(file: Path) -> str | None:
    """A file's text, or None when it is not text (not UTF-8, or holding a NUL)."""
    try:
        raw = file.read_bytes()
        text = raw.decode("utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    return None if "\x00" in text else text.replace("\r\n", "\n")
