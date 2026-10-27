"""The gateway process (design 0001 §6, design 0004 §2): every model request of every tool, to the engine of its role's
slot.

It serves OpenAI's Chat Completions (`POST /v1/chat/completions`, streamed or not), `GET /v1/models` (the roles), `GET
/activity` (each request in flight and the last that ended, of one session if it is named, and its subagents if they
are asked for: `activity.py`) and `GET
/health`, on 127.0.0.1 only (containers reach it through their edge), and on Linux on its socket too, which only the
edge reaches, on Docker Engine (`sockets.py`, design 0014 §3). A request names a role as its model (decision
0008); the gateway waits while the role's slot starts or switches (`Routes.ready`), puts the request in the engine's own
fields (`EngineAdapter.translate`), names the model as the runtime's settings say (`model_name`), and forwards it. A
streamed answer is passed on as it comes, whole lines at a time, each token counted; when the client leaves, the gateway
closes its connection to the engine, which stops generating for it. OpenCode's session-title requests are answered here
(`titles.py`). Every request is recorded (`records.py`) when it ends, with its timings: the wait for the slot, the time
to the first token, the whole time (and the engine's own, llama.cpp's `timings`, when it gives them). An engine that
breaks off a request before answering anything (it crashed: the runtime starts it again) has the request sent again once
the role's slot is served again (`Routes.recovered`, within the hold), on the same stream to the client, which sees only
a longer wait; one that breaks off after answering part, or whose slot is not served again, ends the stream with an
error event that says so (`engine_broke_off`), and the record says what happened (`again`, `broken`). A stream that
stops without its end (no choice with a finish reason, no `[DONE]`, no error event) has broken off too: on Linux, and
over a network, a crashed engine's connection can close cleanly, and only the missing end shows it. A streamed answer is
read by the loop guard as it passes (`loops.py`, design 0004 §2): when its thinking, its text or a tool call repeats
itself, the gateway closes its connection to the engine and ends the stream with an error event that says what repeated
(`model_looped`), and the record keeps it (`looped`, `error`). Completion's fill in the middle (`POST /v1/infill`, `GET
/completion`) is `completion.py`'s: the newest wins, and it is counted, not recorded.

An engine's refusal (any answer but 200) is read whole and passed on as it came, its error recorded; but its refusal of
a request its context cannot hold (its adapter knows its words: `context_full`; KVMem's "prompt + max_tokens exceeds
n_ctx", which OpenCode 1.19 takes for an ordinary error and stops on) is answered as OpenCode reads a context overflow,
on which it compacts the session and goes on (design 0012 §4.1, decision 0090): 400 in OpenAI's shape, its code
`context_length_exceeded`, its message "the context was full: <the engine's words> (the request exceeds the available
context size; ...)", and the record keeps the engine's words (`full`).

A paused session's requests are held at the gateway's door (design 0012 §9.4, decision 0055, `holds.py`): once read, and
its title answered, before its slot is woken or waited for. A streamed one is answered at once (200, an event stream)
and kept alive with comment lines until the session is resumed; then it goes on as any request does, on the same stream,
and is timed from then on, its hold kept apart in its record (`held`). Its wait for the slot then sends the same comment
lines, and since its 200 has gone out, a refusal or the engine's own error is told inside the stream, worded on purpose
(`worded`): retried by OpenCode when the same failure without the hold would have been (a 5xx or 429 status), else not.
A note's release ends it as an empty step the gateway answers itself (`local`: "released"), when it was held before the
note was sent (one held since may carry it), and it stays among its session's requests that ended, so its step's flow
shows the hold. One not streamed waits without headers. The pauses are the owner's: `GET /holds`, `PUT` and `DELETE
/holds/{session}` and `POST /holds/{session}/release` take the service's local token, which the agent, reaching the
gateway through its edge, never has (decision 0084).

A cloud provider's key (design 0016 §5, decision 0106) is handed to the gateway by the service with the same token
(`PUT /keys/{endpoint}`, `DELETE`, and `GET /keys`, which never answers a value), held in memory only (`keys.py`), and
replaced by `…` and its last four wherever it appears in a record or the live view; a slot a cloud model serves takes
requests once its key is held for its launch.

The agent's way to Notion (design 0010 §3) is here too, since the gateway is all a workspace's container reaches:
`/notion/...` forwards the reading and proposing routes (`NOTION`: the shared databases, a query, a page, a search; a
new entry, a change, a removal, submitting the batch; an answer to the owner's comment) to the service as the client
`agent`, and refuses every other (commenting, sending back, approving and rejecting are the owner's, never the
agent's). So is a box's way to its flow (design 0013 §9): `/flows/...` forwards what the agent may ask of a flow
(`FLOWS`: reading it, proposing a box, submitting its proposals, a VERIFY's verdict, a planning's draft of a whole
flow, design 0013 §15, and an orchestrator's decision, §16) the same way, and refuses everything else under
`/flows/`: running, pausing, stopping and changing a flow, deciding proposals, and opening a planning, are the
owner's. The agent opens files for the owner to see in Clank's VS Code window (design 0018 §7), and starts, follows
and stops its jobs (design 0021 §6) and makes its artifacts (§5), the same way: `POST /agents/show`, `/agents/jobs`,
`/agents/jobs/status`, `/agents/jobs/stop` and `/agents/artifacts` are forwarded, and everything else under `/agents/`
refused. Each of these calls acts for the workspace whose key it carries, and for no other (`agentcalls.py`): without
a key the routes know it is refused (401), and a workspace it names must be its key's (403).

The gateway answers Clank's own programs only (`callers.py`): a request addressed to another host name than its own
(`127.0.0.1`, `localhost` or `[::1]` with its port, and `edge` with its port for the containers) is refused (421), and
so is one a browser made (403).

Run as its own process (`python -m clank.components.gateway.server`), supervised by the service (`service.py`), so a
restart of the service or of the console cuts no request in flight. It reads its settings from `config/gateway.json`
and follows the service's routes, asking every second; while the service does not answer it keeps the last routes. On
Linux the service names its socket folder (`--socket-folder`): the process then makes its listeners itself, the TCP
socket and the Unix sockets, its own and the proxy's, before anything else runs, hands them to Uvicorn and the proxy,
and removes the sockets when it stops (`sockets.py`); a port another program holds ends it as Uvicorn would, logged,
with exit status 3.
"""

import argparse
import asyncio
import contextlib
import json
import logging
import math
import os
import re
import secrets
import socket
import sys
import threading
import time
import weakref
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple
from urllib.parse import quote

import anyio
import anyio.to_thread
import httpx2
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from uvicorn.config import STARTUP_FAILURE

from clank.components.gateway import completion
from clank.components.gateway.activity import Activity
from clank.components.gateway.agentcalls import agent_call, key_of
from clank.components.gateway.callers import OnlyClanksCallers
from clank.components.gateway.census import census
from clank.components.gateway.holds import Held, Holds, Released
from clank.components.gateway.keys import Keys
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.loops import LoopGuard
from clank.components.gateway.marks import LocalMarks, held_back, local_calls, whose
from clank.components.gateway.proxy import HOLD_SECONDS, NetworkLog, Proxy, network_token
from clank.components.gateway.records import TrafficLog
from clank.components.gateway.routing import NO_KEY, Routes, SlotRoute
from clank.components.gateway.sessions import session_of
from clank.components.gateway.sockets import Listeners, remove_sockets
from clank.components.gateway.spool import Spool
from clank.components.gateway.titles import local_title
from clank.components.runtime.service import (
    PLAIN_TOKENS_PER_CHARACTER,
    Refusal,
    context_full,
    endpoint_cost,
    endpoint_full,
    endpoint_headers,
    endpoint_label,
    endpoint_refusal,
    endpoint_request,
    translate_request,
)
from clank.kernel.clock import from_text, to_text

if TYPE_CHECKING:
    from clank.client import Client

# What the agent may ask of Notion through the gateway: (method, path under /notion/); `page/<id>` too.
NOTION = {
    ("GET", "databases"), ("POST", "query"), ("GET", "search"), ("POST", "propose/entry"), ("POST", "propose/change"),
    ("POST", "propose/removal"), ("POST", "submit"), ("POST", "reply"),
}  # fmt: skip
NOT_THE_AGENTS = "the agent reads Notion and proposes changes; nothing else (the owner approves them, in VS Code)"
# What the agent may ask of its flow through the gateway: (method, path under /flows/) (design 0013 §9).
FLOWS = {("GET", "read"), ("POST", "propose"), ("POST", "submit"), ("POST", "verdict"), ("POST", "draft"),
         ("POST", "decide"), ("POST", "job")}  # fmt: skip
NOT_THE_AGENTS_FLOW = (
    "the agent reads its flow, proposes boxes, gives a VERIFY's verdict, drafts a flow, gives an orchestrator's "
    "decision and starts a box's job; nothing else (the owner runs, changes and decides flows, and opens a planning)"
)
# What the agent may ask of the agents' part through the gateway (design 0018 §7): opening files for the owner to see.
AGENTS = {("POST", "show"), ("POST", "jobs"), ("POST", "jobs/status"), ("POST", "jobs/stop"), ("POST", "artifacts"),
          ("POST", "boards"), ("GET", "boards"), ("GET", "boards/read"), ("POST", "boards/add"),
          ("POST", "boards/update"), ("POST", "boards/remove"), ("POST", "boards/export")}  # fmt: skip
NOT_THE_AGENTS_SHOW = (
    "the agent opens files for the owner to see, runs its jobs, makes its artifacts and works on boards; nothing else "
    "(the window, the review, the sessions and comments are the owner's)"
)
Forward = Callable[[str, str, Any, dict[str, str]], Awaitable[tuple[int, Any]]]

