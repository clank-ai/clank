"""Design 0016 §13 (design 0012 §4, decision 0067): the Monitor reads a cloud model's figures from its preset's facts,
as it reads an engine's: its window (the smaller of the preset's and the model's) and its most output; no thinking
budget, no exact window, not on this machine's GPU, no token count, no one conversation; its prompt, output and cache
figures read from OpenRouter's usage; where the facts were read; the context totals of a step it answered say it sits
in the cloud (`gpu.device`), all of it attended. The model's facts have no template and no calibration,
so the estimate shares the census out to OpenRouter's `prompt_tokens` at Clank's plain default, saying so. With records
off, the census of a cloud request keeps no text of the prompt (decision 0096)."""

import json
from pathlib import Path

from clank.components.agents.adapters.opencode import OpenCode
from clank.components.agents.context import totals
from clank.components.agents.estimate import estimate
from clank.components.gateway.census import census
from tests.components.gateway.test_cloud_forwarding import ASKS, WORKSPACE_KEY, cloud_slot, forwarding, recorded
from tests.components.runtime.conftest import Rig, add_openrouter
from tests.fakes.openrouter import FakeOpenRouter

CODER = "example-vendor/example-coder"
CLOUD: dict[str, object] = {"title": "cloud: Example Coder", "endpoint": "openrouter", "model": CODER,
                            "options": {"context": 65536, "max_output": 16384, "reasoning": "default"}}  # fmt: skip


def test_a_cloud_presets_facts_say_its_window_and_what_does_not_apply(rig: Rig, openrouter: FakeOpenRouter) -> None:
    add_openrouter(rig)
    rig.preset("cloud-example-coder", CLOUD)
    rig.runtime.endpoints.models("openrouter")  # the list read once: the facts are read from it
    facts = rig.runtime.facts("cloud: Example Coder")
    assert facts is not None
    engine = facts["engine"]
    assert (engine["name"], engine["label"], engine["provider"]) == ("openrouter", "OpenRouter", "cloud openrouter")
    assert (engine["window"], engine["output"], engine["thinking_budget"], engine["exact"]) == (
        65536,
        16384,
        None,
        None,
    )
    assert (engine["on_gpu"], engine["counts_tokens"], engine["one_conversation"]) == (False, False, False)
    assert engine["fields"] == {"prompt": "usage.prompt_tokens", "output": "usage.completion_tokens",
                                "cached": "usage.prompt_tokens_details.cached_tokens"}  # fmt: skip
    assert engine["source"].startswith("OpenRouter's list, read ")
    assert facts["model"] == {"id": CODER, "name": "Example Coder", "template": None, "calibration": None}
    assert (facts["preset"], facts["title"]) == ("cloud-example-coder", "cloud: Example Coder")


def test_the_context_totals_of_a_step_a_cloud_model_answered_say_it_sits_in_the_cloud(
    rig: Rig, openrouter: FakeOpenRouter
) -> None:
    add_openrouter(rig)
    rig.preset("cloud-example-coder", CLOUD)
    rig.runtime.endpoints.models("openrouter")
    facts = rig.runtime.facts("cloud-example-coder")
    step = {"id": "r-1", "time": "2026-10-21T09:00:00.000000Z", "role": "agent", "slot": "main",
            "session": "ses_made_up", "parent": "", "status": 200, "error": "", "looped": "", "left": False,
            "preset": "cloud-example-coder", "usage": {"prompt_tokens": 30000, "completion_tokens": 600}}  # fmt: skip
    routes = {"slots": {"main": {"status": "ready", "preset": "cloud-example-coder", "facts": facts}},
              "roles": {"agent": "main"}, "default_slot": "main"}  # fmt: skip
    doing = {"state": "running", "requests": [], "ended": [step], "slots": {}}
    gpu = totals("ses_made_up", doing, routes, lambda name: facts, OpenCode().compaction)["gpu"]
    assert (gpu["device"], gpu["exact"], gpu["stored"], gpu["attended"], gpu["elsewhere"]) == (
        "cloud", None, 30600, 30600, 0)  # fmt: skip


def test_a_cloud_presets_facts_without_its_list_are_none(rig: Rig) -> None:
    add_openrouter(rig, key=False)
    rig.preset("cloud-example-coder", CLOUD)
    assert rig.runtime.facts("cloud-example-coder") is None


def test_the_estimate_shares_the_census_out_to_openrouters_prompt_tokens_at_the_plain_default(
    rig: Rig, openrouter: FakeOpenRouter
) -> None:
    add_openrouter(rig)
    rig.preset("cloud-example-coder", CLOUD)
    rig.runtime.endpoints.models("openrouter")
    facts = rig.runtime.facts("cloud-example-coder")
    counted = census(
        {"messages": [{"role": "system", "content": "You are an agent. " * 40}, {"role": "user", "content": "Hi"}]},
        0.06, 2000, words=False,
    )  # fmt: skip
    found = estimate(counted, 194, facts)
    assert found is not None
    assert sum(part["tokens"] for part in found["parts"]) == 194
    assert found["calibrated"] is False
    assert "Example Coder is not calibrated, so every part counts alike by its characters" in found["how"]


def test_with_records_off_the_census_of_a_cloud_request_keeps_no_text(
    openrouter: FakeOpenRouter, tmp_path: Path
) -> None:
    secret_words = "made-up research text that must stay on this machine"
    with forwarding(cloud_slot(openrouter.url), tmp_path, records=False) as (url, _):
        import httpx2

        body = {**ASKS, "stream": False, "messages": [{"role": "user", "content": secret_words}]}
        httpx2.post(f"{url}/v1/chat/completions", json=body, headers={"Authorization": f"Bearer {WORKSPACE_KEY}"},
                    timeout=30)  # fmt: skip
        live = httpx2.get(f"{url}/activity", params={"session": "", "ended": "true"}, timeout=10).json()
    assert secret_words not in json.dumps(live)
    assert not (tmp_path / "traffic").exists() or secret_words not in json.dumps(recorded(tmp_path))
