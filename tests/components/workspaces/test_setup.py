"""Design 0004 §10: a workspace's software. Clank proposes the setup from the folder's files (a `pyproject.toml`: an
editable install, with its `dev` extra when it has one; a `requirements.txt`: those requirements; else nothing), into a
virtual environment in the workspace's home. The setup runs in a container of its own, made for it and removed after
it: the sandbox image, the folder and the home mounted as in the workspace's container, the same user and limits, on
the workspace's own internal network, going out only through Clank's proxy (HTTP_PROXY, HTTPS_PROXY and their
lowercase forms) under an identity of its own (`<workspace>.setup`), which the gateway's routes carry, with the hosts of
the set `setup` (the package indexes), only while it runs. It runs with `/bin/bash -c` (no login shell), a clean home of
its own, pip set up by Clank alone and a PATH outside the workspace's home, `~/.venv` made afresh by the image's own
Python first (each of its steps named by its full path) before `~/.venv/bin` comes first on the PATH again, so nothing
else in the workspace's home runs; `~/.venv` in its command is still the workspace's environment. Before it runs, the
workspace's network is there with the edge on it, and the gateway runs (else it is refused, saying so). The operation
asks first unless told yes, saying what runs (the folder's own steps, which can run code from the folder, reaching only
the package indexes, through the proxy), and asks again each time it runs (a changed requirements file too); it keeps a
command it is given in the workspace's record, logs each line of the install, and records the command that ran to its
end; a setup that fails leaves that record as it was."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank import registry
from clank.components.gateway.service import Gateway, network_token
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import (
    AGENT_HOME,
    EDGE_ALIAS,
    NO_PROXY,
    WORKSPACE,
    ContainerSpec,
    image_folder,
    image_tag,
    names,
    run_arguments,
    setup_spec,
)
from clank.components.workspaces.setup import (
    PIP_CONFIG,
    PYTHON,
    SETUP_HOME,
    VENV,
    VENV_PATH,
    proposed_setup,
    setup_script,
)
from clank.kernel.access import local_token
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.operations import Operation
from tests.fakes.platform import FakePlatform

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")
INDEXES = ["pypi.org", "files.pythonhosted.org"]  # the set `setup` as Clank writes it (decision 0169)
PROXY = "http://paper.setup:tok@edge:18211"
RUNNING = {"state": "running", "port": 18210, "problem": ""}
PYPROJECT = """[project]
name = "paper"
version = "1.0"
dependencies = ["numpy"]

