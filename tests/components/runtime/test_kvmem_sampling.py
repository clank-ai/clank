"""Design 0003 §4.1 and decision 0119: KVMem's GPU layers and its sampling are launch options. Left unset, KVMem gets no
flag and keeps its own defaults, which differ by thinking mode, and each option says them in words, as its recorded
`--help` gives them; set, the flag is always given, even at a value one mode's default has, since it then holds for
both modes; the GPU layers at the engine's own 99 give nothing. Each value is bounded as KVMem's server bounds it, and
a value outside is refused in a sentence naming it. With fewer layers on the GPU than the model has (the catalog's
`layers`, 66 for the Qwen3.8 files, as KVMem's log counts them), the estimate puts that share of the weights on the GPU
and names the rest in system memory, the KV cache and the buffers kept whole, and says it is an estimate; a model whose
catalog entry has no layer count keeps its weights whole and says so."""

import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from clank.components.runtime.adapters.engine import Launch, OptionValue
from clank.components.runtime.adapters.kvmem import KvmemLlamacpp
from clank.components.runtime.catalog import catalog
from clank.components.runtime.launching import options_view

RECORDING = Path(__file__).resolve().parents[2] / "fixtures" / "kvmem-llamacpp" / "v0.16.0-rc1" / "program.json"
LAUNCH = Launch(program=("llama-kvmem-server",), model_path="m.gguf", port=18200, facts={"projector": "p.gguf"})
SIZES = {"gpu_weights_mib": 11160, "attention_layers": 16, "kv_width": 1024, "buffers_mib": 277, "overhead_mib": 424,
         "mtp_bytes_per_cell": 4096, "compute_bytes_per_cell": 5120, "layers": 66}  # fmt: skip
SAMPLING = {
    "sampling.temperature": ("--temp", 0.6, "1.0 thinking, 0.7 not thinking"),
    "sampling.top_p": ("--top-p", 0.9, "0.95 thinking, 0.80 not thinking"),
    "sampling.top_k": ("--top-k", 40, "20 (thinking or not)"),
    "sampling.min_p": ("--min-p", 0.05, "0 (none)"),
    "sampling.presence_penalty": ("--presence-penalty", 1.2, "0 thinking, 1.5 not thinking"),
    "sampling.frequency_penalty": ("--frequency-penalty", 0.2, "0 (none)"),
    "sampling.repeat_penalty": ("--repeat-penalty", 1.05, "1 (none)"),
    "sampling.seed": ("--seed", 42, "random, for each request"),
}


def engine() -> KvmemLlamacpp:
    return KvmemLlamacpp("v0.16.0-rc1")


def help_line(flag: str) -> str:
    """The line of KVMem's recorded `--help` that names a flag."""
    text = json.loads(RECORDING.read_text(encoding="utf-8"))["states"]["installed"]["llama-kvmem-server --help"][1]
    return next(line for line in str(text).splitlines() if re.search(rf"(^|\s|,){re.escape(flag)}\b", line))


def test_left_unset_kvmem_gets_no_sampling_flag_and_no_gpu_layers() -> None:
    argv = engine().plan({}, LAUNCH).argv
    assert not {"-ngl", *(flag for flag, _, _ in SAMPLING.values())} & set(argv)


@pytest.mark.parametrize("key", sorted(SAMPLING))
def test_each_sampling_option_set_gives_kvmem_its_flag(key: str) -> None:
    flag, value, _ = SAMPLING[key]
    argv = engine().plan({key: value}, LAUNCH).argv
    assert argv[argv.index(flag) + 1] == str(value)


def test_a_value_one_modes_default_has_is_still_given_since_it_then_holds_for_both() -> None:
    options: dict[str, OptionValue] = {"sampling.temperature": 1.0, "sampling.presence_penalty": 0}
    argv = engine().plan(options, LAUNCH).argv
    assert argv[argv.index("--temp") + 1] == "1"
    assert argv[argv.index("--presence-penalty") + 1] == "0"


def test_the_gpu_layers_give_ngl_but_not_at_the_engines_own_99() -> None:
    assert "-ngl" not in engine().plan({"gpu_layers": 99}, LAUNCH).argv
    argv = engine().plan({"gpu_layers": 40}, LAUNCH).argv
    assert argv[argv.index("-ngl") + 1] == "40"


@pytest.mark.parametrize("key", sorted(SAMPLING))
def test_each_option_says_kvmems_own_default_as_its_recorded_help_gives_it(key: str) -> None:
    flag, _, words = SAMPLING[key]
    shown = {option["key"]: option for option in options_view(engine(), {})}[key]
    assert (shown["value"], shown["source"], shown["gives"]) == (None, "unset", [])
    assert shown["engine_default_words"] == words
    line = help_line(flag)
    for number in re.findall(r"\d+(?:\.\d+)?", words):
        assert number in line, f"{number} of {words!r} in {line!r}"
    if key == "sampling.seed":
        assert "random" in line


