"""Design 0001 §8.4 and decision 0028: `tools.check` checks the VS Code extension too: it installs the extension's
tools from their lock when they are missing or older than the lock, then compiles and tests it; without npm it says
what to install."""

from collections.abc import Sequence
from pathlib import Path

import pytest

from tools.extension import check


class Runner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, command: Sequence[str], folder: Path) -> int:
        self.calls.append(list(command))
        return 0


def project(tmp_path: Path, installed: bool) -> Path:
    folder = tmp_path / "vscode"
    folder.mkdir()
    (folder / "package-lock.json").write_text("{}", encoding="utf-8")
    if installed:
        (folder / "node_modules").mkdir()
        (folder / "node_modules" / ".package-lock.json").write_text("{}", encoding="utf-8")
    return folder


def test_without_npm_it_says_what_to_install(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert check(project(tmp_path, False), which=lambda name: None, runner=Runner()) == 1
    assert "Node 22" in capsys.readouterr().out


def test_it_installs_from_the_lock_when_the_tools_are_missing_then_checks(tmp_path: Path) -> None:
    runner = Runner()
    assert check(project(tmp_path, False), which=lambda name: "npm", runner=runner) == 0
    assert runner.calls == [["npm", "ci", "--no-audit", "--no-fund"], ["npm", "run", "check"]]


def test_with_its_tools_installed_it_only_checks(tmp_path: Path) -> None:
    runner = Runner()
    assert check(project(tmp_path, True), which=lambda name: "npm", runner=runner) == 0
    assert runner.calls == [["npm", "run", "check"]]


def test_asked_for_the_host_suite_it_runs_it_inside_vscode_after_the_checks(tmp_path: Path) -> None:
    runner = Runner()
    assert check(project(tmp_path, True), which=lambda name: name, runner=runner, host=True, display=True) == 0
    assert runner.calls == [["npm", "run", "check"], ["npm", "run", "test:host"]]


def test_without_a_display_the_host_suite_runs_under_a_virtual_one(tmp_path: Path) -> None:
    runner = Runner()
    assert check(project(tmp_path, True), which=lambda name: name, runner=runner, host=True, display=False) == 0
    assert runner.calls[-1] == ["xvfb-run", "-a", "npm", "run", "test:host"]
