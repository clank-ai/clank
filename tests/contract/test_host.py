"""Design 0003 §2 and decision 0030: every host meets the same contract: a process it starts is alive by its identity
until it is stopped, stops once, and is gone after; it reads a file's facts; and it runs a step (of an install) to
its end in its folder, with its environment, each line of its output given as it comes, and its exit status. A host
whose program is the running system itself runs the contract live; any other runs it against what its program
answered at each recorded version, with the inputs the recording was made with."""

import hashlib
import json
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

import pytest

from clank.components.runtime.hosts import HOSTS
from clank.components.runtime.hosts.host import EngineHost
from tests.fakes.recorded import RecordedProgram, recordings


@dataclass
class Scenario:
    """A host, and what the contract asks of it."""

    host: EngineHost
    argv: list[str]
    cwd: str
    log: Path
    file: str
    size: int
    sha256: str
    missing: str
    step_argv: list[str]
    step_env: dict[str, str]
    step_cwd: str
    step_lines: list[str]
    step_status: int


def live(adapter: type[EngineHost], folder: Path) -> Scenario:
    sample = folder / "sample.bin"
    sample.write_bytes(b"clank")
    child = [sys.executable, "-c", "import time; time.sleep(600)"]
    host = cast(Callable[[], EngineHost], adapter)()  # the running system's host takes nothing
    step = [
        sys.executable,
        "-c",
        "import os; print('one'); print(os.environ['CLANK_STEP']); print(os.path.basename(os.getcwd())); exit(3)",
    ]
    return Scenario(
        host, child, str(folder), folder / "child.log", str(sample), 5,
        hashlib.sha256(b"clank").hexdigest(), str(folder / "missing.bin"),
        step, {"CLANK_STEP": "two"}, str(folder / "made" / "step"), ["one", "two", "step"], 3,
    )  # fmt: skip


def replayed(adapter: type[EngineHost], folder: Path) -> Scenario:
    recording: dict[str, Any] = json.loads((folder / "program.json").read_text(encoding="utf-8"))
    inputs = recording["inputs"]
    program = RecordedProgram(recording)
    make = cast(Callable[..., EngineHost], adapter)  # a recorded host takes how to run its program, and its name
    host = make(lambda argv, timeout=0.0: program(argv), inputs["distro"], stream=program.stream)
    return Scenario(
        host, inputs["argv"], inputs["cwd"], Path(inputs["log"]), inputs["file"], inputs["size"], inputs["sha256"],
        inputs["missing"], inputs["step_argv"], inputs["step_env"], inputs["step_cwd"], inputs["step_lines"],
        inputs["step_status"],
    )  # fmt: skip


LIVE = [pytest.param(adapter, None, id=f"{adapter.NAME}-live") for adapter in HOSTS.all() if not adapter.RECORDED]
CASES = LIVE + [
    pytest.param(adapter, folder, id=f"{adapter.NAME}-{folder.name}")
    for adapter in HOSTS.all()
    if adapter.RECORDED
    for folder in recordings(adapter.NAME)
]


def scenario(adapter: type[EngineHost], folder: Path | None, tmp_path: Path) -> Scenario:
    return live(adapter, tmp_path) if folder is None else replayed(adapter, folder)


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_a_started_process_is_alive_by_its_identity_until_it_stops_once(
    adapter: type[EngineHost], folder: Path | None, tmp_path: Path
) -> None:
    case = scenario(adapter, folder, tmp_path)
    identity = case.host.spawn(case.argv, {}, case.cwd, case.log)
    assert identity.host == case.host.name
    assert case.host.alive(identity)
    assert case.host.stop(identity, 5) in ("stopped", "killed")
    assert not case.host.alive(identity)
    assert case.host.stop(identity, 5) == "gone"


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_it_reads_a_files_facts(adapter: type[EngineHost], folder: Path | None, tmp_path: Path) -> None:
    case = scenario(adapter, folder, tmp_path)
    assert (case.host.exists(case.file), case.host.size(case.file)) == (True, case.size)
    assert case.host.sha256(case.file) == case.sha256
    assert (case.host.exists(case.missing), case.host.size(case.missing), case.host.sha256(case.missing)) == (
        False,
        None,
        None,
    )


@pytest.mark.parametrize(("adapter", "folder"), CASES)
def test_a_step_runs_to_its_end_in_its_folder_with_its_environment_each_line_as_it_comes(
    adapter: type[EngineHost], folder: Path | None, tmp_path: Path
) -> None:
    case = scenario(adapter, folder, tmp_path)
    lines: list[str] = []
    status = case.host.run_step(case.step_argv, case.step_env, case.step_cwd, lines.append, lambda: False)
    assert (status, lines) == (case.step_status, case.step_lines)
