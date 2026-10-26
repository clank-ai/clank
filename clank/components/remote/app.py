"""The phone's listener (design 0005 §4): its own FastAPI app, apart from the service's API, answering only the phone
page and its routes.

Every request must come through Tailscale's `serve`, from the tailnet: the connection from this machine's loopback,
Tailscale's verified login in its header, and that login this computer's own user's; a request Funnel brought from the
internet is refused. But for the page itself and pairing, it must carry a paired device's token (the cookie the page
keeps after pairing): the login is the first factor, the device the second. Every action carries the header
`X-Clank-Phone`, which a page from elsewhere cannot send without asking first, and this app never says yes, so another
site cannot act through the owner's browser. What a device does is recorded as that device (`Actor(kind="device")`).
"""

import json
import time
from importlib import resources
from typing import TYPE_CHECKING, Any

import anyio.to_thread
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from clank.components.remote.devices import TTL_DAYS, PairingError
from clank.components.remote.flowsapi import flow_routes
from clank.components.remote.icon import icon_png
from clank.components.remote.stream import phone_stream
from clank.kernel.events import Actor

if TYPE_CHECKING:
    from clank.components.remote.service import Remote

COOKIE = "clank_device"
STREAM_PATH = "/api/stream"  # the live stream (design 0025 §3), logged as one line
ACTION_HEADER = "x-clank-phone"
STATIC = {  # the app's files, from the package (design 0025 §1: nothing fetched from elsewhere)
    "app.js": "text/javascript", "model.mjs": "text/javascript", "sw.js": "text/javascript", "style.css": "text/css",
    "icon.svg": "image/svg+xml",
}  # fmt: skip
CONTENT_POLICY = (
    "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
)


class PairBody(BaseModel):
    """The code typed on the device, and a name for it."""

    code: str = Field(min_length=4, max_length=20)


class TextBody(BaseModel):
    """A message for the agent."""

    text: str = Field(max_length=20000)


class ReplyBody(BaseModel):
    """A reply to what the agent asked to do: once, always or reject."""

    reply: str


class AnswersBody(BaseModel):
    """Answers to the agent's question: for each of its questions, the options chosen or a text."""

    answers: list[list[str]]


class OptionBody(BaseModel):
    """The option chosen for one of Clank's questions, and the words that go with it (a gate's note, design 0013
    §10)."""

    option: str
    text: str = Field("", max_length=20000)


class SeenBody(BaseModel):
    """Marks of the Monitor's Watch for seen on the phone, by their ids (design 0012 §8)."""

    ids: list[str] = Field(max_length=200)


def page(name: str) -> bytes:
    """One of the page's files, from Clank's package."""
    return resources.files("clank.components.remote").joinpath("page", name).read_bytes()


