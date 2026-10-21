"""A slot's operations (design 0003 §6.1, design 0001 §4.2): load, unload and switch, each an operation of the service
under the slot's lock (`slot:<name>`), so every client follows each step and a second one is refused as busy.

- `runtime.load`: plan (the launch planned and shown: its command line and its memory breakdown; refused while the slot
  runs, while another program holds the engines' port, or while the GPU's free memory is short of the plan), start
  (the engine started on its host, its output in `logs/processes/<slot>-<launch>.log`), health (its log says it is
  ready, its API lists the model, and a tiny request comes back), measure (the GPU memory it took, kept with the
  launch beside the estimate, and the configuration kept as the last that worked).
- `runtime.unload`: stop (the engine asked to end, then ended when its time is up; only while it is still the process
  Clank started; then the GPU given up to 30 seconds to free what it took, which the driver does a moment after the
  process ends).
- `runtime.switch`: plan, stop what runs, then start, health and measure as a load does, the port and the GPU checked
  once the old engine is gone. When the new engine fails, `return` starts the last configuration that worked again,
  with the options it had then (design 0001 §4.3), and the switch fails saying why the new one failed.
- `runtime.restart`, started by the watcher after a crash (`watching.py`): decide (after a second crash within the
  hour, ask the user first), then start, health and measure the configuration that crashed, saying it starts again.

An engine that ends while it starts, or is not ready in time, is stopped and the slot left failed with the engine's
own words: the last lines of its log that say what went wrong. A cloud preset (design 0016 §7) plans its connection,
starts nothing here and is unloaded without a stop, as `cloud.py` says; a switch between it and an engine stops one
before the other starts, either way.
"""

import contextlib
import re
import time
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio
import httpx2

from clank.components.runtime import cloud
from clank.components.runtime.cloud import CloudError, CloudPrepared
from clank.components.runtime.gpu import GpuMemory, fit
from clank.components.runtime.hosts.host import EngineHost, HostError, ProcessIdentity
from clank.components.runtime.hosts.local import LocalHost
from clank.components.runtime.hosts.wsl import WslHost
from clank.components.runtime.launching import LaunchError, Prepared, prepare
from clank.components.runtime.state import LastGood
from clank.kernel.operations import Canceled, OperationContext, OperationType, StepSpec
from clank.kernel.questions import Option, QuestionDraft

if TYPE_CHECKING:
    from clank.components.runtime.service import Runtime

WAIT_SECONDS = 0.2
STOP_SECONDS = 60.0
FREE_SECONDS = 30.0  # the most a stop waits for the GPU to free what the engine took
# The most a start after Clank's own stop waits for that engine's port: on Windows a stopped program's child lets go of
# it a moment later, longer on a busy machine. A start with nothing stopped before it is refused at once.
PORT_GRACE_SECONDS = 10.0
TROUBLE = re.compile(r"out of memory|error|failed|assert|abort|cannot|exception", re.IGNORECASE)
TINY = {"messages": [{"role": "user", "content": "Reply with OK."}], "max_tokens": 16, "stream": False}
QUESTION_MINUTES = 30
BRING_UP = (StepSpec("start", repeatable=False), StepSpec("health"), StepSpec("measure"))


class SlotError(Exception):
    """A slot's operation that cannot go on, and why."""


def slot_lock(params: Mapping[str, Any]) -> list[str]:
    """The lock of the slot an operation acts on."""
    return [f"slot:{params.get('slot', 'main')}"]


def operation_types(runtime: "Runtime") -> list[OperationType]:
    """Load, unload and switch."""
    slots = Slots(runtime)
    return [
        OperationType(
            "runtime.load", "Load a preset", (StepSpec("plan"), *BRING_UP), slots.load, locks=slot_lock, owner="runtime"
        ),
        OperationType(
            "runtime.unload", "Unload a slot", (StepSpec("stop"),), slots.unload, locks=slot_lock, owner="runtime"
        ),
        OperationType(
            "runtime.switch",
            "Switch a slot to a preset",
            (StepSpec("plan"), StepSpec("stop"), *BRING_UP, StepSpec("return", repeatable=False)),
            slots.switch,
            locks=slot_lock,
            owner="runtime",
        ),
        OperationType(
            "runtime.restart",
            "Start a crashed slot again",
            (StepSpec("decide"), *BRING_UP),
            slots.restart,
            locks=slot_lock,
            owner="runtime",
        ),
    ]


