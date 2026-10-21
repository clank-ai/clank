"""Design 0003 §3 and §7.3, design 0001 §2 and §3.6: the catalog lists the models Clank knows, each file in each format
with where it comes from, its size and its checksum, and the sizes each engine's memory estimate needs; each preset
Clank ships names a serving setup, a version and a model it knows, with valid options; and a preset whose engine
cannot read any of its model's files, or that names what Clank does not know, is refused before any plan, each problem
in a sentence."""

import json

from clank.components.runtime.adapters import ENGINES
from clank.components.runtime.catalog import catalog, preset_problems
from clank.components.runtime.kinds import Preset
from clank.kernel.settings import DEFAULTS

QWEN = "qwen3.8-27b"
SWIFT = "swift-1.5-qwen3.8-27b"
SWIFT_XXS = "swift-1.5-qwen3.8-27b-iq3xxs"


def test_the_catalog_has_qwen_with_its_vision_projector_with_sources_sizes_and_checksums() -> None:
    model = catalog()[QWEN]
    found = {(file.format, file.role): file for file in model.files}
    assert set(found) == {("gguf", "weights"), ("gguf", "projector")}
    weights = found[("gguf", "weights")]
    assert (weights.repository, weights.revision, weights.size) == (
        "ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF",
        "d562806dbafae37109975e970aae91b43e73b440",
        12120016960,
    )
    assert weights.sha256 == "58fd826723939933dc86f45b7fe04545cbc2de1c70f6fe2cdd3858c87a98c12f"
    assert all(len(file.sha256) == 64 and file.size > 0 for file in model.files)
    assert model.facts.context == 262144
    sizes = model.sizes("kvmem-llamacpp")
    assert sizes["attention_layers"] == 16
    assert sizes["gpu_weights_mib"] > 0


def test_the_catalog_has_swift_1_5_with_its_mtp_head_and_no_projector() -> None:
    model = catalog()[SWIFT]
    assert [(file.format, file.role) for file in model.files] == [("gguf", "weights")]
    weights = model.files[0]
    assert (weights.repository, weights.revision, weights.path, weights.size) == (
        "ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF",
        "d74895bbe5db4bec1e0024e7cc87d59c02d7631a",
        "Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf",
        12120016896,
    )
    assert weights.sha256 == "9aecf1cd41b2cb2f32a74e0d889e33855ebef43b26f43b43feb5720239e677e5"
    assert "vision" not in model.facts.abilities
    assert (model.facts.attention_layers, model.facts.kv_width) == (16, 1024)
    assert model.sizes("kvmem-llamacpp")["mtp_bytes_per_cell"] == 4096


def test_qwen_and_swift_take_the_same_memory_on_kvmem_but_swift_has_no_projector() -> None:
    qwen = catalog()[QWEN].sizes("kvmem-llamacpp")
    assert catalog()[SWIFT].sizes("kvmem-llamacpp") == {
        key: size for key, size in qwen.items() if key != "projector_mib"
    }


def test_the_catalog_has_swift_1_5_iq3_xxs_which_takes_1_6_gb_less_of_the_gpu() -> None:
    model = catalog()[SWIFT_XXS]
    weights = model.files[0]
    assert (weights.repository, weights.revision, weights.path, weights.size) == (
        "ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF",
        "d74895bbe5db4bec1e0024e7cc87d59c02d7631a",
        "Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_XXS-mtp.gguf",
        10442827776,
    )
    assert weights.sha256 == "e23eb251493b8a89f7d0217590b593e696ac9bacaeac8605541e477533dc5838"
    swift = catalog()[SWIFT].sizes("kvmem-llamacpp")
    assert model.sizes("kvmem-llamacpp") == {**swift, "gpu_weights_mib": 9560}  # 11,160 less 1,600


def test_each_preset_clank_ships_is_known_and_valid() -> None:
    shipped = sorted((DEFAULTS / "presets").glob("*.json"))
    assert {path.stem for path in shipped} >= {"daily-262k", "frontier-96k", "frontier-262k", "frontier-262k-lean"}
    for path in shipped:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data.pop("schema") == "preset/1", path.name
        assert preset_problems(Preset.model_validate(data)) == [], path.name


def test_a_preset_its_engine_cannot_run_is_refused_in_sentences() -> None:
    unknown_model = Preset(engine="kvmem-llamacpp", engine_version="v0.16.0-rc1", model="no-such-model")
    assert preset_problems(unknown_model) == ["the catalog has no model no-such-model"]
    wrong_version = Preset(engine="kvmem-llamacpp", engine_version="v9", model=QWEN)
    assert preset_problems(wrong_version) == [
        "KVMem/llama.cpp has no adapter for version v9; the known ones: v0.16.0-rc1"
    ]
    unknown = Preset(engine="vllm", engine_version="v1", model=QWEN)
    assert preset_problems(unknown) == [
        f"there is no engine adapter named 'vllm'; the known ones: {', '.join(a.NAME for a in ENGINES.all())}"
    ]
    bad_option = Preset(engine="kvmem-llamacpp", engine_version="v0.16.0-rc1", model=QWEN, options={"kv.type": "q2"})
    assert preset_problems(bad_option) == ["kv.type is one of f16, q8_0, q5_0, q4_0, not 'q2'"]


def test_a_model_without_a_file_its_engine_reads_is_refused() -> None:
    model = catalog()[QWEN].model_copy(update={"files": [f for f in catalog()[QWEN].files if f.role == "projector"]})
    preset = Preset(engine="kvmem-llamacpp", engine_version="v0.16.0-rc1", model=QWEN)
    assert preset_problems(preset, {QWEN: model}) == [
        f"{QWEN} has no gguf file in the catalog, the format KVMem/llama.cpp reads"
    ]
