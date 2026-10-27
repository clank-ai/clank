"""A program as it was recorded: what an adapter's contract test runs against (design 0001 §8.3, design 0002 §2.10).

A recording, `tests/fixtures/<adapter>/<version>/program.json`, holds what the real program answered at that version:
for each of its states (running, stopped, no access), each command with its exit status, its output and, when it took
a while, how many seconds (an exit status of null: no answer ever came), and, as a fourth value, its errors (design
0014 §2: Docker's words for no access are in its errors); and which commands move it to another state; and, when it
matters, the platform it was recorded on (`sys.platform`'s word) and where its command was. `RecordedProgram` answers
like `run_command` does (the output when the command succeeded, None when it failed or did not answer within the time
limit, the caller then having waited the whole limit, counted in `waited`), like `run_answer` does (`answer`: the
exit status, the output and the errors), like `stream_command` does (`stream`: each line of the output, then the exit
status), or like `launch_program` does (`launch`: an application started, answering by its name); it keeps every
call, and fails the test on a command that was never recorded, so an adapter that starts asking something new is
caught and recorded again. A command is matched without its folder or `.exe`, so a recording made on one platform
answers the adapter on any.
"""

import json
from collections.abc import Callable, Sequence
from pathlib import Path, PureWindowsPath
from typing import Any

from clank.kernel.processes import TIMEOUT_SECONDS, Answer

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


class RecordedProgram:
    """A recorded program, in one of its states."""

    def __init__(self, recording: dict[str, Any], state: str | None = None) -> None:
        self.name: str = recording["program"]
        self.version: str = recording["version"]
        self.platform: str = recording.get("platform", "")
        self.command: str | None = recording.get("command")
        self.state: str = state or recording["initial"]
        self.calls: list[str] = []
        self.waited = 0.0
        self._states: dict[str, dict[str, list[Any]]] = recording["states"]
        self.transitions: dict[str, str] = recording["transitions"]  # none: a platform Clank never starts

    @classmethod
    def load(cls, folder: Path, state: str | None = None) -> "RecordedProgram":
        """The recording in a folder (`<adapter>/<version>/`), starting in its initial state or the one given."""
        return cls(json.loads((folder / "program.json").read_text(encoding="utf-8")), state)

    def __call__(self, arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS) -> str | None:
        status, output, _ = self._answer(arguments, timeout)
        return output if status == 0 else None

    def answer(self, arguments: Sequence[str], timeout: float = TIMEOUT_SECONDS, input: bytes | None = None) -> Answer:
        """The whole answer, as `run_answer` gives it: the exit status (None when no answer came in time, its errors
        then saying so unless the recording says why), the output and the errors; what it would read is ignored."""
        status, output, errors = self._answer(arguments, timeout)
        if status is None and not errors:
            errors = f"no answer within {timeout:g} seconds"
        return Answer(status, output, errors)

    def stream(
        self, arguments: Sequence[str], line: Callable[[str], None], *, canceled: Callable[[], bool] = lambda: False
    ) -> int | None:
        """The recorded output, line by line, then the recorded exit status."""
        status, output, _ = self._answer(arguments, None)
        for text in output.splitlines():
            line(text)
        return status

    def launch(self, arguments: Sequence[str]) -> bool:
        """An application started to run on its own: whether it started."""
        status, _, _ = self._answer(arguments, None)
        return status == 0

    def _answer(self, arguments: Sequence[str], timeout: float | None) -> tuple[int | None, str, str]:
        command = " ".join([PureWindowsPath(arguments[0]).stem, *arguments[1:]])
        self.calls.append(command)
        answers = self._states[self.state]
        assert command in answers, f"{self.name} {self.version} never recorded `{command}` in the state {self.state}"
        status, output, *rest = answers[command]
        seconds = float(rest[0]) if rest else 0.0
        errors = str(rest[1]) if len(rest) > 1 else ""
        if status is None or (timeout is not None and seconds > timeout):
            self.waited += timeout if timeout is not None else seconds
            return None, "", errors if status is None else ""
        self.waited += seconds
        self.state = self.transitions.get(command, self.state)
        return int(status), str(output), errors


def recordings(adapter: str) -> list[Path]:
    """The folders of an adapter's recordings, one per version."""
    return sorted(path.parent for path in (FIXTURES / adapter).glob("*/program.json"))