def test_the_gpu_layers_say_the_engines_own_99_is_every_layer() -> None:
    shown = {option["key"]: option for option in options_view(engine(), {})}["gpu_layers"]
    assert shown["engine_default_words"] == "99: every layer on the GPU"
    assert "(default 99)" in help_line("-ngl")


@pytest.mark.parametrize(
    ("options", "said"),
    [
        ({"sampling.temperature": 2.5}, "sampling.temperature is at most 2, not 2.5"),
        ({"sampling.temperature": -0.1}, "sampling.temperature is at least 0, not -0.1"),
        ({"sampling.top_p": 1.2}, "sampling.top_p is at most 1, not 1.2"),
        ({"sampling.top_k": -1}, "sampling.top_k is at least 0, not -1"),
        ({"sampling.top_k": 2.5}, "sampling.top_k is a whole number, not 2.5"),
        ({"sampling.min_p": 1.5}, "sampling.min_p is at most 1, not 1.5"),
        ({"sampling.presence_penalty": -3}, "sampling.presence_penalty is at least -2, not -3"),
        ({"sampling.frequency_penalty": 2.5}, "sampling.frequency_penalty is at most 2, not 2.5"),
        ({"sampling.repeat_penalty": 0}, "sampling.repeat_penalty is more than 0, not 0"),
        ({"sampling.seed": -1}, "sampling.seed is at least 0, not -1"),
        ({"sampling.seed": 2**32}, "sampling.seed is at most 4,294,967,295, not 4,294,967,296"),
        ({"gpu_layers": -1}, "gpu_layers is at least 0 layers, not -1"),
        ({"sampling.temperature": "warm"}, "sampling.temperature is a number, not 'warm'"),
    ],
)
def test_a_value_outside_kvmems_bounds_is_refused_in_a_sentence_naming_it(
    options: dict[str, object], said: str
) -> None:
    assert engine().validate(options) == [said]


def test_the_bounds_are_the_ones_its_recorded_help_gives() -> None:
    options = {option.key: option for option in engine().options()}
    for key in ("sampling.temperature", "sampling.top_p", "sampling.min_p", "sampling.presence_penalty",
                "sampling.frequency_penalty"):  # fmt: skip
        flag = SAMPLING[key][0]
        low, high = options[key].minimum or 0.0, options[key].maximum or 0.0
        assert f"[{low:g},{high:g}]" in help_line(flag), key
    assert options["sampling.repeat_penalty"].more_than == 0
    assert "> 0" in help_line("--repeat-penalty")


def test_with_fewer_layers_on_the_gpu_the_estimate_puts_that_share_of_the_weights_there() -> None:
    launch = replace(LAUNCH, sizes=SIZES)
    whole = engine().plan({}, launch).memory
    half = engine().plan({"gpu_layers": 33}, launch).memory
    assert half.weights_mib == 5580  # 33 of 66 layers of 11,160 MiB, layers taken as equal in size
    assert (half.kv_mib, half.buffers_mib, half.overhead_mib) == (whole.kv_mib, whole.buffers_mib, whole.overhead_mib)
    assert half.notes[0] == whole.notes[0], "the KV cache's note first, as before"
    assert half.notes[-1] == (
        "weights: 33 of 66 layers on the GPU, about 5,580 MiB; the other 33, about 5,580 MiB, in system memory, read "
        "by the CPU for every token (an estimate: layers taken as equal in size; the KV cache and the buffers counted "
        "whole on the GPU)"
    )
    assert engine().plan({"gpu_layers": 0}, launch).memory.weights_mib == 0


def test_every_layer_on_the_gpu_estimates_the_weights_whole_as_before() -> None:
    launch = replace(LAUNCH, sizes=SIZES)
    whole = engine().plan({}, launch).memory
    assert engine().plan({"gpu_layers": 66}, launch).memory == whole
    assert engine().plan({"gpu_layers": 120}, launch).memory == whole


def test_a_model_with_no_layer_count_keeps_its_weights_whole_and_says_so() -> None:
    sizes = {key: value for key, value in SIZES.items() if key != "layers"}
    estimate = engine().plan({"gpu_layers": 33}, replace(LAUNCH, sizes=sizes)).memory
    assert estimate.weights_mib == 11160
    assert estimate.notes[-1] == (
        "weights: counted whole on the GPU, since the catalog gives no layer count for this model to split them by"
    )
    assert "weights:" not in " ".join(engine().plan({}, replace(LAUNCH, sizes=sizes)).memory.notes)


def test_the_qwen3_8_files_have_the_66_layers_kvmems_log_offloads() -> None:
    startup = json.loads(RECORDING.read_text(encoding="utf-8"))["startup"]
    assert any("offloaded 66/66 layers to GPU" in line for line in startup)
    for model in ("qwen3.8-27b", "swift-1.5-qwen3.8-27b", "swift-1.5-qwen3.8-27b-iq3xxs"):
        assert catalog()[model].sizes("kvmem-llamacpp")["layers"] == 66, model
