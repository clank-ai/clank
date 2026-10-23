"""Design 0013 §17 (decision 0132): while a box waits on its job, the orchestrator has the model. With it on, a
checkpoint of kind `job` starts as the box's turn ends, handed the job's command and its log so far; it decides `wait`,
`side` (one to three side tasks) or `change`. Side tasks run one after another while the job runs, each a session of
its own titled `<flow> · side · <n>`, in Auto mode, writing one note into the corpus (`corpus/<run>-<n>-<slug>.md`),
whose index Clank keeps (`corpus/CORPUS.md`); a task that writes no note fails, saying so. When the job ends, no new
side task starts, the one at work goes on to its end, and the box is told the notes written meanwhile. A side decision
without tasks, with more than three, or past the run's side budget is refused, saying why. Run against the fake bridge
and a synthetic folder."""

import functools
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank.components.flows import jobs
from clank.components.flows import runner as runner_module
from clank.components.flows.orchestrating import ORCHESTRATOR
from clank.components.flows.runner import RunError
from clank.components.flows.verdicts import AGENT
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import FLOW, OWNER, WORKSPACE, Rig, at_work, make_rig, question, running, study, until

pytestmark = pytest.mark.anyio
SEARCH = "python3 anneal.py --seeds 8"
PRIOR = {"title": "Prior bounds", "prompt": "Read papers/ for the best known bounds on the grid.", "reads": ["papers/"]}
NEXT = {"title": "The next fit", "prompt": "Write fit.py for the grid's results, ready to run.", "reads": []}


def decision(choice: str, **more: Any) -> dict[str, Any]:
    return {
        "choice": choice, "why": more.pop("why", "the job runs for a while"), "looping": False, "progressing": True,
        "facts": "The grid's job runs.", "plan": "Wait for its results.", **more,
    }  # fmt: skip


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    flow = study(orchestrator={"on": True})
    flow["boxes"][3]["limits"] = {"minutes": 60}
    monkeypatch.setattr(runner_module, "LOOK", 0.05)
    made = make_rig(home, clock, tmp_path, monkeypatch, flow)
    made.bridge.hold[SEARCH] = threading.Event()
    yield made
    made.bridge.hold[SEARCH].set()
    made.kernel.close()


async def to_the_job(rig: Rig) -> tuple[Any, Any]:
    """The run at T1, which started its job and ended its turn: the grid's session and the job's checkpoint."""
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "About 60 grid points.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    plan = await at_work(rig, "plan")
    rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
    for title, choice in (("Study · orchestrator · 1", "go on"), ("Study · orchestrator · 2", "approve")):
        checkpoint = await until(functools.partial(rig.bridge.prompted, title))
        rig.runner.decide(WORKSPACE, decision(choice), actor=ORCHESTRATOR)
        rig.bridge.finish(checkpoint.session)
    grid = await at_work(rig, "T1")
    rig.runner.job(WORKSPACE, SEARCH, "The annealing seeds", 45, actor=AGENT)
    rig.bridge.finish(grid.session)
    return grid, await until(lambda: rig.bridge.prompted("Study · orchestrator · 3"))


def sent_to(rig: Rig, session: str) -> list[str]:
    return [each.text for each in rig.bridge.prompts if each.session == session]


async def test_a_box_waiting_on_its_job_hands_the_model_to_a_job_checkpoint_whose_wait_lets_it_run(rig: Rig) -> None:
    async with running(rig.kernel):
        grid, checkpoint = await to_the_job(rig)
        for words in ("T1 started a job", "The annealing seeds", SEARCH, "`wait`", "`side`", "`change`"):
            assert words in checkpoint.text, words
        rig.runner.decide(WORKSPACE, decision("wait"), actor=ORCHESTRATOR)
        rig.bridge.finish(checkpoint.session)
        await until(lambda: rig.run().orchestration.working is None)
        rig.bridge.hold[SEARCH].set()
        await until(lambda: len(sent_to(rig, grid.session)) == 2)
    last = rig.run().orchestration.decisions[-1]
    assert (last.kind, last.choice, last.applied) == ("job", "wait", "waited for the job")
    assert rig.bridge.prompted("Study · side") is None


