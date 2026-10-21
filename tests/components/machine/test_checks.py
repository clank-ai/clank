"""Design 0001 §4.7 and §7.3: `clank doctor`'s checks pass, warn or fail as the machine's facts say, each with what to
do about it, and the checks that belong to one platform are skipped on the others."""

import sqlite3
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

import pytest

from clank.components.machine.checks import Facts, run_checks
from clank.components.machine.kinds import Gpu, MachineProfile
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


def no_commands(arguments: Sequence[str]) -> str | None:
    return None


def docker_answers(arguments: Sequence[str]) -> str | None:
    return "28.4.0\n" if arguments[:2] == ["docker", "info"] else None


@pytest.fixture
def facts(home: Home) -> Facts:
    return Facts(
        home=home, profile=PROFILE, run=docker_answers, platform="win32", port=7720, hags_mode=1, free_gb=120.0
    )


def statuses(facts: Facts) -> dict[str, str]:
    return {result.id: result.status for result in run_checks(facts)}


def test_a_well_set_up_machine_passes_every_check(facts: Facts, home: Home) -> None:
    store = Store(home.database)
    store.migrate(kernel_migrations())
    store.close()
    found = statuses(facts)
    assert set(found.values()) == {"passed"}, found
    assert len(found) == 10


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
    results = {result.id: result for result in run_checks(replace(bare, run=no_commands))}
    for check in ("gpu", "wsl", "docker_installed", "docker_running"):
        assert results[check].status == "warning", check
        assert results[check].fix, check


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
