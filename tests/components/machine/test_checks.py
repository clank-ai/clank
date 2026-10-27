"""Design 0001 §4.7 and §7.3: `clank doctor`'s checks pass, warn or fail as the machine's facts say, each with what to
do about it, and the checks that belong to one platform are skipped on the others. Design 0014 §2 and §5: Docker's
checks report what the container platform reports, in its words, read through the workspaces component: no access
names the docker group, never `clank docker start`; a Docker Engine that is not installed names its install; a stopped
one names `sudo systemctl start docker`, since Clank never starts it; Docker from the snap and rootless Docker are
unsupported, saying how to install Docker Engine. Design 0014 §4 and §5: where Docker cannot limit a container's memory
the doctor fails, in Docker's words, with the fix, or warns while `allow_unlimited_memory` allows it."""

import sqlite3
from dataclasses import replace
from typing import Any

import pytest

from clank.components.machine.checks import CheckResult, Facts, run_checks
from clank.components.machine.kinds import Gpu, MachineProfile
from clank.components.workspaces.adapters.docker_engine import INSTALL, JOIN, ROOTLESS, SNAP, Service, from_systemd
from clank.components.workspaces.service import DockerReading, PlatformStatus
from clank.kernel.home import Home
from clank.kernel.store import Store, kernel_migrations

PROFILE = MachineProfile(
    system="Windows 11 (10.0.26200)",
    python="3.12.12",
    wsl="WSL 2, Ubuntu-22.04",
    processor="A processor",
    cores=16,
    memory_gb=62.0,
    gpus=[Gpu(name="NVIDIA GeForce RTX 5080", memory_mib=16303, driver="615.71")],
    docker="28.4.0",
)


STOPPED = from_systemd(Service("loaded", "inactive"))[1]  # Docker Engine stopped, in the adapter's words


def docker(state: str = "running", *, engine: bool = False, detail: str = "") -> DockerReading:
    """Docker as the container platform reports it to the doctor: Docker Desktop, which Clank starts, or the system's
    Docker Engine, which it never does."""
    running = state == "running"
    status = PlatformStatus(
        adapter="docker-engine" if engine else "docker-desktop",
        label="Docker Engine" if engine else "Docker Desktop",
        state=state,
        version=("28.0.4" if engine else "4.85.0") if running else "",
        engine=("28.0.4" if engine else "29.6.2") if running else "",
        detail=detail,
    )
    return DockerReading(status=status, starts=not engine, memory=(True, []) if running else (None, []))


@pytest.fixture
def facts(home: Home) -> Facts:
    return Facts(home=home, profile=PROFILE, docker=docker(), platform="win32", port=7720, hags_mode=1, free_gb=120.0)


def results(facts: Facts) -> dict[str, CheckResult]:
    return {result.id: result for result in run_checks(facts)}


def statuses(facts: Facts) -> dict[str, str]:
    return {result.id: result.status for result in run_checks(facts)}


def test_a_well_set_up_machine_passes_every_check(facts: Facts, home: Home) -> None:
    store = Store(home.database)
    store.migrate(kernel_migrations())
    store.close()
    found = statuses(facts)
    assert set(found.values()) == {"passed"}, found
    assert len(found) == 11


