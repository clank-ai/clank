"""The workspaces component's routes: Docker's status, and starting and stopping it; the workspaces, and opening,
installing the software of (design 0004 §10), stopping and removing one (design 0004 §1).

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


class SetupRequest(BaseModel):
    """A workspace's folder; a setup command to keep and run (empty: its record's, else the proposed one); `yes` runs
    it without asking."""

    folder: str
    command: str = ""
    yes: bool = False


class CloudAnswer(BaseModel):
    """Whether a workspace's agent may use the cloud model (false: kept on this machine)."""

    allow: bool


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

    @routes.post("/workspaces/{name}/cloud")
    async def cloud(name: str, answer: CloudAnswer, request: Request) -> dict[str, Any]:
        """Allow a workspace's agent the cloud model, or keep it on this machine (design 0016 §9); its view after."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: workspaces.allow_cloud(name, answer.allow, actor=actor)
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
