"""The runtime component's part (design 0003): the presets, the serving setups, the hosts, and (from M1.3) what each
slot runs.

Presets are read through the kernel's settings (decision 0007); a preset is found by its id (its file's name) or its
title, so `clank preset show "fast 64K"` and `.../presets/fast-64k` name the same one. Each preset as clients see it
carries its problems (`catalog.preset_problems`): what would stop it from running, before anything is planned.

The hosts (decision 0030) are this machine (`local`, always there) and each host record; a host is added only for a
WSL distribution WSL has. The runtime's state (slots, launches, installs) is in its own tables (`state.py`); the record
routes read those kinds through `read_records` and `read_record` (design 0002 §2.2).

A preset's facts (`facts`, design 0012 §4, decision 0067) are what the Monitor reads of the context window: its engine
adapter's context facts for the preset's options, and its model's template facts and calibration from the catalog; a
slot's route carries those of the preset it runs. A text is counted for a preset (`count_tokens`, decision 0087) by its
engine when the main slot runs that preset and the engine counts, else estimated and said so. What a slot's engine
last said of its drafting (`drafts`, design 0021 §3) is read from the end of its newest launch's log by its adapter.
"""

import math
from collections.abc import Callable, Mapping
from typing import Any

import httpx2

from clank.components.runtime import cloud, guide, launching
from clank.components.runtime.adapters import ENDPOINTS, ENGINES
from clank.components.runtime.adapters.endpoint import Cost
from clank.components.runtime.adapters.endpoint import Refusal as Refusal  # for the gateway (decision 0019)
from clank.components.runtime.adapters.engine import EngineError
from clank.components.runtime.catalog import ModelEntry, preset_problems
from clank.components.runtime.endpoints import Endpoints, record_problems
from clank.components.runtime.gpu import GpuMemory, gpu_memory
from clank.components.runtime.guide import machine_said as machine_said  # for the agents' guide (decision 0019)
from clank.components.runtime.hosts.host import EngineHost as EngineHost  # for the gateway (decision 0019)
from clank.components.runtime.hosts.host import ProcessIdentity as ProcessIdentity  # for the gateway (decision 0019)
from clank.components.runtime.hosts.local import LocalHost
from clank.components.runtime.hosts.wsl import WslHost
from clank.components.runtime.kinds import Host, Preset, RuntimeSettings
from clank.components.runtime.modelfiles import HUB_URL
from clank.components.runtime.recipes import Recipe, recipes
from clank.components.runtime.state import InstallRecord, LaunchRecord, RuntimeState, SlotRecord
from clank.kernel.adapters import AdapterError
from clank.kernel.api import ApiError
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from clank.kernel.settings import Loaded

LOCAL = {"name": "local", "adapter": "local", "distro": "", "clank_folder": "~/.clank", "source": "built-in"}
# Clank's plain estimate of a text's tokens, for a model with no calibration (decision 0087): about 3.3 characters a
# token, above what prose takes and near what code takes, so an estimate errs large.
PLAIN_TOKENS_PER_CHARACTER = 0.3
CALIBRATED_PART = "user"  # the part of a request whose calibration a message of the owner's, or a box's, takes
COUNT_SECONDS = 10  # how long the engine is given to count a text
LOG_TAIL = 64 * 1024  # the bytes at the end of an engine's log its newest figures are read from


class PresetNotFound(Exception):
    """No preset has that id or title."""


class HostNotFound(Exception):
    """No host has that name."""


ROUTE_FIELDS = (
    "status", "busy", "port", "engine", "version", "model_name", "preset", "title", "context", "output", "images",
    "thinking", "facts", "provider", "endpoint", "adapter", "base_url", "reach", "agreed", "launch", "read_timeout",
    "adds", "prices",
)  # fmt: skip


