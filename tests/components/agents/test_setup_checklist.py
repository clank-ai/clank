"""Design 0028 §4 and §5: `clank setup`'s checklist. Each item says its state and, while it is not done, what to do: its
fix, and whether Clank does it on a yes. Each Docker state of §5 has its words and its fix: not installed, the
installer's Docker step in the terminal (winget on Windows, Homebrew on macOS, Clank's installer on Linux), or where to
get Docker when no command can; the snap's or rootless Docker, not supported, the commands shown and never run; Docker
Engine stopped, `sudo systemctl start docker` in the terminal; Docker Desktop stopped, started by Clank through its own
command; not started with the computer, `sudo systemctl enable docker`, offered and not required; no access outside the
docker group, `sudo usermod -aG docker <account>` in the terminal, then a log out and in; no access inside it, the log
out and in alone, which Clank does not do; no memory limits, the kernel setting, which Clank never makes; a folder the
agent cannot write, how to let it. An administrator command runs only in the terminal. Without the service, the model
and the folder are not known, and the service is to start, unless this account may not use Docker yet: a service
started then would keep the session's groups. An item waits while one it needs is not done. Ready says what was set up
and what each thing is for."""

from dataclasses import replace

import pytest

from clank.components.agents.checklist import Building, Facts, Item, Model, VsCode, items, ready, view
from clank.components.workspaces.adapters.platform import PlatformSetup, PlatformStatus
from clank.components.workspaces.service import SetupReading

ENGINE = PlatformStatus(adapter="docker-engine", label="Docker Engine", state="running", version="28.0.4",
                        engine="28.0.4")  # fmt: skip
DESKTOP = PlatformStatus(adapter="docker-desktop", label="Docker Desktop", state="running", version="4.85.0",
                         engine="29.6.2")  # fmt: skip
START = ("sudo", "systemctl", "start", "docker")
ENABLE = ("sudo", "systemctl", "enable", "docker")
JOIN = ("sudo", "usermod", "-aG", "docker", "ada")
OWNER = PlatformSetup(at_boot=True, in_group=True, start=START, boot=ENABLE, join=JOIN)
INSTALLER = "curl -fsSL https://clank-ai.github.io/install.sh | sh"


def reading(status: PlatformStatus = ENGINE, **changes: object) -> SetupReading:
    """Docker as read: everything done, unless changed."""
    desktop = status.adapter == "docker-desktop"
    found = SetupReading(
        status=status,
        starts=desktop,
        setup=PlatformSetup() if desktop else OWNER,
        memory=(True, []),
        image="clank-sandbox:5f2c",
        image_built=True,
    )
    return replace(found, **changes)  # type: ignore[arg-type]


def facts(system: str = "linux", docker: SetupReading | None = None, **changes: object) -> Facts:
    """Everything done on a Linux computer with Docker Engine and a cloud model, unless changed."""
    found = Facts(
        system=system,
        docker=docker or reading(),
        service=True,
        model=Model("cloud-example-coder", "Example Coder", cloud=True),
        workspaces=(("paper", "/home/user/paper"),),
        vscode=VsCode(found=True, extension="0.10.4"),
        tools=frozenset({"curl"}),
    )
    return replace(found, **changes)  # type: ignore[arg-type]


def item(found: Facts, id: str) -> Item:
    return next(each for each in items(found) if each.id == id)


def stopped(status: PlatformStatus, state: str = "stopped", detail: str = "") -> PlatformStatus:
    return status.model_copy(update={"state": state, "version": "", "engine": "", "detail": detail})


def test_with_everything_done_it_is_ready_and_says_what_each_thing_is_for() -> None:
    found = facts()
    assert ready(items(found))
    shown = view(found)
    assert shown["ready"] is True
    assert shown["said"] == "Ready: everything Clank needs is set up."
    said = " ".join(shown["ready_said"])
    for words in ("container of its own for each folder", "clank-sandbox:5f2c", "Example Coder", "paper", "`clank`"):
        assert words in said, words
    assert "Uninstalling" in said, "the setup names where to read how to undo what it set up"
    assert [each.id for each in items(found)] == [
        "docker_installed",
        "docker_running",
        "docker_boot",
        "docker_access",
        "service",
        "image",
        "model",
        "folder",
        "vscode",
    ]


