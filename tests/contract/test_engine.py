"""Design 0001 §8.2-8.3, design 0003 §4 and decision 0010: every engine adapter meets the same contract, run against
what its engine printed at each recorded version: its options are well formed (each key once, each default valid,
each choice listed), every flag they map to is in the engine's own `--help`, its startup log says when it is ready
and what memory it took, and what its version supports is declared."""

import json
from pathlib import Path
from typing import Any

import pytest

from clank.components.runtime.adapters import ENGINES
from clank.components.runtime.adapters.engine import EngineAdapter, flags
from tests.fakes.recorded import recordings

CASES = [
    pytest.param(adapter, folder, id=f"{adapter.NAME}-{folder.name}")
    for adapter in ENGINES.all()
    for folder in recordings(adapter.NAME)
]


def recording(folder: Path) -> dict[str, Any]:
    found: dict[str, Any] = json.loads((folder / "program.json").read_text(encoding="utf-8"))
    return found


def help_text(adapter: type[EngineAdapter], folder: Path) -> str:
    answers = recording(folder)["states"]["installed"]
    return str(answers[f"{adapter.PROGRAM} --help"][1])


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_its_options_are_well_formed(adapter: type[EngineAdapter], folder: Path) -> None:
    engine = adapter(folder.name)
    keys = [option.key for option in engine.options()]
    assert len(keys) == len(set(keys)), "each option's key appears once"
    for option in engine.options():
        assert option.label, option.key
        assert option.help, option.key
        if option.default is not None:
            assert option.problem(option.default) is None, option.key
        if option.kind == "choice":
            assert option.choices, option.key
    assert engine.validate({}) == [], "the defaults are a valid preset"


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_every_flag_its_options_map_to_is_in_its_recorded_help(adapter: type[EngineAdapter], folder: Path) -> None:
    text = help_text(adapter, folder)
    missing = [flag for option in adapter(folder.name).options() for flag in flags(option) if flag not in text]
    assert missing == [], f"{adapter.NAME} {folder.name}'s --help does not show {', '.join(missing)}"


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_its_recorded_startup_says_when_it_is_ready_and_what_memory_it_took(
    adapter: type[EngineAdapter], folder: Path
) -> None:
    engine = adapter(folder.name)
    lines = [str(line) for line in recording(folder)["startup"]]
    assert sum(engine.ready(line) for line in lines) == 1, "one line says it is ready"
    assert not any(engine.ready(line) for line in lines[: len(lines) // 2]), "it is not ready before it says so"
    report = engine.memory_report(lines)
    assert report, "its log says what memory it took"
    assert all(value > 0 for value in report.values())


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_what_its_version_supports_is_declared(adapter: type[EngineAdapter], folder: Path) -> None:
    supported = {capability.name for capability in adapter(folder.name).capabilities()}
    assert {"requests at once", "vision", "speculation"} <= supported
