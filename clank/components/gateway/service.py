"""The gateway component's part in the service (design 0001 §6.6, design 0004 §2): it keeps the gateway's process
running, and tells it where each role's requests go.

The gateway is a process of its own (`server.py`), started on this machine like an engine on the local host, in a
session of its own and without a window, its output in `logs/gateway.log`; its identity (process id, start, command
line) is kept in `state/gateway.json`, so after a restart of the service the one still running is adopted, not started
again, and a restart of the service cuts no request in flight. While the service runs it checks every few seconds that
the gateway runs, and starts it when it does not (unless its settings say not to); a port another program holds is
said, never taken. The state file is changed through the kernel's `files` (Windows refuses a delete or a replace while
a reader holds the file a moment): a stop that cannot delete it leaves it naming the process that ended, which says
stopped; a start that cannot write it keeps the process in memory, so it is never started twice, and writes it at the
next look. `restart` is never half done: whatever its stop met, a start is tried, and what went wrong is said in the
status it answers (`problem`). `activity` asks the gateway what it does now, for the console. The vision model (design
0008 §7) is loaded when the gateway says it is wanted (`wanted`), and kept as its mode says (`keep_vision`: loaded when
always, unloaded when off, and after its idle minutes when on demand). `routes` is what the gateway asks for every
second: each slot as the runtime reports it (`Runtime.route`) and the roles (`agent` is the main slot's, and any other
name too; `completion` is the fast slot's, design 0006; `vision` the vision slot's, loaded on demand), each with its
preset's facts (design 0012 §4), and what the agent's proxy follows (each workspace's hosts, and the runtime's dev mode,
decision 0152); `facts` gives any preset's. `completion` asks the gateway for its last
completions, for the CPU models page. `pause`, `resume` and `release` set a session's pause in the gateway (design 0012
§9.4, decision 0055), with the service's local token, which the gateway's routes for it take (decision 0084); `holds`
says what is paused and held.

On Linux the gateway also listens on a socket, `gateway.sock`, in a folder of its own outside CLANK_HOME (design 0014
§3, decision 0071, `sockets.py`): its start names the folder, checked and made the owner's alone; its status names the
socket (`socket`), or says why it has none (`socket_problem`); a gateway that runs without it (one started before it
had one, adopted as it is, or one whose folder was removed) is started again once no request is in flight
(`keep_socket`), once. `socket_path` and `edge_socket` tell the workspaces component where the edge reaches it.
"""

import base64
import contextlib
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

import anyio
import anyio.to_thread
import httpx2

from clank.components.gateway import sockets
from clank.components.gateway.activity import AGAIN as AGAIN  # the phases its activity says (the Monitor's Now)
from clank.components.gateway.activity import ANSWERING as ANSWERING
from clank.components.gateway.activity import HELD as HELD
from clank.components.gateway.activity import READING as READING
from clank.components.gateway.activity import WAITING as WAITING
from clank.components.gateway.bounds import Bounds
from clank.components.gateway.costs import Costs
from clank.components.gateway.kinds import CompletionSettings, CostSettings, GatewaySettings, VisionSettings
from clank.components.gateway.proxy import HOLD_SECONDS as HOLD_SECONDS  # the workspaces' ask reads these three
from clank.components.gateway.proxy import allowed_host as allowed_host  # through this service (design 0024 §3)
from clank.components.gateway.proxy import network_token as network_token
from clank.components.gateway.routing import NOTION_TOOLS
from clank.components.gateway.sockets import GATEWAY_SOCKET as GATEWAY_SOCKET  # the edge's ways in (design 0014 §3)
from clank.components.gateway.sockets import PROXY_SOCKET as PROXY_SOCKET
from clank.components.gateway.sockets import SocketFolderError as SocketFolderError
from clank.components.runtime.service import ProcessIdentity
from clank.kernel import files
from clank.kernel.access import local_token
from clank.kernel.clock import to_text
from clank.kernel.core import Kernel
from clank.kernel.events import Actor, EventType, Subject

if TYPE_CHECKING:
    from clank.components.runtime.service import EngineHost, Runtime

