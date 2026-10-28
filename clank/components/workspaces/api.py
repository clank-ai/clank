"""The workspaces component's routes: Docker's status, and starting and stopping it; the workspaces, and opening,
installing the software of (design 0004 §10), stopping and removing one (design 0004 §1); a workspace's image layers
(design 0020 §3); Clank's sandbox image built alone, for the setup (design 0028 §4).

They are included under `/api/v1/` behind the local token like every route (design 0002 §2.7). Reading the platform
runs its commands, so it happens off the service's event loop. Starting and stopping return the operation they start
(design 0002 §2.4); a key in `X-Clank-Request-Key` makes a press sent twice start one, and a second one while the
first runs is refused as busy, naming it.
"""

from typing import TYPE_CHECKING, Any

import anyio.to_thread
from fastapi import APIRouter, Request
from pydantic import BaseModel

from clank.kernel.access import CLIENT_HEADER, REQUEST_KEY_HEADER, client_actor

if TYPE_CHECKING:
    from clank.components.workspaces.service import Workspaces


class OpenRequest(BaseModel):
    """A folder to work in, on this machine; `yes` builds the sandbox image without asking, when it is not built."""

    folder: str
    yes: bool = False
    layers: list[str] = []


class ImageRequest(BaseModel):
    """`yes` builds the sandbox image without asking first."""

    yes: bool = False


class SetupRequest(BaseModel):
    """A workspace's folder; a setup command to keep and run (empty: its record's, else the proposed one); `yes` runs
    it without asking."""

    folder: str
    command: str = ""
    yes: bool = False


class CloudAnswer(BaseModel):
    """Whether a workspace's agent may use the cloud model (false: kept on this machine)."""

    allow: bool


class HostWanted(BaseModel):
    """A host a workspace's agent is reaching now (design 0024 §3), asked by the proxy."""

    host: str


class SetAnswer(BaseModel):
    """A named set of hosts a workspace's agent may reach (design 0024 §5), or may not any more."""

    set: str
    allow: bool = True


class HostAnswer(BaseModel):
    """A host a workspace's agent may reach through Clank's proxy (design 0024 §1), or may not any more."""

    host: str
    allow: bool = True


class LayerRequest(BaseModel):
    """An image layer to add to a workspace (`added`), or to take away."""

    layer: str
    added: bool = True


class RemoveRequest(BaseModel):
    """`yes` removes the workspace without asking."""

    yes: bool = False


