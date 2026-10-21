"""Design 0003 §4.1 and decision 0119: options added to an engine adapter change nothing a shipped preset launches.
Each preset in `clank/defaults/presets/` gives, with a fixed launch, exactly the command line, the environment and the
memory estimate it gave before the GPU's layers and the sampling became options: "frontier 262K", the owner's model,
among them. Written before those options were added, and kept as they came."""

import json

import pytest

from clank.components.runtime.adapters import ENGINES
from clank.components.runtime.adapters.engine import Launch
from clank.components.runtime.catalog import catalog
from clank.kernel.settings import DEFAULTS

THINKING = ["--enable-thinking"]
NO_GRAPHS = {"GGML_CUDA_DISABLE_GRAPHS": "1"}
CPU = ["-c", "8192", "-np", "1", "--cache-reuse", "256", "-b", "1024", "-ub", "1024", "-n", "128",
       "--prio", "-1", "--poll", "0", "--no-webui", "-lv", "4"]  # fmt: skip
# Each shipped preset: its flags between the model and the address, its environment, and its memory estimate in MiB.
HELD: dict[str, tuple[list[str], dict[str, str], int]] = {
    "completion-0.5b": ([*CPU[:2], "-t", "6", *CPU[2:]], {}, 688),
    "daily-262k": (
        ["-c", "262144", "-n", "16384", "--kvmem-budget", "36864", "--kvmem-gen-reserve", "16384",
         "--spec-type", "draft-mtp", "--mmproj", "projector.gguf", "--no-mmproj-offload", "--image-max-tokens", "512",
         *THINKING, "--reasoning-budget", "4096"],
        NO_GRAPHS, 14097,
    ),
    "frontier-262k-lean": (
        ["-c", "262144", "-n", "32768", "--kvmem-budget", "73728", "--kvmem-gen-reserve", "40960",
         "--kv-dtype", "q4_0", "--spec-type", "draft-mtp", *THINKING, "-b", "256"],
        NO_GRAPHS, 13285,
    ),
    "frontier-262k": (
        ["-c", "262144", "-n", "32768", "--kvmem-budget", "57344", "--kvmem-gen-reserve", "40960",
         "--kv-dtype", "q4_0", "--spec-type", "draft-mtp", *THINKING],
        NO_GRAPHS, 14453,
    ),
    "frontier-96k": (
        ["-c", "98304", "-n", "32768", "--kvmem-gen-reserve", "16384", "--kv-dtype", "q4_0", "--spec-type",
         "draft-mtp", *THINKING],
        NO_GRAPHS, 14453,
    ),
    "vision": ([*CPU[:2], "-t", "8", *CPU[2:], "--mmproj", "projector.gguf", "--image-max-tokens", "1024"], {}, 4058),
}  # fmt: skip


def shipped() -> list[str]:
    return sorted(path.stem for path in (DEFAULTS / "presets").glob("*.json"))


def test_every_shipped_preset_is_held() -> None:
    assert shipped() == sorted(HELD)


@pytest.mark.parametrize("name", shipped())
def test_a_shipped_preset_launches_exactly_as_before(name: str) -> None:
    preset = json.loads((DEFAULTS / "presets" / f"{name}.json").read_text(encoding="utf-8"))
    engine = ENGINES.get(preset["engine"])(preset["engine_version"])
    launch = Launch(
        program=("engine",),
        model_path="model.gguf",
        port=18200,
        facts={"projector": "projector.gguf", "folder": "folder"},
        sizes=catalog()[preset["model"]].sizes(engine.NAME),
    )
    plan = engine.plan(preset["options"], launch)
    flags, env, total = HELD[name]
    assert list(plan.argv) == ["engine", "-m", "model.gguf", *flags, "--host", "127.0.0.1", "--port", "18200"]
    assert dict(plan.env) == env
    assert plan.memory.total_mib == total
    assert not any(key.startswith("sampling.") or key == "gpu_layers" for key in preset["options"])