log = logging.getLogger(__name__)
WATCH_SECONDS = 5.0
DUE_SECONDS = 0.25  # how soon a change of a slot or a key reaches the gateway's keys
SPEND_SECONDS = 2.0  # how often the gateway's spool of cloud requests is taken (design 0016 §12)
STOP_SECONDS = 5.0
FREE_SECONDS = 15.0  # how long a restart waits for the stopped gateway's port to be free
FREE_POLL_SECONDS = 0.25  # how often it looks
ASK_SECONDS = 2.0  # how long the gateway is given to say what it does
LOOK_SECONDS = 300.0  # the vision model may be loaded first (design 0008 §7)
ROLES = {"agent": "main", "completion": "fast", "vision": "vision"}
VISION = Actor(kind="clank", via="vision")
GATEWAY_ACTOR = Actor(kind="clank", via="gateway")
EVENT_TYPES = [
    EventType(
        "gateway.cloud_wanted",
        "The gateway holds a request of a workspace not yet answered whether it may use the cloud model (design 0016 "
        "§9): the workspace's question is asked.",
        {"workspace": "The workspace.", "session": "The session whose request is held."},
        owner="gateway",
    ),
    EventType(
        "gateway.cloud_refused",
        "A cloud request was refused: by Clank (the workspace kept local, local-only content, the service silent) or "
        "by the provider (its key, credits, a budget, the model, a limit of requests, the data policy); at most one a "
        "minute for each workspace and code (design 0016 §8-§10).",
        {
            "workspace": "The workspace, when known.",
            "session": "The session, when known.",
            "code": "Clank's code for it, such as model_send_denied, local_only, service_silent, key_refused, "
            "no_credits, rate_limited.",
            "status": "Its HTTP status.",
        },
        owner="gateway",
        attention=True,
    ),
    EventType(
        "gateway.cost",
        "What the cloud cost changed (design 0016 §11-§12): today's and this month's totals, this computer's days; at "
        "most every five seconds while they change.",
        {
            "today_usd": "Today's, in US dollars.",
            "month_usd": "This month's, in US dollars.",
            "estimated_usd": "The part of this month's still an estimate.",
        },
        owner="gateway",
    ),
    EventType(
        "gateway.limit_warned",
        "The cloud's spending reached the share of a limit that warns (80%): told once a period (design 0016 §11).",
        {"by": "day or month.", "spent_usd": "What was spent, in US dollars.", "limit_usd": "The limit."},
        owner="gateway",
        attention=True,
    ),
    EventType(
        "gateway.limit_reached",
        "A spending limit was reached: each new cloud request is held, and the owner is asked to raise it (design "
        "0016 §11).",
        {
            "by": "day or month.",
            "spent_usd": "What was spent, in US dollars.",
            "limit_usd": "The limit.",
            "question": "The question that asks to raise it.",
        },
        owner="gateway",
        attention=True,
    ),
    EventType(
        "gateway.limit_raised",
        "The cloud goes on: a limit was raised, or its day or month ended (design 0016 §11).",
        {"by": "day or month.", "limit_usd": "The limit now.", "who": "Who raised it, or that the period ended."},
        owner="gateway",
    ),
]


NOT_PAUSED = "not_paused"  # the gateway's code for resuming a session that is not paused
OLDER = ("the gateway that runs is from before pausing (it has no holds): restart it (clank gateway restart) and pause "
         "again")  # fmt: skip


class HoldError(Exception):
    """A pause the gateway could not set or end, and why."""


