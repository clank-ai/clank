"""Reviewing the agent's changes (design 0007): the workspace's mode, and what Clank does when the agent asks to change
a file.

The agent always asks (OpenCode cannot switch while it runs, §2); the watchers (`watch.py`) hand each ask here. A
change is worked out and kept (`changes.py`), then, in the workspace's mode (its record's `changes`):

- **review**: Clank asks the owner, as a question about the change (Accept, Reject; a reject's words go to the model),
  and answers OpenCode with what the owner chose, from whichever client;
- **auto**: Clank answers at once, as "Clank (auto mode)".

A flow's box runs in a mode of its own (design 0013 §4): the runner gives its session review or auto
(`session_mode`), which answers that session's changes and its subagents' instead of the workspace's.

A change to a plan (`plans.py`: a Markdown file in the folder, not among agents' settings or instructions, whose
header, before the change or after it, says `kind: plan`) is answered at once in either mode, as "Clank (a plan's
progress)", and shown afterwards as in auto mode: the implementer ticks its steps and writes its log without asking
each time (design 0009 §5).

Clank answers `once`, never `always`, so the mode can be switched back (§3). An answer given in the agent's terminal
settles the change and withdraws its question; a server gone withdraws the questions of its changes, and so does a
watcher's first reading for those no longer waiting. Once the file is written (`edited`), the change keeps the file as
written. Each step is an event (`agents.change_proposed`, `agents.change_answered`, `agents.change_made`;
`agents.review_switched` for a mode switched), which the clients follow: VS Code opens the change in the editor.
"""

import contextlib
import logging
import ntpath
import posixpath
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clank.components.agents.changes import NAME, ChangeStore, proposed, unified
from clank.components.agents.plans import is_plan, plan_path
from clank.components.agents.sessions import SessionError
from clank.components.agents.watch import Watchers
from clank.kernel.clock import to_text
from clank.kernel.events import Actor, EventType, Subject
from clank.kernel.questions import Option, Question, QuestionDraft, QuestionError

if TYPE_CHECKING:
    from clank.components.agents.modes import Modes
    from clank.components.agents.sessions import Sessions
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel

log = logging.getLogger(__name__)
MODES = ("review", "auto")
AUTO = Actor(kind="clank", via="auto mode")
PLAN = Actor(kind="clank", via="a plan's progress")
REVIEW = Actor(kind="clank", via="review")
TERMINAL = "the agent's terminal"
LARGEST = 4_000_000  # bytes of a file read to show a change of it
SHOWN_DIFF = 6000  # characters of a change's diff in its question
EVENT_TYPES = [
    EventType(
        "agents.change_proposed",
        "The agent asked to change a file (design 0007): in review mode it waits for your answer, in auto mode Clank "
        "answers at once.",
        {
            "workspace": "The workspace.", "change": "The change's id.", "file": "The file, in its folder.",
            "folder": "The workspace's folder.", "mode": "review or auto.", "additions": "Lines added.",
            "deletions": "Lines removed.",
        },
    ),
    EventType(
        "agents.change_answered",
        "A change the agent asked for was accepted or rejected, by you (from a client or the agent's terminal) or by "
        "auto mode.",
        {
            "workspace": "The workspace.", "change": "The change's id.", "file": "The file, in its folder.",
            "folder": "The workspace's folder.", "mode": "review or auto.", "answer": "accepted or rejected.",
            "by": "Who answered.", "note": "What a reject told the agent.",
        },
    ),
    EventType(
        "agents.change_made",
        "The agent wrote a file it was allowed to change.",
        {
            "workspace": "The workspace.", "change": "The change's id.", "file": "The file, in its folder.",
            "folder": "The workspace's folder.", "mode": "review or auto.", "additions": "Lines added.",
            "deletions": "Lines removed.",
        },
    ),
    EventType(
        "agents.review_switched",
        "A workspace's agent changes files after your review, or in auto mode without asking.",
        {"workspace": "The workspace.", "mode": "review or auto."},
    ),
]  # fmt: skip


