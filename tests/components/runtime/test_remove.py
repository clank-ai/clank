"""Design 0003 §7.4: what Clank put on a host can be taken off it again, and brought back.

A model's files are removed from a host's models folder (`runtime.remove`) after a question that says what goes, what
it frees and how to bring each file back; the catalog keeps the model and every preset stays, so `clank model download`
brings it back. A file the user keeps elsewhere (a `model-file` record) is only forgotten, never deleted. An engine
Clank built by its recipe is removed with its folder (`runtime.uninstall`) after the same kind of question; one adopted
where it was is only forgotten, as is one whose folder is not in the host's engines folder. What a running slot uses
is refused, and nothing is deleted outside the host's Clank folder."""

from pathlib import Path
from typing import Any

import anyio
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.runtime.state import InstallRecord
from clank.kernel.api import create_app
from clank.kernel.events import Actor
from clank.kernel.operations import Operation
from tests.components.runtime.conftest import FILES, Rig

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")
KVMEM = {"setup": "kvmem-llamacpp", "version": "v0.16.0-rc1"}


def placed(tmp_path: Path, name: str) -> Path:
    """Where the bench host's models folder keeps one of the tiny model's files."""
    return tmp_path / "bench-clank" / "models" / "tests" / "tiny" / "0123456789ab" / name


