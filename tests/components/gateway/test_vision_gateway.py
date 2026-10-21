"""Design 0008 §7, in the gateway's process: a request for a role loaded on demand (the vision model) makes the gateway
ask the service for it first, then wait while it loads, and the request is served; when the service says why not
(vision is off), the request is refused in those words. A role not loaded on demand is never asked for."""

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
import uvicorn

from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.records import TrafficLog
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import create_gateway
from clank.kernel.service import server_config
from tests.components.gateway.test_server import started
from tests.support.served import free_port

ASKED = {"model": "vision", "messages": [{"role": "user", "content": "what does mark 1 circle?"}], "max_tokens": 5}


def table(port: int | None, demand: str) -> dict[str, Any]:
    """The routes: the vision slot stopped (no port) or served by the engine on `port`, its role loaded on demand."""
    slot = {
        "status": "ready" if port else "stopped", "port": port, "engine": "llamacpp" if port else None,
        "version": "b11588" if port else None, "model_name": "qwen3-vl-4b", "preset": "vision", "title": "vision 4B",
        "context": 8192, "output": 512,
    }  # fmt: skip
    return {"slots": {"vision": slot}, "roles": {"vision": "vision"}, "default_slot": "vision",
            "demand": {"vision": demand}}  # fmt: skip


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[int]:
    with started(tmp_path / "engine.log", style="llamacpp") as port:
        yield port


def serve(routes: Routes, tmp_path: Path, asked: list[str], answer: str, port: int) -> Iterator[str]:
    """The gateway, whose service loads the vision model when asked (the routes then serve it), or says why not."""

    async def wake(role: str) -> str:
        asked.append(role)
        if not answer:
            routes.update(table(port, "on-demand"))
        return answer

    listen = free_port()
    app = create_gateway(routes, GatewaySettings(port=listen, hold_seconds=10),
                         TrafficLog(tmp_path / "traffic", 256, 14), wake)  # fmt: skip
    server = uvicorn.Server(server_config(app, "127.0.0.1", listen))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the gateway never started"
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{listen}"
    finally:
        server.should_exit = True
        thread.join(15)


def test_a_request_for_the_vision_model_has_it_loaded_then_is_served(engine: int, tmp_path: Path) -> None:
    routes, asked = Routes(), list[str]()
    routes.update(table(None, "on-demand"))
    for url in serve(routes, tmp_path, asked, "", engine):
        answer = httpx2.post(f"{url}/v1/chat/completions", json=ASKED, timeout=60)
        assert answer.status_code == 200, answer.text
    assert asked == ["vision"]


def test_with_vision_off_the_request_is_refused_saying_how_to_turn_it_on(engine: int, tmp_path: Path) -> None:
    routes, asked = Routes(), list[str]()
    routes.update(table(None, "off"))
    refusal = "the vision model is off: the console's F8 page turns it on (v)"
    for url in serve(routes, tmp_path, asked, refusal, engine):
        answer = httpx2.post(f"{url}/v1/chat/completions", json=ASKED, timeout=60)
        assert answer.status_code == 503
        assert refusal in answer.json()["error"]["message"]
        assert (
            httpx2.post(f"{url}/v1/chat/completions", json={**ASKED, "model": "agent"}, timeout=60).status_code == 503
        )
    assert asked == ["vision"], "the agent's role is not loaded on demand"
