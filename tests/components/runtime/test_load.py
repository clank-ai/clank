"""Design 0003 §6.1 and design 0001 §4.1-§4.2, §4.6: a load starts the engine by its plan, waits until it says it is
ready and answers a tiny request, measures the GPU memory it took, and the slot is ready with the engine's identity;
an unload stops it; a port another program holds refuses the start, naming it and leaving it alone; a load while the
slot runs, or while another load runs, is refused; and an engine that fails at its start leaves the slot failed with
its own words."""

from collections.abc import Iterator
from pathlib import Path

import anyio
import pytest

from clank.components.runtime import slots
from clank.components.runtime.gpu import GpuMemory
from clank.components.runtime.hosts.host import HostError, ProcessIdentity
from clank.components.runtime.hosts.local import LocalHost
from clank.components.runtime.hosts.wsl import WslHost
from clank.components.runtime.state import InstallRecord
from clank.kernel.events import Actor
from clank.kernel.operations import Busy, Operation
from tests.components.runtime.conftest import Rig
from tests.fakes.engine import program
from tests.support.ended import wait_ended

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")


@pytest.fixture
def engines(rig: Rig) -> Iterator[Rig]:
    """The rig, and afterwards any engine still running stopped."""
    yield rig
    slot = rig.runtime.state.slot("main")
    if slot.pid is not None and slot.host is not None:
        LocalHost(slot.host).stop(ProcessIdentity(slot.host, slot.pid, slot.started or "", slot.command or ""), 5)


async def run(rig: Rig, type: str, **params: str) -> Operation:
    started = await rig.kernel.operations.start(type, {"slot": "main", **params}, actor=YOU)
    with anyio.fail_after(60):
        return await rig.kernel.operations.wait(started.id)


async def test_a_load_starts_the_engine_waits_until_it_answers_and_the_slot_is_ready(engines: Rig) -> None:
    engines.gpu[:] = [GpuMemory(16303, 2041), GpuMemory(16303, 3150)]
    async with engines.kernel.operations.running():
        done = await run(engines, "runtime.load", preset="fake KVMem")
    assert done.status == "done", done.error
    assert [step.name for step in done.steps] == ["plan", "start", "health", "measure"]
    slot = engines.runtime.state.slot("main")
    assert (slot.status, slot.preset, slot.host, slot.port) == ("ready", "fake-kvmem", "local", engines.port)
    identity = ProcessIdentity("local", slot.pid or 0, slot.started or "", slot.command or "")
    assert LocalHost().alive(identity)
    launch = engines.runtime.state.launch(slot.launch_id or 0)
    assert (launch.outcome, launch.measured_mib, launch.before_mib) == ("ready", 1109, 2041)
    assert "listening on" in Path(launch.log).read_text(encoding="utf-8")
    assert slot.last_good is not None
    assert slot.last_good.preset == "fake-kvmem"
    log = [line.text for line in engines.kernel.operations.log_lines(done.id)]
    assert any(line.startswith("plan: ") and "--kvmem-budget 4096" in line for line in log)
    assert any(line.startswith("memory: weights 1,000 + KV 5") for line in log)


