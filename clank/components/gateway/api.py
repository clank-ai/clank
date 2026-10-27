"""The gateway component's routes in the service's API: its status, what it does now, the requests it kept (newest
first, and one with what was asked and answered), the routes its process follows, and starting and stopping it again
(design 0004 §2); and completion in VS Code (design 0006 §6): `GET /gateway/completion` (its settings, the fast slot,
what loading it needs, the gateway's last completions counted) and `POST /gateway/completion` (turn it on or off, or
change its wait or its lines). `GET /gateway/holds`: the sessions paused and the requests they hold (design 0012 §9.4;
the Guide pauses and resumes through the agents' routes). They are behind the local token like every route (design
0002 §2.7).
"""

from typing import TYPE_CHECKING, Any, Literal

import anyio.to_thread
from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field

from clank.kernel.access import CLIENT_HEADER, client_actor
from clank.kernel.api import ApiError

if TYPE_CHECKING:
    from clank.components.gateway.service import Gateway


class Wanted(BaseModel):
    """A role loaded on demand that a request is waiting for."""

    role: str


class CloudWanted(BaseModel):
    """A workspace not yet answered whether it may use the cloud model, whose request the gateway holds."""

    workspace: str
    session: str = ""


class LimitsChange(BaseModel):
    """The cloud's spending limits to change: either may be left out; null removes one."""

    day_usd: float | None = Field(None, gt=0)
    month_usd: float | None = Field(None, gt=0)


class VisionChange(BaseModel):
    """What to change of the vision model: its mode, its idle minutes or its preset."""

    mode: Literal["off", "on-demand", "always"] | None = None
    idle_minutes: int | None = Field(None, ge=1, le=1440)
    preset: str | None = None


class CompletionChange(BaseModel):
    """What to change of how completion works: any of on, its wait (ms) and its lines."""

    enabled: bool | None = None
    delay_ms: int | None = Field(None, ge=0, le=2000)
    lines: Literal["one", "few"] | None = None