class Slots:
    """What the slots' operations do."""

    def __init__(self, runtime: "Runtime") -> None:
        self.runtime = runtime

    async def load(self, context: OperationContext) -> dict[str, Any]:
        """Plan, start, health, measure."""
        name = str(context.params.get("slot", "main"))
        async with context.step("plan"):
            slot = self.runtime.state.slot(name)
            if slot.status in ("starting", "ready", "stopping"):
                wanted = self._title(str(context.params["preset"]))
                raise SlotError(f"{name} runs {self._title(slot.preset)}: unload it first, or switch to {wanted}")
            prepared = await self._prepare(context, str(context.params["preset"]), context.params.get("options"))
            before = None if isinstance(prepared, CloudPrepared) else await self._ready_to_start(context, prepared)
        return await self._bring_up(context, name, prepared, before, steps=True)

    async def unload(self, context: OperationContext) -> dict[str, Any]:
        """Stop what the slot runs."""
        name = str(context.params.get("slot", "main"))
        async with context.step("stop"):
            ended = await self._stop(context, name, "unloaded")
        return {"slot": name, "stopped": ended}

    async def switch(self, context: OperationContext) -> dict[str, Any]:
        """Plan, stop, start, health, measure; on failure, return to the last configuration that worked."""
        name = str(context.params.get("slot", "main"))
        async with context.step("plan"):
            prepared = await self._prepare(context, str(context.params["preset"]), None)
            fallback = self.runtime.state.slot(name).last_good
        title = prepared.preset.title or prepared.preset_id
        async with context.step("stop"):
            await self._stop(context, name, f"switching to {title}")
        try:
            return await self._bring_up(context, name, prepared, None, steps=True)
        except SlotError as error:
            async with context.step("return"):
                await self._go_back(context, name, fallback, str(error))
        raise AssertionError("unreachable: a return always ends the switch")

    async def restart(self, context: OperationContext) -> dict[str, Any]:
        """Decide (asking after a second crash within the hour), then start the configuration that crashed again."""
        name = str(context.params.get("slot", "main"))
        preset = str(context.params["preset"])
        title = self._title(preset)
        async with context.step("decide"):
            if context.params.get("ask"):
                draft = QuestionDraft(
                    type="approval",
                    title=f"{title} crashed again within an hour: start it again?",
                    detail=str(context.params.get("reason", "")),
                    options=[
                        Option(id="start", label="Start it again", key="y", effect=f"starts {title} again"),
                        Option(id="leave", label="Leave it stopped", key="n", effect=f"{name} stays failed"),
                    ],
                    default="leave",
                    expires=self.runtime.state.now() + timedelta(minutes=QUESTION_MINUTES),
                )
                answer = await context.ask(draft)
                if answer.option != "start":
                    raise Canceled(f"left stopped: {answer.by.describe()} chose to leave it")
            prepared = await self._prepare(context, preset, context.params.get("options"))
        why = "starting it again once after a crash" if not context.params.get("ask") else "starting it again"
        return await self._bring_up(context, name, prepared, None, steps=True, why=why)

    async def _go_back(self, context: OperationContext, name: str, fallback: LastGood | None, reason: str) -> None:
        """Start the last configuration that worked again; always ends the switch with an error saying how it went."""
        if fallback is None:
            raise SlotError(f"{reason}; no configuration has worked yet, so the slot is left failed")
        title = self._title(fallback.preset)
        context.log(f"going back to {title}, the last configuration that worked ({fallback.time:%Y-%m-%d %H:%M})")
        try:
            prepared = await self._prepare(context, fallback.preset, fallback.options)
            await self._bring_up(context, name, prepared, None, steps=False)
        except SlotError as again:
            raise SlotError(f"{reason}; going back to {title} failed too: {again}") from again
        raise SlotError(f"{reason}; back to {title}, which runs again")

    async def _prepare(self, context: OperationContext, preset: str, options: Any) -> "Prepared | CloudPrepared":
        """The launch planned, and shown; for a cloud preset, its connection (`cloud.py`)."""
        try:
            found: Prepared | CloudPrepared = await context.run_blocking(_planned, self.runtime, preset, options)
        except (LaunchError, CloudError) as error:
            raise SlotError(str(error)) from error
        if isinstance(found, CloudPrepared):
            context.log(found.plan_line())
        else:
            context.log(f"plan: {found.plan.command_line()}")
        return found

    async def _ready_to_start(
        self, context: OperationContext, prepared: Prepared, grace: float = 0.0
    ) -> GpuMemory | None:
        """Refuse a start while another program holds the port or the GPU's memory; the GPU's memory before it. After
        Clank's own stop (`grace`), a port still held is asked again until it is free or the grace runs out."""
        port = prepared.plan.port
        deadline = time.monotonic() + grace
        holder = await context.run_blocking(self._holder, prepared.host, port)
        while holder is not None and time.monotonic() < deadline:
            await anyio.sleep(WAIT_SECONDS)
            holder = await context.run_blocking(self._holder, prepared.host, port)
        if holder is not None:
            raise SlotError(
                f"port {port} is held by {holder}: Clank never stops a program it did not start; stop it, or give the "
                "engines another port in config/runtime.json"
            )
        before = await context.run_blocking(self.runtime.read_gpu)
        found = fit(prepared.plan.memory, before, self.runtime.settings().tight_mib)
        context.log("memory: " + "; ".join(found.lines))
        if found.verdict == "does not fit" and not context.params.get("anyway"):
            raise SlotError(
                f"{prepared.preset.title} does not fit in the GPU's free memory: {found.lines[-1]}; another program "
                "uses the GPU, or the preset needs less (ask again with anyway to start it all the same)"
            )
        return before

    def _holder(self, host: EngineHost, port: int) -> str | None:
        """Who holds the port: on the engine's host, or on this machine (where WSL's ports also answer). For an engine
        in WSL, WSL's own relay on this machine (`wslrelay.exe`) holds nothing when no program in WSL listens on the
        port: it goes on listening for about a second after the program that did ended (a switch has just stopped
        it)."""
        found = host.listener(port)
        if found is None and not isinstance(host, LocalHost):
            found = LocalHost().listener(port)
            if found is not None and isinstance(host, WslHost) and found.startswith("wslrelay.exe"):
                return None
        return found

    async def _bring_up(
        self,
        context: OperationContext,
        name: str,
        prepared: "Prepared | CloudPrepared",
        before: GpuMemory | None,
        *,
        steps: bool,
        why: str = "",
    ) -> dict[str, Any]:
        """Start, health and measure, as steps of their own (or within the step that asks, for a return); the port and
        the GPU are checked first when nothing checked them yet. A cloud preset's are `cloud.py`'s."""
        if isinstance(prepared, CloudPrepared):
            return await cloud.bring_up(self, context, name, prepared, steps=steps, why=why)
        state = self.runtime.state
        title = prepared.preset.title or prepared.preset_id
        on_gpu = prepared.plan.memory.on_gpu

        def step(named: str) -> Any:
            return context.step(named) if steps else contextlib.nullcontext()

        async with step("start"):
            if before is None:  # after a stop of Clank's own (a switch, a restart, a return)
                before = await self._ready_to_start(context, prepared, grace=PORT_GRACE_SECONDS)
            launch = state.add_launch(
                slot=name,
                preset=prepared.preset_id,
                options=prepared.preset.options,
                engine=prepared.engine.NAME,
                engine_version=prepared.engine.version.name,
                host=prepared.host_name,
                command_line=prepared.plan.command_line(),
                log="",
                estimate_mib=gpu_estimate(prepared),
                before_mib=before.used_mib if before and on_gpu else None,
            )
            log = self.runtime.kernel.home.logs / "processes" / f"{name}-{launch}.log"
            state.set_log(launch, str(log))
            state.set_slot(
                name, "starting", why or f"loading {title}", actor=context.actor, preset=prepared.preset_id,
                launch_id=launch, host=prepared.host_name, port=prepared.plan.port,
            )  # fmt: skip
            started = time.monotonic()
            try:
                identity = await context.run_blocking(
                    prepared.host.spawn, prepared.plan.argv, dict(prepared.plan.env), prepared.plan.cwd, log
                )
            except Exception as error:
                self._failed(context, name, launch, prepared.preset_id, f"{title} did not start: {error}")
                raise SlotError(f"{title} did not start: {error}") from error
            state.update_slot(name, pid=identity.pid, started=identity.started, command=identity.command)
            context.log(f"started: process {identity.pid} on {prepared.host_name}; its log: {log}")
        async with step("health"):
            await self._healthy(context, name, launch, prepared, identity, log, started)
        async with step("measure"):
            after = await context.run_blocking(self.runtime.read_gpu)
            seconds = round(time.monotonic() - started, 1)
            measured = after.used_mib - before.used_mib if after and before and on_gpu else None
            needed = prepared.engine.needed_mib(_lines(log), before.free_mib) if before and on_gpu else None
            state.finish_launch(launch, "ready", measured_mib=measured, needed_mib=needed, seconds=seconds)
            estimate = prepared.plan.memory.total_mib
            said = f"{measured:,} MiB (estimated {estimate:,})" if measured is not None else "not measured"
            if not on_gpu:
                said = "none: it runs on the CPU"
            if needed is not None:
                said += f"; it needed {needed:,} MiB free to start, which its next estimate learns from"
            context.log(f"ready in {seconds:.0f} s; GPU memory taken: {said}")
            state.set_slot(name, "ready", f"{title} answered in {seconds:.0f} s", actor=context.actor)
            options = dict(prepared.preset.options)
            state.remember_good(name, LastGood(preset=prepared.preset_id, options=options, time=state.now()))
        return {
            "slot": name,
            "preset": prepared.preset_id,
            "launch": launch,
            "seconds": seconds,
            "estimate_mib": estimate,
            "measured_mib": measured,
        }

    async def _healthy(
        self,
        context: OperationContext,
        name: str,
        launch: int,
        prepared: Prepared,
        identity: ProcessIdentity,
        log: Path,
        started: float,
    ) -> None:
        """Wait until the engine says it is ready and answers; fail, stopping it, when it ends or takes too long."""
        title = prepared.preset.title or prepared.preset_id
        limit = self.runtime.settings().start_seconds
        url = f"http://127.0.0.1:{prepared.plan.port}"
        said_ready = False
        while True:
            context.check_canceled()
            lines = _lines(log)
            if not said_ready and any(prepared.engine.ready(line) for line in lines):
                said_ready = True
                context.log("the engine says it is ready")
            if said_ready and await context.run_blocking(_answers, url):
                context.log("it answered a tiny request")
                return
            if await context.run_blocking(prepared.host.alive, identity) is False:
                # Read its log again: it may have written its last words after the look above, then ended.
                reason = f"{title} ended while it started: {_reading(_lines(log))}"
                self._failed(context, name, launch, prepared.preset_id, reason)
                raise SlotError(reason)
            if time.monotonic() - started > limit:
                await context.run_blocking(prepared.host.stop, identity, STOP_SECONDS)
                reason = f"{title} was not ready within {limit} seconds: {_reading(lines)}"
                self._failed(context, name, launch, prepared.preset_id, reason)
                raise SlotError(reason)
            await anyio.sleep(WAIT_SECONDS)

    async def _stop(self, context: OperationContext, name: str, why: str) -> str:
        """Stop what the slot runs, only while it is the process Clank started; what happened."""
        state = self.runtime.state
        slot = state.slot(name)
        if slot.launch_id is not None and state.launch(slot.launch_id).endpoint:
            return cloud.stop(self, context, name, slot, why)
        if slot.pid is None or slot.host is None:
            context.log(f"{name} runs nothing")
            return "nothing"
        identity = ProcessIdentity(slot.host, slot.pid, slot.started or "", slot.command or "")
        host = self.runtime.host(slot.host)
        state.set_slot(name, "stopping", why, actor=context.actor)
        running = await context.run_blocking(self.runtime.read_gpu)
        try:
            ended = await context.run_blocking(host.stop, identity, STOP_SECONDS)
        except HostError as error:
            state.set_slot(name, slot.status, slot.reason, actor=context.actor)  # it may still run: kept as it was
            raise SlotError(str(error)) from error
        context.log(f"process {slot.pid} on {slot.host}: {ended}")
        if slot.launch_id is not None:
            launch = state.launch(slot.launch_id)
            state.finish_launch(slot.launch_id, "stopped", detail=ended)
            took = launch.measured_mib if launch.measured_mib is not None else launch.estimate_mib
            if running is not None and took:
                await self._freed(context, running, took)
        state.set_slot(name, "stopped", f"{why} ({ended})", actor=context.actor)
        return ended

    async def _freed(self, context: OperationContext, running: GpuMemory, took: int) -> None:
        """Wait until the GPU has freed most of what a stopped engine took: the driver frees a process's memory a
        moment after it ends, and a start checked meanwhile would find the GPU still full."""
        target = running.used_mib - took * 3 // 4
        started = time.monotonic()
        while True:
            now = await context.run_blocking(self.runtime.read_gpu)
            seconds = time.monotonic() - started
            if now is None or now.used_mib <= target:
                context.log(f"the GPU freed what it took ({took:,} MiB) in {seconds:.1f} s")
                return
            if seconds > FREE_SECONDS:
                context.log(f"the GPU still holds {now.used_mib - target:,} MiB of what it took after {seconds:.0f} s")
                return
            await anyio.sleep(WAIT_SECONDS)

    def _failed(self, context: OperationContext, name: str, launch: int, preset: str, reason: str) -> None:
        self.runtime.state.finish_launch(launch, "failed", detail=reason)
        self.runtime.state.set_slot(name, "failed", reason, actor=context.actor, preset=preset)

    def _title(self, preset: str | None) -> str:
        return self.runtime.title(preset)


