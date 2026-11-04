"""Work handed to the service's event loop from any thread, never waited for (decision 0158).

The service's API, its event streams, its operations and the flows' runner live on one event loop; watcher threads,
operations' threads and the routes' worker threads record events and answer questions. A thread that waited for the
loop to take what it handed over stalled whenever the loop was busy, and froze for good, with the loop, when the loop
was waiting for a lock that thread held (review mode's, which a flow's box takes as it starts, while review mode asks
its question under it). `Handoff` schedules the work on the loop and returns at once: the loop runs each piece as soon
as it can, in the order handed over, and on the loop's own thread it runs at once.
"""

import asyncio
import threading
from collections.abc import Callable
from typing import Any


class Handoff:
    """The event loop running where it is made (inside a coroutine), and the way any thread gives it work."""

    def __init__(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._thread = threading.get_ident()

    def here(self) -> bool:
        """Whether this is the loop's own thread."""
        return threading.get_ident() == self._thread

    def call(self, function: Callable[..., Any], *arguments: Any) -> bool:
        """Run `function(*arguments)` on the loop: at once on the loop's thread, else scheduled there without waiting.
        False when the loop has ended and it will never run. What `function` raises on the loop is logged by the loop,
        so a function handed over catches what it expects itself."""
        if self.here():
            function(*arguments)
            return True
        try:
            self._loop.call_soon_threadsafe(function, *arguments)
        except RuntimeError:  # the loop is closed
            return False
        return True
