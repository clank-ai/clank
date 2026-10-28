"""Design 0028 §5: how the container platform is set up on this computer, as `clank setup` reads it from the platform's
adapter. Docker Engine says whether systemd starts Docker's service with the computer (its unit file's state, which
starts nothing), whether this account is in the docker group as the system lists it now, and the commands its owner runs
with administrator rights: `sudo systemctl start docker`, `sudo systemctl enable docker` and `sudo usermod -aG docker`
with this account's name (none when the system gives no name). Without systemd it says nothing of the boot and names no
systemctl command; not installed, it names none (the contract holds every recorded platform to the same: Docker Desktop,
which Clank starts through its own command, names none)."""

import pytest

from clank.components.workspaces.adapters.platform import PlatformSetup
from tests.components.workspaces.test_docker_engine import Machine, engine


@pytest.mark.parametrize(
    ("unit_file", "at_boot"),
    [("enabled", True), ("disabled", False), ("masked", False), ("static", True), ("bad", None), ("", None)],
)
def test_whether_systemd_starts_docker_with_the_computer_is_its_unit_files_state(
    unit_file: str, at_boot: bool | None
) -> None:
    machine = Machine("active", unit_file=unit_file)
    assert engine(machine).setup_state().at_boot is at_boot
    assert machine.asked == [], "systemd is asked, never the engine"


def test_the_owners_commands_need_administrator_rights_and_the_join_names_this_account() -> None:
    setup = engine(Machine("inactive"), account=lambda: "ada").setup_state()
    assert setup.start == ("sudo", "systemctl", "start", "docker")
    assert setup.boot == ("sudo", "systemctl", "enable", "docker")
    assert setup.join == ("sudo", "usermod", "-aG", "docker", "ada")


@pytest.mark.parametrize(("listed", "process"), [(True, False), (False, False), (True, True)])
def test_whether_this_account_is_in_the_docker_group_is_as_the_system_lists_it_now(listed: bool, process: bool) -> None:
    setup = engine(Machine("active"), groups=lambda: (listed, process)).setup_state()
    assert setup.in_group is listed, "the system's list, not this process's groups, which it kept from its start"


def test_without_systemd_nothing_is_said_of_the_boot_and_no_systemctl_command_is_named() -> None:
    setup = engine(Machine(None), account=lambda: "ada").setup_state()
    assert (setup.at_boot, setup.start, setup.boot) == (None, (), ())
    assert setup.join[:4] == ("sudo", "usermod", "-aG", "docker")


def test_docker_engine_not_installed_names_no_command() -> None:
    assert engine(Machine("active"), command=None).setup_state() == PlatformSetup()


def test_an_account_whose_name_the_system_does_not_give_is_offered_no_join_command() -> None:
    assert engine(Machine("active"), account=lambda: "").setup_state().join == ()
