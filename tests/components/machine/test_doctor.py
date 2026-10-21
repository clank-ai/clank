"""Design 0001 §7.3 and design 0002 §3.2 (M0.3): `clank doctor` prints each check and how many passed, as text or JSON,
and works without the service; inside the service, the doctor is an operation that records the machine profile and the
checks."""

import json
from collections.abc import Sequence
from typing import Any

import pytest
from click.testing import CliRunner

from clank.cli.main import main
from clank.components.machine import cli, service
from clank.components.machine.component import COMPONENT
from clank.components.machine.kinds import Gpu, MachineProfile
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
    return "28.4.0\n" if arguments[:2] == ["docker", "info"] else None


@pytest.fixture(autouse=True)
def faked(monkeypatch: pytest.MonkeyPatch) -> None:
    for module in (cli, service):
        monkeypatch.setattr(module, "detect", fake_detect)
        monkeypatch.setattr(module, "run_command", fake_run)


def test_doctor_prints_each_check_and_how_many_passed(home: Home) -> None:
    result = CliRunner().invoke(main, ["doctor"], env={"CLANK_HOME": str(home.root)})
    assert "NVIDIA GeForce RTX 5080" in result.output
    assert "Docker running" in result.output
    assert " of 10 checks passed" in result.output


def test_doctor_prints_json_for_scripts_and_models(home: Home) -> None:
    result = CliRunner().invoke(main, ["doctor", "--json"], env={"CLANK_HOME": str(home.root)})
    report = json.loads(result.output)
    assert report["profile"]["cores"] == 16
    assert len(report["checks"]) == 10


@pytest.mark.anyio
async def test_the_doctor_operation_records_the_profile_and_the_checks(home: Home, clock: FakeClock) -> None:
    kernel = open_kernel(home, clock, [COMPONENT])
    try:
        async with kernel.operations.running():
            started = await kernel.operations.start("machine.doctor", actor=Actor(kind="user", via="console"))
            done = await kernel.operations.wait(started.id)
        assert done.status == "done", done.error
        assert done.result is not None
        assert len(done.result["checks"]) == 10
        saved = kernel.settings.get("machine", "machine")
        assert (saved.source, saved.record.model_dump()["cores"]) == ("user", 16)
    finally:
        kernel.close()
