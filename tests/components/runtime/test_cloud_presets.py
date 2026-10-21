"""Design 0016 §7: a preset names an engine or a provider (`endpoint`), never both and never neither; a cloud preset is
for the main slot only; every preset Clank ships reads as before; a cloud preset's problems name a provider not added,
not agreed, or without a key; one is written from a model of the provider's list (never a model without tool calls),
its options from the model; each preset as clients see it says its provider and, for a cloud one, its prices; a cloud
preset needs nothing installed or downloaded; and a provider a preset names cannot be removed."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.runtime.kinds import Preset
from clank.kernel.api import create_app
from clank.kernel.settings import DEFAULTS, read_record
from tests.components.runtime.conftest import Rig, add_openrouter
from tests.fakes.openrouter import FakeOpenRouter

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
CODER = "example-vendor/example-coder"
CLOUD: dict[str, object] = {"title": "cloud: Example Coder", "endpoint": "openrouter", "model": CODER,
         "options": {"context": 65536, "max_output": 16384, "reasoning": "default"}}  # fmt: skip


@pytest.fixture
def http(rig: Rig) -> Iterator[TestClient]:
    with TestClient(create_app(rig.kernel, token="t", port=7725), base_url="http://127.0.0.1:7725") as client:
        yield client


def problems(rig: Rig) -> list[str]:
    return [f"{problem.field}: {problem.message}" for problem in rig.kernel.settings.problems()]


def test_every_preset_clank_ships_reads_as_before_with_its_engine_as_its_provider(rig: Rig) -> None:
    for path in sorted((DEFAULTS / "presets").glob("*.json")):
        found = read_record(Preset, path)
        assert not isinstance(found, list), found
        record = found[0]
        assert isinstance(record, Preset)
        assert record.engine
        assert record.engine_version
        assert not record.endpoint
    view = rig.runtime.preset("fake KVMem")
    assert (view["provider"], view["endpoint"]) == ("kvmem-llamacpp v0.16.0-rc1", "")
    assert "price" not in view


@pytest.mark.parametrize(
    ("values", "words"),
    [
        ({"engine": "kvmem-llamacpp", "engine_version": "v0.16.0-rc1", "endpoint": "openrouter"}, "never both"),
        ({}, "an engine (and its version) or an endpoint"),
        ({"engine": "kvmem-llamacpp"}, "engine_version"),
    ],
)
def test_a_preset_with_both_an_engine_and_an_endpoint_or_neither_is_refused(
    rig: Rig, values: dict[str, Any], words: str
) -> None:
    rig.preset("odd", {"title": "odd", "model": CODER, **values})
    assert any(words in problem for problem in problems(rig)), problems(rig)
    assert "odd" not in [preset["id"] for preset in rig.runtime.presets()]


@pytest.mark.parametrize("slot", ["fast", "vision"])
def test_a_cloud_preset_for_completion_or_vision_is_refused_saying_why(rig: Rig, slot: str) -> None:
    rig.preset("cloud-elsewhere", {**CLOUD, "slot": slot})
    [said] = problems(rig)
    assert "the main slot only" in said
    assert "/infill" in said
    assert "vision" in said


def test_a_cloud_presets_problems_name_the_provider_its_agreement_and_its_key(rig: Rig) -> None:
    rig.preset("cloud-example-coder", CLOUD)
    assert rig.runtime.preset("cloud-example-coder")["problems"] == [
        "there is no provider openrouter: Add a model adds one"
    ]
    add_openrouter(rig, key=False, agreed="")
    said = rig.runtime.preset("cloud: Example Coder")["problems"]
    assert said == [
        "openrouter is not agreed to: Add a model, or clank endpoint add openrouter, asks you first",
        "no key is set for openrouter: Providers and models, k; or clank endpoint key openrouter",
    ]
    rig.preset("cloud-loud", {**CLOUD, "title": "cloud loud", "options": {"reasoning": "loud"}})
    assert any("reasoning is one of" in problem for problem in rig.runtime.preset("cloud-loud")["problems"])


def test_a_cloud_preset_is_written_from_a_model_with_tool_calls_and_says_its_provider_and_prices(
    rig: Rig, http: TestClient, openrouter: FakeOpenRouter
) -> None:
    add_openrouter(rig)
    route = "/api/v1/runtime/endpoints/openrouter/presets"
    answer = http.post(route, json={"model": CODER, "context": 65536}, headers=AUTH)
    assert answer.status_code == 201, answer.text
    view = answer.json()
    assert (view["id"], view["title"], view["provider"], view["endpoint"]) == (
        "cloud-example-coder", "cloud: Example Coder", "cloud openrouter", "openrouter"
    )  # fmt: skip
    assert view["options"] == {"context": 65536, "max_output": 16384, "reasoning": "default", "images": False}
    assert view["price"] == {"in": 0.3, "out": 1.2, "cached_in": 0.03}
    assert (view["slot"], view["model"], view["problems"]) == ("main", CODER, [])
    assert "$0.30 in, $1.20 out per million tokens" in view["notes"]
    written = json.loads(Path(view["file"]).read_text(encoding="utf-8"))
    assert written["endpoint"] == "openrouter"
    assert "engine" not in written
    assert http.get("/api/v1/runtime/presets/cloud-example-coder", headers=AUTH).json() == view
    again = http.post(route, json={"model": CODER}, headers=AUTH)
    assert (again.status_code, again.json()["error"]["code"]) == (409, "exists")
    chatty = http.post(route, json={"model": "example-vendor/example-chat", "title": "chat"}, headers=AUTH)
    assert (chatty.status_code, chatty.json()["error"]["code"]) == (400, "no_tools")
    gone = http.post(route, json={"model": "example-vendor/gone", "title": "gone"}, headers=AUTH)
    assert (gone.status_code, gone.json()["error"]["code"]) == (400, "unknown_model")
    big = http.post(route, json={"model": CODER, "title": "big", "context": 999999}, headers=AUTH)
    assert (big.status_code, big.json()["error"]["code"]) == (400, "invalid")


def test_a_cloud_preset_needs_nothing_installed_or_downloaded(rig: Rig) -> None:
    add_openrouter(rig)
    rig.preset("cloud-example-coder", CLOUD)
    needs = rig.runtime.needs("cloud-example-coder")
    assert needs["engine"]["installed"]
    assert needs["model"]["downloaded"]
    assert needs["model"]["files"] == []
    assert needs["cloud"] == "nothing to install or download: the model runs at OpenRouter"


def test_a_cloud_presets_check_and_count_say_where_its_model_runs(rig: Rig) -> None:
    add_openrouter(rig)
    rig.preset("cloud-example-coder", CLOUD)
    items = [(item.name, item.status) for item in rig.runtime.check("cloud-example-coder")]
    assert items == [("preset", "passed"), ("provider", "passed")]
    counted = rig.runtime.count_tokens("cloud-example-coder", "made-up words")
    assert not counted["exact"]
    assert "runs at OpenRouter" in counted["counted"]


def test_a_provider_a_preset_names_cannot_be_removed(rig: Rig, http: TestClient) -> None:
    add_openrouter(rig)
    rig.preset("cloud-example-coder", CLOUD)
    answer = http.delete("/api/v1/runtime/endpoints/openrouter", headers=AUTH)
    assert (answer.status_code, answer.json()["error"]["code"]) == (409, "in_use")
    assert "the preset cloud-example-coder names it" in answer.json()["error"]["message"]
    assert answer.json()["error"]["presets"] == ["cloud-example-coder"]
    view = http.get("/api/v1/runtime/endpoints/openrouter", headers=AUTH).json()
    assert view["presets"] == ["cloud-example-coder"]
