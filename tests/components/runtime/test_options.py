"""Design 0001 §3.1 and §3.6, design 0003 §4 and §4.1: an engine adapter checks a preset's options against its version:
an option the version does not have, a value outside its range or choices (or not past a bound it must pass), or an
option whose requirement is not met is refused in a sentence naming it; a version no adapter knows is refused naming
the known ones; and the command line is made from what each option maps to, leaving out a value that is the engine's
own default. An option with no default, left unset, gives the engine nothing, and says in words what the engine does
then (decision 0119); set, it is given even at a value one of the engine's defaults has."""

from collections.abc import Mapping, Sequence

import pytest

from clank.components.runtime.adapters.engine import (
    ANY,
    ContextFacts,
    EngineAdapter,
    EngineError,
    EngineOption,
    EngineVersion,
    Launch,
    MemoryEstimate,
    OptionValue,
    Plan,
)
from clank.components.runtime.launching import options_view


class Toy(EngineAdapter):
    NAME = "toy"
    LABEL = "Toy engine"
    PROGRAM = "toy-server"
    FORMAT = "gguf"
    VERSIONS = (EngineVersion("v1", {"requests at once": "1", "vision": "yes", "speculation": "no"}),)

    def options(self) -> list[EngineOption]:
        return [
            EngineOption("context", "Context", "Tokens it sees.", "integer", 4096, {ANY: ("-c", "{value}")},
                         minimum=512, maximum=131072, unit="tokens", engine_default=2048),
            EngineOption("kv.type", "KV type", "The KV cache's type.", "choice", "q8_0", {ANY: ("--kv", "{value}")},
                         choices=("f16", "q8_0", "q4_0"), engine_default="q8_0"),
            EngineOption("vision", "Vision", "Images in.", "choice", "off",
                         {"off": (), "cpu": ("--mmproj", "{projector}", "--cpu-vision"),
                          "gpu": ("--mmproj", "{projector}")},
                         choices=("off", "cpu", "gpu")),
            EngineOption("vision.max_tokens", "Image tokens", "Tokens per image.", "integer", None,
                         {ANY: ("--image-tokens", "{value}")}, minimum=64, requires=("vision",)),
            EngineOption("cuda_graphs", "CUDA graphs", "Faster decoding.", "switch", False,
                         {"false": ("env:NO_GRAPHS=1",), "true": ()}),
            EngineOption("capacity", "KV capacity", "Tokens of KV.", "integer", "auto", {ANY: ("--cap", "{value}")},
                         choices=("auto",), minimum=1024),
            EngineOption("sampling.temperature", "Temperature", "How random.", "number", None,
                         {ANY: ("--temp", "{value}")}, minimum=0, maximum=2,
                         engine_default_words="1.0 thinking, 0.7 not thinking"),
            EngineOption("sampling.repeat_penalty", "Repeat penalty", "Against repeats.", "number", None,
                         {ANY: ("--repeat", "{value}")}, more_than=0, engine_default_words="1 (none)"),
        ]  # fmt: skip

    def plan(self, options: Mapping[str, OptionValue], launch: Launch) -> Plan:
        argv, env = self.arguments(options, {"projector": "/m/projector.gguf"})
        return Plan(
            (*launch.program, "-m", launch.model_path, *argv), env, "/", launch.port, MemoryEstimate(1, 2, 3, 4)
        )

    def ready(self, line: str) -> bool:
        return "listening" in line

    def memory_report(self, lines: Sequence[str]) -> dict[str, float]:
        return {}

    def context_facts(self, options: Mapping[str, OptionValue]) -> ContextFacts:
        window = int(self.resolved(options)["context"])
        fields = {"prompt": "usage.prompt_tokens", "output": "usage.completion_tokens"}
        return ContextFacts(window, 512, None, None, True, False, True, fields, "", "a toy")


LAUNCH = Launch(program=("/e/toy-server",), model_path="/m/model.gguf", port=18200)