class ReviewError(Exception):
    """A mode that cannot be set, and why."""


class Review:
    """The changes the agents ask for, and each workspace's mode."""

    def __init__(self, kernel: "Kernel", sessions: "Sessions") -> None:
        self.kernel = kernel
        self.sessions = sessions
        self.store = ChangeStore(kernel.home.state / "changes")
        self.watchers = Watchers(kernel, self.heard)
        self._lock = threading.RLock()
        self._seen: dict[str, set[str]] = {}  # the asks each workspace's watcher has said since it started
        self._writing: dict[tuple[str, str], str] = {}  # (workspace, file) accepted, not written yet: the change
        self._session_modes: dict[tuple[str, str], str] = {}  # (workspace, session): a flow's box's own mode
        self.modes: Modes | None = None  # the mode shown (design 0009 §7), set by the agents component
        kernel.questions.on_resolved(self._resolved)

    def mode(self, workspace: str) -> str:
        """The workspace's mode: review (the default) or auto."""
        record = self.kernel.settings.get("workspace", workspace).record.model_dump()
        return str(record.get("changes") or "review")

    def session_mode(self, workspace: str, session: str, mode: str | None) -> None:
        """Give one session a mode of its own, review or auto, for its changes and its subagents' (a flow's box,
        design 0013 §4); None takes it back, so the workspace's mode answers them again."""
        if mode is not None and mode not in MODES:
            raise ReviewError(f"a session's changes are reviewed (review) or made without asking (auto), not {mode}")
        with self._lock:
            if mode is None:
                self._session_modes.pop((workspace, session), None)
            else:
                self._session_modes[(workspace, session)] = mode

    def mode_of(self, workspace: str, session: str | None) -> str:
        """The mode a session's changes are answered by: its own, or that of the session it is a subagent of, else
        the workspace's."""
        parents = {each["session"]: each["parent"] for each in self.sessions.seen(workspace)}
        walked: set[str] = set()
        current = session
        while current and current not in walked:
            walked.add(current)
            with self._lock:
                own = self._session_modes.get((workspace, current))
            if own is not None:
                return own
            current = parents.get(current)
        return self.mode(workspace)

    def switch(self, workspace: str, mode: str, *, actor: Actor) -> dict[str, Any]:
        """Set the workspace's mode; it applies to the very next change."""
        if mode not in MODES:
            raise ReviewError(f"a workspace's changes are reviewed (review) or made without asking (auto), not {mode}")
        loaded = self.kernel.settings.get("workspace", workspace)
        record = loaded.record.model_dump()
        if record.get("changes") != mode:
            record["changes"] = mode
            self.kernel.settings.write("workspace", workspace, record, base=loaded.revision, actor=actor)
            said = "reviews each change" if mode == "review" else "lets the agent change files without asking"
            self.kernel.events.record(
                "agents.review_switched",
                summary=f"{actor.describe()} set {workspace} to {mode}: Clank {said}",
                actor=actor,
                subject=Subject(kind="workspace", id=workspace),
                data={"workspace": workspace, "mode": mode},
            )
        return self.view(workspace)

    def view(self, workspace: str) -> dict[str, Any]:
        """The workspace's mode, whether its agents are watched now (else why not), how many changes wait, and whether
        it has one OpenCode window at a time (design 0004 §5)."""
        waiting = sum(1 for each in self.store.recent(workspace) if each["state"] == "waiting")
        mode = self.mode(workspace)
        record = self.kernel.settings.get("workspace", workspace).record.model_dump()
        return {
            "workspace": workspace,
            "mode": mode,
            **(self.modes.shown(workspace) if self.modes is not None else {"agent": None, "shown": mode}),
            "waiting": waiting,
            "one_window": bool(record.get("one_window", True)),
            **self.watchers.state(workspace),
        }

    def view_of_folder(self, folder: str) -> dict[str, Any]:
        """The view of the workspace of a folder; `workspace` None when the folder has none."""
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        wanted = ntpath.normcase(str(Path(folder)))
        for record in workspaces.records():
            if ntpath.normcase(str(Path(record["path"]))) == wanted:
                return self.view(record["name"])
        return {"workspace": None, "mode": "review", "agent": None, "shown": "review", "waiting": 0, "one_window": True,
                "watching": False, "problem": ""}  # fmt: skip

    def reply(self, workspace: str, port: int, request: str, reply: str, *, actor: Actor, message: str = "") -> None:
        """A reply to the agent's ask from a client (the phone): a change waiting for review is answered as its
        question, so every client sees it settled; any other ask is replied to directly."""
        change = self.store.get(request)
        if change is not None and change["state"] == "waiting" and change.get("question"):
            option = "reject" if reply == "reject" else "accept"
            try:
                self.kernel.questions.answer(change["question"], by=actor, option=option, text=message)
                return
            except QuestionError:
                pass  # settled meanwhile: the agent's own answer decides
        self.sessions.permission(workspace, port, request, reply, actor=actor, message=message)

    def questioned(self, request: str) -> bool:
        """Whether an ask of the agent waits as Clank's question (so a client lists the question, not the ask)."""
        change = self.store.get(request)
        return change is not None and change["state"] == "waiting" and bool(change.get("question"))

    def heard(self, workspace: str, line: dict[str, Any]) -> None:
        """A line from a workspace's watcher; then the sessions read it (where each runs, design 0012 §3) and their
        listeners hear it, so a flow that hears an ask finds its question asked (design 0013 §5)."""
        try:
            self._heard(workspace, line)
        finally:
            self.sessions.heard(workspace, line)

    def _heard(self, workspace: str, line: dict[str, Any]) -> None:
        kind = line.get("type")
        if kind == "started":
            with self._lock:
                self._seen[workspace] = set()
        elif kind == "asked":
            self._asked(workspace, int(line["port"]), dict(line["request"]), line.get("input"))
        elif kind == "replied":
            self._replied(workspace, str(line.get("request") or ""), str(line.get("reply") or ""))
        elif kind == "edited":
            self._edited(workspace, str(line.get("file") or ""))
        elif kind == "agent" and self.modes is not None:
            self.modes.heard(workspace, line)
        elif kind == "gone":
            self._gone(workspace, int(line["port"]))
        elif kind == "synced":
            self._synced(workspace)

    def _asked(self, workspace: str, port: int, request: dict[str, Any], given: Any) -> None:
        id = str(request.get("id") or "")
        with self._lock:
            self._seen.setdefault(workspace, set()).add(id)
            if request.get("permission") != "edit" or not NAME.match(id):
                return  # not a change: the agent's terminal and the phone answer it
            known = self.store.get(id)
            if known is not None:
                if known["state"] in ("accepted", "rejected") and not known.get("written"):
                    self._send(known)  # answered while OpenCode did not hear it: say it again
                return
            change = self._change(workspace, port, request, given if isinstance(given, dict) else None)
            if change["mode"] == "review":  # asked under the lock, so an answer from the terminal waits for it
                change["question"] = self.kernel.questions.ask(self._question(change), asked_by=REVIEW).id
            self.store.save(change)
        self._record("agents.change_proposed", change, f"{workspace}'s agent asks to change {change['relative']}")
        if change["mode"] == "auto":
            self._answer(change, "accept", PLAN if change["plan"] else AUTO)

    def _change(
        self, workspace: str, port: int, request: dict[str, Any], given: dict[str, Any] | None
    ) -> dict[str, Any]:
        """A change as asked: the file before and as it would be after, its diff and counts."""
        from clank.components.workspaces.service import WORKSPACE

        workspaces: Workspaces = self.kernel.parts["workspaces"]
        folder = workspaces.folder_of(workspace)
        metadata = request.get("metadata") or {}
        file = str(metadata.get("filepath") or "")
        relative = posixpath.relpath(file, WORKSPACE) if file.startswith(WORKSPACE + "/") else file
        path = Path(folder, *relative.split("/"))
        before, problem = None, ""
        if path.is_file():
            if path.stat().st_size > LARGEST:
                problem = "too large to show beside its change: its diff shows it"
            else:
                before = path.read_bytes().decode("utf-8", errors="replace")
        after, exact = (None, False) if problem else proposed(before, given, str(metadata.get("diff") or ""))
        if after is not None:
            diff, added, removed = unified(before, after, relative)
        else:
            diff = str(metadata.get("diff") or "")
            added, removed = _counted(diff)
            problem = problem or "it could not be worked out from what the agent said: its diff shows it"
        plan = plan_path(relative) and (is_plan(before) or is_plan(after))
        return {
            "id": request["id"], "workspace": workspace, "port": port, "session": request.get("sessionID"),
            "file": file, "path": str(path), "relative": relative, "folder": folder, "before": before, "after": after,
            "exact": exact, "made": None, "diff": diff, "additions": added, "deletions": removed,
            "created": before is None and not path.exists(),
            "mode": "auto" if plan else self.mode_of(workspace, request.get("sessionID")),
            "plan": plan, "state": "waiting",
            "by": "", "note": "", "asked": to_text(self.kernel.clock.now()), "answered": "", "written": "",
            "question": None, "problem": problem,
        }  # fmt: skip

    def _question(self, change: dict[str, Any]) -> QuestionDraft:
        lines = [f"+{change['additions']}"] if change["additions"] else []
        if change["deletions"]:
            lines.append(f"-{change['deletions']}")
        counts = " ".join(lines) or "no lines"
        verb = "create" if change["created"] else "change"
        diff = change["diff"]
        shown = diff if len(diff) <= SHOWN_DIFF else diff[:SHOWN_DIFF] + f"\n… [{len(diff):,} characters]"
        return QuestionDraft(
            type="approval",
            title=f"The agent of {change['workspace']} wants to {verb} {change['relative']} ({counts})",
            detail=shown,
            options=[
                Option(id="accept", label="Accept", effect="The agent changes the file and goes on.", key="y"),
                Option(
                    id="reject", label="Reject", key="n",
                    effect="The file stays as it is; the agent is told no, and why when you say.",
                ),
            ],
            about=Subject(kind="change", id=change["id"]),
        )  # fmt: skip

    def _resolved(self, question: Question) -> None:
        """A question answered: when it is about a change still waiting, answer the agent with it."""
        if question.about is None or question.about.kind != "change" or question.answer is None:
            return
        change = self.store.get(question.about.id)
        if change is None or change["state"] != "waiting":
            return
        self._answer(change, question.answer.option or "reject", question.answer.by, question.answer.text.strip())

    def _answer(self, change: dict[str, Any], option: str, by: Actor, note: str = "") -> None:
        """Settle a change and tell the agent: accepted (once) or rejected (with the note)."""
        with self._lock:
            change = self.store.get(change["id"]) or change
            change.update(
                state="accepted" if option == "accept" else "rejected", by=by.describe(), note=note,
                answered=to_text(self.kernel.clock.now()),
            )  # fmt: skip
            self.store.save(change)
            if change["state"] == "accepted":
                self._writing[(change["workspace"], change["file"])] = change["id"]
        self._record_answer(change)
        self._send(change, by)

    def _send(self, change: dict[str, Any], by: Actor = REVIEW) -> None:
        reply = "once" if change["state"] == "accepted" else "reject"
        try:
            self.sessions.permission(
                change["workspace"], change["port"], change["id"], reply, actor=by, message=change["note"]
            )
        except SessionError as error:
            with self._lock:
                change["problem"] = f"the agent did not hear the answer: {error}"
                self.store.save(change)
            log.warning("answering %s's change %s failed: %s", change["workspace"], change["id"], error)

    def _replied(self, workspace: str, id: str, reply: str) -> None:
        """An answer OpenCode heard: one given in the agent's terminal settles the change and withdraws its question."""
        with self._lock:
            change = self.store.get(id)
            if change is None or change["state"] != "waiting":
                return  # Clank's own answer, or not a change
            change.update(
                state="rejected" if reply == "reject" else "accepted", by=TERMINAL,
                answered=to_text(self.kernel.clock.now()),
            )  # fmt: skip
            self.store.save(change)
            if change["state"] == "accepted":
                self._writing[(workspace, change["file"])] = id
        self._withdraw(change, f"answered in {TERMINAL}")
        self._record_answer(change)

    def _edited(self, workspace: str, file: str) -> None:
        """A file written: the change accepted for it keeps the file as written."""
        with self._lock:
            id = self._writing.pop((workspace, file), None)
            change = self.store.get(id) if id else None
            if change is None:
                return
            path = Path(change["path"])
            try:
                made = path.read_bytes().decode("utf-8", errors="replace") if path.stat().st_size <= LARGEST else None
            except OSError:
                made = None
            change["made"] = made
            change["written"] = to_text(self.kernel.clock.now())
            if made is not None:
                change["diff"], change["additions"], change["deletions"] = unified(
                    change["before"], made, change["relative"]
                )
            self.store.save(change)
        self._record("agents.change_made", change, f"{workspace}'s agent changed {change['relative']}")

    def _gone(self, workspace: str, port: int) -> None:
        """A server stopped: the changes it asked for and nobody answered are withdrawn."""
        for change in self._waiting(workspace):
            if change["port"] == port:
                self._settle_gone(change, "the agent stopped")

    def _synced(self, workspace: str) -> None:
        """A watcher read every running server: a change still waiting that no server asks for any more is withdrawn."""
        with self._lock:
            seen = set(self._seen.get(workspace, set()))
        for change in self._waiting(workspace):
            if change["id"] not in seen:
                self._settle_gone(change, "the agent no longer waits for it")

    def _waiting(self, workspace: str) -> list[dict[str, Any]]:
        return [
            change
            for each in self.store.recent(workspace)
            if each["state"] == "waiting" and (change := self.store.get(each["id"])) is not None
        ]

    def _settle_gone(self, change: dict[str, Any], why: str) -> None:
        with self._lock:
            change.update(state="withdrawn", note=why, answered=to_text(self.kernel.clock.now()))
            self.store.save(change)
        self._withdraw(change, why)

    def _withdraw(self, change: dict[str, Any], why: str) -> None:
        if not change.get("question"):
            return
        with contextlib.suppress(QuestionError):  # answered meanwhile
            self.kernel.questions.withdraw(change["question"], reason=why, by=REVIEW)

    def _record_answer(self, change: dict[str, Any]) -> None:
        said = f"{change['by']} {change['state']} the change to {change['relative']} in {change['workspace']}"
        self._record("agents.change_answered", change, said + (f": {change['note']}" if change["note"] else ""))

    def _record(self, type: str, change: dict[str, Any], summary: str) -> None:
        data = {
            "workspace": change["workspace"], "change": change["id"], "file": change["relative"],
            "folder": change["folder"], "mode": change["mode"],
        }  # fmt: skip
        if type == "agents.change_answered":
            data.update(answer=change["state"], by=change["by"], note=change["note"])
        else:
            data.update(additions=change["additions"], deletions=change["deletions"])
        self.kernel.events.record(
            type, summary=summary, actor=REVIEW, subject=Subject(kind="change", id=change["id"]), data=data
        )


def _counted(diff: str) -> tuple[int, int]:
    """The lines a unified diff adds and removes."""
    lines = diff.splitlines()
    added = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
    return added, removed
