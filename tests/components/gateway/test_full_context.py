"""Design 0012 §4.1 (revised 2026-10-20, decision 0090) and design 0004 §2: an engine's refusal of a request its context
cannot hold (KVMem's 400, "prompt + max_tokens exceeds n_ctx", which OpenCode 1.19 takes for an ordinary error and stops
on; upstream llama.cpp's 400, `exceed_context_size_error`) is answered by the gateway in words and a code OpenCode reads
as a context overflow, on which it compacts the session and goes on: a 400 in OpenAI's shape whose message says the
context was full and that the request exceeds the available context size, its code `context_length_exceeded`, streamed
or not; and inside a stream whose 200 has gone out (a held request, after its resume), an error event in the one shape
OpenCode reads there. The record marks it (`full`, the engine's words), and so do the session's requests that ended.
Any other refusal is passed on as the engine gave it, its error recorded. The requests are synthetic."""

import json
import re
from pathlib import Path
from typing import Any

import httpx2

from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.records import recent
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import OVERFLOW
from tests.components.gateway.test_hold_gateway import SESSION, asking, comments, holding, pause, resume
from tests.components.gateway.test_server import ASKED, received, recorded, serving, started, table
from tests.fakes.engine import FULL, REFUSAL
from tests.support.served import free_port

KVMEM_SAID = "prompt + max_tokens exceeds n_ctx"
# OpenCode 1.19.0's own test of an HTTP error's message (its provider/error.ts, read in its program on 2026-10-20: the
# patterns that bear on these engines, and those that make an error never an overflow).
OVERFLOW_WORDS = (r"exceeds the available context size", r"context[_ ]length[_ ]exceeded", r"too many tokens")
NEVER = (r"^(throttling error|service unavailable):", r"rate limit", r"too many requests")


def opencode_reads_an_overflow(error: dict[str, Any]) -> bool:
    """Whether OpenCode 1.19.0 takes an HTTP error in OpenAI's shape for a context overflow: by its words, unless they
    are a limit of requests, or by its code."""
    message = str(error.get("message") or "")
    if any(re.search(words, message, re.IGNORECASE) for words in NEVER):
        return False
    return error.get("code") == "context_length_exceeded" or any(
        re.search(words, message, re.IGNORECASE) for words in OVERFLOW_WORDS
    )


def routed(port: int, style: str = "kvmem") -> Routes:
    """The routes: the main slot running the fake engine as KVMem, or as upstream llama.cpp."""
    raw = table(port)
    if style == "llamacpp":
        raw["slots"]["main"] |= {"engine": "llamacpp", "version": "b11588"}
    routes = Routes()
    routes.update(raw)
    return routes


def ask(url: str, streamed: bool) -> httpx2.Response:
    body = {**ASKED, "stream": streamed}
    return httpx2.post(f"{url}/v1/chat/completions", json=body, headers={"X-Session-Id": SESSION}, timeout=30)


def test_kvmems_refusal_of_a_full_context_is_answered_as_an_overflow_opencode_compacts_on(tmp_path: Path) -> None:
    for streamed in (True, False):
        folder = tmp_path / ("streamed" if streamed else "whole")
        settings = GatewaySettings(port=free_port(), hold_seconds=10)
        with (
            started(tmp_path / f"engine-{streamed}.log", "--fake-full") as port,
            serving(routed(port), settings, folder) as url,
        ):
            answer = ask(url, streamed)
            ended = httpx2.get(f"{url}/activity", params={"session": SESSION, "ended": "true"}).json()["ended"]
        assert answer.status_code == 400, answer.text
        error = answer.json()["error"]
        assert opencode_reads_an_overflow(error)
        assert (error["code"], error["type"]) == ("context_length_exceeded", "context_length_exceeded")
        assert error["message"].startswith(f"the context was full: {KVMEM_SAID}")
        assert "the request exceeds the available context size" in error["message"]
        [record] = recorded(folder)
        assert (record["status"], record["full"]) == (400, KVMEM_SAID)
        assert record["error"]["code"] == "context_length_exceeded"
        assert ended[-1]["full"] == KVMEM_SAID, "the session's requests that ended say it too"
        [brief] = recent(folder / "traffic", 5)
        assert brief["full"] is True, "and the Requests page's list"
        assert brief["error"].startswith("the context was full: "), "its error in words"


def test_upstream_llamacpps_refusal_of_a_full_context_is_answered_the_same_way(tmp_path: Path) -> None:
    settings = GatewaySettings(port=free_port(), hold_seconds=10)
    with (
        started(tmp_path / "engine.log", "--fake-full", style="llamacpp") as port,
        serving(routed(port, "llamacpp"), settings, tmp_path) as url,
    ):
        answer = ask(url, True)
    assert answer.status_code == 400, answer.text
    error = answer.json()["error"]
    assert opencode_reads_an_overflow(error)
    assert error["message"].startswith(f"the context was full: {FULL['llamacpp']}")
    [record] = recorded(tmp_path)
    assert record["full"] == FULL["llamacpp"]


def test_any_other_refusal_is_passed_on_as_the_engine_gave_it_and_recorded(tmp_path: Path) -> None:
    settings = GatewaySettings(port=free_port(), hold_seconds=10)
    with (
        started(tmp_path / "engine.log", "--fake-refuse", "400") as port,
        serving(  # llama.cpp's words: not KVMem's
            routed(port), settings, tmp_path
        ) as url,
    ):
        answer = ask(url, True)
    assert answer.status_code == 400
    assert answer.json()["error"]["message"] == REFUSAL, "the engine's own answer"
    [record] = recorded(tmp_path)
    assert record["error"]["message"] == REFUSAL
    assert "full" not in record


def test_a_held_requests_full_context_is_told_in_the_stream_in_the_one_shape_opencode_reads_there(
    tmp_path: Path,
) -> None:
    with started(tmp_path / "engine.log", "--fake-full") as port:
        with holding(routed(port), tmp_path) as url:
            pause(url)
            with asking(url, {"X-Session-Id": SESSION}) as answer:
                lines = answer.iter_lines()
                comments(lines, 1)
                resume(url)
                rest = [line for line in lines if line.startswith("data: ")]
        assert len(received(tmp_path / "engine.log")) == 1
    [event] = [json.loads(line[6:]) for line in rest]
    error = event["error"]
    assert json.loads(error["message"]) == {
        "type": "error",
        "error": {"code": "context_length_exceeded", "message": f"the context was full: {KVMEM_SAID} ({OVERFLOW})"},
    }, "OpenAI's Responses shape, written as the error's message: what OpenCode 1.19 reads as an overflow in a stream"
    [record] = recorded(tmp_path)
    assert (record["status"], record["full"]) == (400, KVMEM_SAID)