def _planned(runtime: "Runtime", name: str, options: Any) -> "Prepared | CloudPrepared":
    """A preset's launch planned: an engine's (`launching.prepare`), or a cloud preset's connection."""
    from clank.components.runtime.launching import preset_of

    preset_id, preset = preset_of(runtime, name)
    if preset.cloud:
        if options is not None:
            preset = preset.model_copy(update={"options": dict(options)})
        return cloud.prepare(runtime, preset_id, preset)
    return prepare(runtime, name, options)


def gpu_estimate(prepared: Prepared) -> int | None:
    """The GPU memory a launch is expected to take, without what was learned; None for an engine on the CPU."""
    memory = prepared.plan.memory
    return memory.total_mib - memory.learned_mib if memory.on_gpu else None


def _lines(log: Path) -> list[str]:
    try:
        return log.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _reading(lines: list[str]) -> str:
    """The engine's own words for what went wrong: the last line of its log that says so, else its last line."""
    trouble = [line.strip() for line in lines if TROUBLE.search(line)]
    if trouble:
        return trouble[-1]
    return lines[-1].strip() if lines else "it wrote nothing"


def _answers(url: str) -> bool:
    """Whether the engine lists its model and answers a tiny request that names it."""
    try:
        listed = httpx2.get(f"{url}/v1/models", timeout=10)
        if listed.status_code != 200:
            return False
        models = listed.json().get("data") or []
        if not models:
            return False
        tiny = {**TINY, "model": str(models[0].get("id", ""))}
        answer = httpx2.post(f"{url}/v1/chat/completions", json=tiny, timeout=120)
        return answer.status_code == 200 and bool(answer.json().get("choices"))
    except (httpx2.HTTPError, ValueError, AttributeError):
        return False