FOLLOW_SECONDS = 1.0
HOLDS_FILE = "holds.json"  # in the home's state: the paused sessions
MARKS_FILE = "local-only.json"  # in the home's state: the sessions that used local-only content (design 0016 §10)
WAKE_SECONDS = 5.0  # after asking for a role loaded on demand: how long its slot may take to show it is starting
AGAIN = "the engine broke off before answering; sent again once the slot was served again"
LOOPED = "Clank's loop guard stopped the answer"
OFF = (
    "Ask again; to let such an answer through, set loop_guard to false in config/gateway.json and run clank gateway "
    "restart."
)
Keep = Callable[[dict[str, Any]], None]  # a request's end: its record kept
Again = Callable[[], Awaitable[tuple[httpx2.Response | None, str]]]  # the request sent again once its slot is back
NOT_THE_OWNERS = (
    "pausing and resuming a session are the owner's, through the Clank service (the Guide, or a Watch for rule); "
    "this route takes the service's token"
)
NO_TOKEN = "this gateway was not given the Clank service's token, so nothing can pause or resume a session through it"
FULL = "the context was full"
NEVER_AGAIN = "a cloud request is never sent again by Clank: it may have been billed"
LOCAL_ONLY = (
    "this session used {what}, which never goes to the cloud model: start a new session to use it, or load a local "
    "model"
)
UNKNOWN_KEY = (
    "this OpenCode was started before Clank named workspaces to the gateway: leave it, and start it again here "
    "(a cloud model takes only a workspace's requests)"
)
KEPT_LOCAL = (
    "{workspace} is kept on this machine. Allow the cloud for it on This folder (u), or clank workspace allow FOLDER "
    "--cloud; or load a local model"
)
NOT_ANSWERED = (
    "no one answered whether {workspace} may use the cloud model: it stays on this machine this time, and is asked "
    "again at its next start"
)
NOT_AGREED = (
    "the agreement to {provider} was withdrawn: nothing goes to it until you agree again (Add a model); or load a "
    "local model"
)
SERVICE_SILENT = (
    "the Clank service does not answer, and a cloud request waits for what it says now: start the service again "
    "(clank serve), then ask again"
)
HELD_AT_LIMIT = b": held by Clank: the cloud spending limit is reached\n\n"
HELD_FOR_ANSWER = ": held by Clank: waiting for your answer: may {workspace} use the cloud model?\n\n"
NOTION_CLOUD = (
    "{workspace} may use the cloud model, so its agent reads no Notion page (design 0016 §10): Notion pages never go "
    "to the cloud"
)
LOCAL_ONLY_UNKNOWN = (
    "the Clank service has not yet told the gateway which tools never go to the cloud model, so nothing goes to it: "
    "sent again in a moment, the request goes"
)
CLOUD_NOW = (
    "its slot now runs the cloud model {title}: Clank sends nothing meant for this machine there by itself; sent "
    "again, the request goes to it if its workspace may use it"
)
SLOT_CHANGED = (
    "the slot no longer runs the cloud model this request was for: sent again, it goes to the model the slot runs now"
)
QUESTION_SECONDS = 31 * 60.0  # the workspace's question expires in 30 minutes (design 0016 §9)
POLL_SECONDS = 0.1
CLOUD_CONNECT_SECONDS = 10.0  # how long a provider is given to take the connection (design 0016 §8)
CLOUD_READ_SECONDS = 600.0  # the read timeout between pieces, unless the provider's record says otherwise
OVERFLOW = "the request exceeds the available context size; OpenCode compacts the session on this error"
OVERFLOW_CODE = "context_length_exceeded"  # OpenAI's code for it, which OpenCode reads as an overflow (decision 0090)
Count = Callable[[dict[str, Any], str], None]  # one token of a request's answer, of a kind (`activity.KINDS`)
FAILED_CENSUSES = [0]  # the censuses that could not be made since the gateway started
log = logging.getLogger(__name__)


class Sent(NamedTuple):
    """What came of a cloud request's way to its provider (`cloud_through`): the provider's answer (its headers read,
    its body not), or none and the status, code and words to answer with; the route it went by; when it began (after
    its holds)."""

    upstream: httpx2.Response | None
    status: int
    code: str
    words: str
    route: SlotRoute
    began: float


