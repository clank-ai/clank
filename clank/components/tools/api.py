"""The tools component's routes: the MCP servers, added, listed, shown, removed and checked (the M8.0 plan).

They are included under `/api/v1/` behind the local token like every route (design 0002 §2.7). A client names the folder
it works in (`folder`), whose `.mcp.json` holds the project's servers; a check returns the operation it starts.
"""

from typing import TYPE_CHECKING, Any, Literal

import anyio.to_thread
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from clank.kernel.access import CLIENT_HEADER, REQUEST_KEY_HEADER, client_actor

if TYPE_CHECKING:
    from clank.components.tools.service import Tools

Scope = Literal["user", "project"]


class NewServer(BaseModel):
    """A server to add: its name, its place, and its entry as `.mcp.json` holds one."""

    name: str = Field(description="Its name: letters, digits, '-' and '_'.")
    scope: Scope = Field("user", description="user: yours, everywhere; project: the folder's .mcp.json.")
    folder: str = Field("", description="The folder the client works in (where a project's .mcp.json is).")
    entry: dict[str, Any] = Field(description="Its entry: command, args, env (stdio) or type, url, headers.")
    local_only: bool | None = Field(
        None,
        description="Yours only: what it gives the agent never goes to a cloud model; not given: it does while a cloud "
        "provider is agreed.",
    )


class LocalMark(BaseModel):
    """Whether one of your servers is local only (design 0016 §10)."""

    local_only: bool


class CheckAsked(BaseModel):
    """Which server to check, and for how long to wait for it."""

    folder: str = Field("", description="The folder the client works in.")
    scope: Literal["user", "project", "clank"] | None = Field(
        None, description="Where the server is, when its name is in both places; clank: Clank's own, in a workspace."
    )
    seconds: float = Field(30.0, gt=0, le=600, description="How long it may take to answer.")
    workspace: str = Field("", description="Start it in this workspace's container, as its agent would.")


def router(tools: "Tools") -> APIRouter:
    """The routes, over the tools component's part."""
    routes = APIRouter()

    @routes.get("/mcp/servers")
    async def servers(folder: str = "") -> dict[str, Any]:
        """Every MCP server: yours, then the folder's project's."""
        found = await anyio.to_thread.run_sync(tools.servers, folder)
        return {"servers": found}

    @routes.get("/mcp/servers/{name}")
    async def server(name: str, folder: str = "", scope: Scope | None = None) -> dict[str, Any]:
        """One MCP server; the values of its secrets never, their names, when they were set and their last four
        characters."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(tools.server, name, folder, scope)
        return found

    @routes.post("/mcp/servers")
    async def add(new: NewServer, request: Request) -> dict[str, Any]:
        """Add an MCP server."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        return tools.add(
            new.name, new.entry, scope=new.scope, folder=new.folder, actor=actor, local_only=new.local_only
        )

    @routes.put("/mcp/servers/{name}/local")
    async def mark(name: str, wanted: LocalMark, request: Request) -> dict[str, Any]:
        """Mark one of your servers local only, or not: what it gives the agent never goes to a cloud model."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        return tools.set_local(name, wanted.local_only, actor=actor)

    @routes.delete("/mcp/servers/{name}")
    async def remove(name: str, request: Request, folder: str = "", scope: Scope | None = None) -> dict[str, Any]:
        """Remove an MCP server, with its secrets."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        return tools.remove(name, scope=scope, folder=folder, actor=actor)

    @routes.post("/mcp/servers/{name}/check")
    async def check(name: str, asked: CheckAsked, request: Request) -> dict[str, Any]:
        """Check an MCP server: an operation that starts or reaches it, asks for its tools, and ends it."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        params = {
            "name": name, "folder": asked.folder, "scope": asked.scope, "seconds": asked.seconds,
            "workspace": asked.workspace,
        }  # fmt: skip
        key = request.headers.get(REQUEST_KEY_HEADER)
        started = await tools.kernel.operations.start("mcp.check", params, actor=actor, request_key=key)
        return started.model_dump(mode="json")

    return routes
