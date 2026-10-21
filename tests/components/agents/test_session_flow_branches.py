"""Design 0012 §6.2 and §11 step 5 (decision 0050), design 0009 §4 and §5.1: a session's main branches. When the session
carries out a Clank plan (its message is `/implement`'s, naming the plan's file), they are the plan's checklist steps,
even beside a todo list, and a step joins the step first not ticked when it began; without such a plan, the todo list's
items, matched across revisions by their text, a guessed match flagged, and a step joins the item in progress when it
began; without either, the owner's messages and the runs of steps that answer them.
"""

import json
from typing import Any

from clank.components.agents.adapters.opencode import prompt
from clank.components.agents.sessionflow.branches import checklist, plan_named
from clank.components.agents.sessionflow.flow import Flow
from tests.support.flowlines import SESSION, history, lines, page, status, step, text, tool, updated, user

PLAN = "studies/tau/plan.md"
WRITTEN = """---
kind: plan
status: implementing
---

# Tau against p

## Checks

- [ ] The pilot's tau matches the known limit

## Steps

- [{one}] Write the simulation script
  - [ ] a sub-step is not a step of its own
- [{two}] Run it for n=8
- [ ] Draw the figure

## Log

- 2026-10-19: wrote the script
"""


def written(one: bool, two: bool) -> str:
    return WRITTEN.format(one="x" if one else " ", two="x" if two else " ")


def implementing() -> str:
    """The first message `/implement` sends, naming the plan."""
    return prompt("implement.md").replace("$ARGUMENTS", PLAN)


def ticking(id: str, which: str) -> dict[str, Any]:
    """An edit of the plan that ticks one of its steps."""
    return tool(id, "edit", input={"filePath": f"/workspace/{PLAN}", "oldString": f"- [ ] {which}",
                                   "newString": f"- [x] {which}"})  # fmt: skip


def working(id: str) -> dict[str, Any]:
    return tool(id, "bash", input={"command": "python run.py"}, metadata={"exit": 0})


def items(flow: Flow) -> list[tuple[str, str, str]]:
    return [(item["key"], item["title"], item["state"]) for item in flow.view()["items"]]


def joined(flow: Flow) -> dict[str, str]:
    return {node["id"]: node["item"] for node in flow.view()["nodes"] if node["kind"] == "step"}


def test_a_clank_plans_checklist_steps_become_the_main_branches_even_beside_a_todo_list() -> None:
    flow = Flow(SESSION)
    flow.history(page([
        user("msg_01", 1_000, implementing()),
        step("msg_02", "msg_01", 2_000, [working("c1")], completed=3_000),
    ]))  # fmt: skip
    todos = [{"content": "Draw the figure", "status": "in_progress", "priority": "high"}]
    for line in lines([status("busy"), {"type": "todo.updated", "properties": {"sessionID": SESSION, "todos": todos}}]):
        flow.heard(line)
    assert flow.plan == PLAN
    assert flow.view()["head"]["branches"] != "plan", "the plan's file not read yet"
    flow.planned(written(True, False))
    assert items(flow) == [
        ("plan:1", "Write the simulation script", "done"), ("plan:2", "Run it for n=8", "now"),
        ("plan:3", "Draw the figure", "planned"),
    ]  # fmt: skip
    head = flow.view()["head"]
    assert (head["branches"], head["plan"]) == ("plan", PLAN)
    assert all(item["source"] == "plan" and not item["guessed"] for item in flow.view()["items"])
    flow.planned(None)
    assert flow.view()["head"]["branches"] != "plan", "a plan that can no longer be read gives no branches"


