"""Design 0013 §5, §6 and §10 (decisions 0060, 0061 and 0065): the runner runs a flow in the service, one box after
another: YOU boxes and gates are questions that wait for the owner; each model box is a `flows.box` operation that
starts a new session on the flow's own OpenCode server, sends its first message with the box's agent and model, keeps
that message as a file, follows the session to its end and collects its deliverables; a box that ends without its
deliverable, or with one left from before, fails and waits at a gate; *send back* puts the owner's note, and that the
box was sent back, in the box's next first message; each step is an event with its actor. A session that ended while its
workspace's watcher started again is read once the watcher is back, and its box ends. The flow's next run uses the
server its last run started. A gate says which try the box it sends back to runs, and when that is its last or past its
tries. Run against the fake bridge and a synthetic folder."""

from collections.abc import Iterator
from pathlib import Path

import anyio
import pytest

from clank.components.flows.first import instructions
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import FLOW, OWNER, Rig, make_rig, question, running, study, until

pytestmark = pytest.mark.anyio
MODEL = {"providerID": "clank", "modelID": "agent"}


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, study())
    yield made
    made.kernel.close()


async def brief_done(rig: Rig) -> None:
    """The owner writes the brief and says it is done."""
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "About 60 grid points, at most 48 CPU-hours.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")


async def test_a_flow_of_you_plan_gate_and_task_runs_in_order_one_new_session_per_box(rig: Rig) -> None:
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await until(lambda: question(rig, "Brief"))
        assert rig.bridge.prompts == [], "nothing starts before the brief is done"
        await brief_done(rig)

        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        assert (plan.agent, plan.model) == ("planner", MODEL), "the planner, on the gateway's role"
        assert plan.text.startswith(instructions("plan"))
        assert "About 60 grid points" in plan.text, "the brief it sees, handed whole"
        kept = rig.runner.runs.try_folder(rig.run(), "plan", 1) / "first-message.md"
        assert kept.read_bytes().decode("utf-8") == plan.text, "the first message, kept as a file"
        assert rig.run().box("plan").state == "running"
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})

        gate = await until(lambda: question(rig, "You approve the plan"))
        await anyio.sleep(0.2)
        assert rig.bridge.prompted("T1") is None, "a gate waits"
        assert rig.run().box("plan").state == "done"
        copy = rig.runner.runs.try_folder(rig.run(), "plan", 1) / "deliverables" / "PLAN.md"
        assert copy.read_text(encoding="utf-8") == "# The plan\n"
        rig.kernel.questions.answer(gate.id, by=OWNER, option="approve")

        task = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
        assert (task.agent, task.model) == ("build", MODEL)
        assert task.session != plan.session, "a new session for each box"
        assert task.port == plan.port, "on the flow's one server"
        assert len(rig.bridge.done("serve")) == 1
        assert not rig.bridge.servers[task.port].terminal
        rig.bridge.finish(task.session, {"grid.json": "[]\n"})
        await until(lambda: rig.run().status == "done")

    run = rig.run()
    assert {box: run.box(box).state for box in ("brief", "plan", "approve", "T1")} == dict.fromkeys(
        ("brief", "plan", "approve", "T1"), "done"
    )
    steps = [
        (event.type, event.data.get("box"), event.data.get("outcome"), event.actor.kind)
        for event in rig.events("flows.run_started", "flows.box_started", "flows.box_ended", "flows.run_ended")
    ]
    assert steps == [
        ("flows.run_started", None, None, "user"),
        ("flows.box_started", "brief", None, "clank"),
        ("flows.box_ended", "brief", "done", "user"),
        ("flows.box_started", "plan", None, "clank"),
        ("flows.box_ended", "plan", "done", "clank"),
        ("flows.box_started", "approve", None, "clank"),
        ("flows.box_ended", "approve", "done", "user"),
        ("flows.box_started", "T1", None, "clank"),
        ("flows.box_ended", "T1", "done", "clank"),
        ("flows.run_ended", None, "done", "clank"),
    ]
    [operation, *_] = rig.kernel.operations.find()
    assert operation.type == "flows.box"
    assert [step.name for step in operation.steps] == ["model", "server", "session", "work", "collect"]


async def test_send_back_puts_the_note_in_the_boxs_next_first_message(rig: Rig) -> None:
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan, 240 points\n"})
        gate = await until(lambda: question(rig, "You approve the plan"))
        rig.kernel.questions.answer(gate.id, by=OWNER, option="back", text="About 60 points, as the brief says.")

        again = await until(lambda: rig.bridge.prompted("Study · plan · try 2"))
        assert "This is try 2. Try 1 was done; the user sent it back at You approve the plan." in again.text
        assert "About 60 points, as the brief says." in again.text
        assert rig.run().box("approve").state == "waiting", "the gate runs again after it"
        rig.bridge.finish(again.session, {"PLAN.md": "# The plan, 60 points\n"})
        gate = await until(lambda: question(rig, "You approve the plan"))
        rig.kernel.questions.answer(gate.id, by=OWNER, option="approve")
        await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))


async def test_a_box_that_ends_without_its_deliverable_fails_and_waits_at_a_gate(rig: Rig) -> None:
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session)

        failed = await until(lambda: question(rig, "Write the plan failed"))
        assert "it ended without writing PLAN.md" in failed.title
        assert {option.id for option in failed.options} == {"retry", "take", "skip", "stop"}
        assert rig.run().box("plan").state == "failed"
        await anyio.sleep(0.2)
        assert rig.bridge.prompted("try 2") is None, "a failed box waits for the owner"
        rig.kernel.questions.answer(failed.id, by=OWNER, option="retry", text="Write PLAN.md this time.")

        again = await until(lambda: rig.bridge.prompted("Study · plan · try 2"))
        assert "Try 1 failed: it ended without writing PLAN.md." in again.text
        assert "Write PLAN.md this time." in again.text


