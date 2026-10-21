"""Shared fixtures for the runtime's tests: a rig of a kernel with every component, a catalog of one tiny model whose
files are real (small) files, the fake engine installed on the local host as KVMem, two presets of it (a context of
8K, and a smaller one of 4K, which a test can make fail with the fake engine's `--fake-only-context 4096`), and a GPU
whose memory the test sets; and a bench, the rig with a host of its own for installs and a small recipe; and a fake
OpenRouter (`openrouter`), the adapter's URL pointed at it, with `add_openrouter` writing its record and its made-up
key."""

import hashlib
import json
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from clank import registry
from clank.components.machine import service as machine_service
from clank.components.machine.kinds import MachineProfile
from clank.components.runtime.adapters.openrouter import OpenRouter
from clank.components.runtime.catalog import EngineSizes, ModelEntry, ModelFacts, ModelFileEntry
from clank.components.runtime.gpu import GpuMemory
from clank.components.runtime.recipes import Recipe, RecipeStep
from clank.components.runtime.service import Runtime
from clank.components.runtime.state import InstallRecord
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.fakes.engine import program
from tests.fakes.openrouter import KEY as OPENROUTER_KEY
from tests.fakes.openrouter import FakeOpenRouter
from tests.fakes.openrouter import served as served_openrouter
from tests.fakes.platform import FakePlatform
from tests.support.served import free_port

FILES = {"tiny.gguf": b"gguf weights", "tiny-projector.gguf": b"projector"}


@dataclass
class Rig:
    """What a runtime test works with."""

    kernel: Kernel
    runtime: Runtime
    clock: FakeClock
    models: Path
    port: int
    gpu: list[GpuMemory | None] = field(default_factory=lambda: [GpuMemory(16303, 2041)])

    def read_gpu(self) -> GpuMemory | None:
        """The GPU's memory: each reading in turn, the last one from then on."""
        return self.gpu.pop(0) if len(self.gpu) > 1 else self.gpu[0]

    def preset(self, id: str, values: dict[str, object]) -> None:
        """Write a preset file, read at once."""
        path = self.kernel.home.config / "presets" / f"{id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema": "preset/1", **values}, indent=2) + "\n", encoding="utf-8")
        self.kernel.settings.reload_changed()


def tiny_model(folder: Path) -> ModelEntry:
    """A model of the catalog whose files are in `folder`."""

    def entry(format: str, role: str, name: str) -> ModelFileEntry:
        data = FILES[name]
        return ModelFileEntry(
            format=format,
            role=role,
            repository="tests/tiny",
            revision="0123456789abcdef",
            path=name,
            size=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    return ModelEntry(
        id="tiny",
        name="Tiny",
        facts=ModelFacts(
            architecture="a test's", parameters="0", context=262144, attention_layers=2, kv_width=64, abilities=[]
        ),
        files=[
            entry("gguf", "weights", "tiny.gguf"),
            entry("gguf", "projector", "tiny-projector.gguf"),
        ],
        engines={
            "kvmem-llamacpp": EngineSizes(sizes={"gpu_weights_mib": 1000, "buffers_mib": 100}, source="a test"),
        },
    )


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    """The kernel and the runtime, with the fake engine installed as KVMem and two presets of it."""
    monkeypatch.setattr(machine_service, "detect", lambda *args, **kwargs: MachineProfile(system="A system", cores=4))
    monkeypatch.setattr(machine_service, "run_command", lambda arguments: None)
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="stopped"))
    models = tmp_path / "models"
    models.mkdir()
    for name, data in FILES.items():
        (models / name).write_bytes(data)
    port = free_port()
    config = home.config / "runtime.json"
    config.write_text(json.dumps({"schema": "runtime/1", "port": port}) + "\n", encoding="utf-8")
    kernel = open_kernel(home, clock, registry.components())
    runtime: Runtime = kernel.parts["runtime"]
    rig = Rig(kernel, runtime, clock, models, port)
    runtime.models = {"tiny": tiny_model(models)}
    runtime.read_gpu = rig.read_gpu
    install = InstallRecord(
        setup="kvmem-llamacpp",
        version="v0.16.0-rc1",
        host="local",
        program=list(program("kvmem")),
        folder=str(tmp_path),
        how="test",
    )
    runtime.state.add_install(install, clock.now())
    for name in FILES:
        file = "model-files" / Path(f"{name}.json")
        (home.config / file).parent.mkdir(parents=True, exist_ok=True)
        record = {"schema": "model-file/1", "model": "tiny", "file": name, "host": "local", "path": str(models / name)}
        (home.config / file).write_text(json.dumps(record) + "\n", encoding="utf-8")
    rig.preset("fake-kvmem", {"title": "fake KVMem", "engine": "kvmem-llamacpp", "engine_version": "v0.16.0-rc1",
                              "model": "tiny", "options": {"context": 8192, "kvmem.budget": 4096}})  # fmt: skip
    rig.preset("fake-kvmem-small", {"title": "fake KVMem small", "engine": "kvmem-llamacpp",
                                     "engine_version": "v0.16.0-rc1", "model": "tiny",
                                     "options": {"context": 4096, "kvmem.budget": 2048}})  # fmt: skip
    yield rig
    kernel.close()


