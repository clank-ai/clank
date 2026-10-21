"""What the console asks of the service on the user's behalf (design 0002 §2.15): each call runs in a worker thread,
never on the screen's, so a slow or stopped service never freezes the console; what it did, or why it failed in the
service's own words, is said on the console's message line, and the console stays usable. What a call changes comes
back through the event stream, like a change made anywhere else.

A call that starts an operation (opening a workspace, loading a model) is followed to its end: the message line says
it started (`done`), then how it ended: `finished` (or the started words with "done") when it succeeded, else the
operation's own words for why not. So a message such as "opening myproject" never stays after the work is over. The
following stops when its worker is canceled (the console closing) or the console no longer runs.
"""

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from textual.worker import get_current_worker

from clank.client import ClientError, NotRunning

if TYPE_CHECKING:
    from clank.client import Client
    from clank.console.app import ClankConsole

ENDED = ("done", "failed", "canceled")
FOLLOW_SECONDS = 3600.0
POLL_SECONDS = 0.5


def call(
    console: "ClankConsole",
    request: Callable[[], Any],
    *,
    done: str = "",
    finished: str = "",
    quiet: bool = False,
) -> None:
    """Make a request of the service in a thread; say `done` when it succeeds, and the service's words when not
    (unless `quiet`: for what the user did not ask for, such as presence). When it started an operation, follow it and
    say how it ended."""

    def work() -> None:
        try:
            answer = request()
        except (NotRunning, ClientError) as error:
            if not quiet:
                console.call_from_thread(console.say, str(error), True)
            return
        if done:
            console.call_from_thread(console.say, done)
        operation = started(answer)
        if operation is None or quiet:
            return
        worker = get_current_worker()

        def stopped() -> bool:
            return worker.is_cancelled or not console.is_running  # spelling: keep (Textual's own name)

        ended = follow(console.client, operation, stopped)
        if ended is None:
            return
        if ended["status"] == "done":
            console.call_from_thread(console.say, finished or (f"{done}: done" if done else "done"))
        else:  # failed, or canceled: an error only when it failed
            why = ended.get("error") or ended["status"]
            console.call_from_thread(console.say, f"{done}: {why}" if done else str(why), ended["status"] == "failed")

    console.run_worker(work, thread=True, group="calls", exit_on_error=False)


def started(answer: Any) -> str | None:
    """The id of the operation an answer says was started and has not ended yet, if any."""
    if not isinstance(answer, dict):
        return None
    found = str(answer.get("id") or "")
    if not found.startswith("op-") or answer.get("status") in ENDED:
        return None
    return found


def follow(client: "Client", operation: str, stopped: Callable[[], bool] = lambda: False) -> dict[str, Any] | None:
    """The operation's record once it ended; None when the service stopped answering, it ran too long to wait, or
    whoever follows it stopped."""
    deadline = time.monotonic() + FOLLOW_SECONDS
    while time.monotonic() < deadline and not stopped():
        try:
            values: dict[str, Any] = client.get(f"records/operation/{operation}")["values"]
        except (NotRunning, ClientError):
            return None
        if values.get("status") in ENDED:
            return values
        time.sleep(POLL_SECONDS)
    return None
