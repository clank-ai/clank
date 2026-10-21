"""The host kind of adapter (decision 0030, design 0003 §2): where an engine runs.

A host starts a process in a session of its own, its input from nowhere and its output appended to a log, so the
process outlives the call that started it and the service itself (closing a client, or restarting the service, never
stops a model). It knows the process by a `ProcessIdentity`: the host's name, the process id, its start time as the
host reports it, and the SHA-256 of its command line. A process is alive, and may be signaled, only while all three
match (design 0001 §4.6): a process whose id was reused by another program after the engine ended is never touched.

A stop asks the process to end, waits, and ends it when it has not; it says which happened (`stopped`, `killed`), or
that the process was already gone. A host also answers what a check needs: whether a file exists, its size and its
SHA-256, where `~` leads, and who listens on a port. And it runs a step of an install (`run_step`): one command to its
end, in its folder (made when it is not there), each line of its output given as it comes; canceled, the command is
ended with every process it started. A step that is a small script (a download, a rename) runs with the host's Python
(`PYTHON`), so it needs nothing the host does not already have.
"""

import hashlib
from abc import abstractmethod
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal

from clank.kernel.adapters import Adapter, Capability

Stopped = Literal["stopped", "killed", "gone"]


class HostError(Exception):
    """What a host could not do, in its own words."""


@dataclass(frozen=True)
class ProcessIdentity:
    """A process Clank started: where, its id, its start time as the host says it, its command line's SHA-256."""

    host: str
    pid: int
    started: str
    command: str


def command_hash(argv: Sequence[str]) -> str:
    """The SHA-256 of a command line as the operating system keeps it: each argument followed by a NUL byte."""
    return hashlib.sha256("".join(f"{part}\0" for part in argv).encode("utf-8")).hexdigest()


class EngineHost(Adapter):
    """Where engines run: one machine, or one distribution of it."""

    PYTHON: ClassVar[str] = "python3"

    def __init__(self, name: str) -> None:
        self.name = name

    def capabilities(self) -> list[Capability]:
        """What every host does."""
        return [Capability(name, True, "") for name in ("start", "identify", "stop", "file facts", "listener")]

    @abstractmethod
    def spawn(self, argv: Sequence[str], env: Mapping[str, str], cwd: str, log: Path) -> ProcessIdentity:
        """Start a process in a session of its own, its output appended to `log` (a path of the service's machine);
        `HostError` when it cannot start."""

    @abstractmethod
    def alive(self, identity: ProcessIdentity) -> bool | None:
        """Whether the process still runs and is still that process; None when the host cannot say now (a busy WSL
        can leave the question unanswered), which says nothing about the process."""

    @abstractmethod
    def stop(self, identity: ProcessIdentity, seconds: float) -> Stopped:
        """Ask the process to end, and end it when it has not within `seconds`; nothing when it is gone or not it;
        `HostError` when the host cannot answer, since the process may still run."""

    @abstractmethod
    def output(self, argv: Sequence[str]) -> str | None:
        """What a short command prints (its output and its errors, whatever its exit status), or None when it cannot
        run there."""

    @abstractmethod
    def exists(self, path: str) -> bool:
        """Whether a file is there."""

    @abstractmethod
    def size(self, path: str) -> int | None:
        """A file's size in bytes, or None when it is not there."""

    @abstractmethod
    def sha256(self, path: str) -> str | None:
        """A file's SHA-256, or None when it is not there."""

    @abstractmethod
    def expand(self, path: str) -> str:
        """The path with `~` made the host's home folder."""

    @abstractmethod
    def listener(self, port: int) -> str | None:
        """Who listens on a port of the host, as a name and a process id, or None."""

    @abstractmethod
    def run_step(
        self,
        argv: Sequence[str],
        env: Mapping[str, str],
        cwd: str,
        line: Callable[[str], None],
        canceled: Callable[[], bool],
    ) -> int | None:
        """Run a command to its end in `cwd` (made when it is not there), giving `line` each line of its output as it
        comes; its exit status, or None once `canceled` said to stop (the command and what it started are ended then);
        `HostError` when it cannot run there."""
