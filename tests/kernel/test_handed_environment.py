"""Design 0002 §2.8: a command the service hands a client to run (the agent's `docker exec`) names each variable of its
environment alone; the client runs it with the values given beside it over its own environment, where docker reads
them, so no value is on a command line."""

import subprocess
import sys

import pytest

from clank.kernel.processes import with_environment


def test_a_handed_command_runs_with_its_values_over_this_processes_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLANK_TEST_KEPT", "kept")
    monkeypatch.setenv("CLANK_TEST_OVER", "this process's")
    found = with_environment({"CLANK_TEST_OVER": "the service's", "CLANK_TEST_ADDED": "a value"})
    assert found["CLANK_TEST_KEPT"] == "kept", "the rest of this process's environment stays"
    assert found["CLANK_TEST_OVER"] == "the service's"
    assert found["CLANK_TEST_ADDED"] == "a value"


def test_the_program_it_starts_reads_a_value_named_alone_from_its_environment() -> None:
    """As docker does with `--env NAME`: the name on the command line, the value in the environment."""
    read = "import os, sys; print(os.environ[sys.argv[1]])"
    ran = subprocess.run(
        [sys.executable, "-c", read, "CLANK_TEST_SECRET"],
        env=with_environment({"CLANK_TEST_SECRET": "k1-value"}),
        capture_output=True,
        text=True,
        check=True,
    )
    assert ran.stdout.strip() == "k1-value"