def create_phone_app(remote: "Remote") -> FastAPI:
    """The phone's app, over the remote component's part."""
    from clank.components.agents.service import AgentError, SessionError
    from clank.components.workspaces.service import WorkspaceUnavailable

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    kernel = remote.kernel

    def login_of(request: Request) -> str:
        """The verified Tailscale login of this computer's own user, or refused."""
        if request.client is None or request.client.host not in ("127.0.0.1", "::1"):
            raise HTTPException(403, "this page answers only through Tailscale")
        if "tailscale-funnel-request" in request.headers:
            raise HTTPException(403, "this page answers only on the tailnet, never from the internet")
        login = request.headers.get("tailscale-user-login", "").strip().lower()
        owner = remote.owner_login()
        if not login or not owner or login != owner:
            raise HTTPException(403, "this page answers only to this computer's own Tailscale user")
        return login

    def device_of(request: Request) -> Actor:
        """The paired device asking, as the history names it (and the record of the exchange); or refused."""
        found = remote.devices.device(request.cookies.get(COOKIE, ""), login_of(request))
        if found is None:
            raise HTTPException(401, "pair this device first: a code from the computer (Clank's console, F9, p)")
        request.state.device = (found.id, found.name)
        return Actor(kind="device", via=found.name)

    def acting(request: Request) -> Actor:
        """A device acting: paired, and its request carries the action header."""
        if request.headers.get(ACTION_HEADER) != "1":
            raise HTTPException(403, "an action needs the phone page's own header")
        return device_of(request)

    async def bridged(work: Any, *args: Any) -> Any:
        try:
            return await anyio.to_thread.run_sync(work, *args)
        except (SessionError, AgentError, WorkspaceUnavailable) as error:
            raise HTTPException(409, str(error)) from error

    @app.exception_handler(HTTPException)
    async def refused(request: Request, error: HTTPException) -> JSONResponse:
        never_kept = {"Cache-Control": "no-store"}
        return JSONResponse({"error": error.detail}, status_code=error.status_code, headers=never_kept)

    @app.middleware("http")
    async def recorded(request: Request, call_next: Any) -> Response:
        """Keep every exchange, its bodies whole (traffic.py): what a phone asked and what it was sent; the live
        stream (design 0025 §3) as one line, its body never read whole."""
        began, when = time.perf_counter(), kernel.clock.now()
        asked = await request.body()
        response: Response = await call_next(request)
        if request.url.path == STREAM_PATH and response.status_code == 200:
            device = getattr(request.state, "device", None)
            await anyio.to_thread.run_sync(lambda: remote.traffic.record(
                when=when, device=device, method=request.method, path=request.url.path, query=request.url.query,
                status=response.status_code, ms=(time.perf_counter() - began) * 1000, request=asked,
                request_type=request.headers.get("content-type", ""), response=b"(the live stream)",
                response_type="text/event-stream",
            ))  # fmt: skip
            return response
        chunks = [chunk async for chunk in response.body_iterator]  # type: ignore[attr-defined]
        sent = b"".join(chunk if isinstance(chunk, bytes) else str(chunk).encode() for chunk in chunks)
        device = getattr(request.state, "device", None)
        if device is None and request.cookies.get(COOKIE):  # the page itself names no device: its cookie does
            login = request.headers.get("tailscale-user-login", "").strip().lower()
            found = await anyio.to_thread.run_sync(remote.devices.device, request.cookies[COOKIE], login)
            device = (found.id, found.name) if found is not None else None
        await anyio.to_thread.run_sync(lambda: remote.traffic.record(
            when=when, device=device, method=request.method, path=request.url.path, query=request.url.query,
            status=response.status_code, ms=(time.perf_counter() - began) * 1000, request=asked,
            request_type=request.headers.get("content-type", ""), response=sent,
            response_type=response.headers.get("content-type", ""),
        ))  # fmt: skip
        whole = Response(sent, status_code=response.status_code)
        whole.raw_headers = response.raw_headers
        return whole

    @app.middleware("http")
    async def headers(request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["Content-Security-Policy"] = CONTENT_POLICY
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.get("/")
    async def index(request: Request, claim: str = "") -> Response:
        """The app; a first launch from the Home Screen icon trades its install claim for the device's token (design
        0025 §2), once."""
        login = login_of(request)
        response = Response(page("index.html"), media_type="text/html; charset=utf-8")
        if claim:
            traded = await anyio.to_thread.run_sync(remote.devices.claim, claim, login)
            if traded is not None:
                device, token = traded
                request.state.device = (device.id, device.name)
                response.set_cookie(COOKIE, token, max_age=TTL_DAYS * 86400, httponly=True, secure=True,
                                    samesite="strict")  # fmt: skip
        return response

    @app.get("/pair")
    async def pair_by_link(request: Request, code: str = "") -> Response:
        """The pair link opened on the device (design 0025 §2): paired by the code in it, the cookie set, the steps
        to add the app to the Home Screen served, with the install claim in the icon's start link."""
        login = login_of(request)
        try:
            device, token = await anyio.to_thread.run_sync(remote.paired, code, login)
        except PairingError as error:
            raise HTTPException(403, str(error)) from error
        request.state.device = (device.id, device.name)
        claim = await anyio.to_thread.run_sync(remote.devices.install_claim, device.id)
        machine = remote.machine_name()
        text = page("install.html").decode("utf-8").replace("{{claim}}", claim).replace("{{machine}}", machine)
        response = Response(text, media_type="text/html; charset=utf-8")
        response.set_cookie(COOKIE, token, max_age=TTL_DAYS * 86400, httponly=True, secure=True, samesite="strict")
        return response

    @app.get("/icon-180.png")
    async def icon(request: Request) -> Response:
        """The Home Screen icon, drawn here (iOS takes a PNG)."""
        login_of(request)
        return Response(icon_png(180), media_type="image/png", headers={"Cache-Control": "max-age=86400"})

    @app.get("/manifest.webmanifest")
    async def manifest(request: Request, claim: str = "") -> Response:
        """The app's manifest, its start link carrying the device's install claim when there is one."""
        login_of(request)
        found = json.loads(page("manifest.webmanifest"))
        found["start_url"] = f"./?claim={claim}" if claim else "./"
        return Response(json.dumps(found), media_type="application/manifest+json")

    @app.get("/{name}")
    async def static(name: str, request: Request) -> Response:
        login_of(request)
        if name not in STATIC:
            raise HTTPException(404, "not here")
        return Response(page(name), media_type=STATIC[name])

    @app.post("/api/pair")
    async def pair(wanted: PairBody, request: Request) -> Response:
        login = login_of(request)
        if request.headers.get(ACTION_HEADER) != "1":
            raise HTTPException(403, "an action needs the phone page's own header")
        try:
            device, token = await anyio.to_thread.run_sync(remote.paired, wanted.code, login)
        except PairingError as error:
            raise HTTPException(403, str(error)) from error
        request.state.device = (device.id, device.name)
        response = JSONResponse({"device": device.view()})
        response.set_cookie(COOKIE, token, max_age=TTL_DAYS * 86400, httponly=True, secure=True, samesite="strict")
        return response

    @app.get(STREAM_PATH)
    async def stream(request: Request) -> StreamingResponse:
        """The phone's one live stream (design 0025 §3): now, then each event as it is recorded, now again when it
        changed; `Last-Event-ID` resumes."""
        device_of(request)
        given = request.headers.get("last-event-id", "").strip()
        after = int(given) if given.isdigit() else None
        text = phone_stream(remote, after, lambda: _overview(remote, files=False), remote.closers)
        headers = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}
        return StreamingResponse(text, media_type="text/event-stream", headers=headers)

    @app.get("/api/me")
    async def me(request: Request) -> dict[str, Any]:
        device = device_of(request)
        return {"device": device.via, "login": login_of(request)}

    @app.get("/api/overview")
    async def overview(request: Request) -> dict[str, Any]:
        device_of(request)
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: _overview(remote))
        return found

    @app.get("/api/sessions/{workspace}/{port}/{session}")
    async def messages(workspace: str, port: int, session: str, request: Request, limit: int = 40) -> Any:
        device_of(request)
        return await bridged(kernel.parts["agents"].sessions.messages, workspace, port, session, min(limit, 200))

    @app.post("/api/sessions/{workspace}/{port}/{session}/message")
    async def send(workspace: str, port: int, session: str, wanted: TextBody, request: Request) -> Any:
        actor = acting(request)
        sessions = kernel.parts["agents"].sessions
        await bridged(lambda: sessions.send(workspace, port, session, wanted.text, actor=actor))
        return {"sent": True}

    @app.post("/api/sessions/{workspace}/start")
    async def start(workspace: str, wanted: TextBody, request: Request) -> Any:
        actor = acting(request)
        agents = kernel.parts["agents"]
        env = await bridged(agents.configure, workspace)
        title = "From the phone: " + " ".join(wanted.text.split())[:50]
        return await bridged(lambda: agents.sessions.start(workspace, wanted.text, env=env, actor=actor, title=title))

    @app.post("/api/sessions/{workspace}/{port}/{session}/stop")
    async def stop(workspace: str, port: int, session: str, request: Request) -> Any:
        actor = acting(request)
        await bridged(lambda: kernel.parts["agents"].sessions.stop(workspace, port, session, actor=actor))
        return {"stopped": True}

    @app.post("/api/permissions/{workspace}/{port}/{permission}")
    async def permission(workspace: str, port: int, permission: str, wanted: ReplyBody, request: Request) -> Any:
        actor = acting(request)
        review = kernel.parts["agents"].review
        await bridged(lambda: review.reply(workspace, port, permission, wanted.reply, actor=actor))
        return {"replied": True}

    @app.post("/api/questions/{workspace}/{port}/{question}")
    async def question(workspace: str, port: int, question: str, wanted: AnswersBody, request: Request) -> Any:
        actor = acting(request)
        sessions = kernel.parts["agents"].sessions
        await bridged(lambda: sessions.question(workspace, port, question, wanted.answers, actor=actor))
        return {"replied": True}

    @app.post("/api/clank-questions/{id}")
    async def answer(id: str, wanted: OptionBody, request: Request) -> Any:
        actor = acting(request)
        words = wanted.text.strip()
        try:
            found = await anyio.to_thread.run_sync(
                lambda: kernel.questions.answer(id, by=actor, option=wanted.option, text=words)
            )
        except Exception as error:  # the kernel says why (answered already, no such option)
            raise HTTPException(409, str(error)) from error
        return {"answered": found.id}

    @app.get("/api/flow-files/{question}/{index}")
    async def flow_file(question: str, index: int, request: Request) -> Any:
        """A file that a question a flow waits for shows, as it stands in the folder now (design 0013 §10): by the
        question and the file's place in its list, never by a path the phone sends."""
        from clank.kernel.api import ApiError

        device_of(request)
        try:
            return await anyio.to_thread.run_sync(kernel.parts["flows"].shown_file, question, index)
        except ApiError as error:
            raise HTTPException(error.status, str(error)) from error

    @app.post("/api/marks/seen")
    async def marks_seen(wanted: SeenBody, request: Request) -> Any:
        """Marks of the Monitor's Watch for seen on the phone: they leave its list of what waits (design 0012 §8)."""
        actor = acting(request)
        marks = kernel.parts["agents"].marks
        return {"seen": await anyio.to_thread.run_sync(lambda: marks.seen(wanted.ids, actor=actor))}

    @app.get("/api/traffic")
    async def traffic(request: Request, limit: int = 200) -> dict[str, Any]:
        """What this device and the computer exchanged, newest first (each without its bodies)."""
        device_of(request)
        mine = request.state.device[0]
        return {"exchanges": await anyio.to_thread.run_sync(remote.traffic.recent, mine, max(1, min(limit, 1000)))}

    @app.get("/api/traffic/{id}")
    async def exchange(id: str, request: Request) -> dict[str, Any]:
        """One exchange of this device whole: what it asked, and what it was sent."""
        device_of(request)
        found = await anyio.to_thread.run_sync(remote.traffic.exchange, id)
        if found is None or found["device"] != request.state.device[0]:
            raise HTTPException(404, "no such exchange of this device")
        return found

    @app.get("/api/files")
    async def files(request: Request) -> dict[str, Any]:
        device_of(request)
        return {"files": await anyio.to_thread.run_sync(remote.files)}

    @app.get("/api/files/{workspace}/{name}")
    async def file(workspace: str, name: str, request: Request) -> Response:
        device_of(request)
        path = await anyio.to_thread.run_sync(remote.file_path, workspace, name)
        if path is None:
            raise HTTPException(404, "no such file was sent")
        return FileResponse(path)

    @app.post("/api/signout")
    async def signout(request: Request) -> Response:
        actor = acting(request)
        token = request.cookies.get(COOKIE, "")
        found = remote.devices.device(token, login_of(request))
        if found is not None:
            await anyio.to_thread.run_sync(lambda: remote.revoke(found.id, actor=actor))
        response = JSONResponse({"signed_out": True})
        response.delete_cookie(COOKIE)
        return response

    app.include_router(flow_routes(kernel, device_of, acting), prefix="/api")  # the Flows tab's (design 0025 §6)
    return app