[project.optional-dependencies]
test = ["pytest"]
dev = ["paper[test]"]
"""


def test_a_pyproject_with_a_dev_extra_is_installed_editable_with_it(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    assert (
        proposed_setup(str(tmp_path))
        == f"python3 -m venv --system-site-packages {VENV} && {VENV}/bin/python -m pip install -e '.[dev]'"
    )


def test_a_pyproject_without_a_dev_extra_is_installed_editable(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "paper"\nversion = "1.0"\n', encoding="utf-8")
    assert (
        proposed_setup(str(tmp_path))
        == f"python3 -m venv --system-site-packages {VENV} && {VENV}/bin/python -m pip install -e ."
    )


def test_requirements_are_installed_and_a_folder_with_neither_needs_nothing(tmp_path: Path) -> None:
    assert proposed_setup(str(tmp_path)) is None
    (tmp_path / "requirements.txt").write_text("numpy\n", encoding="utf-8")
    assert proposed_setup(str(tmp_path)) == (
        f"python3 -m venv --system-site-packages {VENV} && {VENV}/bin/python -m pip install -r requirements.txt"
    )


def test_an_unreadable_pyproject_is_installed_without_extras(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[project\nname=", encoding="utf-8")
    assert (
        proposed_setup(str(tmp_path))
        == f"python3 -m venv --system-site-packages {VENV} && {VENV}/bin/python -m pip install -e ."
    )


def a_setup(command: str = "make") -> ContainerSpec:
    return setup_spec(
        "abc", "paper", "C:/work/paper", "clank-sandbox:1", cpus=8, memory_mib=4096, command=command, proxy=PROXY
    )


def test_the_setup_container_joins_the_workspaces_network_and_goes_out_only_through_the_proxy() -> None:
    spec = a_setup()
    arguments = run_arguments(spec)
    assert arguments[:3] == ["run", "--rm", "--name"]
    assert "--detach" not in arguments
    assert spec.networks == ((names("abc").inner("paper"), ""),), "the workspace's internal network, and no other"
    assert arguments[arguments.index("--network") + 1] == names("abc").inner("paper")
    env = dict(spec.env)
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"):
        assert env[name] == PROXY, name
    assert env["NO_PROXY"] == env["no_proxy"] == NO_PROXY
    assert f"HTTPS_PROXY={PROXY}" in arguments
    assert f"type=bind,source=C:/work/paper,target={WORKSPACE}" in arguments
    assert f"type=volume,source={names('abc').volume('paper')},target={AGENT_HOME}" in arguments
    for given in ("--user", "--cap-drop", "--security-opt", "--init", "--cpus", "--memory", "--pids-limit"):
        assert given in arguments


def test_the_setup_runs_with_bash_c_a_clean_home_and_pip_set_up_by_clank_alone() -> None:
    spec = a_setup("make env")
    assert spec.command[:2] == ("/bin/bash", "-c"), "not a login shell, which would read the home's profile"
    assert spec.command[2] == setup_script("make env")
    env = dict(spec.env)
    assert env["HOME"] == SETUP_HOME
    assert SETUP_HOME.startswith("/tmp/"), "a folder of the container's own, removed with it"
    assert not SETUP_HOME.startswith(AGENT_HOME), "never the workspace's home volume"
    assert env["PIP_CONFIG_FILE"] == PIP_CONFIG == "/dev/null", "pip reads no configuration file, Clank's alone"
    first, *rest = spec.command[2].splitlines()
    assert rest == ["make env"], "the command as given, last, so its exit is the setup's"
    assert f"{AGENT_HOME}/.venv" == VENV_PATH
    made = f"/usr/bin/python3 -I -m venv --system-site-packages {VENV_PATH}"
    assert 'mkdir -p "$HOME"' in first
    assert f"rm -rf {VENV_PATH} " in first
    assert made in first, "~/.venv made afresh by the image's own Python"
    assert first.index("rm -rf") < first.index(made)
    assert first.endswith("|| exit"), "a step of Clank's that fails ends the setup"


def image_path() -> str:
    """The PATH the sandbox image gives every container, from its Dockerfile."""
    for line in (image_folder() / "Dockerfile").read_text(encoding="utf-8").splitlines():
        if line.startswith("ENV PATH="):
            return line.removeprefix("ENV PATH=").split()[0]
    raise AssertionError("the Dockerfile sets no PATH")


def test_the_setup_looks_up_nothing_in_the_workspaces_home_until_it_made_venv_afresh() -> None:
    """The image puts ~/.venv/bin first on its PATH, and the home is the workspace's volume: the setup's PATH is the
    image's without it, and its shell and Clank's own first steps are named by their full paths, so none of them can be
    a program left in ~/.venv/bin. Once ~/.venv is made afresh, its bin comes first again, as in the workspace's
    container, for the folder's own steps."""
    spec = a_setup("pip install -r requirements.txt")
    env = dict(spec.env)
    assert f"{VENV_PATH}/bin:" in image_path(), "the image's PATH starts in the home"
    assert env["PATH"] == image_path().replace(f"{VENV_PATH}/bin:", "")
    assert AGENT_HOME not in env["PATH"]
    arguments = run_arguments(spec)
    assert arguments[arguments.index(spec.image) + 1 :][:2] == ["/bin/bash", "-c"], "docker-init finds no other bash"
    first, command = spec.command[2].splitlines()
    *steps, last = first.removesuffix(" || exit").split(" && ")
    for step in steps:
        program = step.split()[0]
        assert program.startswith("/"), step
        assert not program.startswith(AGENT_HOME), step
    assert steps[-1].startswith(f"{PYTHON} -I -m venv "), "~/.venv made afresh before it comes first"
    assert last == f"export PATH={VENV_PATH}/bin:{env['PATH']}"
    assert command == "pip install -r requirements.txt", "the folder's own steps find the fresh ~/.venv's pip first"