def put(tmp_path: Path, name: str, data: bytes | None = None) -> Path:
    path = placed(tmp_path, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(FILES[name] if data is None else data)
    return path


async def run(rig: Rig, kind: str, params: dict[str, Any]) -> Operation:
    """Start an operation; it as it is once it waits on a question or has ended."""
    started = await rig.kernel.operations.start(kind, params, actor=YOU)
    with anyio.fail_after(60):
        while True:
            current = rig.kernel.operations.get(started.id)
            if (current.status == "waiting" and current.waiting_on) or current.status in ("done", "failed", "canceled"):
                return current
            await anyio.sleep(0.05)


async def finish(rig: Rig, operation: Operation) -> Operation:
    with anyio.fail_after(60):
        return await rig.kernel.operations.wait(operation.id)


def remembered(rig: Rig) -> set[str]:
    """The files the model-file records say where they are."""
    return {loaded.record.model_dump()["file"] for loaded in rig.kernel.settings.records("model-file")}


async def test_a_removal_says_what_goes_and_how_to_bring_each_file_back_and_no_removes_nothing(
    bench: Rig, tmp_path: Path
) -> None:
    weights, projector = put(tmp_path, "tiny.gguf"), put(tmp_path, "tiny-projector.gguf")
    async with bench.kernel.operations.running():
        waiting = await run(bench, "runtime.remove", {"model": "tiny", "host": "bench", "format": "gguf"})
        question = bench.kernel.questions.get(waiting.waiting_on or "")
        assert question.title == "Remove 2 files of Tiny (21 bytes) from bench?"
        assert str(weights) in question.detail
        assert str(projector) in question.detail
        assert "`clank model download tiny --format gguf --role weights --host bench`" in question.detail
        assert "`clank model download tiny --format gguf --role projector --host bench`" in question.detail
        assert "every preset that uses it stays" in question.detail
        bench.kernel.questions.answer(question.id, by=YOU, option="cancel")
        done = await finish(bench, waiting)
    assert done.status == "canceled"
    assert weights.exists()
    assert projector.exists()


async def test_yes_removes_the_files_what_was_left_of_them_and_their_empty_folders_and_keeps_the_presets(
    bench: Rig, tmp_path: Path
) -> None:
    put(tmp_path, "tiny.gguf")
    placed(tmp_path, "tiny-projector.gguf.part").write_bytes(b"half")  # a download cut off
    placed(tmp_path, "tiny.gguf.bad").write_bytes(b"bad")  # one whose checksum differed
    async with bench.kernel.operations.running():
        done = await finish(bench, await run(bench, "runtime.remove", {"model": "tiny", "host": "bench", "yes": True}))
    assert done.status == "done", done.error
    assert (done.result or {})["freed"] == len(FILES["tiny.gguf"]) + len(b"half") + len(b"bad")
    assert not (tmp_path / "bench-clank" / "models" / "tests").exists()
    assert (tmp_path / "bench-clank" / "models").is_dir()
    assert "tiny" in (bench.runtime.models or {})
    assert bench.kernel.settings.get("preset", "fake-kvmem").source == "user"


async def test_a_file_the_user_keeps_elsewhere_is_forgotten_without_a_question_and_not_deleted(rig: Rig) -> None:
    async with rig.kernel.operations.running():
        done = await finish(rig, await run(rig, "runtime.remove", {"model": "tiny", "host": "local", "format": "gguf"}))
    assert done.status == "done", done.error
    assert (done.result or {})["forgotten"] == [str(rig.models / "tiny.gguf"), str(rig.models / "tiny-projector.gguf")]
    assert (rig.models / "tiny.gguf").read_bytes() == FILES["tiny.gguf"]
    assert not remembered(rig) & {"tiny.gguf", "tiny-projector.gguf"}


async def test_nothing_of_the_model_on_the_host_is_said_and_nothing_is_asked(bench: Rig) -> None:
    async with bench.kernel.operations.running():
        done = await finish(bench, await run(bench, "runtime.remove", {"model": "tiny", "host": "bench"}))
        unknown = await finish(bench, await run(bench, "runtime.remove", {"model": "nope", "host": "bench"}))
    assert done.status == "done", done.error
    assert (done.result or {}) == {
        "model": "tiny", "name": "Tiny", "host": "bench", "removed": [], "freed": 0, "forgotten": [], "restore": []
    }  # fmt: skip
    assert any("nothing of Tiny is on bench" in line.text for line in bench.kernel.operations.log_lines(done.id))
    assert unknown.status == "failed"
    assert "the catalog has no model 'nope'" in (unknown.error or "")


async def test_a_model_a_running_slot_uses_is_refused(rig: Rig) -> None:
    rig.runtime.state.set_slot("main", "ready", "a test", actor=YOU, preset="fake-kvmem", host="local")
    async with rig.kernel.operations.running():
        refused = await finish(rig, await run(rig, "runtime.remove", {"model": "tiny", "host": "local", "yes": True}))
        other = await finish(rig, await run(rig, "runtime.remove", {"model": "tiny", "host": "elsewhere"}))
    assert refused.status == "failed"
    assert "main runs fake KVMem, which uses Tiny's gguf files on local: unload it first" in (refused.error or "")
    assert {"tiny.gguf", "tiny-projector.gguf"} <= remembered(rig)
    assert other.status == "failed"
    assert "there is no host named 'elsewhere'" in (other.error or "")


async def install_small(bench: Rig) -> None:
    done = await finish(bench, await run(bench, "runtime.install", {**KVMEM, "host": "bench", "yes": True}))
    assert done.status == "done", done.error


async def test_an_engine_built_by_its_recipe_is_removed_with_its_folder_after_a_question(
    bench: Rig, tmp_path: Path
) -> None:
    folder = tmp_path / "bench-clank" / "engines" / "kvmem-llamacpp" / "v0.16.0-rc1"
    async with bench.kernel.operations.running():
        await install_small(bench)
        assert (folder / "build.txt").exists()
        waiting = await run(bench, "runtime.uninstall", {**KVMEM, "host": "bench"})
        question = bench.kernel.questions.get(waiting.waiting_on or "")
        assert question.title == "Remove KVMem/llama.cpp v0.16.0-rc1 from bench?"
        assert str(folder) in question.detail
        assert "`clank engine install kvmem-llamacpp --version v0.16.0-rc1 --host bench` builds it again" in (
            question.detail
        )
        bench.kernel.questions.answer(question.id, by=YOU, option="remove")
        done = await finish(bench, waiting)
    assert done.status == "done", done.error
    assert (done.result or {})["freed"] > 0
    assert not (tmp_path / "bench-clank" / "engines" / "kvmem-llamacpp").exists()
    assert (tmp_path / "bench-clank" / "engines").is_dir()
    assert bench.runtime.state.install("kvmem-llamacpp", "v0.16.0-rc1", "bench") is None


async def test_no_keeps_the_engine_and_its_folder(bench: Rig, tmp_path: Path) -> None:
    async with bench.kernel.operations.running():
        await install_small(bench)
        waiting = await run(bench, "runtime.uninstall", {**KVMEM, "host": "bench"})
        bench.kernel.questions.answer(waiting.waiting_on or "", by=YOU, option="cancel")
        done = await finish(bench, waiting)
    assert done.status == "canceled"
    assert (tmp_path / "bench-clank" / "engines" / "kvmem-llamacpp" / "v0.16.0-rc1" / "build.txt").exists()
    assert bench.runtime.state.install("kvmem-llamacpp", "v0.16.0-rc1", "bench") is not None


@pytest.mark.parametrize("how", ["adopted", "recipe"])
async def test_an_engine_whose_folder_clank_did_not_make_is_forgotten_and_its_folder_kept(
    bench: Rig, tmp_path: Path, how: str
) -> None:
    mine = tmp_path / "my-build"
    mine.mkdir()
    (mine / "server").write_text("built by hand", encoding="utf-8")
    install = InstallRecord(**KVMEM, host="bench", program=[str(mine / "server")], folder=str(mine), how=how)
    bench.runtime.state.add_install(install, bench.clock.now())
    async with bench.kernel.operations.running():
        done = await finish(bench, await run(bench, "runtime.uninstall", {**KVMEM, "host": "bench"}))
    assert done.status == "done", done.error
    assert (done.result or {})["kept"] is True
    assert (mine / "server").exists()
    assert bench.runtime.state.install("kvmem-llamacpp", "v0.16.0-rc1", "bench") is None


async def test_an_engine_a_running_slot_runs_or_one_not_installed_there_is_refused(bench: Rig) -> None:
    bench.runtime.state.set_slot("main", "ready", "a test", actor=YOU, preset="fake-kvmem", host="local")
    async with bench.kernel.operations.running():
        running = await finish(bench, await run(bench, "runtime.uninstall", {**KVMEM, "host": "local", "yes": True}))
        missing = await finish(bench, await run(bench, "runtime.uninstall", {**KVMEM, "host": "bench", "yes": True}))
    assert running.status == "failed"
    assert "main runs fake KVMem on local: unload it first" in (running.error or "")
    assert bench.runtime.state.install("kvmem-llamacpp", "v0.16.0-rc1", "local") is not None
    assert missing.status == "failed"
    assert "KVMem/llama.cpp v0.16.0-rc1 is not installed on bench" in (missing.error or "")


def test_the_commands_remove_a_models_files_and_an_engine(
    bench: Rig, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    put(tmp_path, "tiny.gguf")
    mine = tmp_path / "my-build"
    mine.mkdir()
    install = InstallRecord(**KVMEM, host="bench", program=[str(mine / "server")], folder=str(mine), how="adopted")
    bench.runtime.state.add_install(install, bench.clock.now())
    with TestClient(create_app(bench.kernel, token="t", port=7725), base_url="http://127.0.0.1:7725") as http:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7725", "t", name="cli", http=http))
        removed = CliRunner().invoke(main, ["model", "remove", "tiny", "--host", "bench", "--yes"])
        assert removed.exit_code == 0, removed.output
        assert "Removed 1 file of Tiny from bench, 12 bytes freed." in removed.output
        assert "`clank model download tiny --format gguf --role weights --host bench`" in removed.output
        forgot = CliRunner().invoke(main, ["model", "remove", "tiny", "--host", "local", "--format", "gguf"])
        assert forgot.exit_code == 0, forgot.output
        assert "Clank forgot 2 files of Tiny on local; they stay where they are:" in forgot.output
        assert str(bench.models / "tiny.gguf") in forgot.output
        uninstalled = CliRunner().invoke(
            main, ["engine", "uninstall", "kvmem-llamacpp", "--version", "v0.16.0-rc1", "--host", "bench"]
        )
        assert uninstalled.exit_code == 0, uninstalled.output
        assert f"Clank forgot KVMem/llama.cpp v0.16.0-rc1 on bench; its folder stays where it is: {mine}" in (
            uninstalled.output
        )
        missing = CliRunner().invoke(main, ["model", "remove", "tiny", "--host", "nowhere"])
        assert missing.exit_code == 1
        assert "there is no host named 'nowhere'" in missing.output
