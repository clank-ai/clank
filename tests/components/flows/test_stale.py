"""Design 0013 §8 (decision 0061): a finished box is changed when its settings are edited, or when its deliverable in
the folder no longer matches its fingerprint; every box after it that has run is then stale, and nothing runs again on
its own. Progress is not a change: a TASK box that ticks its step in PLAN.md, adds its Log line and sets the plan's
status marks nothing stale, even when the runner looks while the TASK still works, while a change to the plan's other
lines, or a tick made between boxes, does. An edit the owner makes at a gate is the owner's: it marks nothing stale.
Running again from a box, or sending one back, takes the boxes before it as they stand, so a later change to them marks
the boxes after them stale again. Run against the fake bridge and a synthetic folder."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import FLOW, OWNER, Rig, make_rig, question, running, study, until

pytestmark = pytest.mark.anyio
PLAN = """---
kind: plan
status: ready
title: The study
---
# The study

## Steps

- [ ] Write the grid (grid.json)
- [ ] Write the sweep (sweep.py)

## Log
"""


def tasks() -> dict[str, Any]:
    """YOU, PLAN, then two TASKs that follow the plan, the first waiting for the owner when it is done."""
    return {
        "schema": "flow/1",
        "title": "Study",
        "boxes": [
            {"id": "brief", "type": "you", "title": "Brief", "writes": ["BRIEF.md"]},
            {"id": "plan", "type": "plan", "title": "Write the plan", "writes": ["PLAN.md"]},
            {"id": "T1", "type": "task", "title": "The grid", "writes": ["grid.json"], "when_done": "wait"},
            {"id": "T2", "type": "task", "title": "The sweep", "writes": ["sweep.py"]},
        ],
        "lines": [{"from": "brief", "to": "plan"}, {"from": "plan", "to": "T1"}, {"from": "T1", "to": "T2"}],
    }


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, None)
    yield made
    made.kernel.close()


async def to_the_first_task(rig: Rig) -> Any:
    """The brief done and the plan written; the first TASK's first message sent."""
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "The brief.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
    rig.bridge.finish(plan.session, {"PLAN.md": PLAN})
    return await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))


def states(rig: Rig) -> dict[str, str]:
    run = rig.run()
    return {box: run.box(box).state for box in run.boxes}


async def test_an_edit_to_a_finished_box_marks_the_boxes_after_it_stale_and_starts_nothing(rig: Rig) -> None:
    rig.write_flow(study())
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        asked = await until(lambda: question(rig, "Brief"))
        rig.write("BRIEF.md", "The brief.\n")
        rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        rig.kernel.questions.answer((await until(lambda: question(rig, "You approve"))).id, by=OWNER, option="approve")
        task = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
        rig.bridge.finish(task.session, {"grid.json": "[]\n"})
        await until(lambda: rig.run().status == "done")
        sent = len(rig.bridge.prompts)

        edited = study()
        edited["boxes"][1]["prompt"] = "Write the study plan for the brief, with fixed seeds."
        rig.write_flow(edited)
        await until(lambda: rig.run().box("plan").changed)
        await anyio.sleep(0.2)
    assert rig.run().box("plan").changed == "its settings were edited"
    assert states(rig) == {"brief": "done", "plan": "done", "approve": "stale", "T1": "stale"}
    assert rig.run().box("T1").why == "plan changed: its settings were edited"
    assert len(rig.bridge.prompts) == sent, "nothing runs again on its own"
    [stale] = rig.events("flows.stale")
    assert (stale.data["box"], stale.data["boxes"]) == ("plan", ["approve", "T1"])