def test_the_setups_tilde_venv_is_still_the_workspaces_environment() -> None:
    """A command kept from before names ~/.venv; the setup's own home is another folder."""
    kept = f"python3 -m venv --system-site-packages {VENV} && {VENV}/bin/python -m pip install -r requirements.txt"
    assert setup_script(kept).splitlines()[-1] == (
        f"python3 -m venv --system-site-packages {VENV_PATH} && {VENV_PATH}/bin/python -m pip install"
        " -r requirements.txt"
    )
    assert setup_script("cp ~/.venvrc x").splitlines()[-1] == "cp ~/.venvrc x", "~/.venv itself, nothing longer"
    assert setup_script("ls ~/.cache").splitlines()[-1] == "ls ~/.cache", "the rest of ~ is the setup's clean home"


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    monkeypatch.setattr(Gateway, "status", lambda self: dict(RUNNING))  # the gateway runs (no real one in a test)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    found = tmp_path / "work" / "paper"
    found.mkdir(parents=True)
    (found / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    return found


async def run(kernel: Kernel, kind: str, params: dict[str, Any]) -> Operation:
    started = await kernel.operations.start(kind, params, actor=YOU)
    with anyio.fail_after(30):
        while True:
            current = kernel.operations.get(started.id)
            if (current.status == "waiting" and current.waiting_on) or current.status in ("done", "failed", "canceled"):
                return current
            await anyio.sleep(0.01)


def record(kernel: Kernel, name: str) -> dict[str, Any]:
    return dict(kernel.settings.get("workspace", name).record.model_dump())


async def test_the_setup_installs_the_proposed_software_and_the_record_says_with_what(
    kernel: Kernel, platform: FakePlatform, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway: Gateway = kernel.parts["gateway"]
    carried: list[dict[str, Any]] = []
    original = platform.run_once

    def run_once(spec: ContainerSpec, line: Any, canceled: Any) -> int | None:
        carried.append(gateway.network_routes())  # what the gateway's process is given while the setup runs
        return original(spec, line, canceled)

    monkeypatch.setattr(platform, "run_once", run_once)
    async with kernel.operations.running():
        assert (await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})).status == "done"
        done = await run(kernel, "workspaces.setup", {"folder": str(folder), "yes": True})
    assert done.status == "done", done.error
    command = proposed_setup(str(folder))
    assert command is not None
    setup = names(kernel.home.id).container("paper") + "-setup"
    assert platform.calls[-1] == f"setup {setup}"
    spec = platform.specs[setup]
    assert spec.command == ("/bin/bash", "-c", setup_script(command))
    assert spec.image == image_tag()
    assert spec.networks == ((names(kernel.home.id).inner("paper"), ""),)
    token = network_token(local_token(kernel.home), "paper.setup")
    proxy = f"http://paper.setup:{token}@{EDGE_ALIAS}:{gateway.settings().proxy_port}"
    assert dict(spec.env)["HTTPS_PROXY"] == proxy, "an identity of its own at the proxy, not its agent's"
    [routes] = carried
    assert routes["paper.setup"] == {"hosts": sorted(INDEXES)}, "the package indexes, while it runs"
    assert "paper.setup" not in gateway.network_routes(), "and nothing once it ended"
    assert record(kernel, "paper")["set_up"] == command
    assert record(kernel, "paper")["setup"] is None, "a proposed command is not written into the record"
    lines = [line.text for line in kernel.operations.log_lines(done.id)]
    assert "Successfully installed paper-1.0" in lines


def test_the_gateways_routes_carry_a_setups_hosts_only_while_it_runs_and_only_for_a_workspace_there(
    kernel: Kernel, tmp_path: Path
) -> None:
    """Design 0024 §2: the routes the gateway's process follows; a workspace's agent keeps its own allowances."""
    kernel.settings.write("workspace", "paper", {"path": str(tmp_path), "hosts": {"docs.test": "by you"}}, base=None,
                          actor=YOU)  # fmt: skip
    gateway: Gateway = kernel.parts["gateway"]
    gateway.set_setup("paper", INDEXES)
    gateway.set_setup("gone", INDEXES)
    routes = gateway.network_routes()
    assert routes["paper.setup"] == {"hosts": sorted(INDEXES)}
    assert routes["paper"] == {"hosts": ["docs.test"]}, "the agent's own, unchanged"
    assert "gone.setup" not in routes, "no workspace of that name"
    gateway.set_setup("paper", None)
    assert "paper.setup" not in gateway.network_routes()


async def test_before_it_runs_the_setup_makes_the_workspaces_network_and_puts_the_edge_on_it(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    found = names(kernel.home.id)
    async with kernel.operations.running():
        assert (await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})).status == "done"
        platform.leave_network(found.inner("paper"), found.edge)
        platform.remove_network(found.inner("paper"))
        before = len(platform.calls)
        done = await run(kernel, "workspaces.setup", {"folder": str(folder), "yes": True})
    assert done.status == "done", done.error
    calls = platform.calls[before:]
    assert f"network {found.inner('paper')}" in calls
    assert f"join {found.edge} {found.inner('paper')}" in calls
    assert calls[-1] == f"setup {found.setup('paper')}", "the network and the edge first"
    assert platform.networks[found.inner("paper")] is True, "internal: no route out but the edge"


