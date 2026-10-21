"""The notion component's routes (design 0010), under `/api/v1/` behind the local token like every route: the
connection's status, connecting with the integration's secret, and disconnecting (a secret is taken once, in a body,
and never answered back); the agent's reading (§4): the shared databases, a database's entries, an entry with its page
as Markdown, a search; its proposals (§5): a new entry, a change, a removal, submitting the batch, and the batches,
each with its databases as tables for the review (§6); the owner's comments on a batch and sending it back to its
agent, and the agent's answers to them (§7); and the owner's approval (whole, or in parts) or rejection of a batch (§8).
Commenting, sending back, approving and rejecting are the owner's: `403 forbidden` for the agent.
A request whose client is `agent` (the gateway's, for the agent) is recorded as the agent's session, any other as the
user's through that client. What cannot be done is `409 refused`, with why."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

import anyio.to_thread
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from clank.components.notion.service import AGENT, NotAllowed, NotionRefused
from clank.kernel.access import CLIENT_HEADER, client_actor
from clank.kernel.api import ApiError
from clank.kernel.events import Actor

if TYPE_CHECKING:
    from clank.components.notion.service import Notion


class Query(BaseModel):
    """Which entries of a shared database."""

    database: str = Field(description="The database: its name, or its id (or its data source's).")
    text: str = Field("", description="Entries whose title holds these words.")
    filter: dict[str, Any] | None = Field(None, description="Notion's own filter of a data source's query.")
    limit: int = Field(25, ge=1, le=100, description="How many entries, 1 to 100.")
    cursor: str | None = Field(None, description="Where the last answer stopped (its cursor).")


class Proposed(BaseModel):
    """What every proposal says: the workspace it comes from, why, and the sources of what it states."""

    workspace: str = Field(description="The workspace whose agent proposes it.")
    why: str = Field("", description="Why: the owner reads it in the review.")
    sources: list[str] = Field(
        default_factory=list, description="The files, sections or scripts its content comes from."
    )


class NewEntry(Proposed):
    """A new entry of a shared database."""

    database: str = Field(description="The database: its name, or its id.")
    properties: dict[str, Any] = Field(description="Its properties' values, by name.")
    markdown: str = Field("", description="Its page, in Markdown.")


class Change(Proposed):
    """A change to a shared entry."""

    page: str = Field(description="The entry: its id, or its notion: link.")
    properties: dict[str, Any] = Field(default_factory=dict, description="The properties it changes, by name.")
    markdown: str = Field("", description="Its page as it should be after the change, in Markdown.")


class Removal(Proposed):
    """A shared entry to Notion's trash."""

    page: str = Field(description="The entry: its id, or its notion: link.")


class Submit(BaseModel):
    """The workspace's open batch, made ready for review."""

    workspace: str = Field(description="The workspace.")
    summary: str = Field("", description="What the batch does, in a sentence or two.")


class Approve(BaseModel):
    """Which proposals of a batch to write."""

    proposals: list[str] | None = Field(None, description="Their ids (p1, p2, ...); none given: every one not written.")
    parts: dict[str, list[str]] | None = Field(
        None,
        description="Instead, some parts of some proposals, by proposal: its properties' names, page (its page), or "
        "removal; an empty list is all its parts not written yet.",
    )


class Reject(BaseModel):
    """Why a batch is rejected."""

    reason: str = Field("", description="Why, for the agent.")


class Comment(BaseModel):
    """The owner's comment, and what it is on."""

    text: str = Field(description="What the agent should do.")
    proposal: str | None = Field(None, description="The proposal it is on (p1, p2, ...); none: the whole batch.")
    field: str | None = Field(None, description="A property of the proposal's entry it is on.")
    block: int | None = Field(None, ge=0, description="The block of the proposal's page it is on, from 0.")


class Reply(BaseModel):
    """The agent's answer to a comment."""

    workspace: str = Field(description="The workspace whose agent answers.")
    comment: str = Field(description="The comment's id (c1, c2, ...).")
    text: str = Field(description="What it did, or why not.")


class Connect(BaseModel):
    """The integration's secret."""

    secret: str = Field(description="The Notion integration's Internal Integration Secret.")


