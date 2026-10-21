"""Design 0013 §6 (decision 0061): after a restart of the service, a box's operation is interrupted, then reconciled
through the bridge: a session still working is followed and one that ended meanwhile is collected, neither starting any
session again; one that is gone (its server stopped) fails its box, which waits at a gate. A gate asked before a restart
still waits after it, and its answer lets the flow go on. A run stopped while its box was ending has that box's session
stopped and its try ended after the restart, so it can run again from a box. The tokens a box wrote before a restart
count toward its limit after it. Run against the fake bridge and a synthetic folder; the container and its OpenCode
servers go on while the service restarts."""

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import FLOW, OWNER, Rig, make_rig, question, restart, running, study, until

pytestmark = pytest.mark.anyio


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, study())
    yield made
    made.kernel.close()  # the kernel of its last start


async def to_the_plan(rig: Rig) -> Any:
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "The brief.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    return await until(lambda: rig.bridge.prompted("Study · plan · try 1"))


def boxes(rig: Rig) -> list[tuple[str, str, list[str]]]:
    """The flows.box operations, oldest first: their status, whether they follow a session, and their steps."""
    found = [each for each in rig.kernel.operations.find() if each.type == "flows.box"]
    return [
        (each.status, "follow" if each.params.get("follow") else "", [s.name for s in each.steps])
        for each in reversed(found)
    ]


async def test_a_restart_in_the_middle_of_a_box_follows_the_session_still_working_and_starts_none(rig: Rig) -> None:
    async with running(rig.kernel):
        plan = await to_the_plan(rig)
    again = restart(rig)
    async with running(again.kernel):
        await until(lambda: len(boxes(again)) == 2 and boxes(again)[1][2] == ["work"])
        assert boxes(again)[0][0] == "interrupted"
        [reconciled] = again.events("operation.reconciled")
        assert "still works: the runner follows it" in reconciled.summary
        assert len(again.bridge.done("new")) == 1, "no session started again"
        assert len(again.bridge.prompts) == 1
        again.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        await until(lambda: question(again, "You approve the plan"))
    assert boxes(again)[1] == ("done", "follow", ["work", "collect"])
    assert again.run().box("plan").state == "done"
    assert [attempt.number for attempt in again.run().box("plan").tries] == [1]


async def test_a_session_that_ended_while_the_service_was_down_is_collected(rig: Rig) -> None:
    async with running(rig.kernel):
        plan = await to_the_plan(rig)
    rig.write("PLAN.md", "# The plan\n")
    rig.bridge.servers[plan.port].sessions[plan.session]["status"] = "idle"  # it ended, and no watcher heard it
    again = restart(rig)
    async with running(again.kernel):
        await until(lambda: question(again, "You approve the plan"))
    [reconciled] = again.events("operation.reconciled")
    assert "ended meanwhile: the runner collects it" in reconciled.summary
    assert again.run().box("plan").state == "done"
    assert len(again.bridge.done("new")) == 1


async def test_a_session_gone_with_its_server_fails_its_box_at_a_gate(rig: Rig) -> None:
    async with running(rig.kernel):
        plan = await to_the_plan(rig)
    del rig.bridge.servers[plan.port]  # the container was reopened meanwhile
    again = restart(rig)
    async with running(again.kernel):
        failed = await until(lambda: question(again, "Write the plan failed"))
        assert "its session is gone" in failed.title
        assert len(again.bridge.done("new")) == 1, "no session started again"
        assert boxes(again) == [("interrupted", "", ["model", "server", "session", "work"])]


async def test_a_gate_asked_before_a_restart_still_waits_after_it_and_its_answer_lets_the_flow_go_on(rig: Rig) -> None:
    async with running(rig.kernel):
        plan = await to_the_plan(rig)
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        gate = await until(lambda: question(rig, "You approve the plan"))
    again = restart(rig)
    async with running(again.kernel):
        [waiting] = again.waiting()
        assert waiting.id == gate.id
        again.kernel.questions.answer(gate.id, by=OWNER, option="approve")
        await until(lambda: again.bridge.prompted("Study · T1 · try 1"))


async def test_a_run_stopped_while_its_box_was_ending_is_settled_after_a_restart_and_runs_again_from_a_box(
    rig: Rig,
) -> None:
    held = threading.Event()
    rig.bridge.hold["abort"] = held
    async with running(rig.kernel):
        plan = await to_the_plan(rig)
        rig.runner.stop(FLOW, actor=OWNER)
        await until(lambda: rig.bridge.done("abort"))
        threading.Timer(0.3, held.set).start()  # the session's stop answers once the service is stopping
    assert (rig.run().status, rig.run().box("plan").state) == ("stopped", "running")
    assert rig.run().operation, "the service stopped while the box ended"
    again = restart(rig)
    async with running(again.kernel):
        await until(lambda: again.run().operation == "")
        assert again.bridge.done("abort") == [[str(plan.port), plan.session]] * 2, "its session stopped again"
        attempt = again.run().box("plan").tries[-1]
        assert (attempt.outcome, again.run().box("plan").state) == ("stopped", "failed")
        assert again.run().status == "stopped"
        [reconciled] = again.events("operation.reconciled")
        assert "its run was stopped meanwhile" in reconciled.summary
        again.runner.run_from(FLOW, "plan", actor=OWNER)
        await until(lambda: again.bridge.prompted("Study · plan · try 2"))


async def test_the_tokens_a_box_wrote_before_a_restart_count_toward_its_limit_after_it(rig: Rig) -> None:
    rig.write_flow(study(defaults={"limits": {"tokens": 1000}}))
    async with running(rig.kernel):
        plan = await to_the_plan(rig)
        rig.bridge.step(plan.session, 600)
        await until(lambda: rig.run().box("plan").tries[-1].tokens == 600)
    again = restart(rig)
    async with running(again.kernel):
        await until(lambda: len(boxes(again)) == 2 and boxes(again)[1][2] == ["work"])
        again.bridge.step(plan.session, 500)
        failed = await until(lambda: question(again, "Write the plan failed"))
    assert "it wrote 1,100 tokens, past its limit of 1,000: Clank stopped its session" in failed.title
