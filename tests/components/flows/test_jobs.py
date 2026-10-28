"""Design 0013 §17 (decision 0132): a job, a long computation a box starts with `flow_job`, run detached in the
workspace's container. Its folder in the workspace (`.clank/jobs/<flow>/<run>/<box>-<n>/`) holds its command, its
process id, its log and, once it ends, its exit code, so the service reads its state as files; Clank ends one past its
minutes or when its run stops. The scripts run in the container's shell: tried for real on Linux, and through the fake
platform elsewhere."""

import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from clank.components.flows import jobs
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from clank.kernel.processes import Answer
from tests.components.flows.rig import WORKSPACE, Rig, make_rig


def test_a_jobs_folder_is_named_by_its_flow_run_box_and_number() -> None:
    assert jobs.folder_of("stabrank/flow", 3, "search", 2) == ".clank/jobs/flow/3/search-2"


def test_its_state_is_read_from_its_files() -> None:
    assert jobs.read_state(Path("/nonexistent")) == jobs.State(started=False, ended=False, status=None)


def test_a_job_that_ended_says_its_status_and_the_end_of_its_log(tmp_path: Path) -> None:
    folder = tmp_path / ".clank/jobs/flow/1/search-1"
    folder.mkdir(parents=True)
    (folder / "pid").write_text("123\n", encoding="utf-8")
    (folder / "log").write_text("".join(f"line {n}\n" for n in range(200)), encoding="utf-8")
    assert jobs.read_state(folder) == jobs.State(started=True, ended=False, status=None)
    (folder / "exit").write_text("0\n", encoding="utf-8")
    assert jobs.read_state(folder) == jobs.State(started=True, ended=True, status=0)
    tail = jobs.tail(folder)
    assert tail.endswith("line 199")
    assert "line 100" not in tail, "the end of its log only"


def test_how_a_job_ended_is_said_in_words() -> None:
    assert jobs.ended_words(0, minutes=30) == "exited 0"
    assert jobs.ended_words(jobs.TIMED_OUT, minutes=30) == "ran past its 30 minutes and was ended"
    assert jobs.ended_words(jobs.TERMINATED, minutes=30) == "was ended by Clank"
    assert jobs.ended_words(None, minutes=30) == "is gone: its process ended without an exit code"


@pytest.mark.skipif(not sys.platform.startswith("linux") or not shutil.which("setsid"),
                    reason="the scripts run in the workspace's Linux container: tried on Linux")  # fmt: skip
def test_the_start_and_end_scripts_run_a_command_detached_and_end_it_with_its_group(tmp_path: Path) -> None:
    folder = tmp_path / "job"
    argv = ["sh", "-c", jobs.START, "sh", str(folder), "60", "echo hi; sleep 30; echo late", str(tmp_path)]
    started = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    assert started.returncode == 0, started.stderr
    deadline = time.monotonic() + 5
    while "hi" not in (folder / "log").read_text() if (folder / "log").exists() else True:
        assert time.monotonic() < deadline
        time.sleep(0.05)
    assert subprocess.run(["sh", "-c", jobs.ALIVE, "sh", str(folder)], timeout=5).returncode == 0
    subprocess.run(["sh", "-c", jobs.END, "sh", str(folder)], timeout=20, check=True)
    deadline = time.monotonic() + 15
    while not (folder / "exit").exists():
        assert time.monotonic() < deadline
        time.sleep(0.05)
    assert jobs.read_state(folder).status == jobs.TERMINATED
    assert "late" not in (folder / "log").read_text()


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    """The flows' rig, its kernel closed after the test."""
    made = make_rig(home, clock, tmp_path, monkeypatch, None)
    yield made
    made.kernel.close()


def test_a_job_started_in_the_workspace_writes_its_files_and_is_ended_by_clank(rig: Rig) -> None:
    workspaces = rig.kernel.parts["workspaces"]
    done = jobs.folder_of(f"{WORKSPACE}/study", 1, "search", 1)
    rig.bridge.commands["python anneal.py"] = Answer(0, "best 0.25\n", "")
    jobs.start(workspaces, WORKSPACE, done, "python anneal.py", minutes=30)
    folder = rig.folder / done
    deadline = time.monotonic() + 5
    while not jobs.read_state(folder).ended:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    assert jobs.read_state(folder) == jobs.State(started=True, ended=True, status=0)
    assert (folder / "command").read_text(encoding="utf-8") == "python anneal.py\n"
    assert jobs.tail(folder) == "best 0.25"
    held = jobs.folder_of(f"{WORKSPACE}/study", 1, "search", 2)
    rig.bridge.hold["python long.py"] = threading.Event()
    jobs.start(workspaces, WORKSPACE, held, "python long.py", minutes=30)
    assert jobs.alive(workspaces, WORKSPACE, held) is True
    jobs.end(workspaces, WORKSPACE, held)
    assert jobs.read_state(rig.folder / held).status == jobs.TERMINATED
    assert rig.bridge.jobs_ended == [held]


def test_a_job_whose_workspace_does_not_run_does_not_start(rig: Rig) -> None:
    rig.platform.containers.clear()
    rig.kernel.parts["workspaces"].docker(refresh=True)
    with pytest.raises(jobs.JobError, match="could not start"):
        jobs.start(rig.kernel.parts["workspaces"], WORKSPACE, "x", "true", minutes=1)
    assert jobs.alive(rig.kernel.parts["workspaces"], WORKSPACE, "x") is None


def test_its_time_is_said_in_words() -> None:
    assert [jobs.span(each) for each in (40, 60, 3000, 3660, 7200)] == [
        "40 seconds",
        "1 minute",
        "50 minutes",
        "1 hour 1 minute",
        "2 hours",
    ]


def test_the_files_it_wrote_are_the_folders_newer_ones_but_its_own_and_gits(tmp_path: Path) -> None:
    for path in ("old.txt", "runs/seed-1.json", ".git/index", ".clank/jobs/flow/1/search-1/log"):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / path).write_text("x", encoding="utf-8")
    since = time.time() + 5
    for path in ("runs/seed-1.json", ".git/index", ".clank/jobs/flow/1/search-1/log"):
        os.utime(tmp_path / path, (since + 1, since + 1))
    assert jobs.written(tmp_path, since, ".clank/jobs/flow/1/search-1") == ["runs/seed-1.json"]
