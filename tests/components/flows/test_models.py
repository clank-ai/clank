"""Design 0013 §7 (decisions 0062 and 0063): a box's model is a preset: its own, else the flow's; a VERIFY's is the
preset of the box it checks unless it names another, so a check and its loop cost no switch; a box that names none runs
on what the main slot runs. A run of a flow switches the main slot exactly before each box whose preset is not the one
loaded by then, along the order its boxes run in."""

import itertools
from typing import Any

from clank.components.flows.kinds import Flow
from clank.components.flows.models import named, switches

PRESETS = {"daily 262k": "daily-262k", "daily-262k": "daily-262k", "fast 64k": "fast-64k", "fast-64k": "fast-64k"}


def resolve(name: str) -> str:
    """A preset's id, by its id or its title, as the runtime finds it."""
    return PRESETS.get(name.strip().lower(), name)


def flow(boxes: list[dict[str, Any]], model: str = "") -> Flow:
    """A chain of the boxes after the owner's brief, in their order, a VERIFY's fail line back to the box it checks."""
    if boxes[0]["type"] != "you":
        boxes = [box("brief", "you", writes=["BRIEF.md"]), *boxes]
    lines: list[dict[str, Any]] = []
    for before, then in itertools.pairwise(boxes):
        when = {"when": "pass"} if before["type"] == "verify" else {}
        lines.append({"from": before["id"], "to": then["id"], **when})
    lines += [{"from": each["id"], "to": each["checks"], "when": "fail"} for each in boxes if each["type"] == "verify"]
    return Flow.model_validate({"defaults": {"model": model}, "boxes": boxes, "lines": lines})


def box(id: str, type: str = "task", **values: Any) -> dict[str, Any]:
    writes = [] if type in ("you", "gate", "verify", "decompose") else [f"{id}.md"]
    return {"id": id, "type": type, "title": id, "writes": writes, **values}


def test_a_box_runs_on_its_own_preset_else_the_flows() -> None:
    made = flow([box("plan", "plan"), box("T1", model="fast 64K")], model="daily 262K")
    assert [named(made, each) for each in made.boxes] == ["", "daily 262K", "fast 64K"]


def test_a_verify_runs_on_the_preset_of_the_box_it_checks_unless_it_names_another() -> None:
    made = flow(
        [
            box("plan", "plan", model="fast 64K"),
            box("check", "verify", checks="plan"),
            box("T1"),
            box("again", "verify", checks="T1", model="fast 64K"),
            box("review", "gate"),
        ],
        model="daily 262K",
    )
    by_id = {each.id: each for each in made.boxes}
    assert named(made, by_id["check"]) == "fast 64K", "the checked box's own preset"
    assert named(made, by_id["again"]) == "fast 64K", "its own, when it names one"
    unnamed = flow([box("plan", "plan"), box("check", "verify", checks="plan"), box("review", "gate")], "daily 262K")
    assert named(unnamed, unnamed.boxes[2]) == "daily 262K", "the checked box's: the flow's"


def test_a_box_that_names_no_preset_runs_on_what_the_slot_runs() -> None:
    made = flow([box("plan", "plan"), box("check", "verify", checks="plan"), box("T1")])
    assert [named(made, each) for each in made.boxes] == ["", "", "", ""]
    assert switches(made, "fast-64k", resolve) == [], "nothing is loaded for a box that names none"


def test_a_flow_alternating_two_presets_switches_before_each_box_that_needs_the_other() -> None:
    made = flow(
        [
            box("plan", "plan"),
            box("check", "verify", checks="plan"),
            box("approve", "gate"),
            box("T1", model="fast 64K"),
            box("T2", model="fast-64k"),
            box("T3"),
            box("review", "gate"),
        ],
        model="daily 262K",
    )
    assert switches(made, "daily-262k", resolve) == [("T1", "fast-64k"), ("T3", "daily-262k")], (
        "the plan and its check keep the preset loaded, T2 keeps T1's, by its id or its title"
    )
    assert switches(made, "", resolve) == [("plan", "daily-262k"), ("T1", "fast-64k"), ("T3", "daily-262k")], (
        "with nothing loaded, the first box loads its preset"
    )
