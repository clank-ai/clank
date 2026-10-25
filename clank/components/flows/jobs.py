"""Jobs (design 0013 §17, decision 0132): a long computation a box starts with `flow_job`, run detached in the
workspace's container, so its model is not held waiting on a tool call.

The runner is the workspaces component's (`workspaces/jobs.py`, design 0021 §6: the agent the owner talks to runs jobs
the same way, each at the lowest CPU priority); its names are given here as before. What is a flow's stays here: a
job's folder in the workspace (`folder_of`: `.clank/jobs/<flow>/<run>/<box>-<n>/`), how long past its minutes Clank
waits before ending it itself (`GRACE`), and what the box waiting on it is sent when it ends (`told`).
"""

from clank.components.workspaces.service import jobs as runner

ALIVE = runner.ALIVE
ANSWER_SECONDS = runner.ANSWER_SECONDS
END = runner.END
JobError = runner.JobError
KILL_AFTER = runner.KILL_AFTER
KILLED = runner.KILLED
PASSED = runner.PASSED
ROOT = runner.ROOT
START = runner.START
State = runner.State
TAIL_CHARACTERS = runner.TAIL_CHARACTERS
TAIL_LINES = runner.TAIL_LINES
TERMINATED = runner.TERMINATED
TIMED_OUT = runner.TIMED_OUT
WRITTEN_LOOKED = runner.WRITTEN_LOOKED
WRITTEN_SHOWN = runner.WRITTEN_SHOWN
alive = runner.alive
end = runner.end
ended_words = runner.ended_words
read_state = runner.read_state
span = runner.span
start = runner.start
tail = runner.tail
written = runner.written
GRACE = 60  # seconds past a job's minutes (and `timeout`'s kill) before Clank ends it itself


def folder_of(flow: str, run: int, box: str, number: int) -> str:
    """A job's folder in the workspace, `/`-separated: by its flow's name, its run, its box and its number."""
    name = flow.split("/", 1)[-1]
    return f"{ROOT}/{name}/{run}/{box}-{number}"


def told(
    number: int, title: str, said: str, seconds: float, folder: str, end: str, files: list[str], notes: str = ""
) -> str:
    """What the box waiting on a job is sent when it ends (design 0013 §17): how it ended and after how long, its log's
    last lines (`end`), the files it wrote, the corpus's notes written meanwhile (`notes`, the index's lines), and that
    it goes on from there."""
    log = f"The last lines of its log, {folder}/log:\n```\n{end}\n```" if end else f"Its log, {folder}/log, is empty."
    wrote = (
        "Files written in the folder while it ran, newest first: " + ", ".join(files) + "."
        if files
        else "No file of the folder was written while it ran, besides its log."
    )
    learned = f"Side notes written for the corpus while it ran (read those that help):\n{notes}\n" if notes else ""
    return (
        f"Job {number} ({title}) {said} after {span(seconds)}. {log}\n{wrote}\n{learned}"
        "Go on with your task from here: read what you need of its output, then finish as your task says."
    )
