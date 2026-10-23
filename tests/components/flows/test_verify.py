"""Design 0013 §2, §8 and §9: a VERIFY ends by calling `flow_verdict`, which the service gives to the VERIFY box at work
in the workspace: *pass*, or *fail* with numbered findings, and `criteria`, each line of the brief's limits and of what
done means that the check touched, met or not, with its evidence. The verdict is kept on the VERIFY's try and as
`verdict.md` in the try's folder; a pass goes on along the VERIFY's pass line; a VERIFY that ends without a verdict is
reminded once in its session, then is a failed box, never a pass, and waits at a gate. A verdict is refused, saying
why, while no VERIFY works in the workspace, before its try began or after it ended, and a fail without findings is
refused, as is a criterion not as `flow_verdict` takes it, naming the criterion and its field; the newest verdict of a
try counts, and each is an event with its actor. Run against the fake bridge and a synthetic folder."""

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank.components.flows.runner import RunError
from clank.components.flows.verdicts import AGENT, Criterion
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
    running,
    until,
)

pytestmark = pytest.mark.anyio
SIXTY = Criterion(line="about 60 grid points", met=True, evidence="PLAN.md's grid: 8 x 8 = 64 points")
BUDGET = Criterion(line="at most 48 CPU-hours", met=True, evidence="PLAN.md's estimate: 41.5 CPU-hours")


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, checked_study())
    yield made
    made.kernel.close()


async def to_the_check(rig: Rig) -> Any:
    """The run started, its brief done, its plan written; the check's first message sent."""
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "About 60 grid points, at most 48 CPU-hours.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
    rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n\nAn 8 x 8 grid, 41.5 CPU-hours.\n"})
    return await at_work(rig, "check")


async def test_a_verifys_pass_is_kept_on_its_try_and_as_its_verdict_file_and_the_flow_goes_on_along_its_pass_line(
    rig: Rig,
) -> None:
    async with running(rig.kernel):
        check = await to_the_check(rig)
        assert check.agent == "planner", "a VERIFY runs in Plan mode by default"
        assert "flow_verdict" in check.text
        said = rig.runner.verdict(WORKSPACE, "pass", [], [SIXTY, BUDGET], actor=AGENT)
        assert said["result"] == "pass"
        assert "plan's try 1" in said["said"]
        rig.bridge.finish(check.session)
        await until(lambda: question(rig, "You approve the plan"))

    state = rig.run().box("check")
    assert state.state == "done"
    [attempt] = state.tries
    assert attempt.outcome == "done"
    assert attempt.verdict is not None
    assert (attempt.verdict.result, attempt.verdict.criteria, attempt.verdict.by) == ("pass", [SIXTY, BUDGET], AGENT)
    kept = rig.runner.runs.try_folder(rig.run(), "check", 1) / "verdict.md"
    text = kept.read_text(encoding="utf-8")
    assert text.startswith("# Verdict: pass\n")
    assert "- met: about 60 grid points: PLAN.md's grid: 8 x 8 = 64 points" in text


def sent_to(rig: Rig, session: str) -> list[str]:
    return [each.text for each in rig.bridge.prompts if each.session == session]


async def test_a_verify_that_ends_without_a_verdict_is_reminded_once_then_fails_and_waits_at_a_gate(rig: Rig) -> None:
    """A local model wrote its verdict as text and ended (2026-10-23): it is reminded once, in the same session, to
    give it with `flow_verdict`; still none, the try fails."""
    async with running(rig.kernel):
        check = await to_the_check(rig)
        rig.bridge.finish(check.session)
        await until(lambda: len(sent_to(rig, check.session)) == 2)
        assert "flow_verdict" in sent_to(rig, check.session)[-1]
        assert rig.run().box("check").tries[-1].outcome is None, "not failed before its reminder"
        rig.bridge.finish(check.session)
        failed = await until(lambda: question(rig, "Check the plan failed"))
        assert "it ended without a verdict" in failed.title
        assert {option.id for option in failed.options} == {"retry", "take", "skip", "stop"}
        await anyio.sleep(0.2)
        assert question(rig, "You approve the plan") is None, "never taken for a pass"
    assert rig.run().box("check").state == "failed"


async def test_a_verify_reminded_that_then_gives_its_verdict_goes_on_along_its_pass_line(rig: Rig) -> None:
    async with running(rig.kernel):
        check = await to_the_check(rig)
        rig.bridge.finish(check.session)
        await until(lambda: len(sent_to(rig, check.session)) == 2)
        rig.runner.verdict(WORKSPACE, "pass", [], [SIXTY], actor=AGENT)
        rig.bridge.finish(check.session)
        await until(lambda: question(rig, "You approve the plan"))
    assert rig.run().box("check").state == "done"