async def test_a_setup_while_the_gateway_does_not_run_is_refused_saying_so(
    kernel: Kernel, platform: FakePlatform, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with kernel.operations.running():
        assert (await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})).status == "done"
        monkeypatch.setattr(Gateway, "status", lambda self: {**RUNNING, "state": "stopped"})
        refused = await run(kernel, "workspaces.setup", {"folder": str(folder), "yes": True})
    assert refused.status == "failed"
    assert "the gateway does not run" in (refused.error or "")
    assert "proxy" in (refused.error or "")
    assert not any(call.startswith("setup ") for call in platform.calls), "nothing was run"
    assert "paper.setup" not in kernel.parts["gateway"].network_routes()


async def test_a_command_given_is_kept_and_one_that_fails_leaves_the_record_as_it_was(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    async with kernel.operations.running():
        assert (await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})).status == "done"
        platform.setup_status = 1
        failed = await run(kernel, "workspaces.setup", {"folder": str(folder), "command": "make env", "yes": True})
    assert failed.status == "failed"
    assert "exit 1" in (failed.error or "")
    assert record(kernel, "paper")["setup"] == "make env"
    assert record(kernel, "paper")["set_up"] == ""


async def test_the_setup_asks_first_saying_what_runs_and_what_it_reaches(kernel: Kernel, folder: Path) -> None:
    async with kernel.operations.running():
        assert (await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})).status == "done"
        waiting = await run(kernel, "workspaces.setup", {"folder": str(folder)})
        assert waiting.status == "waiting"
        detail = kernel.questions.get(waiting.waiting_on or "").detail
        assert "the folder's own install steps" in detail
        assert "pip install -e '.[dev]'" in detail
        assert "can run code from the folder" in detail
        assert "only the package indexes (pypi.org, files.pythonhosted.org)" in detail
        assert "through Clank's proxy" in detail
        assert "the set setup in config/network-sets.json" in detail
        assert "~/.venv afresh" in detail
        assert "clean home" in detail
        assert "internet" not in detail, "it reaches the package indexes, not the internet"
        await kernel.operations.cancel(waiting.id, actor=YOU)


async def test_a_setup_run_again_asks_again_so_a_changed_requirements_file_is_asked_for(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    folder = tmp_path / "work" / "notes"
    folder.mkdir(parents=True)
    (folder / "requirements.txt").write_text("numpy\n", encoding="utf-8")
    async with kernel.operations.running():
        assert (await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})).status == "done"
        assert (await run(kernel, "workspaces.setup", {"folder": str(folder), "yes": True})).status == "done"
        (folder / "requirements.txt").write_text("numpy\nsomething-new\n", encoding="utf-8")
        again = await run(kernel, "workspaces.setup", {"folder": str(folder)})
        assert again.status == "waiting", "nothing installs the changed file unasked"
        assert "-r requirements.txt" in kernel.questions.get(again.waiting_on or "").detail
        await kernel.operations.cancel(again.id, actor=YOU)
    assert sum(call.startswith("setup ") for call in platform.calls) == 1


async def test_a_folder_not_opened_yet_or_with_nothing_to_install_is_said_so(kernel: Kernel, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    async with kernel.operations.running():
        refused = await run(kernel, "workspaces.setup", {"folder": str(empty), "yes": True})
        assert refused.status == "failed"
        assert "open it first" in (refused.error or "")
        assert (await run(kernel, "workspaces.open", {"folder": str(empty), "yes": True})).status == "done"
        nothing = await run(kernel, "workspaces.setup", {"folder": str(empty), "yes": True})
    assert nothing.status == "done"
    assert (nothing.result or {})["installed"] is False


async def test_the_folders_view_says_what_its_software_is_and_whether_it_is_installed(
    kernel: Kernel, folder: Path
) -> None:
    workspaces = kernel.parts["workspaces"]
    async with kernel.operations.running():
        assert (await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})).status == "done"
        before = workspaces.folder_view(str(folder))["setup"]
        assert (await run(kernel, "workspaces.setup", {"folder": str(folder), "yes": True})).status == "done"
    after = workspaces.folder_view(str(folder))["setup"]
    command = proposed_setup(str(folder))
    assert before == {"command": command, "proposed": True, "installed": False, "installed_with": ""}
    assert after == {"command": command, "proposed": True, "installed": True, "installed_with": command}
