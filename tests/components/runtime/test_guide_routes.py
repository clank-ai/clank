"""Design 0016 §14 and §15 (plan s35, task 18): Add a model's steps and words come from the service, so every client
walks them alike: `GET /runtime/guide` gives each step in order with its words, from the service's state (no model
usable yet and why, this computer, the MCP servers the agreement marks local, the main slot, Docker, the limits the
settings fill; once a preset is written, its test: a load into a free main slot, or a short request beside the local
model that runs); `GET /runtime/guide/local` gives the main slot's presets, each with its fit and what it still needs
here. The runtime's views carry their own words: each listed model (its line, itself, what its test costs, its
settings), the list, the key's account, the provider's data policy, a cloud preset's prices, and a cloud load's answer,
time and cost."""

from collections.abc import Iterator
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient

from clank.components.runtime import guide
from clank.kernel.api import create_app
from clank.kernel.events import Actor
from tests.components.runtime.conftest import Rig, add_openrouter
from tests.fakes.openrouter import KEY, FakeOpenRouter

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
YOU = Actor(kind="user", via="console")
CODER = "example-vendor/example-coder"
CLOUD: dict[str, object] = {"title": "cloud: Example Coder", "endpoint": "openrouter", "model": CODER,
                            "options": {"context": 65536, "max_output": 16384, "reasoning": "default"}}  # fmt: skip


@pytest.fixture
def http(rig: Rig) -> Iterator[TestClient]:
    with TestClient(create_app(rig.kernel, token="t", port=7725), base_url="http://127.0.0.1:7725") as client:
        yield client


