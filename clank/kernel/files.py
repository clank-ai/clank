"""Files of CLANK_HOME that another program may be reading while Clank changes them (design 0002 §2.16: the state
folder's above all), changed so that neither side fails.

On Windows a file that a program holds open can be neither deleted nor replaced until the program lets go, unless it
opened the file allowing that, which Python's own `open` never does: the delete fails with a sharing violation
(WinError 32), the replace with a refusal (WinError 5), for as long as the reader holds it. Clank's readers hold a file
for a moment (they read it whole and close it), but they read often: the service's threads read `state/gateway.json`
for every status, and the gateway's process reads `state/connection.json` every second; a program outside Clank (an
indexer, an antivirus) may open any of them too. On 2026-10-23 `clank gateway restart` answered 500 when its stop could
not delete `state/gateway.json` while a status was being read. So such a file is:

- written by `replace`: whole, into a file of its own beside it, then put in its place in one step, so a reader finds
  the old or the new and never half of either; tried again for about two seconds (`WAITS`) while another program holds
  the place, then the error raised, the file beside it removed;
- deleted by `remove`, tried again the same way; whether it went, so a caller that could not delete it decides what
  that means instead of failing.

A caller on an event loop, which a wait would hold up whole, gives shorter waits (`MOMENT`, a fifth of a second in
all). An error that is not another program's hold (a full disk) is raised at once. Elsewhere than on Windows a reader
never holds a writer back, and the first try goes through.
"""

import contextlib
import os
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path

WAITS = (0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.5)  # seconds between tries while another program holds a file
MOMENT = (0.01, 0.02, 0.05, 0.1)  # the same, for a caller on an event loop


def held(error: OSError) -> bool:
    """Whether an error says another program holds the file now, which passes, rather than that it cannot be done:
    Windows' sharing and lock violations and its refusal of a replace all come as a `PermissionError`."""
    return isinstance(error, PermissionError)


def replace(path: Path, data: str | bytes, waits: Sequence[float] | None = None) -> None:
    """Write a file whole (text as UTF-8): beside it first, then put in its place in one step; while another program
    holds the place, tried again after each of the waits (`WAITS` unless given), then the error raised and the file as
    it was."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(f".{path.name}.{os.getpid()}-{threading.get_ident()}.writing")
    partial.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    try:
        _again(lambda: os.replace(partial, path), waits)
    except OSError:
        with contextlib.suppress(OSError):
            partial.unlink()
        raise


def remove(path: Path, waits: Sequence[float] | None = None) -> bool:
    """Delete a file (one that is not there is gone already); while another program holds it, tried again after each of
    the waits (`WAITS` unless given); whether it went."""
    try:
        _again(lambda: path.unlink(missing_ok=True), waits)
    except OSError as error:
        if not held(error):
            raise
        return False
    return True


def _again(attempt: Callable[[], None], waits: Sequence[float] | None) -> None:
    """Do it, again after each of the waits while another program holds the file; the last refusal raised."""
    for wait in (*(WAITS if waits is None else waits), None):
        try:
            attempt()
            return
        except OSError as error:
            if wait is None or not held(error):
                raise
            time.sleep(wait)
