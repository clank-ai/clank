"""The runtime component's routes: its slots, presets, serving setups, installs and hosts (design 0003 §8).

They are included under `/api/v1/` behind the local token like every route (design 0002 §2.7). A preset is named by its
id or its title; one that does not exist is a 404 in the API's one error shape. Loading and unloading a slot, and
installing an engine, return the operation they start (design 0002 §2.4); a key in `X-Clank-Request-Key` makes a press
sent twice start one, and a second one while the first runs is refused as busy, naming it.
"""

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from clank.kernel.access import CLIENT_HEADER, REQUEST_KEY_HEADER, client_actor

if TYPE_CHECKING:
    from clank.components.runtime.service import Runtime


class NewHost(BaseModel):
    """A host to add."""

    id: str
    adapter: str = "wsl"
    distro: str = ""
    clank_folder: str = "~/.clank"


class LoadRequest(BaseModel):
    """A preset to load; `anyway` starts it even when the fit check says it does not fit."""

    preset: str
    anyway: bool = False


class InstallRequest(BaseModel):
    """An engine to install on a host by Clank's recipe for it; `yes` installs it without asking."""

    setup: str
    version: str
    host: str
    yes: bool = False


class DownloadRequest(BaseModel):
    """One of a catalog model's files to download to a host: `yes` downloads it without asking, `limit` caps its speed
    (MB/s, 0 for none)."""

    model: str
    format: str
    role: str = "weights"
    host: str
    yes: bool = False
    limit: float = 0


class ModelFileRequest(BaseModel):
    """One of a catalog model's files the user already has on a host, to adopt where it is once verified."""

    model: str
    format: str
    role: str = "weights"
    host: str
    path: str


class RemoveRequest(BaseModel):
    """A catalog model's files to remove from a host: all of them, or those of one format or role; `yes` removes them
    without asking."""

    model: str
    host: str
    format: str | None = None
    role: str | None = None
    yes: bool = False


class UninstallRequest(BaseModel):
    """An engine to remove from a host; `yes` removes the one Clank built without asking."""

    setup: str
    version: str
    host: str
    yes: bool = False


class AdoptRequest(BaseModel):
    """An engine already built, to adopt where it is: the command that runs it, the folder it runs in, the git checkout
    it was built from (its folder, unless named), its libraries' folders."""

    setup: str
    version: str
    host: str
    program: list[str]
    folder: str
    source: str = ""
    library_path: str = ""