async def test_side_tasks_run_one_after_another_each_writing_its_note_into_the_corpus_and_the_box_is_told(
    rig: Rig,
) -> None:
    async with running(rig.kernel):
        grid, checkpoint = await to_the_job(rig)
        rig.runner.decide(WORKSPACE, decision("side", side=[PRIOR, NEXT]), actor=ORCHESTRATOR)
        rig.bridge.finish(checkpoint.session)
        first = await until(lambda: rig.bridge.prompted("Study · side · 1"))
        assert first.agent == "build", "Auto mode: it writes its note"
        for words in (PRIOR["prompt"], "corpus/1-1-prior-bounds.md", "Write nothing else", "papers/"):
            assert words in first.text, words
        assert rig.bridge.prompted("Study · side · 2") is None, "one after another"
        rig.bridge.finish(first.session, {"corpus/1-1-prior-bounds.md": "The best bound is 5.\n\nFrom paper A.\n"})
        second = await until(lambda: rig.bridge.prompted("Study · side · 2"))
        assert "corpus/1-1-prior-bounds.md: The best bound is 5." in second.text, "the corpus so far"
        rig.bridge.finish(second.session, {"corpus/1-2-the-next-fit.md": "fit.py fits the grid.\n"})
        await until(lambda: rig.run().orchestration.sides[-1].state == "done")
        rig.bridge.hold[SEARCH].set()
        await until(lambda: len(sent_to(rig, grid.session)) == 2)
    told = sent_to(rig, grid.session)[-1]
    assert "corpus/1-1-prior-bounds.md: The best bound is 5." in told
    assert "corpus/1-2-the-next-fit.md: fit.py fits the grid." in told
    index = (rig.folder / "corpus" / "CORPUS.md").read_text(encoding="utf-8")
    assert "corpus/1-1-prior-bounds.md: The best bound is 5." in index
    assert "corpus/1-2-the-next-fit.md: fit.py fits the grid." in index
    assert [each.state for each in rig.run().orchestration.sides] == ["done", "done"]


async def test_the_job_ending_while_a_side_task_works_starts_no_other_and_the_box_waits_for_it(rig: Rig) -> None:
    async with running(rig.kernel):
        grid, checkpoint = await to_the_job(rig)
        rig.runner.decide(WORKSPACE, decision("side", side=[PRIOR, NEXT]), actor=ORCHESTRATOR)
        rig.bridge.finish(checkpoint.session)
        first = await until(lambda: rig.bridge.prompted("Study · side · 1"))
        rig.bridge.hold[SEARCH].set()
        await until(lambda: (rig.folder / jobs.folder_of(FLOW, 1, "T1", 1) / "exit").exists())
        await anyio.sleep(0.2)
        assert len(sent_to(rig, grid.session)) == 1, "the side task at work goes on to its end first"
        rig.bridge.finish(first.session, {"corpus/1-1-prior-bounds.md": "The best bound is 5.\n"})
        await until(lambda: len(sent_to(rig, grid.session)) == 2)
    assert rig.bridge.prompted("Study · side · 2") is None
    assert [each.state for each in rig.run().orchestration.sides] == ["done", "dropped"]


async def test_a_side_task_that_writes_no_note_fails_saying_so(rig: Rig) -> None:
    async with running(rig.kernel):
        _, checkpoint = await to_the_job(rig)
        rig.runner.decide(WORKSPACE, decision("side", side=[PRIOR]), actor=ORCHESTRATOR)
        rig.bridge.finish(checkpoint.session)
        first = await until(lambda: rig.bridge.prompted("Study · side · 1"))
        rig.bridge.finish(first.session)
        await until(lambda: rig.run().orchestration.sides[-1].state == "failed")
    assert "wrote no note" in rig.run().orchestration.sides[-1].reason


async def test_a_side_decision_without_tasks_past_three_or_without_a_prompt_is_refused(rig: Rig) -> None:
    async with running(rig.kernel):
        await to_the_job(rig)
        for side, words in (([], "one to three side tasks"), ([PRIOR] * 4, "one to three side tasks"),
                            ([{"title": "No prompt"}], "a side task's prompt")):  # fmt: skip
            with pytest.raises(RunError, match=words):
                rig.runner.decide(WORKSPACE, decision("side", side=side), actor=ORCHESTRATOR)


async def test_past_the_runs_side_budget_a_job_checkpoint_may_only_wait_or_change(
    home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    flow = study(orchestrator={"on": True, "side": {"budget": 0}})
    flow["boxes"][3]["limits"] = {"minutes": 60}
    rig = make_rig(home, clock, tmp_path, monkeypatch, flow)
    rig.bridge.hold[SEARCH] = threading.Event()
    try:
        async with running(rig.kernel):
            _, checkpoint = await to_the_job(rig)
            assert "one of: wait, change; then stop" in checkpoint.text
            assert "The run's side work is spent" in checkpoint.text
            with pytest.raises(RunError, match="choose one of: wait, change"):
                rig.runner.decide(WORKSPACE, decision("side", side=[PRIOR]), actor=ORCHESTRATOR)
            rig.bridge.hold[SEARCH].set()
    finally:
        rig.kernel.close()
