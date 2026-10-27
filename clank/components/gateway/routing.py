"""Where a request goes (design 0001 §6.1, steps 2 and 5; decision 0008): a role's slot, and the engine it runs now.

The gateway process keeps the service's last answer to `GET /api/v1/gateway/routes` and asks again every second; while
the service does not answer it keeps routing by what it last knew (design 0002 §1: a data-plane process keeps what was
already allowed). The answer gives, for each slot, its state, whether an operation is changing it, and, while an
engine runs, the engine's port, its adapter and version, the model name it answers to, the preset, and the preset's
context and output limits; and, for each role, its slot. A request for a role the routes do not name goes to the
default slot (decision 0008: the requested model name is the role, and an unknown name is the main one's).

Each slot's engine is counted (`generation`): the count moves whenever the slot's state, preset or port changes, so a
request that ended under one engine is known not to be held by the next (design 0012 §3: an engine that stopped,
started again after a crash or was switched holds no conversation). An operation queued for the slot (`busy`) alone
does not move it.

A slot a cloud model serves (design 0016 §7-§8) is served once the gateway holds its provider's key for its launch
(`keyed`, decision 0106): until then a request waits as for a starting slot.

A request waits (`ready`) while its slot is starting, stopping or being changed by an operation (a switch passes
through all three), up to the hold; a slot that is stopped or failed, with nothing changing it, refuses at once. A role
loaded on demand (`demand`, design 0008 §7: the vision model) is asked of the service first, which loads it, so its
request waits for the load instead.
"""

import hashlib
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import anyio

WAITING = ("starting", "stopping")
POLL_SECONDS = 0.1
SETTLE_SECONDS = 10.0  # the runtime notices an engine that ended within five seconds, the gateway a second later
NOTION_TOOLS = "clank_notion_"  # Clank's Notion tools, as OpenCode names them: never to a cloud model (design 0016 §10)
FRESH_SECONDS = 3.0  # routes older than this: the service does not answer, and the cloud waits for it (design 0016 §9)
NO_KEY = (
    "the gateway does not hold the key of {endpoint} yet: the Clank service hands it over while its model is loaded "
    "(is the service running?)"
)


@dataclass(frozen=True)
class SlotRoute:
    """A slot as the gateway sees it."""

    slot: str
    status: str
    busy: bool
    port: int | None
    engine: str | None
    version: str | None
    model_name: str | None
    preset: str | None
    title: str | None
    context: int | None
    output: int | None
    provider: str | None = None  # `engine`, or `endpoint` for a provider someone else runs (design 0016 §7)
    endpoint: str | None = None
    adapter: str | None = None
    base_url: str | None = None
    reach: str | None = None
    agreed: bool | None = None
    launch: int | None = None
    read_timeout: float | None = None
    adds: Mapping[str, Any] | None = None
    prices: Mapping[str, Any] | None = None

    @property
    def cloud(self) -> bool:
        """Whether a provider someone else runs serves it, reached at its URL (design 0016 §8)."""
        return self.provider == "endpoint"

    @property
    def serving(self) -> bool:
        """Whether an engine runs and answers in it, or a provider's model serves it."""
        if self.cloud:
            return self.status == "ready" and bool(self.base_url) and bool(self.endpoint)
        return self.status == "ready" and self.port is not None and self.engine is not None


