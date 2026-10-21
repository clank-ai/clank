"""What a flow waits for, told the same way to every client (design 0013 §10, §14 step 7).

A run waits for one question at a time (a YOU box, a gate, a failed box, a box whose *when done* waits, a batch of
proposals; `runs.Waiting`).
Its view names the flow, the run and the box; the files it shows, each with its place in the folder, the box that wrote
it and the tries of that box in the run that kept a copy of it, so a client can open the file as it stands (what an
approval takes, §8) and diff the last two tries; and the answers that take words, with what the words are for (the
runner reads them: *send back*'s note, *try again*'s words; plan s24, calls 9 and 10). VS Code draws it as a gate with
Open and Diff, the phone under its flow: neither knows the runner's rules. A question answered anywhere is no longer
listed, before the runner even moves on.

The files a question shows: a gate's (its `shows`, else the deliverable of the box before it that writes one, as its
question says); a YOU box's own files to write; a failed VERIFY's, the deliverables of the box it checks (at its loop's
gate, board D3: the plan's last two tries to diff, *one more try*'s words for that box); another failed box's, and a
box's whose *when done* waits, its own deliverables; a batch of proposals, none (its question's detail tells them,
and none of their files is written yet). The box that wrote a file a gate shows is the latest before the gate that
writes it.
"""

from pathlib import Path
from typing import Any

from clank.components.flows.kinds import Box, Flow
from clank.components.flows.runner import _before_writes, _box_of, _found_wrong, _sent_back_to
from clank.components.flows.runs import Run, order


def shown(run: Run, flow: Flow, folder: Path) -> dict[str, Any] | None:
    """The view of the question `run` waits for; None when it waits for none, or for a box its flow no longer has."""
    waiting = run.waiting
    box = _box_of(flow, waiting.box) if waiting is not None else None
    if waiting is None or box is None:
        return None
    workspace, name = run.flow.split("/", 1)
    checked = _box_of(flow, box.checks) if waiting.kind == "failed" and box.type == "verify" else None
    if waiting.kind == "gate":
        files = [(path, _writer(flow, box, path)) for path in box.shows or _before_writes(flow, box)]
    elif waiting.kind == "proposals":
        files = []  # its proposals are told in its question's detail: none of their files is written yet
    elif checked is not None:
        files = [(path, checked.id) for path in checked.writes]
    else:
        files = [(path, box.id) for path in box.writes]
    return {
        "question": waiting.question,
        "flow": run.flow,
        "workspace": workspace,
        "name": name,
        "title": run.title or name,
        "run": run.number,
        "box": box.id,
        "box_title": box.title,
        "type": box.type,
        "kind": waiting.kind,
        "folder": str(folder),
        "files": [_file(run, folder, path, writer) for path, writer in files],
        "notes": _notes(flow, box, waiting.kind, run),
    }


def _writer(flow: Flow, gate: Box, path: str) -> str:
    """The box that wrote a file a gate shows: the latest before the gate that writes it; empty for none."""
    before: list[Box] = []
    for id in order(flow):
        if id == gate.id:
            break
        found = _box_of(flow, id)
        if found is not None:
            before.append(found)
    return next((each.id for each in reversed(before) if path in each.writes), "")


def _file(run: Run, folder: Path, path: str, writer: str) -> dict[str, Any]:
    """A file a question shows: its place in the folder, the box that wrote it, and its tries that kept a copy."""
    place = folder.joinpath(*path.split("/"))
    tries = run.boxes[writer].tries if writer in run.boxes else []
    copied = [each.number for each in tries if any(kept.path == path and kept.copied for kept in each.deliverables)]
    return {"path": path, "file": str(place), "box": writer, "tries": copied, "exists": place.is_file()}


def _notes(flow: Flow, box: Box, kind: str, run: Run) -> dict[str, str]:
    """The answers whose words the runner reads, with what the words are for."""
    if kind == "gate":
        target = _sent_back_to(flow, box) or "the box before it"
        return {"back": f"Your note for {target}'s next try: what to change (optional)."}
    if kind == "failed":
        looped = box.type == "verify" and box.checks and _found_wrong(run.box(box.id))
        return {"retry": f"Words for {box.checks if looped else box.id}'s next try (optional)."}
    return {}
