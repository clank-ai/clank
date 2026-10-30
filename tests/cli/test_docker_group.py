"""Design 0028 §5 (decision 0150): on Linux, a `clank` command whose account the system lists in the docker group, but
whose process lacks it (joined since the last login), runs itself again through `sg docker` with the same arguments,
once (`CLANK_DOCKER_GROUP`), so it and the service it starts may use Docker at once; with the group already, without
`sg`, or on Windows, it runs as it is. The command's own entry takes the group first; a test's call of the command
never does."""

import os
import shlex
import shutil
import sys
from typing import Any

import pytest

from clank.cli import dockergroup, main


class Ran(Exception):
    """What os.execvpe was asked to run."""


@pytest.fixture
def linux(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """A Linux whose account was just added to the docker group, sg installed; os.execvpe noted."""
    asked: dict[str, Any] = {}
    monkeypatch.setattr(dockergroup, "WINDOWS", False)
    monkeypatch.setattr(dockergroup, "docker_group", lambda: (True, False))
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.delenv(dockergroup.GUARD, raising=False)

    def ran(file: str, argv: list[str], env: dict[str, str]) -> None:
        asked.update(file=file, argv=argv, env=env)
        raise Ran

    monkeypatch.setattr(os, "execvpe", ran)
    return asked


def test_a_command_joined_since_the_last_login_runs_again_through_sg_with_its_arguments(linux: dict[str, Any]) -> None:
    with pytest.raises(Ran):
        dockergroup.take(["setup", "--check", "it's here"])
    assert linux["file"] == "sg"
    assert linux["argv"][:3] == ["sg", "docker", "-c"]
    assert shlex.split(linux["argv"][3]) == [sys.executable, "-m", "clank", "setup", "--check", "it's here"]
    assert linux["env"][dockergroup.GUARD] == "1", "run again once"


@pytest.mark.parametrize(
    ("groups", "sg", "guard", "windows"),
    [
        ((True, True), True, "", False),  # the group already
        ((False, False), True, "", False),  # not in the group: clank setup offers to join it
        ((True, False), False, "", False),  # no sg: log out and in, as the checklist says
        ((True, False), True, "1", False),  # run again already
        ((True, False), True, "", True),
    ],
)
def test_otherwise_it_runs_as_it_is(
    monkeypatch: pytest.MonkeyPatch, groups: tuple[bool, bool], sg: bool, guard: str, windows: bool
) -> None:
    monkeypatch.setattr(dockergroup, "WINDOWS", windows)
    monkeypatch.setattr(dockergroup, "docker_group", lambda: groups)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}" if sg else None)
    monkeypatch.setenv(dockergroup.GUARD, guard)
    monkeypatch.setattr(os, "execvpe", lambda *args: pytest.fail("run again"))
    assert dockergroup.pending() is False
    dockergroup.take(["setup"])


def test_the_commands_entry_takes_the_group_before_the_command(
    linux: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "argv", ["/usr/local/bin/clank", "status"])
    with pytest.raises(Ran):
        main.run()
    assert shlex.split(linux["argv"][3])[-1] == "status"