def router(workspaces: "Workspaces") -> APIRouter:
    """The routes, over the workspaces component's part."""
    routes = APIRouter()

    @routes.get("/docker")
    async def docker(refresh: bool = False) -> dict[str, Any]:
        """Docker: its state, its versions, a one-line summary, and each container with its owner (`refresh` reads it
        now instead of giving the last reading)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(workspaces.docker, refresh)
        return found

    @routes.post("/docker/start")
    async def start(request: Request) -> dict[str, Any]:
        """Start Docker: an operation that waits until its engine answers."""
        return await _start(workspaces, "docker.start", request)

    @routes.post("/docker/stop")
    async def stop(request: Request) -> dict[str, Any]:
        """Stop Docker and every container in it: an operation that asks first when containers Clank did not start
        are running."""
        return await _start(workspaces, "docker.stop", request)

    @routes.get("/workspaces")
    async def list_workspaces() -> list[dict[str, Any]]:
        """Each workspace: its name, its folder, its limits, its container and the container's state."""
        found: list[dict[str, Any]] = await anyio.to_thread.run_sync(workspaces.workspaces)
        return found

    @routes.get("/workspaces/folder")
    async def folder(folder: str) -> dict[str, Any]:
        """What working in a folder needs of the workspaces: whether it may be a workspace (else why not), its
        workspace, its container's state, and whether the sandbox image is built."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(workspaces.folder_view, folder)
        return found

    @routes.post("/workspaces/open")
    async def open_workspace(wanted: OpenRequest, request: Request) -> dict[str, Any]:
        """Open a folder as a workspace: an operation that makes what is missing (its record, the sandbox image, the
        networks, the edge, its container) and asks first before it builds the image."""
        return await _start(workspaces, "workspaces.open", request, wanted.model_dump())

    @routes.post("/workspaces/image")
    async def build_image(wanted: ImageRequest, request: Request) -> dict[str, Any]:
        """Build Clank's sandbox image when it is not built for this Clank: an operation of its own, which `clank
        setup` runs in the background (design 0028 §4); asked first unless `yes`; opening a workspace is refused while
        it builds, naming it."""
        return await _start(workspaces, "workspaces.image", request, wanted.model_dump())

    @routes.post("/workspaces/setup")
    async def setup_workspace(wanted: SetupRequest, request: Request) -> dict[str, Any]:
        """Install a workspace's own software into its home: an operation that asks first, then runs the setup in a
        container of its own that reaches the internet (design 0004 §10)."""
        return await _start(workspaces, "workspaces.setup", request, wanted.model_dump())

    @routes.post("/workspaces/{name}/stop")
    async def stop_workspace(name: str, request: Request) -> dict[str, Any]:
        """Stop a workspace's container: an operation."""
        return await _start(workspaces, "workspaces.stop", request, {"name": name})

    @routes.post("/workspaces/{name}/remove")
    async def remove_workspace(name: str, wanted: RemoveRequest, request: Request) -> dict[str, Any]:
        """Remove a workspace's container, its home and its record, never its folder: an operation that asks first."""
        return await _start(workspaces, "workspaces.remove", request, {"name": name, "yes": wanted.yes})

    @routes.post("/workspaces/{name}/layers")
    async def layers(name: str, wanted: LayerRequest, request: Request) -> dict[str, Any]:
        """Add an image layer to a workspace (design 0020 §3: tex), or take it away; built the next time it opens."""
        from clank.components.workspaces.folders import WorkspaceError
        from clank.kernel.api import ApiError

        actor = client_actor(request.headers.get(CLIENT_HEADER))
        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(
                lambda: workspaces.set_layer(name, wanted.layer, wanted.added, actor=actor)
            )
        except WorkspaceError as error:
            raise ApiError(409, "refused", str(error)) from error
        return found

    @routes.post("/workspaces/{name}/cloud")
    async def cloud(name: str, answer: CloudAnswer, request: Request) -> dict[str, Any]:
        """Allow a workspace's agent the cloud model, or keep it on this machine (design 0016 §9); its view after."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: workspaces.allow_cloud(name, answer.allow, actor=actor)
        )
        return found

    @routes.get("/workspaces/network-sets")
    async def network_sets() -> dict[str, Any]:
        """The named sets of hosts (design 0024 §5): each its hosts and what it opens, from the owner's file."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(workspaces.network_sets)
        return found

    @routes.post("/workspaces/{name}/sets")
    async def allow_set(name: str, answer: SetAnswer, request: Request) -> dict[str, Any]:
        """Allow a workspace's agent a named set of hosts, or take it back (design 0024 §5); its view after."""
        from clank.components.workspaces.folders import WorkspaceError
        from clank.kernel.api import ApiError

        actor = client_actor(request.headers.get(CLIENT_HEADER))
        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(
                lambda: workspaces.allow_set(name, answer.set, answer.allow, actor=actor)
            )
        except WorkspaceError as error:
            raise ApiError(400, "refused", str(error)) from error
        return found

    @routes.get("/workspaces/hosts/wanted/{question}")
    async def host_decision(question: str) -> dict[str, Any]:
        """How a host's question went (design 0024 §3): waiting, or always, once or no; the proxy reads it while it
        holds the agent's connection."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(workspaces.network.decision, question)
        return found

    @routes.post("/workspaces/{name}/hosts/wanted")
    async def host_wanted(name: str, body: HostWanted) -> dict[str, Any]:
        """A workspace's agent reaches a host (design 0024 §3): allowed by its record, quiet (refused lately), or the
        question the owner is asked, which the proxy then waits on."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: workspaces.host_wanted(name, body.host))
        return found

    @routes.post("/workspaces/{name}/hosts")
    async def hosts(name: str, answer: HostAnswer, request: Request) -> dict[str, Any]:
        """Allow a workspace's agent a host through Clank's proxy, or take it back (design 0024 §1); its view after."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: workspaces.allow_host(name, answer.host, answer.allow, actor=actor)
        )
        return found

    @routes.post("/workspaces/{name}/cloud/ask")
    async def ask_cloud(name: str) -> dict[str, Any]:
        """Before a client starts a workspace's agent: whether the workspace must be asked about the main slot's cloud
        model, and the question when it must (the one open, when there is one)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(workspaces.ask_cloud, name)
        return found

    return routes


async def _start(
    workspaces: "Workspaces", kind: str, request: Request, params: dict[str, Any] | None = None
) -> dict[str, Any]:
    actor = client_actor(request.headers.get(CLIENT_HEADER))
    key = request.headers.get(REQUEST_KEY_HEADER)
    started = await workspaces.kernel.operations.start(kind, params or {}, actor=actor, request_key=key)
    return started.model_dump(mode="json")
