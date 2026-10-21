"""The machine component's routes: the profile with the last doctor run, starting a doctor run, and the machine's
meters of the last minutes.

They are included under `/api/v1/` behind the local token like every route (design 0002 §2.7).
"""

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Request

from clank.kernel.access import CLIENT_HEADER, REQUEST_KEY_HEADER, client_actor

if TYPE_CHECKING:
    from clank.components.machine.service import Machine


def router(machine: "Machine") -> APIRouter:
    """The routes, over the machine component's part."""
    routes = APIRouter()

    @routes.get("/machine")
    def profile() -> dict[str, Any]:
        """The machine profile, and the checks of the last doctor run."""
        return {"profile": machine.profile().model_dump(mode="json"), "doctor": machine.last_doctor()}

    @routes.get("/machine/meters")
    def meters() -> dict[str, Any]:
        """The machine's meters of the last minutes, a reading a second, oldest first."""
        return {"samples": machine.meters()}

    @routes.post("/machine/doctor")
    async def doctor(request: Request) -> dict[str, Any]:
        """Run the doctor: detect the machine again, then run every check."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        key = request.headers.get(REQUEST_KEY_HEADER)
        started = await machine.kernel.operations.start("machine.doctor", actor=actor, request_key=key)
        return started.model_dump(mode="json")

    return routes
