"""The agent's jobs (design 0021 §6): a long computation the agent the owner talks to starts and goes on from, instead
of holding its session on a shell command that OpenCode stops after at most ten minutes.

A job is numbered in its workspace (one past the highest under `FOLDER`), its folder `.clank/jobs/agent/<n>/` in the
workspace's folder. `job.json` keeps its title, its command, its minutes, when it started (seconds since the epoch, by
the service's clock) and the session that started it, and, once Clank saw it end, when and how. The runner
(`workspaces/jobs.py`) runs it in the container at the lowest CPU priority, its process, log and exit kept as files
beside it. Its state: `starting` (no process written yet), `running`, `ended` (its status, and how in words).

`watch_once`, every `WATCH_SECONDS` while the service runs, looks at every workspace's jobs not seen to end: one past
its minutes and `GRACE` is ended; one whose exit came, or whose process the container says is gone, is recorded once
(`agents.job_ended`), and the session that started it, when it named one, is sent what happened: how it ended and after
how long, its log's last lines and the files it wrote.
"""

import contextlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio

from clank.components.workspaces.service import jobs as runner
from clank.kernel.events import CLANK, EventType, Subject

if TYPE_CHECKING:
    from clank.components.agents.sessions import Sessions
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel

log = logging.getLogger(__name__)
FOLDER = f"{runner.ROOT}/agent"  # in the workspace's folder
DEFAULT_MINUTES = 240
MOST_MINUTES = 7 * 24 * 60
GRACE = 60  # seconds past a job's minutes (and `timeout`'s kill) before Clank ends it itself
WATCH_SECONDS = 10.0
EVENT_TYPES = [
    EventType(
        "agents.job_started",
        "The agent started a job in its workspace (design 0021 §6).",
        {"workspace": "The workspace.", "job": "Its number.", "title": "Its title.", "minutes": "Its time limit."},
    ),
    EventType(
        "agents.job_ended",
        "A job of the agent's ended (design 0021 §6): how, and after how long.",
        {
            "workspace": "The workspace.", "job": "Its number.", "title": "Its title.",
            "status": "Its exit status; null when it is gone without one.", "said": "How it ended, in words.",
            "seconds": "How long it ran.",
        },
    ),
]  # fmt: skip


class JobsError(Exception):
    """A job that cannot be started, found or stopped, and why."""


