"""Design 0004 §9 (the owner's request, 2026-10-14: the console shows the machine's CPU, GPU, memory, disks and network
all the time). The service reads them once a second: each reading has the CPU's use (as a whole and per logical
processor), the memory and page file in use, the disks' and the network's rates since the reading before, each fixed
drive's space and each NVIDIA GPU's use, memory, temperature and power (none without NVIDIA's library); the last
readings are kept, the oldest dropped past five minutes, and answered at `GET /machine/meters`; each new one is sent to
the clients live. A GPU whose handle its driver dropped is read again from a fresh start of NVIDIA's library, or else
left out of the readings, said once, while the rest of each reading goes on. Design 0014 §2: the containers' figures
come through the workspaces component's platform, asked only while Docker's last reading is running, so the meters
never wake an engine the owner stopped. A process whose name the system does not give is named by its id."""

import ctypes
import logging
import time
from collections.abc import Iterator
from typing import Any

import psutil
import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.machine import meters, service
from clank.components.machine.meters import KEPT, TOP, Containers, Meters, Nvml, Processes
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.fakes.platform import FakePlatform

AUTH = {"Authorization": "Bearer t", "X-Clank-Client": "console"}
GPU = {"name": "NVIDIA GeForce RTX 5080", "use": 12.0, "memory_used": 2 << 30, "memory_total": 16 << 30,
       "temperature": 41, "power": 31.5, "power_limit": 360.0}  # fmt: skip


@pytest.fixture
def kernel(home: Home, clock: FakeClock) -> Iterator[Kernel]:
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def test_a_reading_has_the_cpu_the_memory_the_disks_the_network_and_the_gpus() -> None:
    meters = Meters(gpus=lambda: [dict(GPU)])
    meters.read("2026-10-14T06:00:00.000000Z")
    time.sleep(0.2)
    reading = meters.read("2026-10-14T06:00:01.000000Z")
    assert reading["time"] == "2026-10-14T06:00:01.000000Z"
    assert 0 <= reading["cpu"] <= 100
    assert reading["cores"]
    assert all(0 <= core <= 100 for core in reading["cores"])
    assert reading["memory_used"] > 0
    assert reading["memory_used"] < reading["memory_total"]
    assert all(reading[rate] >= 0 for rate in ("disk_read", "disk_write", "net_down", "net_up"))
    assert reading["drives"]
    assert all(0 < drive["used"] <= drive["total"] for drive in reading["drives"])
    assert reading["gpus"] == [GPU]
    assert isinstance(reading["processes"], list)
    assert reading["containers"] == []


def test_a_reading_has_the_busiest_and_the_largest_processes_read_every_few_seconds() -> None:
    """The owner, 2026-10-15: the panel did not say enough; what uses the machine is what an htop shows first."""
    moments = iter([0.0, 0.5, 4.0])
    processes = Processes(clock=lambda: next(moments))
    first = processes.read()
    again = processes.read()  # within PROCESS_SECONDS: the same list, not read again
    later = processes.read()
    assert again is first
    assert later is not first
    assert 0 < len(later) <= TOP * 2
    for row in later:
        assert set(row) == {"pid", "name", "cpu", "memory"}
        assert row["name"]
        assert row["pid"] != 0, "the idle process is no process"
        assert 0 <= row["cpu"] <= 100
        assert row["memory"] >= 0
    shown = [row["pid"] for row in later]
    assert len(shown) == len(set(shown))


STATS = [
    {"Name": "clank-abc-paper", "CPUPerc": "1600.00%", "MemUsage": "3.5GiB / 12GiB"},
    {"Name": "clank-abc-edge", "CPUPerc": "0.01%", "MemUsage": "9MiB / 128MiB"},
    {"Name": "n8n", "CPUPerc": "2.00%", "MemUsage": "200MiB / 30GiB"},
    {"Name": "clank-abc-notes", "CPUPerc": "0.50%", "MemUsage": "512KiB / 2GiB"},
]  # `docker stats`' own fields, as the platform gives them


def test_the_workspaces_containers_are_read_from_docker_stats_on_a_thread_of_their_own() -> None:
    asked: list[str] = []

    def stats() -> list[dict[str, Any]]:
        asked.append("stats")
        return [dict(row) for row in STATS]

    containers = Containers("clank-abc-", stats=stats, cpus=32, clock=lambda: 100.0)
    assert containers.read_now() == [
        {"name": "paper", "cpu": 50.0, "memory_used": int(3.5 * (1 << 30)), "memory_total": 12 << 30},
        {"name": "notes", "cpu": 0.0, "memory_used": 512 << 10, "memory_total": 2 << 30},
    ]
    assert asked == ["stats"]
    assert Containers("clank-abc-", stats=list, cpus=32).read_now() == [], "Docker not running: none"


