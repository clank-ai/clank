"""Design 0013 §17 (decision 0132): the box at work starts a long computation as a job with `flow_job`, one at a time,
within its box's minutes; Clank starts it in the workspace's container and keeps it on the box's try, and says how its
end comes back. A job asked for while no box works, a second while one runs, or one longer than its box may run is
refused, saying why; the route answers 409 with those words. A box whose turn ends while its job runs waits on it, its
clock stopped: when the job ends (its exit written, Clank ending it past its minutes, or its process gone) the same
session is sent how it ended, its time and its log's last lines, and the box goes on to its end. Stopping the run ends
its job."""

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient

from clank.components.flows import jobs
from clank.components.flows import runner as runner_module
from clank.components.flows.runner import RunError
from clank.components.flows.verdicts import AGENT
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from clank.kernel.processes import Answer
from tests.components.flows.rig import FLOW, OWNER, WORKSPACE, Rig, make_rig, question, running, study, until

pytestmark = pytest.mark.anyio
SEARCH = "python3 anneal.py --seeds 8"


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    flow = study()
    flow["boxes"][3]["limits"] = {"minutes": 60}
    monkeypatch.setattr(runner_module, "LOOK", 0.05)
    made = make_rig(home, clock, tmp_path, monkeypatch, flow)
    yield made
    made.kernel.close()


async def to_the_grid(rig: Rig) -> Any:
    """The run started; its brief, plan and gate done; the grid's first message sent."""
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "The brief.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
    rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
    gate = await until(lambda: question(rig, "You approve the plan"))
    rig.kernel.questions.answer(gate.id, by=OWNER, option="approve")
    grid = await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))
    await until(lambda: rig.run().box("T1").tries and rig.run().box("T1").tries[-1].sent)
    return grid


async def test_the_box_at_work_starts_a_job_kept_on_its_try_and_is_told_to_end_its_turn(rig: Rig) -> None:
    async with running(rig.kernel):
        await to_the_grid(rig)
        said = rig.runner.job(WORKSPACE, SEARCH, "The annealing seeds", 45, actor=AGENT)
        assert rig.bridge.jobs == [SEARCH]
        [job] = rig.run().box("T1").tries[-1].jobs
    folder = jobs.folder_of(FLOW, 1, "T1", 1)
    assert (job.number, job.title, job.command, job.minutes, job.folder) == (
        1,
        "The annealing seeds",
        SEARCH,
        45,
        folder,
    )
    assert job.ended is None
    assert said["job"] == 1
    assert f"{folder}/log" in said["said"]
    assert "End your turn now" in said["said"]
    [started] = rig.events("flows.job")
    assert started.data["action"] == "started"
    assert started.data["box"] == "T1"


async def test_a_second_job_while_one_runs_is_refused(rig: Rig) -> None:
    rig.bridge.hold[SEARCH] = threading.Event()
    async with running(rig.kernel):
        await to_the_grid(rig)
        rig.runner.job(WORKSPACE, SEARCH, "The annealing seeds", 45, actor=AGENT)
        with pytest.raises(RunError, match=r"job 1 .* still runs: one job at a time"):
            rig.runner.job(WORKSPACE, "python3 other.py", "Another", 5, actor=AGENT)
        rig.bridge.hold[SEARCH].set()


async def test_a_job_longer_than_its_box_may_run_is_refused(rig: Rig) -> None:
    async with running(rig.kernel):
        await to_the_grid(rig)
        with pytest.raises(RunError, match="at most its box's 60 minutes"):
            rig.runner.job(WORKSPACE, SEARCH, "The annealing seeds", 90, actor=AGENT)
        with pytest.raises(RunError, match="a command to run"):
            rig.runner.job(WORKSPACE, "  ", "Nothing", 5, actor=AGENT)
    assert rig.bridge.jobs == []


def test_a_job_while_no_box_works_is_refused_and_the_route_says_why(rig: Rig) -> None:
    with pytest.raises(RunError, match="no box of a flow works in myproject now"):
        rig.runner.job(WORKSPACE, SEARCH, "The annealing seeds", 45, actor=AGENT)
    app = create_app(rig.kernel, token="t", port=7720, background=[rig.kernel.parts["flows"].run])
    with TestClient(app, base_url="http://127.0.0.1:7720") as http:
        answer = http.post(
            "/api/v1/flows/job",
            headers={"Authorization": "Bearer t", "X-Clank-Client": "agent"},
            json={"workspace": WORKSPACE, "command": SEARCH, "title": "The annealing seeds", "minutes": 45},
        )
    assert answer.status_code == 409
    assert "no box of a flow works in myproject now" in answer.json()["error"]["message"]


