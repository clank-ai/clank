"""A host the agent asks for (design 0024 §3, decision 0141): when a workspace's agent reaches a host that is not
allowed, the proxy holds the connection and asks the service; the service asks the owner.

`HostAsks.wanted(workspace, host)` allows at once when the workspace's record allows the host (`allowed`), refuses at
once within the quiet period of that workspace and host (`quiet`), and otherwise names the question: the one still
waiting for that pair, or a new one ("Let paper's agent reach api.semanticscholar.org?"; `y` always, `o` once, `n`
no, the default when it expires after `ASK_SECONDS`). `decision(question)` says how it went: `waiting`, or `always`,
`once` or `no` (an expired or withdrawn question is a no). When a question is resolved, *always* writes the allowance
into the record (the answerer the actor, so the record says who), and *no* or no answer starts the quiet period
(`QUIET_MINUTES`), so a retrying program does not flood the owner; *once* leaves everything as it was: the next
request asks again. The proxy's side is `gateway/proxy.py`; the routes are the workspaces' API.
"""

import threading
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from clank.components.gateway.proxy import ASK_SECONDS as ASK_SECONDS  # the hold's length: the proxy's
from clank.components.gateway.proxy import allowed_host
from clank.kernel.events import Actor, Subject
from clank.kernel.questions import Option, Question, QuestionDraft, QuestionError

if TYPE_CHECKING:
    from clank.kernel.core import Kernel

QUIET_MINUTES = 10  # how long a host refused is not asked for again, per workspace
ASKER = Actor(kind="clank", via="network")
KIND = "workspace"
Allow = Callable[..., Any]  # Workspaces.allow_host(name, host, allow, *, actor)


class HostAsks:
    """The questions about hosts, and the quiet periods."""

    def __init__(self, kernel: "Kernel", allow: Allow) -> None:
        self.kernel = kernel
        self.allow = allow
        self._lock = threading.Lock()
        self._open: dict[tuple[str, str], str] = {}  # the question waiting, by workspace and host
        self._pairs: dict[str, tuple[str, str]] = {}  # each question's workspace and host
        self._quiet: dict[tuple[str, str], datetime] = {}  # until when a refused host is not asked for again
        kernel.questions.on_resolved(self._resolved)

    def wanted(self, workspace: str, host: str) -> dict[str, Any]:
        """The agent of `workspace` reaches `host`: allowed by its record, quiet (refused lately), or the question to
        wait for."""
        name = host.lower().rstrip(".")
        values = self.kernel.settings.get(KIND, workspace).record.model_dump()
        if allowed_host(name, list(values.get("hosts") or {})):
            return {"allowed": True, "quiet": False, "question": None}
        key = (workspace, name)
        now = self.kernel.clock.now()
        with self._lock:
            until = self._quiet.get(key)
            if until is not None and now < until:
                return {"allowed": False, "quiet": True, "question": None}
            open_question = self._open.get(key)
        if open_question is not None and self._waiting(open_question):
            return {"allowed": False, "quiet": False, "question": open_question}
        draft = QuestionDraft(
            type="choice",
            title=f"Let {workspace}'s agent reach {name}?",
            detail=(
                f"The agent in {workspace} is reaching {name} now; its connection waits for your answer. Always "
                f"allows the host for this workspace from now on (its record keeps it; `clank workspace allow FOLDER "
                f"--no-host "
                f"{name}` takes it back); once lets this request out and asks again next time; no refuses it, and the "
                f"host is not asked for again for {QUIET_MINUTES} minutes. Private addresses are never reached."
            ),
            options=[
                Option(id="always", label="Always", key="y", effect="allowed for this workspace from now on"),
                Option(id="once", label="Once", key="o", effect="this request goes out; asked again next time"),
                Option(
                    id="no", label="No", key="n", effect=f"refused, and not asked again for {QUIET_MINUTES} minutes"
                ),
            ],
            default="no",
            expires=now + timedelta(seconds=ASK_SECONDS),
            urgency="high",
            about=Subject(kind=KIND, id=workspace),
        )
        question = self.kernel.questions.ask(draft, asked_by=ASKER)
        with self._lock:
            self._open[key] = question.id
            self._pairs[question.id] = key
        return {"allowed": False, "quiet": False, "question": question.id}

    def decision(self, question: str) -> dict[str, Any]:
        """How a question went: `waiting`; `answered` with `always`, `once` or `no`; `expired` or `withdrawn` (a no);
        `unknown` (a no) for one that is not a host's."""
        with self._lock:
            known = question in self._pairs
        if not known:
            return {"status": "unknown", "decision": "no"}
        try:
            found = self.kernel.questions.get(question)
        except QuestionError:
            return {"status": "unknown", "decision": "no"}
        if found.status == "waiting":
            return {"status": "waiting", "decision": None}
        if found.status == "answered" and found.answer is not None and found.answer.option in ("always", "once", "no"):
            return {"status": "answered", "decision": found.answer.option}
        return {"status": found.status, "decision": "no"}

    def _waiting(self, question: str) -> bool:
        try:
            return self.kernel.questions.get(question).status == "waiting"
        except QuestionError:
            return False

    def _resolved(self, question: Question) -> None:
        """A host's question answered, expired or withdrawn: the allowance written, or the quiet period begun."""
        with self._lock:
            key = self._pairs.get(question.id)
            if key is None:
                return
            if self._open.get(key) == question.id:
                del self._open[key]
        workspace, host = key
        option = question.answer.option if question.status == "answered" and question.answer is not None else None
        if option == "always":
            by = question.answer.by if question.answer is not None else ASKER
            self.allow(workspace, host, True, actor=by)
        elif option != "once":
            with self._lock:
                self._quiet[key] = self.kernel.clock.now() + timedelta(minutes=QUIET_MINUTES)
