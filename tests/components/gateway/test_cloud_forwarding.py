"""Design 0016 §8 (decisions 0109 and 0110): the gateway forwards a cloud slot's requests to the provider's
`/chat/completions` with the listed model id, the bearer key it holds, the session for the provider's cache and the
record's data policy, nothing else changed; a stream comes back line by line, the provider's comment lines and tool
calls' pieces unchanged, a whole answer whole; a mid-stream error ends the stream; a request is never sent again, a
connection refused answered 502 `cloud_unreachable` and one broken off ending the stream; an answer silent for the read
timeout ends with `cloud_silent`; and each refusal passes with its status and Clank's words of what to do, never
OpenCode's retry words for those it must not retry, and never a status it retries by: no provider under the record's
data policy (OpenRouter's 503) is answered 403 (decision 0115). A key echoed in an answer never reaches the record or
the live view."""

import contextlib
import hashlib
import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
import uvicorn

from clank.components.gateway.holds import Holds
from clank.components.gateway.keys import Keys
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.records import TrafficLog
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import RETRIED_STATUSES, RETRIED_WORDS, create_gateway
from clank.kernel.service import server_config
from tests.fakes.openrouter import KEY, FakeOpenRouter
from tests.support.served import free_port

MODEL = "example-vendor/example-coder"
SESSION = "ses_0c2e9ffe1Qk2Lr8xYb3Zd7a1f0"
WORKSPACE_KEY = "clank-ws-made-up-cloudy-key"  # the key of a workspace allowed the cloud (design 0016 §9)
ASKS: dict[str, Any] = {
    "model": "agent",
    "stream": True,
    "stream_options": {"include_usage": True},
    "max_tokens": 64,
    "tools": [{"type": "function", "function": {"name": "bash", "parameters": {"type": "object"}}}],
    "messages": [{"role": "user", "content": "Reply with OK."}],
}


def cloud_slot(url: str, read_timeout: float = 30, data_collection: str = "deny") -> dict[str, Any]:
    """A cloud slot's route, as `GET /gateway/routes` answers it (plan s34's interface)."""
    return {
        "status": "ready", "busy": False, "port": None, "engine": None, "version": None, "model_name": MODEL,
        "preset": "cloud-example-coder", "title": "cloud: Example Coder", "context": 65536, "output": 16384,
        "images": False, "provider": "endpoint", "endpoint": "openrouter", "adapter": "openrouter", "base_url": url,
        "reach": "cloud", "agreed": True, "launch": 7, "read_timeout": read_timeout,
        "adds": {"provider": {"data_collection": data_collection}},
        "prices": {"in": 3e-7, "out": 1.2e-6, "cached_in": 3e-8},
    }  # fmt: skip


@contextlib.contextmanager
def forwarding(
    slot: dict[str, Any],
    tmp_path: Path,
    keys: Keys | None = None,
    ask_cloud: Any = None,
    hold_seconds: int = 3,
    local_only: list[str] | None = None,
    marks: Any = None,
    spool: Any = None,
    token: str | None = None,
    records: bool = True,
    holds: Holds | None = None,
) -> Iterator[tuple[str, Routes]]:
    """The gateway with a cloud route and its key held, its routes naming the workspace `cloudy` (allowed the cloud,
    its key `WORKSPACE_KEY`), served for real; its base URL, and its routes."""
    routes = Routes()
    allowed = {"workspace": "cloudy", "models": "cloud", "answered": True, "question": None}
    workspaces = {hashlib.sha256(WORKSPACE_KEY.encode()).hexdigest(): allowed}
    routes.update(
        {"slots": {"main": slot}, "roles": {"agent": "main"}, "default_slot": "main", "workspaces": workspaces,
         "local_only": local_only or []}
    )  # fmt: skip
    if keys is None:
        keys = Keys()
        keys.put("openrouter", KEY, 7, "")
    settings = GatewaySettings(port=free_port(), hold_seconds=hold_seconds, records=records)
    log = TrafficLog(tmp_path / "traffic", 256, 14) if records else None
    extra = {"spool": spool} if spool is not None else {}
    app = create_gateway(
        routes, settings, log, keys=keys, ask_cloud=ask_cloud, marks=marks, token=token, holds=holds, **extra
    )
    server = uvicorn.Server(server_config(app, "127.0.0.1", settings.port))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the gateway never started"
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{settings.port}", routes
    finally:
        server.should_exit = True
        thread.join(15)