def sent_to(rig: Rig, session: str) -> list[str]:
    """Every message sent to the session, oldest first."""
    return [each.text for each in rig.bridge.prompts if each.session == session]


async def test_a_box_whose_turn_ends_while_its_job_runs_waits_and_is_sent_its_end_in_the_same_session(rig: Rig) -> None:
    rig.bridge.hold[SEARCH] = threading.Event()
    rig.bridge.commands[SEARCH] = Answer(0, "".join(f"seed {n}: 0.3\n" for n in range(80)) + "best 0.25\n", "")
    async with running(rig.kernel):
        grid = await to_the_grid(rig)
        rig.runner.job(WORKSPACE, SEARCH, "The annealing seeds", 60, actor=AGENT)
        rig.bridge.finish(grid.session)
        await until(lambda: rig.bridge.looked)  # waiting on it
        rig.clock.advance(61 * 60)  # past the box's 60 minutes: the job's time does not count against them
        await anyio.sleep(0.3)
        assert rig.run().box("T1").tries[-1].outcome is None, "waiting on its job, not ended"
        assert len(sent_to(rig, grid.session)) == 1
        rig.bridge.hold[SEARCH].set()
        await until(lambda: len(sent_to(rig, grid.session)) == 2)
        told = sent_to(rig, grid.session)[-1]
        rig.bridge.finish(grid.session, {"grid.json": "[]\n"})
        await until(lambda: rig.run().box("T1").state == "done")
    assert told.startswith("Job 1 (The annealing seeds) exited 0 after 1 hour 1 minute.")
    assert "best 0.25" in told
    assert "seed 0:" not in told, "its log's last lines only"
    attempt = rig.run().box("T1").tries[-1]
    [job] = attempt.jobs
    assert (job.status, job.said, job.ended is not None) == (0, "exited 0", True)
    assert attempt.waited == 61 * 60
    assert [each.data["action"] for each in rig.events("flows.job")] == ["started", "ended"]


async def test_a_job_past_its_minutes_is_ended_by_clank_and_the_box_told(rig: Rig) -> None:
    rig.bridge.hold[SEARCH] = threading.Event()
    async with running(rig.kernel):
        grid = await to_the_grid(rig)
        rig.runner.job(WORKSPACE, SEARCH, "The annealing seeds", 10, actor=AGENT)
        rig.bridge.finish(grid.session)
        await anyio.sleep(0.2)
        rig.clock.advance(12 * 60)
        await until(lambda: len(sent_to(rig, grid.session)) == 2)
    assert rig.bridge.jobs_ended == [jobs.folder_of(FLOW, 1, "T1", 1)]
    assert "was ended by Clank: it ran past its 10 minutes" in sent_to(rig, grid.session)[-1]


async def test_a_job_whose_process_is_gone_without_an_exit_is_said_so(rig: Rig) -> None:
    rig.bridge.vanish.add(SEARCH)
    async with running(rig.kernel):
        grid = await to_the_grid(rig)
        rig.runner.job(WORKSPACE, SEARCH, "The annealing seeds", 45, actor=AGENT)
        rig.bridge.finish(grid.session)
        await until(lambda: len(sent_to(rig, grid.session)) == 2)
    assert "is gone: its process ended without an exit code" in sent_to(rig, grid.session)[-1]
    assert rig.run().box("T1").tries[-1].jobs[0].status is None


async def test_stopping_the_run_ends_its_job(rig: Rig) -> None:
    rig.bridge.hold[SEARCH] = threading.Event()
    async with running(rig.kernel):
        grid = await to_the_grid(rig)
        rig.runner.job(WORKSPACE, SEARCH, "The annealing seeds", 45, actor=AGENT)
        rig.bridge.finish(grid.session)
        await anyio.sleep(0.2)
        rig.runner.stop(FLOW, actor=OWNER)
        await until(lambda: rig.run().box("T1").tries[-1].jobs[0].ended)
    assert rig.run().status == "stopped"
    assert rig.bridge.jobs_ended == [jobs.folder_of(FLOW, 1, "T1", 1)]
    assert rig.run().box("T1").tries[-1].jobs[0].status == jobs.TERMINATED
