"""The agents component's routes (design 0004 §4): making a workspace's agent ready.

`GET /agents/plan` says what the agent program would be given (its model and limits), writing nothing. `POST
/agents/prepare` writes the agent program's configuration into the workspace's container and answers the command a
terminal runs to start it; it is quick, so it is a request, not an operation. A workspace whose container does not run,
or a program Clank has no adapter for, is refused with the reason (409). `POST /agents/vscode` opens a folder in Clank's
VS Code window, OpenCode beside the files: an operation (`vscode.py`), since the first time installs the window's
extensions. `GET /agents/servers` lists the MCP servers of a workspace's agent with whether it gets each, and `POST
/agents/servers` gives one or takes it away (design 0004 §10). The session bridge's routes (design 0005 §2): `GET
/agents/sessions` (the OpenCode servers in a workspace's container, their sessions and what waits), a session's
messages, one tool call whole (design 0012 §7), sending one, starting a session, stopping one, and replying to a
permission or a question; the bridge's refusal is a 409 in its own words. The review of the agent's changes (design
0007): `GET /agents/review` (a workspace's mode, by folder or by name, whether its agents are watched, how many changes
wait, and what its window was told of its model's last change, design 0013 §7), `POST /agents/review` (switch it),
`GET /agents/changes` (the newest changes, without the files) and `GET /agents/changes/{id}` (one, with the file
before, after, and as written). `POST /agents/annotations` sends a figure the owner marked up (design 0008), or a
page of a PDF; `POST /agents/latex/pages` renders a PDF of a folder as page images to mark up (design 0020 §10),
and `POST /agents/latex/comments` sends the owner's comments on lines of LaTeX files to the agent (§11). `POST
/agents/show` opens files of a workspace's folder in the owner's VS Code window (design 0018 §7): the agent's, through
the gateway, refused (409) while no VS Code window follows the service. The
Monitor's flows (design 0012 §6.1): `GET /agents/flow/{workspace}` (the flows kept,
briefly) and `GET /agents/flow/{workspace}/{session}` (one, whole, or what changed after the version `since`, with the
session's marks); a session's context totals (design 0012 §4.1): `GET /agents/context/{workspace}/{session}`; what it
does now (design 0012 §5): `GET /agents/now/{workspace}/{session}`. The Monitor's Watch for (design 0012 §8): `GET
/agents/marks` (the newest marks, and how many are not seen) and `POST /agents/marks/seen`. The Monitor's Guide (design
0012 §9): `GET /agents/guide/{workspace}/{session}` (each action with its key, whether it can run and why not, what it
does, its exact call, its cost and its last state; Drop's for the call `item`), and `POST
/agents/guide/{workspace}/{session}/stop`, `.../note`, `.../compact`, `.../undo` (the revert confirmed), `.../redo` and
`.../drop` (the call's part); an action that cannot run is a 409 in the Guide's words.
"""

from typing import TYPE_CHECKING, Any

import anyio.to_thread
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from clank.components.workspaces.service import WorkspaceUnavailable
from clank.kernel.access import CLIENT_HEADER, REQUEST_KEY_HEADER, client_actor

if TYPE_CHECKING:
    from clank.components.agents.service import Agents


class GiveRequest(BaseModel):
    """An MCP server to give to a workspace's agent (`given`), or to take away."""

    workspace: str
    name: str
    given: bool = True


class PrepareRequest(BaseModel):
    """A workspace, and the agent program to make ready in it."""

    workspace: str
    program: str = "opencode"


class VsCodeRequest(BaseModel):
    """A folder to open in Clank's VS Code window, and a file of it, if any."""

    folder: str
    file: str = Field("", description="A file of the folder to open in the window too, named from the folder.")


class MessageRequest(BaseModel):
    """A message to send to an agent's session."""

    text: str


class StartRequest(BaseModel):
    """A new session's first message, and its title."""

    text: str = ""
    title: str = ""


class ReplyRequest(BaseModel):
    """A reply to a permission the agent asked for: once, always or reject."""

    reply: str


class ReviewRequest(BaseModel):
    """A workspace's mode for the agent's changes: review or auto."""

    workspace: str
    mode: str


class ModeRequest(BaseModel):
    """A workspace's mode as the owner sees it: plan, review or auto (design 0009 §7)."""

    workspace: str
    mode: str


class ImplementRequest(BaseModel):
    """A plan to hand to the agent (its path in the workspace's folder), in review or auto mode (design 0009 §8)."""

    workspace: str
    plan: str
    mode: str


