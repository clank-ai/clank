"""Design 0002 §2.9: Clank runs a program to read its answer with a time limit; a program that is missing, fails or
takes too long gives no answer instead of an error, within its time limit even when a process it started holds its
output open, and output in UTF-16 (as `wsl.exe` writes it) is decoded. A long command (a build) is followed line by
line as it writes, to its exit status; canceled, it is ended with every process it started. An application (Docker
Desktop) is started to run on its own, without waiting for it and without a window."""

import sys
import time
from pathlib import Path

from clank.kernel.processes import decode, launch_program, run_answer, run_command, stream_command
from tests.support.ended import wait_ended

WSL = "  NAME            STATE           VERSION\n* Ubuntu-22.04    Running         2\n"


def test_a_programs_output_is_returned() -> None:
    assert (run_command([sys.executable, "-c", "print('hello')"]) or "").strip() == "hello"


def test_a_programs_whole_answer_keeps_its_exit_status_its_output_and_its_errors() -> None:
    script = "import sys; print('out'); print('err', file=sys.stderr); raise SystemExit(3)"
    answer = run_answer([sys.executable, "-c", script])
    assert (answer.status, answer.output.strip(), answer.errors.strip(), answer.ok) == (3, "out", "err", False)
    missing = run_answer(["clank-no-such-program"])
    assert (missing.status, missing.ok) == (None, False)
    assert missing.errors.startswith("could not run clank-no-such-program")
    echoed = run_answer([sys.executable, "-c", "import sys; print(sys.stdin.read().upper())"], input=b"read me")
    assert (echoed.ok, echoed.output.strip()) == (True, "READ ME")
    slow = run_answer([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5)
    assert (slow.status, slow.errors) == (None, "no answer within 0.5 seconds")
    told = run_answer([sys.executable, "-c", "import os; print(os.environ['CLANK_TOLD'], 'PATH' in os.environ)"],
                      env={"CLANK_TOLD": "told"})  # fmt: skip
    assert told.output.split() == ["told", "True"], "added to the environment, not in place of it"


def test_a_failing_missing_or_slow_program_gives_no_answer() -> None:
    assert run_command([sys.executable, "-c", "raise SystemExit(3)"]) is None
    assert run_command(["clank-no-such-program"]) is None
    assert run_command([sys.executable, "-c", "import time; time.sleep(30)"], timeout=0.5) is None


def test_a_slow_program_gives_no_answer_within_its_time_limit_even_when_a_process_it_started_holds_its_output() -> None:
    # Docker Desktop's `docker desktop status` hands the question to a helper program that keeps the output open.
    script = (
        "import subprocess, sys, time;"
        " helper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']);"
        " print(helper.pid, flush=True); time.sleep(30)"
    )
    started = time.monotonic()
    assert run_command([sys.executable, "-c", script], timeout=1) is None
    assert time.monotonic() - started < 10


def test_an_application_is_started_to_run_on_its_own_without_waiting_for_it_and_without_a_window(
    tmp_path: Path,
) -> None:
    done = tmp_path / "done.txt"
    script = (
        "import ctypes, pathlib, sys, time; time.sleep(1); seen = False\n"
        "if sys.platform == 'win32':\n"
        "    window = ctypes.windll.kernel32.GetConsoleWindow()\n"
        "    seen = bool(window) and bool(ctypes.windll.user32.IsWindowVisible(window))\n"
        f"pathlib.Path({str(done)!r}).write_text('visible' if seen else 'hidden')"
    )
    assert launch_program([sys.executable, "-c", script])
    assert not done.exists(), "it returned before the application finished"
    deadline = time.monotonic() + 30
    while not done.exists() or not done.read_text():
        assert time.monotonic() < deadline, "the application never ran"
        time.sleep(0.05)
    assert done.read_text() == "hidden", "it showed a window"
    assert not launch_program([str(tmp_path / "clank-no-such-program")])


def test_output_in_utf16_is_decoded() -> None:
    assert decode(WSL.encode("utf-16-le")) == WSL
    assert decode(b"plain text\n") == "plain text\n"


def test_a_streamed_commands_lines_come_as_written_then_its_exit_status() -> None:
    lines: list[str] = []
    script = "print('one', flush=True); import time; time.sleep(0.3); print('two'); raise SystemExit(3)"
    assert stream_command([sys.executable, "-c", script], lines.append) == 3
    assert lines == ["one", "two"]
    assert stream_command(["clank-no-such-program"], lines.append) is None


def test_a_canceled_command_is_ended_with_the_processes_it_started() -> None:
    lines: list[str] = []
    script = (
        "import subprocess, sys, time; child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']);"
        " print(child.pid, flush=True); time.sleep(60)"
    )
    started = time.monotonic()
    assert stream_command([sys.executable, "-c", script], lines.append, canceled=lambda: bool(lines)) is None
    assert time.monotonic() - started < 30
    assert wait_ended(int(lines[0])), "the canceled command's own child still runs"