def steps(found: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {step["id"]: step for step in found["steps"]}


def test_the_guide_says_each_step_in_order_from_the_services_state(rig: Rig, http: TestClient) -> None:
    rig.kernel.parts["tools"].add("lit", {"command": "python", "args": ["-V"]}, scope="user", folder="", actor=YOU)
    http.put("/api/v1/gateway/cost/limits", json={"day_usd": 5.0}, headers=AUTH)
    answer = http.get("/api/v1/runtime/guide", headers=AUTH)
    assert answer.status_code == 200, answer.text
    found = answer.json()
    assert [step["id"] for step in found["steps"]] == list(guide.STEPS)
    assert [step["title"] for step in found["steps"]] == [guide.TITLES[id] for id in guide.STEPS]
    assert found["usable"]["usable"] is True, "the rig's presets can load"
    shown = steps(found)
    assert shown["choice"]["said"] == ["How should Clank run its model?"]
    assert [option["key"] for option in shown["choice"]["options"]] == ["c", "l"]
    assert shown["agreement"]["servers"] == [{"name": "lit", "local_only": True}]
    assert shown["agreement"]["servers_said"].startswith("MCP servers (each one you have is marked local only")
    assert shown["test"]["mode"] == "load"
    assert shown["ready"]["docker"] == "stopped"
    assert shown["ready"]["said"][0].startswith("Docker is stopped: it can be started from here")
    limits = {field["id"]: field for field in shown["settings"]["limits"]}
    assert (limits["day_usd"]["value"], limits["month_usd"]["value"]) == ("5", "")
    assert limits["day_usd"]["said"] == "A day's cost limit, US dollars (empty: none)"


def test_once_a_preset_is_written_its_test_loads_it_or_asks_beside_the_local_model(
    rig: Rig, http: TestClient, openrouter: FakeOpenRouter
) -> None:
    add_openrouter(rig)
    rig.preset("cloud-example-coder", CLOUD)
    test = steps(http.get("/api/v1/runtime/guide", params={"preset": "cloud-example-coder"}, headers=AUTH).json())
    assert test["test"]["mode"] == "load"
    assert test["test"]["said"] == ["Loading cloud: Example Coder into the main slot; its health is one short request"]
    rig.runtime.state.set_slot("main", "ready", "fake KVMem answered", actor=YOU, preset="fake-kvmem")
    beside = steps(http.get("/api/v1/runtime/guide", params={"preset": "cloud-example-coder"}, headers=AUTH).json())
    assert beside["test"]["mode"] == "ask"
    assert beside["test"]["said"] == ["fake KVMem runs in the main slot: testing with one short request"]
    assert beside["ready"]["kept"].startswith("cloud: Example Coder is written and tested; fake KVMem keeps the main")


def test_the_local_step_lists_the_main_slots_presets_with_what_each_needs(rig: Rig, http: TestClient) -> None:
    answer = http.get("/api/v1/runtime/guide/local", headers=AUTH)
    assert answer.status_code == 200, answer.text
    presets = {preset["id"]: preset for preset in answer.json()["presets"]}
    assert {"fake-kvmem", "fake-kvmem-small"} <= set(presets)
    shown = presets["fake-kvmem"]
    assert shown["title"] == "fake KVMem"
    assert shown["said"]
    assert [step["kind"] for step in shown["steps"]] == ["load"], "its engine is installed and its files downloaded"


def test_each_listed_model_carries_its_words_and_settings(
    rig: Rig, http: TestClient, openrouter: FakeOpenRouter
) -> None:
    add_openrouter(rig)
    found = http.get("/api/v1/runtime/endpoints/openrouter/models", headers=AUTH).json()
    assert found["said"] == "2 that take tool calls, programming models, most used first. Prices per million tokens."
    coder, small = found["models"]
    assert coder["said"]["name"] == "Example Coder"
    assert coder["said"]["facts"] == "262K window · $0.30 in, $1.20 out · thinks"
    assert coder["said"]["about"].startswith("example-vendor/example-coder: A made-up model for coding.")
    assert coder["said"]["test"] == "about $0.000031"
    assert [field["id"] for field in coder["settings"]] == ["title", "context", "max_output", "reasoning"]
    assert [field["value"] for field in coder["settings"]] == ["cloud: Example Coder", "262144", "16384", "default"]
    assert small["said"]["facts"].startswith("33K window · free (20 a minute")
    assert "most output not said" in small["said"]["about"], "a model whose output is not listed"
    assert small["said"]["test"] == "nothing (a free model)"


def test_the_account_and_the_providers_view_carry_their_words(
    rig: Rig, http: TestClient, openrouter: FakeOpenRouter
) -> None:
    add_openrouter(rig, key=False)
    taken = http.put("/api/v1/runtime/endpoints/openrouter/key", json={"key": KEY}, headers=AUTH).json()
    said = 'key "made-up key label" (ends …-key): its own limit $20.00, $18.71 left; OpenRouter counts $0.12 today'
    assert taken["account"]["said"].startswith(said)
    assert (
        http.get("/api/v1/runtime/endpoints/openrouter/account", headers=AUTH).json()["said"]
        == (taken["account"]["said"])
    )
    view = http.get("/api/v1/runtime/endpoints/openrouter", headers=AUTH).json()
    assert view["said"]["policy"] == guide.POLICY["deny"]
    assert http.get("/api/v1/runtime/endpoints", headers=AUTH).json()[0]["said"] == view["said"]


def test_a_cloud_preset_says_its_prices(rig: Rig, http: TestClient, openrouter: FakeOpenRouter) -> None:
    add_openrouter(rig)
    written = http.post("/api/v1/runtime/endpoints/openrouter/presets", json={"model": CODER}, headers=AUTH).json()
    assert written["price_said"] == "$0.30 in, $1.20 out per million tokens"
    [listed] = [each for each in http.get("/api/v1/runtime/presets", headers=AUTH).json() if each.get("endpoint")]
    assert listed["price_said"] == written["price_said"]
    engine = http.get("/api/v1/runtime/presets/fake-kvmem", headers=AUTH).json()
    assert "price_said" not in engine


@pytest.mark.anyio
async def test_a_cloud_loads_result_says_its_answer_its_time_and_its_cost(rig: Rig, openrouter: FakeOpenRouter) -> None:
    add_openrouter(rig)
    rig.preset("cloud-example-coder", CLOUD)
    async with rig.kernel.operations.running():
        started = await rig.kernel.operations.start("runtime.load", {"slot": "main", "preset": "cloud-example-coder"},
                                                    actor=YOU)  # fmt: skip
        with anyio.fail_after(60):
            done = await rig.kernel.operations.wait(started.id)
    assert done.status == "done", done.error
    assert (done.result or {})["said"].startswith("it answered a tiny request: OK in ")
    assert (done.result or {})["said"].endswith(", $0.000021")