def create_gateway(
    routes: Routes,
    settings: GatewaySettings,
    log: TrafficLog | None,
    wake: Callable[[str], Awaitable[str]] | None = None,
    notion: Forward | None = None,
    flows: Forward | None = None,
    holds: Holds | None = None,
    token: str | None = None,
    keys: Keys | None = None,
    ask_cloud: Callable[[str, str], Awaitable[dict[str, Any]]] | None = None,
    marks: LocalMarks | None = None,
    spool: Spool | None = None,
    agents: Forward | None = None,
    proxy: Proxy | None = None,
    port: int | None = None,
    proxy_socket: socket.socket | None = None,
) -> FastAPI:
    """The gateway's application, over its routes, its settings and its records (None: none kept); `wake` asks the
    service for a role loaded on demand, and says why not when it is not loaded ("" when it is being); `notion`
    forwards the agent's Notion requests to the service (`notion_forwarder`), `flows` its requests of its flow
    (`flows_forwarder`); `holds` are the paused sessions (design 0012 §9.4), which only a caller with the service's
    local `token` pauses and resumes (none given: nothing can); `keys` are the cloud providers' keys the service hands
    it with the same token (design 0016 §5), kept out of every record and the live view; `ask_cloud` tells the service
    a workspace not yet answered wants the cloud model (design 0016 §9), which asks its question; `marks` are the
    sessions that used local-only content (design 0016 §10), kept from the cloud; `spool` keeps each cloud request
    that ended, with its cost, until the service takes it (design 0016 §12); `agents` forwards the agent's request to
    open files for the owner (`agents_forwarder`, design 0018 §7); `proxy` is the agent's way to the internet (design
    0024 §2), served on the settings' `proxy_port` with the application, and on `proxy_socket` too when one is given
    (its socket on Linux, design 0014 §3), and stopped with it. `port` is the one it listens on (its settings' when
    none is given): it answers requests addressed to its host names with that port only (`callers.py`)."""
    clients: dict[str, httpx2.AsyncClient] = {}
    activity = Activity(generation=routes.generation)
    holds = holds if holds is not None else Holds()
    keys = keys if keys is not None else Keys()
    routes.keyed = keys.has
    marks = marks if marks is not None else LocalMarks()
    held_at_limit = [0]  # the cloud requests held at a spending limit now (design 0016 §11)

    def keep(record: dict[str, Any]) -> None:
        keys.scrubbed(record)  # a key echoed anywhere in it is replaced (design 0016 §5)
        if str(record.get("provider") or "").startswith("cloud ") and "cost" not in record:
            spooled(record)
        activity.end(record)
        if log is not None:
            log.write(record)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        clients["engine"] = httpx2.AsyncClient(timeout=httpx2.Timeout(None, connect=10))
        clients["cloud"] = httpx2.AsyncClient(timeout=httpx2.Timeout(CLOUD_READ_SECONDS, connect=CLOUD_CONNECT_SECONDS))
        proxied: list[asyncio.AbstractServer] = []
        if proxy is not None:
            try:
                proxied.append(await proxy.serve("127.0.0.1", settings.proxy_port))
            except OSError as error:  # the port is taken: the gateway serves its models all the same, said in its log
                logging.getLogger(__name__).warning(
                    "the agent's proxy could not listen on port %d (%s): the agent reaches no host until the gateway "
                    "starts again with a free proxy_port", settings.proxy_port, error,
                )  # fmt: skip
            if proxy_socket is not None:  # the edge's way to it on Docker Engine (design 0014 §3)
                proxied.append(await proxy.serve_on(proxy_socket))
        try:
            yield
        finally:
            for served in proxied:
                served.close()
                await served.wait_closed()
            await clients["engine"].aclose()
            await clients["cloud"].aclose()

    app = FastAPI(title="Clank gateway", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(OnlyClanksCallers, port=port or settings.port)  # Clank's own programs only, never a web page

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models")
    async def models() -> dict[str, Any]:
        listed = [{"id": role, "object": "model", "owned_by": "clank"} for role in routes.roles()]
        return {"object": "list", "data": listed}

    @app.get("/activity")
    async def now(request: Request, session: str = "", subagents: bool = False, ended: bool = False) -> Response:
        guard = {"on": settings.loop_guard, "ratio": settings.loop_ratio}  # as it applies them: read when it started
        return the_service(request) or JSONResponse({**activity.now(session, subagents, ended), "guard": guard})

    @app.get("/activity/live")
    async def live(
        request: Request, after: int = 0, id: str = "", session: str = "", subagents: bool = False
    ) -> Response:
        return the_service(request) or JSONResponse(activity.live(max(0, after), id, session, subagents))

    def the_owners(request: Request) -> JSONResponse | None:
        """None when the caller is the service (its local token), else the refusal: the agent reaches this gateway
        through the edge, and must never pause or resume a session (decision 0084)."""
        if token is None:
            return JSONResponse({"error": {"code": "unavailable", "message": NO_TOKEN}}, status_code=503)
        given = request.headers.get("authorization", "").encode("utf-8", errors="replace")
        if not secrets.compare_digest(given, f"Bearer {token}".encode()):
            return JSONResponse({"error": {"code": "unauthorized", "message": NOT_THE_OWNERS}}, status_code=401)
        return None

    def the_service(request: Request) -> JSONResponse | None:
        """None when the caller is the service (its local token), else the refusal (design 0015 §10: what every
        request says is the owner's, never the agent's); a gateway given no token (a test's) answers anyone."""
        return None if token is None else the_owners(request)

    @app.get("/holds")
    async def pauses(request: Request) -> Response:
        """Each paused session, and the requests it holds now."""
        return the_owners(request) or JSONResponse({"pauses": holds.view()})

    @app.put("/holds/{session}")
    async def pause(session: str, request: Request) -> Response:
        """Pause a session (`{"by": who}`): its next requests, and its subagents', are held until it is resumed."""
        refused = the_owners(request)
        if refused is not None:
            return refused
        given = await request.json() if await request.body() else {}
        by = str(given.get("by") or "") if isinstance(given, dict) else ""
        return JSONResponse(holds.pause(session, by))

    @app.delete("/holds/{session}")
    async def resume(session: str, request: Request) -> Response:
        """Resume a session: what it held goes on to the engine."""
        refused = the_owners(request)
        if refused is not None:
            return refused
        ended = holds.resume(session)
        if ended is None:
            said = f"session {session} is not paused"
            return JSONResponse({"error": {"code": "not_paused", "message": said}}, status_code=404)
        return JSONResponse(ended)

    @app.post("/holds/{session}/release")
    async def release(session: str, request: Request) -> Response:
        """A note was sent to a paused session: its own requests held now end as empty steps, only those held before
        the time named (`{"before": when the note was about to be sent}`), since one held after may carry the note; the
        pause stays."""
        refused = the_owners(request)
        if refused is not None:
            return refused
        given = await request.json() if await request.body() else {}
        before = str(given.get("before") or "") if isinstance(given, dict) else ""
        try:
            if before:
                from_text(before)
        except ValueError:
            said = f"before is not a time as Clank writes it (2026-10-20T12:22:00.000Z): {before[:40]}"
            return JSONResponse({"error": {"code": "invalid_request", "message": said}}, status_code=400)
        return JSONResponse({"session": session, "released": holds.release(session, before)})

    @app.get("/spend")
    async def spend(request: Request, after: int = 0) -> Response:
        """The cloud requests that ended after the entry `after` (the last the service took), each with its cost; those
        up to it are forgotten (design 0016 §12)."""
        refused = the_owners(request)
        if refused is not None:
            return refused
        if spool is None:
            return JSONResponse({"run": "", "entries": [], "last": 0, "held": held_at_limit[0]})
        return JSONResponse({**spool.after(max(0, after)), "held": held_at_limit[0]})

    def spooled(record: dict[str, Any]) -> None:
        """A cloud request that ended: its cost (the provider's own figure, else an estimate from its tokens at the
        model's prices) kept in its record and appended to the spool."""
        usage = record.get("usage") if isinstance(record.get("usage"), dict) else None
        pieces = record.get("pieces") or {}
        if usage is not None:
            details = usage.get("prompt_tokens_details") or {}
            thinking = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens") or 0
            tokens = {"in": int(usage.get("prompt_tokens") or 0), "cached": int(details.get("cached_tokens") or 0),
                      "out": int(usage.get("completion_tokens") or 0), "thinking": int(thinking)}  # fmt: skip
        else:
            out = int(pieces.get("answer", 0)) + int(pieces.get("tool", 0))
            tokens = {"in": int(record.get("estimated_in") or 0), "cached": 0, "out": out,
                      "thinking": int(pieces.get("thinking", 0))}  # fmt: skip
        error = record.get("error")
        code = str(error.get("code") or "") if isinstance(error, dict) else ""
        status = int(record.get("status") or 0) or None
        if code or (status is not None and status != 200):
            cost = {"usd": 0.0, "how": "usage"}  # refused: nothing billed
        else:
            found = endpoint_cost(str(record.get("adapter") or ""), usage, tokens, record.get("prices") or {})
            cost = {"usd": found.usd, "how": found.how}
        record["cost"] = cost
        if spool is None:
            return
        session, parent = session_of(record.get("headers"))
        spool.add({
            "time": record.get("time"), "id": record.get("id"), "session": session, "parent": parent,
            "workspace": record.get("workspace", ""), "endpoint": record.get("endpoint", ""),
            "preset": record.get("preset") or "", "model": record.get("model_sent") or "",
            "generation": record.get("generation") or "", "tokens": tokens, **cost, "status": status, "code": code,
        })  # fmt: skip

    @app.get("/keys")
    async def held(request: Request) -> Response:
        """Each cloud provider's key held, by its provider, its last four, its launch and when it was set: never its
        value (design 0016 §5)."""
        return the_owners(request) or JSONResponse({"keys": keys.view()})

    @app.put("/keys/{endpoint}")
    async def hold_key(endpoint: str, request: Request) -> Response:
        """Hold a provider's key for a launch (`{"key", "launch", "set"}`), in memory only."""
        refused = the_owners(request)
        if refused is not None:
            return refused
        given = await request.json() if await request.body() else {}
        value = str(given.get("key") or "") if isinstance(given, dict) else ""
        if not value:
            said = {"code": "invalid_request", "message": 'a key is given as {"key": ..., "launch": ...}'}
            return JSONResponse({"error": said}, status_code=400)
        launch = given.get("launch")
        shown = keys.put(endpoint, value, int(launch) if launch is not None else None, str(given.get("set") or ""))
        return JSONResponse(shown)

    @app.delete("/keys/{endpoint}")
    async def forget_key(endpoint: str, request: Request) -> Response:
        """Forget a provider's key."""
        refused = the_owners(request)
        if refused is not None:
            return refused
        keys.forget(endpoint)
        return JSONResponse({"forgotten": endpoint})

    completion.add_routes(app, routes, lambda: clients["engine"], the_service)

    @app.api_route("/notion/{rest:path}", methods=["GET", "POST"])
    async def to_notion(rest: str, request: Request) -> Response:
        if not agent_may(request.method, rest):
            return JSONResponse({"error": {"code": "forbidden", "message": NOT_THE_AGENTS}}, status_code=403)
        call = await agent_call(request, routes)  # its key's workspace, and only that one
        if isinstance(call, JSONResponse):
            return call
        if call.bound.get("models") != "this-machine":  # design 0016 §10: no Notion page reaches the cloud
            said = NOTION_CLOUD.format(workspace=call.workspace)
            return JSONResponse({"error": {"code": "notion_denied", "message": said}}, status_code=403)
        if notion is None:
            said = "Notion is reached through the Clank service, which this gateway was not given"
            return JSONResponse({"error": {"code": "unavailable", "message": said}}, status_code=503)
        status, found = await notion(request.method, rest, call.body, call.params)
        return JSONResponse(found, status_code=status)

    @app.api_route("/flows/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def to_flows(rest: str, request: Request) -> Response:
        if (request.method, rest) not in FLOWS:
            return JSONResponse({"error": {"code": "forbidden", "message": NOT_THE_AGENTS_FLOW}}, status_code=403)
        call = await agent_call(request, routes)  # its key's workspace, and only that one
        if isinstance(call, JSONResponse):
            return call
        if flows is None:
            said = "Flows are reached through the Clank service, which this gateway was not given"
            return JSONResponse({"error": {"code": "unavailable", "message": said}}, status_code=503)
        status, found = await flows(request.method, rest, call.body, call.params)
        return JSONResponse(found, status_code=status)

    @app.api_route("/agents/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def to_agents(rest: str, request: Request) -> Response:
        if (request.method, rest) not in AGENTS:
            return JSONResponse({"error": {"code": "forbidden", "message": NOT_THE_AGENTS_SHOW}}, status_code=403)
        call = await agent_call(request, routes)  # its key's workspace, and only that one
        if isinstance(call, JSONResponse):
            return call
        if agents is None:
            said = "Showing files and jobs are reached through the Clank service, which this gateway was not given"
            return JSONResponse({"error": {"code": "unavailable", "message": said}}, status_code=503)
        status, found = await agents(request.method, rest, call.body, call.params)
        return JSONResponse(found, status_code=status)

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> Response:
        began = time.perf_counter()
        record: dict[str, Any] = {
            "id": f"r-{secrets.token_hex(4)}",
            "time": to_text(datetime.now(UTC)),
            "client": request.client.host if request.client else "",
            "headers": dict(request.headers),
        }
        activity.begin(record, began)
        try:
            return await answer(request, record, began)
        except BaseException:
            activity.drop(record)  # it ended before its record was kept (its client left while it waited)
            raise

    async def answer(request: Request, record: dict[str, Any], began: float) -> Response:
        try:
            body = await request.json()
        except ValueError:
            return _refuse(record, keep, 400, "invalid_request", "the request is not JSON")
        if not isinstance(body, dict):
            return _refuse(record, keep, 400, "invalid_request", "the request is not a JSON object")
        role = str(body.get("model") or "agent")
        streamed = bool(body.get("stream"))
        record.update(role=role, stream=streamed, request=body if settings.records else None)
        title = local_title(body) if settings.local_titles else None
        if title is not None:
            record.update(local="title", status=200, answer=title, total_ms=_ms(began))
            keep(record)
            return _title_answer(title, role, streamed)
        activity.census(record, await anyio.to_thread.run_sync(counted, body, settings))
        noticed(
            body, record
        )  # a call of a local-only tool marks its session, whatever slot serves it (design 0016 §10)
        held = holds.take(record["id"], *session_of(record.get("headers")))
        if held is not None:  # its session is paused (design 0012 §9.4): held at the door
            activity.hold(record, held)
            if streamed:
                stream = held_stream(held, body, role, record)
                weakref.finalize(stream, forget, held, record)  # a client that left before its stream began
                return StreamingResponse(stream, media_type="text/event-stream")
            try:
                await holds.wait(held)
            except Released:
                released(record, held)
                return JSONResponse(_empty_whole(role))
            began = resumed(record, held)
        refused = await woken(role)
        if refused:
            return _refuse(record, keep, 503, "no_engine", refused, began)
        route, why = await routes.ready(role, settings.hold_seconds)
        if route is None:
            return _refuse(record, keep, 503, "no_engine", why, began)
        if route.cloud:
            return await cloud_answer(route, body, record, began, streamed)
        upstream, again, why = await connect(route, body, role, record, began)
        if upstream is None:
            return _refuse(record, keep, 502, "engine_unreachable", why, began)

        if not streamed or upstream.status_code != 200:  # a whole answer, or the engine's refusal (read whole)
            try:
                data = await upstream.aread()
            except httpx2.HTTPError as error:
                await upstream.aclose()
                resent, why = await again()
                if resent is None:
                    return _refuse(
                        record, keep, 502, "engine_broke_off", f"the engine broke off: {error}; {why}", began
                    )
                record["again"] = AGAIN
                upstream = resent
                try:
                    data = await upstream.aread()
                finally:
                    await upstream.aclose()
            finally:
                await upstream.aclose()
            record["status"] = upstream.status_code
            if context_full(str(route.engine), str(route.version), upstream.status_code, data):
                words = _full(record, keep, _said(data), began)
                overflow = {"message": words, "type": OVERFLOW_CODE, "code": OVERFLOW_CODE}
                return JSONResponse({"error": overflow}, status_code=400)
            _read_whole(record, data)
            record["first_token_ms"] = record["total_ms"] = _ms(began)
            keep(record)
            kind = upstream.headers.get("content-type", "application/json")
            return Response(data, status_code=upstream.status_code, media_type=kind)
        relay = relayed(upstream, record, began, again)
        weakref.finalize(relay, activity.drop, record)  # a client that left before the answer began never starts it
        return StreamingResponse(
            relay,
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "text/event-stream"),
        )

    async def gate(
        route: SlotRoute, body: dict[str, Any], record: dict[str, Any]
    ) -> tuple[tuple[str, int, str, str], SlotRoute, dict[str, Any]]:
        """The one gate every cloud request passes right before it is sent, whatever held it first (design 0016 §9,
        §10, §11): the service's routes fresh; the role's slot still on a cloud model, its route as the routes say now;
        the workspace's bound (`admitted`); nothing local-only in its messages or its session (`local_only`), and the
        local-only tools taken out (`without_local_tools`); no spending limit reached. Its verdict, with the route and
        the request as they would go: `go`; `refuse`, with its status, code and words; `ask`, with the workspace not
        yet answered; `limit`."""
        if not await routes.fresh(settings.hold_seconds):
            return ("refuse", 503, "service_silent", SERVICE_SILENT), route, body
        if not routes.local_only_given():  # what never goes to the cloud is not known yet: nothing goes
            return ("refuse", 503, "local_only_unknown", LOCAL_ONLY_UNKNOWN), route, body
        found = routes.route(str(record.get("role") or "agent"))
        if found is None or not found.cloud or not found.serving:
            return ("refuse", 503, "no_engine", SLOT_CHANGED), route, body
        record.update(
            provider=f"cloud {found.endpoint}", endpoint=found.endpoint, adapter=found.adapter, prices=found.prices,
            preset=found.preset, model_sent=found.model_name,
        )  # fmt: skip
        verdict = admitted(found, record)
        if verdict[0] == "refuse":
            return verdict, found, body
        kept_from_cloud = local_only(body, record)
        if kept_from_cloud:
            return ("refuse", 403, "local_only", kept_from_cloud), found, body
        body = without_local_tools(body, record)
        if verdict[0] == "ask":
            return verdict, found, body
        if over_limit():
            return ("limit", 0, "", ""), found, body
        return ("go", 0, "", ""), found, body

    async def cloud_through(
        route: SlotRoute, body: dict[str, Any], record: dict[str, Any], began: float
    ) -> AsyncGenerator[bytes | Sent, None]:
        """The only way to a provider (design 0016 §8 to §11): the gate (`gate`), passed again after each hold, with a
        comment line now and then while its workspace is asked or a spending limit is reached; then the request, in the
        provider's fields, sent to `<base URL>/chat/completions` with the key held for its launch and the session for
        its cache. Last, what came of it (`Sent`): the provider's answer (its headers read, its body not), or the
        status, code and words to answer with. Never sent again (decision 0110)."""
        while True:
            verdict, route, body = await gate(route, body, record)
            if verdict[0] == "refuse":
                yield Sent(None, verdict[1], verdict[2], verdict[3], route, began)
                return
            if verdict[0] == "go":
                break
            if verdict[0] == "ask":
                allowed, words = False, NOT_ANSWERED.format(workspace=verdict[3])
                async with contextlib.aclosing(waiting_answer(verdict[3], record)) as waiting:
                    async for step in waiting:
                        if isinstance(step, bytes):
                            yield step
                            continue
                        allowed, words = step
                        break
                if not allowed:
                    yield Sent(None, 403, "model_send_denied", words, route, began)
                    return
            else:
                async with contextlib.aclosing(limit_waited(record)) as waiting_limit:
                    async for line in waiting_limit:
                        yield line
            began = time.perf_counter()  # held: timed from now, the hold apart
        adapter, label = str(route.adapter), endpoint_label(str(route.adapter))
        session, _ = session_of(record.get("headers"))
        sent, notes = endpoint_request(adapter, body, str(route.model_name), route.adds or {})
        record["estimated_in"] = math.ceil(len(json.dumps(sent.get("messages") or [])) * PLAIN_TOKENS_PER_CHARACTER)
        if record.get("held_back"):
            notes = [*notes, str(record["held_back"])]
        record.update(
            slot=route.slot, preset=route.preset, engine=f"cloud {route.endpoint}", provider=f"cloud {route.endpoint}",
            model_sent=sent["model"], notes=notes, wait_ms=_ms(began), reach=route.reach,
        )  # fmt: skip
        key = keys.value(str(route.endpoint), route.launch)
        if key is None:
            yield Sent(None, 503, "no_engine", NO_KEY.format(endpoint=route.endpoint), route, began)
            return
        waited = float(route.read_timeout or CLOUD_READ_SECONDS)
        request = clients["cloud"].build_request(
            "POST", f"{route.base_url}/chat/completions", json=sent, headers=endpoint_headers(adapter, key, session),
            timeout=httpx2.Timeout(waited, connect=CLOUD_CONNECT_SECONDS),
        )  # fmt: skip
        try:
            upstream = await clients["cloud"].send(request, stream=True)
        except httpx2.ConnectTimeout as error:
            yield Sent(None, 502, "cloud_unreachable", _unreachable(label, error), route, began)
            return
        except httpx2.TimeoutException:
            yield Sent(None, 504, "cloud_silent", _silent(label, waited), route, began)
            return
        except httpx2.HTTPError as error:
            yield Sent(None, 502, "cloud_unreachable", _unreachable(label, error), route, began)
            return
        record["status"] = upstream.status_code
        yield Sent(upstream, upstream.status_code, "", "", route, began)

    async def cloud_answer(
        route: SlotRoute, body: dict[str, Any], record: dict[str, Any], began: float, streamed: bool
    ) -> Response:
        """A cloud slot's request answered (design 0016 §8): a stream that must wait for its workspace's answer or a
        spending limit answered at once and kept alive (`cloud_stream`); any other through the gate
        (`cloud_through`): streamed as it comes, whole, or the provider's refusal with its status and Clank's words."""
        if streamed:
            look, route, body = await gate(route, body, record)  # a first look: a stream that must wait goes on now
            if look[0] == "refuse":
                return _refuse(record, keep, look[1], look[2], look[3], began)
            if look[0] != "go":
                return StreamingResponse(cloud_stream(route, body, record, began), media_type="text/event-stream")
        sent: Sent | None = None
        async with contextlib.aclosing(cloud_through(route, body, record, began)) as going:  # whole: no headers yet
            async for step in going:
                if isinstance(step, Sent):
                    sent = step
        assert sent is not None, "the way to the provider ends with what came of it"
        route, began, upstream = sent.route, sent.began, sent.upstream
        if upstream is None:
            return _refuse(record, keep, sent.status, sent.code, sent.words, began)
        label, waited = endpoint_label(str(route.adapter)), float(route.read_timeout or CLOUD_READ_SECONDS)
        if streamed and upstream.status_code == 200:
            relay = relayed(upstream, record, began, _never, (label, waited))
            weakref.finalize(relay, activity.drop, record)
            kind = upstream.headers.get("content-type", "text/event-stream")
            return StreamingResponse(relay, status_code=200, media_type=kind)
        try:
            data = await upstream.aread()
        except httpx2.TimeoutException:
            return _refuse(record, keep, 504, "cloud_silent", _silent(label, waited), began)
        except httpx2.HTTPError as error:
            return _refuse(record, keep, 502, "cloud_unreachable", _unreachable(label, error), began)
        finally:
            await upstream.aclose()
        if upstream.status_code != 200:
            return cloud_refused(route, upstream, data, record, began)
        _read_whole(record, data)
        record["first_token_ms"] = record["total_ms"] = _ms(began)
        keep(record)
        return Response(data, status_code=200, media_type=upstream.headers.get("content-type", "application/json"))

    def cloud_refused(
        route: SlotRoute, upstream: httpx2.Response, data: bytes, record: dict[str, Any], began: float
    ) -> Response:
        """The provider's refusal, passed on with its status (decision 0110): its words, then Clank's of what to do,
        without OpenCode's retry words for those it must not retry, and as 403 when its status is one OpenCode retries
        by (decision 0115: no provider under the record's data policy, OpenRouter's 503); `Retry-After` kept; a full
        context answered as OpenCode reads an overflow (decision 0090)."""
        adapter, status = str(route.adapter), upstream.status_code
        if endpoint_full(adapter, status, data):
            words = _full(record, keep, _said(data), began)
            overflow = {"message": words, "type": OVERFLOW_CODE, "code": OVERFLOW_CODE}
            return JSONResponse({"error": overflow}, status_code=400)
        refusal = cloud_refusal(route, status, data)
        message = refusal.message if refusal.retried else _unretried(refusal.message)
        record.update(
            status=status, error={"code": refusal.code, "message": message}, refusal=refusal.said, answer="",
            total_ms=_ms(began),
        )  # fmt: skip
        keep(record)
        headers = {"Retry-After": upstream.headers["retry-after"]} if "retry-after" in upstream.headers else {}
        error = {"message": message, "type": refusal.code, "code": refusal.code}
        answered = 403 if not refusal.retried and str(status) in RETRIED_STATUSES else status
        return JSONResponse({"error": error}, status_code=answered, headers=headers)

    def cloud_refusal(route: SlotRoute, status: int, data: bytes) -> Refusal:
        """What the provider's refusal means, by its adapter (`denied`: the record allows only providers that keep no
        data)."""
        provider = (route.adds or {}).get("provider") or {}
        denied = isinstance(provider, Mapping) and provider.get("data_collection") == "deny"
        return endpoint_refusal(str(route.adapter), status, data, str(route.model_name), denied)

    async def cloud_stream(
        route: SlotRoute, body: dict[str, Any], record: dict[str, Any], began: float
    ) -> AsyncGenerator[bytes, None]:
        """A cloud request on a stream whose 200 has gone out (held for its workspace's answer, a spending limit or its
        paused session): through the gate (`cloud_through`), its comment lines passed on; then the provider's answer,
        or a refusal or silence told inside the stream, worded to be retried or not."""
        try:
            sent: Sent | None = None
            async with contextlib.aclosing(cloud_through(route, body, record, began)) as going:
                async for step in going:
                    if isinstance(step, Sent):
                        sent = step
                    else:
                        yield step
            assert sent is not None, "the way to the provider ends with what came of it"
            route, began, upstream = sent.route, sent.began, sent.upstream
            if upstream is None:
                _refuse(record, keep, sent.status, sent.code, sent.words, began)
                yield worded(_held_words(sent, record), retried=sent.code in NEVER_SENT)
                return
            if upstream.status_code != 200:
                try:
                    data = await upstream.aread()
                finally:
                    await upstream.aclose()
                refusal = cloud_refusal(route, upstream.status_code, data)
                record.update(
                    status=upstream.status_code, error={"code": refusal.code, "message": refusal.message},
                    refusal=refusal.said, answer="", total_ms=_ms(began),
                )  # fmt: skip
                keep(record)
                yield worded(refusal.message, retried=refusal.retried)
                return
            label, waited = endpoint_label(str(route.adapter)), float(route.read_timeout or CLOUD_READ_SECONDS)
            async with contextlib.aclosing(relayed(upstream, record, began, _never, (label, waited))) as relay:
                async for chunk in relay:
                    yield chunk
        finally:
            if "total_ms" not in record:
                activity.drop(record)

    def noticed(body: dict[str, Any], record: dict[str, Any]) -> None:
        """Mark the request's session when its messages call a tool that never goes to the cloud."""
        called = local_calls(body.get("messages") or [], routes.local_only())
        session, _ = session_of(record.get("headers"))
        if called and session:
            marks.mark(session, called[0])

    def local_only(body: dict[str, Any], record: dict[str, Any]) -> str:
        """Why a cloud request is kept from the cloud (design 0016 §10, 4): its messages call a local-only tool, or its
        session, or the session that started it, is marked; "" when it is not."""
        prefixes = routes.local_only()
        session, parent = session_of(record.get("headers"))
        called = local_calls(body.get("messages") or [], prefixes)
        tool = called[0] if called else marks.marked(session, parent)
        if not tool:
            return ""
        return LOCAL_ONLY.format(what=whose(tool, prefixes))

    def without_local_tools(body: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
        """The request without the tools that never go to the cloud (design 0016 §10, 3), its record's notes saying
        so."""
        if not body.get("tools"):
            return body
        kept, removed = held_back(body["tools"], routes.local_only())
        if not removed:
            return body
        record["held_back"] = f"{len(removed)} local-only tools held back from the cloud model: {', '.join(removed)}"
        return {**body, "tools": kept}

    def admitted(route: SlotRoute, record: dict[str, Any]) -> tuple[str, int, str, str]:
        """Whether a cloud request may go (design 0016 §9): `go`; `refuse`, with its status, code and words; or `ask`,
        with its workspace's name, for a workspace not yet answered."""
        label = endpoint_label(str(route.adapter))
        if route.agreed is False:
            return "refuse", 403, "model_send_denied", NOT_AGREED.format(provider=label)
        named = routes.workspace(key_of((record.get("headers") or {}).get("authorization")))
        if named is None:
            return "refuse", 403, "model_send_denied", UNKNOWN_KEY
        workspace = str(named.get("workspace"))
        record["workspace"] = workspace
        if named.get("models") == "cloud":
            return "go", 0, "", ""
        if named.get("answered"):
            return "refuse", 403, "model_send_denied", KEPT_LOCAL.format(workspace=workspace)
        return "ask", 0, "", workspace

    async def answered(workspace: str, record: dict[str, Any]) -> tuple[bool, str]:
        """A workspace's answer to its cloud question, asked of the service: whether its request may go, and the words
        of its refusal when not."""
        async with contextlib.aclosing(waiting_answer(workspace, record)) as waiting:
            async for step in waiting:
                if isinstance(step, tuple):
                    return step
        return False, NOT_ANSWERED.format(workspace=workspace)

    async def waiting_answer(workspace: str, record: dict[str, Any]) -> AsyncGenerator[bytes | tuple[bool, str], None]:
        """The service asked once; then, while the workspace is not answered, a comment line now and then; at last
        whether it may go, and why not."""
        session, _ = session_of(record.get("headers"))
        asked: dict[str, Any] = {}
        if ask_cloud is not None:
            with contextlib.suppress(Exception):  # the service may not answer: the routes say what it decides
                asked = await ask_cloud(workspace, session)
        question = asked.get("question")
        record["held_for"] = "the workspace's cloud question"
        deadline = time.monotonic() + QUESTION_SECONDS
        said, seen = time.monotonic(), False
        yield HELD_FOR_ANSWER.format(workspace=workspace).encode()
        while time.monotonic() < deadline:
            named = routes.workspace_named(workspace) or {}
            if named.get("models") == "cloud":
                yield True, ""
                return
            if named.get("answered"):
                yield False, KEPT_LOCAL.format(workspace=workspace)
                return
            question = question or named.get("question")
            seen = seen or (bool(question) and named.get("question") == question)
            if seen and named.get("question") != question:  # the routes showed it, and it is gone: not answered
                yield False, NOT_ANSWERED.format(workspace=workspace)
                return
            if time.monotonic() - said >= holds.keep_seconds:
                said = time.monotonic()
                yield HELD_FOR_ANSWER.format(workspace=workspace).encode()
            await anyio.sleep(POLL_SECONDS)
        yield False, NOT_ANSWERED.format(workspace=workspace)

    def over_limit() -> bool:
        """Whether a spending limit is reached (design 0016 §12): today's and this month's spending as the service
        has it, with the spool's entries it has not taken yet, against the limits."""
        cost = routes.cost()
        if not cost:
            return False
        pending = 0.0
        if spool is not None:
            taken = int(cost.get("taken") or 0) if str(cost.get("run") or "") == spool.run else 0
            pending = sum(float(entry.get("usd") or 0.0) for entry in spool.pending() if int(entry["seq"]) > taken)
        for spent, limit in ((cost.get("day_usd"), cost.get("limit_day_usd")),
                             (cost.get("month_usd"), cost.get("limit_month_usd"))):  # fmt: skip
            if limit is not None and float(spent or 0.0) + pending >= float(limit):
                return True
        return False

    async def limit_waited(record: dict[str, Any]) -> AsyncGenerator[bytes, None]:
        """While a spending limit is reached: a comment line now and then, until it is raised or its day or month
        ends (the service's routes say so); nothing at all when none is."""
        if not over_limit():
            return
        held_at_limit[0] += 1
        record["held_for"] = "the cloud spending limit"
        try:
            said = -holds.keep_seconds
            while over_limit():
                if time.monotonic() - said >= holds.keep_seconds:
                    said = time.monotonic()
                    yield HELD_AT_LIMIT
                await anyio.sleep(POLL_SECONDS)
        finally:
            held_at_limit[0] -= 1

    async def woken(role: str) -> str:
        """A role loaded on demand, asked of the service first: why it is not loaded ("" when it is, or is being)."""
        if wake is None or not routes.demand(role):
            return ""
        refused = await wake(role)  # the service loads it, or says why not (vision is off)
        if not refused:
            await routes.woken(role, WAKE_SECONDS)
        return refused

    async def connect(
        route: SlotRoute, body: dict[str, Any], role: str, record: dict[str, Any], began: float
    ) -> tuple[httpx2.Response | None, Again, str]:
        """The request, in the engine's own fields, sent to the slot's engine: its answer (its headers read, its body
        not), how to send it again once the slot is served again, and why there is none when the engine did not answer
        even then."""
        assert route.engine is not None, "a serving route names its engine"
        assert route.version is not None, "and its version"
        assert route.port is not None, "and its port"
        sent, notes = translate_request(route.engine, route.version, body)
        sent["model"] = route.model_name or sent.get("model")
        record.update(
            slot=route.slot, preset=route.preset, engine=f"{route.engine} {route.version}", model_sent=sent["model"],
            notes=notes, wait_ms=_ms(began),
        )  # fmt: skip

        broken: list[int | None] = [route.port]  # the engine asked last: one that broke off is not taken back at once

        async def again() -> tuple[httpx2.Response | None, str]:
            """The request sent again once the role's slot is served again; None, and why, when it is not."""
            deadline = time.monotonic() + settings.hold_seconds
            while True:
                found, why = await routes.recovered(role, max(deadline - time.monotonic(), 0.0), broken[0])
                if found is None:
                    return None, why
                if found.cloud:  # switched to a cloud model meanwhile: only a request sent anew passes its gate
                    return None, CLOUD_NOW.format(title=found.title or found.preset or "")
                assert found.engine is not None, "a served route names its engine"
                assert found.version is not None, "and its version"
                resent, _ = translate_request(found.engine, found.version, body)
                resent["model"] = found.model_name or resent.get("model")
                url = f"http://127.0.0.1:{found.port}/v1/chat/completions"
                broken[0] = found.port
                try:
                    request = clients["engine"].build_request("POST", url, json=resent)
                    return await clients["engine"].send(request, stream=True), ""
                except httpx2.HTTPError:
                    if time.monotonic() >= deadline:
                        return None, "its engine did not answer when the request was sent again"
                    await anyio.sleep(1.0)  # served on paper, but not listening yet

        url = f"http://127.0.0.1:{route.port}/v1/chat/completions"
        try:
            upstream = await clients["engine"].send(
                clients["engine"].build_request("POST", url, json=sent), stream=True
            )
        except httpx2.HTTPError as error:  # it ended before its answer began (or had ended): wait for it to be back
            resent, why = await again()
            if resent is None:
                return None, again, f"the engine did not answer: {error}; {why}"
            record["again"] = AGAIN
            upstream = resent
        record["status"] = upstream.status_code
        return upstream, again, ""

    def relayed(
        upstream: httpx2.Response,
        record: dict[str, Any],
        began: float,
        again: Again,
        cloud: tuple[str, float] | None = None,
    ) -> AsyncGenerator[bytes, None]:
        """A streamed answer passed on as it comes (`_relay`), read by the loop guard when it is on; a cloud model's
        (`cloud`: its provider's name and read timeout) is never sent again."""
        guard = (
            LoopGuard(settings.loop_windows, settings.loop_ratio, settings.loop_tool_windows)
            if settings.loop_guard
            else None
        )
        if guard is not None:
            activity.guard(record, guard)  # its newest shares show while it streams

        def counted(found: dict[str, Any], kind: str) -> None:
            activity.token(found, kind)
            if cloud is not None:  # a cloud stream cut short is estimated from its pieces (design 0016 §12)
                pieces = found.setdefault("pieces", {})
                pieces[kind] = pieces.get(kind, 0) + 1

        return _relay(upstream, record, keep, began, counted, again,
                      lambda kind, text: activity.heard(record, kind, keys.scrub(text)), guard, cloud)  # fmt: skip

    async def held_stream(held: Held, body: dict[str, Any], role: str, record: dict[str, Any]) -> AsyncIterator[bytes]:
        """A held streamed request (design 0012 §9.4): its comment lines while held; once resumed, the request goes on
        on the same stream, the same keep-alive while it waits for its slot, and a refusal or the engine's own error
        then told inside the stream, worded to be retried or not (`worded`); a note's release ends it as an empty
        step."""
        try:
            try:
                async with contextlib.aclosing(holds.keep(held)) as waiting:
                    async for line in waiting:
                        yield line
            except Released:
                released(record, held)
                yield _empty_step(role)
                return
            began = resumed(record, held)
            refused = await woken(role)
            route: SlotRoute | None = None
            if not refused:
                deadline = time.monotonic() + settings.hold_seconds
                while True:
                    route, _ = await routes.ready(role, min(holds.keep_seconds, max(0.0, deadline - time.monotonic())))
                    if route is not None:
                        break
                    if not routes.changing(role) or time.monotonic() >= deadline:
                        refused = routes.why(role, settings.hold_seconds)
                        break
                    yield b": held by Clank: resumed; waiting for the model's slot\n\n"
            if route is not None and route.cloud:  # the gate, as for any cloud request (design 0016 §9, §10, §11)
                async with contextlib.aclosing(cloud_stream(route, body, record, began)) as answered:
                    async for chunk in answered:
                        yield chunk
                return
            upstream: httpx2.Response | None = None
            status, code = 503, "no_engine"
            if route is not None:
                upstream, again, refused = await connect(route, body, role, record, began)
                status, code = 502, "engine_unreachable"
            if upstream is None:
                _refuse(record, keep, status, code, refused, began)
                yield worded(f"{refused} (the request was held while its session was paused)", retried=True)
                return
            if upstream.status_code != 200:  # the engine's own refusal
                try:
                    data = await upstream.aread()
                finally:
                    await upstream.aclose()
                said = _said(data)
                assert route is not None, "an engine answered: its route was ready"
                if context_full(str(route.engine), str(route.version), upstream.status_code, data):
                    yield _overflowed(_full(record, keep, said, began))
                    return
                record.update(error=said, answer="", total_ms=_ms(began))
                keep(record)
                yield worded(said, retried=upstream.status_code >= 500 or upstream.status_code == 429)
                return
            async with contextlib.aclosing(relayed(upstream, record, began, again)) as relay:
                async for chunk in relay:
                    yield chunk
        finally:
            if "total_ms" not in record:  # never kept: its client left while it was held, or waited for its slot
                activity.drop(record)

    def resumed(record: dict[str, Any], held: Held) -> float:
        """A held request whose pause ended: its hold kept in its record, and from now on it is timed as one that came
        now (its time to the first token, its wait), the hold apart (`held`)."""
        record["held"] = held.facts()
        began = time.perf_counter()
        activity.restart(record, began)
        return began

    def released(record: dict[str, Any], held: Held) -> None:
        """A held request a note closed: answered as an empty step by the gateway itself, never counted (as a title)."""
        total = round(held.seconds * 1000, 1)
        record.update(local="released", status=200, answer="", held=held.facts(), total_ms=total)
        keep(record)

    def forget(held: Held, record: dict[str, Any]) -> None:
        holds.drop(held)
        activity.drop(record)

    return app


async def _relay(
    upstream: httpx2.Response,
    record: dict[str, Any],
    keep: Keep,
    began: float,
    counted: Count,
    again: Callable[[], Awaitable[tuple[httpx2.Response | None, str]]],
    heard: Callable[[str, str], None] | None = None,
    guard: LoopGuard | None = None,
    cloud: tuple[str, float] | None = None,
) -> AsyncGenerator[bytes, None]:
    """The engine's answer, passed on as it comes, whole lines at a time; read along for the record, each token counted
    by its kind as it passes. When the engine breaks off before any token (it crashed), the request is sent again once
    (`again`) and the new answer follows on the same stream; otherwise the stream ends with an error event. When the
    loop guard finds the answer repeating itself, the stream ends with an error event that says what repeated, and the
    connection to the engine is closed. A client that leaves cancels this, which closes the connection to the engine, so
    the engine stops generating."""
    pieces: list[str] = []
    buffer = b""
    left = True
    answered = False
    finished = False  # the stream said it ended: a finish reason, `[DONE]` or an error event
    try:
        while True:
            try:
                async for chunk in upstream.aiter_raw():
                    buffer += chunk
                    *lines, buffer = buffer.split(b"\n")
                    lines = [_engine_error(line, record) for line in lines]
                    for line in lines:
                        finished = finished or _finishes(line)
                        kinds = _read_event(line, pieces, record, heard, guard)
                        if kinds:
                            answered = True
                            record.setdefault("first_token_ms", _ms(began))
                        for kind in kinds:
                            counted(record, kind)
                    if lines:
                        yield b"".join(line + b"\n" for line in lines)
                    if guard is not None and guard.tripped is not None:
                        break  # the connection to the engine closes below, so it stops writing
                tripped = guard is not None and guard.tripped is not None
                if not (finished or _finishes(buffer.strip()) or tripped) and upstream.status_code == 200:
                    raise EndedEarly("its stream stopped without its end")
                left = False
                if guard is not None and guard.tripped is not None:
                    message = f"{LOOPED}: {guard.brief}. {OFF}"  # no numbers: OpenCode retries by them
                    record.update(looped=guard.tripped, error=message)
                    yield _broken(message, "model_looped")
                elif buffer:
                    yield buffer
                break
            except (httpx2.HTTPError, EndedEarly) as error:
                await upstream.aclose()
                buffer = b""
                if cloud is not None:  # a cloud request is never sent again: it may have been billed (decision 0110)
                    left = False
                    label, waited = cloud
                    if isinstance(error, httpx2.TimeoutException) and not isinstance(error, httpx2.ConnectTimeout):
                        record["broken"] = _silent(label, waited)
                        yield _broken(record["broken"], "cloud_silent")
                    else:
                        said = str(error) or type(error).__name__
                        record["broken"] = f"{label} broke off its answer ({said}); {NEVER_AGAIN}"
                        yield _broken(record["broken"], "cloud_unreachable")
                    break
                if answered or "again" in record:
                    record["broken"] = f"the engine broke off its answer: {error}"
                    left = False
                    yield _broken(f"the engine broke off its answer after answering part of it ({error}); ask again")
                    break
                record["waiting_again"] = True  # the console shows it waits for its engine
                try:
                    resent, why = await again()
                finally:
                    record.pop("waiting_again", None)
                if resent is None:
                    record["broken"] = f"the engine broke off its answer before answering: {error}; {why}"
                    left = False
                    yield _broken(f"the engine stopped before answering and was not served again: {why}")
                    break
                record["again"] = AGAIN
                upstream = resent  # the client may still leave the new answer: `left` stays as it is
                finished = False
    finally:
        await upstream.aclose()
        record.update(answer="".join(pieces), total_ms=_ms(began))
        if left:
            record["left"] = "the client left before the answer ended"
        keep(record)


async def _never() -> tuple[httpx2.Response | None, str]:
    """A cloud request's way to be sent again: none (decision 0110)."""
    return None, NEVER_AGAIN


NEVER_SENT = ("cloud_unreachable", "no_engine", "service_silent", "local_only_unknown")  # nothing reached the provider


def _held_words(sent: Sent, record: dict[str, Any]) -> str:
    """A cloud request's refusal told inside a stream that was held: what was refused, and what held it (its paused
    session, the cloud spending limit, or the workspace's cloud question)."""
    if record.get("held"):
        return f"{sent.words} (the request was held while its session was paused)"
    if record.get("held_for") == "the cloud spending limit":
        return f"{sent.words} (the request was held at the cloud spending limit)"
    if record.get("held_for"):
        return f"{sent.words} (the request was held for {record['held_for']})"
    return sent.words


def _unreachable(label: str, error: Exception) -> str:
    said = str(error) or type(error).__name__
    return f"{label} did not answer: {said}; check this computer's network ({NEVER_AGAIN})"


def _silent(label: str, seconds: float) -> str:
    return f"{label} was silent for {seconds:g} s: the answer ends here ({NEVER_AGAIN})"


class EndedEarly(Exception):
    """An engine's stream that stopped without its end: handled as a connection that broke."""


def _finishes(line: bytes) -> bool:
    """Whether a line of a streamed answer says the answer ended: `[DONE]`, an error event, or a choice with its finish
    reason (OpenAI's streams end so; KVMem's and llama.cpp's do)."""
    if not line.startswith(b"data:"):
        return False
    data = line[5:].strip()
    if data == b"[DONE]":
        return True
    if b'"error"' not in data and b'"finish_reason"' not in data:
        return False
    try:
        event = json.loads(data)
    except ValueError:
        return False
    if not isinstance(event, dict):
        return False
    choices = event.get("choices") or []
    return "error" in event or any(isinstance(choice, dict) and choice.get("finish_reason") for choice in choices)


def _broken(message: str, code: str = "engine_broke_off") -> bytes:
    """An error event in the stream, as OpenAI's streams end with one (the status, 200, is already sent)."""
    error = {"error": {"message": message, "type": code, "code": code}}
    return b"data: " + json.dumps(error).encode() + b"\n\n"


def _engine_error(line: bytes, record: dict[str, Any]) -> bytes:
    """A line of the engine's stream, with an error event as OpenAI writes one (an object: its message, type and code;
    KVMem sends a plain string, which OpenAI's clients cannot read) and the error recorded; any other line as it is."""
    if not line.startswith(b"data:") or b'"error"' not in line:
        return line
    try:
        event = json.loads(line[5:])
    except ValueError:
        return line
    if not isinstance(event, dict) or "error" not in event:
        return line
    found = event["error"]
    if isinstance(found, dict):
        record["error"] = str(found.get("message") or found)
        return line
    record["error"] = str(found)
    rewritten = {**event, "error": {"message": str(found), "type": "engine_error", "code": "engine_error"}}
    return b"data: " + json.dumps(rewritten).encode()


def _read_event(
    line: bytes,
    pieces: list[str],
    record: dict[str, Any],
    heard: Callable[[str, str], None] | None = None,
    guard: LoopGuard | None = None,
) -> list[str]:
    """One line of a streamed answer, read for the record: its text, and its usage and the engine's timings when it
    carries them; the kinds of token it carried (`thinking`, `answer`, `tool`: none when it carried no text). Its
    thinking, its answer and its tool calls go to `heard` as they come (the live view), and to the loop guard; each
    tool call's id, as its first piece names it, is kept in the record's `calls` (design 0012 §6.1)."""
    if not line.startswith(b"data:"):
        return []
    data = line[5:].strip()
    if not data or data == b"[DONE]":
        return []
    try:
        event = json.loads(data)
    except ValueError:
        return []
    kinds: list[str] = []
    if isinstance(event, dict):
        for name in ("usage", "timings"):
            if isinstance(event.get(name), dict):
                record[name] = event[name]
        if str(record.get("provider") or "").startswith("cloud ") and isinstance(event.get("id"), str):
            record.setdefault("generation", event["id"])  # the provider's record of the request (design 0016 §12)
        for choice in event.get("choices") or []:
            delta = (choice.get("delta") or {}) if isinstance(choice, dict) else {}
            pieces.append(str(delta.get("content") or ""))
            if heard is not None:
                _heard(delta, heard)
            if guard is not None:
                _guarded(delta, guard)
            for call in delta.get("tool_calls") or []:
                if isinstance(call, dict) and call.get("id") and call["id"] not in record.setdefault("calls", []):
                    record["calls"].append(str(call["id"]))
            if _thought(delta) and "thinking" not in kinds:
                kinds.append("thinking")
            for kind, name in (("answer", "content"), ("tool", "tool_calls")):
                if delta.get(name) and kind not in kinds:
                    kinds.append(kind)
    return kinds


def _thought(delta: dict[str, Any]) -> str:
    """A streamed delta's thinking: `reasoning_content` (llama.cpp's, KVMem's), else `reasoning` (OpenRouter's,
    decision 0074); a delta that carries both is read once."""
    return str(delta.get("reasoning_content") or delta.get("reasoning") or "")


def _guarded(delta: dict[str, Any], guard: LoopGuard) -> None:
    """A streamed delta's thinking, answer and tool calls' arguments, to the loop guard: each call apart, by its
    index, with its name when the delta carries it."""
    if thought := _thought(delta):
        guard.feed("thinking", thought)
    if delta.get("content"):
        guard.feed("answer", str(delta["content"]))
    for call in delta.get("tool_calls") or []:
        if isinstance(call, dict):
            function = call.get("function") or {}
            arguments, name = str(function.get("arguments") or ""), str(function.get("name") or "")
            guard.feed(f"tool {call.get('index', 0)}", arguments, name)


def _heard(delta: dict[str, Any], heard: Callable[[str, str], None]) -> None:
    """A streamed delta's thinking, answer and tool calls (a call's name as it starts, then its arguments)."""
    if thought := _thought(delta):
        heard("thinking", thought)
    if delta.get("content"):
        heard("answer", str(delta["content"]))
    for call in delta.get("tool_calls") or []:
        function = (call.get("function") or {}) if isinstance(call, dict) else {}
        if function.get("name"):
            heard("tool", f"\n→ {function['name']} ")
        if function.get("arguments"):
            heard("tool", str(function["arguments"]))


def _read_whole(record: dict[str, Any], data: bytes) -> None:
    """A whole answer, read for the record: its text, its usage, or its error."""
    try:
        answer = json.loads(data)
    except ValueError:
        record["answer"] = data.decode("utf-8", errors="replace")
        return
    if not isinstance(answer, dict):
        return
    if isinstance(answer.get("usage"), dict):
        record["usage"] = answer["usage"]
    if str(record.get("provider") or "").startswith("cloud ") and isinstance(answer.get("id"), str):
        record.setdefault("generation", answer["id"])
    if "error" in answer:
        record["error"] = answer["error"]
    choices = answer.get("choices") or []
    if choices and isinstance(choices[0], dict):
        record["answer"] = str((choices[0].get("message") or {}).get("content") or "")


def _empty_step(role: str) -> bytes:
    """A held request a note closed (design 0012 §9.4), as a streamed answer: an empty step that ends, then `[DONE]`."""
    ended = {"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": "stop"}
    chunk = {"id": "chatcmpl-held", "object": "chat.completion.chunk", "created": int(time.time()), "model": role,
             "choices": [ended]}  # fmt: skip
    return b"data: " + json.dumps(chunk).encode() + b"\n\ndata: [DONE]\n\n"


def _empty_whole(role: str) -> dict[str, Any]:
    """A held request a note closed, as a whole answer: empty, ended."""
    message = {"role": "assistant", "content": ""}
    return {"id": "chatcmpl-held", "object": "chat.completion", "created": int(time.time()), "model": role,
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}]}  # fmt: skip


def _full(record: dict[str, Any], keep: Keep, said: str, began: float) -> str:
    """An engine's refusal of a full context, kept in its record (`full`: the engine's words, `said`; status 400, as
    the client is told); the words the client is told."""
    words = f"{FULL}: {said} ({OVERFLOW})"
    record.update(status=400, full=said, error={"code": OVERFLOW_CODE, "message": words}, answer="",
                  total_ms=_ms(began))  # fmt: skip
    keep(record)
    return words


def _overflowed(words: str) -> bytes:
    """A full context told inside a stream whose 200 has gone out (a held request, after its resume): an error event
    whose message is OpenAI's Responses shape of it written as JSON, the one form OpenCode 1.19 reads as an overflow in
    a stream (decision 0090)."""
    shape = {"type": "error", "error": {"code": OVERFLOW_CODE, "message": words}}
    return _broken(json.dumps(shape), OVERFLOW_CODE)


def worded(message: str, *, retried: bool) -> bytes:
    """An error told inside a stream whose 200 has gone out (a held request, after its resume: design 0012 §9.4), worded
    on purpose: OpenCode retries an error whose words hold a word of its retry patterns, and ends the run on any other
    (decision 0040). Retried, it says the model is unavailable; not retried, OpenCode's retry words are taken out of
    the engine's own words, and its numbers that hold a status OpenCode retries are spaced out."""
    if retried:
        return _broken(f"the model is unavailable for now: {message}", "unavailable")
    return _broken(_unretried(message), "engine_refused")


RETRIED_STATUSES = ("429", "500", "502", "503", "504", "524")  # decision 0040: what OpenCode 1.19 retries by
RETRIED_WORDS = (  # and words of the same sort, each with words that say the same without it
    (re.compile(r"unavailable", re.IGNORECASE), "not available"),
    (re.compile(r"overloaded", re.IGNORECASE), "over its load"),
    (re.compile(r"exhausted", re.IGNORECASE), "used up"),
    (re.compile(r"rate[ _-]?limit(ed)?", re.IGNORECASE), "limit of requests"),
    (re.compile(r"too many requests", re.IGNORECASE), "more requests than it takes"),
)


def _unretried(words: str) -> str:
    """Words that hold none of OpenCode's retry words, nor a number that holds a status it retries by."""
    for found, instead in RETRIED_WORDS:
        words = found.sub(instead, words)
    return re.sub(
        r"\d+",
        lambda number: " ".join(number.group()) if any(code in number.group() for code in RETRIED_STATUSES)
        else number.group(),
        words,
    )  # fmt: skip


def _said(data: bytes) -> str:
    """What an engine's refusal says: its error's message (OpenAI's shape, or llama.cpp's), else its text."""
    try:
        found = json.loads(data)
    except ValueError:
        return data.decode("utf-8", errors="replace").strip() or "the engine refused the request, saying nothing"
    error = found.get("error") if isinstance(found, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    return str(error or found)


def _title_answer(title: str, role: str, streamed: bool) -> Response:
    """The title, as the model would have answered it: streamed or whole, as asked."""
    made = int(time.time())
    if not streamed:
        message = {"role": "assistant", "content": title}
        whole = {"id": "chatcmpl-title", "object": "chat.completion", "created": made, "model": role,
                 "choices": [{"index": 0, "message": message, "finish_reason": "stop"}]}  # fmt: skip
        return JSONResponse(whole)
    chunks = [
        {"choices": [{"index": 0, "delta": {"role": "assistant", "content": title}, "finish_reason": None}]},
        {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    ]
    lines = [
        "data: "
        + json.dumps(
            {"id": "chatcmpl-title", "object": "chat.completion.chunk", "created": made, "model": role, **chunk}
        )
        for chunk in chunks
    ]
    return Response("\n\n".join([*lines, "data: [DONE]"]) + "\n\n", media_type="text/event-stream")


def _refuse(
    record: dict[str, Any], keep: Keep, status: int, code: str, message: str, began: float | None = None
) -> JSONResponse:
    record.update(status=status, error={"code": code, "message": message})
    if began is not None:
        record["total_ms"] = _ms(began)
    keep(record)
    return JSONResponse({"error": {"message": message, "type": code, "code": code}}, status_code=status)


def agent_may(method: str, path: str) -> bool:
    """Whether the agent may ask this of Notion: reading and proposing only."""
    if (method, path) in NOTION:
        return True
    page = path[len("page/") :] if path.startswith("page/") else ""
    return method == "GET" and bool(page) and "/" not in page and ".." not in page


def notion_forwarder(connect: "Callable[[], Client]", *, close: bool = True) -> Forward:
    """The agent's Notion requests, sent to the service by a client of it (`connect`, named `agent`; closed after
    each request unless `close` is false): the service's answer, its refusal, or that it does not answer."""
    return _forwarder(connect, "notion", "Notion is reached", close=close)


def flows_forwarder(connect: "Callable[[], Client]", *, close: bool = True) -> Forward:
    """The agent's requests of its flow (design 0013 §9), sent to the service as `notion_forwarder` sends Notion's."""
    return _forwarder(connect, "flows", "Flows are reached", close=close)


def agents_forwarder(connect: "Callable[[], Client]", *, close: bool = True) -> Forward:
    """The agent's request to open files for the owner (design 0018 §7), sent to the service as Notion's are."""
    return _forwarder(connect, "agents", "Showing files is reached", close=close)


def _forwarder(connect: "Callable[[], Client]", prefix: str, reached: str, *, close: bool) -> Forward:
    """Requests under `/<prefix>/`, sent to the service's own routes there by a client of it named `agent`: the
    service's answer, its refusal, or that it does not answer (`reached`: what is reached through it)."""
    from clank.client import ClientError, NotRunning

    def silent(error: Exception) -> tuple[int, Any]:
        return 503, {"error": {"code": "unavailable", "message": f"{reached} through the Clank service: {error}"}}

    def call(method: str, path: str, body: Any, params: dict[str, str]) -> tuple[int, Any]:
        try:
            client = connect()
        except NotRunning as error:
            return silent(error)
        try:
            if method == "GET":
                return 200, client.get(f"{prefix}/{path}", **params)
            return 200, client.post(f"{prefix}/{path}", body)
        except ClientError as error:
            return error.status, {"error": {"code": error.code, "message": str(error)}}
        except NotRunning as error:
            return silent(error)
        finally:
            if close:
                client.close()

    async def forward(method: str, path: str, body: Any, params: dict[str, str]) -> tuple[int, Any]:
        return await anyio.to_thread.run_sync(call, method, path, body, params)

    return forward


def counted(body: dict[str, Any], settings: GatewaySettings) -> dict[str, Any] | None:
    """A request's census (`census.py`), measured as the loop guard measures (its ratio, its shortest stretch), with
    words of the request only when the records keep them (`records`); None when it cannot be made, whatever went
    wrong, which leaves the request as it was, and the log counts it, never saying what the request held."""
    shortest = min([*settings.loop_windows, *settings.loop_tool_windows] or [2000])
    try:
        return census(body, settings.loop_ratio, shortest, words=settings.records)
    except Exception:  # noqa: BLE001: a census is the Monitor's, never a reason for a request to fail or stall
        FAILED_CENSUSES[0] += 1
        log.warning("a request's census could not be made (%d so far); the request goes on without one",
                    FAILED_CENSUSES[0])  # fmt: skip
        return None


def _ms(began: float) -> float:
    return round((time.perf_counter() - began) * 1000, 1)


def follow(routes: Routes, fetch: Any, stop: threading.Event) -> None:
    """Ask the service for the routes every second until stopped, keeping the last answer when it gives none."""
    while not stop.is_set():
        with contextlib.suppress(Exception):  # the service may be restarting: the last routes stay
            routes.update(fetch())
        stop.wait(FOLLOW_SECONDS)


def settings_of(raw: Mapping[str, Any] | None) -> GatewaySettings:
    """The gateway's settings from its file's values, or its built-in ones."""
    values = {key: value for key, value in (raw or {}).items() if key != "schema"}
    return GatewaySettings.model_validate(values)


class Serving(uvicorn.Server):
    """Uvicorn serving the gateway, which removes the sockets it made (Linux, design 0014 §3) as it begins to stop:
    after a stop signal, Uvicorn hands the signal back to the process, which then ends at once, running nothing after
    `run`."""

    def __init__(self, config: uvicorn.Config, made: list[tuple[Path, os.stat_result]]) -> None:
        super().__init__(config)
        self.made = made

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        """Its sockets removed, then Uvicorn's own stop."""
        remove_sockets(self.made)
        await super().shutdown(sockets)


def own_listeners(port: int, folder: str | None) -> Listeners | None:
    """On Linux, given its socket folder, the listeners the gateway makes itself (`sockets.listeners`, design 0014 §3):
    its TCP socket, its Unix socket and the proxy's; None otherwise, and Uvicorn makes the TCP socket as before. An
    `OSError` when the port cannot be bound."""
    if sys.platform != "win32" and folder:  # Unix sockets: the type checker knows them only off Windows
        from clank.components.gateway.sockets import listeners

        return listeners(port, Path(folder))
    return None


def main(argv: list[str] | None = None) -> int:
    """Run the gateway: `python -m clank.components.gateway.server [--port PORT] [--socket-folder FOLDER]`, CLANK_HOME
    naming the home."""
    from clank.client import Client
    from clank.kernel.access import local_token
    from clank.kernel.home import Home

    parser = argparse.ArgumentParser(description="Clank's gateway: every model request, to the engine of its role.")
    parser.add_argument("--port", type=int, help="Where to listen (default: the gateway's settings).")
    parser.add_argument(
        "--socket-folder",
        help="On Linux, the folder of its socket and the proxy's: the edge's way in on Docker Engine (design 0014 §3).",
    )
    options = parser.parse_args(argv)
    home = Home.resolve()
    file = home.config / "gateway.json"
    settings = settings_of(json.loads(file.read_text(encoding="utf-8")) if file.is_file() else None)
    port = options.port or settings.port
    try:
        listening = own_listeners(port, options.socket_folder)
    except OSError as error:  # another program holds the port: logged, and ended as Uvicorn ends then
        logging.getLogger(__name__).error(
            "[Errno %s] error while attempting to bind on address %r: %s",
            error.errno, ("127.0.0.1", port), (error.strerror or str(error)).lower(),
        )  # fmt: skip
        return STARTUP_FAILURE
    routes = Routes()
    stop = threading.Event()

    def fetch() -> Any:
        client = Client.connect(home, name="gateway")
        try:
            return client.get("gateway/routes")
        finally:
            client.close()

    def cloud_wanted(workspace: str, session: str) -> dict[str, Any]:
        client = Client.connect(home, name="gateway")
        try:
            found: dict[str, Any] = client.post("gateway/cloud-wanted", {"workspace": workspace, "session": session})
            return found
        finally:
            client.close()

    async def ask_cloud(workspace: str, session: str) -> dict[str, Any]:
        return await anyio.to_thread.run_sync(cloud_wanted, workspace, session)

    def wanted(role: str) -> str:
        client = Client.connect(home, name="gateway")
        try:
            return str(client.post("gateway/wanted", {"role": role}).get("refused") or "")
        except Exception as error:
            return f"the service did not load it: {error}"
        finally:
            client.close()

    async def wake(role: str) -> str:
        return await anyio.to_thread.run_sync(wanted, role)

    def host_wanted(workspace: str, host: str) -> str:
        """Ask the service about a host the agent reaches (design 0024 §3), and wait for the owner's decision."""
        client = Client.connect(home, name="gateway")
        try:
            found = client.post(f"workspaces/{quote(workspace, safe='')}/hosts/wanted", {"host": host})
            if found.get("allowed"):
                return "always"
            question = found.get("question")
            if not question:
                return "no"
            deadline = time.monotonic() + HOLD_SECONDS + 5
            while time.monotonic() < deadline:
                decided = client.get(f"workspaces/hosts/wanted/{quote(str(question), safe='')}")
                if decided.get("status") != "waiting":
                    return str(decided.get("decision") or "no")
                time.sleep(0.5)
            return "no"
        except Exception as error:
            logging.getLogger(__name__).warning(
                "the service could not be asked about %s for %s: %s", host, workspace, error
            )
            return "no"
        finally:
            client.close()

    async def ask_host(workspace: str, host: str) -> str:
        return await anyio.to_thread.run_sync(host_wanted, workspace, host)

    threading.Thread(target=follow, args=(routes, fetch, stop), name="routes", daemon=True).start()
    log = TrafficLog(home.logs / "traffic", settings.record_limit_kib, settings.keep_days) if settings.records else None
    notion = notion_forwarder(lambda: Client.connect(home, name="agent"))
    flows = flows_forwarder(lambda: Client.connect(home, name="agent"))
    agents = agents_forwarder(lambda: Client.connect(home, name="agent"))
    holds = Holds(file=home.state / HOLDS_FILE)  # the pauses outlive a restart (design 0012 §9.4)
    marks = LocalMarks(home.state / MARKS_FILE)  # so do the sessions kept from the cloud (design 0016 §10)
    spool = Spool(home.state)  # and the cloud requests the service has not taken yet (design 0016 §12)
    routes.followed = True  # what the service says now decides a cloud request (design 0016 §9)
    local = local_token(home)
    proxy = Proxy(  # the agent's way to the internet (design 0024 §2), by the routes' allowances
        hosts=routes.hosts_of,
        token_of=lambda workspace: network_token(local, workspace),
        log=NetworkLog(home.logs / "network", settings.network_days),
        ask=ask_host,
    )
    app = create_gateway(
        routes,
        settings,
        log,
        wake,
        notion,
        flows,
        holds,
        local,
        ask_cloud=ask_cloud,
        marks=marks,
        spool=spool,
        agents=agents,
        proxy=proxy,
        port=port,
        proxy_socket=listening.proxy if listening is not None else None,
    )
    from clank.kernel.accepting import keep_accepting
    from clank.kernel.service import server_config

    keep_accepting()  # a client dropped while it is accepted never closes the gateway's socket (Windows)
    made = listening.made if listening is not None else []
    try:
        Serving(server_config(app, "127.0.0.1", port), made).run(sockets=listening.served if listening else None)
    finally:
        remove_sockets(made)  # when it ended without Uvicorn's stop (its start failed); else removed already
        stop.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
