"""The phone's session routes (design 0025 §7; plan s59): the conversation stream, the Guide and the context of a
session, each a thin call on the agents component's service, so the phone's session screen moves with the stream
(design 0023 §3) and offers what the Monitor's Guide offers (design 0012 §9), knowing no rule of either.

- `GET /api/conversation/stream?workspace=&session=&limit=&after=&after_session=`: the conversation pushed as it
  happens: `connected`, a snapshot, each change of the mirror with its version as the event's id, the model's readout
  each second while the session works; `Last-Event-ID` (or `after`) resumes from a version of `after_session`. The
  listener logs it as one line, as it logs the phone's own stream (`app.py`). A workspace Clank does not have is 404.
- `GET /api/guide/{workspace}/{session}`: what the Guide offers now, each action with whether it can run and why not,
  what it does, its cost and its state; `POST .../stop`, `.../note` (`text`, `about`), `.../compact`, `.../pause`,
  `.../resume`, `.../undo` (`message`, `part`, `steps`, `said`), `.../redo` and `.../drop` (`part`), each recorded as
  the device's; what the agents refuse comes back as 409 with their words.
- `GET /api/context/{workspace}/{session}`: the session's context totals (design 0012 §4.1 and §4.4): the window, used,
  left before compaction, the parts with their biggest items.
"""

from collections.abc import Callable
from typing import Any

import anyio.to_thread
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from clank.components.agents.service import GuideError
from clank.components.workspaces.service import WorkspaceUnavailable
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from clank.kernel.settings import SettingsError

CONVERSATION_STREAM_PATH = "/api/conversation/stream"


class NoteBody(BaseModel):
    """A note to the model (design 0012 §9.3), and what it is about when the phone names it."""

    text: str = Field(min_length=1)
    about: str = ""


class UndoBody(BaseModel):
    """The revert the Guide's offer named (design 0012 §9.5): where to cut, and what it takes back, as confirmed."""

    message: str = ""
    part: str = ""
    steps: list[int] = Field(default_factory=list)
    said: list[str] = Field(default_factory=list)


class DropBody(BaseModel):
    """A finished call's result to clear (design 0012 §9.7), by its part."""

    part: str = Field(min_length=1)


def session_routes(
    kernel: Kernel,
    closers: set[Callable[[], None]],
    device_of: Callable[[Request], Actor],
    acting: Callable[[Request], Actor],
    bridged: Callable[..., Any],
) -> APIRouter:
    """The routes, under `/api`; `device_of` names the paired device reading, `acting` the one acting, `bridged` runs
    a call off the event loop and says the agents' refusals as the phone reads them."""
    routes = APIRouter()
    agents = kernel.parts["agents"]
    workspaces = kernel.parts["workspaces"]

    async def guided(work: Callable[[], Any]) -> Any:
        try:
            return await bridged(work)
        except GuideError as error:
            raise HTTPException(409, str(error)) from error

    @routes.get("/conversation/stream")
    async def conversation_stream(
        request: Request,
        workspace: str,
        session: str = "",
        limit: int = 40,
        after: int | None = None,
        after_session: str = "",
    ) -> StreamingResponse:
        device_of(request)
        try:
            folder = str(await anyio.to_thread.run_sync(workspaces.folder_of, workspace))
        except (WorkspaceUnavailable, SettingsError) as error:
            raise HTTPException(404, str(error)) from error
        last = request.headers.get("last-event-id", "")
        if after is None and last.isdigit():
            after = int(last)
        shown = max(1, min(limit, 100))
        body = agents.conversation_stream(folder, session, shown, after, closers, after_session=after_session)
        return StreamingResponse(body, media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @routes.get("/guide/{workspace}/{session}")
    async def guide(workspace: str, session: str, request: Request, item: str = "") -> Any:
        device_of(request)
        return await guided(lambda: agents.guide.offer(workspace, session, item=item))

    @routes.post("/guide/{workspace}/{session}/stop")
    async def guide_stop(workspace: str, session: str, request: Request) -> Any:
        actor = acting(request)
        return await guided(lambda: agents.guide.stop(workspace, session, actor=actor))

    @routes.post("/guide/{workspace}/{session}/note")
    async def guide_note(workspace: str, session: str, body: NoteBody, request: Request) -> Any:
        actor = acting(request)
        return await guided(lambda: agents.guide.note(workspace, session, body.text, actor=actor, about=body.about))

    @routes.post("/guide/{workspace}/{session}/compact")
    async def guide_compact(workspace: str, session: str, request: Request) -> Any:
        actor = acting(request)
        return await guided(lambda: agents.guide.compact(workspace, session, actor=actor))

    @routes.post("/guide/{workspace}/{session}/pause")
    async def guide_pause(workspace: str, session: str, request: Request) -> Any:
        actor = acting(request)
        return await guided(lambda: agents.pausing.pause(workspace, session, actor=actor))

    @routes.post("/guide/{workspace}/{session}/resume")
    async def guide_resume(workspace: str, session: str, request: Request) -> Any:
        actor = acting(request)
        return await guided(lambda: agents.pausing.resume(workspace, session, actor=actor))

    @routes.post("/guide/{workspace}/{session}/undo")
    async def guide_undo(workspace: str, session: str, body: UndoBody, request: Request) -> Any:
        actor = acting(request)
        return await guided(
            lambda: agents.guide.undo(
                workspace, session, actor=actor, message=body.message, part=body.part, steps=body.steps, said=body.said
            )
        )

    @routes.post("/guide/{workspace}/{session}/redo")
    async def guide_redo(workspace: str, session: str, request: Request) -> Any:
        actor = acting(request)
        return await guided(lambda: agents.guide.redo(workspace, session, actor=actor))

    @routes.post("/guide/{workspace}/{session}/drop")
    async def guide_drop(workspace: str, session: str, body: DropBody, request: Request) -> Any:
        actor = acting(request)
        return await guided(lambda: agents.guide.drop(workspace, session, body.part, actor=actor))

    @routes.get("/context/{workspace}/{session}")
    async def context(workspace: str, session: str, request: Request) -> Any:
        device_of(request)
        return await bridged(lambda: agents.context(workspace, session))

    return routes