def test_docker_not_installed_on_linux_offers_clanks_installer_in_the_terminal_with_administrator_rights() -> None:
    found = item(facts(docker=reading(stopped(ENGINE, "not installed"))), "docker_installed")
    assert found.state == "to do"
    assert "container of its own for each folder" in found.said
    assert found.fix is not None
    assert (found.fix.does, found.fix.admin, found.fix.shown) == ("terminal", True, INSTALLER)
    assert found.fix.command == ("sh", "-c", INSTALLER)
    assert "asks before it runs them with sudo" in found.fix.said


@pytest.mark.parametrize(
    ("system", "tool", "command"),
    [
        ("win32", "winget", ("winget", "install", "--id", "Docker.DockerDesktop", "-e")),
        ("darwin", "brew", ("brew", "install", "--cask", "docker")),
    ],
)
def test_docker_not_installed_on_windows_and_macos_offers_their_own_installer_in_the_terminal(
    system: str, tool: str, command: tuple[str, ...]
) -> None:
    docker = reading(stopped(DESKTOP, "not installed"))
    found = item(facts(system, docker, tools=frozenset({tool})), "docker_installed")
    assert found.fix is not None
    assert (found.fix.does, found.fix.command, found.fix.admin) == ("terminal", command, True)
    assert "accept its terms" in found.fix.after


@pytest.mark.parametrize(("system", "where"), [("win32", "docker.com"), ("darwin", "docker.com"),
                                               ("linux", "docs.docker.com/engine/install")])  # fmt: skip
def test_without_a_command_to_install_docker_the_fix_says_where_to_get_it_and_clank_runs_nothing(
    system: str, where: str
) -> None:
    status = stopped(DESKTOP if system != "linux" else ENGINE, "not installed")
    found = item(facts(system, reading(status), tools=frozenset()), "docker_installed")
    assert found.fix is not None
    assert (found.fix.does, found.fix.command) == ("", ())
    assert where in found.fix.said


def test_docker_from_the_snap_or_rootless_docker_is_not_supported_and_its_fix_is_shown_never_run() -> None:
    detail = "Docker from the snap is not supported: its engine cannot mount the hidden folders of your home folder."
    found = item(facts(docker=reading(stopped(ENGINE, "unsupported", detail))), "docker_installed")
    assert (found.state, found.said) == ("to do", detail)
    assert found.fix is not None
    assert (found.fix.does, found.fix.command) == ("", ()), "Clank does not do it: the commands are shown"
    assert INSTALLER in found.fix.said
    assert "Docker's own packages" in found.fix.said


def test_an_old_docker_desktop_is_told_to_update() -> None:
    found = item(facts("win32", reading(stopped(DESKTOP, "unsupported", "update Docker Desktop"))), "docker_installed")
    assert found.fix is not None
    assert "4.37" in found.fix.said
    assert found.fix.does == ""


def test_a_stopped_docker_engine_is_started_with_sudo_systemctl_in_the_terminal() -> None:
    found = item(facts(docker=reading(stopped(ENGINE))), "docker_running")
    assert (found.state, found.said) == ("to do", "Docker Engine is stopped")
    assert found.fix is not None
    assert (found.fix.does, found.fix.command, found.fix.admin) == ("terminal", START, True)
    assert "`sudo systemctl start docker`" in found.fix.said
    assert "sudo asks for your password itself" in found.fix.said


def test_a_failed_docker_service_says_where_to_read_why_and_starts_it_again() -> None:
    found = item(facts(docker=reading(stopped(ENGINE, "failed"))), "docker_running")
    assert "`systemctl status docker`" in found.said
    assert found.fix is not None
    assert found.fix.command == START


def test_a_stopped_docker_desktop_is_started_by_clank_through_its_own_command_without_administrator_rights() -> None:
    found = item(facts("win32", reading(stopped(DESKTOP))), "docker_running")
    assert (found.state, found.said) == ("to do", "Docker Desktop is not running")
    assert found.fix is not None
    assert (found.fix.does, found.fix.command, found.fix.admin) == ("docker", (), False)
    assert "accept its terms" in found.fix.said


def test_docker_engine_not_started_with_the_computer_offers_systemctl_enable_and_is_not_required() -> None:
    found = facts(docker=reading(setup=replace(OWNER, at_boot=False)))
    boot = item(found, "docker_boot")
    assert (boot.state, boot.required) == ("to do", False)
    assert "stopped after the computer restarts" in boot.said
    assert boot.fix is not None
    assert (boot.fix.does, boot.fix.command, boot.fix.admin) == ("terminal", ENABLE, True)
    assert ready(items(found)), "offered, not required"


