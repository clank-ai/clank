"""Design 0001 §8.4: one command runs every check that continuous integration runs, names each one that fails, and
with `--fix` first rewrites what can be rewritten safely."""

from collections.abc import Sequence

import pytest

from tools.check import CHECKS, FIXES, main


class Recorder:
    def __init__(self, failing: str = "") -> None:
        self.commands: list[list[str]] = []
        self.failing = failing

    def __call__(self, command: Sequence[str]) -> int:
        self.commands.append(list(command))
        return 1 if self.failing and self.failing in command else 0


def test_every_check_runs_and_success_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    recorder = Recorder()
    assert main([], recorder) == 0
    assert recorder.commands == [command for _, command in CHECKS]
    assert "every check passed" in capsys.readouterr().out


def test_a_failure_does_not_stop_the_other_checks_and_is_named(capsys: pytest.CaptureFixture[str]) -> None:
    recorder = Recorder(failing="mypy")
    assert main([], recorder) == 1
    assert len(recorder.commands) == len(CHECKS)
    assert "failed: types" in capsys.readouterr().out


def test_fix_rewrites_first_then_checks() -> None:
    recorder = Recorder()
    assert main(["--fix"], recorder) == 0
    assert recorder.commands == [command for _, command in FIXES + CHECKS]


def test_the_types_are_checked_as_on_windows_and_as_on_linux_each_with_its_own_cache() -> None:
    typed = [command for _, command in CHECKS if "mypy" in command]
    assert sorted(command[command.index("--platform") + 1] for command in typed) == ["linux", "win32"]
    assert len({command[command.index("--cache-dir") + 1] for command in typed}) == 2
