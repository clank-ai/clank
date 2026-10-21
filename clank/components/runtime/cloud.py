"""The main slot running a cloud preset (design 0016 §7, decision 0107): what load, unload, switch, adoption after a
restart and the watch mean when a provider someone else runs serves the slot in an engine's place.

- **plan**: the connection, not a launch: the provider, its agreement, its key (set), the model in its list (its window,
  output and prices, that it takes tool calls) and the route the gateway will follow; no GPU, install or catalog.
- **start**: nothing starts on this machine, and the step says so; the launch is kept with its route (never a key), its
  `engine` empty, so the GPU's learned memory never reads it. The gateway's service hands the gateway the key when it
  hears the slot change (decision 0106).
- **health**: the key accepted (the provider's account, asked with it), then the same tiny request an engine is asked
  ("Reply with OK.", 16 tokens at most) to the model with the key: its answer, its time and its cost, shown and kept
  with the launch.
- **measure**: the tiny request's time and cost; the configuration kept as the last that worked.
- **unload**: nothing stops at the provider (requests already streaming finish); the slot is stopped.
- **adopted** after a restart while its record, agreement and key remain; its key asked again at the next watch.
- **watched** every `cloud_health_seconds`: the provider's account, which costs nothing. A refused key fails the slot at
  once; a provider that does not answer leaves it ready, marked "not reached since"; an engine's crash rule never
  applies.

`route` is what the gateway follows (plan s34's interface): the launch's kept route with its reach and agreement read
from the record each time, so withdrawing the agreement applies to the next request.
"""

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from clank.components.runtime.adapters import ENDPOINTS
from clank.components.runtime.adapters.endpoint import EndpointAdapter, ModelLine
from clank.components.runtime.kinds import Endpoint, Preset
from clank.components.runtime.state import LastGood, SlotRecord
from clank.kernel.api import ApiError
from clank.kernel.events import CLANK
from clank.kernel.operations import OperationContext

if TYPE_CHECKING:
    from clank.components.runtime.service import Runtime
    from clank.components.runtime.slots import Slots

TINY_WORDS = "Reply with OK."
TINY_TOKENS = 16
TINY_SECONDS = 120.0
CHAT = "/chat/completions"
KEY = "/key"


class CloudError(Exception):
    """A cloud preset that cannot be planned, started or kept, and why; `code` names a provider's refusal or silence."""

    def __init__(self, message: str, code: str = "refused") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class CloudPrepared:
    """A cloud preset ready to load: the preset, its provider's record and adapter, the model's line, and the route."""

    preset_id: str
    preset: Preset
    record: Endpoint
    adapter: EndpointAdapter
    model: ModelLine
    route: dict[str, Any]

    def plan_line(self) -> str:
        """The plan as one line, as the operation's log shows it."""
        route, model = self.route, self.model
        price = f"${model.price_in:.2f} in, ${model.price_out:.2f} out per million tokens"
        return (
            f"plan: {model.id} at {self.adapter.LABEL} ({self.record.url}), reach {route['reach']}: window "
            f"{route['context']:,} (the model's {model.window:,}), output {route['output']:,}, {price}; nothing runs "
            "on this machine"
        )


def money(usd: float) -> str:
    """US dollars as people read a small amount: $1.29, $0.0123, $0.000021."""
    if usd >= 0.01:
        return f"${usd:.2f}"
    return "$" + f"{usd:.6f}".rstrip("0").rstrip(".") if usd else "$0"


def prepare(runtime: "Runtime", preset_id: str, preset: Preset) -> CloudPrepared:
    """The connection of a cloud preset, planned; `CloudError`, saying what to do, when it cannot load."""
    endpoints = runtime.endpoints
    problems = endpoints.preset_problems(preset)
    if problems:
        raise CloudError("; ".join(problems))
    record = endpoints.record(preset.endpoint)
    adapter = ENDPOINTS.get(record.adapter)()
    try:
        model = endpoints.model(preset.endpoint, preset.model)
    except ApiError as error:
        if error.code == "unknown_model":
            refusal = adapter.refusal(404, b"", model=preset.model)
            raise CloudError(refusal.advice, "no_model") from error
        raise CloudError(str(error), error.code) from error
    if not model.tools:
        raise CloudError(f"{model.id} does not take tool calls, and the agent cannot work without them")
    options = preset.options
    window = min(int(options.get("context") or model.window), model.window)
    output = int(options.get("max_output") or min(16384, model.output or 16384))
    images = bool(options["images"]) if "images" in options else model.images
    reasoning = str(options.get("reasoning") or "default")
    route = {
        "provider": "endpoint", "endpoint": preset.endpoint, "adapter": record.adapter, "base_url": record.url,
        "model_name": model.id, "reach": record.reach, "read_timeout": record.timeout_seconds,
        "adds": adapter.adds(record.options, reasoning), "prices": model.prices(), "context": window, "output": output,
        "images": images,
    }  # fmt: skip
    return CloudPrepared(preset_id, preset, record, adapter, model, route)


