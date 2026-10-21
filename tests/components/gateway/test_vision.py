"""Design 0008 §7: the model that reads images, in the vision slot on the CPU, kept as its mode says. On demand (the
default), a request for the role `vision` makes the service load it (the gateway asks first, then waits for the load)
and it is unloaded after its idle minutes without use; always, it is loaded and kept; off, nothing loads it, a request
is refused saying how to turn it on, and the agent's model is told it reads no images. The routes say each role's
demand; the vision view says the mode, the slot and how long since it was wanted."""

import json
import time
from collections.abc import Iterator

import anyio
import pytest

from clank.components.gateway.service import Gateway
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
def vision(rig: Rig) -> Iterator[Rig]:
    """The rig with the fake engine installed as llama.cpp and a vision preset for the vision slot, on its own port;
    afterwards, any engine still running stopped."""
    config = rig.kernel.home.config / "runtime.json"
    ports = {"fast": free_port(), "vision": free_port()}
    config.write_text(json.dumps({"schema": "runtime/1", "port": rig.port, "ports": ports}) + "\n", encoding="utf-8")
    rig.kernel.settings.reload_changed()
    install = InstallRecord(
        setup="llamacpp", version="b11588", host="local", program=list(program("llamacpp")), folder=".", how="test"
    )
    rig.runtime.state.add_install(install, rig.clock.now())
    rig.preset("fake-vision", {"title": "fake vision", "engine": "llamacpp", "engine_version": "b11588",
                               "model": "tiny", "slot": "vision", "options": {"context": 2048}})  # fmt: skip
    gateway: Gateway = rig.kernel.parts["gateway"]
    gateway.set_vision({"preset": "fake-vision"}, actor=YOU)
    yield rig
    slot = rig.runtime.state.slot("vision")
    if slot.pid is not None and slot.host is not None:
        LocalHost(slot.host).stop(ProcessIdentity(slot.host, slot.pid, slot.started or "", slot.command or ""), 5)


async def settled(rig: Rig) -> None:
    """Until no operation is queued or running."""
    with anyio.fail_after(60):
        while any(op.status in ("queued", "running") for op in rig.kernel.operations.find(limit=20)):
            await anyio.sleep(0.05)


async def test_on_demand_a_request_loads_it_and_idle_unloads_it(vision: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    gateway: Gateway = vision.kernel.parts["gateway"]
    assert gateway.routes()["demand"] == {"vision": "on-demand"}
    monkeypatch.setattr(Gateway, "activity", lambda self: {"requests": []})
    async with vision.kernel.operations.running():
        assert (await gateway.wanted("vision")) == {"refused": "", "loading": "fake-vision"}
        await settled(vision)
        assert vision.runtime.state.slot("vision").status == "ready"
        assert (await gateway.wanted("vision"))["refused"] == "", "a loaded model is only marked as used"
        await gateway.keep_vision()
        await settled(vision)
        assert vision.runtime.state.slot("vision").status == "ready", "used a moment ago: kept"
        gateway._used = time.monotonic() - 11 * 60
        await gateway.keep_vision()
        await settled(vision)
        assert vision.runtime.state.slot("vision").status == "stopped", "idle for longer than its 10 minutes"
    view = gateway.vision()
    assert (view["settings"]["mode"], view["slot"]["status"]) == ("on-demand", "stopped")
    assert view["idle_seconds"] >= 600


async def test_always_loads_and_keeps_it_and_off_refuses_and_unloads(vision: Rig) -> None:
    gateway: Gateway = vision.kernel.parts["gateway"]
    async with vision.kernel.operations.running():
        gateway.set_vision({"mode": "always"}, actor=YOU)
        await gateway.keep_vision()
        await settled(vision)
        assert vision.runtime.state.slot("vision").status == "ready"
        gateway.set_vision({"mode": "off"}, actor=YOU)
        assert (await gateway.wanted("vision"))["refused"].startswith("the vision model is off")
        await gateway.keep_vision()
        await settled(vision)
        assert vision.runtime.state.slot("vision").status == "stopped"
    assert gateway.routes()["demand"] == {"vision": "off"}
    assert vision.kernel.parts["agents"].reads_images() is False, "with vision off the agent's model gets no images"
    assert (await gateway.wanted("agent")) == {"refused": ""}, "only the vision role is loaded on demand"
