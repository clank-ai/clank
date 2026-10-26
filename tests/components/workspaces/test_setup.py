"""Design 0004 §10: a workspace's software. Clank proposes the setup from the folder's files (a `pyproject.toml`: an
editable install, with its `dev` extra when it has one; a `requirements.txt`: those requirements; else nothing), into a
virtual environment in the workspace's home. The setup runs in a container of its own, made for it and removed after
it: the sandbox image, the folder and the home mounted as in the workspace's container, the same user and limits, on
Docker's default network (the internet), which the workspace's own container never joins. The operation asks first
unless told yes, keeps a command it is given in the workspace's record, logs each line of the install, and records the
command that ran to its end; a setup that fails leaves that record as it was."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank import registry
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import AGENT_HOME, WORKSPACE, image_tag, names, run_arguments, setup_spec
from clank.components.workspaces.setup import VENV, proposed_setup
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.operations import Operation
from tests.fakes.platform import FakePlatform

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")
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


def test_the_setup_container_reaches_the_internet_is_removed_after_and_is_contained_like_the_workspaces() -> None:
    spec = setup_spec("abc", "paper", "C:/work/paper", "clank-sandbox:1", cpus=8, memory_mib=4096, command="make")
    arguments = run_arguments(spec)
    assert arguments[:3] == ["run", "--rm", "--name"]
    assert "--detach" not in arguments
    assert arguments[arguments.index("--network") + 1] == "bridge"
    assert f"type=bind,source=C:/work/paper,target={WORKSPACE}" in arguments
    assert f"type=volume,source={names('abc').volume('paper')},target={AGENT_HOME}" in arguments
    for given in ("--user", "--cap-drop", "--security-opt", "--init", "--cpus", "--memory", "--pids-limit"):
        assert given in arguments
    assert arguments[-4:] == ["clank-sandbox:1", "bash", "-lc", "make"]


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
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
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    async with kernel.operations.running():
        assert (await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})).status == "done"
        done = await run(kernel, "workspaces.setup", {"folder": str(folder), "yes": True})
    assert done.status == "done", done.error
    command = proposed_setup(str(folder))
    setup = names(kernel.home.id).container("paper") + "-setup"
    assert platform.calls[-1] == f"setup {setup}"
    spec = platform.specs[setup]
    assert spec.command == ("bash", "-lc", command)
    assert spec.image == image_tag()
    assert record(kernel, "paper")["set_up"] == command
    assert record(kernel, "paper")["setup"] is None, "a proposed command is not written into the record"
    lines = [line.text for line in kernel.operations.log_lines(done.id)]
    assert "Successfully installed paper-1.0" in lines


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


async def test_the_setup_asks_first_naming_the_command_and_that_it_downloads(kernel: Kernel, folder: Path) -> None:
    async with kernel.operations.running():
        assert (await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})).status == "done"
        waiting = await run(kernel, "workspaces.setup", {"folder": str(folder)})
        assert waiting.status == "waiting"
        question = kernel.questions.get(waiting.waiting_on or "")
        assert "pip install -e '.[dev]'" in question.detail
        assert "internet" in question.detail
        await kernel.operations.cancel(waiting.id, actor=YOU)


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
