"""Test support: a cloud model on the real service (design 0016, plan s35's task 18). The clients' tests run against the
service's own routes, OpenRouter answered by plan s34's fake (`tests/fakes/openrouter.py`, its documented recording),
the adapter's URL pointed at it. The bench puts the service where a test needs it through its own parts, as the routes
would leave it: OpenRouter added and agreed (its made-up key kept), a cloud preset written from a listed model, the main
slot running one (its route kept as a load keeps it, nothing started), spending kept as the gateway's spool gives it,
a limit reached (the cloud paused and its question asked). `record` adds to a test's application a note of each call a
client makes to the cloud's routes (`calls`: method, path, body; a key's last four only)."""

import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, Request
from starlette.responses import Response

from clank.components.runtime import cloud
from clank.components.runtime.launching import preset_of
from clank.kernel.access import client_actor
from clank.kernel.api import PREFIX
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from clank.kernel.questions import Question
from clank.kernel.settings import SettingsError
from tests.fakes.openrouter import KEY, FakeOpenRouter

YOU = client_actor("console")
RUNTIME = Actor(kind="clank", via="runtime")
CODER = "example-vendor/example-coder"
NOTED = re.compile(
    r"/runtime/endpoints.*|/runtime/dev|/runtime/presets/[^/]+|/workspaces/[^/]+/cloud(/ask)?|/gateway/cost/limits"
    r"|/mcp/servers/[^/]+/local"
)


