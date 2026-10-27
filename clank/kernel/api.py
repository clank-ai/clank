"""The Clank API: HTTP and JSON under `/api/v1/`, and the one event stream (design 0002 §2.14, decisions 0016, 0017).

Every route needs the local token (`Authorization: Bearer <token>`), reads included; a request addressed to a host name
other than the service's own is refused (a defense against DNS rebinding), and no CORS header is ever sent, so a web
page elsewhere cannot read an answer (design 0002 §2.7). Every route declares its access level through `requires`, and
a test fails when one does not. Errors have one shape: `{"error": {"code", "message", "where"}}`, with the record as it
is now when a change was refused over a stale version. Every kind of record has the same routes: list and read, and
for settings also change and delete, through the kind's own rules; state changes only through its part's own routes.

The event stream (`GET /api/v1/events`) first says `connected` (the client is now subscribed), then sends the kept
events after the one the client last saw, then each new one as it happens; whenever a client joins or leaves, every
client following it hears who is connected (`service.clients`, a live event). A notification of a kept event only
wakes the stream, which then reads what is new from the database in id order: commits are serialized, but the
notifications of two threads may arrive in either order, and reading from the database is what guarantees no gap and
no repeat. A client behind the pruned history, or too slow to keep up, is told to reload (`reset`). Live-only events
(an operation's log lines, who is connected) are sent as they come. When the service stops, every stream says
`closing` and ends (`end_streams`), so its client knows the service is going and no response is left open for the
server to cut.
"""

import json
import os
import secrets
import threading
from collections.abc import AsyncGenerator, AsyncIterator, Awaitable, Callable, Coroutine, Sequence
from contextlib import asynccontextmanager
from datetime import datetime
from itertools import count
from typing import Annotated, Any, Literal

import anyio
import anyio.from_thread
import anyio.lowlevel
from fastapi import APIRouter, Depends, FastAPI, Query, Request, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response

from clank import __version__
from clank.kernel.access import CLIENT_HEADER, client_actor
from clank.kernel.clock import to_text
from clank.kernel.core import Kernel
from clank.kernel.events import CLANK, Event, Subject
from clank.kernel.operations import Busy, OperationError
from clank.kernel.questions import QuestionError
from clank.kernel.records import RegistryError, Settings
from clank.kernel.settings import Loaded, SettingsError

PREFIX = "/api/v1"
KEEPALIVE_SECONDS = 15
BATCH = 500
Access = Literal["control"]
Background = Callable[[], Coroutine[Any, Any, None]]
# How many records a page may hold: a list route refuses more, so no request can ask for everything at once.
PageSize = Annotated[int, Query(ge=1, le=1000, description="How many to return, 1 to 1000.")]


class ApiError(Exception):
    """An error answered in the API's one shape."""

    def __init__(self, status: int, code: str, message: str, **extra: Any) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.extra = extra


SCHEMES: dict[str, HTTPBearer] = {
    "control": HTTPBearer(
        scheme_name="control",
        description="The local token, CLANK_HOME/state/local.token: the user's own clients on this machine.",
        auto_error=False,
    )
}


def requires(level: Access) -> Any:
    """The dependency that admits only callers holding the token of an access level (design 0002 §2.7).

    It is a security dependency, so every route's access level appears in the API's own description (OpenAPI), where
    the tests and `docs/API.md` read it.
    """
    scheme = SCHEMES[level]

    def check(request: Request, credentials: Annotated[HTTPAuthorizationCredentials | None, Security(scheme)]) -> None:
        given = credentials.credentials if credentials is not None else ""
        if not secrets.compare_digest(given.encode(), str(request.app.state.token).encode()):
            raise ApiError(401, "unauthorized", "a call to the Clank API needs the local token (state/local.token)")

    return Depends(check)


class Change(BaseModel):
    """A settings record's new values, and the revision they were based on."""

    values: dict[str, Any]
    base: str | None = None


class AnswerIn(BaseModel):
    """An answer to a question: an option, or words."""

    option: str | None = None
    text: str = ""


