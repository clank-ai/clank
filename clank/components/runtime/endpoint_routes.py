"""The runtime's routes for the providers someone else runs (design 0016 §4-§7, plan s34's interface): their records,
their keys, what their providers say (the account, the models), the cloud presets written from a model, the check
and the test; and whether any model is usable (`GET /runtime/usable`).

They are included with the runtime's routes, under `/api/v1/` behind the local token. A key is taken only in a
request's body, over the loopback, and no route ever answers with it. What asks a provider runs off the service's
event loop.
"""

from typing import TYPE_CHECKING, Any

import anyio.to_thread
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from clank.components.runtime import guide
from clank.kernel.access import CLIENT_HEADER, REQUEST_KEY_HEADER, client_actor

if TYPE_CHECKING:
    from clank.components.runtime.service import Runtime


class NewEndpoint(BaseModel):
    """A provider to add, with the owner's agreement; the MCP servers the agreement screen marked local only (none
    named: every one already added)."""

    id: str = "openrouter"
    adapter: str = "openrouter"
    agree: bool = False
    local_mcp: list[str] | None = None


class EndpointChange(BaseModel):
    """What to change of a provider: its options (merged with its own), its agreement (empty: withdrawn), its read
    timeout or its notes."""

    options: dict[str, Any] | None = None
    agreed: str | None = None
    timeout_seconds: int | None = Field(None, ge=10)
    notes: str | None = None


class NewCloudPreset(BaseModel):
    """A cloud preset to write for one of a provider's models: all but the model may be left to the model's own."""

    model: str
    title: str = ""
    context: int | None = Field(None, ge=1)
    max_output: int | None = Field(None, ge=1)
    reasoning: str | None = None


class CheckAsked(BaseModel):
    """The model a provider's check asks; empty: the model of its first preset."""

    model: str = ""


class TestAsked(BaseModel):
    """The cloud preset to test."""

    preset: str


class GivenKey(BaseModel):
    """A provider's key, given once, in the request's body."""

    key: str = Field(repr=False)


class DevMode(BaseModel):
    """Dev mode on or off (decision 0149)."""

    on: bool