class AnnotationRequest(BaseModel):
    """A figure the owner marked up: its file, the marks, the message, and the marked-up copy (a PNG, as a data URL)."""

    folder: str
    figure: str
    marks: list[dict[str, Any]]
    message: str = ""
    image: str


class CommentsRequest(BaseModel):
    """Comments on lines of LaTeX files to send to the agent: each its file (from the folder), its first and last line,
    the text it covers and its words; and a message besides."""

    folder: str
    comments: list[dict[str, Any]]
    message: str = ""


class PagesRequest(BaseModel):
    """A PDF of a folder to mark up, from the folder."""

    folder: str
    pdf: str


class ShowRequest(BaseModel):
    """Files of a workspace's folder to open in the owner's VS Code window, as the agent named them, and why."""

    workspace: str
    paths: list[str]
    why: str = ""


class SeenRequest(BaseModel):
    """Marks of the Monitor's Watch for seen: these, by their ids, or every mark of a session (or of a workspace)."""

    ids: list[str] | None = None
    workspace: str = ""
    session: str = ""


class NoteRequest(BaseModel):
    """A note to the model (design 0012 §9.3): its text, what it is about ("step 12, `bash pytest -q`"), and whether,
    while a call waits for approval, it rejects that call instead, the note its reason."""

    text: str
    about: str = ""
    reject: bool = True


class UndoRequest(BaseModel):
    """An undo (design 0012 §9.5): the revert the owner confirmed, its message and its part ("" for the turn), and what
    its window said it takes back (the steps' numbers, the owner's messages' ids); refused when any of it changed
    since."""

    message: str = Field(min_length=1)
    part: str = ""
    steps: list[int]
    said: list[str]


class DropRequest(BaseModel):
    """A drop (design 0012 §9.7): the call whose result is cleared, by its part's id."""

    part: str


class AnswerRequest(BaseModel):
    """The answers to a question the agent asked: for each of its questions, the options chosen or a text."""

    answers: list[list[str]]