def test_where_the_platform_says_nothing_of_the_boot_there_is_no_such_item() -> None:
    assert "docker_boot" not in [each.id for each in items(facts("win32", reading(DESKTOP)))]


def test_an_account_outside_the_docker_group_joins_it_in_the_terminal_then_logs_out_and_in() -> None:
    no_access = stopped(ENGINE, "no access", "this account may not use Docker: join the docker group")
    found = item(facts(docker=reading(no_access, setup=replace(OWNER, in_group=False)), service=False), "docker_access")
    assert found.state == "to do"
    assert "not in the docker group" in found.said
    assert "root's rights" in found.said, "Docker's own warning, said before the yes"
    assert found.fix is not None
    assert (found.fix.does, found.fix.command, found.fix.admin) == ("terminal", JOIN, True)
    assert found.fix.after.startswith("log out and in once")
    assert "`clank setup` again" in found.fix.after


@pytest.mark.parametrize(("service", "again"), [(True, "`clank stop`, then `clank`"), (False, "`clank setup` again")])
def test_an_account_in_the_group_whose_session_predates_it_logs_out_and_in_and_clank_runs_nothing(
    service: bool, again: str
) -> None:
    no_access = stopped(ENGINE, "no access", "this account is in the docker group, but ...")
    found = item(facts(docker=reading(no_access), service=service), "docker_access")
    assert "not active in this session yet" in found.said
    assert found.fix is not None
    assert (found.fix.does, found.fix.command) == ("", ())
    assert "log out and in again" in found.fix.said
    assert again in found.fix.said
    running = item(facts(docker=reading(no_access), service=service), "docker_running")
    assert running.state == "done", "no access means the engine runs: systemd said so before Docker refused"


def test_docker_without_memory_limits_names_the_kernel_setting_which_clank_never_makes() -> None:
    words = ["WARNING: No memory limit support"]
    found = item(facts(docker=reading(memory=(False, words))), "docker_memory")
    assert found.state == "to do"
    assert "WARNING: No memory limit support" in found.said
    assert found.fix is not None
    assert found.fix.does == ""
    assert "cgroup_enable=memory" in found.fix.said
    allowed = item(facts(docker=reading(memory=(False, words), allow_unlimited_memory=True)), "docker_memory")
    assert allowed.state == "done"
    assert "allow_unlimited_memory" in allowed.said
    assert "docker_memory" not in [each.id for each in items(facts())], "said only where Docker cannot limit memory"


def test_a_folder_the_agent_cannot_write_says_how_to_let_it_and_clank_does_not_change_it() -> None:
    refused = "the agent works as user 1000 in its container ... `setfacl -R -m u:1000:rwX,d:u:1000:rwX /home/user/x`"
    docker = reading(folder="/home/user/x", folder_access=refused)
    found = item(facts(docker=docker, workspaces=()), "folder")
    assert found.fix is not None
    assert (found.fix.said, found.fix.does) == (refused, "")


def test_a_folder_that_cannot_be_a_workspace_says_why_and_where_to_go() -> None:
    problem = "/home/user is your home folder: its container would see everything in it; open a folder in it"
    found = item(facts(docker=reading(folder="/home/user", folder_problem=problem), workspaces=()), "folder")
    assert found.fix is not None
    assert found.fix.does == ""
    assert problem in found.fix.said
    assert "type `clank` there" in found.fix.said
    fine = item(facts(docker=reading(folder="/home/user/paper"), workspaces=()), "folder")
    assert fine.fix is not None
    assert (fine.fix.does, "/home/user/paper" in fine.fix.said) == ("folder", True)


def test_without_the_service_the_model_and_the_folder_are_not_known_and_the_service_is_to_start() -> None:
    found = facts(service=False, model=None, workspaces=())
    states = {each.id: each.state for each in items(found)}
    assert (states["model"], states["folder"], states["service"]) == ("unknown", "unknown", "to do")
    service = item(found, "service")
    assert service.fix is not None
    assert (service.fix.does, service.fix.admin) == ("service", False)
    assert "`clank serve --background`" in service.fix.said
    assert not ready(items(found))
    assert view(found)["said"].startswith("Not ready yet: Clank's service, A model, A folder")


