"""Completion in the gateway (design 0006 §4): llama.cpp's fill in the middle, `POST /v1/infill`, for the role a request
names as its model (`completion`, the fast slot's, by default).

The request goes to the role's engine with its fields as they came, but for the model, and with the time limits a
completion needs (`LIMITS`, unless it sets its own): a late completion is worth nothing. The newest wins: a completion
is worth something only until the next keystroke, so when a new one comes for a role, the one in flight is broken off
(its connection to the engine closed, which stops the engine on it) and its client answered with an empty completion
(`BROKEN`). A completion is never held while its slot starts or switches, and never kept in the records of the agent's
requests: completions come at typing speed. The gateway keeps the last `KEPT` in memory instead, each with its outcome
and times, and `GET /completion` gives them with their median and 95th percentile, for the console's Completion page.
Everything here runs on the gateway's event loop, so nothing is locked.
"""

import statistics
import time
from collections import deque
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import anyio
import httpx2
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from clank.components.gateway.routing import Routes
from clank.kernel.clock import to_text

LIMITS = {"t_max_prompt_ms": 2000, "t_max_predict_ms": 1500}
KEPT = 200
ROLE = "completion"
BROKEN = {"content": "", "stop": True, "broken_off": "a newer completion came"}


class Completions:
    """The completion in flight for each role, and the last ones that ended."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._flying: dict[str, anyio.CancelScope] = {}
        self._kept: deque[dict[str, Any]] = deque(maxlen=KEPT)

    def newest(self, role: str) -> anyio.CancelScope:
        """A scope for a new completion of a role; the one in flight for it, if any, is broken off."""
        old = self._flying.get(role)
        if old is not None:
            old.cancel()
        scope = anyio.CancelScope()
        self._flying[role] = scope
        return scope

    def ended(self, role: str, scope: anyio.CancelScope, entry: dict[str, Any]) -> None:
        """A completion ended: kept, and no longer in flight."""
        if self._flying.get(role) is scope:
            del self._flying[role]
        self.keep(entry)

    def keep(self, entry: dict[str, Any]) -> None:
        """Keep a completion that ended, with when (seconds since the epoch, for the counts by minute and hour)."""
        self._kept.appendleft({**entry, "at": self._clock()})

    def view(self) -> dict[str, Any]:
        """The last completions, newest first, and what they add up to: how many, how many broken off by newer ones,
        failed or refused, how many in the last minute and hour, and the median and 95th percentile of the time to an
        answer."""
        kept = list(self._kept)
        now = self._clock()
        times = sorted(entry["total_ms"] for entry in kept if entry["outcome"] == "answered")
        return {
            "count": len(kept),
            "broken_off": sum(entry["outcome"] == "broken off" for entry in kept),
            "failed": sum(entry["outcome"] == "failed" for entry in kept),
            "refused": sum(entry["outcome"] == "refused" for entry in kept),
            "last_minute": sum(now - entry["at"] < 60 for entry in kept),
            "last_hour": sum(now - entry["at"] < 3600 for entry in kept),
            "median_ms": statistics.median(times) if times else None,
            "p95_ms": times[min(len(times) - 1, round(0.95 * (len(times) - 1)))] if times else None,
            "recent": [{key: value for key, value in entry.items() if key != "at"} for entry in kept],
        }


def add_routes(
    app: FastAPI,
    routes: Routes,
    client: Callable[[], httpx2.AsyncClient],
    the_service: Callable[[Request], Response | None] | None = None,
) -> Completions:
    """`POST /v1/infill` and `GET /completion` on the gateway's application; its completions. `GET /completion` answers
    only the service (`the_service`: its refusal of anyone else, design 0015 §10)."""
    completions = Completions()

    @app.get("/completion")
    async def counted(request: Request) -> Response:
        refused = the_service(request) if the_service is not None else None
        return refused or JSONResponse(completions.view())

    @app.post("/v1/infill")
    async def infill(request: Request) -> Response:
        began = time.perf_counter()
        entry: dict[str, Any] = {"time": to_text(datetime.now(UTC)), "role": ROLE}
        try:
            body = await request.json()
        except ValueError:
            body = None
        if not isinstance(body, dict):
            return _refused(completions, entry, began, 400, "invalid_request", "the request is not a JSON object")
        role = entry["role"] = str(body.get("model") or ROLE)
        route, why = await routes.ready(role, 0)
        if route is None:
            return _refused(completions, entry, began, 503, "no_engine", why)
        sent = {key: value for key, value in body.items() if key != "model"}
        for key, value in LIMITS.items():
            sent.setdefault(key, value)
        entry.update(slot=route.slot, engine=f"{route.engine} {route.version}")
        scope = completions.newest(role)
        answer: httpx2.Response | None = None
        error = ""
        with scope:
            try:
                answer = await client().post(f"http://127.0.0.1:{route.port}/infill", json=sent)
            except httpx2.HTTPError as failed:
                error = f"the engine did not answer: {failed}"
        entry["total_ms"] = round((time.perf_counter() - began) * 1000, 1)
        if scope.cancelled_caught:  # spelling: keep (AnyIO's own name)
            completions.ended(role, scope, {**entry, "outcome": "broken off"})
            return JSONResponse(BROKEN)
        if answer is None or answer.status_code != 200:
            said = error or f"the engine answered {answer.status_code if answer else 'nothing'}"
            completions.ended(role, scope, {**entry, "outcome": "failed", "error": said[:300]})
            if answer is None:
                return JSONResponse({"error": {"message": said, "type": "engine_unreachable"}}, status_code=502)
            kind = answer.headers.get("content-type", "application/json")
            return Response(answer.content, status_code=answer.status_code, media_type=kind)
        found = _json(answer)
        timings = found.get("timings") or {}
        completions.ended(role, scope, {
            **entry, "outcome": "answered", "chars": len(str(found.get("content") or "")),
            "prompt_n": timings.get("prompt_n"), "prompt_ms": timings.get("prompt_ms"),
            "predicted_n": timings.get("predicted_n"), "predicted_ms": timings.get("predicted_ms"),
        })  # fmt: skip
        return Response(answer.content, media_type=answer.headers.get("content-type", "application/json"))

    return completions


def _refused(
    completions: Completions, entry: dict[str, Any], began: float, status: int, code: str, message: str
) -> JSONResponse:
    total = round((time.perf_counter() - began) * 1000, 1)
    completions.keep({**entry, "outcome": "refused", "total_ms": total, "error": message})
    return JSONResponse({"error": {"message": message, "type": code, "code": code}}, status_code=status)


def _json(answer: httpx2.Response) -> dict[str, Any]:
    try:
        found = answer.json()
    except ValueError:
        return {}
    return found if isinstance(found, dict) else {}
