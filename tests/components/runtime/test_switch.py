"""Design 0003 §6.1 and §6.4, design 0001 §4.2-§4.3: a switch stops what runs and starts the new preset; one whose new
engine fails at its start, or is not ready in time, stops what it started, starts the last configuration that worked
again (with the options it had then), and says why the new one failed in the engine's own words; with no configuration
that worked, the slot is left failed. The new preset here is "fake KVMem small" (a context of 4K), which the fake
engine's `--fake-only-context 4096` makes fail while "fake KVMem" (8K) still starts from the same install. A port still
held a moment after Clank stopped its own engine is waited for, not blamed on another program."""

import json
from collections.abc import Iterator
from pathlib import Path

import anyio
import pytest

from clank.components.runtime.gpu import GpuMemory
from clank.components.runtime.hosts.host import EngineHost, ProcessIdentity
from clank.components.runtime.hosts.local import LocalHost
from clank.components.runtime.slots import Slots
from clank.components.runtime.state import InstallRecord
from clank.kernel.events import Actor
from clank.kernel.operations import Operation
from tests.components.runtime.conftest import Rig
from tests.fakes.engine import program

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")


@pytest.fixture
def engines(rig: Rig) -> Iterator[Rig]:
    yield rig
    slot = rig.runtime.state.slot("main")
    if slot.pid is not None and slot.host is not None:
        LocalHost(slot.host).stop(ProcessIdentity(slot.host, slot.pid, slot.started or "", slot.command or ""), 5)


async def run(rig: Rig, type: str, **params: str) -> Operation:
    started = await rig.kernel.operations.start(type, {"slot": "main", **params}, actor=YOU)
    with anyio.fail_after(60):
        return await rig.kernel.operations.wait(started.id)


def identity(rig: Rig) -> ProcessIdentity:
    slot = rig.runtime.state.slot("main")
    return ProcessIdentity(slot.host or "", slot.pid or 0, slot.started or "", slot.command or "")


def small_fails(rig: Rig, tmp_path: Path, *fake: str) -> None:
    """KVMem installed again, the fake engine told to misbehave as `fake` says, at the small preset's context only."""
    install = InstallRecord(
        setup="kvmem-llamacpp",
        version="v0.16.0-rc1",
        host="local",
        program=list(program("kvmem", *fake, "--fake-only-context", "4096")),
        folder=str(tmp_path),
        how="test",
    )
    rig.runtime.state.add_install(install, rig.clock.now())