@pytest.mark.parametrize(
    ("options", "said"),
    [
        ({"contxt": 8192}, "Toy engine v1 has no option contxt"),
        ({"context": 100}, "context is at least 512 tokens, not 100"),
        ({"context": 200000}, "context is at most 131,072 tokens, not 200,000"),
        ({"context": 4096.5}, "context is a whole number, not 4096.5"),
        ({"kv.type": "q2"}, "kv.type is one of f16, q8_0, q4_0, not 'q2'"),
        ({"cuda_graphs": "yes"}, "cuda_graphs is on or off (true or false), not 'yes'"),
        ({"capacity": "most"}, "capacity is a number or one of auto, not 'most'"),
        ({"vision.max_tokens": 512}, "vision.max_tokens needs vision"),
        ({"sampling.temperature": 2.5}, "sampling.temperature is at most 2, not 2.5"),
        ({"sampling.repeat_penalty": 0}, "sampling.repeat_penalty is more than 0, not 0"),
        ({"sampling.repeat_penalty": -1.5}, "sampling.repeat_penalty is more than 0, not -1.5"),
    ],
)
def test_a_wrong_option_or_value_is_refused_in_a_sentence_naming_it(options: dict[str, object], said: str) -> None:
    assert Toy("v1").validate(options) == [said]


def test_a_version_no_adapter_knows_is_refused_naming_the_known_ones() -> None:
    with pytest.raises(EngineError, match="Toy engine has no adapter for version v9; the known ones: v1"):
        Toy("v9")


def test_the_command_line_comes_from_each_options_mapping_leaving_out_the_engines_own_defaults() -> None:
    plan = Toy("v1").plan({"context": 32768, "vision": "cpu", "vision.max_tokens": 512, "capacity": 65536}, LAUNCH)
    assert plan.argv == (
        "/e/toy-server", "-m", "/m/model.gguf",
        "-c", "32768", "--mmproj", "/m/projector.gguf", "--cpu-vision", "--image-tokens", "512", "--cap", "65536",
    )  # fmt: skip
    assert dict(plan.env) == {"NO_GRAPHS": "1"}
    assert plan.command_line().startswith("NO_GRAPHS=1 /e/toy-server -m /m/model.gguf -c 32768")
    defaults = Toy("v1").plan({}, LAUNCH)
    assert defaults.argv == ("/e/toy-server", "-m", "/m/model.gguf", "-c", "4096", "--cap", "auto")


def test_a_wrong_preset_has_no_plan() -> None:
    with pytest.raises(EngineError, match="context is at least 512"):
        Toy("v1").plan({"context": 1}, LAUNCH)


def test_an_option_says_what_it_maps_to_and_what_its_version_supports() -> None:
    engine = Toy("v1")
    assert engine.option("context").maps_to() == "-c {value}"
    assert engine.option("vision").maps_to() == (
        "off: (nothing); cpu: --mmproj {projector} --cpu-vision; gpu: --mmproj {projector}"
    )
    assert {(c.name, c.supported) for c in engine.capabilities()} == {
        ("requests at once", True),
        ("vision", True),
        ("speculation", False),
    }
    with pytest.raises(EngineError, match="has no option nothing"):
        engine.option("nothing")


def test_a_default_whose_requirement_is_not_met_is_left_out_not_refused() -> None:
    class Defaults(Toy):
        def options(self) -> list[EngineOption]:
            found = super().options()
            return [
                EngineOption(
                    option.key, option.label, option.help, option.kind, 1024, option.maps,
                    minimum=option.minimum, requires=option.requires,
                ) if option.key == "vision.max_tokens" else option
                for option in found
            ]  # fmt: skip

    engine = Defaults("v1")
    assert engine.validate({}) == []
    assert "--image-tokens" not in engine.plan({}, LAUNCH).argv
    assert "--image-tokens" in engine.plan({"vision": "gpu"}, LAUNCH).argv


def test_an_option_left_unset_gives_nothing_and_says_in_words_what_the_engine_does_then() -> None:
    engine = Toy("v1")
    assert "--temp" not in engine.plan({}, LAUNCH).argv
    shown = {option["key"]: option for option in options_view(engine, {})}
    temperature = shown["sampling.temperature"]
    assert (temperature["value"], temperature["source"], temperature["gives"]) == (None, "unset", [])
    assert temperature["engine_default_words"] == "1.0 thinking, 0.7 not thinking"
    assert shown["context"]["engine_default_words"] == "", "an option whose default one value says has no words"


def test_an_option_set_is_given_even_at_a_value_one_of_the_engines_defaults_has() -> None:
    engine = Toy("v1")
    options: dict[str, OptionValue] = {"sampling.temperature": 1.0, "sampling.repeat_penalty": 1.1}
    assert engine.validate(options) == []
    assert engine.plan(options, LAUNCH).argv[-4:] == ("--temp", "1", "--repeat", "1.1")
    shown = {option["key"]: option for option in options_view(engine, options)}
    assert (shown["sampling.temperature"]["source"], shown["sampling.temperature"]["gives"]) == (
        "preset",
        ["--temp", "1"],
    )