def router(gateway: "Gateway") -> APIRouter:
    """The routes, over the gateway component's part."""
    routes = APIRouter()

    @routes.get("/gateway")
    async def status() -> dict[str, Any]:
        """Whether the gateway runs, where it listens and which process it is; or why it does not run. On Linux, its
        socket (`socket`, where the edge reaches it on Docker Engine), or why it has none (`socket_problem`)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(gateway.status)
        return found

    @routes.get("/gateway/activity")
    async def activity(session: str = "", subagents: bool = False, ended: bool = False) -> dict[str, Any]:
        """What the gateway does now, of one session when it is named (OpenCode's session id), and of the subagents it
        started too with `subagents`: each request in flight, how many it has served, and how the last one went; with
        `ended`, the session's own requests that ended, oldest first, numbers only (design 0012 §6.1)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(gateway.activity, session, subagents, ended)
        return found

    @routes.get("/gateway/live")
    async def live(after: int = 0, id: str = "", session: str = "", subagents: bool = False) -> dict[str, Any]:
        """The newest model request as it streams: what was asked, its thinking, its answer and its tool calls from the
        character `after` on (`length`: all of it so far); the last one's once it ended. Of one session when it is
        named (OpenCode's session id), and of the subagents it started too with `subagents`."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(gateway.live, after, id, session, subagents)
        return found

    @routes.get("/gateway/holds")
    async def holds() -> dict[str, Any]:
        """The sessions paused in the gateway (design 0012 §9.4), each with since when, by whom and the requests it
        holds now, with their seconds; none, and why, when the gateway does not run or answer."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(gateway.holds)
        return found

    @routes.get("/gateway/network/log")
    async def network_log(limit: int = 30, workspace: str = "") -> dict[str, Any]:
        """The agent's newest internet exchanges through the proxy (design 0024 §4), of one workspace when named, and
        today's bytes by host."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: gateway.network_log(limit, workspace))
        return found

    @routes.get("/gateway/network/hosts")
    async def network_hosts() -> dict[str, Any]:
        """The hosts each workspace's agent may reach, with when and how each was allowed (design 0024 §1)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(gateway.network_hosts)
        return found

    @routes.get("/gateway/requests")
    async def requests(limit: int = 50) -> dict[str, Any]:
        """The newest model requests kept, newest first, each in brief: who asked, how it went, tokens and speed."""
        found = await anyio.to_thread.run_sync(gateway.requests, max(1, min(limit, 500)))
        return {"requests": found}

    @routes.get("/gateway/requests/{id}")
    async def request(id: str) -> dict[str, Any]:
        """One kept request, with what was asked and what was answered."""
        found = await anyio.to_thread.run_sync(gateway.request, id)
        if found is None:
            raise ApiError(404, "not_found", f"no kept request {id}")
        return found

    @routes.get("/gateway/routes")
    async def table() -> dict[str, Any]:
        """Where each role's requests go: each slot's state and engine, and the roles' slots."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(gateway.routes)
        return found

    @routes.get("/gateway/completion")
    async def completion() -> dict[str, Any]:
        """Completion in VS Code: its settings, the fast slot, what loading its preset needs, and the gateway's last
        completions counted (their median and 95th percentile)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(gateway.completion)
        return found

    @routes.post("/gateway/completion")
    async def change_completion(wanted: CompletionChange, request: Request) -> dict[str, Any]:
        """Turn completion on or off, or change its wait or its lines; the view after."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        values = wanted.model_dump(exclude_none=True)
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: gateway.set_completion(values, actor=actor))
        return found

    @routes.post("/gateway/wanted")
    async def wanted(body: Wanted) -> dict[str, Any]:
        """The gateway waits for a role loaded on demand: its model is loaded (`refused` says why not)."""
        return await gateway.wanted(body.role)

    @routes.post("/gateway/cloud-wanted")
    async def cloud_wanted(body: CloudWanted) -> dict[str, Any]:
        """The gateway holds a request of a workspace not yet answered (design 0016 §9): its question is asked (the
        one open given again); `allowed` when it was answered already."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(gateway.cloud_wanted, body.workspace, body.session)
        return found

    @routes.get("/gateway/cost")
    async def cost(workspace: str = "") -> dict[str, Any]:
        """What the cloud cost today and this month (this computer's days), against the limits, whether it is paused
        or near a limit, with the words every client shows (design 0016 §11); given a workspace, its own today and this
        month too (`workspace`)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: gateway.cost(workspace))
        return found

    @routes.get("/gateway/cost/sessions")
    async def cost_sessions(response: Response, workspace: str = "", limit: int = 50, after: int = 0) -> Any:
        """Each session's cloud cost, its subagents' counted in, newest first; `after` a revision: only those changed
        since (the header X-Clank-Revision gives the newest)."""
        found = await anyio.to_thread.run_sync(
            lambda: gateway.cost_sessions(workspace=workspace, limit=max(1, min(limit, 500)), after=max(0, after))
        )
        response.headers["X-Clank-Revision"] = str(gateway.costs.revision())
        return found

    @routes.get("/gateway/cost/requests")
    async def cost_requests(
        response: Response, session: str = "", workspace: str = "", since: str = "", limit: int = 100, after: int = 0
    ) -> Any:
        """Each cloud request's cost, newest first: of a session (its subagents' too) or a workspace, since a time;
        `after` a revision: only those changed since (the header X-Clank-Revision gives the newest)."""
        wanted = {"session": session, "workspace": workspace, "since": since, "limit": max(1, min(limit, 1000)),
                  "after": max(0, after)}  # fmt: skip
        found = await anyio.to_thread.run_sync(lambda: gateway.cost_requests(**wanted))
        response.headers["X-Clank-Revision"] = str(gateway.costs.revision())
        return found

    @routes.put("/gateway/cost/limits")
    async def limits(change: LimitsChange, request: Request) -> dict[str, Any]:
        """Set or remove the daily or monthly limit of the cloud's spending (`config/cost.json`), recorded with who
        did it; the cost view after."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        values = change.model_dump(exclude_unset=True)
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: gateway.set_limits(values, actor=actor))
        return found

    @routes.get("/gateway/vision")
    async def vision() -> dict[str, Any]:
        """The model that reads images: its mode, its slot, how long since it was wanted, what loading it needs."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(gateway.vision)
        return found

    @routes.post("/gateway/vision")
    async def change_vision(wanted: VisionChange, request: Request) -> dict[str, Any]:
        """Set the vision model off, on demand or always (or its idle minutes, or its preset); the view after."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        values = wanted.model_dump(exclude_none=True)
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: gateway.set_vision(values, actor=actor))
        return found

    @routes.post("/gateway/restart")
    async def restart() -> dict[str, Any]:
        """Stop the gateway and start it again (it picks up changed settings); its status, with what went wrong said
        (`problem`): never half done, whatever the stop met a start is tried."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(gateway.restart)
        return found

    @routes.post("/gateway/stop")
    async def stop() -> dict[str, Any]:
        """Stop the gateway; what happened."""
        ended = await anyio.to_thread.run_sync(gateway.stop)
        return {"stopped": ended}

    return routes