def test_the_meters_never_wake_a_stopped_engine(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> None:
    platform = FakePlatform(state="stopped")
    platform.stats_rows = [{**STATS[0], "Name": f"clank-{home.id}-paper"}]
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    try:
        machine: service.Machine = kernel.parts["machine"]
        workspaces = kernel.parts["workspaces"]
        assert machine.container_stats() == [], "Docker never read yet: nothing asked"
        workspaces.docker(refresh=True)
        assert machine.container_stats() == []
        assert "stats" not in platform.calls, "while Docker's last reading is not running, its engine is asked nothing"
        platform.state = "running"
        workspaces.docker(refresh=True)
        assert machine.container_stats() == platform.stats_rows, "through the workspaces component's platform"
        assert platform.calls.count("stats") == 1
        rows = Containers(f"clank-{home.id}-", stats=machine.container_stats, cpus=32).read_now()
        assert rows == [{"name": "paper", "cpu": 50.0, "memory_used": int(3.5 * (1 << 30)), "memory_total": 12 << 30}]
    finally:
        kernel.close()


def test_without_nvidias_library_there_are_no_gpus() -> None:
    def missing(name: str) -> Any:
        raise OSError(f"{name} is not there")

    assert Nvml(missing).gpus() == []


class Driver:
    """NVIDIA's library as ctypes calls it, with one GPU whose handle the driver can drop (`drop`: an update, a reset):
    a call with a handle given out before then raises what ctypes raises for an access violation; a fresh start of the
    library gives a handle that works, unless nothing works any more (`broken`)."""

    VIOLATION = "exception: access violation reading 0x000002B49D5127C8"

    def __init__(self) -> None:
        self.starts = 0
        self.valid = 0  # the handle that works now
        self.broken = False

    def drop(self) -> None:
        self.valid = -1

    def nvmlInit_v2(self) -> int:
        self.starts += 1
        return 0

    def nvmlDeviceGetCount_v2(self, count: Any) -> int:
        count._obj.value = 1
        return 0

    def nvmlDeviceGetHandleByIndex_v2(self, index: int, handle: Any) -> int:
        self.valid = handle._obj.value = 1000 + self.starts
        return 0

    def nvmlDeviceGetName(self, handle: ctypes.c_void_p, buffer: Any, size: int) -> int:
        buffer.value = b"NVIDIA GeForce RTX 5080"
        return 0

    def nvmlDeviceGetUtilizationRates(self, handle: ctypes.c_void_p, use: Any) -> int:
        if self.broken or handle.value != self.valid:
            raise OSError(self.VIOLATION)
        use._obj.gpu = 12
        return 0

    def __getattr__(self, name: str) -> Any:
        return lambda *args: 999  # every other reading: not supported (NVML_ERROR_UNKNOWN)


def test_a_gpu_whose_handle_its_driver_dropped_is_read_from_a_fresh_start_or_else_left_out_and_said_once(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """On the owner's machine (2026-10-26), once the driver dropped the GPU's handle, every reading raised an access
    violation: the whole reading failed, each second for hours, its traceback logged each time."""
    driver = Driver()
    nvml = Nvml(lambda name: driver)
    [gpu] = nvml.gpus()
    assert (gpu["name"], gpu["use"], gpu["memory_used"]) == ("NVIDIA GeForce RTX 5080", 12.0, None)
    driver.drop()
    with caplog.at_level(logging.WARNING, logger=meters.__name__):
        [again] = nvml.gpus()
        assert again["use"] == 12.0, "read again from a fresh start of the library"
        assert driver.starts == 2
        driver.broken = True
        assert nvml.gpus() == [], "left out: the rest of the reading goes on"
        assert nvml.gpus() == []
        assert driver.starts == 3, "one fresh start each time it fails, then no more"
    assert [record.getMessage() for record in caplog.records] == [
        f"the GPU's meters stopped: NVIDIA's library failed ({Driver.VIOLATION}); they come back when the service "
        "starts again"
    ]


@pytest.mark.skipif(not Nvml().gpus(), reason="no NVIDIA GPU on this machine")
def test_an_nvidia_gpu_is_read_from_its_driver() -> None:
    [gpu, *_] = Nvml().gpus()
    assert "NVIDIA" in gpu["name"]
    assert 0 < gpu["memory_used"] <= gpu["memory_total"]
    assert 0 <= gpu["use"] <= 100
    assert 0 < gpu["temperature"] < 120
    assert gpu["clock"] > 0
    assert gpu["memory_clock"] > 0
    assert gpu["fan"] is None or 0 <= gpu["fan"] <= 100


def test_the_last_readings_are_kept_and_answered_oldest_first(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> None:
    machine: service.Machine = kernel.parts["machine"]
    count = iter(range(1000))
    monkeypatch.setattr(machine, "read_meters", lambda: {"time": "t", "cpu": float(next(count))})
    for _ in range(KEPT + 5):
        machine.keep_reading()
    with TestClient(create_app(kernel, token="t", port=7728), base_url="http://127.0.0.1:7728") as http:
        answer = http.get("/api/v1/machine/meters", headers=AUTH)
    assert answer.status_code == 200, answer.text
    samples = answer.json()["samples"]
    assert len(samples) == KEPT
    assert [sample["cpu"] for sample in samples[:2]] == [5.0, 6.0]
    assert samples[-1]["cpu"] == float(KEPT + 4)


def test_a_process_whose_name_the_system_does_not_give_is_named_by_its_id(monkeypatch: pytest.MonkeyPatch) -> None:
    # Windows gives no name for some of its own processes (seen on GitHub's runner, 2026-10-28): no row is blank.
    monkeypatch.setattr(psutil.Process, "name", lambda self: "")
    rows = Processes(clock=lambda: 0.0).read()
    assert rows
    assert all(row["name"] == f"process {row['pid']}" for row in rows)