def create_app(
    kernel: Kernel,
    *,
    token: str,
    port: int,
    stop: Callable[[], None] = lambda: None,
    background: Sequence[Background] = (),
    started: datetime | None = None,
) -> FastAPI:
    """The API application over a kernel; while it runs, operations run, and so does every background task."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await kernel.operations.recover()
        async with kernel.operations.running(), anyio.create_task_group() as group:
            for task in background:
                group.start_soon(task)
            yield
            group.cancel_scope.cancel()

    app = FastAPI(
        title="Clank API", version=__version__, docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
    )
    app.state.kernel = kernel
    app.state.token = token
    app.state.url = f"http://127.0.0.1:{port}"
    app.state.started = started or kernel.clock.now()
    app.state.streams = {}
    app.state.closers = set()
    app.state.presence = {}
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    @app.middleware("http")
    async def only_this_host(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        if request.headers.get("host", "") not in hosts:
            return _error(421, "wrong_host", f"this service answers only to {', '.join(sorted(hosts))}")
        return await call_next(request)

    _handlers(app)
    app.include_router(_routes(kernel, stop))
    for part in kernel.parts.values():
        router = getattr(part, "router", None)
        if router is not None:
            app.include_router(router(), prefix=PREFIX, dependencies=[requires("control")])
    return app


def access_of(operation: dict[str, Any]) -> str | None:
    """The access level an operation of the API's description declares, if any."""
    for requirement in operation.get("security", []):
        for level in requirement:
            return str(level)
    return None


def _error(status: int, code: str, message: str, where: dict[str, Any] | None = None, **extra: Any) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code, "message": message, "where": where or {}, **extra}}, status_code=status
    )


def _handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def api_error(request: Request, error: ApiError) -> JSONResponse:
        return _error(error.status, error.code, str(error), **error.extra)

    @app.exception_handler(SettingsError)
    async def settings_error(request: Request, error: SettingsError) -> JSONResponse:
        current = _settings_view(error.current) if error.current is not None else None
        return _error(409, "refused", str(error), current=current)

    @app.exception_handler(QuestionError)
    async def question_error(request: Request, error: QuestionError) -> JSONResponse:
        missing = str(error).startswith("there is no")
        return _error(404 if missing else 409, "not_found" if missing else "refused", str(error))

    @app.exception_handler(OperationError)
    async def operation_error(request: Request, error: OperationError) -> JSONResponse:
        missing = str(error).startswith("there is no")
        code = "busy" if isinstance(error, Busy) else "not_found" if missing else "refused"
        return _error(404 if missing else 409, code, str(error))

    @app.exception_handler(RegistryError)
    async def registry_error(request: Request, error: RegistryError) -> JSONResponse:
        return _error(404, "unknown_kind", str(error))

    @app.exception_handler(RequestValidationError)
    async def invalid(request: Request, error: RequestValidationError) -> JSONResponse:
        fields = [".".join(str(part) for part in e["loc"]) for e in error.errors()]
        said = [  # each field by its name (where it came from left out) and why, as Pydantic says it
            f"{'.'.join(str(part) for part in e['loc'] if part not in ('query', 'body', 'path')) or 'the body'}: "
            f"{str(e['msg'])[:1].lower()}{str(e['msg'])[1:]}"
            for e in error.errors()
        ]
        message = "the request is not what this route takes: " + "; ".join(said)
        return _error(422, "invalid", message, {"fields": fields})

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, error: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if error.status_code == 404 else "http_error"
        return _error(error.status_code, code, str(error.detail))


