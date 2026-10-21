"""Design 0003 §7.1, design 0001 §7.4 and decision 0032: an install shows what its recipe will do and asks first; "no"
leaves nothing done; "yes" runs each step on the host with its output in the operation's log, checks the program it
made against its adapter, and records the install; a step that fails stops the install with its last lines, and the
next install goes on from that step, skipping what is already made; a canceled install ends the step's command and
what it started."""

import sys
from pathlib import Path

import anyio
import pytest

from clank.components.runtime.recipes import Recipe
from clank.kernel.events import Actor
from clank.kernel.operations import Operation
from tests.components.runtime.conftest import Rig, small_recipe
from tests.fakes.engine import program
from tests.support.ended import wait_ended

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")


async def install(rig: Rig, **params: object) -> Operation:
    started = await rig.kernel.operations.start(
        "runtime.install", {"setup": "kvmem-llamacpp", "version": "v0.16.0-rc1", "host": "bench", **params}, actor=YOU
    )
    with anyio.fail_after(60):
        while True:
            current = rig.kernel.operations.get(started.id)
            if current.status == "waiting" and current.waiting_on:
                return current
            if current.status in ("done", "failed", "canceled"):
                return current
            await anyio.sleep(0.05)


async def finish(rig: Rig, operation: Operation) -> Operation:
    with anyio.fail_after(60):
        return await rig.kernel.operations.wait(operation.id)


async def test_an_install_asks_first_and_no_leaves_nothing_done(bench: Rig, tmp_path: Path) -> None:
    async with bench.kernel.operations.running():
        waiting = await install(bench)
        question = bench.kernel.questions.get(waiting.waiting_on or "")
        assert question.title == "Install KVMem/llama.cpp v0.16.0-rc1 on bench?"
        assert "fetch:" in question.detail
        assert "nothing is installed with root" in question.detail
        bench.kernel.questions.answer(question.id, by=YOU, option="cancel")
        done = await finish(bench, waiting)
    assert done.status == "canceled"
    assert not (tmp_path / "bench-clank" / "engines").exists()
    assert bench.runtime.state.install("kvmem-llamacpp", "v0.16.0-rc1", "bench") is None


async def test_yes_runs_each_step_with_its_output_checks_the_program_and_records_the_install(
    bench: Rig, tmp_path: Path
) -> None:
    async with bench.kernel.operations.running():
        done = await finish(bench, await install(bench, yes=True))
    assert done.status == "done", done.error
    folder = tmp_path / "bench-clank" / "engines" / "kvmem-llamacpp" / "v0.16.0-rc1"
    assert (folder / "build.txt").read_text(encoding="utf-8") == "built"
    log = [line.text for line in bench.kernel.operations.log_lines(done.id)]
    assert "== fetch" in log
    assert "compiling" in log
    assert any(line.startswith("its --help lists all") for line in log)
    installed = bench.runtime.state.install("kvmem-llamacpp", "v0.16.0-rc1", "bench")
    assert installed is not None
    assert (installed.how, installed.folder, installed.library_path) == ("recipe", str(folder), str(folder / "lib"))
    assert installed.detail == "deviations: none: a test"


async def test_each_step_and_the_check_of_its_program_run_with_the_recipes_environment(
    bench: Rig, tmp_path: Path
) -> None:
    probe = "import os; print('probe:', os.environ['CLANK_PROBE'])"
    wrapper = (
        "import os, subprocess, sys;"
        " sys.exit(subprocess.call([sys.executable, *sys.argv[1:]]) if os.environ.get('CLANK_PROBE') else 3)"
    )
    recipe = Recipe.model_validate(
        {
            **small_recipe().model_dump(),
            "env": {"CLANK_PROBE": "{folder}/probe"},
            "steps": [{"name": "look", "run": [sys.executable, "-c", probe]}],
            "program": [sys.executable, "-c", wrapper, *program("kvmem")[1:]],
        }
    )
    bench.runtime.recipes = {("kvmem-llamacpp", "v0.16.0-rc1"): recipe}
    async with bench.kernel.operations.running():
        done = await finish(bench, await install(bench, yes=True))
    assert done.status == "done", done.error
    folder = tmp_path / "bench-clank" / "engines" / "kvmem-llamacpp" / "v0.16.0-rc1"
    log = [line.text for line in bench.kernel.operations.log_lines(done.id)]
    assert f"probe: {folder}/probe" in log


async def test_a_canceled_install_ends_the_steps_command_with_what_it_started(bench: Rig, tmp_path: Path) -> None:
    started = tmp_path / "child.pid"
    build = (
        "import subprocess, sys, time;"
        " child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)']);"
        f" open({str(started)!r}, 'w').write(str(child.pid)); print('compiling', flush=True); time.sleep(120)"
    )
    bench.runtime.recipes = {("kvmem-llamacpp", "v0.16.0-rc1"): small_recipe(build)}
    async with bench.kernel.operations.running():
        running = await bench.kernel.operations.start(
            "runtime.install", {"setup": "kvmem-llamacpp", "version": "v0.16.0-rc1", "host": "bench", "yes": True},
            actor=YOU,
        )  # fmt: skip
        with anyio.fail_after(60):
            while "compiling" not in [line.text for line in bench.kernel.operations.log_lines(running.id)]:
                await anyio.sleep(0.05)
        await bench.kernel.operations.cancel(running.id, actor=YOU)
        done = await finish(bench, running)
    assert done.status == "canceled"
    assert wait_ended(int(started.read_text(encoding="utf-8"))), "the canceled step's own child still runs"
    assert bench.runtime.state.install("kvmem-llamacpp", "v0.16.0-rc1", "bench") is None


async def test_a_failing_step_stops_the_install_and_the_next_goes_on_from_there(bench: Rig, tmp_path: Path) -> None:
    bench.runtime.recipes = {("kvmem-llamacpp", "v0.16.0-rc1"): small_recipe("raise SystemExit('nvcc: out of space')")}
    async with bench.kernel.operations.running():
        failed = await finish(bench, await install(bench, yes=True))
        assert failed.status == "failed"
        assert "build failed (exit 1)" in failed.error
        assert "nvcc: out of space" in failed.error
        bench.runtime.recipes = {("kvmem-llamacpp", "v0.16.0-rc1"): small_recipe()}
        done = await finish(bench, await install(bench, yes=True))
    assert done.status == "done", done.error
    log = [line.text for line in bench.kernel.operations.log_lines(done.id)]
    assert "fetch: already made (source.txt)" in log
    assert "fetching" not in log
