"""Design 0016 §14 and decision 0105: Add a model's steps and their words are the service's, for every client (the
owner's rule of 2026-10-21, so the phone's app walks the same steps). The steps come in one order, each titled and
worded; Cloud starts at the provider, its key, or the model as the provider stands; the test loads into an empty main
slot, or asks beside a local model, naming it; Ready says Docker's state and where to get it. A model's words are its
line, itself and what one short request costs; its settings are filled from it and checked against it in words. A
local preset's steps come in order, each with its words, its question and its call, or say what to do instead when
Clank has no recipe for its engine. The key's account is one line, with OpenRouter's advice when the key has no
limit."""

from typing import Any

import pytest

from clank.components.runtime import guide

MODEL: dict[str, Any] = {
    "id": "example-vendor/example-coder", "name": "Example Coder", "description": "A made-up model. It codes.",
    "window": 262144, "output": 32768, "price": {"in": 0.3, "out": 1.2, "cached_in": 0.03, "request": 0.0},
    "thinking": True, "efforts": ["low", "medium", "high"], "images": False, "tools": True, "free": False,
    "limits": "", "retires": "2027-01-31",
}  # fmt: skip
USABLE = {"usable": False, "why": "no model runs", "main": {}, "candidates": []}
STOPPED = {"status": "stopped", "preset": None, "title": ""}


def steps(**given: Any) -> dict[str, dict[str, Any]]:
    values: dict[str, Any] = {"usable": USABLE, "endpoint": None, "servers": [], "machine": "This computer: a GPU.",
                              "docker": "running", "main": STOPPED} | given  # fmt: skip
    found = guide.guide(**values)
    return {step["id"]: step for step in found["steps"]}


def test_every_step_comes_in_order_titled_and_worded() -> None:
    found = guide.guide(USABLE, None, [{"name": "lit"}], "This computer: a GPU.", "running", STOPPED)
    assert [step["id"] for step in found["steps"]] == list(guide.STEPS)
    assert all(step["title"] == guide.TITLES[step["id"]] for step in found["steps"])
    choice = found["steps"][0]
    assert choice["said"] == ["No model is usable yet: no model runs.", "How should Clank run its model?"]
    assert [option["key"] for option in choice["options"]] == ["c", "l"]
    assert "This computer: a GPU." in choice["options"][1]["said"]
    agreement = found["steps"][2]
    assert agreement["servers"] == [{"name": "lit", "local_only": True}], "every server added is marked local"
    assert set(agreement["policy"]) == {"deny", "allow"}


@pytest.mark.parametrize(
    ("endpoint", "start"),
    [
        (None, "provider"),
        ({"key": {"set": False}}, "key"),
        ({"key": {"set": True}}, "model"),
    ],
)
def test_cloud_starts_where_the_provider_stands(endpoint: dict[str, Any] | None, start: str) -> None:
    assert guide.guide(USABLE, endpoint, [], "", "", STOPPED)["cloud_from"] == start


def test_the_test_loads_into_an_empty_slot_and_asks_beside_a_local_model() -> None:
    preset = {"id": "cloud-example-coder", "title": "cloud: Example Coder"}
    assert steps(preset=preset)["test"]["mode"] == "load"
    local = {"status": "ready", "preset": "daily-262k", "title": "daily 262K"}
    test = steps(preset=preset, main=local)["test"]
    assert test["mode"] == "ask"
    assert test["ask"].startswith("Load it now? This stops daily 262K in the main slot")
    ready = steps(preset=preset, main=local)["ready"]
    assert ready["kept"].startswith("cloud: Example Coder is written and tested; daily 262K keeps the main slot.")


def test_ready_says_dockers_state_and_where_to_get_it() -> None:
    assert guide.docker_said("running") == "Docker runs: a workspace's container can start."
    assert "it can be started from here" in guide.docker_said("stopped")
    assert "Docker Desktop (Windows, macOS" in guide.docker_said("not installed")
    assert "Docker Engine (Linux" in guide.docker_said("not installed")


def test_a_models_words_are_its_line_itself_and_what_a_short_request_costs() -> None:
    said = guide.model_said(MODEL)
    assert said["facts"] == "262K window · $0.30 in, $1.20 out · thinks"
    about = "example-vendor/example-coder: A made-up model. Window 262,144 tokens, most output 32,768."
    assert said["about"] == f"{about} OpenRouter retires it on 2027-01-31."
    assert said["test"] == "about $0.000031"
    assert guide.listed_said(3, "price", True, "small") == (
        "3 that take tool calls, cheapest first; free ones only; names with small. Prices per million tokens."
    )


def test_a_models_settings_are_filled_from_it_and_the_limits_as_they_are() -> None:
    fields = {field["id"]: field["value"] for field in guide.model_settings(MODEL)}
    assert fields == {"title": "cloud: Example Coder", "context": "262144", "max_output": "16384",
                      "reasoning": "default"}  # fmt: skip
    limits = {field["id"]: field["value"] for field in guide.limit_fields({"day_usd": 5.0, "month_usd": None})}
    assert limits == {"day_usd": "5", "month_usd": ""}


def needs(installed: bool, recipe: bool, downloaded: bool) -> dict[str, Any]:
    return {
        "preset": "daily-262k", "title": "daily 262K", "host": "ubuntu",
        "engine": {"setup": "kvmem-llamacpp", "version": "v0.16.0-rc1", "label": "KVMem/llama.cpp",
                   "installed": installed, "recipe": recipe},
        "model": {"id": "qwen3.8-27b", "name": "Qwen3.8-27B", "format": "gguf", "role": "weights",
                  "files": [{"role": "weights", "path": "m.gguf", "size": 12 << 30, "downloaded": downloaded}]},
    }  # fmt: skip


def test_a_local_presets_steps_come_in_order_each_with_its_words_and_call() -> None:
    found = guide.local_steps(needs(installed=False, recipe=True, downloaded=False), "daily-262k")
    assert [step["kind"] for step in found] == ["install", "download", "load"]
    assert found[0]["call"] == {"method": "POST", "path": "runtime/installs", "body": {
        "setup": "kvmem-llamacpp", "version": "v0.16.0-rc1", "host": "ubuntu", "yes": True}}  # fmt: skip
    assert found[1]["said"] == "download Qwen3.8-27B's weights (12.0 GB)"
    assert found[2]["call"]["body"] == {"preset": "daily-262k"}
    ready = guide.local_steps(needs(installed=True, recipe=False, downloaded=True), "daily-262k")
    assert [step["kind"] for step in ready] == ["load"]


def test_an_engine_without_a_recipe_is_a_step_that_says_what_to_do_instead() -> None:
    [step] = guide.local_steps(needs(installed=False, recipe=False, downloaded=False), "daily-262k")
    assert (step["kind"], step["call"]) == ("cannot", None)
    assert "build it, then adopt it where it is (clank engine adopt); or choose Cloud" in step["asks"]


def test_the_keys_account_is_one_line_with_openrouters_advice_when_it_has_no_limit() -> None:
    account = {"label": "made-up key label", "limit_usd": 20.0, "remaining_usd": 18.71, "used_today_usd": 0.12,
               "used_month_usd": 1.29, "free_tier": False, "budget": None}  # fmt: skip
    assert guide.account_said(account, "-key") == (
        'key "made-up key label" (ends …-key): its own limit $20.00, $18.71 left; OpenRouter counts $0.12 today, $1.29 '
        "this month (UTC days)"
    )
    assert "OpenRouter advises one" in guide.account_said({**account, "limit_usd": None})
