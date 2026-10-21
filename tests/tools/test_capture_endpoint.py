"""Design 0016 §18: the capture of OpenRouter's answers to Clank's fixed made-up requests, run here against the fake
OpenRouter (never the network): it records each exchange the contract reads, never the key, and replaces what the
account says of the owner (its label, limit, use and ids) by made-up values; without the key's variable it records
nothing."""

import json

import httpx2
import pytest

from tests.fakes.openrouter import KEY, served
from tools import capture_endpoint


def test_the_capture_records_each_exchange_never_the_key_and_the_account_made_up() -> None:
    with served() as fake:
        account = fake.exchange("key")["response"]["body"]["data"]
        account.update(label="the owner's own label", usage=123.45, creator_user_id="user_made_up_owner")
        with httpx2.Client(base_url=fake.url, headers={"Authorization": f"Bearer {KEY}"}, timeout=30) as client:
            recording = capture_endpoint.capture(client, "", "")
    names = [each["name"] for each in recording["exchanges"]]
    assert names == ["key", "models", "every model", "answer", "stream", "thinking", "tool call", "generation", "cut",
                     "key refused", "no model"]  # fmt: skip
    text = json.dumps(recording)
    assert KEY not in text.replace(f'"key": "{KEY}"', "")
    assert "the owner's own label" not in text
    assert "user_made_up_owner" not in text
    data = recording["exchanges"][0]["response"]["body"]["data"]
    assert (data["label"], data["usage"], data["creator_user_id"]) == ("made-up key label", 1.29, None)
    assert recording["exchanges"][-2]["response"]["status"] == 401
    cut = recording["exchanges"][8]["response"]["stream"]
    assert len(cut) == 1, "left after its first data line"
    every = [request.body for request in fake.chats()]
    assert all(body["provider"] == {"data_collection": "deny"} for body in every[:-1])


def test_without_the_keys_variable_nothing_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(capture_endpoint.VARIABLE, raising=False)
    assert capture_endpoint.main([]) == 2
