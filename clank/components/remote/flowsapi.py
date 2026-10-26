"""The phone's flow routes (design 0025 §6; plan s58): what the Flows tab reads and does, each a thin call on the flows
component's part, so the phone knows no rule of the runner and says a flow's state as every client does.

- `GET /api/flows`: the service's summaries (`flows/summaries.py`: one line per flow, its state in a word and in
  words, the question it waits for), and the plannings open per workspace (design 0013 §15), for the list.
- `GET /api/flows/{workspace}/{name}`: what the Monitor's Flow view shows (design 0013 §12), as the console draws it:
  the run, every box with its tries, the proposals, Waiting for you, the deliverables, Ahead, a `version`.
- `POST .../run`, `.../pause`, `.../stop`: the run steered, recorded as the device's.
- `POST .../proposals/accept` and `.../proposals/reject`: by their ids, or all still waiting.
- `POST /api/flows/new`: a planning opened in Clank's VS Code window on the PC (the one place that needs no terminal);
  it waits for the window when none runs there.

The kernel's refusals (403, 404, 409) reach the phone with their words. Every action needs the page's own header, as
the listener's other actions do (`app.py`: `acting`).
"""

from collections.abc import Callable
from typing import Any

import anyio.to_thread
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

from clank.kernel.api import ApiError
from clank.kernel.core import Kernel
from clank.kernel.events import Actor


class ProposalsBody(BaseModel):
    """Which proposals to accept or reject: by their ids, or all still waiting."""

    proposals: list[str] = Field(default_factory=list, description="The proposals, by their ids (T1).")
    every: bool = Field(False, alias="all", description="Every proposal still waiting.")

    model_config = ConfigDict(populate_by_name=True)


class NewBody(BaseModel):
    """A planning to open: in which workspace, and the flow's name (empty: the first name free)."""

    workspace: str = Field(min_length=1)
    name: str = ""


def flow_routes(kernel: Kernel, device_of: Callable[[Request], Actor], acting: Callable[[Request], Actor]) -> APIRouter:
    """The routes, under `/api`; `device_of` names the paired device reading, `acting` the one acting."""
    routes = APIRouter()
    flows = kernel.parts["flows"]

    async def served(work: Callable[[], Any]) -> Any:
        """The flows' answer, off the event loop; its refusals as the phone reads them."""
        try:
            return await anyio.to_thread.run_sync(work)
        except ApiError as error:
            raise HTTPException(error.status, str(error)) from error

    @routes.get("/flows")
    async def listed(request: Request) -> Any:
        device_of(request)
        return await served(lambda: {"flows": flows.summaries(), "plannings": flows.plannings_open()})

    @routes.post("/flows/new")
    async def new(body: NewBody, request: Request) -> Any:
        actor = acting(request)
        return await served(lambda: flows.new(body.workspace, "", body.name, "vscode", actor=actor))

    @routes.get("/flows/{workspace}/{name}")
    async def shown(workspace: str, name: str, request: Request) -> Any:
        device_of(request)
        return await served(lambda: _view_or_planning(flows, workspace, name))

    @routes.post("/flows/{workspace}/{name}/run")
    async def run(workspace: str, name: str, request: Request) -> Any:
        actor = acting(request)
        return await served(lambda: flows.go(workspace, name, actor=actor))

    @routes.post("/flows/{workspace}/{name}/pause")
    async def pause(workspace: str, name: str, request: Request) -> Any:
        actor = acting(request)
        return await served(lambda: flows.pause(workspace, name, actor=actor))

    @routes.post("/flows/{workspace}/{name}/stop")
    async def stop(workspace: str, name: str, request: Request) -> Any:
        actor = acting(request)
        return await served(lambda: flows.stop(workspace, name, actor=actor))

    @routes.post("/flows/{workspace}/{name}/proposals/{decision}")
    async def decide(workspace: str, name: str, decision: str, body: ProposalsBody, request: Request) -> Any:
        if decision not in ("accept", "reject"):
            raise HTTPException(404, f"proposals are accepted or rejected, not {decision}")
        actor = acting(request)
        return await served(
            lambda: flows.decide(workspace, name, decision, body.proposals, every=body.every, actor=actor)
        )

    return routes


def _view_or_planning(flows: Any, workspace: str, name: str) -> Any:
    """The flow's view; for a flow being built with the model, its file not written yet, its planning's view."""
    try:
        return flows.view("", f"{workspace}/{name}")
    except ApiError as missing:
        if missing.status != 404:
            raise
        try:
            return flows.planning_view(workspace, f"{workspace}/{name}")
        except ApiError:
            raise missing from None
