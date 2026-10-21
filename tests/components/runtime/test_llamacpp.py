"""Design 0006 §3 and decision 0035: llama.cpp's adapter gives the completion preset exactly the command line
measured on this computer (the measurement of 2026-10-15, the recording's startup), estimates the system memory its log
then reports, and takes none of the GPU: its fit is "on the CPU" however full the GPU is. The completion preset is
Clank's own, for the `fast` slot, which listens on a port of its own."""

import json
from pathlib import Path

from clank.components.runtime.adapters import ENGINES
from clank.components.runtime.adapters.engine import Launch
from clank.components.runtime.adapters.llamacpp import LlamaCpp
from clank.components.runtime.catalog import catalog, preset_problems
from clank.components.runtime.gpu import GpuMemory, fit
from clank.components.runtime.kinds import Preset, RuntimeSettings

RECORDING = Path(__file__).resolve().parents[2] / "fixtures" / "llamacpp" / "b11588" / "program.json"
PRESET = Path(__file__).resolve().parents[3] / "clank" / "defaults" / "presets" / "completion-0.5b.json"
# The flags the recording's startup was made with, as typed for the measurement.
MEASURED = [
    "-c", "8192", "-t", "6", "-np", "1", "--cache-reuse", "256", "-b", "1024", "-ub", "1024",
    "--prio", "-1", "--poll", "0", "--no-webui", "-n", "128", "-lv", "4",
]  # fmt: skip


def pairs(argv: list[str] | tuple[str, ...]) -> dict[str, str]:
    """Each flag with its value (empty for a switch)."""
    found: dict[str, str] = {}
    rest = list(argv)
    while rest:
        flag = rest.pop(0)
        takes = rest and (not rest[0].startswith("-") or rest[0].lstrip("-").isdigit())
        found[flag] = rest.pop(0) if takes else ""
    return found


def launch() -> Launch:
    model = catalog()["qwen2.5-coder-0.5b"]
    return Launch(
        program=("bin/llama-server",),
        model_path="models/qwen2.5-coder-0.5b-q8_0.gguf",
        port=18201,
        facts={"folder": "/opt/llamacpp", "library_path": "bin"},
        sizes=model.sizes("llamacpp"),
    )


def test_the_completion_preset_runs_exactly_what_was_measured() -> None:
    preset = json.loads(PRESET.read_text(encoding="utf-8"))
    plan = LlamaCpp("b11588").plan(preset["options"], launch())
    assert plan.argv[:3] == ("bin/llama-server", "-m", "models/qwen2.5-coder-0.5b-q8_0.gguf")
    assert plan.argv[-4:] == ("--host", "127.0.0.1", "--port", "18201")
    assert pairs(plan.argv[3:-4]) == pairs(MEASURED)
    assert plan.env == {"LD_LIBRARY_PATH": "bin"}
    assert ENGINES.get("llamacpp") is LlamaCpp


def test_it_estimates_the_system_memory_its_log_reports_and_none_of_the_gpu() -> None:
    engine = LlamaCpp("b11588")
    estimate = engine.plan({}, launch()).memory
    reported = engine.memory_report(json.loads(RECORDING.read_text(encoding="utf-8"))["startup"])
    assert reported == {"weights": 500.79, "kv": 96.0, "compute": 90.54}
    assert estimate.kv_mib == 96
    assert abs(estimate.total_mib - sum(reported.values())) < 3
    assert not estimate.on_gpu
    for gpu in (GpuMemory(16303, 16300), GpuMemory(16303, 2041), None):
        found = fit(estimate, gpu, 500)
        assert found.verdict == "on the CPU"
        assert found.lines[-1] == "ON THE CPU: it takes none of the GPU's memory"


def test_the_completion_preset_is_valid_and_its_slot_listens_on_a_port_of_its_own() -> None:
    data = json.loads(PRESET.read_text(encoding="utf-8"))
    data.pop("schema")
    preset = Preset.model_validate(data)
    assert (preset.slot, preset.engine, preset.model) == ("fast", "llamacpp", "qwen2.5-coder-0.5b")
    assert preset_problems(preset) == []
    settings = RuntimeSettings()
    assert settings.slots == ["main", "fast", "vision"]
    assert (settings.port_of("main"), settings.port_of("fast"), settings.port_of("vision")) == (18200, 18201, 18202)
