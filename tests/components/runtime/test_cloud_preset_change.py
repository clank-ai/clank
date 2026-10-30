"""Design 0016 §7 (revised after approval 2026-10-29, the owner's request): a cloud preset's settings change after it is
written, through `PATCH /api/v1/runtime/presets/{name}`: any of its context, its most output (`max_output`) and its
thinking effort (`reasoning`), merged into its options and checked against its model's limits as the provider lists
them, then written over the record at its revision with who changed it. A value beyond the model is refused in the
adapter's words, and so is a most output above half the context (the agent keeps room for a whole answer in every
request); a preset that does not exist is 404, and a local one is refused, saying where its options change. The slot
that runs it follows at once (its kept route planned again, nothing sent), and keeps it as the last configuration that
worked; the change is an event naming the preset, its settings and that slot. The answer says, in the service's words,
what changed, where it applies, and, while a slot runs it, that OpenCode windows open now keep the limits they started
with until they start again. A cloud preset's view gives its settings for a form, the model's limits in their words."""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.runtime.state import LastGood
from clank.kernel.api import create_app
from tests.components.runtime.conftest import Rig, add_openrouter
from tests.fakes.openrouter import FakeOpenRouter
from tests.support.cloud import CloudBench

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
CODER = "example-vendor/example-coder"
ROUTE = "/api/v1/runtime/presets/cloud-example-coder"
WINDOWS = (
    "OpenCode windows open now keep the limits they started with until they start again; the next one started gets "
    "these."
)


@pytest.fixture
def http(rig: Rig) -> Iterator[TestClient]:
    with TestClient(create_app(rig.kernel, token="t", port=7726), base_url="http://127.0.0.1:7726") as client:
        yield client


@pytest.fixture
def written(rig: Rig, http: TestClient, openrouter: FakeOpenRouter) -> dict[str, Any]:
    """OpenRouter added, and a cloud preset of Example Coder written as Add a model writes it, its context 65,536."""
    add_openrouter(rig)
    answer = http.post("/api/v1/runtime/endpoints/openrouter/presets", json={"model": CODER, "context": 65536},
                       headers=AUTH)  # fmt: skip
    assert answer.status_code == 201, answer.text
    found: dict[str, Any] = answer.json()
    return found


