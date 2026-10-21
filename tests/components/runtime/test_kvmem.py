"""Design 0003 §4 and design 0001 §3.6: the KVMem/llama.cpp adapter gives KVMem exactly what the prototype's daily
profile gives it (the prototype's command line for `recipe-iq3-cpuvision`, but for flags that only repeat KVMem's own
defaults), keeps CUDA graphs off by its variable, and estimates the KV cache and the MTP head's pool its log then
reports to the MiB, with the whole context and no reserve beside it when the budget is 0; the frontier preset (decision
0068) gives KVMem the whole context exactly, thinking without a limit, 32,768 tokens out, MTP and no projector; a preset
with a budget whose answers can outgrow the reserve is refused, and "frontier 262K" (decisions 0069 and 0088) keeps a
reserve that holds its longest answer, on the IQ3_S file in the same GPU memory as "frontier 96K"; "frontier 262K lean"
(decision 0078) is the IQ3_XXS file with a larger window in less of the GPU."""

import json
from dataclasses import replace
from pathlib import Path

from clank.components.runtime.adapters import ENGINES
from clank.components.runtime.adapters.engine import Launch, OptionValue
from clank.components.runtime.adapters.kvmem import KvmemLlamacpp
from clank.components.runtime.catalog import catalog
from clank.kernel.settings import DEFAULTS as SHIPPED

RECORDING = Path(__file__).resolve().parents[2] / "fixtures" / "kvmem-llamacpp" / "v0.16.0-rc1" / "program.json"
# The prototype's command line for its daily profile, as `kvmem_service.sh argv recipe-iq3-cpuvision` printed it.
PROTOTYPE = [
    "build/bin/llama-kvmem-server",
    "-m",
    "models/m.gguf",
    "--mmproj",
    "models/p.gguf",
    "--no-mmproj-offload",
    "--image-max-tokens",
    "512",
    "--kvmem-budget",
    "36864",
    "--spec-type",
    "draft-mtp",
    "--host",
    "127.0.0.1",
    "--port",
    "18200",
    "-c",
    "262144",
    "-n",
    "16384",
    "--kvmem-gen-reserve",
    "16384",
    "--kv-dtype",
    "q8_0",
    "--enable-thinking",
    "--reasoning-budget",
    "4096",
]
SWITCHES = {"--no-mmproj-offload", "--enable-thinking"}
DEFAULTS = {"--kv-dtype": "q8_0"}  # KVMem's own default, which the prototype repeats
DAILY: dict[str, OptionValue] = {"vision": "cpu", "vision.max_tokens": 512}
SIZES = {"gpu_weights_mib": 11160, "attention_layers": 16, "kv_width": 1024, "buffers_mib": 537, "overhead_mib": 632}
# The catalog's sizes for Qwen3.8 and Swift 1.5: the recurrent state and the compute buffers' fixed part, the MTP head's
# pool and the compute buffers' growth per cell, and what is left of the overhead.
MTP = {**SIZES, "buffers_mib": 277, "overhead_mib": 424, "mtp_bytes_per_cell": 4096, "compute_bytes_per_cell": 5120}
# What KVMem's log said when "frontier 96K" started on 2026-10-18 (98,304 cells), and the GPU memory it took.
FRONTIER_LOG = {"weights": 11159.69, "kv": 1728.00, "recurrent": 163.20, "compute": 594.28, "mtp": 402653184 / 2**20}
FRONTIER_TOOK_MIB = 14453
LAUNCH = Launch(
    program=("build/bin/llama-kvmem-server",),
    model_path="models/m.gguf",
    port=18200,
    facts={"projector": "models/p.gguf", "folder": "/opt/kvmem", "library_path": "build/bin"},
    sizes=SIZES,
)


def settings(argv: list[str] | tuple[str, ...]) -> dict[str, str]:
    """The flags of a command line with their values, the engine's own defaults left out."""
    found: dict[str, str] = {}
    rest = list(argv[1:])
    while rest:
        flag = rest.pop(0)
        found[flag] = "" if flag in SWITCHES else rest.pop(0)
    return {flag: value for flag, value in found.items() if DEFAULTS.get(flag) != value}