def test_a_step_joins_the_plan_step_first_not_ticked_when_it_began() -> None:
    flow = Flow(SESSION)
    flow.history(page([
        user("msg_01", 1_000, implementing()),
        step("msg_02", "msg_01", 2_000, [working("c1")], completed=2_500),
        step("msg_03", "msg_01", 3_000, [ticking("c2", "Write the simulation script")], completed=3_500),
        step("msg_04", "msg_01", 4_000, [working("c3")], completed=4_500),
        step("msg_05", "msg_01", 5_000, [working("c4"), ticking("c5", "Run it for n=8")], completed=5_500),
        step("msg_06", "msg_01", 6_000, [text("t1", "Now the figure.")]),
    ]))  # fmt: skip
    flow.planned(written(True, True))
    assert joined(flow) == {"msg_02": "plan:1", "msg_03": "plan:1", "msg_04": "plan:2", "msg_05": "plan:2",
                            "msg_06": "plan:3"}  # fmt: skip
    steps = {item["key"]: item["steps"] for item in flow.view()["items"]}
    assert steps == {"plan:1": ["msg_02", "msg_03"], "plan:2": ["msg_04", "msg_05"], "plan:3": ["msg_06"]}
    later = Flow(SESSION)  # a session that goes on with a plan an earlier one began: its first step was ticked then
    later.history(page([
        user("msg_01", 1_000, implementing()),
        step("msg_02", "msg_01", 2_000, [ticking("c1", "Run it for n=8")], completed=2_500),
        step("msg_03", "msg_01", 3_000, [working("c2")], completed=3_500),
    ]))  # fmt: skip
    later.planned(written(True, True))
    assert joined(later) == {"msg_02": "plan:2", "msg_03": "plan:3"}
    before = Flow(SESSION)  # steps that answer a message before the plan was named join none of its steps
    before.history(page([
        user("msg_01", 1_000, "Look around first."),
        step("msg_02", "msg_01", 2_000, [working("c1")], completed=2_500),
        user("msg_03", 3_000, implementing()),
        step("msg_04", "msg_03", 4_000, [working("c2")], completed=4_500),
    ]))  # fmt: skip
    before.planned(written(False, False))
    assert joined(before) == {"msg_02": "", "msg_04": "plan:1"}


def test_a_plans_steps_section_is_read_and_its_other_checklists_are_not() -> None:
    assert checklist(written(True, False)) == [
        ("Write the simulation script", True), ("Run it for n=8", False), ("Draw the figure", False)
    ]  # fmt: skip
    assert checklist("- [x] one\n* [ ] two\nsome text\n") == [("one", True), ("two", False)], "no Steps section"
    assert checklist("# A plan\n\nNo checklist at all.\n") == []
    assert plan_named(implementing()) == PLAN
    assert plan_named("Implement the plan in this file: `studies/a b.md`") == "studies/a b.md"
    assert plan_named("Plot tau against p.") == ""


def todo(content: str, state: str) -> dict[str, str]:
    return {"content": content, "status": state, "priority": "medium"}


def wrote(id: str, todos: list[dict[str, str]]) -> dict[str, Any]:
    """OpenCode's `todowrite` call, as its history keeps it (its output is the list, as JSON)."""
    return tool(id, "todowrite", input={"todos": todos}, output=json.dumps(todos, indent=2))


def revised(todos: list[dict[str, str]]) -> list[dict[str, Any]]:
    """The line OpenCode's `todo.updated` becomes."""
    return lines([{"type": "todo.updated", "properties": {"sessionID": SESSION, "todos": todos}}])


def test_without_a_plan_todo_revisions_become_items_matched_by_their_text_a_guess_flagged() -> None:
    flow = Flow(SESSION)
    flow.history(page([
        user("msg_01", 1_000, "Plot tau against p."),
        step("msg_02", "msg_01", 2_000, [wrote("c1", [
            todo("Read the data", "in_progress"), todo("Draw the figure", "pending"), todo("Check the axis", "pending"),
            todo("Tidy the README", "pending"),
        ])], completed=2_500),
        step("msg_03", "msg_01", 3_000, [working("c2")]),
    ]))  # fmt: skip
    revision = [
        todo("Read the data", "completed"), todo("Draw the tau figure", "in_progress"),
        todo("Check the axis", "pending"),
        todo("Tidy the README", "cancelled"),  # spelling: keep (OpenCode's own word)
        todo("Write the report", "pending"),
    ]  # fmt: skip
    for line in revised(revision):
        flow.heard(line)
    found = flow.view()["items"]
    assert [(item["key"], item["title"], item["state"], item["guessed"]) for item in found] == [
        ("todo:1", "Read the data", "done", False), ("todo:2", "Draw the tau figure", "now", True),
        ("todo:3", "Check the axis", "planned", False), ("todo:4", "Tidy the README", "canceled", False),
        ("todo:5", "Write the report", "planned", False),
    ]  # fmt: skip
    assert "Draw the figure" in found[1]["why"], "a guess says what it rests on"
    assert {item["source"] for item in found} == {"todo"}
    assert flow.view()["head"]["branches"] == "todo"


