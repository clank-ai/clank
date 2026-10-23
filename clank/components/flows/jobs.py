"""Jobs (design 0013 §17, decision 0132): a long computation a box starts with `flow_job`, run detached in the
workspace's container, so its model is not held waiting on a tool call.

**Its files are its state.** A job's folder is in the workspace (`folder_of`: `.clank/jobs/<flow>/<run>/<box>-<n>/`),
so the service reads it as files of the folder, never asking the container: `command` (its words), `pid` (the process
whose session it runs in), `log` (all it printed) and, once it ended, `exit` (its exit status). `START` writes them:
the command runs under `timeout` (its minutes, then `TERM`, then `KILL` `KILL_AFTER` seconds later) in a session of its
own (`setsid`), with nothing tying it to the `docker exec` that started it. `END` ends the whole session (`pkill -s`),
for a job past its minutes or whose run stopped, and writes `exit` as `TERMINATED` when nothing else did. `ALIVE` says
whether any process of the session runs, for a job whose `exit` never came (the container restarted, a kill).
"""

import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from clank.components.flows.accepting import KILL_AFTER, KILLED, TIMED_OUT

if TYPE_CHECKING:
    from clank.components.workspaces.service import Workspaces

__all__ = ["KILLED", "KILL_AFTER", "TIMED_OUT"]  # with what follows: a job's statuses are a box command's
ROOT = ".clank/jobs"  # in the workspace's folder
TERMINATED = 143  # a job Clank ended
TAIL_LINES = 60
TAIL_CHARACTERS = 6_000
ANSWER_SECONDS = 30  # how long the container may take to answer a start, an end or a look
# `sh -c START sh <folder> <seconds> <command> <cwd>`: the command detached, in a session of its own, its files written
START = (
    'mkdir -p "$1" && rm -f "$1/exit" "$1/pid" && printf "%s\\n" "$3" > "$1/command" && cd "$4" || exit 1; '
    'setsid sh -c \'echo $$ > "$3/pid"; timeout --kill-after=' + str(KILL_AFTER) + ' "$1" sh -c "$2" '
    '> "$3/log" 2>&1; echo $? > "$3/exit"\' sh "$2" "$3" "$1" > /dev/null 2>&1 < /dev/null & '
    'i=0; while [ ! -s "$1/pid" ] && [ $i -lt 50 ]; do sleep 0.1; i=$((i + 1)); done; [ -s "$1/pid" ]'
)
# `sh -c END sh <folder>`: `TERM` to every process of the job's session, `KILL` to what is left, its exit written
END = (
    'p=$(cat "$1/pid" 2>/dev/null); [ -n "$p" ] || exit 0; pkill -TERM -s "$p" 2>/dev/null; i=0; '
    'while pgrep -s "$p" > /dev/null 2>&1 && [ $i -lt 100 ]; do sleep 0.1; i=$((i + 1)); done; '
    'pkill -KILL -s "$p" 2>/dev/null; [ -e "$1/exit" ] || echo ' + str(TERMINATED) + ' > "$1/exit"; exit 0'
)
# `sh -c ALIVE sh <folder>`: exits 0 while a process of the job's session runs
ALIVE = 'p=$(cat "$1/pid" 2>/dev/null); [ -n "$p" ] && pgrep -s "$p" > /dev/null 2>&1'


class JobError(Exception):
    """A job that could not be started, and why."""


@dataclass(frozen=True)
class State:
    """A job as its files say: started (its process id written), ended (its exit written), and its status."""

    started: bool
    ended: bool
    status: int | None


def folder_of(flow: str, run: int, box: str, number: int) -> str:
    """A job's folder in the workspace, `/`-separated: by its flow's name, its run, its box and its number."""
    name = flow.split("/", 1)[-1]
    return f"{ROOT}/{name}/{run}/{box}-{number}"


def read_state(folder: Path) -> State:
    """A job's state from its files (`folder` on this machine)."""
    started = (folder / "pid").is_file()
    ended = (folder / "exit").is_file()
    status = None
    if ended:
        with contextlib.suppress(OSError, ValueError):
            status = int((folder / "exit").read_text(encoding="utf-8").strip())
    return State(started=started, ended=ended, status=status)


def tail(folder: Path, lines: int = TAIL_LINES, characters: int = TAIL_CHARACTERS) -> str:
    """The end of a job's log: its last `lines` lines, at most `characters`."""
    try:
        text = (folder / "log").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    end = "\n".join(text.replace("\r\n", "\n").rstrip("\n").split("\n")[-lines:])
    return end[-characters:]


def ended_words(status: int | None, *, minutes: int) -> str:
    """How a job ended, in words."""
    if status is None:
        return "is gone: its process ended without an exit code"
    if status == TIMED_OUT:
        return f"ran past its {minutes} minute{'' if minutes == 1 else 's'} and was ended"
    if status == TERMINATED:
        return "was ended by Clank"
    if status == KILLED:
        return "was killed: it did not end when asked, or ran out of memory"
    return f"exited {status}"


def start(workspaces: "Workspaces", workspace: str, folder: str, command: str, minutes: int) -> None:
    """Start a job in the workspace's container: `folder` its folder in the workspace (`folder_of`), within
    `minutes`. `JobError`, saying why, when it did not start."""
    from clank.components.workspaces.service import WORKSPACE, WorkspaceUnavailable

    inside = f"{WORKSPACE}/{folder}"
    argv = ["sh", "-c", START, "sh", inside, str(minutes * 60), command, WORKSPACE]
    try:
        answer = workspaces.run_in(workspace, argv, timeout=ANSWER_SECONDS)
    except WorkspaceUnavailable as error:
        raise JobError(f"the job could not start: {error}") from error
    if answer.status != 0:
        said = (answer.errors or answer.output).strip() or f"its start exited {answer.status}"
        raise JobError(f"the job could not start: {said}")


def end(workspaces: "Workspaces", workspace: str, folder: str) -> None:
    """End a job and every process it started (`END`); nothing when its container does not run."""
    from clank.components.workspaces.service import WORKSPACE, WorkspaceUnavailable

    with contextlib.suppress(WorkspaceUnavailable):
        workspaces.run_in(workspace, ["sh", "-c", END, "sh", f"{WORKSPACE}/{folder}"], timeout=ANSWER_SECONDS)


def alive(workspaces: "Workspaces", workspace: str, folder: str) -> bool | None:
    """Whether a process of the job still runs; None when the container cannot say."""
    from clank.components.workspaces.service import WORKSPACE, WorkspaceUnavailable

    try:
        argv = ["sh", "-c", ALIVE, "sh", f"{WORKSPACE}/{folder}"]
        answer = workspaces.run_in(workspace, argv, timeout=ANSWER_SECONDS)
    except WorkspaceUnavailable:
        return None
    if answer.status is None:
        return None
    return answer.status == 0
