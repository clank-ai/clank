"""Design 0013 §2, §5 and §8 (decision 0086): a PLAN, a TASK and an INTEGRATE end by writing a short handoff note in
the folder, `.clank/handoff/<flow>/<box>.md`; a note written during its try is copied beside the try as `handoff.md` and
kept on the try, one left from before is not; a box whose deliverable is right is done without its note, its end saying
it left none; `.clank/handoff/` is kept out of git. Every later box but a VERIFY is handed the notes of the boxes before
it, in order: a VERIFY's verdict and a DECOMPOSE's summary stand for theirs. Run against the fake bridge and a
synthetic folder."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from clank.components.flows.verdicts import AGENT
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows import rig as rigs
from tests.components.flows.rig import FLOW, OWNER, WORKSPACE, Rig, at_work, make_rig, question, running, until

pytestmark = pytest.mark.anyio
NOTE = ".clank/handoff/study/plan.md"


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, rigs.study())
    yield made
    made.kernel.close()


async def brief_done(rig: Rig) -> None:
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "About 60 grid points, at most 48 CPU-hours.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")


async def test_a_note_written_during_its_try_is_copied_beside_it_and_kept_on_the_try(rig: Rig) -> None:
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        assert f"Last, write your handoff note in `{NOTE}`" in plan.text
        note = "Chose 60 points on a log grid.\nOpen: the seeds.\n"
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n", NOTE: note})
        await until(lambda: question(rig, "You approve the plan"))

    attempt = rig.run().box("plan").tries[-1]
    assert attempt.outcome == "done"
    assert attempt.handoff is not None
    assert (attempt.handoff.path, attempt.handoff.size, attempt.handoff.copied) == (NOTE, len(note), True)
    copy = rig.runner.runs.try_folder(rig.run(), "plan", 1) / "handoff.md"
    assert copy.read_bytes().decode("utf-8") == note
    ended = [event for event in rig.events("flows.box_ended") if event.data["box"] == "plan"]
    assert "handoff note" not in ended[-1].summary


async def test_a_box_whose_note_is_missing_or_left_from_before_is_done_and_its_end_says_it_left_none(
    rig: Rig,
) -> None:
    rig.write(NOTE, "An old note, from another run.\n")
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        await until(lambda: question(rig, "You approve the plan"))

    found = rig.run().box("plan")
    assert found.state == "done", "the note is not the deliverable: its box is done without it"
    assert found.tries[-1].handoff is None, "a note left from before does not count"
    assert not (rig.runner.runs.try_folder(rig.run(), "plan", 1) / "handoff.md").exists()
    ended = [event for event in rig.events("flows.box_ended") if event.data["box"] == "plan"]
    assert ended[-1].data["outcome"] == "done"
    assert ended[-1].summary == "Write the plan is done (it left no handoff note)"


async def test_the_handoff_folder_is_kept_out_of_git_once_a_box_that_writes_a_note_starts(rig: Rig) -> None:
    ignore = rig.folder / ".clank" / "handoff" / ".gitignore"
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        assert ignore.read_bytes().decode("utf-8").splitlines()[-1] == "*"
        assert (rig.folder / ".clank" / "handoff" / "study").is_dir(), "its flow's folder, ready for the note"
        rig.write(".clank/handoff/.gitignore", "# the owner's own\n*.md\n")
    assert ignore.read_bytes().decode("utf-8") == "# the owner's own\n*.md\n", "one there already is left as it is"


@pytest.fixture
def checked(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, rigs.checked_study())
    yield made
    made.kernel.close()


async def test_the_boxes_after_are_handed_the_notes_before_them_and_a_verify_none(checked: Rig) -> None:
    rig = checked
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        assert "## Notes from the boxes before you" not in plan.text, "no model box ran before it"
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n", NOTE: "Chose 60 points.\nOpen: the seeds.\n"})

        check = await at_work(rig, "check")
        assert "## Notes from the boxes before you" not in check.text, "a VERIFY is independent of the sessions"
        assert "Chose 60 points." not in check.text
        rig.runner.verdict(WORKSPACE, "pass", ["The seeds could be named in the plan."], [], actor=AGENT)
        rig.bridge.finish(check.session)
        gate = await until(lambda: question(rig, "You approve the plan"))
        rig.kernel.questions.answer(gate.id, by=OWNER, option="approve")

        task = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
    notes = task.text[task.text.index("## Notes from the boxes before you") : task.text.index("## The files you")]
    said = f"### plan (PLAN), try 1: its note, `{NOTE}`\n\n> Chose 60 points.\n> Open: the seeds."
    assert said in notes
    verdict = (
        "### check (VERIFY), try 1: its verdict\n\n> Its verdict on plan's try 1: pass.\n> Remarks:\n"
        "> 1. The seeds could be named in the plan."
    )
    assert verdict in notes
    kept = rig.runner.runs.try_folder(rig.run(), "T1", 1) / "first-message.md"
    assert kept.read_bytes().decode("utf-8") == task.text


@pytest.fixture
def split(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    made = make_rig(home, clock, tmp_path, monkeypatch, rigs.decomposing())
    yield made
    made.kernel.close()


async def test_a_decomposes_summary_is_handed_on_as_its_note_and_a_task_that_left_none_is_said(split: Rig) -> None:
    rig = split
    async with running(rig.kernel):
        rig.runner.start(FLOW, actor=OWNER)
        await brief_done(rig)
        plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
        rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
        decompose = await at_work(rig, "split")
        for number in (1, 2):
            rig.runner.proposing.propose(WORKSPACE, rigs.task(number), actor=AGENT)
        rig.runner.proposing.submit(WORKSPACE, "Two tasks, the grid first.", actor=AGENT)
        rig.bridge.finish(decompose.session)
        asked = await until(lambda: question(rig, "proposed"))
        rig.kernel.questions.answer(asked.id, by=OWNER, option="accept")

        first = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
        rig.bridge.finish(first.session, {"out/t1.md": "Task 1's work.\n"})
        second = await until(lambda: rig.bridge.prompted("Study · T2 · try 1"))
    notes = second.text[
        second.text.index("## Notes from the boxes before you") : second.text.index("## Your deliverable")
    ]
    assert "### plan (PLAN), try 1: no note\n\nIt left no handoff note." in notes
    assert "### split (DECOMPOSE), try 1: its summary when it submitted its tasks\n\n> Two tasks, the grid first." \
        in notes  # fmt: skip
    assert "### T1 (TASK), try 1: no note\n\nIt left no handoff note." in notes
    assert notes.index("### plan") < notes.index("### split") < notes.index("### T1")