def router(agents: "Agents") -> APIRouter:
    """The routes, over the agents component's part."""
    from clank.components.agents.service import (
        AgentError,
        AnnotationError,
        CommentError,
        GuideError,
        ModeError,
        PageError,
        ReviewError,
        ShowError,
    )
    from clank.components.agents.sessions import SessionError
    from clank.kernel.api import ApiError
    from clank.kernel.settings import SettingsError

    routes = APIRouter()

    @routes.get("/agents/plan")
    async def plan(program: str = "opencode") -> dict[str, Any]:
        """What the agent program would be given, writing nothing: its model, that model's limits, and notes."""
        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(agents.plan, program)
        except AgentError as error:
            raise ApiError(409, "refused", str(error)) from error
        return found

    @routes.post("/agents/prepare")
    async def prepare(wanted: PrepareRequest) -> dict[str, Any]:
        """Write the agent's configuration into the workspace's container; the command that starts the agent there."""
        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(agents.prepare, wanted.workspace, wanted.program)
        except (AgentError, WorkspaceUnavailable) as error:
            raise ApiError(409, "refused", str(error)) from error
        return found

    @routes.post("/agents/vscode")
    async def vscode(wanted: VsCodeRequest, request: Request) -> dict[str, Any]:
        """Open a folder in Clank's VS Code window, OpenCode beside the files: an operation that sets the window up the
        first time (its settings, its extensions) and then opens the folder, and a file of it when one is named."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        key = request.headers.get(REQUEST_KEY_HEADER)
        params = wanted.model_dump()
        started = await agents.kernel.operations.start("agents.vscode", params, actor=actor, request_key=key)
        return started.model_dump(mode="json")

    async def bridged(work: Any, *args: Any) -> Any:
        """Run a session action off the event loop; the bridge's refusal is a 409 in its own words."""
        try:
            return await anyio.to_thread.run_sync(work, *args)
        except (SessionError, AgentError, GuideError, WorkspaceUnavailable) as error:
            raise ApiError(409, "refused", str(error)) from error

    @routes.get("/agents/sessions")
    async def sessions(workspace: str) -> dict[str, Any]:
        """The OpenCode servers in a workspace's container: each one's sessions with their status, and the permissions
        and questions waiting (design 0005 §2)."""
        return {"servers": await bridged(agents.sessions.servers, workspace)}

    @routes.get("/agents/flow/{workspace}")
    async def flows(workspace: str) -> dict[str, Any]:
        """The flows the service keeps of the workspace's sessions (design 0012 §6.1), newest heard first, each its
        head (its session's facts) and its version."""
        return {"flows": await anyio.to_thread.run_sync(agents.flows.flows, workspace)}

    @routes.get("/agents/flow/{workspace}/{session}")
    async def flow(workspace: str, session: str, since: int = 0) -> dict[str, Any]:
        """A session's flow (design 0012 §6): its head, its nodes (the owner's messages and notes, steps, calls,
        subagents, compaction bands, each with the version at which it changed) and its branches; with `since`, only
        what changed after that version (`whole` when it is not one of this flow's); and its Watch for marks, all of
        them (design 0012 §8)."""
        found = await anyio.to_thread.run_sync(agents.flows.flow, workspace, session, since)
        if found is None:
            raise ApiError(404, "not_found", f"Clank keeps no flow of {session} in {workspace}: its watcher has not "
                           "seen that session")  # fmt: skip
        return {**found, "marks": agents.marks.marks(workspace, session)}

    @routes.get("/agents/marks")
    async def marks(workspace: str = "", session: str = "", limit: int = 100) -> dict[str, Any]:
        """The marks the Watch for rules left (design 0012 §8), newest first, of a workspace or a session when named,
        and how many marks are not seen yet."""
        found = agents.marks.marks(workspace, session, max(1, min(limit, 1000)))
        return {"marks": found, "unseen": agents.marks.unseen()}

    @routes.post("/agents/marks/seen")
    async def seen(wanted: SeenRequest, request: Request) -> dict[str, Any]:
        """Marks seen: by their ids, or every mark of a session (or of a workspace); how many were not seen."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        count = await anyio.to_thread.run_sync(
            lambda: agents.marks.seen(wanted.ids, workspace=wanted.workspace, session=wanted.session, actor=actor)
        )
        return {"seen": count}

    async def pausing(work: Any) -> dict[str, Any]:
        """Run a pause or a resume off the event loop; one that cannot run is a 409 in its own words."""
        from clank.components.agents.service import PauseError

        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(work)
        except PauseError as error:
            raise ApiError(409, "refused", str(error)) from error
        return found

    @routes.get("/agents/guide/{workspace}/{session}/pause")
    async def pause_offered(workspace: str, session: str) -> dict[str, Any]:
        """The Guide's pause (design 0012 §9.4) for the session's root: `p`, pause or resume as it stands, whether it
        can run and why not, what it does, its exact call to the gateway, its cost and its state."""
        return await pausing(lambda: agents.pausing.action(workspace, session))

    @routes.post("/agents/guide/{workspace}/{session}/pause")
    async def pause(workspace: str, session: str, request: Request) -> dict[str, Any]:
        """Pause the session's root after its step: its next model requests, and its subagents', wait in the gateway."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        return await pausing(lambda: agents.pausing.pause(workspace, session, actor=actor))

    @routes.post("/agents/guide/{workspace}/{session}/resume")
    async def resume(workspace: str, session: str, request: Request) -> dict[str, Any]:
        """Resume the session's root: the requests it holds go to the model."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        return await pausing(lambda: agents.pausing.resume(workspace, session, actor=actor))

    @routes.get("/agents/context/{workspace}/{session}")
    async def context(workspace: str, session: str) -> dict[str, Any]:
        """A session's context totals (design 0012 §4.1, §4.4): how much of the window its last finished step used,
        how much is left before OpenCode compacts, the share read from the cache, what sits on the GPU, whose
        conversation the engine holds, and the facts these were read with (its engine's, its model's)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(agents.context, workspace, session)
        return found

    @routes.get("/agents/now/{workspace}/{session}")
    async def doing_now(workspace: str, session: str) -> dict[str, Any]:
        """What a session does now (design 0012 §5): its phase, from the gateway or from OpenCode, with its detail; its
        thinking and its answer against their budgets ("about" while counted live); the prompt; the call being
        written; its speed and its steps'; and the loop guard's state."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(agents.now, workspace, session)
        return found

    @routes.get("/agents/guide/{workspace}/{session}")
    async def guide(workspace: str, session: str, item: str = "") -> dict[str, Any]:
        """What the Guide offers for a session (design 0012 §9.1, §9.4, §9.5, §9.7): Stop now, a note, Compact now,
        the pause, Undo (or Undo turn, or Redo) and Drop (of the call `item`, when named), each with its key, whether
        it can run now and why not, what it does, its exact call to OpenCode or the gateway, its cost and its last
        state (the pause's: pausing after this step, held with its timer, resumed); and the server that runs the
        session."""
        found: dict[str, Any] = await bridged(lambda: agents.guide.offer(workspace, session, item=item))
        return found

    @routes.post("/agents/guide/{workspace}/{session}/stop")
    async def guide_stop(workspace: str, session: str, request: Request) -> dict[str, Any]:
        """Stop the session now (design 0012 §9.2): abort it, and reject what waits in it and its subagents."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await bridged(lambda: agents.guide.stop(workspace, session, actor=actor))
        return found

    @routes.post("/agents/guide/{workspace}/{session}/note")
    async def guide_note(workspace: str, session: str, wanted: NoteRequest, request: Request) -> dict[str, Any]:
        """Send the model a note (design 0012 §9.3), or reject the call waiting for approval with it."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await bridged(lambda: agents.guide.note(
            workspace, session, wanted.text, actor=actor, about=wanted.about, reject=wanted.reject
        ))  # fmt: skip
        return found

    @routes.post("/agents/guide/{workspace}/{session}/compact")
    async def guide_compact(workspace: str, session: str, request: Request) -> dict[str, Any]:
        """Ask OpenCode to compact the session at its next step (design 0012 §9.6), without waiting for it."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await bridged(lambda: agents.guide.compact(workspace, session, actor=actor))
        return found

    @routes.post("/agents/guide/{workspace}/{session}/undo")
    async def guide_undo(workspace: str, session: str, wanted: UndoRequest, request: Request) -> dict[str, Any]:
        """Undo the last step, or the turn (design 0012 §9.5): OpenCode's revert at the message and part the owner
        confirmed, refused when the session moved on since; the words of the owner's messages it took back."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await bridged(lambda: agents.guide.undo(
            workspace, session, actor=actor, message=wanted.message, part=wanted.part, steps=wanted.steps,
            said=wanted.said
        ))  # fmt: skip
        return found

    @routes.post("/agents/guide/{workspace}/{session}/redo")
    async def guide_redo(workspace: str, session: str, request: Request) -> dict[str, Any]:
        """Bring back what the pending undo took back (design 0012 §9.5): OpenCode's unrevert."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await bridged(lambda: agents.guide.redo(workspace, session, actor=actor))
        return found

    @routes.post("/agents/guide/{workspace}/{session}/drop")
    async def guide_drop(workspace: str, session: str, wanted: DropRequest, request: Request) -> dict[str, Any]:
        """Clear a finished call's result (design 0012 §9.7), as OpenCode's own compaction does; refused for the step
        in progress."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await bridged(lambda: agents.guide.drop(workspace, session, wanted.part, actor=actor))
        return found

    @routes.get("/agents/sessions/{workspace}/{port}/{session}/messages")
    async def messages(workspace: str, port: int, session: str, limit: int = 40) -> dict[str, Any]:
        """A session's last messages, briefly."""
        shown = max(1, min(limit, 200))
        found: dict[str, Any] = await bridged(agents.sessions.messages, workspace, port, session, shown)
        return found

    @routes.get("/agents/sessions/{workspace}/{port}/{session}/part/{message}/{part}")
    async def part(workspace: str, port: int, session: str, message: str, part: str) -> dict[str, Any]:
        """One tool call of a session whole (design 0012 §7): its ids, state and title, its input and its output (a
        running call's so far), each with its length, cut only past the bridge's cap (an input to its start, an output
        to its end), as the bridge reads it in the workspace's container."""
        found: dict[str, Any] = await bridged(agents.sessions.part, workspace, port, session, message, part)
        return found

    @routes.post("/agents/sessions/{workspace}/{port}/{session}/message")
    async def message(workspace: str, port: int, session: str, wanted: MessageRequest, request: Request) -> Any:
        """Send a message to a session; the agent answers in its own time."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        await bridged(lambda: agents.sessions.send(workspace, port, session, wanted.text, actor=actor))
        return {"sent": True}

    @routes.post("/agents/sessions/{workspace}/start")
    async def start(workspace: str, wanted: StartRequest, request: Request) -> Any:
        """A new session in the workspace (OpenCode without a terminal is started when none runs), with its first
        message; its port and id."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        env = await bridged(agents.configure, workspace)  # the configuration a new OpenCode reads, written first
        return await bridged(
            lambda: agents.sessions.start(workspace, wanted.text, env=env, actor=actor, title=wanted.title)
        )

    @routes.post("/agents/sessions/{workspace}/{port}/{session}/stop")
    async def stop(workspace: str, port: int, session: str, request: Request) -> Any:
        """Stop what the session does now."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        await bridged(lambda: agents.sessions.stop(workspace, port, session, actor=actor))
        return {"stopped": True}

    @routes.post("/agents/permissions/{workspace}/{port}/{permission}")
    async def permission(workspace: str, port: int, permission: str, wanted: ReplyRequest, request: Request) -> Any:
        """Reply to a permission the agent asked for."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        await bridged(lambda: agents.review.reply(workspace, port, permission, wanted.reply, actor=actor))
        return {"replied": True}

    @routes.post("/agents/questions/{workspace}/{port}/{question}")
    async def question(workspace: str, port: int, question: str, wanted: AnswerRequest, request: Request) -> Any:
        """Answer a question the agent asked."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        await bridged(lambda: agents.sessions.question(workspace, port, question, wanted.answers, actor=actor))
        return {"replied": True}

    @routes.get("/agents/review")
    async def review(folder: str = "", workspace: str = "") -> dict[str, Any]:
        """A workspace's mode for the agent's changes (review or auto), whether its agents are watched now (else
        why not) and how many changes wait, and what its window was told of its model's last change (`model_changed`,
        design 0013 §7); by its name, or by a folder (`workspace` null when it has none)."""
        try:
            if workspace:
                found: dict[str, Any] = await anyio.to_thread.run_sync(agents.review.view, workspace)
            else:
                found = await anyio.to_thread.run_sync(agents.review.view_of_folder, folder)
        except SettingsError as error:
            raise ApiError(409, "refused", f"there is no workspace {workspace!r}") from error
        named = str(found.get("workspace") or "")
        return {**found, "model_changed": agents.model_notice(named) if named else None}

    @routes.post("/agents/review")
    async def switch_review(wanted: ReviewRequest, request: Request) -> dict[str, Any]:
        """Review each change the workspace's agent asks for, or let it change files without asking (auto)."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(
                lambda: agents.review.switch(wanted.workspace, wanted.mode, actor=actor)
            )
        except ReviewError as error:
            raise ApiError(409, "refused", str(error)) from error
        except SettingsError as error:
            raise ApiError(409, "refused", f"there is no workspace {wanted.workspace!r}") from error
        return found

    @routes.post("/agents/mode")
    async def switch_mode(wanted: ModeRequest, request: Request) -> dict[str, Any]:
        """Plan, review or auto: OpenCode's window switched to the planner, or to build with the change rule set; the
        view of `GET /agents/review`, with a note when the window could not be switched."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(
                lambda: agents.modes.switch(wanted.workspace, wanted.mode, actor=actor)
            )
        except (ModeError, ReviewError, SessionError) as error:
            raise ApiError(409, "refused", str(error)) from error
        except SettingsError as error:
            raise ApiError(409, "refused", f"there is no workspace {wanted.workspace!r}") from error
        return found

    @routes.post("/agents/implement")
    async def implement(wanted: ImplementRequest, request: Request) -> dict[str, Any]:
        """Hand a plan to the agent: a new session in OpenCode's window carries it out, in review or auto mode."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(
                lambda: agents.modes.implement(wanted.workspace, wanted.plan, wanted.mode, actor=actor)
            )
        except (ModeError, ReviewError, SessionError, WorkspaceUnavailable) as error:
            raise ApiError(409, "refused", str(error)) from error
        except SettingsError as error:
            raise ApiError(409, "refused", f"there is no workspace {wanted.workspace!r}") from error
        return found

    @routes.get("/agents/plans")
    async def plans(workspace: str) -> dict[str, Any]:
        """The plans in a workspace's folder, newest first: each one's path, title, status, and steps done of all."""
        try:
            found = await anyio.to_thread.run_sync(agents.modes.plans, workspace)
        except (SettingsError, WorkspaceUnavailable) as error:
            raise ApiError(409, "refused", f"there is no workspace {workspace!r}") from error
        return {"plans": found}

    @routes.post("/agents/annotations")
    async def annotate(wanted: AnnotationRequest, request: Request) -> dict[str, Any]:
        """Send a marked-up figure to the workspace's agent (design 0008): each mark in words, the marked-up copy as an
        image when the agent's model reads images; kept in the folder's `.clank/annotations/`."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(
                lambda: agents.annotations.send(
                    wanted.folder, wanted.figure, wanted.marks, wanted.message, wanted.image, actor=actor
                )
            )
        except (AnnotationError, SessionError, AgentError, WorkspaceUnavailable) as error:
            raise ApiError(409, "refused", str(error)) from error
        except OSError as error:
            raise ApiError(409, "refused", f"the figure could not be read: {error}") from error
        return found

    @routes.post("/agents/latex/pages")
    async def pages(wanted: PagesRequest) -> dict[str, Any]:
        """A PDF of a folder as page images for the annotator (design 0020 §10): built first when its `.tex` is beside
        it, rendered in the container with each page's words; the pages, by number."""
        from pathlib import Path

        try:
            workspace, root = agents.annotations.workspace_of(wanted.folder)
            found: dict[str, Any] = await anyio.to_thread.run_sync(
                lambda: agents.pages.render(workspace, Path(root), wanted.pdf)
            )
        except (AnnotationError, PageError, WorkspaceUnavailable) as error:
            raise ApiError(409, "refused", str(error)) from error
        return found

    @routes.post("/agents/latex/comments")
    async def latex_comments(wanted: CommentsRequest, request: Request) -> dict[str, Any]:
        """Send the owner's comments on LaTeX files to the workspace's agent, numbered (design 0020 §11)."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(
                lambda: agents.comments.send(wanted.folder, wanted.comments, wanted.message, actor=actor)
            )
        except (CommentError, AnnotationError, SessionError, WorkspaceUnavailable) as error:
            raise ApiError(409, "refused", str(error)) from error
        return found

    @routes.post("/agents/show")
    async def show(wanted: ShowRequest, request: Request) -> dict[str, Any]:
        """Open files of a workspace's folder in the owner's VS Code window, on the left (design 0018 §7): the agent's,
        through the gateway; what was opened, what was not a file of the folder, and the words for the model."""
        windows = "vscode" in request.app.state.streams.values()
        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(
                lambda: agents.showing.show(wanted.workspace, wanted.paths, wanted.why, windows=windows)
            )
        except ShowError as error:
            raise ApiError(409, "refused", str(error)) from error
        return found

    @routes.get("/agents/changes")
    async def changes(workspace: str | None = None, limit: int = 50) -> dict[str, Any]:
        """The newest changes the agents asked for (of one workspace, when named), without the files' contents."""
        found = await anyio.to_thread.run_sync(lambda: agents.review.store.recent(workspace, min(limit, 200)))
        return {"changes": found}

    @routes.get("/agents/changes/{change}")
    async def change(change: str) -> dict[str, Any]:
        """A change: the file before, as the agent would leave it, and as written; its diff, its answer, who gave
        it."""
        found = await anyio.to_thread.run_sync(agents.review.store.get, change)
        if found is None:
            raise ApiError(404, "not_found", f"there is no change {change!r}")
        return found

    @routes.get("/runtime/guide")
    async def add_model_guide(preset: str = "", folder: str = "") -> dict[str, Any]:
        """Add a model's steps, in order, each with its title and words (design 0016 §14), from the service's state:
        whether a model is usable and why, this computer, the MCP servers the agreement marks local (the folder's
        too), the main slot, Docker and the limits; `preset`, once written, its test (a load, or a short request
        beside the local model that runs) and Ready. Served by the agents' part, which reads all of them; the runtime
        writes the words (`GET /runtime/guide/local`, the Local step, is the runtime's)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: agents.add_model_guide(preset, folder))
        return found

    @routes.get("/agents/servers")
    async def servers(workspace: str, live: bool = False) -> dict[str, Any]:
        """The MCP servers of a workspace's agent: yours and its folder's, each with whether the agent gets it and why
        not (design 0004 §10); with `live`, each one's state in the agents running there and its last check's tools."""
        try:
            found = await anyio.to_thread.run_sync(agents.live if live else agents.servers, workspace)
        except AgentError as error:
            raise ApiError(409, "refused", str(error)) from error
        return {"servers": found}

    @routes.post("/agents/servers")
    async def give(wanted: GiveRequest, request: Request) -> dict[str, Any]:
        """Give an MCP server to a workspace's agent, or take it away (a folder's own is allowed as its entry is now);
        the agents running in the workspace's container start or stop it at once (`applied`)."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(
                lambda: agents.switch(wanted.workspace, wanted.name, wanted.given, actor=actor)
            )
        except AgentError as error:
            raise ApiError(409, "refused", str(error)) from error
        return found

    return routes
