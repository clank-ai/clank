"""The runtime's watcher (design 0003 §6.2-§6.3, design 0001 §4.4 and §4.6): what it does while the service runs.

When the service starts it adopts what its slots ran: an engine still running, by the same identity, keeps its slot
ready without a restart; one that ended meanwhile leaves its slot stopped, said so; one whose start or stop the restart
cut short is stopped. Then, every few seconds, each ready slot's engine must still run, and every `health_seconds` it
must answer (`/v1/models`, which the engines answer even while they generate); three failed health checks in a row
stop it. A host that cannot say whether an engine runs (a busy WSL leaves the question unanswered) says nothing about
it: the slot is kept, and the next look asks again; a stop the host cannot answer for leaves the slot as it was.

A cloud slot (design 0016 §7, `cloud.py`) has no process here: it is adopted while its provider's record, agreement and
key remain, and every `cloud_health_seconds` its provider is asked whether it still takes the key; a refused key fails
the slot, a provider that does not answer leaves it ready, marked; the crash rule below never applies to it.

An engine that ends, or stops answering, makes its slot failed with the engine's own last words and its launch
crashed. One that had been ready for ten minutes or more is started again once (`runtime.restart`), saying so; a second
crash within the hour leaves the slot failed and asks the user whether to start it again; one that crashed soon after
its start is left failed.
"""

import logging
import time
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio
import anyio.to_thread
import httpx2

from clank.components.runtime import cloud
from clank.components.runtime.hosts.host import HostError, ProcessIdentity
from clank.components.runtime.slots import STOP_SECONDS, _lines, _reading
from clank.components.runtime.state import SlotRecord
from clank.kernel.events import CLANK

if TYPE_CHECKING:
    from clank.components.runtime.service import Runtime

log = logging.getLogger(__name__)
WATCH_SECONDS = 5.0
HEALTH_FAILURES = 3
RESTART_AFTER = timedelta(minutes=10)
CRASH_WINDOW = timedelta(hours=1)


