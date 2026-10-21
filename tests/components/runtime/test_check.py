"""Design 0003 §6.5, design 0001 §3.6 and §3.8: a preset's check starts nothing and says, item by item, whether it can
run: the preset is valid; its engine is installed on a host; the program is there; the model's files are there at their
size; the engine's own `--help` lists every flag its plan gives it; and the plan fits in the GPU's free memory. Each
item that fails says why; a GPU that cannot be read leaves the fit unknown."""

import sys
from pathlib import Path

from clank.components.runtime.gpu import GpuMemory
from clank.components.runtime.launching import CheckItem
from clank.components.runtime.state import InstallRecord
from tests.components.runtime.conftest import FILES, Rig


def items(rig: Rig, name: str) -> dict[str, CheckItem]:
    return {item.name: item for item in rig.runtime.check(name)}


def test_a_preset_that_can_run_passes_every_item_and_nothing_starts(rig: Rig) -> None:
    found = rig.runtime.check("fake KVMem")
    assert [(item.name, item.status) for item in found] == [
        ("preset", "passed"),
        ("install", "passed"),
        ("program", "passed"),
        ("model", "passed"),
        ("flags", "passed"),
        ("fit", "passed"),
    ]
    assert found[1].detail == "kvmem-llamacpp v0.16.0-rc1 on local (test)"
    assert found[-1].detail.startswith("weights 1,000 + KV 5 + buffers 100 + overhead 0 = 1,105 MiB")
    assert rig.runtime.state.slot("main").status == "stopped"
    assert rig.runtime.state.launches() == []


def test_vision_adds_the_projector_to_what_is_checked(rig: Rig) -> None:
    rig.preset("seeing", {"engine": "kvmem-llamacpp", "engine_version": "v0.16.0-rc1", "model": "tiny",
                          "options": {"vision": "cpu", "vision.max_tokens": 512}})  # fmt: skip
    assert items(rig, "seeing")["projector"].status == "passed"


def test_a_preset_without_vision_checks_no_projector(rig: Rig) -> None:
    """Only an engine given a projector's path needs one."""
    found = items(rig, "fake KVMem")
    assert "projector" not in found
    assert all(item.status == "passed" for item in found.values()), found


def test_each_item_that_fails_says_why_and_the_check_stops_where_it_cannot_go_on(rig: Rig) -> None:
    rig.preset("wrong", {"engine": "kvmem-llamacpp", "engine_version": "v0.16.0-rc1", "model": "tiny",
                         "options": {"kv.type": "q2"}})  # fmt: skip
    assert [(item.name, item.status) for item in rig.runtime.check("wrong")] == [("preset", "failed")]
    rig.preset("elsewhere", {"engine": "kvmem-llamacpp", "engine_version": "v0.16.0-rc1", "model": "tiny",
                             "host": "ubuntu"})  # fmt: skip
    install = rig.runtime.check("elsewhere")[-1]
    assert (install.name, install.status) == ("install", "failed")
    assert install.detail == (
        "KVMem/llama.cpp v0.16.0-rc1 is not installed on ubuntu: `clank engine install kvmem-llamacpp --version "
        "v0.16.0-rc1`"
    )
    (rig.models / "tiny.gguf").unlink()
    model = items(rig, "fake KVMem")["model"]
    assert (model.status, model.detail) == ("failed", f"tiny.gguf is not on local at {rig.models / 'tiny.gguf'}")
    (rig.models / "tiny.gguf").write_bytes(FILES["tiny.gguf"])
    rig.gpu[0] = GpuMemory(16303, 15800)
    assert items(rig, "fake KVMem")["fit"].status == "failed"
    rig.gpu[0] = None
    assert items(rig, "fake KVMem")["fit"].status == "unknown"


def test_a_flag_its_engine_does_not_list_fails_the_check_naming_it(rig: Rig, tmp_path: Path) -> None:
    terse = InstallRecord(
        setup="kvmem-llamacpp", version="v0.16.0-rc1", host="local",
        program=[sys.executable, "-c", "print('usage: tiny')"], folder=str(tmp_path), how="test",
    )  # fmt: skip
    rig.runtime.state.add_install(terse, rig.clock.now())
    flags = items(rig, "fake KVMem")["flags"]
    assert flags.status == "failed"
    assert flags.detail.startswith("its --help does not list ")
    assert "--kvmem-budget" in flags.detail
