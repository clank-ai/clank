"""Jobs in a workspace's container (design 0013 §17, decision 0132; design 0021 §6): a long computation run detached,
so no model is held waiting on a tool call. Flows' boxes start them (`flows/jobs.py`), and so does the agent the owner
talks to (`agents/jobs.py`); this is the part that runs them, given to other components through `service.py`.

**Its files are its state.** A job's folder is in the workspace, so the service reads it as files of the folder, never
asking the container: `command` (its words), `pid` (the process whose session it runs in), `log` (all it printed) and,
once it ended, `exit` (its exit status). `START` writes them: the command runs at the lowest CPU priority (`nice -n
19`: the model on the same machine keeps its speed), under `timeout` (its minutes, then `TERM`, then `KILL`
`KILL_AFTER` seconds later), in a session of its own (`setsid`), with nothing tying it to the `docker exec` that started
it. `END` ends the whole session (`pkill -s`), for a job past its minutes or no longer wanted, and writes `exit` as
`TERMINATED` when nothing else did. `ALIVE` says whether any process of the session runs, for a job whose `exit` never
came (the container restarted, a kill).
"""

import contextlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clank.components.workspaces.service import Workspaces

KILL_AFTER = 10  # seconds after its time that `timeout` kills a job that did not end when asked
TIMED_OUT = 124  # `timeout`'s exit status when it ended the job at its time
KILLED = 137  # a job killed: by `timeout`, when it did not end when asked, or for want of memory
TERMINATED = 143  # a job Clank ended
ROOT = ".clank/jobs"  # in the workspace's folder
TAIL_LINES = 60
TAIL_CHARACTERS = 6_000
WRITTEN_SHOWN = 20  # the files a job wrote, said: at most these, newest first
WRITTEN_LOOKED = 50_000  # the entries of the folder looked at for them, at most
PASSED = {".git", ".clank", "node_modules", "__pycache__", ".venv", ".mypy_cache", ".pytest_cache"}
ANSWER_SECONDS = 30  # how long the container may take to answer a start, an end or a look
# `sh -c START sh <folder> <seconds> <command> <cwd>`: the command detached, in a session of its own, its files written
START = (
    'mkdir -p "$1" && rm -f "$1/exit" "$1/pid" && printf "%s\\n" "$3" > "$1/command" && cd "$4" || exit 1; '
    'setsid sh -c \'echo $$ > "$3/pid"; nice -n 19 timeout --kill-after=' + str(KILL_AFTER) + ' "$1" sh -c "$2" '
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


def span(seconds: float) -> str:
    """A length of time in words: 40 seconds, 50 minutes, 2 hours 5 minutes."""
    whole = max(0, round(seconds))
    hours, rest = divmod(whole, 3600)
    minutes, rest = divmod(rest, 60)

    def unit(number: int, word: str) -> str:
        return f"{number} {word}{'' if number == 1 else 's'}"

    if hours:
        return unit(hours, "hour") + (f" {unit(minutes, 'minute')}" if minutes else "")
    return unit(minutes, "minute") if minutes else unit(rest, "second")


def written(folder: Path, since: float, job: str) -> list[str]:
    """The files of the workspace's folder (on this machine) written since `since` (seconds since the epoch), newest
    first, `/`-separated, the job's own folder and the folders no work is in (`PASSED`) left out; at most
    `WRITTEN_SHOWN`, of at most `WRITTEN_LOOKED` entries looked at."""
    found: list[tuple[float, str]] = []
    looked = 0
    own = job.rstrip("/") + "/"
    for top, folders, files in os.walk(folder):
        folders[:] = [each for each in folders if each not in PASSED]
        for name in files:
            looked += 1
            path = Path(top) / name
            with contextlib.suppress(OSError):
                modified = path.stat().st_mtime
                relative = path.relative_to(folder).as_posix()
                if modified >= since and not relative.startswith(own):
                    found.append((modified, relative))
        if looked >= WRITTEN_LOOKED:
            break
    return [path for _, path in sorted(found, reverse=True)[:WRITTEN_SHOWN]]


def start(workspaces: "Workspaces", workspace: str, folder: str, command: str, minutes: int) -> None:
    """Start a job in the workspace's container: `folder` its folder in the workspace, within `minutes`. `JobError`,
    saying why, when it did not start."""
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
