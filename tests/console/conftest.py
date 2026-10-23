"""Shared fixtures for the console's tests: a kernel built in the test (a fixed clock, a fake container platform, a
fixed machine profile and doctor's checks, and a fixed version, so frames are the same on every machine and release),
its API served on a free port in a thread of the test, and a client of it."""

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from clank import registry
from clank.client import Client
from clank.components.agents.console import monitor
from clank.components.machine import service as machine_service
from clank.components.machine.checks import CHECKS, CheckResult, Facts, Status
from clank.components.machine.kinds import Gpu, MachineProfile
from clank.components.runtime import checking, cloud
from clank.components.runtime.adapters.openrouter import OpenRouter
from clank.components.runtime.gpu import GpuMemory
from clank.components.workspaces import service as workspaces_service
from clank.console import app as console_app
from clank.console.style import CLANK, LoadedStyle, use
from clank.kernel import api
from clank.kernel.clock import FakeClock
from clank.kernel.console_kinds import StyleSettings
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.home import Home
from tests.fakes.openrouter import served as served_openrouter
from tests.fakes.platform import FakePlatform, container
from tests.support import live
from tests.support.cloud import CloudBench
from tests.support.live import live_service

PROFILE = MachineProfile(
    system="Windows 11 (10.0.26200)",
    python="3.12.12",
    wsl="WSL 2, Ubuntu-22.04",
    processor="A processor",
    cores=16,
    memory_gb=62.0,
    gpus=[Gpu(name="NVIDIA GeForce RTX 5080", memory_mib=16303, driver="615.71")],
    docker="29.6.2",
    detected=datetime(2026, 10, 11, 11, 40, tzinfo=UTC),
)
DOCTOR: dict[str, tuple[Status, str, str]] = {
    "docker_running": ("warning", "not running", "start it with `clank docker start` (or open Docker Desktop)"),
    "port": ("passed", "47720 is free for the service", ""),
}


def checked(facts: Facts) -> list[CheckResult]:
    """The doctor's checks, the same on every machine: all passed but Docker running."""
    passed: tuple[Status, str, str] = ("passed", "as expected", "")
    return [CheckResult(id, title, *DOCTOR.get(id, passed)) for id, title, _ in CHECKS]


@pytest.fixture
def anyio_backend() -> str:
    """Run asynchronous tests on asyncio, the event loop Textual runs on."""
    return "asyncio"


@pytest.fixture
def clock() -> FakeClock:
    """A clock that moves only when a test moves it."""
    return FakeClock(datetime(2026, 10, 11, 11, 40, tzinfo=UTC))


GIB = 1 << 30
READING: dict[str, Any] = {
    "time": "2026-10-11T13:54:00.000000Z", "cpu": 12.0, "cores": [12.0, 30.0, 4.0, 8.0] * 4,
    "memory_used": 24 * GIB, "memory_total": 64 * GIB, "swap_used": 0, "swap_total": 8 * GIB,
    "disk_read": 12 << 20, "disk_write": 3 << 20, "net_down": 1200 << 10, "net_up": 40 << 10,
    "drives": [{"mount": "C:\\", "used": 800 * GIB, "total": 1800 * GIB}],
    "gpus": [{"name": "NVIDIA GeForce RTX 5080", "use": 3.0, "memory_used": 2041 << 20, "memory_total": 16303 << 20,
              "temperature": 34, "power": 18.0, "power_limit": 360.0}],
}  # fmt: skip


@pytest.fixture(autouse=True)
def clanks_style() -> Iterator[None]:
    """Each test ends in Clank's style: a console started in another leaves that one in force for the drawing helpers,
    which read the style in force (`clank.console.style.use`)."""
    yield
    use(LoadedStyle(CLANK, StyleSettings()))


@pytest.fixture(autouse=True)
def monitor_first_on_session(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """The Monitor's tests were written while it opened on the Session view (board A), and press on from there; it opens
    on the Flow view now (decision 0130), which a test marked `flow_first` holds."""
    if "flow_first" not in request.keywords:
        monkeypatch.setattr(monitor, "FIRST_VIEW", "session")


@pytest.fixture
def still_spinner(monkeypatch: pytest.MonkeyPatch) -> None:
    """The console's spinner held still, and the Monitor's Now panel's: where a session the Monitor follows works, its
    spinner would turn four times a second and no frame would be the same twice (a test turns it itself)."""
    monkeypatch.setattr(console_app, "SPIN_SECONDS", 3600.0)
    monkeypatch.setattr(monitor, "TURN_SECONDS", 3600.0)


@pytest.fixture
def home(tmp_path: Path) -> Home:
    """A temporary CLANK_HOME with its folders created."""
    home = Home(tmp_path / "clank-home")
    home.ensure()
    return home


@pytest.fixture
def platform() -> FakePlatform:
    """Docker running two containers that Clank did not start, and one stopped."""
    return FakePlatform(
        containers=[
            container("another-model-relay", labels={"toolbox.role": "relay"}),
            container("toolbox-sandbox-017", labels={"toolbox.sandbox": "1"}),
            container("old-build", state="exited"),
        ]
    )


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    """The kernel and every component, with nothing real behind them."""
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    monkeypatch.setattr(workspaces_service, "WAIT_SECONDS", 0.001)
    monkeypatch.setattr(machine_service, "detect", lambda *args, **kwargs: PROFILE)
    monkeypatch.setattr(machine_service, "run_command", lambda arguments: None)
    monkeypatch.setattr(machine_service, "run_checks", checked)
    monkeypatch.setattr(api, "__version__", "0.0.0")  # frames do not change with each release
    kernel = open_kernel(home, clock, registry.components())
    monkeypatch.setattr(kernel.parts["runtime"], "read_gpu", lambda: GpuMemory(16303, 2041))  # not this machine's
    machine = kernel.parts["machine"]
    monkeypatch.setattr(machine, "read_meters", lambda: dict(READING))  # nor its meters
    machine.keep_reading()
    yield kernel
    kernel.close()


@pytest.fixture
def cloud_api(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> Iterator[CloudBench]:
    """A cloud model on the real service (plan s35, task 18): OpenRouter answered by the fake one, the adapter's URL
    pointed at it, and each call a client makes to the cloud's routes noted on the service the test serves."""
    with served_openrouter() as fake:
        monkeypatch.setattr(OpenRouter, "URL", fake.url)
        for module in (cloud, checking):  # a short request's time, as the frames show it: the same however slow
            monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: 0.0))
        bench = CloudBench(kernel, fake)
        made = api.create_app

        def created(*args: Any, **kwargs: Any) -> Any:
            app = made(*args, **kwargs)
            bench.record(app)
            return app

        monkeypatch.setattr(live, "create_app", created)
        yield bench


@pytest.fixture
def client(kernel: Kernel, request: pytest.FixtureRequest) -> Iterator[Client]:
    """A client of the kernel's API, served for real on a free port (the cloud's calls noted when the test asks for
    `cloud_api`, which comes first)."""
    if "cloud_api" in request.fixturenames:
        request.getfixturevalue("cloud_api")
    with live_service(kernel) as client:
        yield client
