"""Design 0013 §3 and §9 (decisions 0057 and 0064): the boxes a model proposes join the flow's file once accepted, each
marked with the run and the box that proposed them. TASKs proposed after a DECOMPOSE fan out from it and join at the box
after it, one after another in the order proposed, whatever order they are accepted in; one task alone is a chain
between them; a box proposed after a box of the chain goes between it and the next, and a VERIFY checks the box it
follows, its fail line back to it; a task proposed later goes to the box the tasks join at, past a VERIFY that checks
one of them, so the rules refuse it (a DECOMPOSE's tasks each lead to that box) rather than join it at that VERIFY. A
DECOMPOSE's tasks taken out (replaced by its new proposals) leave the lines reconnected around them. Whatever breaks a
rule of §3 is refused in the rule's words. Pure functions over the flow's values; nothing runs."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from clank.components.flows.kinds import Box, Flow
from clank.components.flows.proposals import Batch, Proposal, joined, refusals
from clank.components.flows.verdicts import AGENT

D1 = Path(__file__).with_name("d1-flow.json")
WHEN = datetime(2026, 10, 20, 1, 0, tzinfo=UTC)
TASKS = ["T1", "T2", "T3", "T4"]


def without_tasks() -> Flow:
    """Board D1's flow before its DECOMPOSE proposed: split leads straight to join."""
    values = json.loads(D1.read_text(encoding="utf-8"))
    del values["schema"]
    values["boxes"] = [box for box in values["boxes"] if box["id"] not in TASKS]
    values["lines"] = [line for line in values["lines"] if line["from"] not in TASKS and line["to"] not in TASKS]
    values["lines"].insert(5, {"from": "split", "to": "join"})
    return Flow.model_validate(values)


def proposal(number: int, after: str = "split", type: str = "task", **box: Any) -> Proposal:
    id = box.pop("id", f"T{number}")
    made = Box(id=id, type=type, title=box.pop("title", f"Task {number}"), prompt="Do it.", **box)
    if type == "task" and not made.writes:
        made = made.model_copy(update={"writes": [f"out/{id}.md"]})
    return Proposal(id=id, number=number, after=after, box=made, given=WHEN, by=AGENT)


def batch(*proposals: Proposal, box: str = "split", accepted: tuple[str, ...] = ()) -> Batch:
    marked = [each.model_copy(update={"state": "accepted"}) if each.id in accepted else each for each in proposals]
    return Batch(flow="myproject/study", run=1, box=box, attempt=1, proposals=marked)


def ids(values: dict[str, Any]) -> list[str]:
    return [box["id"] for box in values["boxes"]]


def lines(values: dict[str, Any]) -> list[tuple[str, str, str | None]]:
    return [(line["from"], line["to"], line.get("when")) for line in values["lines"]]


def test_tasks_proposed_after_a_decompose_fan_out_from_it_and_join_at_the_box_after_it_in_the_order_proposed() -> None:
    proposed = batch(*(proposal(number) for number in range(1, 5)))
    values = joined(without_tasks(), proposed, TASKS)
    assert ids(values) == ["brief", "plan", "check", "approve", "split", *TASKS, "join", "review"]
    assert sorted(lines(values)) == sorted(
        [
            ("brief", "plan", None), ("plan", "check", None), ("check", "approve", "pass"),
            ("check", "plan", "fail"), ("approve", "split", None), ("join", "review", None),
            *(("split", task, None) for task in TASKS), *((task, "join", None) for task in TASKS),
        ]
    )  # fmt: skip
    flow = Flow.model_validate(values)
    assert [box.proposed.model_dump() for box in flow.boxes if box.proposed is not None] == [
        {"run": 1, "by": "split", "accepted": "owner"}
    ] * 4
    assert refusals(values) == []


def test_one_task_alone_is_a_chain_between_the_decompose_and_the_box_after_it() -> None:
    values = joined(without_tasks(), batch(proposal(1)), ["T1"])
    assert ("split", "join", None) not in lines(values)
    assert ("split", "T1", None) in lines(values)
    assert ("T1", "join", None) in lines(values)
    assert refusals(values) == []


def test_tasks_accepted_out_of_order_keep_the_order_proposed() -> None:
    flow = without_tasks()
    first = batch(*(proposal(number) for number in range(1, 5)))
    values = joined(flow, first, ["T3"])
    values = joined(Flow.model_validate(values), batch(*first.proposals, accepted=("T3",)), ["T1"])
    values = joined(Flow.model_validate(values), batch(*first.proposals, accepted=("T1", "T3")), ["T4", "T2"])
    assert ids(values) == ["brief", "plan", "check", "approve", "split", *TASKS, "join", "review"]
    assert refusals(values) == []