def translate_request(engine: str, version: str, body: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """A request as a serving setup's engine takes it (design 0001 §6.3): its adapter's own fields, a note for each
    change. The gateway's way to the adapters (decision 0019: a component uses another through its service)."""
    return ENGINES.get(engine)(version).translate(body)


def context_full(engine: str, version: str, status: int, body: bytes) -> bool:
    """Whether an engine's answer is its refusal of a request its context cannot hold (design 0012 §4.1, decision
    0090), by its adapter's words; never for an engine or version Clank does not know. The gateway's way to the
    adapters, as `translate_request`."""
    try:
        adapter = ENGINES.get(engine)(version)
    except (AdapterError, EngineError):
        return False
    return adapter.says_full(status, body)


def endpoint_request(
    adapter: str, body: Mapping[str, Any], model: str, adds: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """A request as a provider someone else runs takes it (design 0016 §8, decision 0109): as the tool sent it, its
    model the listed id, the record's and the preset's fields added where the tool set none; a note for each. The
    gateway's way to the endpoint adapters, as `translate_request` is to the engines'."""
    return ENDPOINTS.get(adapter)().translate(body, model, adds)


def endpoint_headers(adapter: str, key: str, session: str) -> dict[str, str]:
    """The headers of a request to a provider: its key, and the session for its cache."""
    return ENDPOINTS.get(adapter)().headers(key, session)


def endpoint_refusal(adapter: str, status: int, body: bytes, model: str, denied: bool) -> Refusal:
    """What a provider's refusal means, in words that say what to do, and whether OpenCode may retry it."""
    return ENDPOINTS.get(adapter)().refusal(status, body, model=model, denied=denied)


def endpoint_full(adapter: str, status: int, body: bytes) -> bool:
    """Whether a provider's refusal is the model's context being full (decision 0090), by its adapter's words."""
    try:
        return ENDPOINTS.get(adapter)().says_full(status, body)
    except AdapterError:
        return False


def endpoint_cost(adapter: str, usage: Mapping[str, Any] | None, tokens: Mapping[str, int], prices: Any) -> Cost:
    """A cloud request's cost: the provider's own figure in its usage, else an estimate from its tokens at the
    model's prices (design 0016 §12); an estimate at no price for a provider Clank does not know."""
    try:
        return ENDPOINTS.get(adapter)().cost(usage, tokens, prices if isinstance(prices, Mapping) else {})
    except AdapterError:
        return Cost(0.0, "estimate", dict(tokens))


def endpoint_label(adapter: str) -> str:
    """A provider's name as the owner reads it, such as OpenRouter."""
    try:
        return ENDPOINTS.get(adapter).LABEL
    except AdapterError:
        return adapter


class Runtime:
    """The runtime component, built on the kernel."""

    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel
        self.state = RuntimeState(kernel.store, kernel.events, kernel.clock)
        self.models: Mapping[str, ModelEntry] | None = None  # the catalog's, unless a test gives its own
        self.recipes: Mapping[tuple[str, str], Recipe] = recipes()  # Clank's own, unless a test gives its own
        self.model_url = HUB_URL  # where a model's file is downloaded from, unless a test serves its own
        self.read_gpu: Callable[[], GpuMemory | None] = gpu_memory
        self._hosts: dict[str, tuple[tuple[str, str], EngineHost]] = {}
        kernel.settings.check_with("endpoint", record_problems)  # a provider's record against its adapter
        self.endpoints = Endpoints(self)
        from clank.components.runtime.watching import Watcher

        self.watcher = Watcher(self)

    async def run(self) -> None:
        """While the service runs: adopt what the slots ran, then watch it (design 0003 §6.2-§6.3)."""
        await self.watcher.run()

    async def adopt(self) -> None:
        """What each slot ran before the service started: adopted when it still runs, else said."""
        await self.watcher.adopt()

    async def watch_once(self, health: bool | None = None) -> None:
        """Look at each ready slot once."""
        await self.watcher.watch_once(health)

    def route(self, name: str) -> dict[str, Any]:
        """A slot as the gateway routes to it (design 0004 §2): its state and whether an operation is changing it, and,
        while an engine runs, the engine's port, serving setup and version, the model name it answers to, the preset,
        and the preset's context and output limits, whether its model reads images (its `vision` option is not off,
        design 0008 §5), its thinking budget, when its engine has one and thinking is on (design 0012 §8), and the
        preset's facts (`facts`); and its provider (`engine`, reach `this-machine`). A cloud slot's (design 0016 §7) is
        its launch's kept route, its reach and agreement read now (`cloud.route`): the provider (`endpoint`), its base
        URL, the model's listed id, the read timeout, what the gateway adds to each request, the model's prices."""
        slot = self.state.slot(name)
        changing = ("runtime.load", "runtime.switch", "runtime.unload", "runtime.restart")
        busy = any(
            operation.type in changing and str(operation.params.get("slot") or "main") == name
            for operation in self.kernel.operations.find(limit=50)
            if operation.status in ("queued", "running", "waiting")
        )
        view: dict[str, Any] = dict.fromkeys(ROUTE_FIELDS)
        view.update(status=slot.status, busy=busy)
        if slot.status != "ready" or slot.preset is None:
            return {key: view[key] for key in ROUTE_FIELDS}
        kept = cloud.route(self, slot)
        if kept is not None:
            view.update({key: value for key, value in kept.items() if key in ROUTE_FIELDS})
            view.update(preset=slot.preset, title=self.title(slot.preset), facts=self.facts(slot.preset))
            return {key: view[key] for key in ROUTE_FIELDS}
        _, preset = launching.preset_of(self, slot.preset)
        adapter = ENGINES.get(preset.engine)(preset.engine_version)
        values = {option.key: preset.options.get(option.key, option.default) for option in adapter.options()}
        view.update(
            port=slot.port, engine=preset.engine, version=preset.engine_version, preset=slot.preset,
            model_name=self.settings().model_name or preset.model, title=preset.title or slot.preset,
            context=values.get("context"), output=values.get("max_output"),
            images=str(values.get("vision") or "off") != "off",
            thinking=values.get("thinking.budget") if values.get("thinking", True) else None,
            facts=self.facts(slot.preset), provider="engine", reach="this-machine",
        )  # fmt: skip
        return {key: view[key] for key in ROUTE_FIELDS}

    def facts(self, preset: str) -> dict[str, Any] | None:
        """A preset's facts, by its id or its title, as the Monitor reads them (design 0012 §4, decision 0067): its
        engine adapter's context facts for its options, with the engine's name, label and version, and its model's
        facts from the catalog (its template, its calibration); None for a preset, an engine or a model not known."""
        try:
            id, found = launching.preset_of(self, preset)
            if found.cloud:
                return self.endpoints.facts(id, found)
            model = launching.models(self).get(found.model)
            return None if model is None else preset_facts(id, found, model)
        except (PresetNotFound, AdapterError, EngineError, ValueError, TypeError):
            return None

    def drafts(self, slot: str) -> dict[str, Any] | None:
        """The drafts the engine a slot runs last said it proposed and had accepted (design 0021 §3), read from the end
        of its newest launch's log by its adapter; None for a slot never launched, an engine that does not say it, or
        a log that is gone."""
        record = self.state.slot(slot)
        if record.launch_id is None:
            return None
        launch = self.state.launch(record.launch_id)
        try:
            with open(launch.log, "rb") as log:
                log.seek(0, 2)
                log.seek(max(log.tell() - LOG_TAIL, 0))
                lines = log.read().decode("utf-8", errors="replace").splitlines()
            return ENGINES.get(launch.engine)(launch.engine_version).drafts(lines)
        except (OSError, AdapterError, EngineError):
            return None

    def count_tokens(self, preset: str, text: str) -> dict[str, Any]:
        """How many tokens `text` is for a preset's model (design 0013 §5, decision 0087), by its id or its title: its
        `tokens`, whether they are `exact`, and how they were `counted`. Counted by the engine only when the main slot
        runs that preset now and its engine counts (its adapter's `TOKENIZE`); else estimated from the model's
        calibration, else from Clank's plain default, saying why. Nothing is loaded to count."""
        rate, source, reasons = PLAIN_TOKENS_PER_CHARACTER, "Clank's plain default", []
        if not preset:
            return _estimate(text, rate, source, ["no preset named"])
        try:
            id, found = launching.preset_of(self, preset)
            if found.cloud:
                label = ENDPOINTS.get(self.endpoints.record(found.endpoint).adapter).LABEL
                said = f"the model runs at {label}, which counts no text before it is sent"
                return _estimate(text, rate, source, [said])
            adapter = ENGINES.get(found.engine)(found.engine_version)
        except (PresetNotFound, AdapterError, EngineError, ValueError, TypeError, ApiError):
            return _estimate(text, rate, source, [f"no preset {preset} that Clank can read"])
        model = launching.models(self).get(found.model)
        calibration = model.calibration if model is not None else None
        if model is not None and calibration is not None and calibration.tokens_per_character:
            per = calibration.tokens_per_character
            rate = per.get(CALIBRATED_PART, sum(per.values()) / len(per))
            source = f"{model.name}'s calibration ({calibration.measured})"
        elif model is not None:
            reasons.append(f"{model.name} has no calibration")
        title, engine = found.title or id, f"{adapter.LABEL} {found.engine_version}"
        slot = self.state.slot("main")
        if slot.status != "ready" or slot.preset != id or slot.port is None:
            reasons.append(f"the main slot does not run {title} now")
        elif not adapter.TOKENIZE:
            reasons.append(f"{engine} does not count tokens")
        else:
            try:
                answer = httpx2.post(
                    f"http://127.0.0.1:{slot.port}{adapter.TOKENIZE}", json={"content": text}, timeout=COUNT_SECONDS
                )
                answer.raise_for_status()
                tokens = len(answer.json()["tokens"])
                return {"tokens": tokens, "exact": True, "counted": f"counted by {engine}, which runs {title} now"}
            except (httpx2.HTTPError, ValueError, KeyError, TypeError) as error:
                reasons.append(f"{engine} did not count it: {error or type(error).__name__}")
        return _estimate(text, rate, source, reasons)

    def usable(self) -> dict[str, Any]:
        """Whether a model is usable (design 0016 §14, decision 0105): the main slot is ready, or a preset for it can
        load now (an engine preset whose engine is installed and whose model is downloaded on a host; a cloud preset
        whose provider is agreed and whose key is set); the main slot, and the presets that can load now, looked for
        only while the main slot is not ready: each engine preset asks its host for its model's files (through WSL,
        seconds each), and every `clank work`, `clank code` and console start waited 22-32 s on it with a model
        loaded."""
        slot = self.state.slot("main")
        views = {view["id"]: view for view in self.presets()}
        running = views.get(slot.preset or "")
        main = {
            "status": slot.status, "preset": slot.preset, "title": running["title"] if running else "",
            "provider": running["provider"] if running else "",
        }  # fmt: skip
        candidates = []
        for view in views.values() if slot.status != "ready" else ():
            if view["slot"] != "main" or view["problems"]:
                continue
            if not view["endpoint"]:
                try:
                    needs = self.needs(view["id"])
                except (PresetNotFound, HostNotFound, AdapterError, EngineError, ValueError):
                    continue
                if not (needs["engine"]["installed"] and needs["model"]["downloaded"]):
                    continue
            candidates.append({"preset": view["id"], "title": view["title"], "provider": view["provider"]})
        if slot.status == "ready":
            why = f"the main slot runs {main['title'] or slot.preset}"
        elif candidates:
            why = f"the main slot runs nothing; {len(candidates)} of its presets can load now"
        else:
            why = "no model runs in the main slot, and no preset for it can load here: add one (Add a model)"
        usable = slot.status == "ready" or bool(candidates)
        fallback = self.settings().fallback_preset  # what loads when none has worked yet (design 0016 §7)
        return {"usable": usable, "why": why, "main": main, "candidates": candidates, "fallback": fallback}

    def guide(
        self, *, servers: list[str], machine: str, docker: str, limits: dict[str, Any], preset: str = ""
    ) -> dict[str, Any]:
        """Add a model's steps and words (design 0016 §14, `GET /runtime/guide`): from the runtime's state, and what
        the part serving the route knows of the rest (the MCP servers, this computer, Docker, the limits); `preset`,
        once written, gives its test's and Ready's words."""
        slot = self.state.slot("main")
        written = None
        if preset:
            try:
                written = self.preset(preset)
            except PresetNotFound:
                written = None
        endpoints = self.endpoints.views()
        main = {"status": slot.status, "preset": slot.preset, "title": self.title(slot.preset) if slot.preset else ""}
        return guide.guide(self.usable(), endpoints[0] if endpoints else None, [{"name": name} for name in servers],
                           machine, docker, main, written, limits)  # fmt: skip

    def guide_local(self) -> dict[str, Any]:
        """Add a model's Local step: the main slot's presets, each with its words and what it still needs here."""
        found = []
        for preset in self.presets():
            if preset.get("slot", "main") != "main" or preset.get("endpoint"):
                continue
            try:
                steps = guide.local_steps(self.needs(preset["id"]), preset["id"])
            except (PresetNotFound, HostNotFound, AdapterError, EngineError, ValueError):
                continue
            try:
                plan: dict[str, Any] | None = launching.plan_view(self, preset["id"])
            except Exception:  # an unknown setup or a launch that cannot be planned: its words say so
                plan = None
            found.append({"id": preset["id"], "title": preset["title"], "said": guide.local_said(preset, plan, steps),
                          "steps": steps})  # fmt: skip
        return {"presets": found}

    def title(self, preset: str | None) -> str:
        """A preset's title, or its id when it is gone; "nothing" for none."""
        if preset is None:
            return "nothing"
        try:
            return str(self.preset(preset)["title"])
        except PresetNotFound:
            return preset

    def settings(self) -> RuntimeSettings:
        """How the runtime runs its engines, as the settings say now."""
        return RuntimeSettings.model_validate(self.kernel.settings.get("runtime", "runtime").record.model_dump())

    def read_records(self, kind: str) -> list[SlotRecord] | list[LaunchRecord] | list[InstallRecord] | None:
        """The records of one of the runtime's state kinds, for the record routes; None for another kind."""
        if kind == "slot":
            return self.state.slots(self.settings().slots)
        if kind == "launch":
            return self.state.launches()
        if kind == "install":
            return self.state.installs()
        return None

    def read_record(self, kind: str, id: str) -> SlotRecord | LaunchRecord | InstallRecord | None:
        """One record of one of the runtime's state kinds; `KeyError` when it does not exist; None for another kind."""
        if kind == "slot":
            if id not in self.settings().slots:
                raise KeyError(f"there is no slot {id}")
            return self.state.slot(id)
        if kind == "launch":
            if not id.isdigit():
                raise KeyError(f"there is no launch {id}")
            return self.state.launch(int(id))
        if kind == "install":
            found = next((install for install in self.state.installs() if install.id == id), None)
            if found is None:
                raise KeyError(f"there is no install {id}")
            return found
        return None

    def presets(self) -> list[dict[str, Any]]:
        """Every preset, Clank's own and the user's, as clients show them."""
        known = launching.models(self)
        return [_preset_view(self, loaded, known) for loaded in self.kernel.settings.records("preset")]

    def needs(self, name: str) -> dict[str, Any]:
        """What a preset needs on the host it would run on, and whether each is there (design 0006 §6): its engine
        installed (and whether Clank has a recipe to install it), and its model's files downloaded there (each file it
        reads: its weights, and its projector when it reads images). The host is
        the preset's own, else the one its engine is installed on, else the first that runs an engine reading the same
        format (only that host is asked about the file). A cloud preset needs nothing here (design 0016 §7)."""
        view = self.preset(name)
        if view["endpoint"]:
            return _cloud_needs(self, view)
        engine = ENGINES.get(view["engine"])
        setup = (view["engine"], view["engine_version"])
        installs = [each for each in self.state.installs() if (each.setup, each.version) == setup]
        known = {adapter.NAME for adapter in ENGINES.all()}
        readers = sorted(
            each.host
            for each in self.state.installs()
            if each.setup in known and ENGINES.get(each.setup).FORMAT == engine.FORMAT
        )
        host_name = view["host"] or (installs[0].host if installs else (readers[0] if readers else ""))
        model = launching.models(self).get(view["model"])
        file = model.file(engine.FORMAT) if model is not None else None
        roles = launching.files_read(engine(view["engine_version"]), view["options"])
        files = []
        for role in roles:
            each = model.file(engine.FORMAT, role) if model is not None else None
            if each is None:
                continue
            present = False
            if host_name:
                try:
                    host = self.host(host_name)
                    present = host.size(launching.file_place(self, view["model"], each, host_name, host)) == each.size
                except HostNotFound:
                    present = False
            files.append({"role": role, "path": each.path, "size": each.size, "downloaded": present})
        downloaded = all(each["downloaded"] for each in files if each["role"] == "weights") and bool(files)
        return {
            "preset": view["id"],
            "title": view["title"],
            "host": host_name,
            "engine": {
                "setup": view["engine"], "version": view["engine_version"], "label": engine.LABEL,
                "installed": any(each.host == host_name for each in installs), "recipe": setup in self.recipes,
            },
            "model": {
                "id": view["model"], "name": model.name if model is not None else view["model"],
                "format": engine.FORMAT, "role": file.role if file is not None else "weights",
                "size": file.size if file is not None else None, "downloaded": downloaded,
                "files": files,
            },
            "problems": view["problems"],
        }  # fmt: skip

    def preset(self, name: str) -> dict[str, Any]:
        """The preset whose id or title is `name`; `PresetNotFound` when none is."""
        wanted = name.strip().lower()
        for loaded in self.kernel.settings.records("preset"):
            if wanted in (loaded.id.lower(), str(loaded.record.model_dump().get("title", "")).lower()):
                return _preset_view(self, loaded, launching.models(self))
        raise PresetNotFound(f"there is no preset named {name!r}; `clank preset list` lists them")

    def engines(self) -> list[dict[str, Any]]:
        """Every serving setup Clank has an adapter for: the versions it knows, where each is installed and how, and
        the versions Clank has a recipe for."""
        installs = self.state.installs()
        return [
            {
                "name": adapter.NAME,
                "label": adapter.LABEL,
                "program": adapter.PROGRAM,
                "format": adapter.FORMAT,
                "versions": [version.name for version in adapter.VERSIONS],
                "installs": [
                    {"version": found.version, "host": found.host, "how": found.how, "folder": found.folder}
                    for found in installs
                    if found.setup == adapter.NAME
                ],
                "recipes": sorted(version for setup, version in self.recipes if setup == adapter.NAME),
            }
            for adapter in ENGINES.all()
        ]

    def hosts(self) -> list[dict[str, Any]]:
        """This machine, then each host record."""
        found = [dict(LOCAL)]
        for loaded in self.kernel.settings.records("host"):
            host = Host.model_validate(loaded.record.model_dump())
            found.append(
                {
                    "name": loaded.id,
                    "adapter": host.adapter,
                    "distro": host.distro,
                    "clank_folder": host.clank_folder,
                    "source": loaded.source,
                }
            )
        return found

    def host(self, name: str) -> EngineHost:
        """The host of that name: this machine, or a host record's; made once while its record stays the same, so what
        it learned (a WSL host's home folder) is asked of WSL once."""
        for found in self.hosts():
            if found["name"] != name:
                continue
            key = (found["adapter"], found["distro"])
            made = self._hosts.get(name)
            if made is not None and made[0] == key:
                return made[1]
            host: EngineHost = (
                WslHost(distro=found["distro"], name=name) if found["adapter"] == "wsl" else LocalHost(name)
            )
            self._hosts[name] = (key, host)
            return host
        raise HostNotFound(f"there is no host named {name!r}; `clank host list` lists them")

    def add_host(
        self, id: str, adapter: str, *, distro: str = "", clank_folder: str = "~/.clank", actor: Actor
    ) -> dict[str, Any]:
        """Write a host record; a WSL host only for a distribution WSL has."""
        if adapter == "wsl":
            have = WslHost.distributions()
            if distro not in have:
                listed = ", ".join(have) or "none"
                raise ValueError(f"WSL has no distribution named {distro}; it has {listed}")
        values = {"adapter": adapter, "distro": distro, "clank_folder": clank_folder}
        self.kernel.settings.write("host", id, values, base=None, actor=actor)
        return next(found for found in self.hosts() if found["name"] == id)

    def operation_types(self) -> list[Any]:
        """Loading, unloading and switching a slot (design 0003 §6.1); installing an engine (§7.1); downloading and
        adopting a model's file (§7.2)."""
        from clank.components.runtime import checking, installing, modelfiles, slots

        return [
            *slots.operation_types(self), *installing.operation_types(self), *modelfiles.operation_types(self),
            *checking.operation_types(self),
        ]  # fmt: skip

    def check(self, name: str) -> list[launching.CheckItem]:
        """The check of a preset, item by item; it starts nothing (design 0003 §6.5)."""
        return launching.check(self, name)

    def router(self) -> Any:
        """The runtime's routes."""
        from clank.components.runtime.api import router

        return router(self)


def _estimate(text: str, rate: float, source: str, reasons: list[str]) -> dict[str, Any]:
    """A text's tokens estimated at `rate` tokens per character, labeled as an estimate, with how and why."""
    why = f" ({'; '.join(reasons)})" if reasons else ""
    counted = f"an estimate: {rate:g} tokens per character, {source}{why}"
    return {"tokens": math.ceil(len(text) * rate), "exact": False, "counted": counted}


def _cloud_needs(runtime: Runtime, view: Mapping[str, Any]) -> dict[str, Any]:
    """What a cloud preset needs here: nothing installed or downloaded, its model running at its provider."""
    try:
        label = ENDPOINTS.get(runtime.endpoints.record(view["endpoint"]).adapter).LABEL
    except (ApiError, AdapterError):
        label = str(view["endpoint"])
    return {
        "preset": view["id"], "title": view["title"], "host": "", "endpoint": view["endpoint"],
        "engine": {"setup": "", "version": "", "label": label, "installed": True, "recipe": False},
        "model": {"id": view["model"], "name": view["model"], "format": "", "role": "weights", "size": None,
                  "downloaded": True, "files": []},
        "cloud": f"nothing to install or download: the model runs at {label}",
        "problems": view["problems"],
    }  # fmt: skip


def preset_facts(id: str, preset: Preset, model: ModelEntry) -> dict[str, Any]:
    """A preset's facts (`Runtime.facts`): its engine adapter's context facts for its options, with the engine's name,
    label and version, and its model's facts; raises what the adapters raise for an engine or options not known."""
    adapter = ENGINES.get(preset.engine)(preset.engine_version)
    context = adapter.context_facts(preset.options)
    engine = {"name": preset.engine, "label": adapter.LABEL, "version": preset.engine_version, **context.view()}
    return {"preset": id, "title": preset.title or id, "engine": engine, "model": model.facts_view()}


def _preset_view(runtime: Runtime, loaded: Loaded, known: Mapping[str, ModelEntry]) -> dict[str, Any]:
    """A preset as clients show it: its values, where it comes from, its provider (its engine and version, or `cloud`
    and its provider), a cloud preset's prices and its settings as a form changes them (design 0016 §7), its problems,
    and the sampling it gives its engine (design 0003 §4.1; none for a cloud preset, which starts no engine)."""
    values = loaded.record.model_dump(mode="json")
    record = Preset.model_validate(loaded.record.model_dump())
    title = values.pop("title", "") or loaded.id
    view = {"id": loaded.id, "title": title, **values, "source": loaded.source, "file": str(loaded.path)}
    if record.cloud:
        extras = runtime.endpoints.preset_extras(record)
        price = extras["price"]
        view.update(provider=f"cloud {record.endpoint}", price=price, settings=extras["settings"])
        if price is not None:
            view["price_said"] = f"{guide.per_million(price)} per million tokens"
        return {**view, "problems": runtime.endpoints.preset_problems(record), "sampling": []}
    view["provider"] = f"{record.engine} {record.engine_version}"
    return {**view, "problems": preset_problems(record, known), "sampling": launching.sampling_view(record)}
