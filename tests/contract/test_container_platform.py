"""Design 0002 §2.10 and design 0001 §8.2-8.3: every container platform adapter meets the same contract, run against
what its program answered at each recorded version, as it ran where it was recorded (that platform, its command where
it was installed): running, it reports its version, its engine's and its containers, with Clank's labels read exactly
and every label's name; stopped, no containers, read within a few seconds although the stopped program leaves some
questions unanswered; a start and a stop are asked of the program and change its state, even when the program's own
start does nothing; without its command it is not installed and refuses to start; what it supports is read from the
program."""

import sys
from pathlib import Path

import pytest

from clank.components.workspaces.adapters import CONTAINER_PLATFORMS
from clank.components.workspaces.adapters.platform import ContainerPlatform, PlatformError
from tests.fakes.recorded import RecordedProgram, recordings

CASES = [
    pytest.param(adapter, folder, id=f"{adapter.NAME}-{folder.name}")
    for adapter in CONTAINER_PLATFORMS.all()
    for folder in recordings(adapter.NAME)
]


def build(adapter: type[ContainerPlatform], program: RecordedProgram, installed: bool = True) -> ContainerPlatform:
    """The adapter on the recorded program, as it ran where it was recorded."""
    command = (program.command or "docker") if installed else None
    return adapter(program, command, platform=program.platform or sys.platform, launch=program.launch)


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_running_it_reports_its_version_its_engine_and_its_containers(
    adapter: type[ContainerPlatform], folder: Path
) -> None:
    program = RecordedProgram.load(folder, state="running")
    status = build(adapter, program).status()
    assert (status.adapter, status.state, status.running) == (adapter.NAME, "running", True)
    assert status.version == program.version
    assert status.engine
    states = {container.state for container in status.containers}
    assert "running" in states
    assert states - {"running"}, "the recording shows a container that is not running"


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_clanks_labels_are_read_exactly_and_every_labels_name_is_listed(
    adapter: type[ContainerPlatform], folder: Path
) -> None:
    containers = build(adapter, RecordedProgram.load(folder, state="running")).status().containers
    clanks = [container for container in containers if container.clank]
    assert clanks, "the recording shows one of Clank's containers"
    assert all(set(container.clank) <= {"clank.home", "clank.component", "clank.record"} for container in clanks)
    assert all(len(container.clank["clank.home"]) == 12 for container in clanks)
    assert any(key.startswith("toolbox.") for container in containers for key in container.label_keys)
    assert any(not container.clank and not container.name.startswith("toolbox") for container in containers)


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_stopped_it_reports_no_containers_within_a_few_seconds(adapter: type[ContainerPlatform], folder: Path) -> None:
    program = RecordedProgram.load(folder, state="stopped")
    status = build(adapter, program).status()
    assert (status.state, status.running, status.containers, status.engine) == ("stopped", False, [], "")
    assert program.waited <= 3, "a question the stopped program never answers is asked with a short time limit"


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_a_start_and_a_stop_are_asked_of_the_program_and_change_its_state(
    adapter: type[ContainerPlatform], folder: Path
) -> None:
    program = RecordedProgram.load(folder, state="stopped")
    platform = build(adapter, program)
    platform.request_start()
    assert platform.status().running
    platform.request_stop()
    assert platform.status().state == "stopped"


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_without_its_command_it_is_not_installed_and_refuses_to_start(
    adapter: type[ContainerPlatform], folder: Path
) -> None:
    program = RecordedProgram.load(folder)
    platform = build(adapter, program, installed=False)
    status = platform.status()
    assert (status.state, status.running) == ("not installed", False)
    assert status.detail
    with pytest.raises(PlatformError):
        platform.request_start()
    assert program.calls == []


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_what_it_supports_is_read_from_the_program(adapter: type[ContainerPlatform], folder: Path) -> None:
    installed = build(adapter, RecordedProgram.load(folder)).capabilities()
    assert {capability.name: capability.supported for capability in installed} == {
        "status": True,
        "start": True,
        "stop": True,
    }
    missing = build(adapter, RecordedProgram.load(folder), installed=False).capabilities()
    assert not any(capability.supported for capability in missing)
