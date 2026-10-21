"""Design 0013 §4 and §5: a box's *accept when* may also be a command, which the runner runs in the workspace's
container, in its folder, after the box's session ended and its deliverables were written: it passes when it exits 0,
and the box is done; otherwise the box fails, saying the command and how it ended, and its next try's first message
has the end of the command's output. The command and all it said are kept in the try's folder; a command that runs
past the box's time is ended in the container and fails the box, and one killed says it ran past its time or out of
memory; a box that wrote nothing does not run it. The owner's stop, a cancel from the Operations page and the
service's stop end a command still running, in the container, at once (§6: a stopped box's try counts as stopped); a
deliverable the command rewrote is kept as the command left it, its copy and fingerprint agreeing. Run against the
fake bridge and a synthetic folder; the command's shell, on Linux, against a real `sh` and `timeout`."""

import hashlib
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

import pytest

from clank.components.flows import accepting
from clank.components.flows.accepting import accept
from clank.kernel.clock import FakeClock
from clank.kernel.home import Home
from clank.kernel.processes import Answer
from tests.components.flows.rig import FLOW, OWNER, Rig, make_rig, question, running, study, until

pytestmark = pytest.mark.anyio
TESTS = "python3 -m pytest -q tests/test_grid.py"
FAILED = "".join(f"line {number} of the run\n" for number in range(1, 61)) + (
    "FAILED tests/test_grid.py::test_points - assert 240 == 64\n1 failed in 0.4s\n"
)


@pytest.fixture
def rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    flow = study()
    flow["boxes"][3]["accept_command"] = TESTS
    flow["boxes"][3]["limits"] = {"minutes": 2}
    made = make_rig(home, clock, tmp_path, monkeypatch, flow)
    yield made
    made.kernel.close()


async def to_the_grid(rig: Rig) -> Any:
    """The run started; its brief, plan and gate done; the grid's first message sent."""
    rig.runner.start(FLOW, actor=OWNER)
    asked = await until(lambda: question(rig, "Brief"))
    rig.write("BRIEF.md", "The brief.\n")
    rig.kernel.questions.answer(asked.id, by=OWNER, option="done")
    plan = await until(lambda: rig.bridge.prompted("Study · plan · try 1"))
    rig.bridge.finish(plan.session, {"PLAN.md": "# The plan\n"})
    gate = await until(lambda: question(rig, "You approve the plan"))
    rig.kernel.questions.answer(gate.id, by=OWNER, option="approve")
    return await until(lambda: rig.bridge.prompted("Study · T1 · try 1"))


async def test_a_box_whose_accept_command_exits_0_is_done_the_command_run_in_the_container_after_its_session(
    rig: Rig,
) -> None:
    rig.bridge.commands[TESTS] = Answer(0, "3 passed in 0.2s\n", "")
    async with running(rig.kernel):
        grid = await to_the_grid(rig)
        assert rig.bridge.ran == [], "not before its session ended"
        rig.bridge.finish(grid.session, {"grid.json": "[]\n"})
        await until(lambda: rig.run().status == "done")
    assert rig.bridge.ran == [TESTS]
    [argv] = rig.bridge.commanded
    assert argv[:4] == ["sh", "-c", accepting.RUN, "sh"], "under `timeout`, its process id in a file"
    assert argv[4].startswith("/tmp/clank-accept-")
    assert argv[5:] == ["10", "120", TESTS], "ended in the container at the box's time, killed 10 seconds later"
    attempt = rig.run().box("T1").tries[-1]
    assert (attempt.outcome, rig.run().box("T1").state) == ("done", "done")
    assert attempt.command is not None
    assert (attempt.command.command, attempt.command.status) == (TESTS, 0)
    kept = rig.runner.runs.try_folder(rig.run(), "T1", 1) / "accept-command.txt"
    text = kept.read_text(encoding="utf-8")
    assert text.startswith(f"$ {TESTS}\n")
    assert "3 passed in 0.2s" in text
    assert text.rstrip().endswith("It exited 0: it passes.")