def test_the_daily_preset_gives_kvmem_what_the_prototypes_daily_profile_gives_it() -> None:
    plan = KvmemLlamacpp("v0.16.0-rc1").plan(DAILY, LAUNCH)
    assert settings(plan.argv) == settings(PROTOTYPE)
    assert plan.env["GGML_CUDA_DISABLE_GRAPHS"] == "1"
    assert (plan.cwd, plan.env["LD_LIBRARY_PATH"]) == ("/opt/kvmem", "build/bin")


def test_the_kv_cache_it_estimates_is_what_its_log_reports() -> None:
    engine = KvmemLlamacpp("v0.16.0-rc1")
    startup = json.loads(RECORDING.read_text(encoding="utf-8"))["startup"]
    reported = engine.memory_report(startup)
    estimate = engine.plan(DAILY, LAUNCH).memory
    assert estimate.kv_mib == round(reported["kv"]) == 1768
    assert estimate.weights_mib == round(reported["weights"])
    assert engine.plan({**DAILY, "kv.type": "q4_0"}, LAUNCH).memory.kv_mib == 936


def test_the_mtp_heads_own_pool_it_estimates_is_what_its_log_reports() -> None:
    engine = KvmemLlamacpp("v0.16.0-rc1")
    startup = json.loads(RECORDING.read_text(encoding="utf-8"))["startup"]
    reported = engine.memory_report(startup)
    launch = replace(LAUNCH, sizes=MTP)
    estimate = engine.plan(DAILY, launch).memory
    assert reported["mtp"] == 208  # KVMEM_TRACE mtp_pool cells=53248 ... bytes=218103808
    assert estimate.buffers_mib == round(reported["compute"] + reported["recurrent"] + reported["mtp"]) == 745
    assert estimate.total_mib == engine.plan(DAILY, LAUNCH).memory.total_mib  # the daily estimate is unchanged
    assert engine.plan({**DAILY, "spec.type": "none"}, launch).memory.buffers_mib == 537


def test_with_no_budget_its_kv_cache_is_the_whole_context_with_no_reserve_beside_it() -> None:
    engine = KvmemLlamacpp("v0.16.0-rc1")
    launch = replace(LAUNCH, sizes=MTP)
    estimate = engine.plan({"kvmem.budget": 0, "context": 65536}, launch).memory
    assert estimate.kv_mib == 2176  # 65,536 cells of 34,816 bytes: 16 layers, a key and a value of 1,024 at q8_0
    assert estimate.buffers_mib == 277 + 256 + 320  # the MTP head's pool and the compute buffers' growth, by cell
    assert estimate.notes[0].startswith("KV: 65,536 cells")


def test_the_frontier_preset_gives_kvmem_the_whole_context_and_thinking_without_a_limit() -> None:
    preset = json.loads((SHIPPED / "presets" / "frontier-96k.json").read_text(encoding="utf-8"))
    plan = KvmemLlamacpp("v0.16.0-rc1").plan(preset["options"], LAUNCH)
    flags = settings(plan.argv)
    assert preset["model"] == "swift-1.5-qwen3.8-27b"
    assert "--kvmem-budget" not in flags  # KVMem's own default, 0: the whole context, attended exactly
    assert "--reasoning-budget" not in flags  # KVMem's own default, -1: thinking without a limit
    assert "--reasoning-effort" not in flags  # the template's own default, xhigh
    assert "--mmproj" not in flags
    assert (flags["-c"], flags["-n"], flags["--kv-dtype"]) == ("98304", "32768", "q4_0")
    assert flags["--spec-type"] == "draft-mtp"
    assert "--enable-thinking" in flags
    assert plan.env["GGML_CUDA_DISABLE_GRAPHS"] == "1"


def test_the_frontier_preset_took_what_its_estimate_says_to_the_mib() -> None:
    engine = KvmemLlamacpp("v0.16.0-rc1")
    preset = json.loads((SHIPPED / "presets" / "frontier-96k.json").read_text(encoding="utf-8"))
    estimate = engine.plan(preset["options"], replace(LAUNCH, sizes=MTP)).memory
    assert estimate.kv_mib == round(FRONTIER_LOG["kv"])
    assert estimate.buffers_mib == round(FRONTIER_LOG["compute"] + FRONTIER_LOG["recurrent"] + FRONTIER_LOG["mtp"])
    assert estimate.total_mib == FRONTIER_TOOK_MIB


