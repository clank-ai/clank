"""Design 0013 §17 (decision 0132): the box at work starts a long computation as a job with `flow_job`, one at a time,
within its box's minutes; Clank starts it in the workspace's container and keeps it on the box's try, and says how its
end comes back. A job asked for while no box works, a second while one runs, or one longer than its box may run is
refused, saying why; the route answers 409 with those words."""

import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.flows import jobs
from clank.components.flows.runner import RunError
from clank.components.flows.verdicts import AGENT
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from tests.components.flows.rig import FLOW, OWNER, WORKSPACE, Rig, make_rig, question, running, study, until

pytestmark = pytest.mark.anyio
SEARCH = "python3 anneal.py --seeds 8"


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    flow = study()
    flow["boxes"][3]["limits"] = {"minutes": 60}
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