async def test_a_stop_the_host_cannot_answer_for_fails_and_keeps_the_engine_in_its_slot(
    engines: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    engines.gpu[:] = [GpuMemory(16303, 2041), GpuMemory(16303, 3150)]
    async with engines.kernel.operations.running():
        await run(engines, "runtime.load", preset="fake KVMem")
        running = engines.runtime.state.slot("main").pid

        def unanswered(self: LocalHost, identity: ProcessIdentity, seconds: float) -> str:
            raise HostError("WSL did not answer: the engine may still run")

        with monkeypatch.context() as patch:  # this unload only: `undo()` would undo the rig's own patches too
            patch.setattr(LocalHost, "stop", unanswered)
            done = await run(engines, "runtime.unload")
    assert done.status == "failed"
    assert "the engine may still run" in (done.error or "")
    slot = engines.runtime.state.slot("main")
    assert (slot.status, slot.pid) == ("ready", running)


async def test_an_unload_stops_the_engine_and_the_slot_is_stopped(engines: Rig) -> None:
    async with engines.kernel.operations.running():
        await run(engines, "runtime.load", preset="fake KVMem small")
        slot = engines.runtime.state.slot("main")
        identity = ProcessIdentity("local", slot.pid or 0, slot.started or "", slot.command or "")
        done = await run(engines, "runtime.unload")
    assert done.status == "done", done.error
    assert engines.runtime.state.slot("main").status == "stopped"
    assert not LocalHost().alive(identity)
    assert engines.runtime.state.launch(slot.launch_id or 0).outcome == "stopped"


async def test_a_port_another_program_holds_refuses_the_start_naming_it(engines: Rig) -> None:
    import socket

    with socket.socket() as taken:
        taken.bind(("127.0.0.1", engines.port))
        taken.listen()
        async with engines.kernel.operations.running():
            done = await run(engines, "runtime.load", preset="fake KVMem")
    assert done.status == "failed"
    assert f"port {engines.port} is held by" in done.error
    assert "Clank never stops a program it did not start" in done.error
    assert engines.runtime.state.slot("main").status == "stopped"
    assert engines.runtime.state.launches() == []


class Distribution(WslHost):
    """A WSL host in which `listening` listens on every port (nothing when it is None)."""

    def __init__(self, listening: str | None) -> None:
        super().__init__(lambda argv, timeout=0.0: None, "Ubuntu")
        self.listening = listening

    def listener(self, port: int) -> str | None:
        return self.listening


def test_wsls_own_relay_is_no_holder_of_a_port_no_program_in_wsl_listens_on(
    engines: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WSL's relay (`wslrelay.exe`) listens on Windows' side of a port for about a second after the program in WSL
    that listened on it ended, as when a switch has just stopped the engine before it."""
    holder = slots.Slots(engines.runtime)._holder
    monkeypatch.setattr(LocalHost, "listener", lambda self, port: "wslrelay.exe (process 56988)")
    assert holder(Distribution(None), 18200) is None
    assert holder(Distribution("llama-server (process 4242)"), 18200) == "llama-server (process 4242)"
    assert holder(LocalHost(), 18200) == "wslrelay.exe (process 56988)", "an engine on Windows cannot have that port"
    monkeypatch.setattr(LocalHost, "listener", lambda self, port: "python.exe (process 7)")
    assert holder(Distribution(None), 18200) == "python.exe (process 7)"


async def test_a_load_while_the_slot_runs_or_another_load_runs_is_refused(engines: Rig) -> None:
    async with engines.kernel.operations.running():
        first = await engines.kernel.operations.start(
            "runtime.load", {"slot": "main", "preset": "fake KVMem"}, actor=YOU
        )
        with pytest.raises(Busy, match=first.id):
            await engines.kernel.operations.start(
                "runtime.load", {"slot": "main", "preset": "fake KVMem small"}, actor=YOU
            )
        with anyio.fail_after(60):
            await engines.kernel.operations.wait(first.id)
        again = await run(engines, "runtime.load", preset="fake KVMem small")
    assert again.status == "failed"
    assert again.error == "main runs fake KVMem: unload it first, or switch to fake KVMem small"


async def test_an_engine_that_fails_at_its_start_leaves_the_slot_failed_in_its_own_words(
    engines: Rig, tmp_path: Path
) -> None:
    failing = InstallRecord(
        setup="kvmem-llamacpp",
        version="v0.16.0-rc1",
        host="local",
        program=list(program("kvmem", "--fake-fail-start", "oom")),
        folder=str(tmp_path),
        how="test",
    )
    engines.runtime.state.add_install(failing, engines.clock.now())
    async with engines.kernel.operations.running():
        done = await run(engines, "runtime.load", preset="fake KVMem")
    assert done.status == "failed"
    assert "out of memory" in done.error
    slot = engines.runtime.state.slot("main")
    assert (slot.status, slot.preset) == ("failed", "fake-kvmem")
    assert "out of memory" in slot.reason
    [launch] = engines.runtime.state.launches()
    assert (launch.outcome, "out of memory" in launch.detail) == ("failed", True)


async def test_the_last_words_of_an_engine_that_ends_while_it_starts_are_read_once_it_has_ended(
    engines: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The engine wrote its last words and ended between Clank's look at its log and its look at the process."""
    failing = InstallRecord(
        setup="kvmem-llamacpp",
        version="v0.16.0-rc1",
        host="local",
        program=list(program("kvmem", "--fake-fail-start", "oom")),
        folder=str(tmp_path),
        how="test",
    )
    engines.runtime.state.add_install(failing, engines.clock.now())
    read = slots._lines
    looks: list[Path] = []

    def first_look_too_early(log: Path) -> list[str]:
        looks.append(log)
        return [] if len(looks) == 1 else read(log)

    alive = LocalHost.alive

    def answered_once_ended(host: LocalHost, identity: ProcessIdentity) -> bool:
        wait_ended(identity.pid)
        return alive(host, identity)

    monkeypatch.setattr(slots, "_lines", first_look_too_early)
    monkeypatch.setattr(LocalHost, "alive", answered_once_ended)
    async with engines.kernel.operations.running():
        done = await run(engines, "runtime.load", preset="fake KVMem")
    assert done.status == "failed"
    assert "out of memory" in done.error


def test_the_routes_load_and_unload_by_operations_and_list_the_slots(engines: Rig) -> None:
    from fastapi.testclient import TestClient

    from clank.kernel.api import create_app

    auth = {"Authorization": "Bearer t", "X-Clank-Client": "vscode", "X-Clank-Request-Key": "press-1"}
    with TestClient(create_app(engines.kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as http:
        started = http.post("/api/v1/runtime/slots/main/load", json={"preset": "fake KVMem"}, headers=auth).json()
        assert (started["type"], started["started_by"]["via"]) == ("runtime.load", "vscode")

        def status() -> str:
            return str(http.get(f"/api/v1/records/operation/{started['id']}", headers=auth).json()["values"]["status"])

        deadline = __import__("time").monotonic() + 60
        while status() not in ("done", "failed"):
            assert __import__("time").monotonic() < deadline
            __import__("time").sleep(0.1)
        slot, fast, vision = http.get("/api/v1/runtime/slots", headers=auth).json()
        assert [(each["name"], each["status"]) for each in (fast, vision)] == [
            ("fast", "stopped"),
            ("vision", "stopped"),
        ]
        assert (slot["name"], slot["status"], slot["preset"]) == ("main", "ready", "fake-kvmem")
        unloading = http.post("/api/v1/runtime/slots/main/unload", headers={**auth, "X-Clank-Request-Key": "press-2"})
        assert unloading.json()["type"] == "runtime.unload"
