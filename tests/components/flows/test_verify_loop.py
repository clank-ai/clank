"""Design 0013 §3, §5 and §10 (decision 0057): a VERIFY's fail line leads back to the box it checks, which runs its next
try handed the findings, and every box after it up to the VERIFY runs again; the VERIFY's own next try is handed its
last findings, to check how each was answered. The box runs again only while it has tries: when they are used up, the
fail goes to a gate instead, so the third fail of a box with three tries never brings a fourth. That gate offers *one
more try* (past the cap, with the owner's note), *take it as it is* (the flow goes on along the pass line, the box's
files as the owner left them at the gate), *skip the check* and *stop*. The driver takes the fail line from the run's
file alone, so a restart between the VERIFY's end and the loop taken goes on the same way. Run against the fake bridge
and a synthetic folder."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank.components.flows.deliverables import fingerprint
from clank.components.flows.verdicts import AGENT
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import (
    FLOW,
    OWNER,
    WORKSPACE,
    Rig,
    at_work,
    checked_study,
    make_rig,
    question,
    restart,
    running,
    until,
)

pytestmark = pytest.mark.anyio
FINDINGS = [
    "No CPU-hour budget.",
    "Seeds not fixed.",
    "240 grid points where the brief allows about 60.",
]


def rigged(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tries: int | None) -> Rig:
    return make_rig(home, clock, tmp_path, monkeypatch, checked_study(tries))


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = rigged(home, clock, tmp_path, monkeypatch, None)
    yield made
    made.kernel.close()


@pytest.fixture
def once(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    """The rig, its plan given one try."""
    made = rigged(home, clock, tmp_path, monkeypatch, 1)
    yield made
    made.kernel.close()


async def to_the_plan(rig: Rig) -> Any:
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "About 60 grid points, at most 48 CPU-hours.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    return await until(lambda: rig.bridge.prompted("Study · plan · try 1"))


async def plan_then_fail(rig: Rig, number: int) -> Any:
    """The plan's try `number` writes PLAN.md; the check's try `number` fails it with the findings; the check's
    session."""
    plan = await until(lambda: rig.bridge.prompted(f"Study · plan · try {number}"))
    rig.bridge.finish(plan.session, {"PLAN.md": f"# The plan, try {number}\n\n240 grid points.\n"})
    check = await at_work(rig, "check", number)
    rig.runner.verdict(WORKSPACE, "fail", FINDINGS, [], actor=AGENT)
    rig.bridge.finish(check.session)
    return check


async def test_a_fail_hands_the_checked_boxs_next_try_the_findings_and_the_verifys_next_try_its_own(rig: Rig) -> None:
    async with running(rig.kernel):
        await to_the_plan(rig)
        await plan_then_fail(rig, 1)

        again = await until(lambda: rig.bridge.prompted("Study · plan · try 2"))
        assert "This is try 2. Try 1 was done; Check the plan (check) found it wrong" in again.text
        assert "1. No CPU-hour budget.\n2. Seeds not fixed.\n3. 240 grid points where the brief allows about 60." in (
            again.text
        )
        assert rig.run().box("check").state == "waiting", "the check runs again after it"
        rig.bridge.finish(again.session, {"PLAN.md": "# The plan, try 2\n\n64 grid points, 41.5 CPU-hours.\n"})

        check = await at_work(rig, "check", 2)
        assert "you found plan's try 1 wrong, and plan has run its try 2 since" in check.text
        assert "1. No CPU-hour budget." in check.text, "its own findings, to check how each was answered"
        assert "Write the study plan for the brief." not in check.text, "never the checked box's prompt or session"
        rig.runner.verdict(WORKSPACE, "pass", [], [], actor=AGENT)
        rig.bridge.finish(check.session)
        await until(lambda: question(rig, "You approve the plan"))

    run = rig.run()
    assert [len(run.box(name).tries) for name in ("plan", "check")] == [2, 2]
    first = run.box("check").tries[0]
    assert first.outcome == "done"
    assert first.verdict is not None
    assert (first.verdict.result, first.verdict.findings, first.verdict.checked) == ("fail", FINDINGS, 1)
    ended = [event for event in rig.events("flows.box_ended") if event.data["box"] == "check"]
    assert ended[0].summary == (
        "Check the plan found plan's try 1 wrong, with 3 findings: back to plan, for its try 2 of 3"
    )


async def test_the_third_fail_goes_to_a_gate_never_to_a_fourth_try(rig: Rig) -> None:
    async with running(rig.kernel):
        await to_the_plan(rig)
        for number in (1, 2, 3):
            await plan_then_fail(rig, number)
        gate = await until(lambda: question(rig, "Check the plan"))
        await anyio.sleep(0.2)
        assert rig.bridge.prompted("Study · plan · try 4") is None, "never a fourth try on its own"
    assert gate.title == "Study: Check the plan: plan used its 3 tries, and the check still fails"
    assert "1. No CPU-hour budget." in gate.detail
    labels = {option.id: option.label for option in gate.options}
    assert labels == {
        "retry": "One more try (plan's try 4, past its 3)",
        "take": "Take plan as it is",
        "skip": "Skip the check",
        "stop": "Stop the flow",
    }
    assert rig.run().box("check").state == "failed"
    assert len(rig.run().box("plan").tries) == 3


async def test_one_more_try_at_the_loops_gate_runs_the_checked_box_past_its_cap_with_the_owners_note(once: Rig) -> None:
    rig = once
    async with running(rig.kernel):
        await to_the_plan(rig)
        await plan_then_fail(rig, 1)
        gate = await until(lambda: question(rig, "plan used its 1 try"))
        rig.kernel.questions.answer(gate.id, by=OWNER, option="retry", text="Use a coarser grid.")
        again = await until(lambda: rig.bridge.prompted("Study · plan · try 2"))
        assert "Check the plan (check) found it wrong" in again.text
        assert "1. No CPU-hour budget." in again.text
        assert "The user's note: Use a coarser grid." in again.text
        rig.bridge.finish(again.session, {"PLAN.md": "# The plan, coarser\n"})
        check = await at_work(rig, "check", 2)
        rig.runner.verdict(WORKSPACE, "fail", ["Still 240 points."], [], actor=AGENT)
        rig.bridge.finish(check.session)
        second = await until(lambda: question(rig, "plan used 2 tries, past its 1"))
        assert "1. Still 240 points." in second.detail


async def test_take_it_as_it_is_goes_on_along_the_pass_line_with_the_owners_edit_made_at_the_gate(once: Rig) -> None:
    rig = once
    async with running(rig.kernel):
        await to_the_plan(rig)
        await plan_then_fail(rig, 1)
        gate = await until(lambda: question(rig, "plan used its 1 try"))
        rig.write("PLAN.md", "# The plan, as the owner fixed it\n\n64 grid points.\n")
        rig.runner.nudge()
        await anyio.sleep(0.2)
        assert rig.run().box("plan").changed == "", "the owner's to edit while the gate waits"
        rig.kernel.questions.answer(gate.id, by=OWNER, option="take")
        await until(lambda: question(rig, "You approve the plan"))
        await anyio.sleep(0.2)
    run = rig.run()
    assert run.box("check").state == "done"
    assert (run.box("plan").state, run.box("plan").changed) == ("done", "")
    [kept] = run.box("plan").kept
    assert kept.sha256 == fingerprint(rig.folder, "PLAN.md").sha256, "the owner's edit, as it stands"


async def test_skip_the_check_goes_on_and_marks_the_verify_skipped(once: Rig) -> None:
    rig = once
    async with running(rig.kernel):
        await to_the_plan(rig)
        await plan_then_fail(rig, 1)
        gate = await until(lambda: question(rig, "plan used its 1 try"))
        rig.kernel.questions.answer(gate.id, by=OWNER, option="skip")
        await until(lambda: question(rig, "You approve the plan"))
    assert rig.run().box("check").state == "skipped"


async def test_a_restart_between_the_verifys_end_and_the_loop_taken_goes_on_the_same_way(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with running(rig.kernel):
        await to_the_plan(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        check = await at_work(rig, "check")
        monkeypatch.setattr(rig.runner, "nudge", lambda: None)  # the service stops before its driver looks again
        rig.runner.verdict(WORKSPACE, "fail", FINDINGS, [], actor=AGENT)
        rig.bridge.finish(check.session)
        await until(lambda: rig.run().box("check").state == "failed" and not rig.run().operation)
    assert rig.run().at == "check"
    restart(rig)
    async with running(rig.kernel):
        again = await until(lambda: rig.bridge.prompted("Study · plan · try 2"))
    assert "1. No CPU-hour budget." in again.text
