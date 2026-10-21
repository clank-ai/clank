"""The whole suite's rules about what is the owner's: no test may reach the owner's own Clank (its service, its records,
its containers), and no test may run a program in the terminal it runs in.

Before any test runs, CLANK_HOME points to an empty folder of the session's own, removed after it; the real-engine
tests, which read this machine's records on purpose, find the real home in `tests.support.homes`. (Found 2026-10-13: a
test of the bare `clank`, written when it printed its help, reached the owner's service once `clank` came to mean
`clank work`, and opened the repository as a workspace.) A program a page or `clank work` would run in the terminal
(the agent's `docker exec --tty`) fails the test that reaches it instead; tests give the console or the command a
runner of their own."""

import os
import shutil
import tempfile
from collections.abc import Sequence
from pathlib import Path

import pytest

from tests.support.homes import REAL_HOME

SESSION_HOME = Path(tempfile.mkdtemp(prefix="clank-tests-home-"))


def pytest_configure(config: pytest.Config) -> None:
    """Point CLANK_HOME at the session's own empty folder."""
    assert SESSION_HOME.resolve() != REAL_HOME.root.resolve()
    os.environ["CLANK_HOME"] = str(SESSION_HOME)


def pytest_unconfigure(config: pytest.Config) -> None:
    """Remove the session's folder."""
    shutil.rmtree(SESSION_HOME, ignore_errors=True)


@pytest.fixture(autouse=True)
def _no_program_takes_the_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """A program run in the terminal for real fails the test instead."""

    def refused(argv: Sequence[str]) -> int:
        raise AssertionError(f"a test ran {list(argv)[:3]} in its terminal: give it a runner of its own")

    monkeypatch.setattr("clank.console.terminal.attached", refused)
    monkeypatch.setattr("clank.components.agents.cli.terminal", refused)
    monkeypatch.setattr("clank.components.flows.cli.terminal", refused)


@pytest.fixture(autouse=True)
def _no_test_splits_windows_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows Terminal is never split for real: a test that needs it gives a launcher of its own."""

    def refused(argv: Sequence[str]) -> int:
        raise AssertionError(f"a test split Windows Terminal: {list(argv)[:4]}")

    monkeypatch.setattr("clank.kernel.where.run_wt", refused)


@pytest.fixture(autouse=True)
def _no_test_finds_vs_code(monkeypatch: pytest.MonkeyPatch) -> None:
    """VS Code is never found on the PATH, so no test opens a window of it: a test names its fake in its settings."""
    monkeypatch.setattr("clank.components.agents.vscode.which", lambda name: None)
