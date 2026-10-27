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
    """VS Code is never found on the PATH, so no test opens a window of it: a test names its fake in its settings. Nor
    is VS Code's remote command, and the tests sit at the PC, whatever terminal runs them (over SSH, or in VS Code's
    Remote-SSH, a test would otherwise open a window on the other computer, design 0018 §8): a test that needs either
    sets it."""
    monkeypatch.setattr("clank.components.agents.vscode.which", lambda name: None)
    monkeypatch.setattr("clank.kernel.where.which", lambda name: None)
    for name in ("SSH_CONNECTION", "SSH_CLIENT", "SSH_TTY", "VSCODE_IPC_HOOK_CLI"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def _no_test_asks_github_for_the_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clank's VS Code window never asks GitHub for a release's extension for real (design 0028 §6): a test of it gives
    the fake GitHub of `tests/fakes/github.py`."""

    def refused(url: str) -> bytes:
        raise AssertionError(f"a test asked GitHub for {url}: give it the fake GitHub")

    monkeypatch.setattr("clank.components.agents.extension.fetch", refused)
    monkeypatch.setattr("clank.components.agents.extension.download", refused)


@pytest.fixture(autouse=True)
def _colors_whatever_the_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The console draws its colors in the tests whatever the terminal that runs them asks: with NO_COLOR set there,
    Textual drew gray, and the tests of the console's colors failed (2026-10-25); a test of NO_COLOR sets it."""
    monkeypatch.delenv("NO_COLOR", raising=False)


@pytest.fixture(autouse=True)
def _no_test_asks_tailscale_or_the_internet(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tailscale's command is never run for real (`tailscale serve` would change the owner's tailnet): Clank finds no
    Tailscale unless a test fakes what it says. Nor does the phone's checkup open an address or ask public DNS: a test
    of the checkup gives it answers of its own (design 0025 §2)."""

    def refused(*args: object, **kwargs: object) -> None:
        raise AssertionError("a test reached the network through the phone's checkup: give it answers of its own")

    monkeypatch.setattr("clank.components.remote.tailnet.program", lambda: None)
    monkeypatch.setattr("clank.components.remote.probes.reach", refused)
    monkeypatch.setattr("clank.components.remote.probes.public_addresses", refused)