def _shown(mark: dict[str, Any], asks: set[str]) -> bool:
    """Whether the page shows a mark's ask already in OpenCode's own box (a permission by its id, a question by its
    session), so one ask is not listed twice."""
    kind, _, id = str(mark.get("key") or "").partition(":")
    if kind in ("ask", "stopped"):
        return f"ask:{id}" in asks
    return kind == "question" and f"question:{mark.get('session')}" in asks


def _flow_shown(view: dict[str, Any]) -> dict[str, Any]:
    """What the phone is told of a question about a flow: its flow, run and box, the files it shows (by their place in
    the folder, the box that wrote each, its tries), the answers that take words; not this computer's own paths."""
    kept = ("flow", "title", "run", "box", "box_title", "type", "kind", "notes")
    files = [{key: file[key] for key in ("path", "box", "tries", "exists")} for file in view["files"]]
    return {**{key: view[key] for key in kept if key in view}, "files": files}


def _overview(remote: "Remote", files: bool = True) -> dict[str, Any]:
    """What the phone shows first: the model, what the agent's model does now (the gateway's requests in flight and the
    last one), the machine (its CPU, memory and GPU, as last read), each workspace (the running ones first) with its
    agents' sessions and what waits (a change waiting for review only as Clank's question), Clank's questions waiting
    (one about a flow with what it shows, design 0013 §10), the Monitor's marks told to the phone and not seen yet
    (design 0012 §8; one of an ask the page shows in OpenCode's own box is not listed again), and the newest files
    sent."""
    from clank.components.agents.service import SessionError

    kernel = remote.kernel
    runtime = kernel.parts["runtime"]
    slots = runtime.state.slots(runtime.settings().slots)
    main = next((slot for slot in slots if slot.name == "main"), None)
    model = {
        "status": main.status if main else "unknown", "preset": (main.preset or "") if main else "",
        "title": runtime.title(main.preset) if main and main.preset else "",
    }  # fmt: skip
    doing = kernel.parts["gateway"].activity()
    agent = {"state": doing["state"], "requests": doing["requests"], "served": doing["served"], "last": doing["last"]}
    samples = kernel.parts["machine"].meters()
    machine = None
    if samples:
        last = samples[-1]
        gpu = (last.get("gpus") or [None])[0]
        machine = {"cpu": last.get("cpu"), "memory_used": last.get("memory_used"),
                   "memory_total": last.get("memory_total"), "gpu": gpu}  # fmt: skip
    workspaces = []
    agents = kernel.parts["agents"]
    asks: set[str] = set()  # the asks shown in OpenCode's own boxes (or as Clank's question): permissions, questions
    for row in kernel.parts["workspaces"].workspaces():
        shown: dict[str, Any] = {"name": row["name"], "state": row["state"], "servers": [], "problem": ""}
        if row["state"] == "running":
            try:
                shown["servers"] = agents.sessions.servers(row["name"])
            except SessionError as error:
                shown["problem"] = str(error)
        for server in shown["servers"]:  # a change waiting for review shows as Clank's question, with its diff
            asks |= {f"ask:{each['id']}" for each in server["permissions"]}
            asks |= {f"question:{each.get('session')}" for each in server["questions"]}
            server["permissions"] = [each for each in server["permissions"] if not agents.review.questioned(each["id"])]
        workspaces.append(shown)
    workspaces.sort(key=lambda shown: shown["state"] != "running")
    waiting = kernel.questions.waiting()
    flows = kernel.parts["flows"].about(waiting)  # what a question about a flow shows (design 0013 §10)
    questions = [
        {"id": question.id, "title": question.title, "detail": question.detail,
         "options": [{"id": option.id, "label": option.label, "effect": option.effect} for option in question.options],
         **({"flow": _flow_shown(flows[question.id])} if question.id in flows else {})}
        for question in waiting
    ]  # fmt: skip
    told = ("id", "workspace", "session", "title", "rule", "name", "node", "why", "time", "offer", "did")
    marks = [{key: mark[key] for key in told} for mark in agents.marks.phone() if not _shown(mark, asks)]
    found = {"model": model, "agent": agent, "machine": machine, "workspaces": workspaces, "questions": questions,
             "marks": marks}  # fmt: skip
    if files:
        found["files"] = remote.files(limit=30)
    return found
