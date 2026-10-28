"""Design 0002 §2.10 and design 0001 §8.2-8.3: every container platform adapter meets the same contract, run against
what its program answered at each recorded version, as it ran where it was recorded (that platform, its command where
it was installed): running, it reports its version, its engine's and its containers, with Clank's labels read exactly
and every label's name; stopped, no containers, read within a few seconds although the stopped program leaves some
questions unanswered; a start and a stop are asked of the program and change its state, even when the program's own
start does nothing; without its command it is not installed and refuses to start; what it supports is read from the
program. Design 0004 §3 (revised 2026-10-26): each container's networks are read by name from the same listing, a
stopped one's too, so the edge's place on every workspace's network costs no other question. Design 0014 §2: an
adapter that asks for a command's whole answer gets it as recorded, with its errors; and a platform Clank does not
start (a system service, whose recording has no transitions: Docker Engine) refuses a start and a stop with the
command its owner runs, having run nothing, and its capabilities say so. Design 0028 §5: how it is set up is read from
the program, and only a platform Clank does not start names the commands its owner runs, each with administrator
rights; one Clank starts asks nothing for it."""

import json
import re
import sys
from pathlib import Path

import pytest

from clank.components.workspaces.adapters import CONTAINER_PLATFORMS, docker_engine
from clank.components.workspaces.adapters.platform import ContainerPlatform, PlatformError, PlatformSetup
from tests.fakes.recorded import RecordedProgram, recordings


def starts(folder: Path) -> bool:
    """Whether Clank starts and stops the recorded platform: its recording moves it between states."""
    return bool(RecordedProgram.load(folder).transitions)


RECORDED = [(adapter, folder) for adapter in CONTAINER_PLATFORMS.all() for folder in recordings(adapter.NAME)]
CASES = [pytest.param(adapter, folder, id=f"{adapter.NAME}-{folder.name}") for adapter, folder in RECORDED]
STARTED = [
    pytest.param(adapter, folder, id=f"{adapter.NAME}-{folder.name}") for adapter, folder in RECORDED if starts(folder)
]


def build(adapter: type[ContainerPlatform], program: RecordedProgram, installed: bool = True) -> ContainerPlatform:
    """The adapter on the recorded program, as it ran where it was recorded: a command's output, or its whole answer
    with its errors (design 0014 §2)."""
    command = (program.command or "docker") if installed else None
    platform = program.platform or sys.platform
    return adapter(program, command, platform=platform, launch=program.launch, answer=program.answer)


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
def test_each_containers_networks_are_read_by_name_a_stopped_ones_too(
    adapter: type[ContainerPlatform], folder: Path
) -> None:
    program = RecordedProgram.load(folder, state="running")
    containers = build(adapter, program).status().containers
    assert all(container.networks for container in containers), "every container is on a network, Docker's own at least"
    assert any(len(container.networks) > 1 for container in containers), "the recording shows one on several"
    assert all("," not in network for container in containers for network in container.networks)
    assert any(container.networks for container in containers if container.state != "running")
    assert not [call for call in program.calls if call.startswith("docker network")], "no question of their own"


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_stopped_it_reports_no_containers_within_a_few_seconds(adapter: type[ContainerPlatform], folder: Path) -> None:
    program = RecordedProgram.load(folder, state="stopped")
    status = build(adapter, program).status()
    assert (status.state, status.running, status.containers, status.engine) == ("stopped", False, [], "")
    assert program.waited <= 3, "a question the stopped program never answers is asked with a short time limit"


@pytest.mark.parametrize(("adapter", "folder"), STARTED)
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
        "start": starts(folder),
        "stop": starts(folder),
    }
    missing = build(adapter, RecordedProgram.load(folder), installed=False).capabilities()
    assert not any(capability.supported for capability in missing)


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_a_platform_clank_does_not_start_refuses_with_the_command_to_run(
    adapter: type[ContainerPlatform], folder: Path
) -> None:
    program = RecordedProgram.load(folder, state="stopped")
    platform = build(adapter, program)
    refused = [capability for capability in platform.capabilities() if not capability.supported]
    assert [capability.name for capability in refused] == ([] if starts(folder) else ["start", "stop"])
    asked = len(program.calls)  # what it supports is read from the program
    asks = {"start": platform.request_start, "stop": platform.request_stop}
    for capability in refused:
        command = re.search(r"`([^`]+)`", capability.how)
        assert command is not None, f"{capability.name} names no command to run: {capability.how}"
        with pytest.raises(PlatformError, match=re.escape(command.group(1))):
            asks[capability.name]()
    assert program.calls[asked:] == [], "asked anyway, it runs nothing"


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_how_it_is_set_up_is_read_from_the_program_and_only_one_clank_does_not_start_names_its_owners_commands(
    adapter: type[ContainerPlatform], folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(docker_engine, "account_name", lambda: "owner")  # this account, as the system lists it
    for state in json.loads((folder / "program.json").read_text(encoding="utf-8"))["states"]:
        program = RecordedProgram.load(folder, state=state)
        setup = build(adapter, program).setup_state()
        if starts(folder):
            assert setup == PlatformSetup(), state
            assert program.calls == [], f"{state}: nothing is asked of a platform Clank starts itself"
            continue
        assert setup.at_boot is not None, f"{state}: as recorded"
        for command in (setup.start, setup.boot, setup.join):
            assert command[:1] == ("sudo",), f"{state}: {command} needs administrator rights, run by its owner"
        assert setup.join[-1] == "owner", f"{state}: the docker group's command names this account"
