"""Design 0016 §18: the checks owed with the owner's key, against OpenRouter itself. Never in CI: run only when asked
(`uv run pytest -m openrouter`), with the key typed for the run in `CLANK_TEST_OPENROUTER_KEY` (never stored), on
Clank's made-up words only, to the cheapest model that takes tool calls (`CLANK_TEST_OPENROUTER_MODEL` names another).
Each answer that differs from the documentation revises design 0016 §3 and the adapter in one commit."""

import json
import os
from collections.abc import Iterator
from typing import Any

import httpx2
import pytest

from clank.components.runtime.adapters.openrouter import OpenRouter
from tools.capture_endpoint import URL, VARIABLE, _cheapest

pytestmark = [
    pytest.mark.openrouter,
    pytest.mark.skipif(not os.environ.get(VARIABLE), reason=f"it asks OpenRouter itself: set {VARIABLE} for the run"),
]
TINY = [{"role": "user", "content": "Reply with OK."}]


@pytest.fixture(scope="module")
def client() -> Iterator[httpx2.Client]:
    key = os.environ.get(VARIABLE, "")
    with httpx2.Client(base_url=URL, headers={"Authorization": f"Bearer {key}"}, timeout=120) as found:
        yield found


@pytest.fixture(scope="module")
def model(client: httpx2.Client) -> str:
    named = os.environ.get("CLANK_TEST_OPENROUTER_MODEL", "")
    return named or _cheapest(client.get("/models").json()["data"])


def events(text: str) -> list[dict[str, Any]]:
    found = []
    for line in text.splitlines():
        if line.startswith("data:") and line[5:].strip() != "[DONE]":
            found.append(json.loads(line[5:]))
    return found


def test_check_1_the_models_list_with_and_without_the_key(client: httpx2.Client) -> None:
    keyed = client.get("/models", params=OpenRouter().models_query("most-popular"))
    assert keyed.status_code == 200, keyed.text
    assert OpenRouter().models(keyed.json()), "the adapter reads the list"
    bare = httpx2.get(f"{URL}/models", timeout=60)
    print(f"check 1: without the key the list answers {bare.status_code}")


def test_check_2_and_7_a_streams_id_is_its_generation_and_its_last_message_has_the_cost(
    client: httpx2.Client, model: str
) -> None:
    body = {"model": model, "messages": TINY, "max_tokens": 16, "stream": True, "provider": {"data_collection": "deny"}}
    answer = client.post("/chat/completions", json=body)
    assert answer.status_code == 200, answer.text
    found = events(answer.text)
    usage = next(event["usage"] for event in reversed(found) if event.get("usage"))
    assert OpenRouter().cost(usage, {}, {}).how == "usage", "usage.cost in the stream's last message"
    print(f"check 2: the stream's id is {found[0].get('id')}")


def test_check_7_a_whole_answer_has_its_cost(client: httpx2.Client, model: str) -> None:
    answer = client.post("/chat/completions", json={"model": model, "messages": TINY, "max_tokens": 16})
    assert answer.status_code == 200, answer.text
    assert OpenRouter().cost(answer.json().get("usage"), {}, {}).how == "usage"


def test_check_10_the_keys_own_facts_read(client: httpx2.Client) -> None:
    answer = client.get("/key")
    assert answer.status_code == 200
    account = OpenRouter().account(answer.json())
    print(f"check 10: limit {account.limit_usd}, left {account.remaining_usd}")


def test_check_6_and_5_a_refused_key_reads_into_words() -> None:
    answer = httpx2.get(f"{URL}/key", headers={"Authorization": "Bearer made-up-wrong-key"}, timeout=60)
    refusal = OpenRouter().refusal(answer.status_code, answer.content)
    assert refusal.code == "key_refused", answer.text
