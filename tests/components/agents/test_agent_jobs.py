"""Design 0021 §6: the agent the owner talks to starts a long computation as a job. A job is numbered in its workspace,
its folder `.clank/jobs/agent/<n>/` in the folder, its title, command, minutes and the session that started it kept in
its `job.json` beside the runner's files; it runs in the container through the runner. A job is running once its
process id is written, and ended once its exit is; one is listed, or read whole with its log's last lines and the files
it wrote, and stopped. The watcher ends a job past its minutes, and when one ends records `agents.job_ended` once and
tells the session that started it, in a message saying how it ended, its log's end and the files it wrote. The agent
reaches them through the gateway: start, status and stop."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from clank import registry
from clank.components.agents.jobs import AgentJobs, JobsError
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import names
from clank.components.workspaces.service import jobs as runner
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import Answer
from tests.fakes.platform import FakePlatform, container

YOU = Actor(kind="user", via="console")


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def ran() -> list[list[str]]:
    """The commands run in the workspace's container."""
    return []


@pytest.fixture
def folder(kernel: Kernel, platform: FakePlatform, ran: list[list[str]], tmp_path: Path) -> Path:
    """A workspace `paper` whose container runs, every command run in it answered and kept in `ran`."""
    folder = tmp_path / "paper"
    folder.mkdir()
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    platform.containers.append(
        container(names(kernel.home.id).container("paper"), labels={"clank.home": kernel.home.id})
    )

    def inside(argv: list[str], given: Any) -> Answer:
        ran.append(argv)
        return Answer(0, "", "")

    platform.inside = inside
    return folder


def jobs_of(kernel: Kernel) -> AgentJobs:
    found: AgentJobs = kernel.parts["agents"].jobs
    return found


def test_a_job_is_numbered_its_files_kept_in_the_folder_and_started_in_the_container(
    kernel: Kernel, folder: Path, ran: list[list[str]]
) -> None:
    jobs = jobs_of(kernel)
    started = jobs.start("paper", "python anneal.py --steps 1e6", "anneal", 90, session="ses_1")
    assert (started["job"], started["folder"]) == (1, ".clank/jobs/agent/1")
    kept = json.loads((folder / ".clank/jobs/agent/1/job.json").read_text(encoding="utf-8"))
    assert {key: kept[key] for key in ("title", "command", "minutes", "session")} == {
        "title": "anneal", "command": "python anneal.py --steps 1e6", "minutes": 90, "session": "ses_1",
    }  # fmt: skip
    [argv] = ran
    assert argv[:3] == ["sh", "-c", runner.START]
    assert argv[4:] == ["/workspace/.clank/jobs/agent/1", "5400", "python anneal.py --steps 1e6", "/workspace"]
    assert jobs.start("paper", "make", "build", 10)["job"] == 2
    assert "job 1 (anneal) started" in started["said"]
    assert "you are told when it ends" in started["said"]


def test_a_job_is_running_once_its_process_is_written_and_ended_once_its_exit_is(kernel: Kernel, folder: Path) -> None:
    jobs = jobs_of(kernel)
    jobs.start("paper", "python anneal.py", "anneal", 90)
    own = folder / ".clank/jobs/agent/1"
    assert jobs.one("paper", 1)["state"] == "starting"
    (own / "pid").write_text("41\n", encoding="utf-8")
    (own / "log").write_text("step 1\nstep 2\n", encoding="utf-8")
    assert jobs.one("paper", 1)["state"] == "running"
    (folder / "results.csv").write_text("x,y\n", encoding="utf-8")
    (own / "exit").write_text("0\n", encoding="utf-8")
    one = jobs.one("paper", 1)
    assert (one["state"], one["status"], one["said"]) == ("ended", 0, "exited 0")
    assert one["tail"].endswith("step 2")
    assert one["written"] == ["results.csv"]
    assert [each["job"] for each in jobs.list("paper")] == [1]
    with pytest.raises(JobsError, match="paper has no job 9"):
        jobs.one("paper", 9)


def test_an_ended_job_is_recorded_once_and_the_session_that_started_it_told(
    kernel: Kernel, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = jobs_of(kernel)
    sessions = kernel.parts["agents"].sessions
    sent: list[tuple[str, int, str, str]] = []
    monkeypatch.setattr(sessions, "runs", lambda workspace, session: 4096)
    monkeypatch.setattr(
        sessions, "send", lambda workspace, port, session, text, *, actor: sent.append((workspace, port, session, text))
    )
    jobs.start("paper", "python anneal.py", "anneal", 90, session="ses_1")
    own = folder / ".clank/jobs/agent/1"
    (own / "pid").write_text("41\n", encoding="utf-8")
    (own / "log").write_text("energy -1.25\n", encoding="utf-8")
    (own / "exit").write_text("0\n", encoding="utf-8")
    jobs.watch_once()
    jobs.watch_once()
    [told] = sent
    assert told[:3] == ("paper", 4096, "ses_1")
    assert told[3].startswith("Job 1 (anneal) exited 0 after")
    assert "energy -1.25" in told[3]
    events = kernel.events.latest(10, types=["agents.job_ended"])
    assert len(events) == 1
    assert "Job 1 (anneal) exited 0" in events[0].summary


def test_a_job_past_its_minutes_is_ended_and_one_is_stopped_when_asked(
    kernel: Kernel, folder: Path, ran: list[list[str]], clock: FakeClock
) -> None:
    jobs = jobs_of(kernel)
    jobs.start("paper", "python forever.py", "forever", 1)
    (folder / ".clank/jobs/agent/1/pid").write_text("41\n", encoding="utf-8")
    clock.advance(60 + runner.KILL_AFTER + 61)
    jobs.watch_once()
    assert ["sh", "-c", runner.END] in [argv[:3] for argv in ran], "past its minute and the grace: ended"
    jobs.start("paper", "python other.py", "other", 30)
    (folder / ".clank/jobs/agent/2/pid").write_text("42\n", encoding="utf-8")
    said = jobs.stop("paper", 2)
    assert ran[-1][:3] == ["sh", "-c", runner.END]
    assert "job 2 (other) is being stopped" in said["said"]


def test_the_routes_start_follow_and_stop_a_job_and_list_every_workspaces(kernel: Kernel, folder: Path) -> None:
    from fastapi.testclient import TestClient

    from clank.kernel.api import create_app

    headers = {"Authorization": "Bearer t"}
    with TestClient(create_app(kernel, token="t", port=7727), base_url="http://127.0.0.1:7727") as http:
        body = {"workspace": "paper", "command": "python sweep.py", "title": "sweep", "minutes": 60}
        started = http.post("/api/v1/agents/jobs", json=body, headers=headers).json()
        assert started["job"] == 1
        (folder / ".clank/jobs/agent/1/pid").write_text("41\n", encoding="utf-8")
        one = http.post("/api/v1/agents/jobs/status", json={"workspace": "paper", "job": 1}, headers=headers).json()
        assert (one["title"], one["state"]) == ("sweep", "running")
        listed = http.get("/api/v1/agents/jobs", headers=headers).json()["jobs"]
        assert [(each["workspace"], each["job"]) for each in listed] == [("paper", 1)]
        stopped = http.post("/api/v1/agents/jobs/stop", json={"workspace": "paper", "job": 1}, headers=headers)
        assert "is being stopped" in stopped.json()["said"]
        refused = http.post("/api/v1/agents/jobs", json={**body, "workspace": "nowhere"}, headers=headers)
        assert refused.status_code == 409
        assert "there is no workspace 'nowhere'" in refused.json()["error"]["message"]
