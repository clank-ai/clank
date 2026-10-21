"""Design 0016 §6 (design 0015 §11, decision 0076): a provider's check asks it only Clank's own made-up requests (its
key, its list, one short reply, a call to a made-up tool, a little thinking) and says, item by item and in order, its
agreement, its key, its account, its models, the model, the answer, tool calls, thinking, its data policy and Clank's
cost limits, each with its words; a refused key fails the key and leaves the rest unknown; the result is an event and
the provider's last check. The test of a cloud preset is one short request: its answer, time and cost, or the refusal's
code and what to do; what either cost is kept."""

from typing import Any

import anyio
import pytest

from clank.components.runtime.adapters.openrouter import OpenRouter
from clank.kernel.events import Actor
from clank.kernel.operations import Operation
from tests.components.runtime.conftest import Rig, add_openrouter
from tests.fakes.openrouter import FakeOpenRouter
from tests.support.served import free_port

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")
CODER = "example-vendor/example-coder"
CLOUD: dict[str, object] = {"title": "cloud: Example Coder", "endpoint": "openrouter", "model": CODER,
                            "options": {"context": 65536, "max_output": 16384, "reasoning": "default"}}  # fmt: skip
ORDER = ["agreed", "key", "account", "models", "model", "answer", "tools", "thinking", "policy", "limits"]
MADE_UP = {"Reply with OK.", "Look up the made-up word blue.", "Think briefly, then reply with OK."}


@pytest.fixture
def cloud(rig: Rig, openrouter: FakeOpenRouter) -> Rig:
    add_openrouter(rig)
    rig.preset("cloud-example-coder", CLOUD)
    return rig


async def run(rig: Rig, type: str, **params: Any) -> Operation:
    async with rig.kernel.operations.running():
        started = await rig.kernel.operations.start(type, params, actor=YOU)
        with anyio.fail_after(60):
            return await rig.kernel.operations.wait(started.id)


def said(items: list[dict[str, Any]]) -> dict[str, tuple[str, str]]:
    return {item["name"]: (item["status"], item["said"]) for item in items}


async def test_the_check_says_each_item_in_order_with_its_words(cloud: Rig, openrouter: FakeOpenRouter) -> None:
    openrouter.play("answer", "tool call", "thinking")
    done = await run(cloud, "runtime.endpoint_check", id="openrouter")
    assert done.status == "done", done.error
    result = done.result or {}
    assert [item["name"] for item in result["items"]] == ORDER
    found = said(result["items"])
    assert found["agreed"] == ("ok", "2026-10-21 09:12 UTC")
    assert found["key"][0] == "ok"
    assert found["key"][1] == 'set (ends …-key), accepted: "made-up key label"; its limit $20.00, $18.71 left'
    assert found["account"] == ("ok", "used today $0.12, this month $1.29 (OpenRouter's count, UTC days)")
    assert found["models"][0] == "ok"
    assert found["models"][1].startswith("2 take tool calls (listed ")
    assert found["model"] == (
        "ok", f"{CODER}: window 262,144, output 32,768, $0.30 in, $1.20 out per million"
    )  # fmt: skip
    assert found["answer"][0] == "ok"
    assert found["answer"][1].startswith("OK in ")
    assert found["answer"][1].endswith(", cost $0.000021")
    assert found["tools"] == ("ok", "a call to the made-up tool came back as a tool call")
    assert found["thinking"] == ("ok", "streamed as reasoning")
    assert found["policy"] == ("ok", "answered with data_collection deny")
    assert found["limits"] == ("warn", "no daily or monthly limit in Clank (L on the Providers page)")
    assert result["ok"] is True
    [event] = cloud.kernel.events.latest(types=["runtime.endpoint_checked"])
    assert event.data == {"id": "openrouter", "ok": True, "items": result["items"]}
    view = cloud.runtime.endpoints.view("openrouter")
    assert view["check"]["ok"] is True
    assert view["check"]["items"] == result["items"]
    assert view["check"]["time"]
    for chat in openrouter.chats():
        assert {message["content"] for message in chat.body["messages"]} <= MADE_UP, "Clank's made-up requests only"
    assert cloud.runtime.endpoints.own_costs() == pytest.approx(0.000021 + 0.000032 + 0.00003)


