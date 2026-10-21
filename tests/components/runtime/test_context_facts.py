"""Design 0012 §4 and §4.4, decision 0067: each engine adapter declares its context facts for a preset's options (the
window and the output limit, the thinking budget when there is one, the exact window and how it picks, or the whole
window attended, where it runs, whether it counts tokens, whether it keeps one conversation, and where its answer
reports each figure), so the Monitor reads every figure from the loaded slot and never from one engine's numbers. Each
model of the catalog may give its template's facts (how it renders earlier thinking and tool calls, its reasoning
markers) and its calibration, and says when it has neither. Design 0012 §4.1 (revised 2026-10-20, decision 0090): each
adapter says how its engine refuses a request its context cannot hold (KVMem's 400 "prompt + max_tokens exceeds n_ctx",
llama.cpp's 400 of type `exceed_context_size_error`), so the gateway can tell OpenCode the context was full."""

from clank.components.runtime.adapters import ENGINES
from clank.components.runtime.adapters.engine import ContextFacts, ExactWindow
from clank.components.runtime.adapters.kvmem import KvmemLlamacpp
from clank.components.runtime.adapters.llamacpp import LlamaCpp
from clank.components.runtime.catalog import Calibration, ModelEntry, TemplateFacts, catalog
from clank.components.runtime.service import context_full
from tests.components.runtime.conftest import Rig


def test_kvmem_declares_its_window_its_output_its_thinking_budget_and_its_exact_window_for_a_presets_options() -> None:
    facts = KvmemLlamacpp("v0.16.0-rc1").context_facts({})
    assert (facts.window, facts.output, facts.thinking_budget) == (262144, 16384, 4096), "Clank's defaults"
    assert facts.exact == ExactWindow(tokens=36864, block=128, first=128, picks="by likeness to the last user message")
    assert (facts.on_gpu, facts.counts_tokens, facts.one_conversation) == (True, False, True)
    assert facts.fields == {
        "prompt": "usage.prompt_tokens",
        "output": "usage.completion_tokens",
        "cached": "usage.prompt_cache_hit_tokens",
    }, "KVMem reports totals only, in its usage; no timings"
    assert "prompt + max_tokens exceeds n_ctx" in facts.full, "how it says the context is full (decision 0090)"
    smaller = KvmemLlamacpp("v0.16.0-rc1").context_facts(
        {"context": 98304, "max_output": 8192, "kvmem.budget": 24576, "thinking.budget": 2048}
    )
    assert (smaller.window, smaller.output, smaller.thinking_budget) == (98304, 8192, 2048)
    assert smaller.exact is not None
    assert smaller.exact.tokens == 24576


def test_kvmem_with_a_budget_of_0_attends_its_whole_window_and_its_method_says_how_it_picks() -> None:
    whole = KvmemLlamacpp("v0.16.0-rc1").context_facts({"kvmem.budget": 0})
    assert whole.exact is None, "a budget of 0 holds the whole context on the GPU"
    assert whole.on_gpu is True
    recency = KvmemLlamacpp("v0.16.0-rc1").context_facts({"kvmem.method": "recency"})
    assert recency.exact is not None
    assert recency.exact.picks == "the most recent"


def test_kvmem_with_thinking_off_or_unlimited_has_no_thinking_budget() -> None:
    adapter = KvmemLlamacpp("v0.16.0-rc1")
    assert adapter.context_facts({"thinking": False}).thinking_budget is None
    assert adapter.context_facts({"thinking.budget": -1}).thinking_budget is None


def test_llamacpp_attends_its_whole_window_in_system_memory_counts_tokens_and_reports_its_cache_in_its_timings() -> (
    None
):
    facts = LlamaCpp("b11588").context_facts({})
    assert (facts.window, facts.output, facts.thinking_budget) == (8192, 128, None), "Clank's completion defaults"
    assert facts.exact is None, "it attends its whole window"
    assert (facts.on_gpu, facts.counts_tokens, facts.one_conversation) == (False, True, False)
    assert facts.fields == {
        "prompt": "usage.prompt_tokens",
        "output": "usage.completion_tokens",
        "cached": "timings.cache_n",
        "timings": "timings",
    }
    assert LlamaCpp("b11588").context_facts({"context": 16384}).window == 16384


def test_every_engine_adapter_declares_its_context_facts_for_its_default_options() -> None:
    for kind in ENGINES.all():
        adapter, name = kind(kind.VERSIONS[-1].name), kind.NAME
        facts = adapter.context_facts({})
        assert isinstance(facts, ContextFacts), name
        values = adapter.resolved({})
        assert (facts.window, facts.output) == (values["context"], values["max_output"]), name
        assert {"prompt", "output"} <= set(facts.fields), f"{name}: every engine says where its usage is"
        assert facts.source, f"{name}: where its facts were read"
        view = facts.view()
        assert view["window"] == facts.window, name
        assert isinstance(view["fields"], dict), name


