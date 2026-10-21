"""Design 0003 §4.1 and decision 0119: llama.cpp's sampling (build b11588) is a set of launch options with the keys
KVMem's has. Left unset, llama.cpp gets no flag and keeps its own defaults, or the model file's own where the file
carries one (`general.sampling.*`, for the temperature, top_p, top_k, min_p and the repeat penalty), which each option
says in words, its numbers as its recorded `--help` gives them; set, the flag is always given, over the model file's
own. A value outside what it means (a share from 0 to 1, a count or a temperature of 0 or more, a repeat penalty above
0, a seed of -1 for random or more) is refused in a sentence naming it."""

import json
import re
from pathlib import Path

import pytest

from clank.components.runtime.adapters.engine import Launch
from clank.components.runtime.adapters.llamacpp import LlamaCpp
from clank.components.runtime.launching import options_view

RECORDING = Path(__file__).resolve().parents[2] / "fixtures" / "llamacpp" / "b11588" / "program.json"
LAUNCH = Launch(program=("llama-server",), model_path="m.gguf", port=18201)
SAMPLING = {
    "sampling.temperature": ("--temp", 0.2, "0.80, or the model file's own"),
    "sampling.top_p": ("--top-p", 0.9, "0.95, or the model file's own"),
    "sampling.top_k": ("--top-k", 10, "40, or the model file's own"),
    "sampling.min_p": ("--min-p", 0.1, "0.05, or the model file's own"),
    "sampling.presence_penalty": ("--presence-penalty", 0.5, "0.00 (none)"),
    "sampling.frequency_penalty": ("--frequency-penalty", 0.3, "0.00 (none)"),
    "sampling.repeat_penalty": ("--repeat-penalty", 1.1, "1.00 (none), or the model file's own"),
    "sampling.seed": ("--seed", 7, "-1 (random)"),
}


def engine() -> LlamaCpp:
    return LlamaCpp("b11588")


def help_line(flag: str) -> str:
    """The line of llama.cpp's recorded `--help` that names a flag."""
    text = json.loads(RECORDING.read_text(encoding="utf-8"))["states"]["installed"]["llama-server --help"][1]
    return next(line for line in str(text).splitlines() if re.search(rf"(^|\s|,){re.escape(flag)}\b", line))


def test_left_unset_llamacpp_gets_no_sampling_flag() -> None:
    argv = engine().plan({}, LAUNCH).argv
    assert not {flag for flag, _, _ in SAMPLING.values()} & set(argv)


@pytest.mark.parametrize("key", sorted(SAMPLING))
def test_each_sampling_option_set_gives_llamacpp_its_flag(key: str) -> None:
    flag, value, _ = SAMPLING[key]
    argv = engine().plan({key: value}, LAUNCH).argv
    assert argv[argv.index(flag) + 1] == str(value)


def test_a_value_its_help_gives_as_the_default_is_still_given_over_the_model_files_own() -> None:
    argv = engine().plan({"sampling.temperature": 0.8}, LAUNCH).argv
    assert argv[argv.index("--temp") + 1] == "0.8"


@pytest.mark.parametrize("key", sorted(SAMPLING))
def test_each_option_says_llamacpps_own_default_as_its_recorded_help_gives_it(key: str) -> None:
    flag, _, words = SAMPLING[key]
    shown = {option["key"]: option for option in options_view(engine(), {})}[key]
    assert (shown["value"], shown["source"], shown["gives"]) == (None, "unset", [])
    assert shown["engine_default_words"] == words
    line = help_line(flag)
    for number in re.findall(r"-?\d+(?:\.\d+)?", words):
        assert f"default: {number}" in line, f"{number} of {words!r} in {line!r}"


@pytest.mark.parametrize(
    ("options", "said"),
    [
        ({"sampling.temperature": -0.5}, "sampling.temperature is at least 0, not -0.5"),
        ({"sampling.top_p": 1.5}, "sampling.top_p is at most 1, not 1.5"),
        ({"sampling.top_k": -1}, "sampling.top_k is at least 0, not -1"),
        ({"sampling.min_p": -0.1}, "sampling.min_p is at least 0, not -0.1"),
        ({"sampling.repeat_penalty": 0}, "sampling.repeat_penalty is more than 0, not 0"),
        ({"sampling.seed": -2}, "sampling.seed is at least -1, not -2"),
    ],
)
def test_a_value_outside_what_it_means_is_refused_in_a_sentence_naming_it(
    options: dict[str, object], said: str
) -> None:
    assert engine().validate(options) == [said]


def test_its_penalties_are_unbounded_as_its_help_leaves_them() -> None:
    assert engine().validate({"sampling.presence_penalty": 3.0, "sampling.frequency_penalty": -3.0}) == []