def _routes(kernel: Kernel, stop: Callable[[], None]) -> APIRouter:
    router = APIRouter(prefix=PREFIX, dependencies=[requires("control")])

    def actor(request: Request) -> Any:
        return client_actor(request.headers.get(CLIENT_HEADER))

    @router.get("/service")
    def service(request: Request) -> dict[str, Any]:
        """The service: its version, its address and process, since when it runs, and the clients that follow it."""
        state = request.app.state
        return {
            "version": __version__,
            "url": state.url,
            "pid": os.getpid(),
            "started": to_text(state.started),
            "clients": sorted(state.streams.values()),
            "presence": {client: to_text(moment) for client, moment in state.presence.items()},
        }

    @router.post("/service/stop")
    def stop_service() -> dict[str, Any]:
        """Stop the service; what runs in the data plane is left running."""
        stop()
        return {"stopping": True}

    @router.get("/kinds")
    def kinds() -> list[dict[str, Any]]:
        """Every kind of record: its label and help, whether it is settings or state, and its schema."""
        return [_kind_view(kind) for kind in kernel.kinds.all()]

    @router.get("/records/{kind}")
    def records(kind: str) -> list[dict[str, Any]]:
        """Every record of a kind (the newest ones, for state)."""
        found = kernel.kinds.get(kind)
        if issubclass(found, Settings):
            return [_settings_view(loaded) for loaded in kernel.settings.records(kind)]
        return [_state_view(kind, record) for record in _state_list(kernel, kind)]

    @router.get("/records/{kind}/{id:path}")
    def record(kind: str, id: str) -> dict[str, Any]:
        """One record."""
        found = kernel.kinds.get(kind)
        if issubclass(found, Settings):
            return _settings_view(kernel.settings.get(kind, id))
        return _state_view(kind, _state_get(kernel, kind, id))

    @router.put("/records/{kind}/{id:path}")
    def write_record(kind: str, id: str, change: Change, request: Request) -> dict[str, Any]:
        """Change a settings record, if `base` is the revision it is at now."""
        _settings_only(kernel, kind)
        return _settings_view(kernel.settings.write(kind, id, change.values, base=change.base, actor=actor(request)))

    @router.delete("/records/{kind}/{id:path}")
    def delete_record(kind: str, id: str, base: str, request: Request) -> dict[str, Any]:
        """Remove the user's file of a settings record; Clank's own, if any, comes back."""
        _settings_only(kernel, kind)
        kernel.settings.delete(kind, id, base=base, actor=actor(request))
        return {"deleted": True}

    @router.get("/history")
    def history(before: int | None = None, limit: PageSize = 50, types: str | None = None) -> list[dict[str, Any]]:
        """The newest kept events, newest first, a page at a time."""
        names = [name for name in (types or "").split(",") if name] or None
        return [event.model_dump(mode="json") for event in kernel.events.latest(limit, before=before, types=names)]

    @router.get("/events")
    async def events(
        request: Request,
        after: int | None = None,
        types: str | None = None,
        subject_kind: str | None = None,
        subject_id: str | None = None,
        follow: bool = True,
    ) -> StreamingResponse:
        """The event stream: what happened after the event `after` (or Last-Event-ID), then what happens."""
        last = request.headers.get("last-event-id", "")
        if after is None and last.isdigit():
            after = int(last)
        subject = Subject(kind=subject_kind, id=subject_id) if subject_kind and subject_id else None
        names = [name for name in (types or "").split(",") if name] or None
        client = actor(request).via
        streams: dict[int, str] = request.app.state.streams
        closers: set[Callable[[], None]] = request.app.state.closers

        async def body() -> AsyncIterator[str]:
            key = next(_stream_numbers)
            streams[key] = client
            announced = False
            try:
                async for chunk in event_stream(
                    kernel, after=after, types=names, subject=subject, follow=follow, closers=closers
                ):
                    yield chunk
                    if not announced:  # the first chunk says this stream is subscribed, so it hears itself join
                        announced = True
                        _announce(kernel, streams)
            finally:
                streams.pop(key, None)
                _announce(kernel, streams)

        return StreamingResponse(body(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    @router.get("/questions")
    def questions(status: str | None = "waiting") -> list[dict[str, Any]]:
        """The questions of a status (waiting, unless asked otherwise), oldest first for waiting ones."""
        found = kernel.questions.waiting() if status == "waiting" else kernel.questions.find(status)
        return [question.model_dump(mode="json") for question in found]

    @router.post("/questions/{id}/answer")
    def answer(id: str, given: AnswerIn, request: Request) -> dict[str, Any]:
        """Answer a question, once; the answer records this client."""
        answered = kernel.questions.answer(id, by=actor(request), option=given.option, text=given.text)
        return answered.model_dump(mode="json")

    @router.get("/operations")
    def operations(status: str | None = None, limit: PageSize = 50) -> list[dict[str, Any]]:
        """The newest operations, optionally of one status."""
        return [operation.model_dump(mode="json") for operation in kernel.operations.find(status, limit)]

    @router.get("/operations/{id}/log")
    def operation_log(id: str, after: int = 0) -> list[dict[str, Any]]:
        """An operation's log, from the line after `after` on."""
        return [line.model_dump(mode="json") for line in kernel.operations.log_lines(id, after)]

    @router.post("/operations/{id}/cancel")
    async def cancel(id: str, request: Request) -> dict[str, Any]:
        """Ask a running operation to stop at its next check."""
        return (await kernel.operations.cancel(id, actor=actor(request))).model_dump(mode="json")

    @router.post("/operations/{id}/retry")
    async def retry(id: str, request: Request) -> dict[str, Any]:
        """Start an interrupted or failed operation again, when that is safe."""
        return (await kernel.operations.retry(id, actor=actor(request))).model_dump(mode="json")

    @router.post("/presence")
    def presence(request: Request) -> dict[str, Any]:
        """Say that the user is active in this client (at most once a minute)."""
        request.app.state.presence[actor(request).via] = kernel.clock.now()
        return {}

    @router.get("/openapi.json")
    def openapi(request: Request) -> dict[str, Any]:
        """The API's own description (OpenAPI)."""
        description: dict[str, Any] = request.app.openapi()
        return description

    return router


_stream_numbers = count(1)


async def event_stream(
    kernel: Kernel,
    *,
    after: int | None,
    types: Sequence[str] | None = None,
    subject: Subject | None = None,
    follow: bool = True,
    closers: set[Callable[[], None]] | None = None,
) -> AsyncGenerator[str, None]:
    """The event stream's text: the kept events after `after` (none if it is None), then, if `follow`, each new one
    until the stream is closed: while it is open, `closers` holds the function that closes it."""
    send, receive = anyio.create_memory_object_stream[Event | None](max_buffer_size=1000)
    token = anyio.lowlevel.current_token()
    loop = threading.get_ident()
    overflow = threading.Event()
    closing = threading.Event()

    def deliver(item: Event | None) -> None:
        try:
            if threading.get_ident() == loop:
                send.send_nowait(item)
            else:
                anyio.from_thread.run_sync(send.send_nowait, item, token=token)
        except anyio.WouldBlock:
            overflow.set()
        except (anyio.ClosedResourceError, anyio.BrokenResourceError, RuntimeError):
            pass

    def wake(event: Event) -> None:
        if _matches(event, types, subject):
            deliver(event if event.id is None else None)

    def close() -> None:
        closing.set()
        deliver(None)

    stop = kernel.events.subscribe(wake)
    if closers is not None:
        closers.add(close)
    try:
        yield _sse("connected", {})
        seen = kernel.events.last_id() if after is None else after
        if after is not None and kernel.events.missed(after):
            yield _sse("reset", {"reason": "events after the one you last saw were pruned; reload what you show"})
            seen = kernel.events.last_id()
        while True:
            batch = kernel.events.after(seen, types=types, subject=subject, limit=BATCH)
            for event in batch:
                yield _sse_event(event)
                seen = event.id or seen
            if len(batch) < BATCH:
                break
        if not follow:
            return
        while True:
            with anyio.move_on_after(KEEPALIVE_SECONDS) as idle:
                item = await receive.receive()
            if closing.is_set():
                yield _sse("closing", {"reason": "the service is stopping"})
                return
            if idle.cancelled_caught:  # spelling: keep (AnyIO's own name)
                yield ": keepalive\n\n"
                continue
            if overflow.is_set():
                yield _sse("reset", {"reason": "this client fell behind; reload what you show"})
                return
            if item is not None:
                yield _sse_event(item)
                continue
            while True:
                batch = kernel.events.after(seen, types=types, subject=subject, limit=BATCH)
                for event in batch:
                    yield _sse_event(event)
                    seen = event.id or seen
                if len(batch) < BATCH:
                    break
    finally:
        if closers is not None:
            closers.discard(close)
        stop()
        send.close()
        receive.close()


def end_streams(app: FastAPI) -> None:
    """Close every event stream of the API: each says `closing` to its client and ends. The server calls this when it
    stops, before it waits for the responses still open."""
    for close in list(app.state.closers):
        close()


def _announce(kernel: Kernel, streams: dict[int, str]) -> None:
    clients = sorted(streams.values())
    kernel.events.publish_live(
        "service.clients",
        summary=f"clients following: {', '.join(clients) or 'none'}",
        actor=CLANK,
        data={"clients": clients},
    )


def _matches(event: Event, types: Sequence[str] | None, subject: Subject | None) -> bool:
    return (types is None or event.type in types) and (subject is None or event.subject == subject)


def _sse(name: str, data: dict[str, Any]) -> str:
    return f"event: {name}\ndata: {json.dumps(data)}\n\n"


def _sse_event(event: Event) -> str:
    head = f"id: {event.id}\n" if event.id is not None else ""
    return f"{head}event: {event.type}\ndata: {event.model_dump_json()}\n\n"


def _kind_view(kind: type[Any]) -> dict[str, Any]:
    settings = issubclass(kind, Settings)
    return {
        "kind": kind.KIND,
        "label": kind.LABEL,
        "help": kind.HELP,
        "sort": "settings" if settings else "state",
        "single": bool(getattr(kind, "SINGLE", False)),
        "on_change": getattr(kind, "ON_CHANGE", None),
        "applies": kind.applies() if settings else None,
        "version": getattr(kind, "VERSION", None),
        "defined_in": f"{kind.__module__}.{kind.__qualname__}",
        "schema": kind.model_json_schema(),
    }


def _settings_view(loaded: Loaded) -> dict[str, Any]:
    return {
        "kind": loaded.kind,
        "id": loaded.id,
        "title": loaded.record.title or loaded.id,
        "source": loaded.source,
        "revision": loaded.revision,
        "file": str(loaded.path) if loaded.path else None,
        "user_file": str(loaded.user_file),
        "values": loaded.record.model_dump(mode="json"),
    }


def _state_view(kind: str, record: Any) -> dict[str, Any]:
    title = getattr(record, "title", None) or getattr(record, "summary", "")
    return {"kind": kind, "id": str(record.id), "title": title, "values": record.model_dump(mode="json")}


def _settings_only(kernel: Kernel, kind: str) -> None:
    if not issubclass(kernel.kinds.get(kind), Settings):
        raise ApiError(405, "refused", f"{kind} is state: it changes only through its own actions, never directly")


def _state_list(kernel: Kernel, kind: str) -> list[Any]:
    if kind == "event":
        return list(kernel.events.latest(100))
    if kind == "question":
        return list(kernel.questions.find())
    if kind == "operation":
        return list(kernel.operations.find())
    for part in kernel.parts.values():  # a component reads its own state kinds (design 0002 §2.2)
        reader = getattr(part, "read_records", None)
        if reader is not None and (found := reader(kind)) is not None:
            return list(found)
    raise ApiError(404, "not_found", f"no reader is declared for the kind {kind}")


def _state_get(kernel: Kernel, kind: str, id: str) -> Any:
    if kind == "event":
        found = kernel.events.after(int(id) - 1, limit=1) if id.isdigit() else []
        if not found or found[0].id != int(id):
            raise ApiError(404, "not_found", f"there is no event {id}")
        return found[0]
    if kind == "question":
        return kernel.questions.get(id)
    if kind == "operation":
        return kernel.operations.get(id)
    for part in kernel.parts.values():
        reader = getattr(part, "read_record", None)
        if reader is None:
            continue
        try:
            found = reader(kind, id)
        except KeyError as error:
            raise ApiError(404, "not_found", str(error.args[0])) from error
        if found is not None:
            return found
    raise ApiError(404, "not_found", f"no reader is declared for the kind {kind}")
