"""Design 0016 §8 and design 0015 §8 (decision 0074): thinking streamed as `reasoning`, as OpenRouter streams it, is
read as `reasoning_content` is: it shows in the live view, counts as thinking, trips the loop guard when it repeats
itself, and reaches the tool unchanged; a delta that carries both is read once."""

import json
from pathlib import Path
from typing import Any

import httpx2

from clank.components.gateway.loops import LoopGuard
from clank.components.gateway.server import _guarded, _heard, _read_event
from tests.components.gateway.test_cloud_forwarding import asked, cloud_slot, forwarding, lines
from tests.fakes.openrouter import FakeOpenRouter

TAGS = "</f>\n</invoke>\n</functions>\n"


def event(delta: dict[str, Any]) -> bytes:
    return b"data: " + json.dumps({"choices": [{"index": 0, "delta": delta, "finish_reason": None}]}).encode()


def test_thinking_as_reasoning_counts_as_thinking_and_is_heard() -> None:
    heard: list[tuple[str, str]] = []
    kinds = _read_event(event({"reasoning": "The owner asks for OK."}), [], {}, lambda *each: heard.append(each))
    assert kinds == ["thinking"]
    assert heard == [("thinking", "The owner asks for OK.")]


def test_a_delta_carrying_both_names_is_read_once() -> None:
    heard: list[tuple[str, str]] = []
    both = {"reasoning": "Once.", "reasoning_content": "Once."}
    assert _read_event(event(both), [], {}, lambda *each: heard.append(each)) == ["thinking"]
    assert heard == [("thinking", "Once.")]
    fed: list[tuple[str, str]] = []
    _heard(both, lambda *each: fed.append(each))
    assert fed == [("thinking", "Once.")]


def test_thinking_as_reasoning_that_repeats_itself_trips_the_loop_guard() -> None:
    guard = LoopGuard()
    for _ in range(400):
        _guarded({"reasoning": TAGS}, guard)
        if guard.tripped is not None:
            break
    assert guard.tripped is not None
    assert "thinking" in guard.tripped


def test_thinking_as_reasoning_shows_in_the_live_view_and_reaches_the_tool_unchanged(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    with forwarding(cloud_slot(openrouter.url), tmp_path) as (url, _):
        openrouter.play("thinking")
        answer = asked(url)
        live = httpx2.get(f"{url}/activity/live", timeout=10).json()
    assert lines(answer) == openrouter.exchange("thinking")["response"]["stream"]
    thought = "".join(str(part[1]) for part in live["parts"] if part[0] == "thinking")
    assert "The owner asks for OK." in thought