@pytest.fixture
def gateway(openrouter: FakeOpenRouter, tmp_path: Path) -> Iterator[str]:
    with forwarding(cloud_slot(openrouter.url), tmp_path) as (url, _):
        yield url


def recorded(tmp_path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for file in sorted((tmp_path / "traffic").glob("*.jsonl"))
            for line in file.read_text(encoding="utf-8").splitlines()]  # fmt: skip


def asked(url: str, body: dict[str, Any] | None = None, **headers: str) -> httpx2.Response:
    sent = {"X-Session-Id": SESSION, "Authorization": f"Bearer {WORKSPACE_KEY}", **headers}
    return httpx2.post(f"{url}/v1/chat/completions", json=body or ASKS, headers=sent, timeout=30)


def lines(answer: httpx2.Response) -> list[str]:
    return [line for line in answer.text.split("\n\n") if line]


def test_a_streamed_request_reaches_the_provider_as_the_tool_sent_it_with_the_key_and_the_session(
    gateway: str, openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    openrouter.play("comments")
    answer = asked(gateway)
    assert answer.status_code == 200, answer.text
    assert lines(answer) == openrouter.exchange("comments")["response"]["stream"], "line by line, comments included"
    [sent] = openrouter.chats()
    assert sent.body == {**ASKS, "model": MODEL, "provider": {"data_collection": "deny"}}
    assert sent.headers["authorization"] == f"Bearer {KEY}"
    assert sent.headers["x-session-id"] == SESSION
    assert not {"http-referer", "x-title", "x-openrouter-title"} & set(sent.headers)
    [record] = recorded(tmp_path)
    assert (record["provider"], record["model_sent"], record["reach"], record["status"]) == (
        "cloud openrouter", MODEL, "cloud", 200
    )  # fmt: skip
    assert record["notes"] == ["provider.data_collection deny added (the provider's record)"]
    assert record["usage"]["cost"] == 0.000021
    assert KEY not in json.dumps(record)


def test_a_whole_answer_comes_back_whole(gateway: str, openrouter: FakeOpenRouter) -> None:
    answer = asked(gateway, {**ASKS, "stream": False})
    assert answer.status_code == 200, answer.text
    assert answer.json() == openrouter.exchange("answer")["response"]["body"]


def test_a_tool_calls_pieces_and_thinking_pass_unchanged(gateway: str, openrouter: FakeOpenRouter) -> None:
    for play in ("tool call", "thinking"):
        openrouter.play(play)
        answer = asked(gateway)
        assert lines(answer) == openrouter.exchange(play)["response"]["stream"], play


def test_a_mid_stream_error_ends_the_stream_and_is_recorded(
    gateway: str, openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    openrouter.play("mid-stream error")
    answer = asked(gateway)
    assert '"finish_reason":"error"' in lines(answer)[-1]
    [record] = recorded(tmp_path)
    assert record["error"] == "Provider disconnected unexpectedly"


def test_a_connection_refused_is_answered_cloud_unreachable_and_never_sent_again(tmp_path: Path) -> None:
    with forwarding(cloud_slot(f"http://127.0.0.1:{free_port()}/api/v1"), tmp_path) as (url, _):
        answer = asked(url)
    assert answer.status_code == 502
    error = answer.json()["error"]
    assert error["code"] == "cloud_unreachable"
    assert error["message"].startswith("OpenRouter did not answer")
    assert "check this computer's network" in error["message"]


def test_a_stream_broken_off_before_any_answer_ends_and_is_never_sent_again(
    gateway: str, openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    openrouter.played["exchanges"].append(
        {"name": "dropped", "request": {}, "response": {"status": 200, "headers": {}, "stream": []}}
    )
    openrouter.play("dropped")
    answer = asked(gateway)
    assert answer.status_code == 200
    assert '"code": "cloud_unreachable"' in lines(answer)[-1]
    time.sleep(0.5)
    assert len(openrouter.chats()) == 1, "never sent again: it may have been billed"
    [record] = recorded(tmp_path)
    assert "never sent again" in record["broken"]


def test_an_answer_silent_for_the_read_timeout_ends_with_cloud_silent(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    openrouter.silence = 5
    with forwarding(cloud_slot(openrouter.url, read_timeout=0.5), tmp_path) as (url, _):
        openrouter.play("silent")
        streamed = asked(url)
        openrouter.play("silent")
        whole = asked(url, {**ASKS, "stream": False})
    assert '"code": "cloud_silent"' in lines(streamed)[-1]
    assert (whole.status_code, whole.json()["error"]["code"]) == (504, "cloud_silent")
    assert "OpenRouter was silent for 0.5 s" in whole.json()["error"]["message"]
    assert len(openrouter.chats()) == 2


@pytest.mark.parametrize(
    ("play", "status", "answered", "words", "retried"),
    [
        ("key refused", 401, 401, "OpenRouter refused the key: it may have been deleted or disabled", False),
        ("no credits", 402, 402, "Your OpenRouter credits are used up, or this key's own limit is reached", False),
        ("budget", 403, 403, "OpenRouter refused this request: Made-up words: a budget refused this request", False),
        ("no model", 404, 404, "OpenRouter lists no model example-vendor/example-coder", False),
        ("rate limited", 429, 429, "Made-up words: rate limited upstream", True),
        ("no provider", 503, 403, "serves it with data_collection deny: pick another model, or allow it", False),
    ],
)
def test_each_refusal_passes_with_its_status_and_words_of_what_to_do(
    gateway: str,
    openrouter: FakeOpenRouter,
    tmp_path: Path,
    play: str,
    status: int,
    answered: int,
    words: str,
    retried: bool,
) -> None:
    if play == "key refused":
        openrouter.key = "another-made-up-key"
    else:
        openrouter.play(play)
    answer = asked(gateway)
    assert answer.status_code == answered
    message = answer.json()["error"]["message"]
    if not retried:
        assert str(answer.status_code) not in RETRIED_STATUSES, "OpenCode retries by the status alone"
        assert not any(pattern.search(message) for pattern, _ in RETRIED_WORDS), message
        assert not any(code in message for code in RETRIED_STATUSES), message
    assert words.split(":")[0] in message
    if play == "rate limited":
        assert answer.headers["retry-after"] == "7"
    [record] = recorded(tmp_path)
    assert record["status"] == status
    assert KEY not in json.dumps(record)


def test_a_key_echoed_in_an_answer_never_reaches_the_record_or_the_live_view(
    gateway: str, openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    echo = openrouter.exchange("stream")["response"]["stream"][0].replace('"content":"O"', f'"content":"{KEY}"')
    openrouter.played["exchanges"].append(
        {
            "name": "echo",
            "request": {},
            "response": {
                "status": 200,
                "headers": {},
                "stream": [echo, *openrouter.exchange("stream")["response"]["stream"][2:]],
            },
        }
    )
    openrouter.play("echo")
    asked(gateway)
    live = httpx2.get(f"{gateway}/activity/live", timeout=10).json()
    kept = json.dumps(recorded(tmp_path), ensure_ascii=False)
    assert KEY not in json.dumps(live)
    assert KEY not in kept
    assert f"…{KEY[-4:]}" in kept
