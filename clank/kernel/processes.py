"""Processes: running a program to read its answer (design 0002 §2.9, the first of its part).

Components ask the system's own programs (`nvidia-smi`, `wsl.exe`, `docker`) what they know. Each is run with a time
limit and without a window; a program that is missing, fails or takes too long gives no answer (None), never an
error, so a missing tool means "not there". When its time is up it is ended with every process it started: a program
can hand the question to a helper that keeps its output open (`docker desktop status` does), and on Windows reading
the output waits for the last holder, so the limit would not hold. `wsl.exe` writes UTF-16, which `decode` reads.
Callers take the function as a parameter (`Run`, or `TimedRun` when they set the limit), so tests give fixed answers.
A caller that must say why a command failed (Docker's container commands) asks for its whole answer instead
(`run_answer`, an `Answer`: its exit status, its output and its errors).
A long command (a step of an install, a build) is followed instead (`stream_command`): each line of its output as it
is written, then its exit status; asked to stop, it is ended with every process it started, so a canceled build leaves
no compiler running. An application (Docker Desktop) is started to run on its own (`launch_program`), not waited for.
Whatever is started to run on its own (the service, an engine, an application) gets `background_flags()`: on Windows a
console of its own that has no window, never none at all, since a program without a console that starts a console
program (a virtual environment's python.exe starts the real interpreter) opens a new, visible window for it. Starting,
adopting and stopping the engines Clank runs is the hosts' (`components/runtime/hosts`).
"""

import contextlib
import os
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

import psutil

Run = Callable[[Sequence[str]], str | None]
Launch = Callable[[Sequence[str]], bool]
TIMEOUT_SECONDS = 15.0
CANCEL_SECONDS = 0.25
ENDED_SECONDS = 10.0  # how long the output of a program ended at its time limit is still read


class TimedRun(Protocol):
    """A `Run` whose caller sets the time limit, as `run_command` takes it."""

    def __call__(self, arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS) -> str | None:
        """The program's output, or None when it is missing, fails or takes longer than `timeout` seconds."""


@dataclass(frozen=True)
class Answer:
    """What a program said: its exit status (None when it could not run, or ran out of time), its output, its errors
    (or why it gave no answer)."""

    status: int | None
    output: str
    errors: str

    @property
    def ok(self) -> bool:
        """Whether it ran and exited with 0."""
        return self.status == 0


class TimedAnswer(Protocol):
    """A program's whole answer, as `run_answer` gives it, with the caller's time limit."""

    def __call__(
        self, arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS, input: bytes | None = None
    ) -> Answer:
        """Its exit status, output and errors; `input`, when given, is what it reads."""


def decode(output: bytes) -> str:
    """A program's output as text: UTF-16 when it has the zero bytes UTF-16 puts in plain text, else UTF-8."""
    if output.count(b"\x00") > len(output) // 4:
        return output.decode("utf-16-le", errors="replace").lstrip("﻿")
    return output.decode("utf-8", errors="replace")


def run_command(arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS) -> str | None:
    """Run a program and return its output, or None when it is missing, fails or takes longer than `timeout` seconds
    (it is then ended with every process it started)."""
    answer = run_answer(arguments, timeout)
    return answer.output if answer.ok else None


def run_answer(
    arguments: Sequence[str],
    timeout: float = TIMEOUT_SECONDS,
    input: bytes | None = None,
    env: Mapping[str, str] | None = None,
) -> Answer:
    """Run a program and return its whole answer, giving it `input` to read when there is some and `env` added to its
    environment; one that is missing, or takes longer than `timeout` seconds (it is then ended with every process it
    started), has no exit status, and its errors say why."""
    flags = 0
    if sys.platform == "win32":  # an `if` on sys.platform, so the type checker knows the name exists only there
        flags = subprocess.CREATE_NO_WINDOW
    try:
        process = subprocess.Popen(
            list(arguments),
            stdin=subprocess.PIPE if input is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=flags,
            env={**os.environ, **env} if env else None,
        )
    except OSError as error:
        return Answer(None, "", f"could not run {arguments[0]}: {error}")
    with process:
        try:
            output, errors = process.communicate(input=input, timeout=timeout)
        except subprocess.TimeoutExpired:
            _end(process)
            with contextlib.suppress(subprocess.TimeoutExpired, OSError, ValueError):
                process.communicate(timeout=ENDED_SECONDS)
            return Answer(None, "", f"no answer within {timeout:g} seconds")
    return Answer(process.returncode, decode(output), decode(errors))


