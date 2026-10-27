"""Design 0002 §1 and §2.7: a service that holds its home's lock but no longer answers (on the owner's PC, 2026-10-26,
its socket closed by a dropped client) is not left in the way. The service says which process holds the lock, and
when it started (`state/service.pid`); `clank stop` ends that process when the API does not answer, saying so; a
second `clank serve` says the first runs without answering and how to end it, instead of "starting"; a process that
ended, or another that took its number since, is never named."""

import subprocess
import sys
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import psutil
import pytest
from click.testing import CliRunner

from clank.cli.service import stop
from clank.kernel import service
from clank.kernel.access import Connection, write_connection
from clank.kernel.home import Home


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Home:
    monkeypatch.setenv("CLANK_HOME", str(tmp_path / "home"))
    found = Home.resolve()
    found.state.mkdir(parents=True, exist_ok=True)
    return found


@pytest.fixture
def silent() -> Iterator[psutil.Process]:
    """A process that runs and answers nothing, standing for a service gone deaf."""
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
    try:
        yield psutil.Process(child.pid)
    finally:
        child.kill()
        child.wait(timeout=10)


def test_the_process_holding_the_lock_is_known_by_its_number_and_its_start(home: Home, silent: psutil.Process) -> None:
    assert service.holder(home) is None, "no file: none"
    service.write_holder(home, silent.pid)
    found = service.holder(home)
    assert found is not None
    assert found[0] == silent.pid
    (home.state / service.PID).write_text(f"{silent.pid} {silent.create_time() - 3600}", encoding="utf-8")
    assert service.holder(home) is None, "another process that took its number since is never named"


def test_clank_stop_ends_a_service_that_holds_the_lock_but_does_not_answer(home: Home, silent: psutil.Process) -> None:
    service.write_holder(home, silent.pid)
    write_connection(home, Connection("http://127.0.0.1:9", silent.pid, datetime.now(UTC), "0.0.0"))
    result = CliRunner().invoke(stop)
    assert result.exit_code == 0, result.output
    assert f"did not answer (process {silent.pid}), so it was ended" in result.output
    deadline = time.monotonic() + 10
    while silent.is_running() and silent.status() != psutil.STATUS_ZOMBIE and time.monotonic() < deadline:
        time.sleep(0.1)
    assert not silent.is_running() or silent.status() == psutil.STATUS_ZOMBIE
    assert not (home.state / service.PID).exists()
    result = CliRunner().invoke(stop)
    assert result.exit_code == 1, "nothing left to end: the usual words"
    assert "not running" in result.output


def test_a_second_serve_says_the_first_runs_without_answering_and_how_to_end_it(
    home: Home, silent: psutil.Process
) -> None:
    first = service.Service(home, [])
    service.write_holder(home, silent.pid)
    said = first.held_by_another(now=service.started_at(silent.pid) + timedelta(minutes=5))
    assert f"(process {silent.pid}" in said
    assert "does not answer: `clank stop` ends it" in said
    assert "is starting" in first.held_by_another(now=service.started_at(silent.pid) + timedelta(seconds=5))