def test_items_wait_while_docker_is_not_installed_or_cannot_be_used() -> None:
    missing = {each.id: each.state for each in items(facts(docker=reading(stopped(ENGINE, "not installed"))))}
    assert (missing["docker_running"], missing["docker_access"], missing["image"]) == ("waits", "waits", "waits")
    no_access = reading(stopped(ENGINE, "no access"), setup=replace(OWNER, in_group=False))
    assert item(facts(docker=no_access), "image").state == "waits"


def test_while_this_account_may_not_use_docker_the_service_waits_for_it_not_for_docker_to_run() -> None:
    no_access = reading(stopped(ENGINE, "no access"), setup=replace(OWNER, in_group=False))
    service = item(facts(docker=no_access, service=False), "service")
    assert (service.state, service.fix) == ("waits", None), "started now, it would keep this session's groups"
    assert "could not use Docker either" in service.said
    stopped_engine = item(facts(docker=reading(stopped(ENGINE)), service=False), "service")
    assert stopped_engine.state == "to do", "Docker stopped is no reason to wait: the service runs without it"


def test_the_image_not_built_is_to_do_and_one_being_built_shows_its_operation() -> None:
    found = item(facts(docker=reading(image_built=False)), "image")
    assert found.state == "to do"
    assert "about a gigabyte" in found.said
    building = item(facts(docker=reading(image_built=False), building=Building("op-1a2b", "#5 [3/9] RUN apt-get")),
                    "image")  # fmt: skip
    assert (building.state, building.said) == ("doing", "being built in the background (op-1a2b): #5 [3/9] RUN apt-get")
    assert not ready(items(facts(docker=reading(image_built=False))))


@pytest.mark.parametrize(
    ("system", "gpus", "said"),
    [
        (
            "linux",
            ("NVIDIA GeForce RTX 5080, 16 GB",),
            "This computer has NVIDIA GeForce RTX 5080, 16 GB: local models",
        ),
        ("linux", (), "no NVIDIA GPU Clank can use: the cloud is the way"),
        ("darwin", (), "A Mac has no NVIDIA GPU: the cloud is the way"),
    ],
)
def test_the_model_says_the_gpu_found_or_that_the_cloud_is_the_way(
    system: str, gpus: tuple[str, ...], said: str
) -> None:
    found = item(facts(system, model=None, gpus=gpus), "model")
    assert found.state == "to do"
    assert said in found.said
    assert found.fix is not None
    assert found.fix.does == "model"
    assert "or both" in found.fix.said


def test_a_model_that_answered_says_where_it_runs() -> None:
    assert "at OpenRouter" in item(facts(), "model").said
    local = item(facts(model=Model("daily-262k", "daily 262K", cloud=False)), "model")
    assert local.said == "daily 262K answered a test request (on this computer)"


@pytest.mark.parametrize(
    ("vscode", "state", "said"),
    [
        (VsCode(found=True, extension="0.10.4"), "done", "its extension 0.10.4 is installed"),
        (VsCode(found=False), "to do", "VS Code is not installed"),
        (VsCode(found=True), "to do", "Clank's extension is not in its VS Code window yet"),
    ],
)
def test_clanks_vs_code_window_is_optional_and_says_how_to_get_it(vscode: VsCode, state: str, said: str) -> None:
    found = facts(vscode=vscode)
    window = item(found, "vscode")
    assert (window.state, window.required) == (state, False)
    assert said in window.said
    assert ready(items(found)), "optional"


def test_only_a_fix_that_runs_a_command_in_the_terminal_needs_administrator_rights() -> None:
    cases = [
        facts(docker=reading(stopped(ENGINE))),
        facts(docker=reading(setup=replace(OWNER, at_boot=False))),
        facts(docker=reading(stopped(ENGINE, "no access"), setup=replace(OWNER, in_group=False))),
        facts("win32", reading(stopped(DESKTOP))),
        facts(service=False),
        facts(model=None, workspaces=()),
    ]
    for found in cases:
        for each in items(found):
            if each.fix is not None and each.fix.admin:
                assert each.fix.does == "terminal", each.id
                assert each.fix.command, each.id


def test_the_view_gives_each_items_fix_with_its_command_as_a_list() -> None:
    shown = view(facts(docker=reading(stopped(ENGINE))))
    running = next(each for each in shown["items"] if each["id"] == "docker_running")
    assert running["fix"]["command"] == list(START)
    assert running["fix"]["shown"] == "sudo systemctl start docker"
    assert shown["ready"] is False
    assert shown["ready_said"] == []
