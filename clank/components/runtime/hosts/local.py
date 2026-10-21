"""The local host: processes on the service's own machine, on any operating system (decision 0030).

It starts a process through Python (a session of its own on Linux and macOS; a process group and a console of its own,
without a window, on Windows: the kernel's `background_flags()`) and knows it through psutil: its start is the time the
system recorded (on Linux, the clock ticks from the boot, which no setting of the system clock moves), its command line
the one the operating system keeps. A start answers once the process shows the command line it was started with, as
the WSL host's does: for a moment after Python's start returns, Linux can still show it empty (the new program's
arguments are set up after the parent is let go); one that never shows it is ended. On Linux and macOS a stop sends
SIGTERM, then SIGKILL when the time is up; on Windows a process in a console of its own cannot be asked politely, so a
stop ends it at once and says so (`killed`). It is not recorded: its program is the running system itself, so its
contract runs live. The handles of the processes it started are kept for as long as the service runs, and each is
reaped once its process ends, so none is left a zombie. A process adopted after a restart has no handle; psutil
follows it by its id. A step of an install is followed by the kernel's `stream_command`.
"""

import contextlib
import hashlib
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import ClassVar

import psutil

from clank.components.runtime.hosts.host import EngineHost, HostError, ProcessIdentity, Stopped, command_hash
from clank.kernel.processes import background_flags, stream_command

CHUNK = 8 * 1024 * 1024
BECOME_SECONDS = 10.0  # the most a start waits for its process to show the command line it was started with
_STARTED: dict[int, "subprocess.Popen[bytes]"] = {}


class LocalHost(EngineHost):
    """This machine."""

    NAME = "local"
    LABEL = "This machine"
    PLATFORMS = ("linux", "darwin", "win32")
    RECORDED: ClassVar[bool] = False
    PYTHON: ClassVar[str] = sys.executable

    def __init__(self, name: str = "local") -> None:
        super().__init__(name)

    def spawn(self, argv: Sequence[str], env: Mapping[str, str], cwd: str, log: Path) -> ProcessIdentity:
        """Start it with its output appended to the log."""
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("ab") as output:
            try:
                process = subprocess.Popen(
                    list(argv),
                    cwd=cwd or None,
                    env={**os.environ, **env},
                    stdin=subprocess.DEVNULL,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    start_new_session=sys.platform != "win32",
                    creationflags=background_flags(),
                    close_fds=True,
                )
            except OSError as error:
                raise HostError(f"cannot start {argv[0]}: {error.strerror or error}") from error
        _STARTED[process.pid] = process
        want = command_hash(argv)
        deadline = time.monotonic() + BECOME_SECONDS
        while (found := _identity(self.name, process.pid)) is not None and found.command != want:
            if time.monotonic() > deadline:
                process.kill()
                _reap(process.pid)
                raise HostError(
                    f"{argv[0]} did not show the command line it was started with within {BECOME_SECONDS:g} seconds, "
                    f"so it was ended; its log: {log}"
                )
            time.sleep(0.01)
        if found is None:
            raise HostError(f"{argv[0]} ended as soon as it started; its log: {log}")
        return found

    def alive(self, identity: ProcessIdentity) -> bool:
        """Its id names a process with the same start time and command line."""
        return identity.host == self.name and _identity(self.name, identity.pid) == identity

    def stop(self, identity: ProcessIdentity, seconds: float) -> Stopped:
        """SIGTERM, then SIGKILL when the time is up (on Windows, the end at once)."""
        if not self.alive(identity):
            return "gone"
        process = psutil.Process(identity.pid)
        try:
            process.terminate()
            process.wait(seconds)
            ended: Stopped = "killed" if sys.platform == "win32" else "stopped"
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(10)
            ended = "killed"
        except psutil.NoSuchProcess:
            ended = "stopped"
        _reap(identity.pid)
        return ended

    def output(self, argv: Sequence[str]) -> str | None:
        """What it prints, within a minute."""
        flags = 0
        if sys.platform == "win32":  # an `if` on sys.platform, so the type checker knows the name exists only there
            flags = subprocess.CREATE_NO_WINDOW
        try:
            done = subprocess.run(
                list(argv), capture_output=True, timeout=60, stdin=subprocess.DEVNULL, creationflags=flags
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        return (done.stdout + done.stderr).decode("utf-8", errors="replace")

    def exists(self, path: str) -> bool:
        """Whether the file is there."""
        return Path(self.expand(path)).is_file()

    def size(self, path: str) -> int | None:
        """Its size, or None."""
        found = Path(self.expand(path))
        return found.stat().st_size if found.is_file() else None

    def sha256(self, path: str) -> str | None:
        """Its SHA-256, read in pieces, or None."""
        found = Path(self.expand(path))
        if not found.is_file():
            return None
        digest = hashlib.sha256()
        with found.open("rb") as data:
            while piece := data.read(CHUNK):
                digest.update(piece)
        return digest.hexdigest()

    def expand(self, path: str) -> str:
        """`~` is this user's home folder."""
        return str(Path(path).expanduser())

    def listener(self, port: int) -> str | None:
        """The program listening on the port, by name and process id."""
        try:
            for connection in psutil.net_connections(kind="tcp"):
                listening = connection.laddr and connection.laddr.port == port and connection.status == "LISTEN"
                if listening and connection.pid:
                    with contextlib.suppress(psutil.Error):
                        return f"{psutil.Process(connection.pid).name()} (process {connection.pid})"
                    return f"process {connection.pid}"
        except (psutil.Error, OSError):
            return None
        return None

    def run_step(
        self,
        argv: Sequence[str],
        env: Mapping[str, str],
        cwd: str,
        line: Callable[[str], None],
        canceled: Callable[[], bool],
    ) -> int | None:
        """Run it here, in its folder, with its environment added to the service's."""
        Path(cwd).mkdir(parents=True, exist_ok=True)
        status = stream_command(argv, line, canceled=canceled, cwd=cwd, env=env)
        if status is None and not canceled():
            raise HostError(f"cannot run {argv[0]}: no such program")
        return status


def _reap(pid: int) -> None:
    started = _STARTED.pop(pid, None)
    if started is not None:
        with contextlib.suppress(subprocess.TimeoutExpired):
            started.wait(1)


def _identity(host: str, pid: int) -> ProcessIdentity | None:
    started = _STARTED.get(pid)
    if started is not None and started.poll() is not None:
        _reap(pid)
        return None
    try:
        process = psutil.Process(pid)
        if process.status() == psutil.STATUS_ZOMBIE:
            return None
        return ProcessIdentity(host, pid, _start(process), command_hash(process.cmdline()))
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return None


def _start(process: psutil.Process) -> str:
    """Its start, which nothing changes while it runs: on Linux, the clock ticks from the boot to its start (field 22
    of `/proc/<pid>/stat`, as the WSL host reads it), since psutil's time of day for it adds the boot time read now,
    which moves by whole seconds whenever the system clock is set (a virtual machine's host sets it again and again);
    elsewhere, the time the system recorded when it started."""
    if sys.platform == "linux":
        return Path(f"/proc/{process.pid}/stat").read_bytes().rsplit(b") ", 1)[1].split()[19].decode()
    return f"{process.create_time():.3f}"
