"""Locks a process holds on a file for as long as it runs, such as the one that keeps a second service off a
CLANK_HOME (design 0002 §1: one service per home).

The lock is the operating system's own (`msvcrt.locking` on Windows, `flock` elsewhere), on the first byte of the
file, so it is released when its holder ends however it ends, a crash included: a lock file left behind by a dead
process does not block anyone. Taking a lock never waits; a lock already held raises `LockHeld` at once.
"""

import contextlib
import os
import sys
from collections.abc import Iterator
from pathlib import Path


class LockHeld(Exception):
    """Another process holds the lock."""


@contextlib.contextmanager
def hold(path: Path) -> Iterator[None]:
    """Hold the lock on `path` (created if missing) until the block ends; raises `LockHeld` if another holds it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            _lock(descriptor)
        except OSError as error:
            raise LockHeld(f"{path} is locked by another process") from error
        try:
            yield
        finally:
            _unlock(descriptor)
    finally:
        os.close(descriptor)


if sys.platform == "win32":
    import msvcrt

    def _lock(descriptor: int) -> None:
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)

    def _unlock(descriptor: int) -> None:
        os.lseek(descriptor, 0, os.SEEK_SET)
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)

else:
    import fcntl

    def _lock(descriptor: int) -> None:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _unlock(descriptor: int) -> None:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