async def test_a_tasks_own_progress_in_the_plan_marks_nothing_stale(rig: Rig) -> None:
    rig.write_flow(tasks())
    async with running(rig.kernel):
        task = await to_the_first_task(rig)
        progressed = PLAN.replace("status: ready", "status: implementing").replace(
            "- [ ] Write the grid", "- [x] Write the grid"
        )
        progressed += "\n- 2026-10-19: wrote grid.json, 60 points.\n"
        rig.bridge.finish(task.session, {"PLAN.md": progressed, "grid.json": "[]\n"})
        wait = await until(lambda: question(rig, "The grid is done"))
        rig.kernel.questions.answer(wait.id, by=OWNER, option="go")
        await until(lambda: rig.bridge.prompted("Study · T2 · try 1"))
        await anyio.sleep(0.1)
    assert rig.run().box("plan").changed == ""
    assert states(rig) == {"brief": "done", "plan": "done", "T1": "done", "T2": "running"}
    assert rig.events("flows.stale") == []


async def test_a_task_that_changes_the_plans_other_lines_marks_the_boxes_after_the_plan_stale(rig: Rig) -> None:
    rig.write_flow(tasks())
    async with running(rig.kernel):
        task = await to_the_first_task(rig)
        rewritten = PLAN.replace("Write the grid (grid.json)", "Write a grid of 240 points (grid.json)")
        rig.bridge.finish(task.session, {"PLAN.md": rewritten, "grid.json": "[]\n"})
        await until(lambda: rig.run().box("plan").changed)
    assert rig.run().box("plan").changed == "PLAN.md changed in the folder"
    assert rig.run().box("T1").state == "stale"


async def test_a_tick_made_between_boxes_marks_the_boxes_after_the_plan_stale(rig: Rig) -> None:
    rig.write_flow(tasks())
    async with running(rig.kernel):
        task = await to_the_first_task(rig)
        rig.bridge.finish(task.session, {"grid.json": "[]\n"})
        wait = await until(lambda: question(rig, "The grid is done"))
        rig.write("PLAN.md", PLAN.replace("- [ ] Write the sweep", "- [x] Write the sweep"))
        rig.kernel.questions.answer(wait.id, by=OWNER, option="go")
        await until(lambda: rig.run().box("plan").changed)
    assert rig.run().box("plan").changed == "PLAN.md changed in the folder"
    assert rig.run().box("T1").state == "stale"


async def test_an_edit_approved_at_a_gate_marks_nothing_stale(rig: Rig) -> None:
    rig.write_flow(study())
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        asked = await until(lambda: question(rig, "Brief"))
        rig.write("BRIEF.md", "The brief.\n")
        rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan, 240 points\n"})
        gate = await until(lambda: question(rig, "You approve"))
        rig.write("PLAN.md", "# The plan, 60 points\n")
        rig.runner.nudge()
        await anyio.sleep(0.2)
        assert rig.run().box("plan").changed == "", "the owner edits it at the gate"
        rig.kernel.questions.answer(gate.id, by=OWNER, option="approve")
        task = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
        assert "# The plan, 60 points" in task.text
        rig.bridge.finish(task.session, {"grid.json": "[]\n"})
        await until(lambda: rig.run().status == "done")
    assert states(rig) == dict.fromkeys(("brief", "plan", "approve", "T1"), "done")
    assert rig.events("flows.stale") == []