def test_the_database_check_closes_the_database_it_read(
    facts: Facts, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = Store(home.database)
    store.migrate(kernel_migrations())
    store.close()
    opened: list[sqlite3.Connection] = []
    connect = sqlite3.connect

    def recorded(*args: Any, **kwargs: Any) -> sqlite3.Connection:
        opened.append(connect(*args, **kwargs))
        return opened[-1]

    monkeypatch.setattr(sqlite3, "connect", recorded)
    assert statuses(facts)["state_database"] == "passed"
    assert opened
    for connection in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_a_machine_without_a_gpu_wsl_or_docker_gets_warnings_with_what_to_do(facts: Facts) -> None:
    bare = replace(
        facts, profile=PROFILE.model_copy(update={"gpus": [], "wsl": "not installed", "docker": "not installed"})
    )
    missing = docker("not installed", detail="install Docker Desktop (docker.com/products/docker-desktop)")
    found = results(replace(bare, docker=missing))
    for check in ("gpu", "wsl", "docker_installed", "docker_running"):
        assert found[check].status == "warning", check
        assert found[check].fix, check


def test_hardware_accelerated_gpu_scheduling_turned_on_is_a_warning(facts: Facts) -> None:
    results = {result.id: result for result in run_checks(replace(facts, hags_mode=2))}
    assert results["hags"].status == "warning"
    assert "Graphics" in results["hags"].fix


def test_windows_checks_are_skipped_elsewhere(facts: Facts) -> None:
    found = statuses(replace(facts, platform="linux", profile=PROFILE.model_copy(update={"wsl": ""})))
    assert (found["wsl"], found["hags"]) == ("skipped", "skipped")


def test_a_clank_home_that_cannot_be_written_fails(facts: Facts, home: Home) -> None:
    unwritable = replace(facts, home=Home(home.root / "missing" / "\0bad"))
    results = {result.id: result for result in run_checks(unwritable)}
    assert results["clank_home"].status == "failed"


def test_little_room_for_models_is_a_warning_and_room_that_cannot_be_measured_too(facts: Facts) -> None:
    results = {result.id: result for result in run_checks(replace(facts, free_gb=20.0))}
    assert results["disk"].status == "warning"
    assert "10 to 20 GB" in results["disk"].fix
    unknown = {result.id: result for result in run_checks(replace(facts, free_gb=None))}
    assert (unknown["disk"].status, unknown["disk"].detail) == ("warning", "cannot be measured")


def test_docker_checks_report_what_the_container_platform_reports(facts: Facts) -> None:
    linux = replace(facts, platform="linux", profile=PROFILE.model_copy(update={"wsl": ""}))
    denied = results(replace(linux, docker=docker("no access", engine=True, detail=JOIN)))
    assert (denied["docker_installed"].status, denied["docker_running"].status) == ("passed", "warning")
    assert "`sudo usermod -aG docker $USER`" in denied["docker_running"].fix
    assert "clank docker start" not in denied["docker_running"].fix
    missing = results(replace(linux, docker=docker("not installed", engine=True, detail=INSTALL)))
    assert missing["docker_installed"].status == "warning"
    assert "docs.docker.com/engine/install" in missing["docker_installed"].fix
    stopped = results(replace(linux, docker=docker("stopped", engine=True, detail=STOPPED)))
    assert stopped["docker_running"].status == "warning"
    assert "`sudo systemctl start docker`" in stopped["docker_running"].fix
    assert "clank docker start" not in stopped["docker_running"].fix
    desktop = results(replace(facts, docker=docker("stopped")))
    assert "`clank docker start`" in desktop["docker_running"].fix, "Docker Desktop, which Clank starts"
    running = results(replace(linux, docker=docker(engine=True)))
    assert running["docker_running"].status == "passed"
    assert "Docker Engine" in running["docker_running"].detail
    assert "28.0.4" in running["docker_running"].detail
    assert "Docker Engine" in running["docker_installed"].detail


def test_the_doctor_names_docker_from_the_snap_and_rootless_docker_as_unsupported(facts: Facts) -> None:
    for said in (SNAP, ROOTLESS):
        found = results(replace(facts, platform="linux", docker=docker("unsupported", engine=True, detail=said)))
        assert found["docker_installed"].status == "warning"
        assert found["docker_installed"].fix == said
        assert "docs.docker.com/engine/install" in found["docker_installed"].fix


def test_the_doctor_fails_when_docker_cannot_limit_memory_and_warns_when_it_is_allowed(facts: Facts) -> None:
    linux = replace(facts, platform="linux")
    words = ["WARNING: No memory limit support"]
    refused = results(replace(linux, docker=replace(docker(engine=True), memory=(False, words))))
    assert refused["docker_memory"].status == "failed"
    assert "WARNING: No memory limit support" in refused["docker_memory"].detail
    assert "`cgroup_enable=memory`" in refused["docker_memory"].fix
    assert "/boot/firmware/cmdline.txt" in refused["docker_memory"].fix
    allowing = replace(docker(engine=True), memory=(False, words), allow_unlimited_memory=True)
    allowed = results(replace(linux, docker=allowing))
    assert allowed["docker_memory"].status == "warning"
    assert "allow_unlimited_memory" in allowed["docker_memory"].detail
    assert results(replace(linux, docker=docker(engine=True)))["docker_memory"].status == "passed"
    stopped = results(replace(linux, docker=docker("stopped", engine=True, detail=STOPPED)))
    assert stopped["docker_memory"].status == "skipped", "read only while Docker runs"
