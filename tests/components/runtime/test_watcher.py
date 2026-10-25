"""Design 0003 §6.2-§6.3 and design 0001 §4.4, §4.6: the runtime watches each running slot. An engine that ends makes
the slot failed with its own last words, and the launch crashed; one that had been ready ten minutes or more is started
again once, saying so; a second crash within the hour leaves it failed and asks the user, who can start it again; an
engine whose health fails three times in a row is stopped and the slot failed. When the service starts, an engine
still running is adopted, not restarted, and a slot whose engine ended meanwhile is said to have stopped while the
service was not running. A host that cannot say whether the engine runs (a busy WSL leaves a question unanswered)
says nothing about it: the slot is kept, and asked again.

Design 0021 §10: a preset on trial names a fallback; when its engine crashes, the slot loads the fallback, saying
why."""

from collections.abc import Iterator
from pathlib import Path

import anyio
import pytest

from clank.components.runtime.hosts.host import ProcessIdentity
from clank.components.runtime.hosts.local import LocalHost
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


def kvmem_runs(rig: Rig, tmp_path: Path, *fake: str) -> None:
    install = InstallRecord(
        setup="kvmem-llamacpp",
        version="v0.16.0-rc1",
        host="local",
        program=list(program("kvmem", *fake)),
        folder=str(tmp_path),
        how="test",
    )
    rig.runtime.state.add_install(install, rig.clock.now())


def identity(rig: Rig) -> ProcessIdentity:
    slot = rig.runtime.state.slot("main")
    return ProcessIdentity(slot.host or "", slot.pid or 0, slot.started or "", slot.command or "")


async def load(rig: Rig) -> Operation:
    started = await rig.kernel.operations.start("runtime.load", {"slot": "main", "preset": "fake KVMem"}, actor=YOU)
    with anyio.fail_after(60):
        return await rig.kernel.operations.wait(started.id)


async def until(holds: object, seconds: float = 30) -> None:
    with anyio.fail_after(seconds):
        while not holds():  # type: ignore[operator]
            await anyio.sleep(0.05)


async def test_an_engine_that_ends_leaves_the_slot_failed_in_its_own_words(engines: Rig, tmp_path: Path) -> None:
    kvmem_runs(engines, tmp_path, "--fake-crash-after", "2")  # after its load has ended, even on a busy machine
    async with engines.kernel.operations.running():
        await load(engines)
        await until(lambda: not LocalHost().alive(identity(engines)))
        await engines.runtime.watch_once()
    slot = engines.runtime.state.slot("main")
    assert (slot.status, slot.preset) == ("failed", "fake-kvmem")
    assert "GGML_ASSERT(stat == cudaSuccess) failed" in slot.reason
    assert engines.runtime.state.launches()[0].outcome == "crashed"


async def test_one_ready_ten_minutes_is_started_again_once_and_says_so(engines: Rig) -> None:
    async with engines.kernel.operations.running():
        await load(engines)
        first = identity(engines)
        engines.clock.advance(11 * 60)
        LocalHost().stop(first, 5)  # a crash, as far as the runtime can tell
        await engines.runtime.watch_once()
        await until(lambda: engines.runtime.state.slot("main").status == "ready")
    assert identity(engines).pid != first.pid
    summaries = [event.summary for event in engines.kernel.events.latest(20, types=["runtime.slot"])]
    assert any("starting it again once" in summary for summary in summaries)


async def test_a_second_crash_within_the_hour_leaves_it_failed_and_asks(engines: Rig) -> None:
    async with engines.kernel.operations.running():
        await load(engines)
        engines.clock.advance(11 * 60)
        LocalHost().stop(identity(engines), 5)
        await engines.runtime.watch_once()
        await until(lambda: engines.runtime.state.slot("main").status == "ready")
        engines.clock.advance(15 * 60)
        LocalHost().stop(identity(engines), 5)
        await engines.runtime.watch_once()
        await until(lambda: bool(engines.kernel.questions.waiting()))
        [question] = engines.kernel.questions.waiting()
        assert question.title == "fake KVMem crashed again within an hour: start it again?"
        assert engines.runtime.state.slot("main").status == "failed"
        engines.kernel.questions.answer(question.id, by=YOU, option="start")
        await until(lambda: engines.runtime.state.slot("main").status == "ready")


