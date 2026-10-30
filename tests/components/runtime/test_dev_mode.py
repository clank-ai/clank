"""Design 0016 §4, §8 and §16 (decision 0149): dev mode, for testing. It is off until the owner turns it on, and kept
in the runtime's settings (`config/runtime.json`'s `dev_mode`) with who turned it on or off. While it is on, every
cloud provider is asked for any of a model's providers (`data_collection allow`) from the next request, whatever its
record says: the route the gateway follows, a load's tiny request and the provider's check, each request's notes
naming dev mode. The record keeps its own policy, which applies again from the next request once dev mode is off; a
record that already allows any provider, and its `zdr`, are left as they are. Each provider says dev mode beside its
own policy, as `GET` and `PUT /runtime/dev` say what dev mode does."""

from collections.abc import Iterator
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient

from clank.components.runtime import cloud as cloud_slot
from clank.components.runtime.adapters.openrouter import OpenRouter
from clank.kernel.api import create_app
from clank.kernel.events import Actor
from clank.kernel.operations import Operation
from tests.components.runtime.conftest import Rig, add_openrouter
from tests.fakes.openrouter import FakeOpenRouter

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")
AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
DEV = "/api/v1/runtime/dev"
CODER = "example-vendor/example-coder"
CLOUD: dict[str, object] = {"title": "cloud: Example Coder", "endpoint": "openrouter", "model": CODER,
                            "options": {"context": 65536, "max_output": 16384, "reasoning": "default"}}  # fmt: skip
DENY = {"provider": {"data_collection": "deny"}}
ALLOW = {"provider": {"data_collection": "allow"}, "provider_from": "dev mode"}


@pytest.fixture
def http(rig: Rig) -> Iterator[TestClient]:
    with TestClient(create_app(rig.kernel, token="t", port=7725), base_url="http://127.0.0.1:7725") as client:
        yield client


@pytest.fixture
def cloud(rig: Rig, openrouter: FakeOpenRouter) -> Rig:
    """The rig with OpenRouter agreed, its key set and a cloud preset."""
    add_openrouter(rig)
    rig.preset("cloud-example-coder", CLOUD)
    return rig


async def run(rig: Rig, type: str, **params: Any) -> Operation:
    async with rig.kernel.operations.running():
        started = await rig.kernel.operations.start(type, params, actor=YOU)
        with anyio.fail_after(60):
            return await rig.kernel.operations.wait(started.id)


def runtime_changes(rig: Rig) -> list[Any]:
    """The changes of the runtime's settings, as events."""
    return [event for event in rig.kernel.events.latest(types=["settings.changed"]) if event.data["kind"] == "runtime"]


def dev(rig: Rig, on: bool) -> dict[str, Any]:
    """Dev mode turned on or off, as the console does."""
    return rig.runtime.endpoints.set_dev(on, actor=YOU)


async def test_dev_mode_is_off_until_turned_on_and_kept_with_who_turned_it_on(rig: Rig, http: TestClient) -> None:
    off = http.get(DEV, headers=AUTH).json()
    assert off["on"] is False
    assert off["said"].startswith("Dev mode is off: each cloud provider is asked as its record says")
    on = http.put(DEV, json={"on": True}, headers=AUTH)
    assert on.status_code == 200, on.text
    assert on.json()["on"] is True
    assert on.json()["said"].startswith(
        "Dev mode is on: Clank asks every cloud provider for any of a model's providers"
    )
    assert '"dev_mode": true' in (rig.kernel.home.config / "runtime.json").read_text(encoding="utf-8")
    assert rig.runtime.settings().dev_mode is True
    [changed] = runtime_changes(rig)
    assert changed.data["applies"] == "now"
    assert [change["field"] for change in changed.data["changes"]] == ["dev_mode"]
    assert changed.actor.via == "console"
    assert http.put(DEV, json={"on": True}, headers=AUTH).json()["on"] is True
    assert len(runtime_changes(rig)) == 1, "turning it on again changes nothing"
    assert http.put(DEV, json={"on": False}, headers=AUTH).json()["on"] is False
    assert rig.runtime.settings().dev_mode is False


