"""The fake engine in the runner's rig (design 0013 §7): the runtime's tiny model, the fake engine installed on this
machine as KVMem (the runtime's own tests' engine, `tests/fakes/engine.py`), and two presets of it for the main slot,
"daily 8K" and "fast 4K", so a flow's boxes switch the main slot by the runtime's own `runtime.switch`, its engines
real processes of this machine's CPU, against a GPU whose readings the test gives (nothing reads the real one). A test
stops what the slot runs when it ends (`stop`)."""

import json
from pathlib import Path

from clank.components.runtime.gpu import GpuMemory
from clank.components.runtime.hosts.host import ProcessIdentity
from clank.components.runtime.hosts.local import LocalHost
from clank.components.runtime.service import Runtime
from clank.components.runtime.state import InstallRecord
from tests.components.flows.rig import Rig
from tests.components.runtime.conftest import FILES, tiny_model
from tests.fakes.engine import program
from tests.support.served import free_port

DAILY, FAST = "daily-8k", "fast-4k"
TITLES = {DAILY: "daily 8K", FAST: "fast 4K"}
CONTEXTS = {DAILY: 8192, FAST: 4096}
OUTPUTS = {DAILY: 2048, FAST: 1024}
SETUP, VERSION = "kvmem-llamacpp", "v0.16.0-rc1"


def runtime_of(rig: Rig) -> Runtime:
    found: Runtime = rig.kernel.parts["runtime"]
    return found


def install(rig: Rig, folder: Path, *fake: str) -> None:
    """The fake engine installed as KVMem, told to misbehave as `fake` says (the newest install is the one used)."""
    record = InstallRecord(setup=SETUP, version=VERSION, host="local", program=list(program("kvmem", *fake)),
                           folder=str(folder), how="test")  # fmt: skip
    runtime_of(rig).state.add_install(record, rig.clock.now())


def with_engines(rig: Rig, folder: Path) -> Rig:
    """The rig with the tiny model, the fake engine and the presets "daily 8K" and "fast 4K"; `folder` keeps the
    model's files."""
    runtime = runtime_of(rig)
    home = rig.kernel.home
    models = folder / "models"
    models.mkdir()
    for name, data in FILES.items():
        (models / name).write_bytes(data)
    (home.config / "runtime.json").write_text(json.dumps({"schema": "runtime/1", "port": free_port()}) + "\n",
                                              encoding="utf-8")  # fmt: skip
    for name in FILES:
        record = {"schema": "model-file/1", "model": "tiny", "file": name, "host": "local", "path": str(models / name)}
        place = home.config / "model-files" / f"{name}.json"
        place.parent.mkdir(parents=True, exist_ok=True)
        place.write_text(json.dumps(record) + "\n", encoding="utf-8")
    for id, title in TITLES.items():
        options = {"context": CONTEXTS[id], "max_output": OUTPUTS[id], "kvmem.budget": CONTEXTS[id] // 2}
        values = {"schema": "preset/1", "title": title, "engine": SETUP, "engine_version": VERSION, "model": "tiny",
                  "options": options}  # fmt: skip
        place = home.config / "presets" / f"{id}.json"
        place.parent.mkdir(parents=True, exist_ok=True)
        place.write_text(json.dumps(values, indent=2) + "\n", encoding="utf-8")
    rig.kernel.settings.reload_changed()
    runtime.models = {"tiny": tiny_model(models)}
    runtime.read_gpu = lambda: GpuMemory(16303, 2041)
    install(rig, folder)
    return rig


def runs(rig: Rig) -> str | None:
    """The preset the main slot runs, when it is ready."""
    slot = runtime_of(rig).state.slot("main")
    return slot.preset if slot.status == "ready" else None


def stop(rig: Rig) -> None:
    """Stop the engine the main slot runs, if any: a test leaves no process behind."""
    slot = runtime_of(rig).state.slot("main")
    if slot.pid is not None and slot.host is not None:
        identity = ProcessIdentity(slot.host, slot.pid, slot.started or "", slot.command or "")
        LocalHost(slot.host).stop(identity, 5)
