"""Design 0003 §3 and §6, design 0001 §4.1 and §4.8, design 0002 §2.2: the runtime keeps each slot's state (a new one is
stopped), each change with its reason, announced as `runtime.slot`; it keeps each launch and each engine installed;
and the record routes read these state kinds through the runtime's part, as they read the kernel's own."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.machine import service as machine_service
from clank.components.machine.kinds import MachineProfile
from clank.components.runtime.service import Runtime
from clank.components.runtime.state import InstallRecord, LastGood
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
YOU = Actor(kind="user", via="console")
INSTALL = InstallRecord(
    setup="kvmem-llamacpp",
    version="v0.16.0-rc1",
    host="ubuntu-22.04",
    program=["~/src/kvmem-llama.cpp/build/bin/llama-kvmem-server"],
    folder="~/src/kvmem-llama.cpp",
    library_path="build/bin",
    how="adopted",
    detail="the build the prototype uses, at commit db4bc22",
)


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(machine_service, "detect", lambda *args, **kwargs: MachineProfile(system="A system", cores=4))
    monkeypatch.setattr(machine_service, "run_command", lambda arguments: None)
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="stopped"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def runtime(kernel: Kernel) -> Runtime:
    part: Runtime = kernel.parts["runtime"]
    return part


def test_a_new_slot_is_stopped_and_each_change_is_kept_with_its_reason_and_announced(
    kernel: Kernel, clock: FakeClock
) -> None:
    state = runtime(kernel).state
    assert (state.slot("main").status, state.slot("main").reason) == ("stopped", "never started")
    clock.advance(60)
    changed = state.set_slot(
        "main", "starting", "loading daily 262K", actor=YOU, preset="daily-262k", host="local", port=18200
    )
    assert (changed.status, changed.preset, changed.since) == ("starting", "daily-262k", clock.now())
    assert state.slot("main") == changed
    [event] = kernel.events.latest(1, types=["runtime.slot"])
    assert event.summary == "main: starting (loading daily 262K)"
    assert (event.data["slot"], event.data["status"], event.actor) == ("main", "starting", YOU)
    stopped = state.set_slot("main", "stopped", "unloaded", actor=YOU)
    assert (stopped.preset, stopped.pid) == (None, None), "a stopped slot runs nothing"


def test_the_last_configuration_that_worked_is_kept_with_the_slot(kernel: Kernel, clock: FakeClock) -> None:
    state = runtime(kernel).state
    good = LastGood(preset="daily-262k", options={"vision": "cpu"}, time=clock.now())
    state.remember_good("main", good)
    state.set_slot("main", "stopped", "unloaded", actor=YOU)
    assert state.slot("main").last_good == good


def test_launches_and_installs_are_kept(kernel: Kernel, clock: FakeClock) -> None:
    state = runtime(kernel).state
    state.add_install(INSTALL, clock.now())
    assert [found.id for found in state.installs()] == ["kvmem-llamacpp@v0.16.0-rc1@ubuntu-22.04"]
    assert state.install("kvmem-llamacpp", "v0.16.0-rc1", "ubuntu-22.04") == state.installs()[0]
    assert state.install("kvmem-llamacpp", "v0.17.0", "ubuntu-22.04") is None
    launch = state.add_launch(
        slot="main",
        preset="daily-262k",
        options={"vision": "cpu"},
        engine="kvmem-llamacpp",
        engine_version="v0.16.0-rc1",
        host="ubuntu-22.04",
        command_line="llama-kvmem-server -m m.gguf",
        log="logs/processes/main-1.log",
        estimate_mib=13600,
        before_mib=1900,
    )
    clock.advance(41)
    state.finish_launch(launch, "ready", measured_mib=13580, seconds=41.0)
    found = state.launch(launch)
    assert (found.outcome, found.measured_mib, found.seconds, found.ready_at) == ("ready", 13580, 41.0, clock.now())


def test_the_record_routes_read_the_runtimes_state_through_its_part(kernel: Kernel, clock: FakeClock) -> None:
    runtime(kernel).state.add_install(INSTALL, clock.now())
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as http:
        slots = http.get("/api/v1/records/slot", headers=AUTH).json()
        assert [(slot["id"], slot["values"]["status"]) for slot in slots] == [
            ("main", "stopped"), ("fast", "stopped"), ("vision", "stopped"),
        ]  # fmt: skip
        install = http.get("/api/v1/records/install/kvmem-llamacpp@v0.16.0-rc1@ubuntu-22.04", headers=AUTH).json()
        assert install["values"]["how"] == "adopted"
        missing = http.get("/api/v1/records/launch/99", headers=AUTH)
        assert (missing.status_code, missing.json()["error"]["code"]) == (404, "not_found")
