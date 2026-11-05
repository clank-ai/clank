"""Design 0001 §7.2 and §4.7: `clank doctor` says whether anyone but the user may open CLANK_HOME's secrets/ and state/,
and changes nothing (decision 0167). On Windows it names every other entry of their access lists, who it is and what
it allows, and the icacls commands that remove it, for the owner to run (an entry from the folder above goes with the
command that turns inheritance off and grants the user and SYSTEM alone); on Linux and macOS it names a mode that lets
others in, with `chmod 700`. Clank's service also puts them right as it starts. Design 0028 §4: `clank setup` reads
the same, and a list it cannot read leaves its checklist whole. Always on a temporary home."""

import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest

from clank.components.agents import checklist, setupfacts
from clank.components.machine.checks import CheckResult, Facts, run_checks
from clank.components.machine.kinds import MachineProfile
from clank.components.workspaces.adapters.platform import PlatformStatus
from clank.components.workspaces.service import SetupReading
from clank.kernel import private
from clank.kernel.home import Home

windows = pytest.mark.skipif(sys.platform != "win32", reason="Windows' access lists")
posix = pytest.mark.skipif(sys.platform == "win32", reason="a mode means nothing on Windows")
USERS = "S-1-5-32-545"  # BUILTIN\Users, on every Windows
RUNNING = PlatformStatus(adapter="docker-desktop", label="Docker Desktop", state="running", version="4.85.0")
FACTS = checklist.Facts(system="win32", docker=SetupReading(status=RUNNING, starts=True, image_built=True))


def check(home: Home) -> CheckResult:
    """The doctor's answer on who may open secrets/ and state/."""
    found = run_checks(Facts(home=home, profile=MachineProfile(), free_gb=100.0))
    return next(result for result in found if result.id == "private_folders")


def run(command: tuple[str, ...]) -> None:
    subprocess.run(command, check=True, capture_output=True)


def test_before_the_folders_exist_the_check_is_skipped(tmp_path: Path) -> None:
    found = check(Home(tmp_path / "home"))
    assert (found.status, found.title) == ("skipped", "Only you can open secrets and state")
    assert not (tmp_path / "home" / "secrets").exists(), "the doctor changes nothing"


@windows
def test_once_clank_set_them_only_the_user_and_system_may_open_them(home: Home) -> None:
    found = check(home)
    assert (found.status, found.detail) == ("passed", "only you and SYSTEM may open secrets/ and state/")


@windows
def test_an_extra_grant_is_named_with_the_icacls_command_that_removes_it(home: Home) -> None:
    run(("icacls", str(home.secrets), "/grant", f"*{USERS}:(OI)(CI)R"))
    found = check(home)
    assert found.status == "warning"
    assert found.detail == "secrets/'s access list also names BUILTIN\\Users (read)"
    command = f'icacls "{home.secrets}" /remove "*{USERS}"'
    assert f"`{command}`" in found.fix
    assert "Clank also sets them itself each time its service starts" in found.fix
    assert [tuple(each.commands) for each in home.exposed()] == [
        (("icacls", str(home.secrets), "/remove", f"*{USERS}"),)
    ]
    for each in home.exposed():
        for given in each.commands:
            run(given)
    assert check(home).status == "passed", "the command the doctor gave removed it"


@windows
def test_an_entry_from_the_folder_above_is_named_with_the_command_that_turns_inheritance_off(tmp_path: Path) -> None:
    home = Home(tmp_path / "home")
    home.root.mkdir()
    run(("icacls", str(home.root), "/grant", f"*{USERS}:(OI)(CI)M"))
    home.state.mkdir()  # made as an earlier Clank made it: its list from the folder above
    found = check(home)
    assert found.status == "warning"
    assert "state/'s access list also names " in found.detail
    assert "BUILTIN\\Users (read and write, from the folder above)" in found.detail
    [exposed] = home.exposed()
    [reset] = exposed.commands
    assert reset[:4] == ("icacls", str(home.state), "/inheritance:r", "/grant:r")
    assert reset[-1] == "*S-1-5-18:(OI)(CI)F"
    assert f'`icacls "{home.state}" /inheritance:r /grant:r ' in found.fix
    run(reset)
    assert check(home).status == "passed", "the command the doctor gave removed it"
    assert not (tmp_path / "home" / "secrets").exists(), "the doctor changes nothing"


@windows
def test_the_doctor_reads_the_lists_and_writes_none(home: Home, monkeypatch: pytest.MonkeyPatch) -> None:
    run(("icacls", str(home.secrets), "/grant", f"*{USERS}:(OI)(CI)R"))

    def refused(folder: Path, user: str) -> None:
        raise AssertionError(f"the doctor wrote {folder}'s list")

    monkeypatch.setattr(private, "_write", refused)
    assert check(home).status == "warning"
    assert check(home).status == "warning", "still there: the doctor only says it"


@windows
def test_clank_setup_reads_what_the_doctor_reads(home: Home) -> None:
    assert setupfacts.exposed(home) == ()
    run(("icacls", str(home.state), "/grant", f"*{USERS}:(OI)(CI)R"))
    [found] = setupfacts.exposed(home)
    assert (found.folder, found.said) == (home.state, "state/'s access list also names BUILTIN\\Users (read)")
    [item] = [each for each in checklist.items(replace(FACTS, exposed=(found,))) if each.id == "private_folders"]
    assert (item.said, item.fix and item.fix.said) == private.words([found])


def test_a_list_that_cannot_be_read_leaves_the_setup_whole(home: Home, monkeypatch: pytest.MonkeyPatch) -> None:
    def unreadable(folder: Path) -> None:
        raise PermissionError(13, "Access is denied", str(folder))

    monkeypatch.setattr(private, "exposed", unreadable)
    assert setupfacts.exposed(home) == ()
    assert check(home).status == "failed", "the doctor says it"


@posix
def test_a_mode_that_lets_others_in_is_named_with_chmod(home: Home) -> None:
    assert check(home).detail == "only you may open secrets/ and state/"
    home.secrets.chmod(0o750)
    found = check(home)
    assert found.status == "warning"
    assert found.detail == "secrets/ has mode 750, so others may open it"
    assert f"`chmod 700 {home.secrets}`" in found.fix
    assert home.secrets.stat().st_mode & 0o777 == 0o750, "the doctor changes nothing"