def background_flags() -> int:
    """The creation flags of a program started to run on its own: on Windows, a process group and a console of its own,
    without a window; elsewhere none (a session of its own, `start_new_session`, does it)."""
    if sys.platform == "win32":  # an `if` on sys.platform, so the type checker knows the names exist only there
        return subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW
    return 0


def launch_program(arguments: Sequence[str]) -> bool:
    """Start an application to run on its own (in a process group or session of its own, without a window), without
    waiting for it: whether it started. A thread waits for its end, so it is never left unreaped."""
    try:
        process = subprocess.Popen(
            list(arguments),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=background_flags(),
            start_new_session=sys.platform != "win32",
            close_fds=True,
        )
    except OSError:
        return False
    threading.Thread(target=process.wait, name=f"launched {process.pid}", daemon=True).start()
    return True


def _never() -> bool:
    return False


def stream_command(
    arguments: Sequence[str],
    line: Callable[[str], None],
    *,
    canceled: Callable[[], bool] = _never,
    cwd: str | None = None,
    env: Mapping[str, str] | None = None,
) -> int | None:
    """Run a program to its end (in `cwd`, with `env` added to this process's environment), giving `line` each line of
    its output (and of its errors) as it is written; its exit status, or None when it cannot start or was canceled:
    `canceled` is asked a few times a second, and once it says so, the program and every process it started are
    ended."""
    flags = 0
    if sys.platform == "win32":
        flags = subprocess.CREATE_NO_WINDOW
    try:
        process = subprocess.Popen(
            list(arguments),
            cwd=cwd,
            env={**os.environ, **env} if env else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            creationflags=flags,
        )
    except OSError:
        return None
    with process:
        pending: queue.Queue[bytes | None] = queue.Queue()
        reader = threading.Thread(target=_read, args=(process, pending), daemon=True)
        reader.start()
        asked = time.monotonic()
        while (raw := _next(pending)) is not None:
            if raw:
                line(_line(raw))
            if time.monotonic() - asked >= CANCEL_SECONDS:
                asked = time.monotonic()
                if canceled():
                    _end(process)
                    reader.join(10)
                    return None
        reader.join()
        return process.wait()


def _read(process: "subprocess.Popen[bytes]", pending: "queue.Queue[bytes | None]") -> None:
    """Pass on each line the program writes, then None at the end of its output."""
    assert process.stdout is not None
    with contextlib.suppress(OSError, ValueError):  # the pipe closed under it: the program was ended
        for raw in process.stdout:
            pending.put(raw)
    pending.put(None)


def _next(pending: "queue.Queue[bytes | None]") -> bytes | None:
    """The next line; b"" when none came for a moment (time to ask whether to stop); None at the end."""
    try:
        return pending.get(timeout=CANCEL_SECONDS)
    except queue.Empty:
        return b""


def _line(raw: bytes) -> str:
    """One line as text: `wsl.exe`'s own UTF-16 lines are read by dropping their zero bytes."""
    if raw.count(b"\x00") > len(raw) // 4:
        raw = raw.replace(b"\x00", b"")
    return raw.decode("utf-8", errors="replace").lstrip("﻿").rstrip("\r\n")


def _end(process: "subprocess.Popen[bytes]") -> None:
    """End a process, then every process it had started (listed first, so none escapes by losing its parent)."""
    try:
        family = psutil.Process(process.pid).children(recursive=True)
    except psutil.Error:
        family = []
    with contextlib.suppress(OSError):
        process.kill()
    for member in family:
        with contextlib.suppress(psutil.Error):
            member.kill()
    with contextlib.suppress(subprocess.TimeoutExpired):
        process.wait(10)
