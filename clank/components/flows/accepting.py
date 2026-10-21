"""*Accept when* as a command (design 0013 §4, §5): what the runner runs in the workspace's container after a box.

A box's `accept_command` is the owner's, from the flow's file. The runner runs it after the box's session ended and its
deliverables were found written during its try (in the *collect* step), in the workspace's container, in its folder,
as its user (`sh -c`), within the box's time limit: `timeout` ends it in the container, so nothing it started outlives
it there. It passes when it exits 0. All it said is kept in the try's folder (`accept-command.txt`, `kept`); the run's
file keeps how it ended, the end of its output and the deliverables it changed (`Commanded`), and the box's next try is
told the end of its output when it failed (`told`).

**It can be stopped.** `RUN` starts `timeout` in the background and writes its process id to a file of the box's
operation (`pid_file`), so that `END`, run in the container when the owner stops the run, the operation is canceled or
the service stops, can send it `TERM`: `timeout` passes it on to every process the command started, and kills them
`KILL_AFTER` seconds later if they have not ended. `END` waits a few seconds for the file, and leaves a mark that keeps
the command from starting if it had not started yet.
"""

import contextlib
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from clank.components.workspaces.service import Workspaces

KILL_AFTER = 10  # seconds after its time that `timeout` kills a command that did not end when asked
GRACE = 30  # seconds the runner waits past the command's time for the container to answer
ENDING = 15  # seconds the runner waits for the container to say it ended a command
TIMED_OUT = 124  # `timeout`'s exit status when it ended the command at its time
KILLED = 137  # a command killed: by `timeout`, when it did not end when asked, or for want of memory
TAIL_LINES = 40
TAIL_CHARACTERS = 4_000
# `sh -c RUN sh <pid file> <kill after> <seconds> <command>`: the command under `timeout`, its process id in the file
RUN = (
    'if [ -e "$1.stop" ]; then rm -f "$1.stop"; exit 143; fi; '
    'timeout --kill-after="$2" "$3" sh -c "$4" & echo $! > "$1"; wait $!; status=$?; rm -f "$1"; exit $status'
)
# `sh -c END sh <pid file>`: `TERM` to that `timeout`, once its file says which process it is
END = (
    'touch "$1.stop"; i=0; while [ ! -s "$1" ] && [ $i -lt 25 ]; do sleep 0.2; i=$((i + 1)); done; '
    'if [ -s "$1" ]; then rm -f "$1.stop"; kill -TERM "$(cat "$1")" 2>/dev/null; fi; exit 0'
)


class Commanded(BaseModel):
    """A box's accept command as it ran: its words, how it ended, the end of its output, and what it changed."""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(description="The command, as the flow's file says it.")
    status: int | None = Field(description="Its exit status; empty when the container gave none.")
    ended: str = Field(description="How it ended, in words: exited 0, ran past its time, could not run.")
    tail: str = Field("", description="The end of its output (its last 40 lines, at most 4,000 characters).")
    changed: list[str] = Field(
        default_factory=list,
        description="The deliverables it changed (a formatter, a generator): the try keeps them as it left them.",
    )

    @property
    def passed(self) -> bool:
        """Whether it exited 0."""
        return self.status == 0

    @property
    def reason(self) -> str:
        """Why the box failed, when it did not pass."""
        return f"its accept command `{self.command}` {self.ended}"


@dataclass(frozen=True)
class Ran:
    """A box's accept command once it ran, or was ended: how, all it said, and the fingerprints (by path) of the
    deliverables before it, to tell which it changed."""

    commanded: Commanded
    said: str
    before: dict[str, str]


def pid_file(tag: str) -> str:
    """Where in the container the command's `timeout` writes its process id: a file of `tag`, the box's operation."""
    return f"/tmp/clank-accept-{re.sub(r'[^A-Za-z0-9_.-]', '-', tag)}.pid"


def accept(
    workspaces: "Workspaces", workspace: str, command: str, minutes: int, tag: str = "accept"
) -> tuple[Commanded, str]:
    """Run a box's accept command in the workspace's container, within `minutes`: how it ended, and all it said."""
    from clank.components.workspaces.service import WorkspaceUnavailable

    seconds = minutes * 60
    argv = ["sh", "-c", RUN, "sh", pid_file(tag), str(KILL_AFTER), str(seconds), command]
    try:
        answer = workspaces.run_in(workspace, argv, timeout=seconds + KILL_AFTER + GRACE)
    except WorkspaceUnavailable as error:
        return Commanded(command=command, status=None, ended=f"could not run: {error}"), ""
    said = answer.output + (("\n" if answer.output and not answer.output.endswith("\n") else "") + answer.errors)
    span = f"{minutes} minute" + ("" if minutes == 1 else "s")
    if answer.status == TIMED_OUT:
        ended = f"ran past its {span} and was ended"
    elif answer.status == KILLED:
        ended = f"was killed: it ran past its {span} and did not end when asked, or ran out of memory"
    elif answer.status is None:
        ended = f"gave no exit status: {answer.errors.strip() or 'the container did not answer'}"
    else:
        ended = f"exited {answer.status}"
    return Commanded(command=command, status=answer.status, ended=ended, tail=_tail(said)), said


def end(workspaces: "Workspaces", workspace: str, tag: str) -> None:
    """End the accept command of `tag` in the workspace's container, with every process it started (`END`)."""
    from clank.components.workspaces.service import WorkspaceUnavailable

    with contextlib.suppress(WorkspaceUnavailable):  # its container does not run: nor does the command
        workspaces.run_in(workspace, ["sh", "-c", END, "sh", pid_file(tag)], timeout=ENDING)


def kept(commanded: Commanded, said: str) -> str:
    """The command and all it said, for `accept-command.txt` in the try's folder."""
    verdict = "it passes" if commanded.passed else "it does not pass"
    body = said if said.endswith("\n") or not said else said + "\n"
    text = f"$ {commanded.command}\n{body}\nIt {commanded.ended}: {verdict}.\n"
    if commanded.changed:
        them = "it" if len(commanded.changed) == 1 else "them"
        text += f"It changed {', '.join(commanded.changed)}: the try keeps {them} as it left {them}.\n"
    return text


def told(commanded: Commanded) -> str:
    """What a box's next try is told of an accept command that failed: the end of its output."""
    if not commanded.tail.strip():
        return "It said nothing."
    fence = "```"
    while fence in commanded.tail:
        fence += "`"
    return f"The end of what it said:\n\n{fence}\n{commanded.tail.rstrip(chr(10))}\n{fence}"


def _tail(said: str) -> str:
    lines = said.replace("\r\n", "\n").rstrip("\n").split("\n")
    tail = "\n".join(lines[-TAIL_LINES:])
    return tail[-TAIL_CHARACTERS:]