def route(runtime: "Runtime", slot: SlotRecord) -> dict[str, Any] | None:
    """A cloud slot's route as the gateway follows it, its reach and agreement read now; None for an engine's slot."""
    if slot.launch_id is None:
        return None
    launch = runtime.state.launch(slot.launch_id)
    if not launch.endpoint or launch.route is None:
        return None
    found = dict(launch.route)
    try:
        record = runtime.endpoints.record(launch.endpoint)
        found.update(reach=record.reach, agreed=record.is_agreed)
    except ApiError:
        found.update(agreed=False)
    return found


async def bring_up(
    slots: "Slots", context: OperationContext, name: str, prepared: CloudPrepared, *, steps: bool, why: str = ""
) -> dict[str, Any]:
    """Start (nothing here), health (the key accepted, one tiny request) and measure a cloud preset."""
    import contextlib

    runtime = slots.runtime
    state = runtime.state
    title = prepared.preset.title or prepared.preset_id
    label, model = prepared.adapter.LABEL, prepared.model.id

    def step(named: str) -> Any:
        return context.step(named) if steps else contextlib.nullcontext()

    async with step("start"):
        launch = state.add_launch(
            slot=name, preset=prepared.preset_id, options=prepared.preset.options, engine="", engine_version="",
            host="", command_line=f"nothing runs on this machine: {model} at {label}", log="",
            endpoint=prepared.preset.endpoint, route=prepared.route,
        )  # fmt: skip
        state.set_route(launch, {**prepared.route, "launch": launch})
        state.set_slot(
            name, "starting", why or f"loading {title}", actor=context.actor, preset=prepared.preset_id,
            launch_id=launch, host=None, port=None, pid=None,
        )  # fmt: skip
        started = time.monotonic()
        context.log(f"nothing starts on this machine: {model} runs at {label}; the gateway is handed the key")
    async with step("health"):
        try:
            said, usd = await context.run_blocking(_healthy, runtime, prepared, launch)
        except CloudError as error:
            slots._failed(context, name, launch, prepared.preset_id, f"{title}: {error}")
            from clank.components.runtime.slots import SlotError

            raise SlotError(f"{title}: {error}") from error
        context.log(said)
    async with step("measure"):
        seconds = round(time.monotonic() - started, 1)
        state.finish_launch(launch, "ready", seconds=seconds, cost_usd=usd)
        context.log(f"ready in {seconds:.1f} s; its tiny request cost {money(usd)}")
        state.set_slot(name, "ready", f"{title} answered in {seconds:.1f} s", actor=context.actor)
        state.remember_good(name, LastGood(preset=prepared.preset_id, options=dict(prepared.preset.options),
                                           time=state.now()))  # fmt: skip
    return {"slot": name, "preset": prepared.preset_id, "launch": launch, "seconds": seconds, "cost_usd": usd,
            "said": said}  # fmt: skip


def _healthy(runtime: "Runtime", prepared: CloudPrepared, launch: int) -> tuple[str, float]:
    """The key accepted, then the tiny request answered: what to say of it, and what it cost."""
    endpoints, adapter = runtime.endpoints, prepared.adapter
    id, model = prepared.preset.endpoint, prepared.model.id
    title = prepared.preset.title or prepared.preset_id
    try:
        key = endpoints.key(id, user="runtime", why=f"launch {launch}: {title}")
        account = endpoints.ask(id, key, "GET", KEY)
        if account.status_code != 200:
            raise CloudError(adapter.refusal(account.status_code, account.content, model=model).message)
        tiny = {"messages": [{"role": "user", "content": TINY_WORDS}], "max_tokens": TINY_TOKENS, "stream": False}
        sent, _ = adapter.translate(tiny, model, prepared.route["adds"])
        began = time.monotonic()
        answer = endpoints.ask(id, key, "POST", CHAT, body=sent, seconds=TINY_SECONDS)
    except ApiError as error:
        raise CloudError(str(error)) from error
    seconds = time.monotonic() - began
    denied = prepared.record.options.get("data_collection", "deny") == "deny"
    if answer.status_code != 200:
        raise CloudError(adapter.refusal(answer.status_code, answer.content, model=model, denied=denied).message)
    try:
        found = answer.json()
        text = str(found["choices"][0]["message"].get("content") or "").strip()
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
        raise CloudError(f"{adapter.LABEL}'s answer to a tiny request could not be read: {error}") from error
    cost = adapter.cost(found.get("usage"), {}, prepared.route["prices"])
    estimate = "≈ " if cost.how == "estimate" else ""
    return f"it answered a tiny request: {text} in {seconds:.1f} s, {estimate}{money(cost.usd)}", cost.usd