async def test_a_deliverable_left_from_before_does_not_count(rig: Rig) -> None:
    rig.write("PLAN.md", "# A plan from yesterday\n")
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session)
        failed = await until(lambda: question(rig, "Write the plan failed"))
        assert "PLAN.md is left from before: it was not written during this try" in failed.title


async def test_skipping_a_failed_box_goes_on_and_stopping_ends_the_run(rig: Rig) -> None:
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session)
        failed = await until(lambda: question(rig, "Write the plan failed"))
        rig.kernel.questions.answer(failed.id, by=OWNER, option="skip")
        gate = await until(lambda: question(rig, "You approve the plan"))
        assert rig.run().box("plan").state == "skipped"
        rig.kernel.questions.answer(gate.id, by=OWNER, option="stop")
        await until(lambda: rig.run().status == "stopped")
    [ended] = rig.events("flows.run_ended")
    assert (ended.data["outcome"], ended.actor) == ("stopped", OWNER)
    assert rig.bridge.prompted("T1") is None


async def test_a_brief_not_written_yet_is_asked_for_again_saying_which_file_is_missing(rig: Rig) -> None:
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        asked = await until(lambda: question(rig, "Brief"))
        rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
        again = await until(lambda: next((each for each in rig.waiting() if each.id != asked.id), None))
        assert "BRIEF.md is not in the folder yet" in again.detail
        rig.write("BRIEF.md", "The brief.\n")
        rig.kernel.questions.answer(again.id, by=OWNER, option="done")
        await until(lambda: rig.bridge.prompted("Study · plan · try 1"))


async def test_a_box_whose_when_done_waits_asks_before_the_next_starts(rig: Rig) -> None:
    flow = study()
    flow["boxes"][3]["when_done"] = "wait"
    flow["boxes"].append({"id": "T2", "type": "task", "title": "The sweep", "writes": ["sweep.py"]})
    flow["lines"].append({"from": "T1", "to": "T2"})
    rig.write_flow(flow)
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        rig.kernel.questions.answer((await until(lambda: question(rig, "You approve"))).id, by=OWNER, option="approve")
        task = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
        rig.bridge.finish(task.session, {"grid.json": "[]\n"})
        wait = await until(lambda: question(rig, "The grid is done"))
        await anyio.sleep(0.2)
        assert rig.bridge.prompted("T2") is None
        rig.kernel.questions.answer(wait.id, by=OWNER, option="go")
        await until(lambda: rig.bridge.prompted("Study · T2 · try 1"))


async def test_an_idle_heard_before_the_sessions_answer_began_does_not_end_the_box(rig: Rig) -> None:
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.status(plan.session, "idle")  # said for the new session before its run began
        await anyio.sleep(0.2)
        assert rig.run().box("plan").state == "running", "it goes on"
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        await until(lambda: question(rig, "You approve the plan"))


async def test_a_box_whose_session_ended_while_its_watcher_started_again_ends_once_the_watcher_is_back(
    rig: Rig,
) -> None:
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        await until(lambda: rig.run().box("plan").tries[-1].sent)  # the runner knows its first message went
        rig.write("PLAN.md", "# The plan\n")
        rig.bridge.servers[plan.port].sessions[plan.session]["status"] = "idle"  # it ended, and no watcher heard it
        rig.bridge.say({"type": "started"})  # the watcher started again
        rig.bridge.say({"type": "synced", "ports": [plan.port]})
        await until(lambda: question(rig, "You approve the plan"))
    assert rig.run().box("plan").state == "done"


async def test_the_flows_next_run_uses_the_server_its_last_run_started(rig: Rig) -> None:
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        rig.kernel.questions.answer((await until(lambda: question(rig, "You approve"))).id, by=OWNER, option="approve")
        task = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
        rig.bridge.finish(task.session, {"grid.json": "[]\n"})
        await until(lambda: rig.run().status == "done")

        rig.runner.start(FLOW, actor=OWNER)
        rig.kernel.questions.answer((await until(lambda: question(rig, "Brief"))).id, by=OWNER, option="done")
        await until(lambda: len(rig.bridge.prompts) == 3)
    assert rig.run(2).box("plan").tries[0].port == plan.port
    assert len(rig.bridge.done("serve")) == 1, "one server for the flow's runs"


async def test_a_gate_says_which_try_the_box_it_sends_back_to_runs_and_when_it_is_past_its_tries(rig: Rig) -> None:
    flow = study()
    flow["boxes"][1]["tries"] = 2
    rig.write_flow(flow)
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        first = await until(lambda: question(rig, "You approve the plan"))
        [back] = [option for option in first.options if option.id == "back"]
        assert back.effect.startswith("plan runs try 2 of 2, its last, with your note;")
        rig.kernel.questions.answer(first.id, by=OWNER, option="back", text="Fewer points.")

        again = await until(lambda: rig.bridge.prompted("Study · plan · try 2"))
        rig.bridge.finish(again.session, {"PLAN.md": "# The plan, fewer points\n"})
        second = await until(lambda: next((each for each in rig.waiting() if each.id != first.id), None))
        [back] = [option for option in second.options if option.id == "back"]
        assert back.effect.startswith("plan runs try 3, past its 2 tries, with your note;")