def small_recipe(build: str = "open('build.txt', 'w').write('built')") -> Recipe:
    """A recipe for KVMem of two small Python steps: fetch (makes source.txt) and build (runs `build`, makes
    build.txt); its program is the fake engine."""
    fetch = "print('fetching'); open('source.txt', 'w').write('src')"
    return Recipe(
        setup="kvmem-llamacpp",
        version="v0.16.0-rc1",
        summary="a test's recipe of two small steps",
        download="nothing",
        steps=[
            RecipeStep(name="fetch", run=[sys.executable, "-c", fetch], makes="source.txt"),
            RecipeStep(name="build", run=[sys.executable, "-c", f"print('compiling'); {build}"], makes="build.txt"),
        ],
        program=list(program("kvmem")),
        library_path=["{folder}/lib"],
        deviations=["none: a test"],
    )


@pytest.fixture
def bench(rig: Rig, tmp_path: Path) -> Rig:
    """The rig with a local host `bench` whose Clank folder is a temporary one, and the small recipe for KVMem."""
    record = {"schema": "host/1", "adapter": "local", "clank_folder": str(tmp_path / "bench-clank")}
    (rig.kernel.home.config / "hosts").mkdir(parents=True, exist_ok=True)
    (rig.kernel.home.config / "hosts" / "bench.json").write_text(json.dumps(record) + "\n", encoding="utf-8")
    rig.kernel.settings.reload_changed()
    rig.runtime.recipes = {("kvmem-llamacpp", "v0.16.0-rc1"): small_recipe()}
    return rig


@pytest.fixture
def openrouter(monkeypatch: pytest.MonkeyPatch) -> Iterator[FakeOpenRouter]:
    """A fake OpenRouter served on a free port, the adapter's URL pointed at it (design 0016 §18's test switch)."""
    with served_openrouter() as fake:
        monkeypatch.setattr(OpenRouter, "URL", fake.url)
        yield fake


def add_openrouter(rig: Rig, *, key: bool = True, agreed: str = "2026-10-21T09:12:04.120Z") -> None:
    """OpenRouter's record, agreed, written as Add a model writes it, and its made-up key kept (unless `key` is
    false); the adapter's URL is the fake's when the `openrouter` fixture runs first."""
    from clank.kernel.events import Actor

    you = Actor(kind="user", via="console")
    values = {**OpenRouter.template(), "agreed": agreed}
    rig.kernel.settings.write("endpoint", "openrouter", values, base=None, actor=you)
    if key:
        rig.kernel.secrets.put("endpoint/openrouter", "key", OPENROUTER_KEY, actor=you)