class Watcher:
    """The runtime's eyes on its engines."""

    def __init__(self, runtime: "Runtime") -> None:
        self.runtime = runtime
        self._misses: dict[str, int] = {}
        self._asked: dict[str, float] = {}

    async def run(self) -> None:
        """Adopt, then watch, while the service runs; a round that fails is logged, and the next one comes."""
        try:
            await self.adopt()
        except Exception:
            log.exception("adopting what the slots ran failed")
        while True:
            try:
                await self.watch_once()
            except Exception:
                log.exception("watching the slots failed")
            await anyio.sleep(WATCH_SECONDS)

    async def adopt(self) -> None:
        """What each slot ran before the service started: adopted when it still runs, else said."""
        state = self.runtime.state
        for name in self.runtime.settings().slots:
            slot = state.slot(name)
            if self._cloud(slot):
                if slot.status in ("starting", "ready", "stopping"):
                    await anyio.to_thread.run_sync(cloud.adopt, self.runtime, name, slot)
                    self._asked.pop(name, None)  # its key is asked at the next watch
                continue
            if slot.pid is None or slot.host is None:
                continue
            identity = ProcessIdentity(slot.host, slot.pid, slot.started or "", slot.command or "")
            host = self.runtime.host(slot.host)
            title = self.runtime.title(slot.preset)
            alive = await anyio.to_thread.run_sync(host.alive, identity)
            if alive is None:
                continue  # the host did not answer: the watch asks again
            if not alive:
                if slot.launch_id is not None:
                    state.finish_launch(slot.launch_id, "stopped", detail="it ended while the service was not running")
                state.set_slot(name, "stopped", "stopped while the service was not running", actor=CLANK)
            elif slot.status == "ready":
                said = f"adopted after the service started: {title} still runs"
                state.set_slot(name, "ready", said, actor=CLANK, keep_since=True)
            else:
                try:
                    ended = await anyio.to_thread.run_sync(host.stop, identity, STOP_SECONDS)
                except HostError:
                    continue  # it may still run: the slot stays as recorded
                if slot.launch_id is not None:
                    state.finish_launch(slot.launch_id, "stopped", detail=ended)
                said = f"its {'start' if slot.status == 'starting' else 'stop'} was cut short by the service's restart"
                state.set_slot(name, "stopped", f"{said} ({ended})", actor=CLANK)

    async def watch_once(self, health: bool | None = None) -> None:
        """Look at each ready slot once: is its engine still there, and (when it is time, or asked) does it answer?"""
        settings = self.runtime.settings()
        for name in settings.slots:
            slot = self.runtime.state.slot(name)
            if slot.status == "ready" and self._cloud(slot):
                due = time.monotonic() - self._asked.get(name, 0.0) >= settings.cloud_health_seconds
                if health if health is not None else due:
                    self._asked[name] = time.monotonic()
                    await anyio.to_thread.run_sync(cloud.watch, self.runtime, name, slot)
                continue
            if slot.status != "ready" or slot.pid is None or slot.host is None:
                continue
            identity = ProcessIdentity(slot.host, slot.pid, slot.started or "", slot.command or "")
            host = self.runtime.host(slot.host)
            if await anyio.to_thread.run_sync(host.alive, identity) is False:
                await self._crashed(name, self._reading(slot.launch_id))
                continue
            due = time.monotonic() - self._asked.get(name, 0.0) >= settings.health_seconds
            if not (health if health is not None else due):
                continue
            self._asked[name] = time.monotonic()
            if await anyio.to_thread.run_sync(_answers_health, f"http://127.0.0.1:{slot.port}"):
                self._misses[name] = 0
                continue
            self._misses[name] = self._misses.get(name, 0) + 1
            if self._misses[name] >= HEALTH_FAILURES:
                try:
                    await anyio.to_thread.run_sync(host.stop, identity, STOP_SECONDS)
                except HostError:
                    continue  # it may still run: kept, and stopped at the next look
                self._misses[name] = 0
                await self._crashed(name, f"it did not answer its health check {HEALTH_FAILURES} times in a row")

    async def _crashed(self, name: str, reason: str) -> None:
        """Keep the crash, then start it again once, ask, or leave it failed."""
        state = self.runtime.state
        slot = state.slot(name)
        title = self.runtime.title(slot.preset)
        now = state.now()
        launch = state.launch(slot.launch_id) if slot.launch_id is not None else None
        if launch is not None:
            state.finish_launch(launch.id, "crashed", detail=reason)
        state.set_slot(name, "failed", f"{title} crashed: {reason}", actor=CLANK, preset=slot.preset)
        if launch is None or slot.preset is None:
            return
        recent = [
            earlier
            for earlier in state.launches(20)
            if earlier.id != launch.id
            and earlier.slot == name
            and earlier.outcome == "crashed"
            and earlier.ended_at is not None
            and now - earlier.ended_at < CRASH_WINDOW
        ]
        params: dict[str, Any] = {"slot": name, "preset": slot.preset, "options": launch.options, "reason": reason}
        if recent:
            await self.runtime.kernel.operations.start("runtime.restart", {**params, "ask": True}, actor=CLANK)
        elif launch.ready_at is not None and now - launch.ready_at >= RESTART_AFTER:
            await self.runtime.kernel.operations.start("runtime.restart", {**params, "ask": False}, actor=CLANK)

    def _cloud(self, slot: SlotRecord) -> bool:
        """Whether a provider someone else runs serves the slot (design 0016 §7): no process of its own here."""
        return slot.launch_id is not None and bool(self.runtime.state.launch(slot.launch_id).endpoint)

    def _reading(self, launch_id: int | None) -> str:
        if launch_id is None:
            return "it ended"
        log = self.runtime.state.launch(launch_id).log
        return f"it ended: {_reading(_lines(Path(log)))}" if log else "it ended"


def _answers_health(url: str) -> bool:
    """Whether the engine answers (its list of models: cheap, and answered while it generates)."""
    try:
        return httpx2.get(f"{url}/v1/models", timeout=5).status_code == 200
    except httpx2.HTTPError:
        return False
