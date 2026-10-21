"""A session's main branches (design 0012 §6.2, decision 0050), and the branch each of its steps joins.

- **A Clank plan's steps**, when the session carries one out: a message of `/implement` names the plan's file
  ("Implement the plan in this file: ..."; design 0009 §5.1), and its Steps section's checklist (design 0009 §4) gives
  the branches, stable and ticked by the implementer, who works on the first step not ticked. A plan's ticks are its
  file's now; the boxes the session's edits of the file ticked (`[ ]` made `[x]` in an `edit` call's input) say how
  many were ticked when each step began, so a step read from the history joins its plan step as surely as one seen
  live. Steps that answer a message from before the plan was named join none.
- **The todo list's items** otherwise (`todos.py`), matched across its revisions by their text.
- **The owner's messages** without either (`from_said`): each is a branch, and the steps that answer it are its run.

An item is `{key, title, source, state, guessed, why, steps}`: its state done, now (the step being worked on while the
session works), planned or canceled; what a guess rests on in `why`.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any

from clank.components.agents.sessionflow.text import brief

ASKED = re.compile(r"Implement the plan in this file:[ \t]*([^\n]+)")
BOX = re.compile(r"^(\s*)[-*+]\s+\[([ xX])\]\s+(.*\S)\s*$")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
EDITS = ("edit", "multiedit")


@dataclass
class Step:
    """What the branches need of a step: its id, the message it answers, and the boxes its edits of the plan ticked."""

    id: str
    said: str
    ticks: int = 0
    guessed: list[str] = field(default_factory=list)


def plan_named(text: str) -> str:
    """The plan's file a message of `/implement` names, as written ("" when it names none)."""
    found = ASKED.search(text or "")
    return found.group(1).strip().strip("`'\"").strip() if found else ""


def checklist(text: str) -> list[tuple[str, bool]]:
    """A plan's steps, each with whether it is ticked: the checklist of its Steps section (its outermost items), or
    every checklist line of the file when it has no such section."""
    lines = (text or "").splitlines()
    section: list[str] | None = None
    for index, line in enumerate(lines):
        heading = HEADING.match(line)
        if heading and heading.group(2).strip().lower() == "steps":
            level = len(heading.group(1))
            section = []
            for following in lines[index + 1 :]:
                ends = HEADING.match(following)
                if ends and len(ends.group(1)) <= level:
                    break
                section.append(following)
            break
    boxes = [BOX.match(line) for line in (lines if section is None else section)]
    found = [box for box in boxes if box is not None]
    outermost = min((len(box.group(1)) for box in found), default=0)
    return [(box.group(3), box.group(2) != " ") for box in found if len(box.group(1)) == outermost]


def ticks(tool: str, input: Any, plan: str) -> tuple[int, bool]:
    """How many boxes of the plan's file an edit ticked, and whether that is a guess (its input was cut short)."""
    if tool not in EDITS or not plan:
        return 0, False
    said = str(input or "")
    try:
        given = json.loads(said)
    except ValueError:
        given = None
    if isinstance(given, dict):
        edits: list[Any] = given["edits"] if isinstance(given.get("edits"), list) else [given]
        if not same_file(str(given.get("filePath") or ""), plan):
            return 0, False
        made: int = sum(_boxes(each.get("newString")) - _boxes(each.get("oldString")) for each in edits
                        if isinstance(each, dict))  # fmt: skip
        return max(made, 0), False
    if plan not in said:
        return 0, False
    old, _, new = said.partition('"newString"')  # a cut input: its old text comes before its new one
    return max(_boxes(new) - _boxes(old), 0), True


def from_plan(
    path: str, plan: list[tuple[str, bool]], steps: list[Step], *, busy: bool
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """The plan's steps as the branches, and the plan step each session step joins: the first not ticked when it
    began."""
    ticked = sum(1 for _, done in plan if done)
    base = ticked - sum(step.ticks for step in steps)
    first = next((index for index, (_, done) in enumerate(plan) if not done), len(plan))
    items: list[dict[str, Any]] = [
        {"key": f"plan:{index + 1}", "title": brief(title), "source": "plan",
         "state": "done" if done else ("now" if busy and index == first else "planned"), "guessed": False,
         "why": "", "steps": []}
        for index, (title, done) in enumerate(plan)
    ]  # fmt: skip
    joined: dict[str, str] = {}
    made = 0
    for step in steps:
        index = base + made
        made += step.ticks
        if not 0 <= index < len(items):
            joined[step.id] = ""
            continue
        item = items[index]
        joined[step.id] = item["key"]
        item["steps"].append(step.id)
        if step.guessed or base < 0:
            item["guessed"] = True
            item["why"] = (
                f"the plan {path} has fewer boxes ticked than this session's edits ticked"
                if base < 0
                else f"an edit of {path} was cut short, so the boxes it ticked were counted from what was kept"
            )
    return items, joined


def same_file(path: str, plan: str) -> bool:
    """Whether a file the agent edited (its path in the container) is the plan (its path in the folder)."""
    path, plan = path.replace("\\", "/"), plan.replace("\\", "/").lstrip("./")
    return path == plan or path.endswith("/" + plan)


def _boxes(text: Any) -> int:
    """How many ticked boxes a text holds."""
    said = str(text or "")
    return said.count("[x]") + said.count("[X]")


def from_said(
    said: list[tuple[str, str]], steps: list[Step], *, busy: bool
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """The owner's messages (each its id and text) as the branches, and the one each step answers."""
    items: list[dict[str, Any]] = [
        {"key": f"said:{id}", "title": brief(text), "source": "said",
         "state": "now" if busy and index == len(said) - 1 else "done", "guessed": False, "why": "", "steps": []}
        for index, (id, text) in enumerate(said)
    ]  # fmt: skip
    keyed = {item["key"]: item for item in items}
    joined: dict[str, str] = {}
    for step in steps:
        item = keyed.get(f"said:{step.said}")
        joined[step.id] = item["key"] if item is not None else ""
        if item is not None:
            item["steps"].append(step.id)
    return items, joined