async def test_a_box_whose_accept_command_exits_1_fails_saying_the_command_and_its_next_try_has_the_end_of_its_output(
    rig: Rig,
) -> None:
    rig.bridge.commands[TESTS] = Answer(1, FAILED, "")
    async with running(rig.kernel):
        grid = await to_the_grid(rig)
        rig.bridge.finish(grid.session, {"grid.json": "[]\n"})
        failed = await until(lambda: question(rig, "The grid failed"))
        assert failed.title == f"Study: The grid failed: its accept command `{TESTS}` exited 1"
        rig.kernel.questions.answer(failed.id, by=OWNER, option="retry")
        again = await until(lambda: rig.bridge.prompted("Study · T1 · try 2"))
    assert f"Try 1 failed: its accept command `{TESTS}` exited 1." in again.text
    assert "FAILED tests/test_grid.py::test_points - assert 240 == 64\n1 failed in 0.4s" in again.text
    assert "line 23 of the run" in again.text, "its last 40 lines"
    assert "line 22 of the run" not in again.text
    kept = rig.runner.runs.try_folder(rig.run(), "T1", 1) / "accept-command.txt"
    assert "line 1 of the run\n" in kept.read_text(encoding="utf-8"), "kept whole in the try's folder"


async def test_a_command_that_runs_past_the_boxs_time_fails_the_box(rig: Rig) -> None:
    rig.bridge.commands[TESTS] = Answer(124, "collected 3 items\n", "")
    async with running(rig.kernel):
        grid = await to_the_grid(rig)
        rig.bridge.finish(grid.session, {"grid.json": "[]\n"})
        failed = await until(lambda: question(rig, "The grid failed"))
    assert failed.title.endswith(f"its accept command `{TESTS}` ran past its 2 minutes and was ended")


async def test_a_box_that_wrote_nothing_does_not_run_its_accept_command(rig: Rig) -> None:
    async with running(rig.kernel):
        grid = await to_the_grid(rig)
        rig.bridge.finish(grid.session)
        failed = await until(lambda: question(rig, "The grid failed"))
    assert "it ended without writing grid.json" in failed.title
    assert rig.bridge.ran == []


async def test_a_stop_while_the_accept_command_runs_ends_it_in_the_container_and_its_try_counts_as_stopped(
    rig: Rig,
) -> None:
    rig.bridge.commands[TESTS] = Answer(0, "3 passed in 0.2s\n", "")
    rig.bridge.hold[TESTS] = threading.Event()
    async with running(rig.kernel):
        grid = await to_the_grid(rig)
        rig.bridge.finish(grid.session, {"grid.json": "[]\n"})
        await until(lambda: rig.bridge.ran == [TESTS])
        rig.runner.stop(FLOW, actor=OWNER)
        await until(lambda: not rig.run().operation, seconds=5)  # the run is free at once, not after the command
    assert rig.bridge.ended == [rig.bridge.commanded[0][4]], "ended in the container"
    attempt = rig.run().box("T1").tries[-1]
    assert attempt.outcome == "stopped"
    assert attempt.reason == f"stopped by {OWNER.describe()} while its accept command ran"
    assert attempt.command is not None
    assert attempt.command.ended == f"was ended: stopped by {OWNER.describe()} while its accept command ran"
    assert rig.run().status == "stopped"


async def test_a_cancel_from_the_operations_page_while_the_accept_command_runs_ends_it_in_the_container(
    rig: Rig,
) -> None:
    rig.bridge.hold[TESTS] = threading.Event()
    async with running(rig.kernel):
        grid = await to_the_grid(rig)
        rig.bridge.finish(grid.session, {"grid.json": "[]\n"})
        await until(lambda: rig.bridge.ran == [TESTS])
        operation = rig.run().operation
        await rig.kernel.operations.cancel(operation, actor=OWNER)
        await until(lambda: rig.kernel.operations.get(operation).status == "canceled", seconds=5)
    assert rig.bridge.ended, "ended in the container"
    attempt = rig.run().box("T1").tries[-1]
    assert (attempt.outcome, attempt.reason) == ("stopped", "canceled from the Operations page")