async def test_while_it_is_on_the_next_request_asks_any_provider_and_off_again_the_records_policy(cloud: Rig) -> None:
    done = await run(cloud, "runtime.load", slot="main", preset="cloud-example-coder")
    assert done.status == "done", done.error
    assert cloud.runtime.route("main")["adds"] == DENY
    dev(cloud, True)
    assert cloud.runtime.route("main")["adds"] == ALLOW, "from the next request, with no load"
    dev(cloud, False)
    assert cloud.runtime.route("main")["adds"] == DENY
    assert cloud.runtime.endpoints.record("openrouter").options == {"data_collection": "deny", "zdr": False}


async def test_a_load_while_it_is_on_sends_its_tiny_request_to_any_provider(
    cloud: Rig, openrouter: FakeOpenRouter
) -> None:
    dev(cloud, True)
    done = await run(cloud, "runtime.load", slot="main", preset="cloud-example-coder")
    assert done.status == "done", done.error
    [tiny] = openrouter.chats()
    assert tiny.body["provider"] == {"data_collection": "allow"}
    launch = cloud.runtime.state.launch(cloud.runtime.state.slot("main").launch_id or 0)
    assert (launch.route or {})["adds"] == DENY, "the launch keeps the record's own, so off applies at once"


async def test_the_providers_check_asks_as_dev_mode_says_and_its_policy_item_says_so(
    cloud: Rig, openrouter: FakeOpenRouter
) -> None:
    dev(cloud, True)
    openrouter.play("answer", "tool call", "thinking")
    done = await run(cloud, "runtime.endpoint_check", id="openrouter")
    assert done.status == "done", done.error
    items = {item["name"]: (item["status"], item["said"]) for item in (done.result or {})["items"]}
    assert items["policy"][0] == "warn"
    assert items["policy"][1].startswith("dev mode: data_collection allow, whatever this record says (its own: deny)")
    assert {chat.body["provider"]["data_collection"] for chat in openrouter.chats()} == {"allow"}


async def test_each_provider_says_dev_mode_beside_its_own_policy(rig: Rig, http: TestClient) -> None:
    add_openrouter(rig, key=False)
    [before] = http.get("/api/v1/runtime/endpoints", headers=AUTH).json()
    assert before["dev_mode"] is False
    assert before["said"]["policy"].startswith("Clank asks only for providers that do not keep your data")
    http.put(DEV, json={"on": True}, headers=AUTH)
    [during] = http.get("/api/v1/runtime/endpoints", headers=AUTH).json()
    assert during["dev_mode"] is True
    assert during["options"]["data_collection"] == "deny", "the record keeps its own"
    assert during["said"]["policy"].startswith("Dev mode: Clank asks for any provider")
    assert "this record's own is deny" in during["said"]["policy"]


def test_dev_mode_relaxes_only_the_data_policy_and_a_request_says_where_it_came_from() -> None:
    relaxed = cloud_slot.dev_adds(
        {"provider": {"data_collection": "deny", "zdr": True}, "reasoning": {"effort": "low"}}
    )
    assert relaxed == {
        "provider": {"data_collection": "allow", "zdr": True}, "reasoning": {"effort": "low"},
        "provider_from": "dev mode",
    }  # fmt: skip
    assert cloud_slot.dev_adds({"provider": {"data_collection": "allow"}}) == {"provider": {"data_collection": "allow"}}
    assert cloud_slot.dev_adds({}) == {}
    sent, notes = OpenRouter().translate({"model": "x", "messages": []}, CODER, ALLOW)
    assert sent["provider"] == {"data_collection": "allow"}
    assert "provider_from" not in sent, "what the gateway adds goes to OpenRouter; where it came from does not"
    assert notes == ["provider.data_collection allow added (dev mode)"]
