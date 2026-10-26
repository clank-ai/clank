"""One line per flow for a list (design 0025 §6; design 0013 §12), made in the service so every client says a flow's
state in the same words and knows no rule of the runner: the phone's Flows tab reads these, the console's lists can.

`summarize` is a pure function of the flow, its latest run (none when it never ran), its planning when it is being
built with the model (design 0013 §15) and the presets' titles. Its `state` is one word a client filters by (never,
queued, running, paused, waits, building, done, stopped) and its `words` say it the way the canvas wrote it: the box
a run is at with how many boxes are done ("Write the plan · 3 of 9"), what it waits for and where ("waits for you:
gate · You approve the plan"), why it stopped. A run's state wins over its planning's: once a built flow runs, the run
says. The run's time is its end, else its start, so a list sorts by it.
"""

from collections.abc import Mapping
from typing import Any

from clank.components.flows.building import OPEN, Planning
from clank.components.flows.kinds import Flow
from clank.components.flows.runs import Run, order
from clank.kernel.clock import to_text

WAITS = {
    "gate": "gate",
    "you": "your part",
    "failed": "a box failed",
    "done": "a box is done",
    "proposals": "proposals",
}
BUILDING = {
    "waiting": "waits for its OpenCode window",
    "opening": "its session starts",
    "talking": "talking it through",
    "built": "written, look, then run",
}
RANK = {"waits": 0, "running": 1, "paused": 1, "queued": 1, "building": 1, "done": 2, "stopped": 2, "never": 3}


def summarize(
    id: str, flow: Flow, run: Run | None, planning: Planning | None, titles: Mapping[str, str]
) -> dict[str, Any]:
    """The flow's line: its names, its state and words, the box it is at, how many boxes are done of all, the preset
    its running box uses (else its default's), its run's time, the question it waits for, and its file's problems
    count left to the caller (zero here)."""
    workspace, name = id.split("/", 1) if "/" in id else ("", id)
    box_titles = {box.id: box.title for box in flow.boxes}
    ordered = order(flow)
    at = run.at if run is not None else ""
    done = sum(1 for box in (run.boxes.values() if run is not None else []) if box.state == "done")
    state, words = _state(flow, run, planning, box_titles)
    model = next((box.model for box in flow.boxes if box.id == at and box.model), "") or flow.defaults.model
    return {
        "id": id,
        "workspace": workspace,
        "name": name,
        "title": flow.title or name,
        "state": state,
        "words": words,
        "box": at,
        "box_title": box_titles.get(at, at),
        "position": {"done": done, "of": len(ordered)},
        "model": titles.get(model, model),
        "time": to_text(run.ended or run.created) if run is not None else None,
        "question": run.waiting.question if run is not None and run.waiting is not None else "",
        "problems": 0,
    }


def _state(flow: Flow, run: Run | None, planning: Planning | None, titles: Mapping[str, str]) -> tuple[str, str]:
    if run is None:
        if planning is not None and planning.status in OPEN:
            return "building", f"building: {BUILDING[planning.status]}"
        return "never", "not run yet"
    at_title = titles.get(run.at, run.at)
    if run.status == "queued":
        return "queued", f"queued behind {run.behind.split('/', 1)[-1]}" if run.behind else "queued"
    if run.status == "done":
        gates = {box.id for box in flow.boxes if box.type == "gate"}
        approved = any(name in gates and box.state == "done" for name, box in run.boxes.items())
        return "done", "done · approved by you" if approved else "done"
    if run.status == "stopped":
        reasons = [
            made.reason for box in run.boxes.values() for made in box.tries if made.outcome == "stopped" and made.reason
        ]
        return "stopped", f"stopped: {reasons[-1]}" if reasons else "stopped"
    if run.waiting is not None:
        what = WAITS.get(run.waiting.kind, run.waiting.kind)
        return "waits", f"waits for you: {what} · {titles.get(run.waiting.box, run.waiting.box)}"
    running = [name for name, box in run.boxes.items() if box.state == "running"]
    if run.paused:
        return "paused", f"paused · {titles.get(running[-1], running[-1])} runs on" if running else "paused"
    done = sum(1 for box in run.boxes.values() if box.state == "done")
    return "running", f"{at_title} · {done} of {len(order(flow))}"


def sort_key(line: Mapping[str, Any]) -> tuple[int, int, str]:
    """What waits for you first, then what runs or is built, then what ended, each newest first and those without a
    time after those with one; never run last."""
    time = line["time"]
    return RANK.get(line["state"], 3), 1 if time is None else 0, "" if time is None else _descending(time)


def _descending(time: str) -> str:
    """A key that sorts a later time first: each character of the time, as a string, inverted."""
    return "".join(chr(0x10FFFF - ord(char)) for char in time)


def planned(planning: Planning) -> dict[str, Any]:
    """The line of a planning whose flow is not written yet (design 0013 §15): building, at its planning's state, with
    the planning's name as its title, since it began; the question that told the owner, once a draft was written."""
    workspace, name = planning.flow.split("/", 1) if "/" in planning.flow else ("", planning.flow)
    return {
        "id": planning.flow,
        "workspace": workspace,
        "name": name,
        "title": planning.name or name,
        "state": "building",
        "words": f"building: {BUILDING.get(planning.status, planning.status)}",
        "box": "",
        "box_title": "",
        "position": {"done": 0, "of": 0},
        "model": "",
        "time": to_text(planning.started),
        "question": planning.question,
        "problems": 0,
    }
