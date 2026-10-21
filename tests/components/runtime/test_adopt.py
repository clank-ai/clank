"""Design 0003 §7.1 and the M1.4 plan's review focus 3: an engine already built is adopted where it is (nothing fetched,
built or moved) once Clank has checked it: its program is there, its `--help` lists every flag its adapter can give,
and the checkout it was built from is at the commit the adapter's version names. Another commit, or a missing flag, is
refused saying what differs; local changes in the checkout are recorded with the install."""

import sys
from collections.abc import Sequence
from pathlib import Path

import anyio
import pytest

from clank.components.runtime.hosts.local import LocalHost
from clank.kernel.events import Actor
from clank.kernel.operations import Operation
from tests.components.runtime.conftest import Rig
from tests.fakes.engine import program

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")
KNOWN = "db4bc22ee6e8f4b590188dcc0457e72022eb1bbe"


class Checkout(LocalHost):
    """This machine, with git's answers about the engine's checkout set by the test (and the folders git was asked
    about kept), and `~` leading to the folder of the Python that runs the tests."""

    def __init__(self, head: str, changes: str = "") -> None:
        super().__init__("bench")
        self.head = head
        self.changes = changes
        self.asked: list[str] = []

    def output(self, argv: Sequence[str]) -> str | None:
        if argv[0] == "git":
            self.asked.append(argv[2])
            return self.head if "rev-parse" in argv else self.changes
        return super().output(argv)

    def expand(self, path: str) -> str:
        return str(Path(str(Path(sys.executable).parent) + path[1:])) if path.startswith("~") else path


@pytest.fixture
def checkout(bench: Rig, monkeypatch: pytest.MonkeyPatch) -> Checkout:
    found = Checkout(f"{KNOWN}\n")
    original = bench.runtime.host
    monkeypatch.setattr(bench.runtime, "host", lambda name: found if name == "bench" else original(name))
    return found


async def adopt(rig: Rig, folder: Path, **params: object) -> Operation:
    wanted = {"setup": "kvmem-llamacpp", "version": "v0.16.0-rc1", "host": "bench", "folder": str(folder)}
    started = await rig.kernel.operations.start(
        "runtime.adopt", {"program": list(program("kvmem")), **wanted, **params}, actor=YOU
    )
    with anyio.fail_after(60):
        return await rig.kernel.operations.wait(started.id)


async def test_an_engine_at_the_known_commit_listing_every_flag_is_adopted_where_it_is(
    bench: Rig, checkout: Checkout, tmp_path: Path
) -> None:
    async with bench.kernel.operations.running():
        done = await adopt(bench, tmp_path, library_path=f"{tmp_path}/build/bin")
    assert done.status == "done", done.error
    installed = bench.runtime.state.install("kvmem-llamacpp", "v0.16.0-rc1", "bench")
    assert installed is not None
    assert (installed.how, installed.program, installed.folder) == ("adopted", list(program("kvmem")), str(tmp_path))
    assert installed.library_path == f"{tmp_path}/build/bin"
    assert installed.detail == f"built from {KNOWN[:7]}, the commit of KVMem/llama.cpp v0.16.0-rc1"


async def test_paths_given_from_the_home_folder_are_checked_and_recorded_as_the_host_expands_them(
    bench: Rig, checkout: Checkout
) -> None:
    home = Path(sys.executable).parent
    given = ["~/" + Path(sys.executable).name, *program("kvmem")[1:]]
    async with bench.kernel.operations.running():
        done = await adopt(bench, Path("~"), program=given, source="~/checkout")
    assert done.status == "done", done.error
    installed = bench.runtime.state.install("kvmem-llamacpp", "v0.16.0-rc1", "bench")
    assert installed is not None
    assert (installed.program[0], installed.folder) == (sys.executable, str(home))
    assert checkout.asked == [str(home / "checkout")] * 2


async def test_local_changes_in_the_checkout_are_recorded_with_the_install(
    bench: Rig, checkout: Checkout, tmp_path: Path
) -> None:
    checkout.changes = " m llama.cpp\n M scripts/multimodal_canary.py\n"
    async with bench.kernel.operations.running():
        done = await adopt(bench, tmp_path)
    assert done.status == "done", done.error
    installed = bench.runtime.state.install("kvmem-llamacpp", "v0.16.0-rc1", "bench")
    assert installed is not None
    assert installed.detail.endswith("; with local changes in llama.cpp, scripts/multimodal_canary.py")


async def test_an_engine_built_from_another_commit_is_refused_saying_which(
    bench: Rig, checkout: Checkout, tmp_path: Path
) -> None:
    checkout.head = "1234567890abcdef1234567890abcdef12345678\n"
    async with bench.kernel.operations.running():
        done = await adopt(bench, tmp_path)
    assert done.status == "failed"
    assert f"{tmp_path} is at commit 1234567, not {KNOWN[:7]}" in done.error
    assert bench.runtime.state.install("kvmem-llamacpp", "v0.16.0-rc1", "bench") is None


async def test_a_folder_that_is_no_checkout_is_refused_asking_for_the_source(
    bench: Rig, checkout: Checkout, tmp_path: Path
) -> None:
    checkout.head = "fatal: not a git repository (or any of the parent directories): .git\n"
    async with bench.kernel.operations.running():
        done = await adopt(bench, tmp_path)
    assert done.status == "failed"
    assert "cannot tell which commit it was built from" in done.error
    assert "source" in done.error


async def test_a_program_whose_help_lacks_a_flag_is_refused_naming_it(
    bench: Rig, checkout: Checkout, tmp_path: Path
) -> None:
    lacking = [sys.executable, "-c", "print('usage: server -m model.gguf --host H --port N')"]
    async with bench.kernel.operations.running():
        done = await adopt(bench, tmp_path, program=lacking)
    assert done.status == "failed"
    assert "its --help does not list " in done.error
    assert "--kvmem-budget" in done.error
    assert "is not KVMem/llama.cpp v0.16.0-rc1 as Clank knows it" in done.error


async def test_a_program_that_is_not_there_is_refused(bench: Rig, checkout: Checkout, tmp_path: Path) -> None:
    async with bench.kernel.operations.running():
        done = await adopt(bench, tmp_path, program=[str(tmp_path / "build" / "bin" / "llama-kvmem-server")])
    assert done.status == "failed"
    assert "is not on bench" in done.error
