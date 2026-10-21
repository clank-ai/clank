"""Design 0001 §8.3: adapters are tested against what the real program answered at its pinned version. The recorded
program answers each command as recorded for its current state, moves between states on the recorded commands, and
fails on any command that was never recorded, so an adapter that starts asking something new is caught. It keeps time
as the real program did: an answer that never came, or came later than the caller waits, is lost, the caller having
waited its whole time limit; an application it launches answers by its name; and it says on which platform it was
recorded and where its command was."""

import json
from pathlib import Path

import pytest

from tests.fakes.recorded import RecordedProgram

RECORDING = {
    "program": "Example",
    "version": "1.2.3",
    "recorded": "2026-10-11",
    "how": "Made up for this test.",
    "initial": "running",
    "states": {
        "running": {"tool status": [0, "running\n"], "tool stop": [0, ""]},
        "stopped": {"tool status": [1, "stopped\n"], "tool start": [0, ""]},
    },
    "transitions": {"tool stop": "stopped", "tool start": "running"},
}


SLOW = {
    **RECORDING,
    "platform": "win32",
    "command": r"C:\Programs\Tool\tool.exe",
    "states": {
        "running": {"tool stop": [0, "stopping\n", 13.0]},
        "stopped": {"tool status": [None, "", 16.2], "tool start": [0, "already running\n"], "Tool App": [0, ""]},
    },
    "transitions": {"tool stop": "stopped", "Tool App": "running"},
}


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    folder = tmp_path / "example" / "1.2.3"
    folder.mkdir(parents=True)
    (folder / "program.json").write_text(json.dumps(RECORDING), encoding="utf-8")
    return folder


def test_the_recorded_program_answers_by_state_and_moves_on_its_transitions(folder: Path) -> None:
    program = RecordedProgram.load(folder)
    assert (program.name, program.version) == ("Example", "1.2.3")
    assert program(["tool", "status"]) == "running\n"
    assert program([r"C:\Programs\tool.exe", "stop"]) == ""
    assert program.state == "stopped"
    assert program(["tool", "status"]) is None
    assert program.calls == ["tool status", "tool stop", "tool status"]


def test_it_can_start_in_another_state(folder: Path) -> None:
    program = RecordedProgram.load(folder, state="stopped")
    assert program(["tool", "status"]) is None


def test_a_command_never_recorded_fails_the_test(folder: Path) -> None:
    program = RecordedProgram.load(folder)
    with pytest.raises(AssertionError, match="never recorded"):
        program(["tool", "remove", "everything"])


def test_an_answer_that_never_came_keeps_the_caller_waiting_its_whole_time_limit() -> None:
    program = RecordedProgram(SLOW, state="stopped")
    assert program(["tool", "status"], timeout=2) is None
    assert program.waited == 2


def test_an_answer_later_than_the_time_limit_is_lost_and_changes_nothing() -> None:
    program = RecordedProgram(SLOW)
    assert program(["tool", "stop"], timeout=5) is None
    assert (program.state, program.waited) == ("running", 5)
    assert program(["tool", "stop"], timeout=60) == "stopping\n"
    assert (program.state, program.waited) == ("stopped", 18)


def test_an_application_it_launches_answers_by_its_name_and_moves_it_on() -> None:
    program = RecordedProgram(SLOW, state="stopped")
    assert program([r"C:\Programs\Tool\tool.exe", "start"]) == "already running\n"
    assert program.state == "stopped"
    assert program.launch([r"C:\Programs\Tool\Tool App.exe"])
    assert (program.state, program.calls[-1]) == ("running", "Tool App")
    assert (program.platform, program.command) == ("win32", r"C:\Programs\Tool\tool.exe")
