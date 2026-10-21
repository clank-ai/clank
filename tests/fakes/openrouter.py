"""A fake OpenRouter (design 0016 §18): a FastAPI app served on a free port in a thread, playing an HTTP recording of
OpenRouter's API (`tests/fixtures/openrouter/<date>/http.json`; the documented shapes, `documented`, by default), so
the runtime's and the gateway's tests reach no network and no one's account.

It answers OpenRouter's routes under `/api/v1`: `GET /key` (the key's facts), `GET /models` (the recorded models; only
those that take tool calls when asked `supported_parameters=tools`), `POST /chat/completions` (a whole answer, or a
stream of the recorded lines, comment lines among them) and `GET /generation` (a request's record afterward, once
`generations_ready`). Every route takes only its key, `made-up-openrouter-key` (never one that starts with `sk-`, so
the repository's secrets check passes): any other is refused as the recording's `key refused` says. What a chat request
is answered with is the next of `plays` (an exchange's name: `tool call`, `thinking`, `comments`, `mid-stream error`,
`cut`, `no credits`, `budget`, `no model`, `rate limited`, `no provider`, `key refused`; or `silent`, nothing at all
for `silence` seconds), else `stream` or `answer` as the request asks. `cost` replaces every usage's cost,
`token_seconds` spaces a stream's lines. It keeps every request it was sent (`sent`), its headers too.
"""

import contextlib
import json
import threading
import time
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import anyio
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse

from clank.kernel.service import server_config
from tests.support.served import free_port

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "openrouter"
DOCUMENTED = FIXTURES / "documented" / "http.json"
KEY = "made-up-openrouter-key"


def recordings() -> list[Path]:
    """Every HTTP recording of OpenRouter, the documented shapes first."""
    found = sorted(FIXTURES.glob("*/http.json"))
    return sorted(found, key=lambda path: path.parent.name != "documented")


def recording(path: Path = DOCUMENTED) -> dict[str, Any]:
    """An HTTP recording, read."""
    found: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return found


@dataclass
class Sent:
    """A request the fake was sent."""

    method: str
    path: str
    query: dict[str, str]
    headers: dict[str, str]
    body: Any


@dataclass
class FakeOpenRouter:
    """OpenRouter's API, as a recording has it."""

    played: dict[str, Any] = field(default_factory=recording)
    key: str = KEY
    plays: list[str] = field(default_factory=list)
    cost: float | None = None
    token_seconds: float = 0.0
    silence: float = 30.0
    generations_ready: bool = True
    sent: list[Sent] = field(default_factory=list)
    url: str = ""
    closing: bool = False

    def exchange(self, name: str) -> dict[str, Any]:
        """The recorded exchange of that name."""
        for each in self.played["exchanges"]:
            if each["name"] == name:
                found: dict[str, Any] = each
                return found
        raise KeyError(f"the recording has no exchange named {name!r}")

    def play(self, *names: str) -> None:
        """Answer the next chat requests with these exchanges, in order."""
        self.plays.extend(names)

    def chats(self) -> list[Sent]:
        """The chat requests it was sent."""
        return [each for each in self.sent if each.path.endswith("/chat/completions")]

    def models(self) -> list[dict[str, Any]]:
        """Every model the recording lists."""
        seen: dict[str, dict[str, Any]] = {}
        for each in self.played["exchanges"]:
            body = each["response"].get("body")
            if each["request"]["path"] == "/models" and isinstance(body, dict):
                for model in body.get("data") or []:
                    seen.setdefault(model["id"], model)
        return list(seen.values())

    def app(self) -> FastAPI:
        """Its routes."""
        app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

        async def heard(request: Request) -> JSONResponse | None:
            raw = await request.body()
            body = json.loads(raw) if raw else None
            self.sent.append(
                Sent(request.method, request.url.path, dict(request.query_params), dict(request.headers), body)
            )
            if request.headers.get("authorization") != f"Bearer {self.key}":
                return self._answer("key refused")  # type: ignore[return-value]
            return None

        @app.get("/api/v1/key")
        async def key(request: Request) -> Response:
            return await heard(request) or self._answer("key")

        @app.get("/api/v1/models")
        async def models(request: Request) -> Response:
            refused = await heard(request)
            if refused is not None:
                return refused
            listed = self.models()
            if "tools" in request.query_params.get("supported_parameters", ""):
                listed = [model for model in listed if "tools" in (model.get("supported_parameters") or [])]
            return JSONResponse({"data": listed, "total_count": len(listed), "links": {"next": None}})

        @app.get("/api/v1/generation")
        async def generation(request: Request) -> Response:
            refused = await heard(request)
            if refused is not None:
                return refused
            if not self.generations_ready:
                said = {"error": {"code": 404, "message": "Made-up words: generation not found"}}
                return JSONResponse(said, status_code=404)
            return self._answer("generation")

        @app.post("/api/v1/chat/completions")
        async def chat(request: Request) -> Response:
            refused = await heard(request)
            if refused is not None:
                return refused
            body = self.sent[-1].body or {}
            name = self.plays.pop(0) if self.plays else ("stream" if body.get("stream") else "answer")
            if name == "silent":
                return StreamingResponse(self._silent(), media_type="text/event-stream")
            return self._answer(name)

        return app

    def _answer(self, name: str) -> Response:
        response = self.exchange(name)["response"]
        headers = {key: value for key, value in response["headers"].items() if key != "content-type"}
        if "stream" in response:
            lines = [self._costed(line) for line in response["stream"]]
            return StreamingResponse(self._streamed(lines), status_code=response["status"], headers=headers,
                                     media_type="text/event-stream")  # fmt: skip
        body = response["body"]
        if isinstance(body, dict) and isinstance(body.get("usage"), dict) and self.cost is not None:
            body = {**body, "usage": {**body["usage"], "cost": self.cost}}
        return JSONResponse(body, status_code=response["status"], headers=headers)

    def _costed(self, line: str) -> str:
        if self.cost is None or '"usage"' not in line or not line.startswith("data: {"):
            return line
        event = json.loads(line.removeprefix("data: "))
        event["usage"] = {**event["usage"], "cost": self.cost}
        return "data: " + json.dumps(event, separators=(",", ":"))

    async def _streamed(self, lines: list[str]) -> AsyncIterator[bytes]:
        for line in lines:
            if self.token_seconds:
                await anyio.sleep(self.token_seconds)
            yield (line + "\n\n").encode()

    async def _silent(self) -> AsyncIterator[bytes]:
        ends = time.monotonic() + self.silence
        while time.monotonic() < ends and not self.closing:
            await anyio.sleep(0.05)
        yield b""


@contextlib.contextmanager
def served(fake: FakeOpenRouter | None = None) -> Iterator[FakeOpenRouter]:
    """A fake OpenRouter served for real on a free port; its `url` is its API's base, as OpenRouter's is."""
    fake = fake or FakeOpenRouter()
    port = free_port()
    server = uvicorn.Server(server_config(fake.app(), "127.0.0.1", port))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the fake OpenRouter never started"
        time.sleep(0.01)
    fake.url = f"http://127.0.0.1:{port}/api/v1"
    try:
        yield fake
    finally:
        fake.closing = True
        server.should_exit = True
        thread.join(15)
