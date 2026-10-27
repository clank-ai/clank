"""The conversation stream (design 0023 §3): what happens in a conversation, pushed to a client as it happens, over
Server-Sent Events, from the mirror (`mirror.py`) and its change log.

`conversation_stream` first says `connected`, then finds the conversation as `GET /agents/conversation` does (the
session named, else the folder's newest), and sends a `snapshot`: the route's answer with the mirror's `version`. Then
each change the mirror keeps comes as its own event (`message`, `part`, `delta`, `removed`, `status`, `waiting`), its
id the version it made, a burst gathered for `GATHER_SECONDS` so it comes as one flush; a `snapshot` change (a merge,
the cap) brings the whole again. A client that gives `after` (its last version) gets the changes since, or a snapshot
when the log no longer reaches back that far. While the session works, a `readout` event each `READOUT_SECONDS`
carries the model's readout (`Agents.readout`: its speed, its context, what it does now), for the panel's header and
foot. When no session was named and the folder's newest session changes, the stream says `session` and ends: the
client opens the new one. A folder with no session yet gets a snapshot saying so, and the stream looks for one every
`WATCH_SECONDS`. A keepalive comment comes after `KEEPALIVE_SECONDS` of silence; `closing` when the service stops (the
app's `closers`, as the kernel's event stream uses them). A conversation the bridge cannot read (its refusal, a server
gone, a container stopped) ends the stream with `problem` and its words, the response whole, so the client opens it
again later; a traceback for each of its tries told nobody more (the owner's log, 2026-10-26).
"""

import json
import threading
import time
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, Any

import anyio
import anyio.lowlevel
import anyio.to_thread

from clank.components.agents.sessions import SessionError
from clank.components.workspaces.service import WorkspaceUnavailable

if TYPE_CHECKING:
    from clank.components.agents.service import Agents

GATHER_SECONDS = 0.05  # a burst of changes is sent as one flush (0.1 put a change 111 ms behind the mirror; this, 60)
READOUT_SECONDS = 1.0  # the readout, while the session works
KEEPALIVE_SECONDS = 15.0
WATCH_SECONDS = 2.0  # a folder with no session yet is looked at again


def _sse(name: str, data: dict[str, Any], id: int | None = None) -> str:
    head = f"id: {id}\n" if id is not None else ""
    return f"{head}event: {name}\ndata: {json.dumps(data)}\n\n"


async def conversation_stream(
    agents: "Agents",
    folder: str,
    session: str,
    limit: int,
    after: int | None,
    closers: set[Callable[[], None]] | None = None,
    after_session: str = "",
) -> AsyncGenerator[str, None]:
    """The stream's text (the module's docstring says what comes). `after` resumes from a version of the session
    `after_session`; another session's versions mean nothing, so a client that followed the folder's newest gets a
    snapshot when the newest is another."""
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
            pass  # a flush is due anyway: the versions are read from the mirror, not from what was delivered
        except (anyio.ClosedResourceError, anyio.BrokenResourceError, RuntimeError):
            pass

    def close() -> None:
        closing.set()
        deliver(None)

    async def wait(seconds: float) -> bool:
        """Wait for a delivery or `seconds`; whether one came (None: the service is closing)."""
        with anyio.move_on_after(seconds) as scope:
            await receive.receive()
        return not scope.cancelled_caught  # spelling: keep (AnyIO's own name)

    def snapshot(found: dict[str, Any], version: int) -> str:
        return _sse("snapshot", {**found, "version": version}, version)

    if closers is not None:
        closers.add(close)
    stop: Callable[[], None] | None = None
    try:
        yield _sse("connected", {})
        found = await anyio.to_thread.run_sync(agents.conversation, folder, session, limit)
        while found["session"] is None:  # no session yet: say so, then look again until one is there
            yield snapshot(found, 0)
            if found["workspace"] is None:
                return
            while True:
                came = await wait(WATCH_SECONDS)
                if closing.is_set():
                    yield _sse("closing", {"reason": "the service is stopping"})
                    return
                found = await anyio.to_thread.run_sync(agents.conversation, folder, session, limit)
                if found["session"] is not None or came:
                    break
        workspace, chosen = str(found["workspace"]), str(found["session"]["id"])
        busy = bool(found["session"]["busy"])
        version = agents.mirror.version(workspace, chosen)
        stop = agents.mirror.subscribe(workspace, chosen, deliver)
        resuming = after is not None and (not after_session or after_session == chosen)
        since = agents.mirror.changes_since(workspace, chosen, after) if resuming and after is not None else None
        if since is None or any(event.get("type") == "snapshot" for _, event in since):
            yield snapshot(found, version)
        else:
            for each, event in since:
                yield _sse(str(event["type"]), event, each)
                version = each
        last_readout = time.monotonic() if not busy else 0.0
        while True:
            came = await wait(READOUT_SECONDS if busy else KEEPALIVE_SECONDS)
            if closing.is_set():
                yield _sse("closing", {"reason": "the service is stopping"})
                return
            if came:
                await anyio.sleep(GATHER_SECONDS)
                while True:  # what else was delivered meanwhile is covered by the versions read now
                    try:
                        receive.receive_nowait()
                    except anyio.WouldBlock:
                        break
                changes = agents.mirror.changes_since(workspace, chosen, version)
                if changes is None or any(event.get("type") == "snapshot" for _, event in changes):
                    found = await anyio.to_thread.run_sync(agents.conversation, folder, chosen, limit)
                    if found["session"] is None:
                        yield _sse("session", {"id": ""})
                        return
                    version = agents.mirror.version(workspace, chosen)
                    busy = bool(found["session"]["busy"])
                    yield snapshot(found, version)
                else:
                    for each, event in changes:
                        yield _sse(str(event["type"]), event, each)
                        version = each
                        if event.get("type") == "status":
                            busy = bool(event.get("busy"))
            elif not busy:
                yield ": keepalive\n\n"
            if busy and time.monotonic() - last_readout >= READOUT_SECONDS:
                readout = await anyio.to_thread.run_sync(agents.readout, folder, chosen)
                last_readout = time.monotonic()
                yield _sse("readout", {"type": "readout", "readout": readout})
            if not session:
                kept = agents.flows.flows(workspace)
                newest = str((kept[0] if kept else {}).get("session") or "")
                if newest and newest != chosen:
                    yield _sse("session", {"id": newest})
                    return
    except (SessionError, WorkspaceUnavailable) as error:  # the bridge's refusal: said, and the stream ends whole
        yield _sse("problem", {"reason": f"the conversation could not be read: {error}"})
    finally:
        if stop is not None:
            stop()
        if closers is not None:
            closers.discard(close)
        send.close()
        receive.close()
