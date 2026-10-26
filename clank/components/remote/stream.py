"""The phone's one live stream (design 0025 §3, decision 0143): Server-Sent Events from the listener to a paired
device, in place of asking every few seconds.

`phone_stream` says `connected`, then `now` (what the phone shows first, as `overview` gives it: the model, the agent's
requests, the machine, the workspaces with their sessions, the questions, the marks; never the files), then each of
the kernel's events as it is recorded: its id, type, time, its summary as `title`, whether it needs the owner's
attention (as its type declares, decision 0113), its subject, and the names its data holds that a screen opens on
(`about`: workspace, flow, box, session, question); never the rest of its data, so a push or a line is titles and
names only (§1). `now` is looked at every `NOW_SECONDS` and sent again once when it changed. A device that comes back
with `Last-Event-ID` gets the events it missed (`reset` when they were pruned, as the kernel's own stream says). A
keepalive comment comes after `KEEPALIVE_SECONDS` of silence; `closing` when the listener stops (`closers`).
"""

import json
import threading
import time
from collections.abc import AsyncGenerator, Callable
from functools import partial
from typing import TYPE_CHECKING, Any

import anyio
import anyio.lowlevel
import anyio.to_thread

from clank.kernel.events import Event

if TYPE_CHECKING:
    from clank.components.remote.service import Remote

NOW_SECONDS = 1.0  # how often `now` is looked at
KEEPALIVE_SECONDS = 15.0
BATCH = 500
ABOUT = ("workspace", "flow", "box", "session", "question", "operation", "preset", "slot")


def _sse(name: str, data: Any, id: int | None = None) -> str:
    head = f"id: {id}\n" if id is not None else ""
    return f"{head}event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def event_line(event: Event) -> dict[str, Any]:
    """An event as the phone draws it: titles and names, never the rest of its data."""
    about = {key: event.data[key] for key in ABOUT if isinstance(event.data.get(key), str | int)}
    line: dict[str, Any] = {
        "id": event.id,
        "type": event.type,
        "time": event.time.isoformat(),
        "title": event.summary,
        "attention": bool(event.attention),
        "subject": {"kind": event.subject.kind, "id": event.subject.id} if event.subject is not None else None,
    }
    if about:
        line["about"] = about
    return line


async def phone_stream(
    remote: "Remote",
    after: int | None,
    overview: Callable[[], dict[str, Any]],
    closers: set[Callable[[], None]] | None = None,
) -> AsyncGenerator[str, None]:
    """The stream's text (the module's docstring says what comes)."""
    kernel = remote.kernel
    send, receive = anyio.create_memory_object_stream[object](max_buffer_size=1000)
    token = anyio.lowlevel.current_token()
    loop = threading.get_ident()
    closing = threading.Event()

    def deliver(item: object) -> None:
        try:
            if threading.get_ident() == loop:
                send.send_nowait(item)
            else:
                anyio.from_thread.run_sync(send.send_nowait, item, token=token)
        except anyio.WouldBlock:
            pass  # a wake is due anyway: the events are read from the log, not from what was delivered
        except (anyio.ClosedResourceError, anyio.BrokenResourceError, RuntimeError):
            pass

    def wake(event: Event) -> None:
        if event.id is not None:
            deliver(event.id)

    def close() -> None:
        closing.set()
        deliver(None)

    async def wait(seconds: float) -> bool:
        """Wait for a delivery or `seconds`; whether one came."""
        with anyio.move_on_after(seconds) as scope:
            await receive.receive()
        return not scope.cancelled_caught  # spelling: keep (AnyIO's own name)

    stop = kernel.events.subscribe(wake)
    if closers is not None:
        closers.add(close)
    try:
        yield _sse("connected", {})
        seen = kernel.events.last_id() if after is None else after
        if after is not None and kernel.events.missed(after):
            yield _sse("reset", {"reason": "events after the one you last saw were pruned; reload what you show"})
            seen = kernel.events.last_id()
        while True:  # the events a device missed, before anything else
            batch = await anyio.to_thread.run_sync(partial(kernel.events.after, seen, limit=BATCH))
            for event in batch:
                yield _sse("event", event_line(event), event.id)
                seen = event.id or seen
            if len(batch) < BATCH:
                break
        last_now: dict[str, Any] | None = None
        quiet_since = time.monotonic()
        while True:
            now = await anyio.to_thread.run_sync(overview)
            if now != last_now:
                last_now = now
                yield _sse("now", now)
                quiet_since = time.monotonic()
            came = await wait(NOW_SECONDS)
            if closing.is_set():
                yield _sse("closing", {"reason": "the listener is stopping"})
                return
            if came:
                while True:  # what else was delivered meanwhile is covered by the log read now
                    try:
                        receive.receive_nowait()
                    except anyio.WouldBlock:
                        break
                while True:
                    batch = await anyio.to_thread.run_sync(partial(kernel.events.after, seen, limit=BATCH))
                    for event in batch:
                        yield _sse("event", event_line(event), event.id)
                        seen = event.id or seen
                    if len(batch) < BATCH:
                        break
                quiet_since = time.monotonic()
            elif time.monotonic() - quiet_since >= KEEPALIVE_SECONDS:
                yield ": keepalive\n\n"
                quiet_since = time.monotonic()
    finally:
        stop()
        if closers is not None:
            closers.discard(close)
        send.close()
        receive.close()