class Routes:
    """The routes the gateway follows, as the service last gave them."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._raw: dict[str, Any] = {"slots": {}, "roles": {}, "default_slot": "main"}
        self._engines: dict[str, tuple[Any, ...]] = {}  # each slot's state, preset and port, as last given
        self._generations: dict[str, int] = {}
        self.updated = 0.0
        # Whether the gateway holds a cloud provider's key for a launch (design 0016 §5): a cloud route serves once it
        # does; none given, it never waits for one.
        self.keyed: Callable[[str, int | None], bool] | None = None
        self.followed = False  # whether the routes come from a service asked every second (`follow`)

    def workspace(self, key: str) -> dict[str, Any] | None:
        """The workspace a request names by its key (design 0016 §9), with its bound; None for a key Clank does not
        know (an OpenCode started before workspaces were named, a script)."""
        if not key:
            return None
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        with self._lock:
            found = self._raw.get("workspaces", {}).get(digest)
        return dict(found) if isinstance(found, dict) else None

    def workspace_named(self, name: str) -> dict[str, Any] | None:
        """A workspace's bound, by its name."""
        with self._lock:
            found = [dict(each) for each in self._raw.get("workspaces", {}).values() if each.get("workspace") == name]
        return found[0] if found else None

    def hosts_of(self, workspace: str) -> list[str] | None:
        """The hosts a workspace's agent may reach through the proxy (design 0024 §1), as the routes carry them; None
        for a workspace the routes do not name, which is allowed nothing."""
        with self._lock:
            found = (self._raw.get("network") or {}).get(workspace)
        if not isinstance(found, dict):
            return None
        return [str(each) for each in found.get("hosts") or []]

    def local_only(self) -> list[str]:
        """The names (prefixes) of the tools that never go to a cloud model (design 0016 §10): Clank's Notion tools
        always, whatever the routes name, and those the routes name."""
        with self._lock:
            named = [str(each) for each in self._raw.get("local_only") or []]
        return named if NOTION_TOOLS in named else [NOTION_TOOLS, *named]

    def local_only_given(self) -> bool:
        """Whether the service gave the tools that never go to a cloud model; false while its routes say they were
        not given yet, and then nothing goes to the cloud (routes no service gives, a test's, need not say)."""
        with self._lock:
            return bool(self._raw.get("local_only_given", True))

    def cost(self) -> dict[str, Any]:
        """The cloud's spending and limits as the service has them (design 0016 §12)."""
        with self._lock:
            return dict(self._raw.get("cost") or {})

    def stale(self) -> bool:
        """Whether the service's routes are older than `FRESH_SECONDS` (it does not answer); never for routes no
        service gives (a test's)."""
        return self.followed and time.monotonic() - self.updated > FRESH_SECONDS

    async def fresh(self, seconds: float) -> bool:
        """Wait up to `seconds` for the service's routes to be fresh again; whether they are (design 0016 §9: a cloud
        request is decided by what the service says now)."""
        deadline = time.monotonic() + seconds
        while self.stale():
            if time.monotonic() >= deadline:
                return False
            await anyio.sleep(POLL_SECONDS)
        return True

    def update(self, raw: Mapping[str, Any]) -> None:
        """Take the service's answer."""
        with self._lock:
            self._raw = {
                "slots": dict(raw.get("slots") or {}),
                "roles": dict(raw.get("roles") or {}),
                "default_slot": str(raw.get("default_slot") or "main"),
                "demand": dict(raw.get("demand") or {}),
                "workspaces": dict(raw.get("workspaces") or {}),
                "local_only": [str(each) for each in raw.get("local_only") or []],
                "local_only_given": bool(raw.get("local_only_given", True)),
                "cost": dict(raw.get("cost") or {}),
                "network": dict(raw.get("network") or {}),
            }
            slots: dict[str, Any] = self._raw["slots"]
            for name in {*slots, *self._engines}:
                found = slots.get(name) or {}
                engine = (found.get("status"), found.get("preset"), found.get("port"))
                if self._engines.get(name) != engine:
                    self._engines[name] = engine
                    self._generations[name] = self._generations.get(name, 0) + 1
            self.updated = time.monotonic()

    def generation(self, slot: str) -> int:
        """How many times the slot's engine changed (its state, preset or port) since the gateway started."""
        with self._lock:
            return self._generations.get(slot, 0)

    def demand(self, role: str) -> str:
        """How a role's model is loaded when it is loaded on demand (`off`, `on-demand`, `always`); "" for one the
        owner loads (design 0008 §7)."""
        with self._lock:
            return str(self._raw.get("demand", {}).get(role) or "")

    async def woken(self, role: str, seconds: float) -> None:
        """After asking the service for a role's model: until its slot serves or is changing, at most `seconds` (the
        routes are asked for every second)."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            found = self.route(role)
            if found is not None and (found.serving or found.busy or found.status in WAITING):
                return
            await anyio.sleep(POLL_SECONDS)

    def roles(self) -> list[str]:
        """The roles a tool can ask for, by name."""
        with self._lock:
            return sorted(self._raw["roles"])

    def route(self, role: str) -> SlotRoute | None:
        """The role's slot as it is now, or None when the routes name no such slot."""
        with self._lock:
            name = self._raw["roles"].get(role, self._raw["default_slot"])
            raw = self._raw["slots"].get(name)
        if raw is None:
            return None
        return SlotRoute(
            slot=name, status=str(raw.get("status") or "stopped"), busy=bool(raw.get("busy")), port=raw.get("port"),
            engine=raw.get("engine"), version=raw.get("version"), model_name=raw.get("model_name"),
            preset=raw.get("preset"), title=raw.get("title"), context=raw.get("context"), output=raw.get("output"),
            provider=raw.get("provider"), endpoint=raw.get("endpoint"), adapter=raw.get("adapter"),
            base_url=raw.get("base_url"),
            reach=raw.get("reach"), agreed=raw.get("agreed"), launch=raw.get("launch"),
            read_timeout=raw.get("read_timeout"), adds=raw.get("adds"), prices=raw.get("prices"),
        )  # fmt: skip

    def changing(self, role: str) -> bool:
        """Whether the role's slot is being changed now: starting, stopping, or an operation at work on it."""
        found = self.route(role)
        return found is not None and (found.busy or found.status in WAITING)

    def why(self, role: str, seconds: float) -> str:
        """Why the role's slot does not serve after a wait of `seconds`, in words that say what to do."""
        return _why(role, self.route(role), self.changing(role), seconds)

    async def ready(self, role: str, seconds: float) -> tuple[SlotRoute | None, str]:
        """The role's slot once an engine serves it: at once, or after waiting up to `seconds` while it starts,
        stops or is being changed; otherwise None, and why, in words that say what to do."""
        deadline = time.monotonic() + seconds
        while True:
            found = self.route(role)
            keyless = found is not None and found.serving and not found.busy and not self._keyed(found)
            if found is not None and found.serving and not found.busy and not keyless:
                return found, ""
            changing = found is not None and (found.busy or found.status in WAITING or keyless)
            if not changing or time.monotonic() >= deadline:
                if keyless and found is not None:
                    return None, f"{NO_KEY.format(endpoint=found.endpoint)} after {seconds:g} seconds"
                return None, _why(role, found, changing, seconds)
            await anyio.sleep(POLL_SECONDS)

    def _keyed(self, found: SlotRoute) -> bool:
        """Whether the route can be sent to: an engine's always; a cloud model's once its key is held."""
        return not found.cloud or self.keyed is None or self.keyed(str(found.endpoint), found.launch)

    async def recovered(self, role: str, seconds: float, broken: int | None = None) -> tuple[SlotRoute | None, str]:
        """After the role's engine broke off a request: the slot once an engine serves it again, waiting up to `seconds`
        while it is started again (or switched); None, and why, when it is not served again. A slot served by an
        engine on another port than the one that broke off (`broken`) is taken at once. A slot still served
        `SETTLE_SECONDS` later is taken as it is (its engine lived on, or another serves it); one that stops being
        served and stays neither served nor changing for `SETTLE_SECONDS` (nothing starts it again) is given up."""
        deadline = time.monotonic() + seconds
        settled = time.monotonic() + SETTLE_SECONDS
        went = False
        while time.monotonic() < deadline:
            found = self.route(role)
            moment = time.monotonic()
            if found is not None and found.serving and not found.busy:
                if went or moment >= settled or (broken is not None and found.port != broken):
                    return found, ""
            else:
                if not went or (found is not None and (found.busy or found.status in WAITING)):
                    settled = moment + SETTLE_SECONDS
                went = True
                if moment >= settled:
                    state = found.status if found is not None else "gone"
                    return None, f"its slot is {state} and nothing is starting it again (the Models page says why)"
            await anyio.sleep(POLL_SECONDS)
        return None, f"its slot was not served again within {seconds:g} seconds"


def _why(role: str, found: SlotRoute | None, changing: bool, seconds: float) -> str:
    if found is None:
        return f"no slot serves the role {role!r}; the gateway's routes name none (is the Clank service running?)"
    if changing:
        return f"the {found.slot} slot was still {found.status} after {seconds:g} seconds; try again when it is ready"
    return (
        f"no model runs in the {found.slot} slot ({found.status}): load one with `clank model load PRESET` "
        "(`clank preset list` shows them), or from the console's Presets page"
    )
