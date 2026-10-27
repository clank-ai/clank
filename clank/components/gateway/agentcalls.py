"""An agent's calls through the gateway act for its own workspace, and for no other (design 0016 §9's keys; design 0010
§3, design 0013 §9, design 0018 §7).

A workspace's container reaches the gateway, and through it the service's routes an agent may use: `/notion/`, its
flow's `/flows/` and the agents' part's `/agents/` (`server.py` forwards what each allows, as the client `agent`). Each
of those names the workspace it acts for, in its JSON body or its query. Every container reaches the gateway through
the one edge, and the agent's shell can call these routes as Clank's MCP server does, so a name alone would let one
workspace's agent start a job in another's container, read its flow, or open its files.

So each call must carry its workspace's key, the bearer token Clank's MCP server sends (`CLANK_GATEWAY_KEY`), which the
routes the gateway follows map to the workspace (`Routes.workspace`, by the key's SHA-256): without a key they know, it
is refused (401), in words that say to start the agent's window again, which gives Clank's tools in it their
workspace's key. A `workspace` it names, in its JSON body or its query, must be that one (403 otherwise); left out, or
empty, it is filled in, so what is forwarded always names the key's workspace. What else a call names of a workspace (a
job's number, a board, a flow, a comment of a Notion batch, the files it shows or makes an artifact of) the service
looks up inside the workspace named, so binding the workspace binds them too. A body that is not a JSON object is
refused (400): no route an agent may use takes another.
"""

import json
from typing import Any, NamedTuple

from fastapi import Request
from fastapi.responses import JSONResponse

from clank.components.gateway.routing import Routes

WORKSPACE = "workspace"  # the field, and the query parameter, a call names its workspace by
NO_KEY = (
    "this request carries no workspace key the gateway knows, so it cannot say which workspace's agent sent it (an "
    "agent's window started before its workspace had a key sends none): close the agent's window and start it again "
    "from Clank, so its tools get their workspace's key"
)
OTHER_WORKSPACE = (
    "this agent works for {workspace}, and this request names {named}: an agent acts for its own workspace only"
)
NOT_JSON = "the request is not JSON"
NOT_AN_OBJECT = "the request is not a JSON object"


class Call(NamedTuple):
    """An agent's call, bound to its workspace: the workspace's name and bound (as the routes give it), and the body
    and query to forward, each naming it."""

    workspace: str
    bound: dict[str, Any]
    body: Any
    params: dict[str, str]


def key_of(authorization: str | None) -> str:
    """The key a request names its workspace by: its bearer token (OpenCode's `apiKey`, Clank's MCP server's
    `CLANK_GATEWAY_KEY`; design 0016 §9)."""
    given = str(authorization or "")
    return given[len("Bearer ") :].strip() if given.lower().startswith("bearer ") else ""


async def agent_call(request: Request, routes: Routes) -> Call | JSONResponse:
    """The call bound to the workspace its key names: the body to forward (a POST's, with its `workspace`) and the query
    (a GET's, with its `workspace`); or its refusal: 401 without a key the routes know, 400 for a body that is not a
    JSON object, 403 when it names another workspace."""
    bound = routes.workspace(key_of(request.headers.get("authorization")))
    workspace = str((bound or {}).get(WORKSPACE) or "")
    if bound is None or not workspace:
        return _refused(401, "unauthorized", NO_KEY)
    named: list[Any] = [each for each in request.query_params.getlist(WORKSPACE) if each]
    params = dict(request.query_params)
    body: Any = None
    if request.method == "GET":  # a GET's query is forwarded, never its body
        params[WORKSPACE] = workspace
    else:
        raw = await request.body()
        try:
            given = json.loads(raw) if raw else {}
        except ValueError:
            return _refused(400, "invalid_request", NOT_JSON)
        if not isinstance(given, dict):
            return _refused(400, "invalid_request", NOT_AN_OBJECT)
        if given.get(WORKSPACE) not in (None, ""):
            named.append(given[WORKSPACE])
        body = {**given, WORKSPACE: workspace}
    other = next((each for each in named if each != workspace), None)
    if other is not None:
        said = OTHER_WORKSPACE.format(workspace=workspace, named=str(other)[:80])
        return _refused(403, "wrong_workspace", said)
    return Call(workspace, bound, body, params)


def _refused(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)