def router(notion: "Notion") -> APIRouter:
    """The routes, over the notion component's part."""
    routes = APIRouter()

    @routes.get("/notion/status")
    async def status() -> dict[str, Any]:
        """Whether Clank is connected to Notion, as which integration and in which workspace, and any problem."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(notion.status)
        return found

    @routes.post("/notion/connect")
    async def connect(given: Connect, request: Request) -> dict[str, Any]:
        """Keep the integration's secret once Notion accepts it."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        try:
            found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: notion.connect(given.secret, actor=actor))
        except NotionRefused as error:
            raise ApiError(409, "refused", str(error)) from error
        return found

    @routes.delete("/notion/connect")
    async def disconnect(request: Request) -> dict[str, Any]:
        """Remove the secret."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: notion.disconnect(actor=actor))
        return found

    @routes.get("/notion/databases")
    async def databases(request: Request) -> dict[str, Any]:
        """The shared databases, with their properties described."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        return {"databases": await _refused(lambda: notion.databases(actor=actor))}

    @routes.post("/notion/query")
    async def query(asked: Query, request: Request) -> dict[str, Any]:
        """A shared database's entries as compact rows, and the cursor of the next ones."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await _refused(lambda: notion.query(
            asked.database, text=asked.text, filter=asked.filter, limit=asked.limit, cursor=asked.cursor, actor=actor
        ))  # fmt: skip
        return found

    @routes.get("/notion/page/{page}")
    async def page(page: str, request: Request) -> dict[str, Any]:
        """An entry: its properties, and its page as Markdown."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await _refused(lambda: notion.page(page, actor=actor))
        return found

    @routes.get("/notion/search")
    async def search(text: str, request: Request) -> dict[str, Any]:
        """Entries and databases whose title holds the words."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        return {"results": await _refused(lambda: notion.search(text, actor=actor))}

    @routes.post("/notion/propose/entry")
    async def propose_entry(asked: NewEntry, request: Request) -> dict[str, Any]:
        """Stage a new entry in the workspace's open batch."""
        actor = _actor(request)
        found: dict[str, Any] = await _refused(lambda: notion.propose_entry(
            asked.workspace, asked.database, asked.properties, markdown=asked.markdown, why=asked.why,
            sources=asked.sources, actor=actor,
        ))  # fmt: skip
        return found

    @routes.post("/notion/propose/change")
    async def propose_change(asked: Change, request: Request) -> dict[str, Any]:
        """Stage a change to a shared entry in the workspace's open batch."""
        actor = _actor(request)
        found: dict[str, Any] = await _refused(lambda: notion.propose_change(
            asked.workspace, asked.page, properties=asked.properties, markdown=asked.markdown, why=asked.why,
            sources=asked.sources, actor=actor,
        ))  # fmt: skip
        return found

    @routes.post("/notion/propose/removal")
    async def propose_removal(asked: Removal, request: Request) -> dict[str, Any]:
        """Stage a shared entry's removal in the workspace's open batch."""
        actor = _actor(request)
        found: dict[str, Any] = await _refused(
            lambda: notion.propose_removal(asked.workspace, asked.page, why=asked.why, actor=actor)
        )
        return found

    @routes.post("/notion/submit")
    async def submit(asked: Submit, request: Request) -> dict[str, Any]:
        """Make the workspace's open batch ready for review."""
        actor = _actor(request)
        found: dict[str, Any] = await _refused(lambda: notion.submit(asked.workspace, asked.summary, actor=actor))
        return found

    @routes.get("/notion/batches")
    async def batches(workspace: str | None = None) -> dict[str, Any]:
        """The batches (of a workspace), newest first, in brief."""
        return {"batches": await _refused(lambda: notion.batches(workspace=workspace))}

    @routes.get("/notion/batches/{id}")
    async def batch(id: str) -> dict[str, Any]:
        """A batch, whole: its proposals with what the review shows."""
        found: dict[str, Any] = await _refused(lambda: notion.batch(id))
        return found

    @routes.post("/notion/batches/{id}/approve")
    async def approve(id: str, asked: Approve, request: Request) -> dict[str, Any]:
        """Write a batch's proposals (or those named) to Notion: the owner's, never the agent's."""
        actor = _actor(request)
        found: dict[str, Any] = await _refused(
            lambda: notion.approve(id, proposals=asked.proposals, parts=asked.parts, actor=actor)
        )
        return found

    @routes.get("/notion/batches/{id}/tables")
    async def tables(id: str, everything: bool = False) -> dict[str, Any]:
        """Each database a batch touches as a table of its entries now, marked with the batch's proposals: the
        changed ones and their neighbors, or every one (`everything`)."""
        return {"tables": await _refused(lambda: notion.tables(id, everything=everything))}

    @routes.post("/notion/batches/{id}/comments")
    async def comment(id: str, asked: Comment, request: Request) -> dict[str, Any]:
        """The owner's comment on a batch, a proposal, a property or a block; the comment."""
        actor = _actor(request)
        found: dict[str, Any] = await _refused(lambda: notion.comment(
            id, asked.text, proposal=asked.proposal, field=asked.field, block=asked.block, actor=actor
        ))  # fmt: skip
        return found

    @routes.delete("/notion/batches/{id}/comments/{comment}")
    async def uncomment(id: str, comment: str, request: Request) -> dict[str, Any]:
        """Take back a comment not sent to the agent yet."""
        actor = _actor(request)
        found: dict[str, Any] = await _refused(lambda: notion.uncomment(id, comment, actor=actor))
        return found

    @routes.post("/notion/batches/{id}/return")
    async def send_back(id: str, request: Request) -> dict[str, Any]:
        """Send a batch back to its agent with the comments not sent yet."""
        actor = _actor(request)
        found: dict[str, Any] = await _refused(lambda: notion.send_back(id, actor=actor))
        return found

    @routes.post("/notion/reply")
    async def reply(asked: Reply, request: Request) -> dict[str, Any]:
        """The agent's answer to a comment; the comment."""
        actor = _actor(request)
        found: dict[str, Any] = await _refused(
            lambda: notion.reply(asked.workspace, asked.comment, asked.text, actor=actor)
        )
        return found

    @routes.post("/notion/batches/{id}/reject")
    async def reject(id: str, asked: Reject, request: Request) -> dict[str, Any]:
        """Reject a batch with a reason: the owner's, never the agent's."""
        actor = _actor(request)
        found: dict[str, Any] = await _refused(lambda: notion.reject(id, asked.reason, actor=actor))
        return found

    return routes


def _actor(request: Request) -> Actor:
    """The agent's session for the gateway's requests on the agent's behalf, else the user through their client."""
    client = request.headers.get(CLIENT_HEADER)
    return AGENT if (client or "").lower() == "agent" else client_actor(client)


async def _refused[T](work: Callable[[], T]) -> T:
    """Work off the event loop, what cannot be done answered `409 refused`."""
    try:
        return await anyio.to_thread.run_sync(work)
    except NotAllowed as error:
        raise ApiError(403, "forbidden", str(error)) from error
    except NotionRefused as error:
        raise ApiError(409, "refused", str(error)) from error
