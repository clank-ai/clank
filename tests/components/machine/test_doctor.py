"""Design 0001 §7.3 and design 0002 §2.1 and §3.2 (M0.3): `clank doctor` prints each check and how many passed, as text
or JSON, and works without the service; inside the service, the doctor is an operation that records the machine profile
and the checks. A component's declaration may name doctor checks of its own (the phone's way in, design 0025 §2):
they run after the machine's, and one that fails to run is said as a failed check. Design 0014 §2: both read Docker
from the platform the settings choose (`read_platform`), never from a docker command of their own."""

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner

from clank.cli.main import main
from clank.components.machine import cli, service
from clank.components.machine.checks import CHECKS, CheckResult, Facts, run_checks
from clank.components.machine.component import COMPONENT
from clank.components.machine.kinds import Gpu, MachineProfile
from clank.components.workspaces.service import DockerReading, PlatformStatus
from clank.kernel.clock import FakeClock
from clank.kernel.core import open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home

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


def fake_detect(*args: Any, **kwargs: Any) -> MachineProfile:
    return PROFILE


def fake_run(arguments: Sequence[str]) -> str | None:
    return None


RUNNING = DockerReading(
    status=PlatformStatus(
        adapter="docker-desktop", label="Docker Desktop", state="running", version="4.85.0", engine="29.6.2"
    ),
    starts=True,
    memory=(True, []),
)
READ: list[Path] = []  # the homes whose Docker the doctor read


def fake_read_platform(home: Home) -> DockerReading:
    READ.append(home.root)
    return RUNNING


@pytest.fixture(autouse=True)
def faked(monkeypatch: pytest.MonkeyPatch) -> None:
    READ.clear()
    for module in (cli, service):
        monkeypatch.setattr(module, "detect", fake_detect)
        monkeypatch.setattr(module, "run_command", fake_run)
        monkeypatch.setattr(module, "read_platform", fake_read_platform)


def test_doctor_prints_each_check_and_how_many_passed(home: Home) -> None:
    result = CliRunner().invoke(main, ["doctor"], env={"CLANK_HOME": str(home.root)})
    assert "NVIDIA GeForce RTX 5080" in result.output
    assert "Docker running" in result.output
    assert " of 11 checks passed" in result.output
    assert [home.root] == READ, "Docker as the platform the settings choose reports it"


def test_doctor_prints_json_for_scripts_and_models(home: Home) -> None:
    result = CliRunner().invoke(main, ["doctor", "--json"], env={"CLANK_HOME": str(home.root)})
    report = json.loads(result.output)
    assert report["profile"]["cores"] == 16
    assert len(report["checks"]) == 11


@pytest.mark.anyio
async def test_the_doctor_operation_records_the_profile_and_the_checks(home: Home, clock: FakeClock) -> None:
    kernel = open_kernel(home, clock, [COMPONENT])
    try:
        async with kernel.operations.running():
            started = await kernel.operations.start("machine.doctor", actor=Actor(kind="user", via="console"))
            done = await kernel.operations.wait(started.id)
        assert done.status == "done", done.error
        assert done.result is not None
        assert len(done.result["checks"]) == 11
        assert [home.root] == READ, "read without the workspaces component's part, as the doctor must"
        saved = kernel.settings.get("machine", "machine")
        assert (saved.source, saved.record.model_dump()["cores"]) == ("user", 16)
    finally:
        kernel.close()


def test_the_doctor_runs_the_checks_each_component_declares_after_its_own(home: Home) -> None:
    def declared(given: Home) -> list[dict[str, str]]:
        assert given == home
        return [{"id": "x.one", "title": "X: one", "status": "warning", "detail": "said", "fix": "do this"}]

    def broken(given: Home) -> list[dict[str, str]]:
        raise RuntimeError("no answer")

    results = run_checks(Facts(home=home, profile=PROFILE, docker=RUNNING, more=(declared, broken)))
    assert [result.id for result in results[: len(CHECKS)]] == [id for id, _, _ in CHECKS]
    assert results[len(CHECKS)] == CheckResult("x.one", "X: one", "warning", "said", "do this")
    failed = results[len(CHECKS) + 1]
    assert (failed.status, failed.detail) == ("failed", "the check itself failed: no answer")
