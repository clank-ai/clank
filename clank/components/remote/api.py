"""The remote component's routes in the service's local API (design 0005 §5): whether remote access is on and where,
turning it on and off, making a pairing code, the paired devices and revoking one, and the files the agents sent. Only
the computer's own clients reach this API (the local token), so a code is never made from a device.
"""

from typing import TYPE_CHECKING, Any

import anyio.to_thread
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from clank.kernel.access import CLIENT_HEADER, client_actor
from clank.kernel.api import ApiError

if TYPE_CHECKING:
    from clank.components.remote.service import Remote


class SwitchRequest(BaseModel):
    """Remote access on or off."""

    on: bool


class PairRequest(BaseModel):
    """A name for the device to pair."""

    name: str = Field("phone", min_length=1, max_length=40)


def router(remote: "Remote") -> APIRouter:
    """The routes, over the remote component's part."""
    from clank.components.remote.service import RemoteError

    routes = APIRouter()

    @routes.get("/remote")
    async def status() -> dict[str, Any]:
        """Whether remote access is on, listening and published, its address, why not, and the paired devices."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(remote.status)
        return found

    @routes.post("/remote/switch")
    async def switch(wanted: SwitchRequest, request: Request) -> dict[str, Any]:
        """Turn remote access on or off; it applies within a few seconds."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: remote.switch(wanted.on, actor=actor))
        return found

    @routes.post("/remote/pair")
    async def pair(wanted: PairRequest, request: Request) -> dict[str, Any]:
        """A code to pair a device: typed on the phone page within fifteen minutes, once."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: remote.pair(wanted.name, actor=actor))
        return found

    @routes.post("/remote/pair/cancel")
    async def cancel(request: Request) -> dict[str, Any]:
        """Cancel the pairing code waiting: it no longer pairs (`canceled`: whether one was waiting)."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: remote.cancel_pairing(actor=actor))
        return found

    @routes.post("/remote/devices/{id}/revoke")
    async def revoke(id: str, request: Request) -> dict[str, Any]:
        """Revoke a paired device."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: remote.revoke(id, actor=actor))
        except RemoteError as error:
            raise ApiError(404, "not_found", str(error)) from error
        return found

    @routes.get("/remote/traffic")
    async def traffic(device: str = "", limit: int = 200) -> dict[str, Any]:
        """What the paired devices and this computer exchanged (one device's, when named), newest first, each without
        its bodies."""
        found = await anyio.to_thread.run_sync(remote.traffic.recent, device, max(1, min(limit, 2000)))
        return {"exchanges": found}

    @routes.get("/remote/traffic/{id}")
    async def exchange(id: str) -> dict[str, Any]:
        """One exchange whole: what the device asked, and what it was sent."""
        found: dict[str, Any] | None = await anyio.to_thread.run_sync(remote.traffic.exchange, id)
        if found is None:
            raise ApiError(404, "not_found", f"no exchange {id}")
        return found

    @routes.get("/remote/files")
    async def files(limit: int = 100) -> dict[str, Any]:
        """The files the agents sent to the phone, the newest first."""
        return {"files": await anyio.to_thread.run_sync(remote.files, max(1, min(limit, 500)))}

    return routes