def router(runtime: "Runtime") -> APIRouter:
    """The providers' routes, over the runtime's part."""
    routes = APIRouter()
    endpoints = runtime.endpoints

    @routes.get("/runtime/dev")
    def dev_mode() -> dict[str, Any]:
        """Dev mode (decision 0149): whether every cloud provider is asked for any of a model's providers, and what
        that means, in words."""
        return endpoints.dev_view()

    @routes.put("/runtime/dev")
    def set_dev_mode(asked: DevMode, request: Request) -> dict[str, Any]:
        """Turn dev mode on or off, recorded with who did it; the next request goes so."""
        return endpoints.set_dev(asked.on, actor=client_actor(request.headers.get(CLIENT_HEADER)))

    @routes.get("/runtime/endpoints")
    def endpoint_list() -> list[dict[str, Any]]:
        """Every provider someone else runs: its record, its key (set, its last four), its presets, its last check."""
        return endpoints.views()

    @routes.get("/runtime/endpoints/{id}")
    def endpoint(id: str) -> dict[str, Any]:
        """One provider."""
        return endpoints.view(id)

    @routes.post("/runtime/endpoints", status_code=201)
    def add_endpoint(new: NewEndpoint, request: Request) -> dict[str, Any]:
        """Add a provider from its adapter's template, with the owner's agreement; the MCP servers named are marked
        local only (every one already added, when none are named)."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        return endpoints.add(new.id, new.adapter, agree=new.agree, local_mcp=new.local_mcp, actor=actor)

    @routes.patch("/runtime/endpoints/{id}")
    def change_endpoint(id: str, change: EndpointChange, request: Request) -> dict[str, Any]:
        """Change a provider's options, agreement (empty withdraws it), read timeout or notes."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        return endpoints.change(id, change.model_dump(exclude_unset=True), actor=actor)

    @routes.delete("/runtime/endpoints/{id}")
    def remove_endpoint(id: str, request: Request) -> dict[str, Any]:
        """Remove a provider and its key; refused while a slot runs one of its presets or a preset names it."""
        return endpoints.remove(id, actor=client_actor(request.headers.get(CLIENT_HEADER)))

    @routes.put("/runtime/endpoints/{id}/key")
    async def set_key(id: str, given: GivenKey, request: Request) -> dict[str, Any]:
        """Keep a provider's key once the provider accepts it; its last four and the account, never the key."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: endpoints.set_key(id, given.key, actor=actor))
        return {**found, "account": _account_said(found["account"], found["key"]["ends"])}

    @routes.delete("/runtime/endpoints/{id}/key")
    def remove_key(id: str, request: Request) -> dict[str, Any]:
        """Forget a provider's key."""
        return endpoints.remove_key(id, actor=client_actor(request.headers.get(CLIENT_HEADER)))

    @routes.get("/runtime/endpoints/{id}/account")
    async def account(id: str, fresh: bool = False) -> dict[str, Any]:
        """The key's own facts as its provider counts them (read at most once a minute; `fresh` asks again)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: endpoints.account(id, fresh=fresh))
        return _account_said(found, endpoints.key_view(id)["ends"])

    @routes.get("/runtime/endpoints/{id}/models")
    async def models(
        id: str, search: str = "", sort: str = "most-popular", free: bool = False, all: bool = False,
        fresh: bool = False,
    ) -> dict[str, Any]:  # fmt: skip
        """The provider's live list of models that take tool calls (`all`: every one; `free`: the free ones), read with
        the key and kept an hour (`fresh` asks again); `search` narrows by name or id; `sort` is most-popular, price,
        context or newest."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: endpoints.models(id, search=search, sort=sort, free=free, everything=all, fresh=fresh)
        )
        models = [{**model, "said": guide.model_said(model), "settings": guide.model_settings(model)}
                  for model in found["models"]]  # fmt: skip
        return {**found, "models": models, "said": guide.listed_said(found["count"], found["sort"], free, search)}

    @routes.post("/runtime/endpoints/{id}/presets", status_code=201)
    async def write_preset(id: str, wanted: NewCloudPreset, request: Request) -> dict[str, Any]:
        """Write a cloud preset for one of the provider's models (never one without tool calls), its options those
        given, else the model's; the preset as `GET /runtime/presets/{name}` gives it."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        options = wanted.model_dump(exclude_none=True, exclude={"model", "title"})
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: endpoints.write_preset(id, wanted.model, title=wanted.title, wanted=options, actor=actor)
        )
        return found

    @routes.post("/runtime/endpoints/{id}/check")
    async def check(id: str, request: Request, wanted: CheckAsked | None = None) -> dict[str, Any]:
        """Check a provider with Clank's own made-up requests (the model given, else its presets'): an operation whose
        result is each item, passed, failed or warned, with why."""
        endpoints.record(id)
        params = {"id": id, "model": wanted.model if wanted else ""}
        return await _started(runtime, "runtime.endpoint_check", params, request)

    @routes.post("/runtime/endpoints/{id}/test")
    async def test(id: str, wanted: TestAsked, request: Request) -> dict[str, Any]:
        """Test a cloud preset with one short request: an operation whose result is its answer, time and cost, or what
        failed and what to do."""
        endpoints.record(id)
        return await _started(runtime, "runtime.endpoint_test", {"id": id, "preset": wanted.preset}, request)

    @routes.get("/runtime/usable")
    async def usable() -> dict[str, Any]:
        """Whether a model is usable: the main slot ready, or a preset for it that can load now (with none, the console
        opens on Add a model)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(runtime.usable)
        return found

    @routes.get("/runtime/guide/local")
    async def guide_local() -> dict[str, Any]:
        """Add a model's Local step: the main slot's presets, each with its words (its fit here) and what it still
        needs here, in order (`GET /runtime/guide`, the steps before, is served with what the other parts know)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(runtime.guide_local)
        return found

    return routes


def _account_said(account: dict[str, Any], ends: str) -> dict[str, Any]:
    """The key's account with its line (design 0016 §5)."""
    return {**account, "said": guide.account_said(account, ends)}


async def _started(runtime: "Runtime", kind: str, params: dict[str, Any], request: Request) -> dict[str, Any]:
    """An operation started, as a client follows it (a key in `X-Clank-Request-Key` starts one however often sent)."""
    actor = client_actor(request.headers.get(CLIENT_HEADER))
    key = request.headers.get(REQUEST_KEY_HEADER)
    started = await runtime.kernel.operations.start(kind, params, actor=actor, request_key=key)
    return started.model_dump(mode="json")
