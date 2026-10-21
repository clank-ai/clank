"""Handing the console's terminal to a program and taking it back (design 0004 §1): the agent (OpenCode) is started
from the console, runs in the same terminal, and the console comes back when it ends.

`hand_over` suspends the console (Textual's `App.suspend`: the terminal's modes are restored, its alternate screen
left), runs the program attached to the terminal (`attached`: inherited input and output, no console of its own) and
resumes the console, redrawn. It is called on the console's own thread, so nothing draws over the program, and the
program's end is waited for there; what the service sends meanwhile waits in the console's queue and is drawn after.
What could leave the console suspended is kept inside: the program not starting, Ctrl+C (which is the program's while
it runs, not the console's), keys typed into the terminal and left unread (dropped before the console reads keys again,
so none of them is taken as one of its keys), and a terminal resized meanwhile (its new size is sent to the console,
since Windows' terminal does not say it on resume). Where the console cannot step aside (its headless tests, a
snapshot), the program runs without suspending. The program that runs is the console's `terminal`, replaced in tests.
"""

import contextlib
import ctypes
import os
import signal
import subprocess
import sys
from collections.abc import Callable, Sequence
from typing import Any, Protocol

from textual import events
from textual.geometry import Size

Terminal = Callable[[Sequence[str]], int]
STD_INPUT_HANDLE = -10


class Console(Protocol):
    """What `hand_over` needs of the console."""

    @property
    def is_headless(self) -> bool:
        """Whether it runs without a terminal (tests, snapshots)."""

    @property
    def size(self) -> Size:
        """Its size in columns and rows."""

    def suspend(self) -> contextlib.AbstractContextManager[None]:
        """Step aside from the terminal while the block runs."""

    def post_message(self, message: Any) -> bool:
        """Send itself a message."""


def attached(argv: Sequence[str]) -> int:
    """Run a program in this terminal and wait for its end; Ctrl+C is the program's meanwhile."""
    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        return subprocess.call(list(argv))
    finally:
        signal.signal(signal.SIGINT, previous)


def forget_typed_ahead() -> None:
    """Drop the keys the program left unread, so the console does not take them as its own."""
    if sys.platform != "win32":
        with contextlib.suppress(OSError, ValueError):
            import termios

            termios.tcflush(sys.stdin.fileno(), termios.TCIFLUSH)
        return
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.GetStdHandle(STD_INPUT_HANDLE)
    kernel32.FlushConsoleInputBuffer(handle)


def hand_over(
    console: Console, argv: Sequence[str], run: Terminal, forget: Callable[[], None] = forget_typed_ahead
) -> int | str:
    """Run a program in the console's terminal and take the terminal back; its exit status, or why it could not run.
    Call it on the console's own thread."""
    if console.is_headless:
        return _run(argv, run)
    with console.suspend():
        outcome = _run(argv, run)
        with contextlib.suppress(OSError, ValueError, AttributeError):
            forget()
    _resize(console)
    return outcome


def _run(argv: Sequence[str], run: Terminal) -> int | str:
    """The program's exit status, or why it could not run: nothing may leave the console suspended."""
    try:
        return run(argv)
    except (OSError, ValueError) as error:
        return f"{argv[0] if argv else 'it'} could not start: {error}"
    except KeyboardInterrupt:
        return "interrupted"


def _resize(console: Console) -> None:
    """Tell the console the terminal's size, when it changed while the program ran."""
    stdout = sys.__stdout__
    if stdout is None:
        return
    with contextlib.suppress(OSError, ValueError):
        columns, rows = os.get_terminal_size(stdout.fileno())
        if (columns, rows) != (console.size.width, console.size.height):
            console.post_message(events.Resize.from_dimensions((columns, rows), None))
