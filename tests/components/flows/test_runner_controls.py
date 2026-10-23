"""Design 0013 §4, §5 and §6 (decisions 0059 and 0061): a box over its time limit, or past the tokens it may write, has
its session stopped and fails; a box whose session ended while its watcher said nothing is found ended by the runner's
own look at its status; a box in Auto has its session's changes accepted while the workspace stays in Review; and
the owner's controls: pause lets the running box finish and starts no other until the run goes on; stop stops the
running box's session and ends the run; run from here runs the box and every box after it again, as new tries, each
first message saying why it runs again; and a second flow's run waits behind the first. A nudge of the runner from
another thread never waits for the event loop (§6: the runner runs in the service, which nothing may hang). Run against
the fake bridge and a synthetic folder."""

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank.components.flows import runner as runner_module
from clank.components.flows.runner import RunError
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import FLOW, OWNER, Rig, make_rig, question, running, study, until

pytestmark = pytest.mark.anyio


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, study())
    yield made
    made.kernel.close()


async def to_the_plan(rig: Rig) -> Any:
    """The run started, its brief done; the plan's first message sent."""
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "The brief.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    return await until(lambda: rig.bridge.prompted("Study · plan · try 1"))


async def test_a_box_over_its_time_limit_has_its_session_stopped_and_fails(rig: Rig) -> None:
    flow = study()
    flow["boxes"][1]["limits"] = {"minutes": 1}
    rig.write_flow(flow)
    async with running(rig.kernel):
        plan = await to_the_plan(rig)
        await anyio.sleep(0.1)
        assert rig.bridge.done("abort") == []
        rig.clock.advance(61)
        failed = await until(lambda: question(rig, "Write the plan failed"))
        assert "it ran past its limit of 1 minute: Clank stopped its session" in failed.title
        assert rig.bridge.done("abort") == [[str(plan.port), plan.session]]


async def test_a_box_past_the_tokens_it_may_write_has_its_session_stopped_and_fails(rig: Rig) -> None:
    flow = study(defaults={"limits": {"tokens": 1000}})
    rig.write_flow(flow)
    async with running(rig.kernel):
        plan = await to_the_plan(rig)
        rig.bridge.step(plan.session, 600)
        await anyio.sleep(0.1)
        assert rig.bridge.done("abort") == []
        rig.bridge.step(plan.session, 300, reasoning=200)
        failed = await until(lambda: question(rig, "Write the plan failed"))
        assert "it wrote 1,100 tokens, past its limit of 1,000: Clank stopped its session" in failed.title
        assert rig.bridge.done("abort") == [[str(plan.port), plan.session]]
    attempt = rig.run().box("plan").tries[0]
    assert (attempt.outcome, attempt.tokens) == ("failed", 1100)