async def test_a_port_still_held_a_moment_after_clank_stopped_its_engine_is_waited_for(
    engines: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On Windows a stopped engine's port can stay held for a moment (its program's child exits a little later, longer
    on a busy machine), as the switch tests found on 2026-10-19."""
    real = Slots._holder
    lingering = [0]

    def holder(self: Slots, host: EngineHost, port: int) -> str | None:
        if lingering[0] > 0:
            lingering[0] -= 1
            return "python.exe (process 1)"
        return real(self, host, port)

    monkeypatch.setattr(Slots, "_holder", holder)
    async with engines.kernel.operations.running():
        await run(engines, "runtime.load", preset="fake KVMem")
        lingering[0] = 3
        done = await run(engines, "runtime.switch", preset="fake KVMem")
    assert done.status == "done", done.error


async def test_a_switch_stops_what_runs_and_starts_the_new_preset(engines: Rig) -> None:
    async with engines.kernel.operations.running():
        await run(engines, "runtime.load", preset="fake KVMem")
        old = identity(engines)
        done = await run(engines, "runtime.switch", preset="fake KVMem small")
    assert done.status == "done", done.error
    assert [step.name for step in done.steps] == ["plan", "stop", "start", "health", "measure"]
    assert not LocalHost().alive(old)
    slot = engines.runtime.state.slot("main")
    assert (slot.status, slot.preset) == ("ready", "fake-kvmem-small")
    assert LocalHost().alive(identity(engines))
    assert slot.last_good is not None
    assert slot.last_good.preset == "fake-kvmem-small"


async def test_a_switch_waits_for_the_gpu_to_free_what_the_stopped_engine_took(engines: Rig) -> None:
    """The driver frees a process's memory a moment after it ends: right after KVMem stopped on this machine
    (2026-10-13), the GPU still showed 6.6 GB in use, and the fit check refused the next preset."""
    held, freed = GpuMemory(16303, 15000), GpuMemory(16303, 2041)
    engines.gpu[:] = [freed, held, held, held, freed]  # the load's before and after; then still held twice; then freed
    async with engines.kernel.operations.running():
        await run(engines, "runtime.load", preset="fake KVMem")
        done = await run(engines, "runtime.switch", preset="fake KVMem small")
    assert done.status == "done", done.error
    log = [line.text for line in engines.kernel.operations.log_lines(done.id)]
    assert any(line.startswith("the GPU freed what it took (12,959 MiB) in ") for line in log), log


async def test_a_switch_whose_engine_fails_goes_back_to_the_last_that_worked_and_says_why(
    engines: Rig, tmp_path: Path
) -> None:
    async with engines.kernel.operations.running():
        await run(engines, "runtime.load", preset="fake KVMem")
        engines.preset("fake-kvmem", {"title": "fake KVMem", "engine": "kvmem-llamacpp",
                                      "engine_version": "v0.16.0-rc1", "model": "tiny",
                                      "options": {"context": 16384}})  # fmt: skip
        small_fails(engines, tmp_path, "--fake-fail-start", "oom")
        done = await run(engines, "runtime.switch", preset="fake KVMem small")
    assert done.status == "failed"
    assert "out of memory" in done.error
    assert done.error.endswith("back to fake KVMem, which runs again")
    assert [step.name for step in done.steps][-1] == "return"
    slot = engines.runtime.state.slot("main")
    assert (slot.status, slot.preset) == ("ready", "fake-kvmem")
    launch = engines.runtime.state.launch(slot.launch_id or 0)
    assert json.loads(json.dumps(launch.options)) == {"context": 8192, "kvmem.budget": 4096}, "the options it had then"
    assert LocalHost().alive(identity(engines))


async def test_a_switch_whose_engine_is_never_ready_goes_back_too(engines: Rig, tmp_path: Path) -> None:
    (engines.kernel.home.config / "runtime.json").write_text(
        json.dumps({"schema": "runtime/1", "port": engines.port, "start_seconds": 2}) + "\n", encoding="utf-8"
    )
    engines.kernel.settings.reload_changed()
    async with engines.kernel.operations.running():
        await run(engines, "runtime.load", preset="fake KVMem")
        small_fails(engines, tmp_path, "--fake-start-seconds", "30")
        done = await run(engines, "runtime.switch", preset="fake KVMem small")
    assert done.status == "failed"
    assert "was not ready within 2 seconds" in done.error
    assert engines.runtime.state.slot("main").preset == "fake-kvmem"


async def test_with_nothing_that_worked_a_failed_switch_leaves_the_slot_failed(engines: Rig, tmp_path: Path) -> None:
    small_fails(engines, tmp_path, "--fake-fail-start", "oom")
    async with engines.kernel.operations.running():
        done = await run(engines, "runtime.switch", preset="fake KVMem small")
    assert done.status == "failed"
    assert done.error.endswith("no configuration has worked yet, so the slot is left failed")
    assert engines.runtime.state.slot("main").status == "failed"


def test_the_route_starts_a_switch_and_an_unknown_slot_is_not_found(engines: Rig) -> None:
    from fastapi.testclient import TestClient

    from clank.kernel.api import create_app

    auth = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
    with TestClient(create_app(engines.kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as http:
        started = http.post("/api/v1/runtime/slots/main/switch", json={"preset": "fake KVMem small"}, headers=auth)
        assert started.json()["type"] == "runtime.switch"
        missing = http.post("/api/v1/runtime/slots/side/switch", json={"preset": "fake KVMem small"}, headers=auth)
        assert (missing.status_code, missing.json()["error"]["code"]) == (404, "not_found")
        deadline = __import__("time").monotonic() + 60
        while engines.runtime.state.slot("main").status not in ("ready", "failed"):
            assert __import__("time").monotonic() < deadline
            __import__("time").sleep(0.1)