@dataclass
class CloudBench:
    """The service, a fake OpenRouter, and what the clients asked of the cloud's routes."""

    kernel: Kernel
    openrouter: FakeOpenRouter
    calls: list[tuple[str, str, Any]] = field(default_factory=list)
    _runs: int = 0

    # What a test sets up.

    def add(self, key: bool = True, local_mcp: list[str] | None = None) -> None:
        """OpenRouter added and agreed now, as Add a model leaves it (the MCP servers named marked local only, every
        one when none are), and its made-up key kept (unless `key` is false)."""
        self.kernel.parts["runtime"].endpoints.add("openrouter", "openrouter", agree=True, local_mcp=local_mcp,
                                                   actor=YOU)  # fmt: skip
        if key:
            self.kernel.secrets.put("endpoint/openrouter", "key", KEY, actor=YOU)

    def write_preset(self, model: str = CODER, **values: Any) -> dict[str, Any]:
        """A cloud preset written from a listed model, as `POST /runtime/endpoints/openrouter/presets` writes one."""
        runtime = self.kernel.parts["runtime"]
        title = str(values.pop("title", ""))
        found: dict[str, Any] = runtime.endpoints.write_preset("openrouter", model, title=title, wanted=values,
                                                               actor=YOU)  # fmt: skip
        return found

    def run(self, preset: str) -> None:
        """The main slot running a preset: a local one ready, or a cloud one as its load leaves it (its route kept,
        nothing started on this machine)."""
        runtime = self.kernel.parts["runtime"]
        state = runtime.state
        preset_id, record = preset_of(runtime, preset)
        title = record.title or preset_id
        if not record.cloud:
            state.set_slot("main", "ready", f"{title} answered in 1 s", actor=RUNTIME, preset=preset_id)
            return
        prepared = cloud.prepare(runtime, preset_id, record)
        launch = state.add_launch(
            slot="main", preset=preset_id, options=record.options, engine="", engine_version="", host="",
            command_line=f"nothing runs on this machine: {record.model}", log="", endpoint=record.endpoint,
            route=prepared.route,
        )  # fmt: skip
        state.set_route(launch, {**prepared.route, "launch": launch})
        state.set_slot("main", "ready", f"{title} answered in 1 s", actor=RUNTIME, preset=preset_id, launch_id=launch,
                       host=None, port=None, pid=None)  # fmt: skip

    def spend(self, usd: float, requests: int = 1, *, session: str = "", workspace: str = "",
              estimated: bool = False) -> None:  # fmt: skip
        """Cloud requests kept as the gateway's spool gives them (now, `usd` shared among them), and the totals said."""
        gateway = self.kernel.parts["gateway"]
        self._runs += 1
        entries = [
            {"seq": seq, "id": f"req-{self._runs}-{seq}", "session": session, "workspace": workspace,
             "endpoint": "openrouter", "preset": "cloud-example-coder", "model": CODER,
             "tokens": {"in": 1200, "cached": 800, "out": 90, "thinking": 0}, "usd": round(usd / requests, 6),
             "how": "estimate" if estimated else "usage", "status": 200}
            for seq in range(1, requests + 1)
        ]  # fmt: skip
        gateway.costs.keep_entries(f"run-{self._runs}", entries)
        gateway.costs._told_at = -1e9  # said at once, not five seconds after the last
        gateway.costs.announce()

    def set_limits(self, **values: float | None) -> None:
        """The cloud's limits, as `PUT /gateway/cost/limits` sets them."""
        self.kernel.parts["gateway"].set_limits(values, actor=YOU)

    def reach(self, by: str = "day", spent: float = 5.02) -> Question:
        """A limit reached: `spent` spent today against a limit of $5.00 (unless one is set), the cloud paused and the
        owner asked whether to raise it."""
        gateway = self.kernel.parts["gateway"]
        key = "day_usd" if by == "day" else "month_usd"
        if self.limits[key] is None:
            self.set_limits(**{key: 5.0})
        self.spend(spent)
        gateway.costs.check_limits()
        paused = gateway.costs.paused_view()
        assert paused is not None, "the limit was not reached"
        return self.kernel.questions.get(str(paused["question"]))

    def mark(self, name: str, local: bool) -> None:
        """An MCP server marked local only, or not."""
        self.kernel.parts["tools"].set_local(name, local, actor=YOU)

    # What a test reads.

    @property
    def endpoint(self) -> dict[str, Any] | None:
        """OpenRouter's record as its file has it, or None."""
        try:
            found: dict[str, Any] = self.kernel.settings.get("endpoint", "openrouter").record.model_dump()
        except SettingsError:
            return None
        return found

    @property
    def presets(self) -> dict[str, dict[str, Any]]:
        """The cloud presets, by id."""
        return {each["id"]: each for each in self.kernel.parts["runtime"].presets() if each.get("endpoint")}

    @property
    def limits(self) -> dict[str, Any]:
        found: dict[str, Any] = self.kernel.parts["gateway"].cost_settings().model_dump()
        return found

    @property
    def local(self) -> dict[str, bool]:
        """Each MCP server's mark: local only, or not."""
        return {each["name"]: bool(each.get("local_only")) for each in self.kernel.parts["tools"].servers()}

    @property
    def paused(self) -> dict[str, Any] | None:
        found: dict[str, Any] | None = self.kernel.parts["gateway"].costs.paused_view()
        return found

    def bound(self, name: str) -> dict[str, Any]:
        """A workspace's bound, with its words."""
        found: dict[str, Any] = self.kernel.parts["workspaces"].cloud.view(name)
        return found

    def key(self) -> str | None:
        """The key kept, read from its file without a `secret.used` event: for a test's assertion only."""
        path = self.kernel.home.secrets / "endpoint" / "openrouter" / "key"
        return path.read_text(encoding="utf-8") if path.is_file() else None

    # Noting the calls.

    def record(self, app: FastAPI) -> None:
        """Note each call a client makes to the cloud's routes on this application."""

        @app.middleware("http")
        async def noted(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
            path = request.url.path.removeprefix(PREFIX)
            if NOTED.fullmatch(path) and (request.method != "GET" or path.endswith("/models")):
                raw = await request.body()
                body = json.loads(raw) if raw else dict(request.query_params)
                if isinstance(body, dict) and "key" in body:
                    body = {**body, "key": "…" + str(body["key"])[-4:]}
                self.calls.append((request.method, path.lstrip("/"), body))
            return await call_next(request)