class AgentJobs:
    """The jobs of the agents of every workspace."""

    def __init__(self, kernel: "Kernel", sessions: "Sessions") -> None:
        self.kernel = kernel
        self.sessions = sessions

    @property
    def workspaces(self) -> "Workspaces":
        """The workspaces' part, whose containers run the jobs."""
        found: Workspaces = self.kernel.parts["workspaces"]
        return found

    def start(
        self, workspace: str, command: str, title: str, minutes: int = DEFAULT_MINUTES, *, session: str = ""
    ) -> dict[str, Any]:
        """Start a job in the workspace's container; its number, its folder and the words for the model."""
        command, title = command.strip(), " ".join(title.split()) or "a job"
        if not command:
            raise JobsError("a job needs a command")
        if not 1 <= minutes <= MOST_MINUTES:
            raise JobsError(f"a job's minutes are 1 to {MOST_MINUTES:,} (a week)")
        root = self._root(workspace)
        number = 1 + max((int(each.name) for each in root.glob("*") if each.name.isdigit()), default=0)
        folder = f"{FOLDER}/{number}"
        kept = {"title": title, "command": command, "minutes": minutes, "session": session,
                "started": self._now(), "ended": None, "status": None, "said": ""}  # fmt: skip
        (root / str(number)).mkdir(parents=True, exist_ok=True)
        self._keep(root / str(number), kept)
        try:
            runner.start(self.workspaces, workspace, folder, command, minutes)
        except runner.JobError as error:
            raise JobsError(str(error)) from error
        self.kernel.events.record(
            "agents.job_started", summary=f"{workspace}: job {number} ({title}) started", actor=CLANK,
            subject=Subject(kind="workspace", id=workspace),
            data={"workspace": workspace, "job": number, "title": title, "minutes": minutes},
        )  # fmt: skip
        said = (
            f"job {number} ({title}) started in the container, at the lowest CPU priority, for at most {minutes} "
            f"minutes; its output goes to {folder}/log. Go on with other work, or end your turn: you are told when it "
            "ends (job_status shows it now)."
        )
        return {"job": number, "folder": folder, "said": said}

    def list(self, workspace: str) -> list[dict[str, Any]]:
        """The workspace's jobs, newest first, briefly."""
        root = self._root(workspace)
        numbers = sorted((int(each.name) for each in root.glob("*") if each.name.isdigit()), reverse=True)
        return [self._view(workspace, root / str(number), number, whole=False) for number in numbers]

    def one(self, workspace: str, number: int) -> dict[str, Any]:
        """One job whole: its state, how long it ran, its log's last lines and the files it wrote."""
        folder = self._root(workspace) / str(number)
        if not (folder / "job.json").is_file():
            raise JobsError(f"{workspace} has no job {number}")
        return self._view(workspace, folder, number, whole=True)

    def stop(self, workspace: str, number: int) -> dict[str, Any]:
        """End a job and everything it started."""
        found = self.one(workspace, number)
        if found["state"] == "ended":
            return {**found, "said": f"job {number} ({found['title']}) had ended already: {found['said']}"}
        runner.end(self.workspaces, workspace, f"{FOLDER}/{number}")
        return {**found, "said": f"job {number} ({found['title']}) is being stopped, with everything it started"}

    def watch_once(self) -> None:
        """End the jobs past their minutes, and record and tell the ones that ended (module docstring)."""
        for record in self.workspaces.records():
            workspace = str(record["name"])
            root = Path(record["path"]) / FOLDER
            for folder in sorted(root.glob("*")) if root.is_dir() else []:
                if folder.name.isdigit():
                    with contextlib.suppress(OSError, ValueError, KeyError):
                        self._watch(workspace, folder, int(folder.name))

    async def run(self) -> None:
        """Watch the jobs while the service runs."""
        while True:
            try:
                await anyio.to_thread.run_sync(self.watch_once)
            except Exception:
                log.exception("watching the agent's jobs failed")
            await anyio.sleep(WATCH_SECONDS)

    def _watch(self, workspace: str, folder: Path, number: int) -> None:
        kept = self._kept(folder)
        if kept.get("ended") is not None:
            return
        state = runner.read_state(folder)
        if not state.started:
            return
        ran = self._now() - float(kept["started"])
        if not state.ended and ran > int(kept["minutes"]) * 60 + runner.KILL_AFTER + GRACE:
            runner.end(self.workspaces, workspace, f"{FOLDER}/{number}")
            state = runner.read_state(folder)
        if not state.ended and runner.alive(self.workspaces, workspace, f"{FOLDER}/{number}") is not False:
            return
        said = runner.ended_words(state.status, minutes=int(kept["minutes"]))
        self._keep(folder, {**kept, "ended": self._now(), "status": state.status, "said": said})
        title = str(kept["title"])
        summary = f"Job {number} ({title}) {said} after {runner.span(ran)}"
        self.kernel.events.record(
            "agents.job_ended", summary=f"{workspace}: {summary}", actor=CLANK,
            subject=Subject(kind="workspace", id=workspace),
            data={"workspace": workspace, "job": number, "title": title, "status": state.status, "said": said,
                  "seconds": round(ran)},
        )  # fmt: skip
        session = str(kept.get("session") or "")
        port = self.sessions.runs(workspace, session) if session else None
        if port is not None:
            self.sessions.send(workspace, port, session, self._told(summary, folder, number, kept), actor=CLANK)

    def _told(self, summary: str, folder: Path, number: int, kept: dict[str, Any]) -> str:
        """What the session that started a job is sent when it ends."""
        end = runner.tail(folder)
        where = f"{FOLDER}/{number}/log"
        log_said = f"The last lines of its log, {where}:\n```\n{end}\n```" if end else f"Its log, {where}, is empty."
        files = runner.written(folder.parents[3], float(kept["started"]), f"{FOLDER}/{number}")
        wrote = (
            "Files written in the folder while it ran, newest first: " + ", ".join(files) + "."
            if files
            else "No file of the folder was written while it ran, besides its log."
        )
        return f"{summary}. {log_said}\n{wrote}\nGo on from here: read what you need of its output."

    def _view(self, workspace: str, folder: Path, number: int, *, whole: bool) -> dict[str, Any]:
        kept = self._kept(folder)
        state = runner.read_state(folder)
        status = state.status if state.ended else kept.get("status")
        ended = state.ended or kept.get("ended") is not None
        found: dict[str, Any] = {
            "workspace": workspace, "job": number, "title": kept["title"], "command": kept["command"],
            "minutes": kept["minutes"], "session": kept.get("session") or "", "started": kept["started"],
            "state": "ended" if ended else "running" if state.started else "starting",
            "status": status if ended else None,
            "said": (kept.get("said") or runner.ended_words(status, minutes=int(kept["minutes"]))) if ended else "",
            "seconds": round((float(kept.get("ended") or self._now())) - float(kept["started"])),
            "folder": f"{FOLDER}/{number}",
        }  # fmt: skip
        if whole:
            found["tail"] = runner.tail(folder)
            found["written"] = runner.written(folder.parents[3], float(kept["started"]), f"{FOLDER}/{number}")
        return found

    def _root(self, workspace: str) -> Path:
        try:
            return Path(self.workspaces.folder_of(workspace)) / FOLDER
        except Exception as error:  # the workspaces' own refusal: no such workspace
            raise JobsError(f"there is no workspace {workspace!r}") from error

    def _now(self) -> float:
        return self.kernel.clock.now().timestamp()

    @staticmethod
    def _kept(folder: Path) -> dict[str, Any]:
        found: dict[str, Any] = json.loads((folder / "job.json").read_text(encoding="utf-8"))
        return found

    @staticmethod
    def _keep(folder: Path, kept: dict[str, Any]) -> None:
        (folder / "job.json").write_text(json.dumps(kept, indent=2) + "\n", encoding="utf-8")