def router(runtime: "Runtime") -> APIRouter:
    """The routes, over the runtime component's part."""
    from clank.components.runtime import launching
    from clank.components.runtime.service import HostNotFound, PresetNotFound

    routes = APIRouter()

    @routes.get("/runtime/slots")
    def slots() -> list[dict[str, Any]]:
        """Each slot: its state since when and why, and what it runs."""
        return [slot.model_dump(mode="json") for slot in runtime.state.slots(runtime.settings().slots)]

    @routes.post("/runtime/slots/{slot}/load")
    async def load(slot: str, wanted: LoadRequest, request: Request) -> dict[str, Any]:
        """Load a preset into an empty slot: an operation."""
        params = {"slot": _known(runtime, slot), "preset": wanted.preset, "anyway": wanted.anyway}
        return await _start(runtime, "runtime.load", params, request)

    @routes.post("/runtime/slots/{slot}/switch")
    async def switch(slot: str, wanted: LoadRequest, request: Request) -> dict[str, Any]:
        """Stop what a slot runs and start a preset; back to the last that worked if it fails: an operation."""
        params = {"slot": _known(runtime, slot), "preset": wanted.preset, "anyway": wanted.anyway}
        return await _start(runtime, "runtime.switch", params, request)

    @routes.post("/runtime/slots/{slot}/unload")
    async def unload(slot: str, request: Request) -> dict[str, Any]:
        """Stop what a slot runs: an operation."""
        return await _start(runtime, "runtime.unload", {"slot": _known(runtime, slot)}, request)

    @routes.get("/runtime/presets")
    def presets() -> list[dict[str, Any]]:
        """Every preset, Clank's own and the user's."""
        return runtime.presets()

    @routes.get("/runtime/presets/{name}")
    def preset(name: str) -> dict[str, Any]:
        """One preset, by its id or its title."""
        try:
            return runtime.preset(name)
        except PresetNotFound as error:
            raise HTTPException(404, str(error)) from error

    @routes.get("/runtime/presets/{name}/plan")
    def plan(name: str) -> dict[str, Any]:
        """A preset's options, each with where its value comes from; its command line, memory and fit, or why not."""
        try:
            return launching.plan_view(runtime, name)
        except PresetNotFound as error:
            raise HTTPException(404, str(error)) from error

    @routes.get("/runtime/models")
    def models() -> list[dict[str, Any]]:
        """The catalog's models: each file, and where it is on each host whose engine reads it, and whether it is."""
        return launching.models_view(runtime)

    @routes.get("/runtime/launches")
    def launches(limit: int = Query(20, ge=1, le=1000)) -> list[dict[str, Any]]:
        """The newest launches, newest first: what each started, how long it took, the memory it took."""
        return [launch.model_dump(mode="json") for launch in runtime.state.launches(limit)]

    @routes.get("/runtime/gpu")
    def gpu() -> dict[str, int] | None:
        """The GPU's memory now, or nothing when it cannot be read."""
        found = runtime.read_gpu()
        if found is None:
            return None
        return {"total_mib": found.total_mib, "used_mib": found.used_mib, "free_mib": found.free_mib}

    @routes.post("/runtime/presets/{name}/check")
    def check(name: str) -> list[dict[str, Any]]:
        """Check a preset, item by item, starting nothing."""
        try:
            return [vars(item) for item in runtime.check(name)]
        except PresetNotFound as error:
            raise HTTPException(404, str(error)) from error

    @routes.get("/runtime/engines")
    def engines() -> list[dict[str, Any]]:
        """Every serving setup Clank has an adapter for: its versions, where each is installed, its recipes."""
        return runtime.engines()

    @routes.get("/runtime/installs")
    def installs() -> list[dict[str, Any]]:
        """Every engine installed on a host."""
        return [{"id": found.id, **found.model_dump(mode="json")} for found in runtime.state.installs()]

    @routes.post("/runtime/installs")
    async def install(wanted: InstallRequest, request: Request) -> dict[str, Any]:
        """Install an engine on a host by its recipe: an operation, which asks first unless told `yes`."""
        known_host(wanted.host)
        if (wanted.setup, wanted.version) not in runtime.recipes:
            known = ", ".join(f"{setup} {version}" for setup, version in sorted(runtime.recipes)) or "none"
            raise HTTPException(404, f"Clank has no recipe for {wanted.setup} {wanted.version}; it has: {known}")
        return await _start(runtime, "runtime.install", wanted.model_dump(), request)

    @routes.post("/runtime/installs/adopt")
    async def adopt(wanted: AdoptRequest, request: Request) -> dict[str, Any]:
        """Adopt an engine already built, where it is: an operation that checks it first."""
        known_host(wanted.host)
        return await _start(runtime, "runtime.adopt", wanted.model_dump(), request)

    @routes.post("/runtime/downloads")
    async def download(wanted: DownloadRequest, request: Request) -> dict[str, Any]:
        """Download a model's file to a host: an operation, which asks first unless told `yes`."""
        known_host(wanted.host)
        return await _start(runtime, "runtime.download", wanted.model_dump(), request)

    @routes.post("/runtime/model-files")
    async def adopt_file(wanted: ModelFileRequest, request: Request) -> dict[str, Any]:
        """Adopt a model's file the user has, where it is: an operation that verifies it first."""
        known_host(wanted.host)
        return await _start(runtime, "runtime.verify", wanted.model_dump(), request)

    @routes.post("/runtime/model-files/remove")
    async def remove_files(wanted: RemoveRequest, request: Request) -> dict[str, Any]:
        """Remove a model's files from a host: an operation, which asks first unless told `yes`; the catalog keeps the
        model and every preset stays, and a file the user keeps elsewhere is only forgotten."""
        known_host(wanted.host)
        return await _start(runtime, "runtime.remove", wanted.model_dump(), request)

    @routes.post("/runtime/installs/remove")
    async def uninstall(wanted: UninstallRequest, request: Request) -> dict[str, Any]:
        """Remove an engine from a host: an operation; one Clank built is deleted with its folder after a question
        (unless told `yes`), any other only forgotten."""
        known_host(wanted.host)
        return await _start(runtime, "runtime.uninstall", wanted.model_dump(), request)

    def known_host(name: str) -> None:
        try:
            runtime.host(name)
        except HostNotFound as error:
            raise HTTPException(404, str(error)) from error

    @routes.get("/runtime/hosts")
    def hosts() -> list[dict[str, Any]]:
        """Where engines run: this machine, and each host record."""
        return runtime.hosts()

    @routes.post("/runtime/hosts")
    def add_host(new: NewHost, request: Request) -> dict[str, Any]:
        """Add a host; a WSL host only for a distribution WSL has."""
        from clank.kernel.api import ApiError

        actor = client_actor(request.headers.get(CLIENT_HEADER))
        try:
            return runtime.add_host(new.id, new.adapter, distro=new.distro, clank_folder=new.clank_folder, actor=actor)
        except ValueError as error:
            raise ApiError(409, "refused", str(error)) from error

    from clank.components.runtime.endpoint_routes import router as endpoint_router

    routes.include_router(endpoint_router(runtime))
    return routes


def _known(runtime: "Runtime", slot: str) -> str:
    if slot not in runtime.settings().slots:
        raise HTTPException(404, f"there is no slot {slot}; config/runtime.json lists the slots")
    return slot


async def _start(runtime: "Runtime", kind: str, params: dict[str, Any], request: Request) -> dict[str, Any]:
    actor = client_actor(request.headers.get(CLIENT_HEADER))
    key = request.headers.get(REQUEST_KEY_HEADER)
    started = await runtime.kernel.operations.start(kind, params, actor=actor, request_key=key)
    return started.model_dump(mode="json")