def test_a_catalog_entry_may_give_its_templates_facts_and_its_calibration_and_says_when_it_has_neither() -> None:
    base = catalog()["qwen3.8-27b"].model_dump()
    template = {"earlier_thinking": "kept", "tool_calls": "json", "reasoning": ["<r>", "</r>"], "source": "a test"}
    calibration = {"tokens_per_character": {"tool results": 0.31, "your messages": 0.27}, "measured": "2026-10-19"}
    entry = ModelEntry.model_validate({**base, "template": template, "calibration": calibration})
    assert entry.template == TemplateFacts.model_validate(template)
    assert entry.calibration == Calibration.model_validate(calibration)
    shown = entry.facts_view()
    assert (shown["id"], shown["name"]) == ("qwen3.8-27b", "Qwen3.8-27B")
    assert shown["template"] == template
    assert shown["calibration"] == calibration
    bare = ModelEntry.model_validate({**base, "template": None, "calibration": None})
    assert (bare.facts_view()["template"], bare.facts_view()["calibration"]) == (None, None)


def test_the_qwen38_models_say_their_template_leaves_earlier_thinking_out_and_writes_calls_as_xml() -> None:
    for id in ("qwen3.8-27b", "swift-1.5-qwen3.8-27b", "swift-1.5-qwen3.8-27b-iq3xxs"):
        template = catalog()[id].template
        assert template is not None, id
        assert (template.earlier_thinking, template.tool_calls, template.reasoning) == (
            "dropped",
            "xml",
            ["<think>", "</think>"],
        ), id
        assert "to read" in template.source, f"{id}: the template inside the model file is to read (design 0012 §10)"


def test_no_model_of_the_catalog_is_calibrated_yet() -> None:
    assert {id: entry.calibration for id, entry in catalog().items()} == dict.fromkeys(catalog()), (
        "a calibration is measured on the real model (design 0012 §4.2), not yet done"
    )


def test_a_presets_facts_are_its_engines_for_its_options_and_its_models(rig: Rig) -> None:
    facts = rig.runtime.facts("fake KVMem")
    assert facts is not None
    assert (facts["preset"], facts["title"]) == ("fake-kvmem", "fake KVMem")
    engine = facts["engine"]
    assert (engine["name"], engine["label"], engine["version"]) == ("kvmem-llamacpp", "KVMem/llama.cpp", "v0.16.0-rc1")
    assert (engine["window"], engine["output"], engine["one_conversation"]) == (8192, 16384, True)
    picks = "by likeness to the last user message"
    assert engine["exact"] == {"tokens": 4096, "block": 128, "first": 128, "picks": picks}
    assert engine["fields"]["cached"] == "usage.prompt_cache_hit_tokens"
    model = rig.runtime.models["tiny"] if rig.runtime.models else None
    assert model is not None
    assert facts["model"] == {"id": "tiny", "name": model.name, "template": None, "calibration": None}
    small = rig.runtime.facts("fake-kvmem-small")
    assert small is not None
    assert small["engine"]["window"] == 4096, "by its id too"
    assert rig.runtime.facts("no such preset") is None


def test_each_engine_says_how_it_refuses_a_request_its_context_cannot_hold() -> None:
    kvmem, llamacpp = ("kvmem-llamacpp", "v0.16.0-rc1"), ("llamacpp", "b11588")
    said_by_kvmem = b'{"error":"prompt + max_tokens exceeds n_ctx"}'
    said_by_llamacpp = (
        b'{"error":{"code":400,"message":"request (300000 tokens) exceeds the available context size (262144 tokens), '
        b'try increasing it","type":"exceed_context_size_error","n_prompt_tokens":300000,"n_ctx":262144}}'
    )
    assert context_full(*kvmem, 400, said_by_kvmem)
    assert context_full(*llamacpp, 400, said_by_llamacpp)
    assert not context_full(*kvmem, 400, said_by_llamacpp), "KVMem's server has no other words for it"
    assert not context_full(*llamacpp, 400, said_by_kvmem)
    assert not context_full(*kvmem, 500, said_by_kvmem), "a refusal of a full context is a 400"
    assert not context_full(*kvmem, 400, b'{"error":"empty prompt"}')
    assert not context_full("an-engine-clank-does-not-know", "v1", 400, said_by_kvmem)
    assert not context_full("kvmem-llamacpp", "v9.9", 400, said_by_kvmem), "nor a version it was not written for"
    assert "exceed_context_size_error" in LlamaCpp("b11588").context_facts({}).full
    assert all(adapter.FULL for adapter in ENGINES.all()), "a new engine says its words with its adapter"