async def test_a_refused_key_fails_the_key_and_leaves_the_rest_unknown(cloud: Rig, openrouter: FakeOpenRouter) -> None:
    openrouter.key = "another-made-up-key"
    done = await run(cloud, "runtime.endpoint_check", id="openrouter")
    result = done.result or {}
    found = said(result["items"])
    assert found["agreed"][0] == "ok"
    assert found["key"][0] == "fail"
    assert found["key"][1].startswith("OpenRouter refused the key")
    assert {found[name][0] for name in ORDER[2:]} == {"unknown"}
    assert result["ok"] is False
    assert openrouter.chats() == []


async def test_a_model_named_for_the_check_is_the_one_asked(cloud: Rig, openrouter: FakeOpenRouter) -> None:
    done = await run(cloud, "runtime.endpoint_check", id="openrouter", model="example-vendor/example-small:free")
    found = said((done.result or {})["items"])
    assert found["model"][1].startswith("example-vendor/example-small:free: window 32,768")
    assert found["thinking"] == ("warn", "example-vendor/example-small:free does not think")
    assert {chat.body["model"] for chat in openrouter.chats()} == {"example-vendor/example-small:free"}


@pytest.mark.parametrize(
    ("play", "code", "words"),
    [
        ("no credits", "no_credits", "Your OpenRouter credits are used up"),
        ("no model", "no_model", "OpenRouter lists no model example-vendor/example-coder"),
        ("no provider", "data_policy", "serves it with data_collection deny"),
        ("budget", "refused", "OpenRouter refused this request"),
        ("key refused", "key_refused", "OpenRouter refused the key"),
    ],
)
async def test_the_test_of_a_cloud_preset_says_each_refusal_by_its_code(
    cloud: Rig, openrouter: FakeOpenRouter, play: str, code: str, words: str
) -> None:
    openrouter.play(play)
    done = await run(cloud, "runtime.endpoint_test", id="openrouter", preset="cloud-example-coder")
    assert done.status == "done", done.error
    result = done.result or {}
    assert (result["ok"], result["code"]) == (False, code)
    assert words in result["said"]


async def test_the_test_of_a_cloud_preset_says_its_answer_time_and_cost(cloud: Rig, openrouter: FakeOpenRouter) -> None:
    done = await run(cloud, "runtime.endpoint_test", id="openrouter", preset="cloud: Example Coder")
    result = done.result or {}
    assert (result["ok"], result["answer"], result["cost_usd"]) == (True, "OK", 0.000021)
    assert result["said"] == f"OK in {result['seconds']:.1f} s, $0.000021"
    [chat] = openrouter.chats()
    assert chat.body["messages"] == [{"role": "user", "content": "Reply with OK."}]
    assert cloud.runtime.endpoints.own_costs() == pytest.approx(0.000021)


async def test_the_test_says_when_openrouter_does_not_answer(cloud: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("clank.components.runtime.endpoints.ASK_SECONDS", 2.0)
    record = cloud.runtime.endpoints.record("openrouter")
    unreachable = f"http://127.0.0.1:{free_port()}/api/v1"
    monkeypatch.setattr(OpenRouter, "URL", unreachable)
    cloud.kernel.settings.write(
        "endpoint", "openrouter", {**record.model_dump(), "url": unreachable},
        base=cloud.kernel.settings.get("endpoint", "openrouter").revision, actor=YOU,
    )  # fmt: skip
    done = await run(cloud, "runtime.endpoint_test", id="openrouter", preset="cloud-example-coder")
    result = done.result or {}
    assert (result["ok"], result["code"]) == (False, "cloud_unreachable")
    assert "OpenRouter did not answer" in result["said"]
