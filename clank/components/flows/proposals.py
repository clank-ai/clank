"""The boxes a model proposes for its flow (design 0013 §9; decision 0064), and how they join the flow's file.

A box's model proposes boxes with `flow_propose_box` while it works; each proposal is checked when staged and kept in a
batch beside the proposing try, `run-<n>/<box>/try-<k>/proposals.json` (`Batch`, `Batches`), numbered in the order
proposed. A proposal holds the box as it would join the flow (`box`, the owner's edits included, the model's own
`original` kept beside it once edited), the box it comes after, its why, and its state: *proposed* (waiting for the
owner), *accepted*, *rejected*, or *replaced* (set aside when its box ran again, §9). Each takes its id in the flow when
staged (`T<n>` for a TASK), never reused in the run. `read` makes the box from the tool's arguments, each refusal naming
the argument to fix: the type, the box it comes after, a title and a prompt, a deliverable (but for a VERIFY, a
DECOMPOSE and a GATE), each file in the folder, and none that agents load as settings or instructions.

`joined` puts accepted proposals into the flow's values, a pure function: TASKs proposed after a DECOMPOSE (or after one
of its tasks) join its tasks, which fan out from it and join at the box after them, one after another in the order of
the boxes (§3); that box is found past a VERIFY that checks one of the tasks, so a task proposed then is refused by the
rules (each task leads to that box), never joined at the VERIFY. Any other box goes between the box it comes after and
the box after that, a VERIFY checking the box it follows with its fail line back to it. Proposals after one box keep
the order proposed, whatever order they are accepted in. Boxes taken out (a DECOMPOSE's tasks replaced by its new
proposals) leave their lines reconnected. Each joined box is marked with its run and the box that proposed it.
`refusals` checks the result against the flow's rules, in the rules' own words, each naming its box or its line.
"""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from clank.components.agents.service import INSTRUCTIONS, SETTINGS
from clank.components.flows.kinds import Box, BoxType, Flow, Mode
from clank.components.flows.rules import in_the_folder, on_its_own
from clank.components.flows.runs import Run, Runs, read_whole, write_whole
from clank.kernel.events import Actor

SCHEMA: Literal["flow-proposals/1"] = "flow-proposals/1"
PREFIX = {"task": "T", "plan": "P", "verify": "V", "decompose": "D", "integrate": "I", "gate": "G", "you": "Y"}
State = Literal["proposed", "accepted", "rejected", "replaced"]
Values = dict[str, Any]
TYPES: tuple[str, ...] = get_args(BoxType)
MODES: tuple[str, ...] = get_args(Mode)
WRITES_NOTHING = ("verify", "decompose", "gate")  # the types that may propose no deliverable
EDITABLE = frozenset(Box.model_fields) - {"id", "proposed"}  # what the owner may change of a proposed box


class ProposalRefused(ValueError):
    """A proposal that cannot be staged as sent, and what to fix."""


class Part(BaseModel):
    """A part of a batch's file: no field but its own."""

    model_config = ConfigDict(extra="forbid")


class Proposal(Part):
    """A box proposed for the flow, and what became of it."""

    id: str = Field(description="The id it takes in the flow, such as T1.")
    number: int = Field(ge=1, description="Its place in the batch, from 1: proposals after one box run in this order.")
    after: str = Field(description="The box of the flow it comes after.")
    box: Box = Field(description="The box as it would join the flow, the owner's edits included.")
    original: Box | None = Field(None, description="The box as the model proposed it, once the owner edited it.")
    why: str = Field("", description="Why the model proposed it.")
    state: State = Field("proposed", description="proposed (waiting for the owner), accepted, rejected or replaced.")
    given: datetime = Field(description="When it was proposed.")
    by: Actor = Field(description="Who proposed it: the agent's session, through the gateway.")
    decided: datetime | None = Field(None, description="When it was decided.")
    decided_by: Actor | None = Field(None, description="Who decided it: the owner through a client, or auto-accept.")
    said: str = Field("", description="Why it could not join when accepted, or why it was set aside.")