def on_disk(view: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = json.loads(Path(view["file"]).read_text(encoding="utf-8"))
    return found


def test_its_most_output_is_raised_within_the_models_limit_and_written_with_who_changed_it(
    rig: Rig, http: TestClient, written: dict[str, Any]
) -> None:
    answer = http.patch(ROUTE, json={"max_output": 32768}, headers=AUTH)
    assert answer.status_code == 200, answer.text
    found = answer.json()
    assert found["preset"]["options"] == {
        "context": 65536,
        "max_output": 32768,
        "reasoning": "default",
        "images": False,
    }
    assert (found["changed"], found["was"], found["slot"]) == (["max_output"], {"max_output": 16384}, None)
    assert on_disk(written)["options"]["max_output"] == 32768
    assert found["said"][:2] == [
        "cloud: Example Coder: most output 32,768 tokens (was 16,384).",
        "It applies when the preset is next loaded.",
    ]
    assert WINDOWS not in found["said"], "no slot runs it: no OpenCode window has its limits"
    assert any("its thinking and its answer share the most output" in line.lower() for line in found["said"])
    assert any("OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX" in line for line in found["said"]), "above 32,000"
    changes = [event for event in rig.kernel.events.after(0, types=["settings.changed"])
               if event.subject and event.subject.id == "cloud-example-coder"]  # fmt: skip
    assert changes[-1].actor.describe() == "you (console)"
    assert changes[-1].data["changes"] == [
        {"field": "options", "old": written["options"], "new": found["preset"]["options"]}
    ]


def test_a_value_beyond_the_model_is_refused_in_the_adapters_words_and_nothing_is_written(
    http: TestClient, written: dict[str, Any]
) -> None:
    refused = {
        "max_output": (99999, f"max_output is at most 32,768 for {CODER}, not 99,999"),
        "context": (999999, f"context is at most 262,144 for {CODER}, not 999,999"),
        "reasoning": ("max", f"reasoning is default or one of low, medium, high for {CODER}"),
    }
    for key, (value, words) in refused.items():
        answer = http.patch(ROUTE, json={key: value}, headers=AUTH)
        assert (answer.status_code, answer.json()["error"]["code"]) == (400, "invalid"), key
        assert words in answer.json()["error"]["message"]
    assert on_disk(written)["options"] == written["options"], "nothing was written"


def test_the_most_output_is_at_most_half_the_context(http: TestClient, written: dict[str, Any]) -> None:
    halved = http.patch(ROUTE, json={"context": 32768}, headers=AUTH)
    assert halved.status_code == 200, "16,384 is half of 32,768: still allowed"
    answer = http.patch(ROUTE, json={"max_output": 20000}, headers=AUTH)
    assert (answer.status_code, answer.json()["error"]["code"]) == (400, "invalid")
    said = answer.json()["error"]["message"]
    assert "max_output is at most half the context (16,384 of 32,768), not 20,000" in said
    assert "a whole answer in every request" in said
    smaller = http.patch(ROUTE, json={"context": 16384}, headers=AUTH)
    assert smaller.status_code == 400, "the most output it has, 16,384, would be all of it"
    assert on_disk(written)["options"]["context"] == 32768


def test_an_unknown_preset_is_404_and_a_local_one_says_where_its_options_change(
    http: TestClient, written: dict[str, Any]
) -> None:
    missing = http.patch("/api/v1/runtime/presets/nothing-here", json={"max_output": 8192}, headers=AUTH)
    assert (missing.status_code, missing.json()["error"]["code"]) == (404, "not_found")
    local = http.patch("/api/v1/runtime/presets/fake-kvmem", json={"max_output": 8192}, headers=AUTH)
    assert (local.status_code, local.json()["error"]["code"]) == (400, "local_preset")
    said = local.json()["error"]["message"]
    assert said.startswith("fake KVMem is a local preset: its options are in its file (")
    assert "o on Presets, then e on Launch options" in said
    by_title = http.patch("/api/v1/runtime/presets/cloud%3A%20Example%20Coder", json={"reasoning": "low"},
                          headers=AUTH)  # fmt: skip
    assert by_title.status_code == 200, "a preset is named by its id or its title"


def test_nothing_to_change_is_refused_and_the_same_values_change_nothing(
    rig: Rig, http: TestClient, written: dict[str, Any]
) -> None:
    empty = http.patch(ROUTE, json={}, headers=AUTH)
    assert (empty.status_code, empty.json()["error"]["code"]) == (400, "invalid")
    assert "give context, max_output or reasoning" in empty.json()["error"]["message"]
    before = len(rig.kernel.events.after(0, types=["settings.changed"]))
    same = http.patch(ROUTE, json={"max_output": 16384}, headers=AUTH)
    assert same.status_code == 200
    assert same.json()["changed"] == []
    assert same.json()["said"] == ["Nothing changed: cloud: Example Coder has these settings already."]
    assert len(rig.kernel.events.after(0, types=["settings.changed"])) == before


def test_the_slot_that_runs_it_follows_from_the_next_request_and_keeps_it_as_the_last_that_worked(
    rig: Rig, http: TestClient, written: dict[str, Any], openrouter: FakeOpenRouter
) -> None:
    CloudBench(rig.kernel, openrouter).run("cloud-example-coder")
    old = dict(written["options"])
    rig.runtime.state.remember_good("main", LastGood(preset="cloud-example-coder", options=old, time=rig.clock.now()))
    assert rig.runtime.route("main")["output"] == 16384
    assert "reasoning" not in rig.runtime.route("main")["adds"]

    answer = http.patch(ROUTE, json={"max_output": 32768, "reasoning": "high"}, headers=AUTH)
    assert answer.status_code == 200, answer.text
    found = answer.json()
    assert found["slot"] == "main"
    assert found["said"][:2] == [
        "cloud: Example Coder: most output 32,768 tokens (was 16,384); thinking effort high (was default).",
        "The main slot runs it and follows the change from the next request.",
    ]
    assert WINDOWS in found["said"]
    assert any("the gateway adds it" in line for line in found["said"]), "the effort reaches open windows at once"
    route = rig.runtime.route("main")
    assert (route["output"], route["context"], route["adds"]["reasoning"]) == (32768, 65536, {"effort": "high"})
    assert route["adds"]["provider"] == {"data_collection": "deny"}
    good = rig.runtime.state.slot("main").last_good
    assert good is not None
    assert (good.options["max_output"], good.options["reasoning"]) == (32768, "high")
    assert openrouter.chats() == [], "nothing was sent: the route is planned again, no tiny request"
    [event] = rig.kernel.events.after(0, types=["runtime.preset_changed"])
    assert event.data == {
        "preset": "cloud-example-coder", "title": "cloud: Example Coder", "fields": ["max_output", "reasoning"],
        "options": found["preset"]["options"], "slot": "main",
    }  # fmt: skip
    assert event.summary == "you (console) changed the most output and the thinking effort of cloud: Example Coder"


def test_a_cloud_presets_view_gives_its_settings_with_the_models_limits_in_their_words(
    http: TestClient, written: dict[str, Any]
) -> None:
    assert written["settings"] == [
        {"id": "context", "value": "65536",
         "said": "Context, in tokens (at most 262,144, the model's window; a smaller one makes OpenCode compact sooner "
                 "and each request cost less)"},
        {"id": "max_output", "value": "16384",
         "said": "Most output, in tokens: its thinking and its answer together (at most 32,768, the model's most)"},
        {"id": "reasoning", "value": "default",
         "said": "Thinking effort, one of default, low, medium, high (less thinking leaves more of the most output for "
                 "the answer)"},
    ]  # fmt: skip
    http.patch(ROUTE, json={"context": 32768}, headers=AUTH)
    view = http.get(ROUTE, headers=AUTH).json()
    [output] = [field for field in view["settings"] if field["id"] == "max_output"]
    assert output["said"].endswith("(at most 16,384, half the context)")
    local = http.get("/api/v1/runtime/presets/fake-kvmem", headers=AUTH).json()
    assert "settings" not in local, "a local preset's options are in its file"