def stop(slots: "Slots", context: OperationContext, name: str, slot: SlotRecord, why: str) -> str:
    """Unload a cloud slot: nothing stops at the provider; the slot is stopped (the gateway forgets the key)."""
    state = slots.runtime.state
    assert slot.launch_id is not None
    launch = state.launch(slot.launch_id)
    label = _label(slots.runtime, launch.endpoint)
    said = f"nothing stops at {label}: requests already streaming finish, and the gateway forgets the key"
    state.set_slot(name, "stopping", why, actor=context.actor)
    state.finish_launch(slot.launch_id, "stopped", detail=said)
    context.log(said)
    state.set_slot(name, "stopped", f"{why} (nothing ran here)", actor=context.actor)
    return "nothing ran here"


def adopt(runtime: "Runtime", name: str, slot: SlotRecord) -> None:
    """A cloud slot after a restart of the service: kept ready while its record, agreement and key remain."""
    state = runtime.state
    assert slot.launch_id is not None
    launch = state.launch(slot.launch_id)
    title = runtime.title(slot.preset)
    if slot.status != "ready":
        state.finish_launch(slot.launch_id, "stopped", detail="the service's restart cut it short")
        state.set_slot(name, "stopped", "its load was cut short by the service's restart", actor=CLANK)
        return
    problems = _problems(runtime, slot)
    if problems:
        state.finish_launch(launch.id, "stopped", detail="; ".join(problems))
        state.set_slot(name, "stopped", f"stopped while the service was not running: {'; '.join(problems)}",
                       actor=CLANK)  # fmt: skip
        return
    label = _label(runtime, launch.endpoint)
    state.set_slot(name, "ready", f"adopted after the service started: {title} runs at {label}", actor=CLANK,
                   keep_since=True)  # fmt: skip


def watch(runtime: "Runtime", name: str, slot: SlotRecord) -> None:
    """Ask the provider whether it still takes the key (its account, which costs nothing): a refused key fails the
    slot; no answer leaves it ready, marked "not reached since"."""
    state = runtime.state
    assert slot.launch_id is not None
    launch = state.launch(slot.launch_id)
    id = launch.endpoint
    try:
        adapter = runtime.endpoints.adapter(id)
        key = runtime.endpoints.key(id, user="runtime", why=f"launch {launch.id}: is the key still taken")
        answer = runtime.endpoints.ask(id, key, "GET", KEY)
    except ApiError as error:
        if error.code == "cloud_unreachable":
            if not slot.reason.startswith("not reached since"):
                moment = state.now().astimezone().strftime("%H:%M")
                state.set_slot(name, "ready", f"not reached since {moment}: {error}", actor=CLANK, keep_since=True)
            return
        _fail(runtime, name, slot, str(error))
        return
    if answer.status_code == 401:
        said = f"{adapter.LABEL} refused the key: it may have been deleted; set a new one"
        _fail(runtime, name, slot, said)
    elif answer.status_code == 200 and slot.reason.startswith("not reached since"):
        state.set_slot(name, "ready", f"{adapter.LABEL} answers again", actor=CLANK, keep_since=True)


def _fail(runtime: "Runtime", name: str, slot: SlotRecord, said: str) -> None:
    assert slot.launch_id is not None
    runtime.state.finish_launch(slot.launch_id, "stopped", detail=said)
    runtime.state.set_slot(name, "failed", said, actor=CLANK, preset=slot.preset)


def _problems(runtime: "Runtime", slot: SlotRecord) -> list[str]:
    from clank.components.runtime.launching import preset_of
    from clank.components.runtime.service import PresetNotFound

    try:
        _, preset = preset_of(runtime, slot.preset or "")
    except PresetNotFound as error:
        return [str(error)]
    return runtime.endpoints.preset_problems(preset)


def _label(runtime: "Runtime", id: str) -> str:
    try:
        return runtime.endpoints.adapter(id).LABEL
    except ApiError:
        return id