async def test_the_services_stop_while_the_accept_command_runs_ends_it_in_the_container_at_once(rig: Rig) -> None:
    rig.bridge.hold[TESTS] = threading.Event()
    async with running(rig.kernel):
        grid = await to_the_grid(rig)
        rig.bridge.finish(grid.session, {"grid.json": "[]\n"})
        await until(lambda: rig.bridge.ran == [TESTS])
        began = time.monotonic()
    assert time.monotonic() - began < 5, "the service's stop did not wait for the command"
    assert rig.bridge.ended, "ended in the container, so it does not run twice once the box is collected again"


async def test_a_deliverable_the_command_rewrote_is_kept_as_the_command_left_it(rig: Rig) -> None:
    rig.bridge.commands[TESTS] = Answer(0, "formatted grid.json\n", "")
    rig.bridge.effects[TESTS] = lambda: rig.write("grid.json", "[\n]\n")
    async with running(rig.kernel):
        grid = await to_the_grid(rig)
        rig.bridge.finish(grid.session, {"grid.json": "[]\n"})
        await until(lambda: rig.run().status == "done")
    state = rig.run().box("T1")
    assert (state.state, state.changed) == ("done", ""), "not changed in the folder: the command's work is the try's"
    [kept] = state.tries[-1].deliverables
    folder = rig.runner.runs.try_folder(rig.run(), "T1", 1)
    copy = (folder / "deliverables" / "grid.json").read_bytes()
    assert (copy, kept.sha256) == (b"[\n]\n", hashlib.sha256(copy).hexdigest()), "its copy and fingerprint agree"
    assert state.tries[-1].command is not None
    assert state.tries[-1].command.changed == ["grid.json"]
    said = (folder / "accept-command.txt").read_text(encoding="utf-8")
    assert said.endswith("It changed grid.json: the try keeps it as it left it.\n")


def alive(pid: int) -> bool:
    """Whether a process runs (one ended and not yet reaped does not)."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return False
    return stat.rsplit(")", 1)[-1].split()[0] != "Z"


@pytest.mark.skipif(
    sys.platform != "linux" or not (shutil.which("sh") and shutil.which("timeout")),
    reason="the command runs in the workspace's Linux container: its shell is tried on Linux",
)
def test_the_commands_shell_ends_it_and_every_process_it_started_when_asked(tmp_path: Path) -> None:
    pid = str(tmp_path / "clank-accept-op.pid")
    child = tmp_path / "child.pid"
    running = subprocess.Popen(["sh", "-c", accepting.RUN, "sh", pid, "2", "60", f"sleep 60 & echo $! > {child}; wait"])
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not (child.exists() and child.read_text(encoding="utf-8").strip()):
            time.sleep(0.05)  # the command at work, so that the stop ends it rather than keeps it from starting
        began = time.monotonic()
        subprocess.run(["sh", "-c", accepting.END, "sh", pid], timeout=30, check=True)
        status = running.wait(timeout=30)
    finally:
        running.kill()
    assert time.monotonic() - began < 20, "ended when asked, not at its time"
    assert status != 0
    assert not Path(pid).exists(), "its file removed"
    started = int(child.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline and alive(started):
        time.sleep(0.1)
    assert not alive(started), "every process the command started ended with it"
    late = subprocess.run(["sh", "-c", accepting.RUN, "sh", pid, "2", "60", "true"], timeout=30)
    assert late.returncode == 0, "the mark of an ended command is gone once it was ended"


def test_a_command_killed_says_it_ran_past_its_time_and_did_not_end_or_ran_out_of_memory() -> None:
    class Workspaces:
        def run_in(self, workspace: str, argv: list[str], input: bytes | None = None, timeout: float = 30) -> Answer:
            return Answer(137, "", "")

    commanded, _ = accept(cast(Any, Workspaces()), "myproject", "make check", 1)
    assert commanded.reason == (
        "its accept command `make check` was killed: it ran past its 1 minute and did not end when asked, or ran out "
        "of memory"
    )