def test_tasks_proposed_after_a_task_of_the_decompose_join_its_tasks_right_after_it() -> None:
    flow = Flow.model_validate(joined(without_tasks(), batch(proposal(1), proposal(2)), ["T1", "T2"]))
    later = batch(proposal(5, after="T1"), proposal(6, after="T1"), box="T1")
    values = joined(flow, later, ["T5", "T6"])
    assert ids(values)[4:9] == ["split", "T1", "T5", "T6", "T2"]
    assert ("split", "T5", None) in lines(values)
    assert ("T6", "join", None) in lines(values)
    assert Flow.model_validate(values).boxes[6].proposed.by == "T1"  # type: ignore[union-attr]


def test_a_box_proposed_after_a_box_of_the_chain_goes_between_it_and_the_next() -> None:
    values = joined(without_tasks(), batch(proposal(1, after="approve", type="plan", id="P1", writes=["NOTES.md"])),
                    ["P1"])  # fmt: skip
    assert ids(values)[3:6] == ["approve", "P1", "split"]
    assert ("approve", "P1", None) in lines(values)
    assert ("P1", "split", None) in lines(values)
    assert ("approve", "split", None) not in lines(values)
    assert refusals(values) == []


def test_a_task_proposed_later_is_refused_never_joined_at_a_verify_that_checks_one_of_the_tasks() -> None:
    staged = batch(proposal(1), proposal(2, after="T1", type="verify", id="V1"), proposal(3, id="T2"))
    flow = Flow.model_validate(joined(without_tasks(), staged, ["T1"]))
    flow = Flow.model_validate(joined(flow, batch(*staged.proposals, accepted=("T1",)), ["V1"]))
    values = joined(flow, batch(*staged.proposals, accepted=("T1", "V1")), ["T2"])
    assert ("T2", "V1", None) not in lines(values), "V1 checks T1 only: T2 is not joined at it"
    assert ("T2", "join", None) in lines(values)
    assert any("only a DECOMPOSE's tasks fan out, each to the same box after them" in each for each in refusals(values))


def test_boxes_proposed_after_a_verify_go_on_its_pass_line() -> None:
    values = joined(without_tasks(), batch(proposal(1, after="check", type="gate", id="G1")), ["G1"])
    assert ("check", "G1", "pass") in lines(values)
    assert ("G1", "approve", None) in lines(values)
    assert ("check", "plan", "fail") in lines(values)
    assert refusals(values) == []


def test_a_verify_proposed_after_a_box_checks_it_with_its_fail_line_back_to_it() -> None:
    plan = proposal(1, after="approve", type="plan", id="P1", writes=["NOTES.md"])
    values = joined(without_tasks(), batch(plan, proposal(2, after="approve", type="verify", id="V1")), ["P1", "V1"])
    assert ids(values)[3:7] == ["approve", "P1", "V1", "split"]
    assert values["boxes"][5]["checks"] == "P1"
    assert {("P1", "V1", None), ("V1", "split", "pass"), ("V1", "P1", "fail")} <= set(lines(values))
    assert refusals(values) == []


def test_a_decomposes_tasks_taken_out_leave_the_lines_reconnected_around_them() -> None:
    flow = Flow.model_validate(joined(without_tasks(), batch(*(proposal(n) for n in range(1, 4))), ["T1", "T2", "T3"]))
    again = batch(proposal(5), proposal(6))
    values = joined(flow, again, ["T5", "T6"], removing=["T2", "T3"])
    assert ids(values)[4:8] == ["split", "T1", "T5", "T6"]
    assert {("split", "T2", None), ("T3", "join", None)}.isdisjoint(lines(values))
    assert refusals(values) == []
    alone = joined(flow, batch(), [], removing=["T1", "T2", "T3"])
    assert ("split", "join", None) in lines(alone), "the decompose leads to the box after its tasks again"
    assert refusals(alone) == []


def test_boxes_joined_by_auto_accept_are_marked_so() -> None:
    values = joined(without_tasks(), batch(proposal(1)), ["T1"], accepted="auto-accept")
    assert values["boxes"][5]["proposed"] == {"run": 1, "by": "split", "accepted": "auto-accept"}


def test_a_flow_that_breaks_a_rule_is_refused_in_the_rules_words() -> None:
    values = joined(without_tasks(), batch(proposal(1, writes=["grid.json"], mode="plan")), ["T1"])
    [said] = refusals(values)
    assert said == (
        "T1: grid.json is not Markdown, and T1 runs in Plan mode, whose planner writes Markdown only: give it the "
        "mode review or auto"
    )
    values = joined(without_tasks(), batch(proposal(1, after="T9")), ["T1"])
    assert refusals(values), "it reaches nothing"


@pytest.mark.parametrize("type", ["you", "gate"])
def test_a_box_done_by_you_with_a_model_is_refused_naming_the_box(type: str) -> None:
    values = joined(without_tasks(), batch(proposal(1, after="approve", type=type, id="X1", model="daily 262K")),
                    ["X1"])  # fmt: skip
    assert refusals(values) == [f"X1: a {type.upper()} is done by you: it has no model"]