async def test_a_finished_run_whose_workspace_is_gone_is_passed_over_quietly(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    rig.write_flow(study())
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await until(lambda: question(rig, "Brief"))
        rig.runner.stop(FLOW, actor=OWNER)
        await until(lambda: rig.run().status == "stopped")
        workspace = rig.kernel.settings.get("workspace", "myproject")
        rig.kernel.settings.delete("workspace", "myproject", base=workspace.revision, actor=OWNER)
        with caplog.at_level("ERROR"):
            rig.runner.nudge()
            await anyio.sleep(0.2)
    assert [record.message for record in caplog.records if record.levelname == "ERROR"] == []


async def test_a_tasks_progress_seen_while_it_still_works_marks_nothing_stale(rig: Rig) -> None:
    rig.write_flow(tasks())
    async with running(rig.kernel):
        first = await to_the_first_task(rig)
        ticked = PLAN.replace("- [ ] Write the grid", "- [x] Write the grid")
        rig.bridge.finish(first.session, {"PLAN.md": ticked, "grid.json": "[]\n"})
        rig.kernel.questions.answer((await until(lambda: question(rig, "The grid is done"))).id, by=OWNER, option="go")
        second = await until(lambda: rig.bridge.prompted("Study · T2 · try 1"))
        rig.write("PLAN.md", ticked.replace("- [ ] Write the sweep", "- [x] Write the sweep") + "\n- swept.\n")
        rig.runner.nudge()  # anything that wakes the runner while T2 works: a flow edited, a question answered
        await anyio.sleep(0.2)
        assert rig.run().box("plan").changed == "", "T2's own progress, while it works"
        assert rig.run().box("T1").state == "done"
        rig.bridge.finish(second.session, {"sweep.py": "print()\n"})
        await until(lambda: rig.run().status == "done")
    assert rig.run().box("plan").changed == ""
    assert states(rig) == dict.fromkeys(("brief", "plan", "T1", "T2"), "done")
    assert rig.events("flows.stale") == []


async def finished(rig: Rig) -> None:
    """The flow `study` run to its end: the brief, the plan, the gate approved, the grid."""
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "The brief.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
    rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
    rig.kernel.questions.answer((await until(lambda: question(rig, "You approve"))).id, by=OWNER, option="approve")
    task = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
    rig.bridge.finish(task.session, {"grid.json": "[]\n"})
    await until(lambda: rig.run().status == "done")


async def test_a_box_edited_again_after_running_from_the_box_after_it_marks_that_box_stale_again(rig: Rig) -> None:
    rig.write_flow(study())
    async with running(rig.kernel):
        await finished(rig)
        rig.write("PLAN.md", "# The plan, 60 points\n")
        rig.runner.nudge()
        await until(lambda: rig.run().box("T1").state == "stale")
        rig.runner.run_from(FLOW, "T1", actor=OWNER)
        task = await until(lambda: rig.bridge.prompted("Study · T1 · try 2"))
        assert rig.run().box("plan").changed == "", "running again from T1 takes the plan as it stands"
        rig.bridge.finish(task.session, {"grid.json": "[60]\n"})
        await until(lambda: rig.run().status == "done")

        rig.write("PLAN.md", "# The plan, 240 points\n")
        rig.runner.nudge()
        await until(lambda: rig.run().box("T1").state == "stale")
    assert rig.run().box("plan").changed == "PLAN.md changed in the folder"
    marked = [(event.data["box"], event.data["boxes"]) for event in rig.events("flows.stale")]
    assert marked == [("plan", ["approve", "T1"]), ("plan", ["T1"])]


async def test_a_box_edited_again_after_a_box_after_it_was_sent_back_marks_the_boxes_after_it_stale_again(
    rig: Rig,
) -> None:
    rig.write_flow(study())
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        asked = await until(lambda: question(rig, "Brief"))
        rig.write("BRIEF.md", "The brief.\n")
        rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        gate = await until(lambda: question(rig, "You approve"))
        rig.write("BRIEF.md", "The brief, with fixed seeds.\n")
        rig.runner.nudge()
        await until(lambda: rig.run().box("brief").changed)
        rig.kernel.questions.answer(gate.id, by=OWNER, option="back", text="Read the brief again.")
        again = await until(lambda: rig.bridge.prompted("Study · plan · try 2"))
        assert rig.run().box("brief").changed == "", "sending the plan back takes the brief as it stands"
        rig.bridge.finish(again.session, {"PLAN.md": "# The plan, with fixed seeds\n"})
        await until(lambda: question(rig, "You approve"))

        rig.write("BRIEF.md", "The brief, with other seeds.\n")
        rig.runner.nudge()
        await until(lambda: rig.run().box("brief").changed)
    assert rig.run().box("plan").state == "stale"
    marked = [(event.data["box"], event.data["boxes"]) for event in rig.events("flows.stale")]
    assert marked == [("brief", ["plan"]), ("brief", ["plan"])]