def test_a_preset_whose_answers_can_outgrow_kvmems_reserve_is_refused() -> None:
    engine = KvmemLlamacpp("v0.16.0-rc1")
    assert engine.validate({"max_output": 32768}) == [
        "max_output (32,768) is more than kvmem.gen_reserve (16,384): with a budget, KVMem v0.16 fails an answer "
        "that outgrows its reserve once it has retrieved older context; raise the reserve or lower the output"
    ]
    assert engine.validate({"max_output": 16384}) == []  # the daily preset's pairing
    assert engine.validate({"kvmem.budget": 0, "max_output": 32768}) == []  # its pool is the whole context
    assert engine.validate({"kvmem.gen_reserve": 0, "max_output": 512})[0].startswith(
        "max_output (512) is more than kvmem.gen_reserve (256)"  # 0 is KVMem's own 256
    )


def test_the_default_frontier_262k_is_the_iq3_s_file_with_57_344_tokens_exact_and_a_40_960_token_reserve() -> None:
    """Decision 0088, the owner's verdict from real use (2026-10-20): the preset decision 0069 sized, Swift 1.5's IQ3_S
    file at KVMem's own prompt batch, in the 98,304 cells "frontier 96K" takes."""
    engine = KvmemLlamacpp("v0.16.0-rc1")
    preset = json.loads((SHIPPED / "presets" / "frontier-262k.json").read_text(encoding="utf-8"))
    exact = json.loads((SHIPPED / "presets" / "frontier-96k.json").read_text(encoding="utf-8"))
    sizes = catalog()[preset["model"]].sizes("kvmem-llamacpp")
    plan = engine.plan(preset["options"], replace(LAUNCH, sizes=sizes))
    flags = settings(plan.argv)
    assert (preset["title"], preset["model"]) == ("frontier 262K", "swift-1.5-qwen3.8-27b")
    assert preset["model"] == exact["model"]
    assert (flags["-c"], flags["--kvmem-budget"], flags["--kvmem-gen-reserve"]) == ("262144", "57344", "40960")
    assert (flags["-n"], flags["--kv-dtype"], flags["--spec-type"]) == ("32768", "q4_0", "draft-mtp")
    assert "-b" not in flags, "KVMem's own batch of 512"
    assert "--reasoning-budget" not in flags  # KVMem's own default, -1: thinking without a limit
    assert "--mmproj" not in flags
    assert engine.validate(preset["options"]) == []
    # 98,304 cells either way: the same GPU memory as frontier 96K, whose start took 14,453 MiB
    assert plan.memory == engine.plan(exact["options"], replace(LAUNCH, sizes=sizes)).memory
    assert plan.memory.total_mib == FRONTIER_TOOK_MIB


def test_frontier_262k_lean_is_the_iq3_xxs_file_with_a_73_728_token_window_in_less_of_the_gpu() -> None:
    """Decision 0078's preset, kept beside the default by decision 0088: the smaller IQ3_XXS file, a 73,728-token window
    and a prompt batch of 256, measured on 2026-10-18 to leave about 1.2 GB of the card free beside the
    desktop, where the IQ3_S pool left 264-448 MiB."""
    engine = KvmemLlamacpp("v0.16.0-rc1")
    preset = json.loads((SHIPPED / "presets" / "frontier-262k-lean.json").read_text(encoding="utf-8"))
    sizes = catalog()[preset["model"]].sizes("kvmem-llamacpp")
    plan = engine.plan(preset["options"], replace(LAUNCH, sizes=sizes))
    flags = settings(plan.argv)
    assert (preset["title"], preset["model"]) == ("frontier 262K lean", "swift-1.5-qwen3.8-27b-iq3xxs")
    assert (flags["-c"], flags["--kvmem-budget"], flags["--kvmem-gen-reserve"]) == ("262144", "73728", "40960")
    assert (flags["-n"], flags["--kv-dtype"], flags["-b"]) == ("32768", "q4_0", "256")
    assert "--reasoning-budget" not in flags
    assert engine.validate(preset["options"]) == []
    # weights 9,560 + KV 2,016 (114,688 cells) + buffers 1,285 + overhead 424: the start measured 13,436
    assert plan.memory.total_mib == 13285
    assert "when the GPU needs room" in preset["notes"]


def test_it_is_one_of_the_serving_setups() -> None:
    assert ENGINES.get("kvmem-llamacpp") is KvmemLlamacpp
