"""Design 0004 §1: handing the console's terminal to a program. The console steps aside, the program runs attached to
the terminal, the keys it left unread are dropped, and the console comes back; a program that cannot start, or one
interrupted, still gives the console back, saying so; headless (tests, snapshots) the program runs without stepping
aside; a terminal resized meanwhile tells the console its new size; and Ctrl+C belongs to the program while it runs."""

import os
import signal
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import pytest
from textual import events
from textual.geometry import Size

from clank.console.terminal import attached, hand_over


class Console:
    """A console as `hand_over` sees it: whether it is headless, its size, and what it was asked."""

    def __init__(self, headless: bool = False) -> None:
        self.is_headless = headless
        self.size = Size(80, 24)
        self.steps: list[str] = []
        self.posted: list[Any] = []

    @contextmanager
    def suspend(self) -> Iterator[None]:
        self.steps.append("suspend")
        yield
        self.steps.append("resume")

    def post_message(self, message: Any) -> bool:
        self.posted.append(message)
        return True


def step(console: Console, name: str, status: int = 0) -> Callable[[Sequence[str]], int]:
    """A program that notes it ran, and ends with a status."""

    def run(argv: Sequence[str]) -> int:
        console.steps.append(name)
        return status

    return run


def forgotten(console: Console) -> Callable[[], None]:
    """Dropping the unread keys, noted."""
    return lambda: console.steps.append("forget")


def test_the_console_steps_aside_runs_the_program_drops_its_unread_keys_and_comes_back() -> None:
    console = Console()
    outcome = hand_over(console, ["opencode"], step(console, "run"), forgotten(console))
    assert (outcome, console.steps) == (0, ["suspend", "run", "forget", "resume"])


def test_a_program_that_cannot_start_or_is_interrupted_still_gives_the_console_back() -> None:
    console = Console()

    def missing(argv: Sequence[str]) -> int:
        raise FileNotFoundError("no such program")

    def interrupted(argv: Sequence[str]) -> int:
        raise KeyboardInterrupt

    assert hand_over(console, ["docker"], missing, lambda: None) == "docker could not start: no such program"
    assert hand_over(console, ["docker"], interrupted, lambda: None) == "interrupted"
    assert console.steps == ["suspend", "resume", "suspend", "resume"]


def test_headless_the_program_runs_without_stepping_aside() -> None:
    console = Console(headless=True)
    assert hand_over(console, ["opencode"], step(console, "run", 5), lambda: None) == 5
    assert console.steps == ["run"]


def test_a_terminal_resized_while_the_program_ran_tells_the_console_its_size(monkeypatch: pytest.MonkeyPatch) -> None:
    console = Console()
    monkeypatch.setattr(os, "get_terminal_size", lambda fd: os.terminal_size((100, 30)))
    hand_over(console, ["opencode"], lambda argv: 0, lambda: None)
    [resized] = console.posted
    assert isinstance(resized, events.Resize)
    assert (resized.size.width, resized.size.height) == (100, 30)


def test_a_program_runs_attached_with_ctrl_c_its_own_and_the_console_s_handler_back_after() -> None:
    before = signal.getsignal(signal.SIGINT)
    assert attached([sys.executable, "-c", "raise SystemExit(3)"]) == 3
    assert signal.getsignal(signal.SIGINT) is before
