"""Design 0003 §2 and §6.3, design 0001 §4.6, decision 0030: the local host starts a process in a session of its own,
its output in a log, without a window (on Windows, neither it nor the interpreter a virtual environment's python.exe
starts for it shows one); knows it by its id, start time and command line, once it shows the command line it was started
with (one that never does is ended and refused), and by a start no setting of the system clock moves; says it is gone
once its id names another process, and never stops that one; stops its own politely, and kills it when it does not end
in time; refuses a program it cannot start in its own words; and reads a file's facts and who listens on a port."""

import dataclasses
import hashlib
import importlib
import itertools
import os
import socket
import sys
import time
from collections.abc import Callable
from pathlib import Path

import psutil
import pytest

from clank.components.runtime.hosts import local
from clank.components.runtime.hosts.host import HostError, command_hash
from clank.components.runtime.hosts.local import LocalHost
from tests.support.served import free_port

CHILD = [sys.executable, "-c", "import time; print('started', flush=True); time.sleep(600)"]
# A program that writes whether it has a console window anyone can see, then waits.
WINDOW = (
    "import ctypes, pathlib, sys, time; window = ctypes.windll.kernel32.GetConsoleWindow();"
    " seen = bool(window) and bool(ctypes.windll.user32.IsWindowVisible(window));"
    " pathlib.Path(sys.argv[1]).write_text('visible' if seen else 'hidden'); time.sleep(600)"
)


def until(holds: Callable[[], bool], seconds: float = 10) -> None:
    deadline = time.monotonic() + seconds
    while not holds():
        assert time.monotonic() < deadline, "never got there"
        time.sleep(0.02)


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""


def test_a_started_process_logs_runs_on_its_own_and_is_known_by_its_identity(tmp_path: Path) -> None:
    host = LocalHost()
    log = tmp_path / "logs" / "child.log"
    identity = host.spawn(CHILD, {"CLANK_TEST": "1"}, str(tmp_path), log)
    try:
        assert (identity.host, identity.pid > 0, len(identity.command)) == ("local", True, 64)
        assert host.alive(identity)
        until(lambda: "started" in text(log))
        if sys.platform != "win32":
            assert os.getsid(identity.pid) == identity.pid, "it leads a session of its own"
    finally:
        assert host.stop(identity, 5) in ("stopped", "killed")
    assert not host.alive(identity)


@pytest.mark.skipif(sys.platform != "win32", reason="only Windows gives a console program a window of its own")
def test_a_started_process_shows_no_window_nor_does_the_interpreter_it_starts(tmp_path: Path) -> None:
    report = tmp_path / "window.txt"
    host = LocalHost()
    identity = host.spawn([sys.executable, "-c", WINDOW, str(report)], {}, str(tmp_path), tmp_path / "window.log")
    try:
        until(lambda: text(report) != "")
        assert text(report) == "hidden"
    finally:
        host.stop(identity, 5)


def test_an_identity_whose_id_now_names_another_process_is_not_alive_and_is_not_stopped(tmp_path: Path) -> None:
    host = LocalHost()
    identity = host.spawn(CHILD, {}, str(tmp_path), tmp_path / "a.log")
    reused = dataclasses.replace(identity, started="1.000")  # the same id with another start: a reused id
    try:
        assert not host.alive(reused)
        assert host.stop(reused, 1) == "gone"
        assert host.alive(identity)
    finally:
        host.stop(identity, 5)


@pytest.mark.skipif(sys.platform != "linux", reason="only Linux gives a start as the boot time read now plus a count")
def test_a_process_is_still_itself_when_the_system_clock_is_set_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    procfs = importlib.import_module("psutil._pslinux")  # psutil's part for Linux, which only Linux has
    host = LocalHost()
    identity = host.spawn(CHILD, {}, str(tmp_path), tmp_path / "a.log")
    try:
        boot = procfs.boot_time()
        # A virtual machine's clock, set again and again by its host, moves the boot time Linux gives by whole seconds.
        monkeypatch.setattr(procfs, "boot_time", lambda: boot + 1)
        assert host.alive(identity)
    finally:
        monkeypatch.undo()
        host.stop(identity, 5)


def test_a_start_waits_until_the_process_shows_the_command_line_it_was_started_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = psutil.Process.cmdline
    reads = itertools.count()
    # For a moment after the start returns, Linux can show its command line empty.
    monkeypatch.setattr(psutil.Process, "cmdline", lambda self: [] if next(reads) < 3 else real(self))
    host = LocalHost()
    identity = host.spawn(CHILD, {}, str(tmp_path), tmp_path / "a.log")
    try:
        assert identity.command == command_hash(CHILD)
        assert host.alive(identity)
    finally:
        host.stop(identity, 5)


def test_a_process_that_never_shows_the_command_line_it_was_started_with_is_ended_and_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = {child.pid for child in psutil.Process().children()}
    monkeypatch.setattr(psutil.Process, "cmdline", lambda self: ["another program"])
    monkeypatch.setattr(local, "BECOME_SECONDS", 0.3)
    with pytest.raises(HostError, match=r"did not show the command line it was started with within 0\.3 seconds"):
        LocalHost().spawn(CHILD, {}, str(tmp_path), tmp_path / "a.log")
    monkeypatch.undo()
    assert all(child.pid in before for child in psutil.Process().children()), "the process it started was ended"


@pytest.mark.skipif(sys.platform == "win32", reason="on Windows the local host's polite stop is the end itself")
def test_a_process_that_ignores_the_polite_stop_is_killed_when_its_time_is_up(tmp_path: Path) -> None:
    stubborn = [
        sys.executable,
        "-c",
        "import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); print('ok', flush=True); time.sleep(600)",
    ]
    host = LocalHost()
    log = tmp_path / "stubborn.log"
    identity = host.spawn(stubborn, {}, str(tmp_path), log)
    until(lambda: "ok" in text(log))
    assert host.stop(identity, 0.5) == "killed"
    assert not host.alive(identity)


def test_a_program_that_cannot_start_is_refused_in_the_hosts_words(tmp_path: Path) -> None:
    with pytest.raises(HostError, match=r"cannot start .*missing-program"):
        LocalHost().spawn([str(tmp_path / "missing-program")], {}, str(tmp_path), tmp_path / "x.log")


def test_a_files_facts_and_a_ports_listener_are_read(tmp_path: Path) -> None:
    model = tmp_path / "model.bin"
    model.write_bytes(b"abc")
    host = LocalHost()
    assert (host.exists(str(model)), host.size(str(model))) == (True, 3)
    assert host.sha256(str(model)) == hashlib.sha256(b"abc").hexdigest()
    assert (host.exists(str(tmp_path / "none")), host.size(str(tmp_path / "none"))) == (False, None)
    assert host.expand("~/.clank") == str(Path.home() / ".clank")
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        listener = host.listener(taken.getsockname()[1])
    assert listener is not None
    assert f"process {os.getpid()}" in listener
    assert host.listener(free_port()) is None


def test_a_step_whose_program_is_missing_is_refused_in_the_hosts_words(tmp_path: Path) -> None:
    with pytest.raises(HostError, match="cannot run clank-no-such-program"):
        LocalHost().run_step(["clank-no-such-program"], {}, str(tmp_path), lambda text: None, lambda: False)