class Batch(BaseModel):
    """The proposals of one try of a box."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["flow-proposals/1"] = Field(SCHEMA, alias="schema")
    flow: str = Field(description="The flow's id: <workspace>/<name>.")
    run: int = Field(ge=1, description="The run.")
    box: str = Field(description="The box that proposed them.")
    attempt: int = Field(ge=1, alias="try", description="Its try.")
    summary: str = Field("", description="What the model said when it submitted them.")
    submitted: datetime | None = Field(None, description="When the model submitted them for the owner.")
    question: str = Field("", description="The question that asks the owner about them.")
    asked: list[str] = Field(default_factory=list, description="The proposals that question asks about.")
    replaced: list[str] | None = Field(
        None,
        description="The boxes its first proposal to join took out of the flow: those its box added before that had "
        "not started in the run; empty until one joins.",
    )
    proposals: list[Proposal] = Field(default_factory=list, description="Its proposals, in the order proposed.")

    def waiting(self) -> list[Proposal]:
        """The proposals still waiting for the owner."""
        return [each for each in self.proposals if each.state == "proposed"]

    def find(self, id: str) -> Proposal | None:
        """A proposal by its id."""
        return next((each for each in self.proposals if each.id == id), None)


class Batches:
    """The batches of every run, each beside its try: `run-<n>/<box>/try-<k>/proposals.json`."""

    def __init__(self, runs: Runs) -> None:
        self.runs = runs

    def path(self, run: Run, box: str, attempt: int) -> Path:
        """Where a try's batch is kept."""
        return self.runs.try_folder(run, box, attempt) / "proposals.json"

    def load(self, run: Run, box: str, attempt: int) -> Batch | None:
        """A try's batch, if it has one that reads."""
        try:
            return Batch.model_validate_json(read_whole(self.path(run, box, attempt)))
        except (OSError, ValueError):
            return None

    def last(self, run: Run, box: str) -> Batch | None:
        """The batch of a box's last try, if it has one."""
        tries = run.boxes[box].tries if box in run.boxes else []
        return self.load(run, box, tries[-1].number) if tries else None

    def of_run(self, run: Run) -> list[Batch]:
        """Every batch of a run that reads, by box and try."""
        folder = self.runs.run_folder(run)
        found = []
        for path in sorted(folder.glob("*/try-*/proposals.json")) if folder.is_dir() else []:
            try:
                found.append(Batch.model_validate_json(read_whole(path)))
            except (OSError, ValueError):
                continue
        return sorted(found, key=lambda batch: (batch.box, batch.attempt))

    def save(self, batch: Batch) -> Path:
        """Write a batch whole, at once; its path."""
        folder = self.runs.flow_folder(batch.flow) / f"run-{batch.run}" / batch.box / f"try-{batch.attempt}"
        path = folder / "proposals.json"
        write_whole(path, json.dumps(batch.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n")
        return path


def read(given: Mapping[str, Any], flow: Flow, *, id: str = "X1") -> tuple[str, Box, str]:
    """The box a model proposes, from the tool's arguments: the box it comes after, the box (its id `id`), and why;
    `ProposalRefused`, naming the argument to fix, when it cannot be one."""
    type = _text(given.get("type")).lower()
    if type not in TYPES:
        raise ProposalRefused(f"type is one of {', '.join(TYPES)}, not {_text(given.get('type'))!r}")
    after = _text(given.get("after"))
    ids = [box.id for box in flow.boxes]
    if after not in ids:
        named = f"names no box of the flow: {after}" if after else "is empty"
        raise ProposalRefused(f"after {named}; name the box it comes after, one of {', '.join(ids)}")
    title, prompt = _text(given.get("title")), _text(given.get("prompt"))
    if not title:
        raise ProposalRefused("the title is empty: say what the box does in a few words")
    if not prompt:
        raise ProposalRefused(
            "the prompt is empty: write everything the box's model must know, for a model that has never seen this "
            "session"
        )
    writes = _files(given.get("deliverable"), "deliverable")
    if not writes and type not in WRITES_NOTHING:
        raise ProposalRefused(f"{_tag(type)} writes a deliverable: name the files it writes in the folder")
    for path in writes:
        _not_settings(path)
    sees = _files(given.get("sees"), "sees")
    mode = _text(given.get("mode")).lower()
    if mode and mode not in MODES:
        raise ProposalRefused(f"mode is one of {', '.join(MODES)}, or empty for the box's own; not {mode!r}")
    accept = given.get("accept_when")
    accepted = [_text(each) for each in accept] if isinstance(accept, list) else _text(accept).splitlines()
    values: dict[str, Any] = {
        "id": id, "type": type, "title": title, "prompt": prompt, "writes": writes, "sees": sees,
        "mode": mode or None, "model": _text(given.get("model")),
        "accept_when": [each.strip() for each in accepted if each.strip()],
    }  # fmt: skip
    try:
        box = Box.model_validate(values)
    except ValidationError as error:
        said = "; ".join(f"{'.'.join(map(str, each['loc']))}: {each['msg']}" for each in error.errors())
        raise ProposalRefused(said.replace("Value error, ", "")) from error
    return after, box, _text(given.get("why"))


def edited(box: Box, changes: Mapping[str, Any]) -> Box:
    """A proposed box with the owner's changes: any of a box's settings but its id and its mark, checked as a
    proposal is (its files in the folder, no deliverable agents load as settings or instructions, a deliverable but for
    a VERIFY, a DECOMPOSE and a GATE); `ProposalRefused`, naming the setting to fix."""
    unknown = sorted(str(key) for key in changes if key not in EDITABLE)
    if unknown:
        raise ProposalRefused(
            f"{', '.join(unknown)}: not a setting of a box you may change; you may change {', '.join(sorted(EDITABLE))}"
        )
    values = {**box.model_dump(mode="json"), **changes}
    if "writes" in changes:
        values["writes"] = _files(changes["writes"], "deliverable")
        for path in values["writes"]:
            _not_settings(path)
    if "sees" in changes:
        values["sees"] = _files(changes["sees"], "sees")
    if "shows" in changes:
        values["shows"] = _files(changes["shows"], "shows")
    if "mode" in changes and not _text(changes["mode"]):
        values["mode"] = None  # the box's own: Plan for PLAN, VERIFY, DECOMPOSE, INTEGRATE, the workspace's for a TASK
    if not _text(values.get("prompt")):
        raise ProposalRefused("the prompt is empty: write everything the box's model must know")
    type = _text(values.get("type")).lower()
    if not values.get("writes") and type not in WRITES_NOTHING:
        raise ProposalRefused(f"{_tag(type)} writes a deliverable: name the files it writes in the folder")
    try:
        return Box.model_validate(values)
    except ValidationError as error:
        said = "; ".join(f"{'.'.join(map(str, each['loc']))}: {each['msg']}" for each in error.errors())
        raise ProposalRefused(said.replace("Value error, ", "")) from error


def _text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _files(value: Any, argument: str) -> list[str]:
    """Files of the folder, one path or a list of them; `ProposalRefused`, naming the argument, for one outside it."""
    listed = value if isinstance(value, list) else ([value] if _text(value) else [])
    found = []
    for each in listed:
        try:
            found.append(in_the_folder(_text(each)))
        except ValueError as error:
            raise ProposalRefused(f"{argument} {error}") from error
    return found


def _not_settings(path: str) -> None:
    """A deliverable that agents load as settings or instructions is refused, in any case (the planner may not write
    those either)."""
    parts = path.split("/")
    folders = {name.lower() for name in SETTINGS}
    for part in parts:
        if part.lower() in folders:
            raise ProposalRefused(
                f"deliverable {path} is in {part}, a folder agents and assistants load their settings from: a box "
                "may not write it"
            )
    if parts[-1].lower() in {name.lower() for name in INSTRUCTIONS}:
        raise ProposalRefused(f"deliverable {path} instructs agents and assistants: a box may not write it")


def _tag(type: str) -> str:
    return f"{'an' if type == 'integrate' else 'a'} {type.upper()}"


def next_id(type: str, taken: set[str]) -> str:
    """The id a proposed box takes: its type's letter and the lowest number not taken."""
    prefix = PREFIX.get(type, "X")
    number = 1
    while f"{prefix}{number}" in taken:
        number += 1
    return f"{prefix}{number}"


def joined(
    flow: Flow,
    batch: Batch,
    adding: Sequence[str],
    *,
    accepted: Literal["owner", "auto-accept"] = "owner",
    removing: Sequence[str] = (),
) -> Values:
    """The flow's values with the batch's proposals `adding` joined, each marked as accepted by `accepted`, and the
    boxes `removing` taken out first. The flow's rules are not checked here: `refusals` checks the result."""
    values = flow.model_dump(mode="json")
    boxes: list[Values] = values["boxes"]
    lines: list[Values] = values["lines"]
    for name in removing:
        _take_out(boxes, lines, name)
    present = {box["id"] for box in boxes}
    placed = {each.id: each.number for each in batch.proposals if each.state == "accepted" and each.id in present}
    for proposal in sorted((each for each in batch.proposals if each.id in adding), key=lambda each: each.number):
        box = proposal.box.model_dump(mode="json")
        box["id"] = proposal.id
        box["proposed"] = {"run": batch.run, "by": batch.box, "accepted": accepted}
        if flow.built is not None:
            on_its_own(box)  # a built flow runs on its own: its tasks' changes are not asked (design 0013 §15)
        earlier = [
            each.id
            for each in batch.proposals
            if each.after == proposal.after and each.number < proposal.number and each.id in placed
        ]
        anchor = max(earlier, key=lambda id: placed[id]) if earlier else ""
        _put(boxes, lines, box, proposal.after, anchor, set(placed))
        placed[proposal.id] = proposal.number
    return values


def refusals(values: Values) -> list[str]:
    """What is wrong with a flow's values, in the rules' own words, each naming its box or its line; none when it
    keeps every rule."""
    try:
        Flow.model_validate(values)
    except ValidationError as error:
        return [_said(values, problem) for problem in error.errors()]
    return []


def _said(values: Values, problem: Any) -> str:
    place = tuple(problem.get("loc") or ())
    message = str(problem.get("msg") or "").removeprefix("Value error, ")
    if len(place) >= 2 and place[0] == "boxes" and isinstance(place[1], int) and place[1] < len(values["boxes"]):
        return f"{values['boxes'][place[1]].get('id', place[1])}: {message}"
    if len(place) >= 2 and place[0] == "lines" and isinstance(place[1], int) and place[1] < len(values["lines"]):
        line = values["lines"][place[1]]
        return f"the line from {line.get('from')} to {line.get('to')}: {message}"
    return message


def _on(lines: list[Values], name: str) -> list[Values]:
    """The lines that lead on from a box: then and pass."""
    return [line for line in lines if line["from"] == name and line.get("when") != "fail"]


def _into(lines: list[Values], name: str) -> list[Values]:
    """The lines that lead on into a box."""
    return [line for line in lines if line["to"] == name and line.get("when") != "fail"]


def _line(source: str, target: str, when: str | None = None) -> Values:
    return {"from": source, "to": target, "when": when}


def _put(boxes: list[Values], lines: list[Values], box: Values, after: str, anchor: str, batch: set[str]) -> None:
    """Put a box into the flow after `after`, or right after `anchor`: an earlier proposal after it that joined."""
    types = {each["id"]: each["type"] for each in boxes}
    fan = ""
    if box["type"] == "task":
        if types.get(after) == "decompose":
            fan = after
        elif types.get(after) == "task":
            into = [line["from"] for line in _into(lines, after)]
            fan = into[0] if len(into) == 1 and types.get(into[0]) == "decompose" else ""
    if fan:
        _into_fan(boxes, lines, box, fan, anchor or (after if after != fan else ""), batch)
    else:
        _into_chain(boxes, lines, box, anchor or after)


def _into_fan(
    boxes: list[Values], lines: list[Values], box: Values, decompose: str, anchor: str, batch: set[str]
) -> None:
    """A TASK joins a DECOMPOSE's tasks: a line from the DECOMPOSE, one to the box they join at; its place among the
    boxes is right after `anchor`, else after the tasks of other batches, else right after the DECOMPOSE."""
    types = {each["id"]: each["type"] for each in boxes}
    tasks = [line["to"] for line in _on(lines, decompose) if types.get(line["to"]) == "task"]
    at = _index(boxes, decompose)
    if tasks:
        target = _joins_at(boxes, lines, tasks)
        others = [_index(boxes, task) for task in tasks if task not in batch]
        at = _index(boxes, anchor) if anchor else max([at, *others])
        added = [_line(decompose, box["id"])] + ([_line(box["id"], target)] if target else [])
        _insert_lines(lines, added, max(_last_line(lines, task) for task in tasks) + 1)
    else:
        leaving = _on(lines, decompose)
        where = lines.index(leaving[0]) if leaving else _last_line(lines, decompose) + 1
        for line in leaving:
            lines.remove(line)
        added = [_line(decompose, box["id"])] + [_line(box["id"], line["to"]) for line in leaving]
        _insert_lines(lines, added, where)
    boxes.insert(at + 1, box)


def _joins_at(boxes: list[Values], lines: list[Values], tasks: list[str]) -> str:
    """The box a DECOMPOSE's tasks join at: where the first task's then or pass lines lead, past the VERIFYs that check
    one of its tasks (a VERIFY proposed after a task goes between it and that box, and the rules then refuse a second
    task, since each leads straight to that box); none when they lead nowhere."""
    checks = {box["id"]: box.get("checks") for box in boxes if box["type"] == "verify"}
    name, seen = tasks[0], {tasks[0]}
    while True:
        leaving = _on(lines, name)
        if not leaving or leaving[0]["to"] in seen:
            return ""
        name = str(leaving[0]["to"])
        if name not in tasks and checks.get(name, "") not in tasks:
            return name
        seen.add(name)


def _into_chain(boxes: list[Values], lines: list[Values], box: Values, anchor: str) -> None:
    """A box goes between `anchor` and the box after it (a VERIFY's pass line stays its pass line); a VERIFY proposed
    checks the box it follows, its fail line back to it."""
    leaving = _on(lines, anchor)
    where = lines.index(leaving[0]) if leaving else _last_line(lines, anchor) + 1
    for line in leaving:
        lines.remove(line)
    verify = box["type"] == "verify"
    if verify and not box.get("checks"):
        box["checks"] = anchor
    added = [_line(anchor, box["id"], leaving[0].get("when") if leaving else None)]
    added += [_line(box["id"], line["to"], "pass" if verify else None) for line in leaving]
    if verify:
        added.append(_line(box["id"], box["checks"], "fail"))
    _insert_lines(lines, added, where)
    at = _index(boxes, anchor)
    boxes.insert(at + 1 if at >= 0 else len(boxes), box)


def _take_out(boxes: list[Values], lines: list[Values], name: str) -> None:
    """Take a box out of the flow, joining the box before it to the box after it when nothing else leads on from the
    one or into the other (a DECOMPOSE whose last task goes leads to the box after its tasks again)."""
    into, leaving = _into(lines, name), _on(lines, name)
    where = min((lines.index(line) for line in into + leaving), default=len(lines))
    lines[:] = [line for line in lines if name not in (line["from"], line["to"])]
    for before in into:
        for after in leaving:
            if not _on(lines, before["from"]) and not _into(lines, after["to"]):
                lines.insert(min(where, len(lines)), _line(before["from"], after["to"], before.get("when")))
    boxes[:] = [box for box in boxes if box["id"] != name]


def _index(boxes: list[Values], name: str) -> int:
    return next((index for index, box in enumerate(boxes) if box["id"] == name), -1)


def _last_line(lines: list[Values], name: str) -> int:
    """The index of the last line touching a box; -1 for none."""
    return max((index for index, line in enumerate(lines) if name in (line["from"], line["to"])), default=-1)


def _insert_lines(lines: list[Values], added: list[Values], at: int) -> None:
    """New lines where the lines they replace were, else after the box's last line, so the file's difference stays
    small."""
    at = min(max(at, 0), len(lines))
    lines[at:at] = added
