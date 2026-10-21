"""Design 0003 §6.1 and §8.4, design 0001 §3.6 and §5.8: the next estimate for an engine on a host learns from what its
last launch there measured, and says so; `clank model load`, `switch` and `unload` follow their operations step by
step and print how they ended (exit 1 when they failed); `clank model status` prints each slot; `clank preset check`
prints each item."""

from collections.abc import Iterator, Sequence

import anyio
import pytest
from click.testing import CliRunner, Result
from fastapi.testclient import TestClient

from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.runtime.adapters.kvmem import KvmemLlamacpp
from clank.components.runtime.gpu import GpuMemory
from clank.components.runtime.hosts.host import ProcessIdentity
from clank.components.runtime.hosts.local import LocalHost
from clank.components.runtime.launching import prepare
from clank.kernel.api import create_app
from clank.kernel.events import Actor
from tests.components.runtime.conftest import Rig

YOU = Actor(kind="user", via="console")


@pytest.fixture
def engines(rig: Rig) -> Iterator[Rig]:
    yield rig
    slot = rig.runtime.state.slot("main")
    if slot.pid is not None and slot.host is not None:
        LocalHost(slot.host).stop(ProcessIdentity(slot.host, slot.pid, slot.started or "", slot.command or ""), 5)


def run(*arguments: str) -> Result:
    return CliRunner().invoke(main, list(arguments))


@pytest.mark.anyio
async def test_the_next_estimate_learns_from_what_the_last_launch_measured(engines: Rig) -> None:
    engines.gpu[:] = [GpuMemory(16303, 2041), GpuMemory(16303, 3541)]  # it took 1,500 MiB; 1,105 were estimated
    async with engines.kernel.operations.running():
        started = await engines.kernel.operations.start("runtime.load", {"preset": "fake KVMem"}, actor=YOU)
        with anyio.fail_after(60):
            await engines.kernel.operations.wait(started.id)
    memory = prepare(engines.runtime, "fake KVMem").plan.memory
    assert (memory.learned_mib, memory.total_mib) == (395, 1500)
    assert memory.notes[-1] == "learned: +395 MiB, what launch 1 on local took beyond its estimate"
    small = prepare(engines.runtime, "fake KVMem small").plan.memory
    assert small.learned_mib == 395, "what the engine took on the host, whichever of its presets ran"


@pytest.mark.anyio
async def test_an_engine_that_reserves_more_than_it_touches_teaches_what_it_needed_to_start(
    engines: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An engine that plans its memory and reserves more than it touches (as vLLM does; NInfer did, until decision
    0034) says in its log what it needed free to start: the next estimate learns from that, not from what it took."""

    def needed(self: KvmemLlamacpp, lines: Sequence[str], free_before_mib: int) -> int:
        return 1700

    monkeypatch.setattr(KvmemLlamacpp, "needed_mib", needed)
    engines.gpu[:] = [GpuMemory(16303, 2041), GpuMemory(16303, 3541)]  # it took 1,500 MiB
    async with engines.kernel.operations.running():
        started = await engines.kernel.operations.start("runtime.load", {"preset": "fake KVMem"}, actor=YOU)
        with anyio.fail_after(60):
            done = await engines.kernel.operations.wait(started.id)
    assert done.status == "done", done.error
    [launch] = engines.runtime.state.launches()
    assert (launch.measured_mib, launch.needed_mib) == (1500, 1700)
    log = [line.text for line in engines.kernel.operations.log_lines(done.id)]
    assert any(
        line.endswith("; it needed 1,700 MiB free to start, which its next estimate learns from") for line in log
    )
    memory = prepare(engines.runtime, "fake KVMem").plan.memory
    assert memory.total_mib == 1700
    assert memory.notes[-1].startswith(f"learned: +{1700 - (launch.estimate_mib or 0):,} MiB, what launch 1 on local")


def test_the_model_commands_follow_their_operations_and_print_how_they_ended(
    engines: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    with TestClient(create_app(engines.kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7720", "t", name="cli", http=http))
        checked = run("preset", "check", "fake KVMem")
        assert checked.exit_code == 0, checked.output
        assert "ok    install    kvmem-llamacpp v0.16.0-rc1 on local (test)" in checked.output
        loaded = run("model", "load", "fake KVMem")
        assert loaded.exit_code == 0, loaded.output
        assert "  1 of 4: plan" in loaded.output
        assert "main: fake KVMem is ready" in loaded.output
        status = run("model", "status")
        assert status.output.startswith("main  ready  fake KVMem  (kvmem-llamacpp v0.16.0-rc1 on local, port ")
        switched = run("model", "switch", "fake KVMem small")
        assert switched.exit_code == 0, switched.output
        assert "main: fake KVMem small is ready" in switched.output
        unloaded = run("model", "unload")
        assert unloaded.exit_code == 0, unloaded.output
        assert "main: stopped (stopped)" in unloaded.output or "main: stopped (killed)" in unloaded.output
        assert run("model", "status").output.startswith("main  stopped")
        missing = run("model", "load", "nothing like it")
        assert missing.exit_code == 1
        assert "there is no preset named 'nothing like it'" in missing.output