class Gateway:
    """The gateway component, built on the kernel."""

    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel
        self.problem = ""
        self._lock = threading.Lock()
        self._unsaved: dict[str, Any] | None = None  # the process started, while its state file cannot be written
        self._used: float | None = None  # when the vision model was last wanted (design 0008 §7)
        self.keys_due = threading.Event()  # a slot or a key changed: the keys the gateway holds are looked at soon
        self.bounds = Bounds(kernel)  # each workspace's key at the gateway, and how far its requests may go
        self._local_only: list[str] | None = None  # the tools never sent to the cloud, as the agents component gives
        self.costs = Costs(self)  # what the cloud cost, taken from the gateway's spool (design 0016 §12)
        self._socket_again: int | None = None  # the process started again for its socket (design 0014 §3)
        kernel.events.subscribe(self._heard)

    def _heard(self, event: Any) -> None:
        """A slot changed, or a provider's key was set or removed: the gateway's keys are looked at again soon."""
        scope = str(event.data.get("scope") or "") if isinstance(event.data, dict) else ""
        if event.type == "runtime.slot" or (event.type.startswith("secret.") and scope.startswith("endpoint/")):
            self.keys_due.set()

    def sync_keys(self) -> list[dict[str, Any]]:
        """Hand the gateway the key of each provider whose model a slot runs, for its launch, and take back the others
        (design 0016 §5, decision 0106): read through the kernel (`user=\"gateway\"`, its launch the reason: one
        `secret.used`), put to the gateway behind the local token, never written anywhere. A key held for another
        launch, or set before the one kept now, is handed again. The keys the gateway holds after; none when it does not
        run or answer."""
        self.keys_due.clear()
        wanted: dict[str, tuple[int | None, str]] = {}
        for name in self.runtime.settings().slots:
            route = self.runtime.route(name)
            if route.get("provider") == "endpoint" and route.get("endpoint"):
                wanted[str(route["endpoint"])] = (route.get("launch"), str(route.get("title") or route.get("preset")))
        try:
            held = {each["endpoint"]: each for each in self._keys("GET", "").json().get("keys") or []}
        except HoldError:
            return []
        for endpoint, (launch, title) in wanted.items():
            shown = next(
                (each for each in self.kernel.secrets.shown(f"endpoint/{endpoint}") if each.name == "key"), None
            )
            if shown is None:
                continue
            have = held.get(endpoint)
            if have is not None and have.get("launch") == launch and have.get("set") == shown.set:
                continue
            value = self.kernel.secrets.value(
                f"endpoint/{endpoint}", "key", user="gateway", why=f"launch {launch}: {title}"
            )
            self._keys("PUT", endpoint, {"key": value, "launch": launch, "set": shown.set})
        for endpoint in held:
            if endpoint not in wanted:
                self._keys("DELETE", endpoint)
        try:
            found: list[dict[str, Any]] = self._keys("GET", "").json().get("keys") or []
        except HoldError:
            return []
        return found

    def take_spend(self) -> int:
        """Take the gateway's spool of cloud requests into the service's table (none twice); how many were new."""
        return self.costs.take()

    def price_generations(self) -> int:
        """Make each estimate exact from the provider's record of it, once its time comes; how many were."""
        return self.costs.price_generations()

    def cost_requests(self, **wanted: Any) -> list[dict[str, Any]]:
        """Each cloud request's cost, newest first (`Costs.requests`)."""
        return self.costs.requests(**wanted)

    def cost(self, workspace: str = "") -> dict[str, Any]:
        """What the cloud cost today and this month, against the limits, and whether it is paused (design 0016 §11);
        asked for a workspace, its own too."""
        return self.costs.view(workspace)

    def cost_sessions(self, **wanted: Any) -> list[dict[str, Any]]:
        """Each session's cloud cost, its subagents' counted in (`Costs.sessions`)."""
        return self.costs.sessions(**wanted)

    def cost_for(self, boxes: dict[str, list[str]]) -> dict[str, Any] | None:
        """What a flow's boxes cost, by their sessions (the flows component's way to the costs); None for none."""
        return self.costs.for_sessions(boxes)

    def cost_settings(self) -> CostSettings:
        """The cloud's spending limits, as `config/cost.json` says now."""
        return CostSettings.model_validate(self.kernel.settings.get("cost", "cost").record.model_dump())

    def set_limits(self, values: dict[str, Any], *, actor: Actor) -> dict[str, Any]:
        """Change the daily or monthly limit (None removes it), recorded with who did it; the cost view after."""
        loaded = self.kernel.settings.get("cost", "cost")
        record = {**loaded.record.model_dump(), **values}
        self.kernel.settings.write("cost", "cost", record, base=loaded.revision, actor=actor)
        self.costs.check_limits(who=actor.describe())
        return self.cost()

    def ask_gateway(
        self, method: str, path: str, *, params: dict[str, str] | None = None, body: dict[str, Any] | None = None
    ) -> httpx2.Response:
        """One of the gateway's routes that only the service calls, with its local token; a refusal or no answer as
        `HoldError`."""
        status = self.status()
        if status["state"] != "running":
            raise HoldError(status["problem"] or "the gateway does not run")
        try:
            answer = httpx2.request(method, f"http://127.0.0.1:{status['port']}{path}", params=params, json=body,
                                    headers=self._token(), timeout=ASK_SECONDS)  # fmt: skip
        except httpx2.HTTPError as error:
            raise HoldError(f"the gateway did not answer: {error}") from error
        if answer.status_code >= 400:
            raise HoldError(f"the gateway refused: {_said(answer).get('message') or answer.status_code}")
        return answer

    def _token(self) -> dict[str, str]:
        """The service's local token, as the gateway's routes that are the owner's take it (design 0015 §10)."""
        return {"Authorization": f"Bearer {local_token(self.kernel.home)}"}

    def _keys(self, method: str, endpoint: str, body: dict[str, Any] | None = None) -> httpx2.Response:
        """Ask the gateway's keys, with the service's local token; a refusal or no answer as `HoldError`."""
        status = self.status()
        if status["state"] != "running":
            raise HoldError(status["problem"] or "the gateway does not run")
        named = f"/{quote(endpoint, safe='')}" if endpoint else ""
        url = f"http://127.0.0.1:{status['port']}/keys{named}"
        token = local_token(self.kernel.home)
        try:
            answer = httpx2.request(method, url, json=body, headers={"Authorization": f"Bearer {token}"},
                                    timeout=ASK_SECONDS)  # fmt: skip
        except httpx2.HTTPError as error:
            raise HoldError(f"the gateway did not answer: {error}") from error
        if answer.status_code >= 400:
            raise HoldError(f"the gateway refused: {_said(answer).get('message') or answer.status_code}")
        return answer

    @property
    def runtime(self) -> "Runtime":
        """The runtime, whose slots the gateway routes to."""
        found: Runtime = self.kernel.parts["runtime"]
        return found

    def settings(self) -> GatewaySettings:
        """How the gateway runs, as the settings say now."""
        return GatewaySettings.model_validate(self.kernel.settings.get("gateway", "gateway").record.model_dump())

    def completion_settings(self) -> CompletionSettings:
        """How completion in VS Code works, as the settings say now."""
        return CompletionSettings.model_validate(
            self.kernel.settings.get("completion", "completion").record.model_dump()
        )

    def completion(self) -> dict[str, Any]:
        """Completion as the console's page and VS Code show it (design 0006 §6): its settings; the fast slot (its
        state, its preset); what that preset (else Clank's first preset for the slot) needs on its host and whether
        each is there; the gateway's address; and its last completions, counted (none when it does not answer, and
        why)."""
        slot_name = ROLES["completion"]
        slot = next(each for each in self.runtime.state.slots(self.runtime.settings().slots) if each.name == slot_name)
        preset = slot.preset or next(
            (each["id"] for each in self.runtime.presets() if each["slot"] == slot_name and not each["problems"]), None
        )
        status = self.status()
        counts, problem = None, ""
        if status["state"] == "running":
            try:
                answer = httpx2.get(
                    f"http://127.0.0.1:{status['port']}/completion", headers=self._token(), timeout=ASK_SECONDS
                )
                answer.raise_for_status()
                counts = answer.json()
            except (httpx2.HTTPError, ValueError) as error:
                problem = f"the gateway did not count its completions: {error}"
        else:
            problem = status["problem"] or "the gateway does not run"
        return {
            "settings": self.completion_settings().model_dump(mode="json"),
            "slot": slot.model_dump(mode="json"),
            "title": self.runtime.title(slot.preset) if slot.preset else "",
            "needs": self.runtime.needs(preset) if preset and slot.status != "ready" else None,
            "url": f"http://127.0.0.1:{status['port']}/v1",
            "counts": counts,
            "problem": problem,
        }

    def set_completion(self, values: dict[str, Any], *, actor: Actor) -> dict[str, Any]:
        """Change how completion works (any of on, its wait, its lines); the view after."""
        loaded = self.kernel.settings.get("completion", "completion")
        record = {**loaded.record.model_dump(), **values}
        self.kernel.settings.write("completion", "completion", record, base=loaded.revision, actor=actor)
        return self.completion()

    def routes(self) -> dict[str, Any]:
        """Where each role's requests go, as the gateway's process asks for it; how the role loaded on demand is (the
        vision model's mode, design 0008 §7); and what the agent's proxy follows: each workspace's hosts, and whether
        dev mode is on (decision 0152: every public host goes out)."""
        settings = self.runtime.settings()
        slots = {name: self.runtime.route(name) for name in settings.slots}
        demand = {"vision": self.vision_settings().mode} if "vision" in slots else {}
        return {
            "slots": slots, "roles": dict(ROLES), "default_slot": "main", "demand": demand,
            "workspaces": self.bounds.routes(), "local_only": self.local_only(),
            "local_only_given": self._local_only is not None, "cost": self.costs.routes(),
            "network": self.network_routes(), "dev_mode": settings.dev_mode,
        }  # fmt: skip

    def network_log(self, limit: int = 30, workspace: str = "") -> dict[str, Any]:
        """The agent's newest internet exchanges (design 0024 §4), of one workspace when named, and today's bytes by
        host, from the network log the gateway's process writes."""
        from clank.components.gateway.proxy import NetworkLog

        log = NetworkLog(self.kernel.home.logs / "network", today=lambda: self.kernel.clock.now().astimezone().date())
        return {"exchanges": log.recent(max(1, min(limit, 500)), workspace), "by_host": log.by_host()}

    def network_hosts(self) -> dict[str, dict[str, str]]:
        """The hosts each workspace's agent may reach through the proxy, with when and how each was allowed."""
        return {
            loaded.id: dict(loaded.record.model_dump().get("hosts") or {})
            for loaded in self.kernel.settings.records("workspace")
        }

    def network_routes(self) -> dict[str, dict[str, Any]]:
        """Each workspace's hosts allowed through the proxy (design 0024 §1), from its record, as the gateway's
        routes carry them."""
        return {
            loaded.id: {"hosts": sorted(loaded.record.model_dump().get("hosts") or {})}
            for loaded in self.kernel.settings.records("workspace")
        }

    def local_only(self) -> list[str]:
        """The tools that never go to a cloud model (design 0016 §10), by their prefixes: Clank's Notion tools always,
        and those the agents component gave."""
        given = [each for each in self._local_only or [] if each != NOTION_TOOLS]
        return [NOTION_TOOLS, *given]

    def set_local_only(self, prefixes: list[str]) -> None:
        """The names of the tools that never go to a cloud model (design 0016 §10), by their prefixes, as the agents
        component gives them (decision 0019: the gateway uses no tools component); the next routes carry them."""
        self._local_only = list(prefixes)

    def workspace_key(self, workspace: str, *, why: str) -> str:
        """A workspace's key at the gateway (design 0016 §9), made the first time it is asked for; read through the
        kernel, recorded with why (the agents component writes it into OpenCode's configuration and Clank's MCP
        server's environment). Every workspace has one, a cloud provider agreed or not: the agent's calls through the
        gateway to Notion, its flow and the agents' part act for the workspace their key names, and are refused
        without one (`agentcalls.py`)."""
        return self.bounds.key(workspace, why=why)

    def set_bound(self, workspace: str, **values: Any) -> None:
        """A workspace's bound (`models`), whether it was answered (`answered`, True for now) and its open question
        (`question`), as the workspaces component gives them; the next routes carry them."""
        self.bounds.set(workspace, **values)

    def bound(self, workspace: str) -> dict[str, Any] | None:
        """A workspace's bound as the routes carry it; None before its key is made."""
        return self.bounds.view(workspace)

    def cloud_wanted(self, workspace: str, session: str) -> dict[str, Any]:
        """The gateway holds a request of a workspace not yet answered (design 0016 §9, decision 0112): the event
        `gateway.cloud_wanted`, on which the workspaces component asks the workspace's question; the question, or
        whether the workspace is already allowed or kept local."""
        bound = self.bound(workspace) or {}
        if bound.get("models") == "cloud":
            return {"question": None, "allowed": True}
        if bound.get("answered"):
            return {"question": None, "allowed": False}
        if not bound.get("question"):
            self.kernel.events.record(
                "gateway.cloud_wanted",
                summary=f"the gateway holds a request of {workspace}, which may not use the cloud model yet",
                actor=GATEWAY_ACTOR,
                subject=Subject(kind="workspace", id=workspace),
                data={"workspace": workspace, "session": session},
            )
            bound = self.bound(workspace) or {}
        return {"question": bound.get("question")}

    def facts(self, preset: str) -> dict[str, Any] | None:
        """A preset's facts, its engine's and its model's (`Runtime.facts`, design 0012 §4): what the Monitor reads of
        a step a preset answered, though the slot may run another now; None for a preset not known."""
        return self.runtime.facts(preset)

    def vision_settings(self) -> VisionSettings:
        """The model that reads images, as the settings say now."""
        return VisionSettings.model_validate(self.kernel.settings.get("vision", "vision").record.model_dump())

    async def wanted(self, role: str) -> dict[str, Any]:
        """A request for a role loaded on demand came (the gateway asks before it waits for the slot): its model is
        loaded when it is not and nothing changes its slot; `refused` says why not (vision off, no preset)."""
        if role != "vision":
            return {"refused": ""}
        settings = self.vision_settings()
        if settings.mode == "off":
            return {"refused": "the vision model is off: the console's F8 page turns it on (v)"}
        self._used = time.monotonic()
        route = self.runtime.route("vision")
        if route["status"] in ("ready", "starting") or route["busy"]:
            return {"refused": ""}
        try:
            self.runtime.preset(settings.preset)
        except Exception:
            return {"refused": f"the vision model's preset {settings.preset!r} is not there"}
        await self.kernel.operations.start("runtime.load", {"slot": "vision", "preset": settings.preset}, actor=VISION)
        return {"refused": "", "loading": settings.preset}

    def look(self, image: bytes, question: str) -> str:
        """The vision model's answer about an image (PNG), through the gateway (role `vision`, loaded on demand); ""
        when vision is off or it does not answer."""
        if self.vision_settings().mode == "off":
            return ""
        status = self.status()
        if status["state"] != "running":
            return ""
        url = "data:image/png;base64," + base64.b64encode(image).decode()
        body = {
            "model": "vision", "max_tokens": 500, "temperature": 0.2,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": url}}, {"type": "text", "text": question},
            ]}],
        }  # fmt: skip
        try:
            answer = httpx2.post(
                f"http://127.0.0.1:{status['port']}/v1/chat/completions", json=body, timeout=LOOK_SECONDS
            )
            answer.raise_for_status()
            return str(answer.json()["choices"][0]["message"].get("content") or "").strip()
        except (httpx2.HTTPError, ValueError, KeyError, IndexError) as error:
            log.warning("the vision model did not read the image: %s", error)
            return ""

    def set_vision(self, values: dict[str, Any], *, actor: Actor) -> dict[str, Any]:
        """Change the vision model's mode, idle minutes or preset; its view after."""
        loaded = self.kernel.settings.get("vision", "vision")
        record = {**loaded.record.model_dump(), **values}
        self.kernel.settings.write("vision", "vision", record, base=loaded.revision, actor=actor)
        return self.vision()

    def vision(self) -> dict[str, Any]:
        """The vision model as the console shows it: its settings, its slot, how long since it was last wanted, and
        what loading its preset needs on its host (while it does not run)."""
        settings = self.vision_settings()
        slot = next(each for each in self.runtime.state.slots(self.runtime.settings().slots) if each.name == "vision")
        needs = None
        if slot.status != "ready":
            try:
                needs = self.runtime.needs(settings.preset)
            except Exception:
                needs = None
        idle = round(time.monotonic() - self._used) if self._used is not None else None
        return {
            "settings": settings.model_dump(mode="json"),
            "slot": slot.model_dump(mode="json"),
            "title": self.runtime.title(slot.preset) if slot.preset else "",
            "idle_seconds": idle,
            "needs": needs,
        }

    async def keep_vision(self) -> None:
        """The vision model as its mode says: loaded and kept when always, unloaded when off, and when on demand
        unloaded after its idle minutes without a request (none in flight)."""
        settings = self.vision_settings()
        route = self.runtime.route("vision")
        if route["busy"] or route["status"] in ("starting", "stopping"):
            return
        loaded = route["status"] == "ready"
        if settings.mode == "always" and route["status"] in ("stopped", "failed") and not self._failed_lately(route):
            with contextlib.suppress(Exception):
                self.runtime.preset(settings.preset)
                await self.kernel.operations.start(
                    "runtime.load", {"slot": "vision", "preset": settings.preset}, actor=VISION
                )
            return
        if not loaded or settings.mode == "always":
            return
        if settings.mode == "on-demand":
            if self._used is None:
                self._used = time.monotonic()  # loaded before this service started: its idle time starts now
            flying = any(
                each.get("role") == "vision"
                for each in (await anyio.to_thread.run_sync(self.activity)).get("requests") or []
            )
            if flying or time.monotonic() - self._used < settings.idle_minutes * 60:
                return
        await self.kernel.operations.start("runtime.unload", {"slot": "vision"}, actor=VISION)

    @staticmethod
    def _failed_lately(route: dict[str, Any]) -> bool:
        """A failed load is not tried again by itself: the owner sees why and loads it (F8)."""
        return bool(route["status"] == "failed")

    def status(self) -> dict[str, Any]:
        """Whether the gateway runs, where it listens and which process it is; or why it does not run. On Linux, its
        socket too, where the edge reaches it on Docker Engine (`socket`, design 0014 §3), or why it has none
        (`socket_problem`)."""
        kept = self._kept()
        running = kept is not None and self._host().alive(_identity(kept)) is not False
        port = int(kept["port"]) if running and kept else self.settings().port
        state = "running" if running else ("problem" if self.problem else "stopped")
        socket, socket_problem = self._socket_of(kept if running else None)
        return {
            "state": state,
            "port": port,
            "url": f"http://127.0.0.1:{port}/v1",
            "pid": int(kept["pid"]) if running and kept else None,
            "since": kept.get("since") if running and kept else None,
            "problem": "" if running else self.problem,
            "log": str(self.kernel.home.logs / "gateway.log"),
            "socket": socket,
            "socket_problem": socket_problem,
        }

    def socket_path(self) -> Path | None:
        """Where the edge reaches the gateway on Linux (design 0014 §3): the running gateway's socket when it listens on
        one, else where it listens once started, by its settings; None on any other system. `SocketFolderError`, saying
        why, when the settings' folder may not be used."""
        if not sockets.LINUX:
            return None
        kept = self._kept()
        running = kept is not None and self._host().alive(_identity(kept)) is not False
        found, _ = self._socket_of(kept if running else None)
        if found:
            return Path(found)
        wanted, refused = self._wanted_socket()
        if wanted is None:
            raise SocketFolderError(refused)
        return wanted

    def edge_socket(self) -> Path | None:
        """`socket_path`, its folder made the owner's alone when it is not there yet, so the edge can mount it before
        the gateway listens: a gateway that starts makes its socket in the same folder, and the edge sees it (design
        0014 §3). `SocketFolderError`, saying why, when the folder may not be used."""
        path = self.socket_path()
        if path is not None:
            sockets.prepare_folder(path.parent)
        return path

    def keep_socket(self) -> str:
        """On Linux, a gateway running without its socket (one started before it had one and adopted as it is, or one
        whose folder was removed) started again once no request is in flight, the service's log saying why (design 0014
        §3); once only, so one that cannot make it is not started again and again. What was done; "" for nothing."""
        if not sockets.LINUX:
            return ""
        kept = self._kept()
        if kept is None or self._host().alive(_identity(kept)) is False:
            return ""
        if self._socket_of(kept)[0]:
            self._socket_again = None  # it has its socket: one lost later is worth one more start
            return ""
        why, again = self._without(kept)
        if not again:
            return ""
        doing = self.activity()
        if doing.get("problem") or doing.get("requests"):
            return ""  # a request in flight, or the gateway does not say: the next look
        log.warning("the gateway runs without its socket (%s): it is started again, no request being in flight", why)
        found = self.restart()
        self._socket_again = found.get("pid")
        return f"started again without a request in flight: {why}"

    def _wanted_socket(self) -> tuple[Path | None, str]:
        """Where the gateway's socket goes by its settings now: its path, or None and why the folder may not be used;
        (None, "") on any system but Linux, where the gateway listens on no socket."""
        if not sockets.LINUX:
            return None, ""
        folder = sockets.socket_folder(self.settings().socket_folder, self.kernel.home.id)
        try:
            found = sockets.checked_socket_folder(folder, self.kernel.home.root, sockets.runs_from(), Path.home())
        except SocketFolderError as error:
            return None, str(error)
        return found / GATEWAY_SOCKET, ""

    def _socket_of(self, kept: dict[str, Any] | None) -> tuple[str | None, str]:
        """The running gateway's socket when it listens there, else None and why it has none, in words; (None, "") on
        any system but Linux, and while the gateway does not run (`kept` None)."""
        if not sockets.LINUX or kept is None:
            return None, ""
        path = kept.get("socket")
        if path and sockets.is_socket(Path(path)):
            return str(path), ""
        why, again = self._without(kept)
        return None, f"{why}: it is started again once no request is in flight" if again else why

    def _without(self, kept: dict[str, Any]) -> tuple[str, bool]:
        """Why a running gateway listens on no socket, and whether starting it again would give it one: not when it was
        started without one (its folder could not be used then), nor when something else is where the socket goes, nor
        when its folder may not be used, nor once it was started again for it."""
        had = kept.get("socket")
        if "socket" not in kept:
            why = "it was started before the gateway listened on a socket"
        elif not had:
            return f"it was started without one: {kept.get('socket_refused') or 'its folder could not be used'}", False
        elif os.path.lexists(had):
            return f"{had} is there and is not its socket: remove it, then clank gateway restart", False
        else:
            why = f"its socket {had} is not there"
        wanted, refused = self._wanted_socket()
        if wanted is None:
            return f"{why}; {refused}", False
        if os.path.lexists(wanted) and not sockets.is_socket(wanted):
            return f"{why}; {wanted} is there and is not a socket: remove it, then clank gateway restart", False
        if kept.get("pid") == self._socket_again:
            told = self.kernel.home.logs / "gateway.log"
            return f"{why}; started again for it, it still has none: {told} says why", False
        return why, True

    def ensure(self) -> dict[str, Any]:
        """Adopt the gateway that runs, or start it; its status."""
        with self._lock:
            kept = self._kept()
            if kept is not None and self._host().alive(_identity(kept)) is not False:
                self._save()  # one kept in memory only is written once its file can be
                return self.status()  # running, or the host cannot say: it is left as it is
            port = self.settings().port
            holder = self._host().listener(port)
            if holder is not None:
                self.problem = f"port {port} is held by {holder}: give the gateway another port in config/gateway.json"
                return self.status()
            argv = [sys.executable, "-m", "clank.components.gateway.server", "--port", str(port)]
            socket, refused = self._ready_socket()
            if socket is not None:
                argv += ["--socket-folder", str(socket.parent)]
            env = {"CLANK_HOME": str(self.kernel.home.root)}
            identity = self._host().spawn(argv, env, str(self.kernel.home.root), self.kernel.home.logs / "gateway.log")
            self._keep(identity, port, socket, refused)
            self.problem = ""
            return self.status()

    def _ready_socket(self) -> tuple[Path | None, str]:
        """On Linux, where the gateway about to start makes its socket, its folder made ready; None and why, the
        service's log saying it too, when the folder may not be used (it then listens on 127.0.0.1 alone); (None, "")
        on any other system."""
        wanted, refused = self._wanted_socket()
        if wanted is not None:
            try:
                sockets.prepare_folder(wanted.parent)
            except SocketFolderError as error:
                wanted, refused = None, str(error)
        if refused:
            log.warning("%s; the gateway starts without its socket", refused)
        return wanted, refused

    def stop(self) -> str:
        """Stop the gateway; what happened (stopped, killed, or gone when it did not run)."""
        with self._lock:
            kept = self._kept()
            if kept is None:
                return "gone"
            ended = self._host().stop(_identity(kept), STOP_SECONDS)
            self._forget()
            return ended

    def restart(self) -> dict[str, Any]:
        """Stop the gateway and start it again (it picks up changed settings); its status. Never half done: whatever
        the stop met, a start is tried (a gateway the stop left running is adopted as it is), and what went wrong is
        said in the status (`problem`)."""
        problem = ""
        kept = self._kept()
        try:
            self.stop()
        except Exception as error:  # the host could not end it: it may still run, and is then adopted
            log.warning("the gateway could not be stopped: %s", error)
            problem = f"the gateway could not be stopped ({error}), so it runs on with the settings it started with"
        else:
            self._wait_free(int(kept["port"]) if kept else self.settings().port)
        found = self.ensure()
        return {**found, "problem": problem or found["problem"]}

    def _wait_free(self, port: int) -> None:
        """Until the stopped gateway's port is free, `FREE_SECONDS` at most: on Windows its process lets go of it a
        moment after it was told to end (the owner's restart of 2026-10-26 found the port held, so it started nothing,
        and every model request failed until the service started the gateway again by itself)."""
        deadline = time.monotonic() + FREE_SECONDS
        while self._host().listener(port) is not None and time.monotonic() < deadline:
            time.sleep(FREE_POLL_SECONDS)

    def _forget(self) -> None:
        """Delete the gateway's state file; one another program holds open even after a while is left, naming a
        process that has ended, which says stopped."""
        self._unsaved = None
        if not files.remove(self._file()):
            log.warning("the gateway's state file %s is held open by another program: left as it is", self._file())

    def activity(self, session: str = "", subagents: bool = False, ended: bool = False) -> dict[str, Any]:
        """What the gateway does now: whether it runs, its requests in flight and the last that ended (its
        `GET /activity`), of one session when it is named and of its subagents too with `subagents`, with the
        session's requests that ended too with `ended`; none when it does not run, and why when it does not answer."""
        status = self.status()
        found = {"state": status["state"], "port": status["port"], "problem": status["problem"]}
        idle = {"requests": [], "served": 0, "last": None}
        if status["state"] != "running":
            return {**found, **idle}
        try:
            answer = httpx2.get(
                f"http://127.0.0.1:{status['port']}/activity",
                params={"session": session, "subagents": subagents, "ended": ended} if session else None,
                headers=self._token(),
                timeout=ASK_SECONDS,
            )
            answer.raise_for_status()
            doing: dict[str, Any] = answer.json()
        except (httpx2.HTTPError, ValueError) as error:
            return {**found, **idle, "problem": f"the gateway did not say what it does: {error}"}
        return {**found, **idle, **doing}

    def live(self, after: int = 0, id: str = "", session: str = "", subagents: bool = False) -> dict[str, Any]:
        """The newest request's text as it streams (the gateway's `GET /activity/live`), of one session when it is
        named and of its subagents too with `subagents`: what it is, what was asked, and its thinking, answer and tool
        calls from the character `after` on; none when the gateway does not answer."""
        status = self.status()
        idle = {"id": "", "flying": False, "meta": None, "asked": "", "length": 0, "parts": [], "newest": ""}
        if status["state"] != "running":
            return {**idle, "problem": status["problem"] or "the gateway does not run"}
        try:
            answer = httpx2.get(
                f"http://127.0.0.1:{status['port']}/activity/live",
                params={"after": after, "id": id, "session": session, "subagents": subagents},
                headers=self._token(),
                timeout=ASK_SECONDS,
            )
            answer.raise_for_status()
            found: dict[str, Any] = answer.json()
        except (httpx2.HTTPError, ValueError) as error:
            return {**idle, "problem": f"the gateway did not say: {error}"}
        return {**found, "problem": ""}

    def pause(self, session: str, by: str) -> dict[str, Any]:
        """Pause a session in the gateway (design 0012 §9.4): its next model requests, and its subagents', are held
        until it is resumed; the pause (`already` when it was paused before), with what it holds now."""
        found: dict[str, Any] = self._hold("PUT", session, {"by": by}).json()
        return found

    def resume(self, session: str) -> dict[str, Any] | None:
        """End a session's pause: what it held goes on to the engine; the pause as it was, with how many requests it let
        go (`held`), or None when it was not paused."""
        answer = self._hold("DELETE", session)
        if answer.status_code == 404:
            return None
        found: dict[str, Any] = answer.json()
        return found

    def release(self, session: str, before: str) -> int:
        """A note was sent to the session: its own requests held before `before` (when the note was about to be sent)
        end as empty steps, since one held after may carry the note; the pause stays; how many (0 when the gateway does
        not run: nothing is held there)."""
        if self.status()["state"] != "running":
            return 0
        return int(self._hold("POST", session, {"before": before}, path="/release").json()["released"])

    def holds(self) -> dict[str, Any]:
        """The paused sessions, each with since when, by whom and the requests it holds now; none, and why, when the
        gateway does not run or answer."""
        try:
            found = self._hold("GET", "").json()
        except HoldError as error:
            return {"pauses": [], "problem": str(error)}
        return {"pauses": list(found.get("pauses") or []), "problem": ""}

    def _hold(self, method: str, session: str, body: dict[str, Any] | None = None, path: str = "") -> httpx2.Response:
        """Ask the gateway's holds, with the service's local token; a refusal or no answer as `HoldError`. A 404 is an
        answer only when it is the gateway's own word that a session it was asked to resume is not paused; any other
        (FastAPI's own, for a route it lacks) is a gateway from before pausing, which the service adopted after an
        update, and a pause through it would hold nothing."""
        status = self.status()
        if status["state"] != "running":
            raise HoldError(status["problem"] or "the gateway does not run")
        named = f"/{quote(session, safe='')}" if session else ""
        url = f"http://127.0.0.1:{status['port']}/holds{named}{path}"
        token = local_token(self.kernel.home)
        try:
            answer = httpx2.request(method, url, json=body, headers={"Authorization": f"Bearer {token}"},
                                    timeout=ASK_SECONDS)  # fmt: skip
        except httpx2.HTTPError as error:
            raise HoldError(f"the gateway did not answer: {error}") from error
        if answer.status_code < 400:
            return answer
        said = _said(answer)
        if answer.status_code == 404 and method == "DELETE" and said.get("code") == NOT_PAUSED:
            return answer  # the gateway's own word: the session is not paused
        if answer.status_code == 404 and not said:  # no such route, FastAPI's own 404: a gateway from before pausing
            raise HoldError(OLDER)
        words = str(said.get("message") or "") or answer.text.strip() or f"status {answer.status_code}"
        raise HoldError(f"the gateway refused: {words}")

    def requests(self, limit: int = 50) -> list[dict[str, Any]]:
        """The newest model requests the gateway kept, newest first, each in brief (`records.recent`)."""
        from clank.components.gateway.records import recent

        return recent(self.kernel.home.logs / "traffic", limit)

    def request(self, id: str) -> dict[str, Any] | None:
        """One kept request with what was asked and answered; None when it is not kept (`records.find`)."""
        from clank.components.gateway.records import find

        return find(self.kernel.home.logs / "traffic", id)

    def answers(self, seconds: float) -> bool:
        """Whether the gateway answers on its port within `seconds`."""
        deadline = time.monotonic() + seconds
        url = f"http://127.0.0.1:{self.status()['port']}/health"
        while time.monotonic() < deadline:
            with contextlib.suppress(httpx2.HTTPError):
                if httpx2.get(url, timeout=2).status_code == 200:
                    return True
            time.sleep(0.1)
        return False

    async def run(self) -> None:
        """While the service runs: keep the gateway running, unless its settings say not to start it, and on Linux with
        its socket (`keep_socket`); keep the vision model as its mode says (design 0008 §7); and hand the gateway the
        keys of the cloud models the slots run (design 0016 §5): at once when a slot or a key changes, and at each
        watch, so a gateway started again gets them within seconds."""
        while True:
            try:
                if self.settings().start:
                    await anyio.to_thread.run_sync(self.ensure)
                    await anyio.to_thread.run_sync(self.keep_socket)
            except Exception:
                log.exception("keeping the gateway running failed")
            try:
                await self.keep_vision()
            except Exception:
                log.exception("keeping the vision model as its mode says failed")
            ends = time.monotonic() + WATCH_SECONDS
            await self._sync_keys()
            taken = 0.0
            while time.monotonic() < ends:
                await anyio.sleep(DUE_SECONDS)
                if self.keys_due.is_set():
                    await self._sync_keys()
                if time.monotonic() - taken >= SPEND_SECONDS:
                    taken = time.monotonic()
                    await self._take_spend()

    async def _take_spend(self) -> None:
        """The cloud's spending taken, and estimates made exact when their time comes (design 0016 §12)."""
        try:
            await anyio.to_thread.run_sync(self.take_spend)
            await anyio.to_thread.run_sync(self.price_generations)
        except HoldError:
            pass  # the gateway does not run: nothing to take
        except Exception:
            log.exception("taking the cloud's spending failed")
        try:
            await anyio.to_thread.run_sync(self.costs.check_limits)
            await anyio.to_thread.run_sync(self.costs.announce)
        except Exception:
            log.exception("checking the cloud's spending against its limits failed")

    async def _sync_keys(self) -> None:
        try:
            await anyio.to_thread.run_sync(self.sync_keys)
        except Exception:
            log.exception("handing the gateway the cloud models' keys failed")

    def router(self) -> Any:
        """The gateway's routes in the service's API."""
        from clank.components.gateway.api import router

        return router(self)

    def _host(self) -> "EngineHost":
        return self.runtime.host("local")

    def _file(self) -> Any:
        return self.kernel.home.state / "gateway.json"

    def _kept(self) -> dict[str, Any] | None:
        """The gateway's process as last kept: in memory while its state file cannot be written, else in that file."""
        unsaved = self._unsaved
        if unsaved is not None:
            return dict(unsaved)
        try:
            found = json.loads(self._file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return found if isinstance(found, dict) and "pid" in found else None

    def _keep(self, identity: ProcessIdentity, port: int, socket: Path | None = None, refused: str = "") -> None:
        """Keep the process started, with its socket (None: it listens on none, and `refused` says why): in its state
        file, else in memory until that file can be written."""
        self._unsaved = {
            "host": identity.host, "pid": identity.pid, "started": identity.started, "command": identity.command,
            "port": port, "since": to_text(self.kernel.clock.now()), "socket": str(socket) if socket else None,
            "socket_refused": refused,
        }  # fmt: skip
        self._save()

    def _save(self) -> None:
        """Write the process kept in memory to its state file, when one is; it stays in memory while it cannot be."""
        unsaved = self._unsaved
        if unsaved is None:
            return
        try:
            files.replace(self._file(), json.dumps(unsaved) + "\n")
        except OSError as error:
            log.warning("the gateway's state file %s could not be written (%s): kept in memory", self._file(), error)
            return
        self._unsaved = None


def _identity(kept: dict[str, Any]) -> ProcessIdentity:
    return ProcessIdentity(str(kept["host"]), int(kept["pid"]), str(kept["started"]), str(kept["command"]))


def _said(answer: httpx2.Response) -> dict[str, Any]:
    """The gateway's own error in a refusal (its code and message), {} when the answer holds none."""
    try:
        found = answer.json()
    except ValueError:
        return {}
    error = found.get("error") if isinstance(found, dict) else None
    return error if isinstance(error, dict) else {}