async def test_a_box_that_ended_unheard_is_found_ended_by_the_runners_own_look(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Its watcher said nothing (OpenCode's stream went silent, 2026-10-22: the PLAN ended after 25 minutes and the run
    waited for its limit of 30); the runner reads the session's status itself now and then, and goes on."""
    monkeypatch.setattr(runner_module, "LOOK", 0.2)
    async with running(rig.kernel):
        plan = await to_the_plan(rig)
        rig.bridge.finish_unheard(plan.session, {"PLAN.md": "The plan.\n"})
        await until(lambda: rig.run().box("plan").tries[0].outcome == "done", seconds=5)
    assert rig.bridge.done("abort") == [], "its session ended on its own: nothing stopped it"


async def test_a_box_in_auto_has_its_changes_accepted_while_the_workspace_stays_in_review(rig: Rig) -> None:
    flow = study()
    flow["boxes"][3]["mode"] = "auto"
    rig.write_flow(flow)
    rig.write("grid.py", "x = 1\n")
    async with running(rig.kernel):
        plan = await to_the_plan(rig)
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        rig.kernel.questions.answer((await until(lambda: question(rig, "You approve"))).id, by=OWNER, option="approve")
        task = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
        assert task.agent == "build"
        for session, id in ((task.session, "per_box"), ("ses_window", "per_window")):
            rig.bridge.say({
                "type": "asked", "port": task.port,
                "input": {"filePath": "/workspace/grid.py", "oldString": "x = 1", "newString": "x = 2"},
                "request": {"id": id, "sessionID": session, "permission": "edit", "patterns": ["grid.py"],
                            "metadata": {"filepath": "/workspace/grid.py", "diff": "-x = 1\n+x = 2\n"}},
            })  # fmt: skip
        assert rig.bridge.done("permission") == [[str(task.port), "per_box", "once"]]
        [waiting] = rig.waiting()
        assert "grid.py" in waiting.title, "the owner's own session's change waits for review"
        assert rig.kernel.parts["agents"].review.mode("myproject") == "review"
        rig.bridge.finish(task.session, {"grid.json": "[]\n"})
        await until(lambda: rig.run().status == "done")
        rig.bridge.say({
            "type": "asked", "port": task.port, "input": None,
            "request": {"id": "per_after", "sessionID": task.session, "permission": "edit", "patterns": ["grid.py"],
                        "metadata": {"filepath": "/workspace/grid.py", "diff": "-x = 1\n+x = 3\n"}},
        })  # fmt: skip
        assert len(rig.waiting()) == 2, "once the box ended, its session's mode is the workspace's again"


async def test_pause_lets_the_running_box_finish_and_starts_no_other_until_the_run_goes_on(rig: Rig) -> None:
    async with running(rig.kernel):
        plan = await to_the_plan(rig)
        rig.runner.pause(FLOW, actor=OWNER)
        assert rig.bridge.done("abort") == [], "the running box goes on"
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        await until(lambda: rig.run().box("plan").state == "done")
        await anyio.sleep(0.2)
        assert question(rig, "You approve") is None, "nothing starts while it is paused"
        assert rig.run().paused
        rig.runner.resume(FLOW, actor=OWNER)
        await until(lambda: question(rig, "You approve"))
    steered = [event.data["action"] for event in rig.events("flows.run_steered")]
    assert steered == ["pause", "resume"]


async def test_stop_stops_the_running_boxs_session_and_ends_the_run(rig: Rig) -> None:
    async with running(rig.kernel):
        plan = await to_the_plan(rig)
        rig.runner.stop(FLOW, actor=OWNER)
        await until(lambda: rig.run().box("plan").state == "failed")
        assert rig.bridge.done("abort") == [[str(plan.port), plan.session]]
        assert rig.run().status == "stopped"
        await anyio.sleep(0.1)
        assert rig.waiting() == [], "a stopped run asks nothing"
    attempt = rig.run().box("plan").tries[0]
    assert (attempt.outcome, attempt.reason) == ("stopped", "stopped by you (console)")
    [ended] = rig.events("flows.run_ended")
    assert (ended.data["outcome"], ended.actor) == ("stopped", OWNER)
    stopped = [event for event in rig.events("flows.box_ended") if event.data["box"] == "plan"]
    assert [(event.data["outcome"], event.actor) for event in stopped] == [("stopped", OWNER)]


async def test_run_from_here_runs_the_box_and_every_box_after_it_again_as_new_tries(rig: Rig) -> None:
    async with running(rig.kernel):
        plan = await to_the_plan(rig)
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        rig.kernel.questions.answer((await until(lambda: question(rig, "You approve"))).id, by=OWNER, option="approve")
        task = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
        rig.bridge.finish(task.session, {"grid.json": "[]\n"})
        await until(lambda: rig.run().status == "done")

        rig.runner.run_from(FLOW, "plan", actor=OWNER)
        again = await until(lambda: rig.bridge.prompted("Study · plan · try 2"))
        assert "This is try 2. Try 1 was done; the user ran the flow again from this box." in again.text
        assert "sent back" not in again.text, "nothing was sent back"
        assert {box: rig.run().box(box).state for box in ("brief", "approve", "T1")} == {
            "brief": "done", "approve": "waiting", "T1": "waiting"
        }  # fmt: skip
        rig.bridge.finish(again.session, {"PLAN.md": "# The plan, again\n"})
        rig.kernel.questions.answer((await until(lambda: question(rig, "You approve"))).id, by=OWNER, option="approve")
        task = await until(lambda: rig.bridge.prompted("Study · T1 · try 2"))
        assert "Try 1 was done; the user ran the flow again from plan, a box before this one." in task.text
    assert rig.run().number == 1, "the same run, its boxes' next tries"
    with pytest.raises(RunError, match="has no box nowhere"):
        rig.runner.run_from(FLOW, "nowhere", actor=OWNER)


async def test_a_second_flows_run_waits_behind_the_first_and_begins_when_it_ends(rig: Rig) -> None:
    rig.write_flow(study(title="Another"), name="another")
    async with running(rig.kernel):
        await to_the_plan(rig)
        second = rig.runner.start("myproject/another", actor=OWNER)
        assert (second.status, second.behind) == ("queued", "myproject/study#1")
        await anyio.sleep(0.2)
        assert question(rig, "Another") is None, "it waits"
        with pytest.raises(RunError, match="already runs"):
            rig.runner.start(FLOW, actor=OWNER)
        rig.runner.stop(FLOW, actor=OWNER)
        await until(lambda: question(rig, "Another: Brief"))
        assert rig.run(1, "myproject/another").status == "running"


async def test_a_run_stopped_while_its_box_is_starting_starts_no_session(rig: Rig) -> None:
    held = threading.Event()
    rig.bridge.hold["serve"] = held
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        asked = await until(lambda: question(rig, "Brief"))
        rig.write("BRIEF.md", "The brief.\n")
        rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
        await until(lambda: rig.bridge.done("serve"))
        rig.runner.stop(FLOW, actor=OWNER)
        held.set()
        await until(lambda: rig.run().box("plan").state == "failed")
    assert rig.bridge.done("new") == [], "no session started for a stopped run"
    attempt = rig.run().box("plan").tries[0]
    assert (attempt.outcome, attempt.reason) == ("stopped", "stopped by you (console) before its session started")
    assert rig.run().operation == ""


async def test_a_nudge_from_another_thread_returns_at_once_while_the_event_loop_is_busy(rig: Rig) -> None:
    """A flow written from another thread (auto-accept, your edit through the API) tells the runner while the settings'
    lock is held, and the driver may wait for that lock on the event loop: a nudge that waited for the loop would hang
    both."""
    free = threading.Event()
    took: list[float] = []

    def nudge() -> None:
        began = time.monotonic()
        rig.runner.nudge()
        took.append(time.monotonic() - began)
        free.set()

    async with running(rig.kernel):
        await anyio.sleep(0.05)  # the driver runs
        threading.Thread(target=nudge, daemon=True).start()
        free.wait(timeout=3)  # the event loop busy, as when it waits for the settings' lock
    assert took, "the nudge never returned"
    assert took[0] < 1, f"the nudge waited {took[0]:.1f} s for the event loop"