async def test_a_crash_of_a_preset_that_names_a_fallback_loads_the_fallback_and_says_why(
    engines: Rig, tmp_path: Path
) -> None:
    kvmem_runs(engines, tmp_path, "--fake-crash-after", "2")  # after its load has ended, even on a busy machine
    trial = {"title": "fake KVMem trial", "engine": "kvmem-llamacpp", "engine_version": "v0.16.0-rc1", "model": "tiny",
             "fallback": "fake-kvmem-small", "options": {"context": 8192, "kvmem.budget": 4096}}  # fmt: skip
    engines.preset("fake-kvmem-trial", trial)
    async with engines.kernel.operations.running():
        started = await engines.kernel.operations.start(
            "runtime.load", {"slot": "main", "preset": "fake KVMem trial"}, actor=YOU
        )
        with anyio.fail_after(60):
            await engines.kernel.operations.wait(started.id)
        await until(lambda: not LocalHost().alive(identity(engines)))
        await engines.runtime.watch_once()
        await until(lambda: engines.runtime.state.slot("main").preset == "fake-kvmem-small")
    operations = engines.kernel.operations.find(limit=20)
    [fallback] = [
        each for each in operations if each.type == "runtime.load" and each.params["preset"] == "fake-kvmem-small"
    ]
    assert "fake KVMem trial crashed" in str(fallback.params.get("why"))
    assert "loading its fallback, fake KVMem small" in str(fallback.params.get("why"))


async def test_an_engine_whose_health_fails_three_times_is_stopped_and_the_slot_failed(
    engines: Rig, tmp_path: Path
) -> None:
    kvmem_runs(engines, tmp_path, "--fake-deaf-after", "1")
    async with engines.kernel.operations.running():
        await load(engines)
        deaf = identity(engines)
        await anyio.sleep(1.5)
        for _ in range(3):
            await engines.runtime.watch_once(health=True)
    slot = engines.runtime.state.slot("main")
    assert slot.status == "failed"
    assert "did not answer its health check 3 times in a row" in slot.reason
    assert not LocalHost().alive(deaf)


async def test_after_a_restart_of_the_service_a_running_engine_is_adopted_and_an_ended_one_said(engines: Rig) -> None:
    async with engines.kernel.operations.running():
        await load(engines)
    running = identity(engines)
    await engines.runtime.adopt()
    slot = engines.runtime.state.slot("main")
    assert (slot.status, slot.pid) == ("ready", running.pid)
    assert "adopted" in slot.reason
    LocalHost().stop(running, 5)
    await engines.runtime.adopt()
    slot = engines.runtime.state.slot("main")
    assert (slot.status, slot.reason) == ("stopped", "stopped while the service was not running")


async def test_an_engine_whose_host_cannot_say_whether_it_runs_is_not_taken_for_ended(
    engines: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with engines.kernel.operations.running():
        await load(engines)
        running = identity(engines)
        # Undone here, not at the test's end: the rig's own patches outlive the fixture that stops the engine, and a
        # stop that hears no answer takes the engine for gone and leaves it running.
        with monkeypatch.context() as patch:
            patch.setattr(LocalHost, "alive", lambda self, identity: None)  # no answer, as from a busy WSL
            for _ in range(3):
                await engines.runtime.watch_once(health=True)
            await engines.runtime.adopt()
    slot = engines.runtime.state.slot("main")
    assert (slot.status, slot.pid) == ("ready", running.pid), slot.reason
    assert engines.runtime.state.launches()[0].outcome == "ready"