async def test_a_verdict_while_no_verify_works_in_the_workspace_or_after_its_try_ended_is_refused_saying_why(
    rig: Rig,
) -> None:
    with pytest.raises(RunError, match="no box of a flow works in myproject now"):
        rig.runner.verdict(WORKSPACE, "pass", [], [], actor=AGENT)
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        asked = await until(lambda: question(rig, "Brief"))
        rig.write("BRIEF.md", "The brief.\n")
        rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        with pytest.raises(RunError, match="plan works now, and it is a PLAN: only a VERIFY gives a verdict"):
            rig.runner.verdict(WORKSPACE, "pass", [], [], actor=AGENT)
        with pytest.raises(RunError, match="no box of a flow works in elsewhere now"):
            rig.runner.verdict("elsewhere", "pass", [], [], actor=AGENT)
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        check = await until(lambda: rig.bridge.prompted("Study · check · try 1"))
        rig.bridge.finish(check.session)
        await until(lambda: len(sent_to(rig, check.session)) == 2)  # reminded once
        rig.bridge.finish(check.session)
        await until(lambda: question(rig, "Check the plan failed"))
        with pytest.raises(RunError, match="no box of a flow works in myproject now"):
            rig.runner.verdict(WORKSPACE, "pass", [], [], actor=AGENT)
    assert rig.run().box("check").tries[-1].verdict is None


async def test_a_fail_without_findings_or_a_result_but_pass_or_fail_is_refused_saying_what_to_fix(rig: Rig) -> None:
    async with running(rig.kernel):
        await to_the_check(rig)
        with pytest.raises(RunError, match="a fail lists its findings, each one thing to fix"):
            rig.runner.verdict(WORKSPACE, "fail", ["  "], [], actor=AGENT)
        with pytest.raises(RunError, match="a verdict is pass or fail, not 'passed'"):
            rig.runner.verdict(WORKSPACE, "passed", [], [], actor=AGENT)
        with pytest.raises(RunError, match="criterion 1 names no line"):
            rig.runner.verdict(WORKSPACE, "pass", [], [Criterion(line=" ", met=True)], actor=AGENT)
    assert rig.run().box("check").tries[-1].verdict is None


async def test_a_criterion_not_as_flow_verdict_takes_it_is_refused_naming_the_criterion_and_its_field(
    rig: Rig,
) -> None:
    sixty = SIXTY.model_dump()
    async with running(rig.kernel):
        await to_the_check(rig)
        with pytest.raises(RunError, match="criterion 1 has file, which a criterion does not take: give its line, met"):
            rig.runner.verdict(WORKSPACE, "pass", [], [{**sixty, "file": "PLAN.md"}], actor=AGENT)
        with pytest.raises(RunError, match="criterion 2's met is 'perhaps': say true or false"):
            rig.runner.verdict(WORKSPACE, "pass", [], [sixty, {**sixty, "met": "perhaps"}], actor=AGENT)
        with pytest.raises(RunError, match="criterion 1 does not say whether it is met: say true or false"):
            rig.runner.verdict(WORKSPACE, "pass", [], [{"line": "about 60 grid points"}], actor=AGENT)
        with pytest.raises(RunError, match="criterion 1 is not an object: give each as its line, met and evidence"):
            rig.runner.verdict(WORKSPACE, "pass", [], ["about 60 grid points"], actor=AGENT)
        with pytest.raises(RunError, match="criterion 1 names no line"):
            rig.runner.verdict(WORKSPACE, "pass", [], [{"met": True}], actor=AGENT)
        assert rig.run().box("check").tries[-1].verdict is None
        budget = {"line": "at most 48 CPU-hours", "met": "Not met", "evidence": 61.5}
        rig.runner.verdict(WORKSPACE, "pass", [], [budget, {**sixty, "met": "yes"}], actor=AGENT)
    verdict = rig.run().box("check").tries[-1].verdict
    assert verdict is not None
    assert verdict.criteria == [Criterion(line="at most 48 CPU-hours", met=False, evidence="61.5"), SIXTY], (
        "met said in words read as such, evidence as text"
    )


async def test_a_verdict_before_the_verifys_first_message_was_sent_is_refused_and_nothing_is_kept(rig: Rig) -> None:
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        asked = await until(lambda: question(rig, "Brief"))
        rig.write("BRIEF.md", "About 60 grid points.\n")
        rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.hold["prompt"] = threading.Event()  # the check's first message, held while it is being sent
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        await until(lambda: len(rig.bridge.done("prompt")) == 2)
        assert rig.run().box("check").tries[-1].sent is None
        with pytest.raises(RunError, match="check's try has not begun, or has ended: no verdict is kept for it"):
            rig.runner.verdict(WORKSPACE, "pass", [], [SIXTY], actor=AGENT)
        rig.bridge.hold["prompt"].set()
        await until(lambda: rig.bridge.prompted("Study · check · try 1"))
    assert rig.run().box("check").tries[-1].verdict is None


async def test_the_newest_verdict_of_a_try_counts_and_each_is_an_event_with_its_actor(rig: Rig) -> None:
    async with running(rig.kernel):
        check = await to_the_check(rig)
        rig.runner.verdict(WORKSPACE, "fail", ["No CPU-hour budget."], [], actor=AGENT)
        rig.runner.verdict(WORKSPACE, "pass", [], [BUDGET], actor=AGENT)
        rig.bridge.finish(check.session)
        await until(lambda: question(rig, "You approve the plan"))
    verdicts = rig.events("flows.verdict")
    assert [(event.data["result"], event.data["findings"], event.actor) for event in verdicts] == [
        ("fail", 1, AGENT),
        ("pass", 0, AGENT),
    ]
    assert verdicts[0].data["box"] == "check"
    assert verdicts[0].data["checks"] == "plan"
    assert "No CPU-hour budget" not in verdicts[0].summary, "no event holds a verdict's words"
    assert rig.run().box("check").state == "done"
