"""Design 0028 §6 (decisions 0170 and 0171): continuous integration's release gate. Python 3.12, the Python Clank
installs with, runs on Linux and on Windows on every push, and so does an install made as the installers make it, with
constraints.txt; a push to main runs to its end, so each has its verdict; the release waits for those lanes alone,
Python 3.14 being a canary that holds none; each Monday the checks run on the newest dependencies. The workflow is
read as text, since Clank has no YAML library (design 0014 §7)."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKS = (ROOT / ".github" / "workflows" / "checks.yml").read_text(encoding="utf-8")
NOT_SCHEDULED = "if: github.event_name != 'schedule'"


def job(name: str) -> str:
    """One job of the checks, as its text: from its key to the next job's."""
    found = re.search(rf"\n  {re.escape(name)}:\n(.*?)(?=\n  [a-z][a-z0-9-]*:\n|\Z)", CHECKS, re.S)
    assert found, f"no job {name}"
    return found.group(1)


def head(name: str) -> str:
    """A job's settings, before its steps."""
    return job(name).split("steps:", 1)[0]


def test_python_3_12_runs_on_linux_and_windows_on_every_push() -> None:
    lanes = head("oldest-python")
    assert "os: [ubuntu-24.04, windows-2025]" in lanes
    assert 'python-version: "3.12"' in job("oldest-python")
    assert "uv run --locked python -m tools.check" in job("oldest-python")
    assert [line.strip() for line in lanes.splitlines() if "if:" in line] == [NOT_SCHEDULED], "every push"


def test_an_install_as_users_make_it_runs_on_every_push_and_checks_each_version() -> None:
    installed = job("installed")
    assert [line.strip() for line in head("installed").splitlines() if "if:" in line] == [NOT_SCHEDULED]
    assert "uv tool install --constraints constraints.txt --python 3.12 ." in installed
    assert "metadata.version(name)" in installed, "each dependency at the version constraints.txt names"
    assert "clank --version" in installed


def test_a_push_to_main_runs_to_its_end_and_only_a_pull_request_cancels_its_older_run() -> None:
    concurrency = CHECKS.split("\nconcurrency:\n", 1)[1].split("\n\n", 1)[0]
    assert "cancel-in-progress: ${{ github.event_name == 'pull_request' }}" in concurrency


def test_the_release_waits_for_the_3_12_lanes_and_the_install_and_not_the_canary() -> None:
    release = head("release")
    assert "needs: [oldest-python, installed]" in release
    assert "newest-python" not in release, "Python 3.14 holds no release"
    canary = head("newest-python")
    assert "github.event.schedule == '17 5 * * *'" in canary, "each night"
    assert "startsWith(github.ref, 'refs/tags/')" in canary, "and each tag"


def test_each_monday_the_checks_run_on_the_newest_dependencies() -> None:
    assert '- cron: "41 6 * * 1"' in CHECKS
    newest = job("newest-dependencies")
    assert "github.event.schedule == '41 6 * * 1'" in head("newest-dependencies")
    assert newest.index("uv lock --upgrade") < newest.index("uv run python -m tools.constraints")
    assert newest.index("uv run python -m tools.constraints") < newest.index("uv run python -m tools.check")
