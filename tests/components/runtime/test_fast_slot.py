"""Design 0006 §3: the `fast` slot runs an engine on the CPU beside the main one. Its load is not held back by a full
GPU, its engine listens on the slot's own port, nothing of the GPU is measured or learned from it, and the main slot is
left as it was."""

import json
from collections.abc import Iterator

import anyio
import pytest

from clank.components.runtime.gpu import GpuMemory
from clank.components.runtime.hosts.host import ProcessIdentity
from clank.components.runtime.hosts.local import LocalHost
from clank.components.runtime.state import InstallRecord
from clank.kernel.events import Actor
from tests.components.runtime.conftest import Rig
from tests.fakes.engine import program
from tests.support.served import free_port

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")


@pytest.fixture
def fast(rig: Rig) -> Iterator[Rig]:
    """The rig with the fake engine installed as llama.cpp, a completion preset for the fast slot, and the fast slot's
    own port; afterwards, any engine still running stopped."""
    config = rig.kernel.home.config / "runtime.json"
    config.write_text(json.dumps({"schema": "runtime/1", "port": rig.port, "ports": {"fast": free_port()}}) + "\n")
    rig.kernel.settings.reload_changed()
    install = InstallRecord(
        setup="llamacpp", version="b11588", host="local", program=list(program("llamacpp")), folder=".", how="test"
    )
    rig.runtime.state.add_install(install, rig.clock.now())
    rig.preset("fake-completion", {"title": "fake completion", "engine": "llamacpp", "engine_version": "b11588",
                                   "model": "tiny", "slot": "fast", "options": {"context": 2048}})  # fmt: skip
    yield rig
    for name in ("main", "fast"):
        slot = rig.runtime.state.slot(name)
        if slot.pid is not None and slot.host is not None:
            LocalHost(slot.host).stop(ProcessIdentity(slot.host, slot.pid, slot.started or "", slot.command or ""), 5)


async def test_the_fast_slot_loads_beside_a_full_gpu_on_its_own_port(fast: Rig) -> None:
    fast.gpu[:] = [GpuMemory(16303, 16250)]
    async with fast.kernel.operations.running():
        started = await fast.kernel.operations.start(
            "runtime.load", {"slot": "fast", "preset": "fake completion"}, actor=YOU
        )
        with anyio.fail_after(60):
            done = await fast.kernel.operations.wait(started.id)
    assert done.status == "done", done.error
    slot = fast.runtime.state.slot("fast")
    own = fast.runtime.settings().port_of("fast")
    assert (slot.status, slot.preset, slot.port) == ("ready", "fake-completion", own)
    assert own != fast.port
    launch = fast.runtime.state.launch(slot.launch_id or 0)
    assert (launch.estimate_mib, launch.measured_mib, launch.before_mib) == (None, None, None)
    log = [line.text for line in fast.kernel.operations.log_lines(done.id)]
    assert any("ON THE CPU" in line for line in log)
    assert any("GPU memory taken: none: it runs on the CPU" in line for line in log)
    assert fast.runtime.state.slot("main").status != "ready"