def test_an_unchanged_todo_keeps_its_item_when_a_new_one_alike_is_listed_before_it() -> None:
    flow = Flow(SESSION)
    flow.history(page([
        user("msg_01", 1_000, "Plot tau against p."),
        step("msg_02", "msg_01", 2_000, [wrote("c1", [todo("Run the tests", "in_progress"),
                                                      todo("Fix the import", "pending")])], completed=2_500),
        step("msg_03", "msg_01", 3_000, [wrote("c2", [todo("Run the tests again", "pending"),
                                                      todo("Run the tests", "completed"),
                                                      todo("Fix the import", "in_progress")])], completed=3_500),
    ]))  # fmt: skip
    found = flow.view()["items"]
    assert [(item["key"], item["title"], item["state"], item["guessed"]) for item in found] == [
        ("todo:1", "Run the tests", "done", False), ("todo:2", "Fix the import", "now", False),
        ("todo:3", "Run the tests again", "planned", False),
    ], "the same text is the same item, wherever the revision lists it"  # fmt: skip


def test_a_long_todo_list_read_from_the_history_is_kept_whole() -> None:
    """The bridge cuts a call's input and output; a `todowrite` call's list comes whole beside them."""
    listed = [
        todo(f"Check the figure of run {n} against the paper's table, axis by axis", "pending") for n in range(12)
    ]
    listed[0]["status"] = "in_progress"
    flow = Flow(SESSION)
    flow.history(page([user("msg_01", 1_000, "Check every figure."),
                       step("msg_02", "msg_01", 2_000, [wrote("c1", listed)], completed=2_500)]))  # fmt: skip
    assert flow.view()["head"]["branches"] == "todo"
    assert [item["state"] for item in flow.view()["items"]] == ["now", *["planned"] * 11]


def test_a_step_joins_the_todo_item_in_progress_when_it_began() -> None:
    flow = Flow(SESSION)
    flow.history(page([
        user("msg_01", 1_000, "Plot tau against p."),
        step("msg_02", "msg_01", 2_000, [wrote("c1", [todo("Read the data", "in_progress"),
                                                      todo("Draw the figure", "pending")])], completed=2_500),
        step("msg_03", "msg_01", 3_000, [working("c2")], completed=3_500),
        step("msg_04", "msg_01", 4_000, [wrote("c3", [todo("Read the data", "completed"),
                                                      todo("Draw the figure", "in_progress")])], completed=4_500),
        step("msg_05", "msg_01", 5_000, [working("c4")], completed=5_500),
    ]))  # fmt: skip
    assert joined(flow) == {"msg_02": "", "msg_03": "todo:1", "msg_04": "todo:1", "msg_05": "todo:2"}
    for line in lines([*updated(step("msg_06", "msg_01", 6_000, [working("c5")]))]):
        flow.heard(line)
    for line in revised([todo("Read the data", "completed"), todo("Draw the figure", "completed")]):
        flow.heard(line)  # heard while msg_06 runs: it wrote this revision, so it began on the one before
    assert joined(flow)["msg_06"] == "todo:2"
    assert [item["steps"] for item in flow.view()["items"]] == [["msg_03", "msg_04"], ["msg_05", "msg_06"]]


def test_without_either_the_owners_messages_and_the_runs_of_steps_between_them_are_the_branches() -> None:
    flow = Flow(SESSION)
    flow.history(page(history()))
    for line in lines([status("busy")]):
        flow.heard(line)
    found = flow.view()["items"]
    assert [(item["key"], item["source"], item["state"]) for item in found] == [
        ("said:msg_01", "said", "done"), ("said:msg_04", "said", "now")
    ]  # fmt: skip
    assert found[0]["title"].startswith("Plot tau against p for n=8")
    assert joined(flow) == {"msg_02": "said:msg_01", "msg_03": "said:msg_01", "msg_05": "said:msg_04"}
    assert flow.view()["head"]["branches"] == "said"
