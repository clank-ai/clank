"""Design 0006 §4: the gateway's fill in the middle. A completion for the `completion` role goes to the fast slot's
engine (llama.cpp's `/infill`), its fields as they came but for the model and with time limits a late completion needs;
the newest completion wins (the one in flight is broken off, its client answered with nothing); with no engine serving
the role it is refused at once, never held; and the gateway keeps the last ones in memory, with their times, for the
Completion page, never in its records of the agent's requests."""

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
import uvicorn

from clank.components.gateway.completion import LIMITS
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.records import TrafficLog
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import create_gateway
from clank.kernel.service import server_config
from tests.components.gateway.test_server import received, started
from tests.support.served import free_port


def table(port: int | None) -> dict[str, Any]:
    """The service's routes: nothing in the main slot, the fast slot running llama.cpp."""
    fast = {
        "status": "ready" if port else "stopped", "port": port, "engine": "llamacpp", "version": "b11588",
        "model_name": "qwen2.5-coder-0.5b", "preset": "completion-0.5b", "title": "completion 0.5B", "context": 8192,
        "output": 128,
    }  # fmt: skip
    main = {"status": "stopped", "port": None, "engine": None, "version": None, "model_name": None, "preset": None,
            "title": None, "context": None, "output": None}  # fmt: skip
    return {"slots": {"main": main, "fast": fast}, "roles": {"agent": "main", "completion": "fast"},
            "default_slot": "main"}  # fmt: skip


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[tuple[int, Path]]:
    """A fake llama.cpp that reads each prompt for half a second; its port and its log."""
    log = tmp_path / "engine.log"
    with started(log, "--fake-prompt-seconds", "0.5", style="llamacpp") as port:
        yield port, log


def serve(routes: Routes, tmp_path: Path) -> Iterator[str]:
    port = free_port()
    app = create_gateway(routes, GatewaySettings(port=port, hold_seconds=10), TrafficLog(tmp_path / "traffic", 256, 14))
    server = uvicorn.Server(server_config(app, "127.0.0.1", port))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the gateway never started"
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(15)


@pytest.fixture
def gateway(engine: tuple[int, Path], tmp_path: Path) -> Iterator[str]:
    routes = Routes()
    routes.update(table(engine[0]))
    yield from serve(routes, tmp_path)


ASKED = {
    "model": "completion",
    "input_prefix": "def f(x):\n",
    "input_suffix": "\n",
    "prompt": "    ret",
    "n_predict": 24,
}


def test_a_completion_goes_to_the_fast_slots_engine_and_is_counted(
    gateway: str, engine: tuple[int, Path], tmp_path: Path
) -> None:
    answer = httpx2.post(f"{gateway}/v1/infill", json=ASKED, timeout=30)
    assert answer.status_code == 200, answer.text
    assert answer.json()["content"] == "middle7"
    [sent] = received(engine[1])
    assert sent == {**{key: value for key, value in ASKED.items() if key != "model"}, **LIMITS}
    found = httpx2.get(f"{gateway}/completion", timeout=10).json()
    assert (found["count"], found["broken_off"], found["failed"]) == (1, 0, 0)
    [last] = found["recent"]
    assert (last["outcome"], last["prompt_n"], last["predicted_n"], last["chars"]) == ("answered", 12, 3, 7)
    assert last["total_ms"] >= 500
    assert found["median_ms"] == last["total_ms"]
    assert not list((tmp_path / "traffic").glob("*.jsonl")), "the agent's records keep no completion"


def test_the_newest_completion_wins_and_the_one_in_flight_is_broken_off(gateway: str, engine: tuple[int, Path]) -> None:
    answers: list[httpx2.Response] = []
    first = threading.Thread(
        target=lambda: answers.append(httpx2.post(f"{gateway}/v1/infill", json=ASKED, timeout=30)), daemon=True
    )
    first.start()
    time.sleep(0.2)  # the engine is reading the first one's prompt
    newer = httpx2.post(f"{gateway}/v1/infill", json={**ASKED, "prompt": "    retu"}, timeout=30)
    first.join(30)
    assert newer.json()["content"] == "middle8"
    [broken] = answers
    assert broken.status_code == 200
    assert broken.json() == {"content": "", "stop": True, "broken_off": "a newer completion came"}
    found = httpx2.get(f"{gateway}/completion", timeout=10).json()
    assert [entry["outcome"] for entry in found["recent"]] == ["answered", "broken off"]
    assert (found["count"], found["broken_off"]) == (2, 1)
    deadline = time.monotonic() + 5
    while "client left before the middle" not in engine[1].read_text(encoding="utf-8"):
        assert time.monotonic() < deadline, "the engine was never left: it went on with an old completion"
        time.sleep(0.05)


def test_with_no_engine_for_the_role_a_completion_is_refused_at_once(tmp_path: Path) -> None:
    routes = Routes()
    routes.update(table(None))
    for url in serve(routes, tmp_path):
        began = time.monotonic()
        answer = httpx2.post(f"{url}/v1/infill", json=ASKED, timeout=30)
        assert time.monotonic() - began < 2, "a completion is never held while a slot starts"
        assert answer.status_code == 503
        assert "fast" in answer.json()["error"]["message"]
        found = httpx2.get(f"{url}/completion", timeout=10).json()
        assert [entry["outcome"] for entry in found["recent"]] == ["refused"]
        assert json.dumps(found)  # plain JSON for the service
