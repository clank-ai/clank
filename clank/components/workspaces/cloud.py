"""Where a workspace's requests may go (design 0016 §9; decisions 0103 and 0112): each workspace's bound, kept in its
record (`models`: `this-machine` for every workspace until the owner says otherwise, or `cloud`; `cloud_answered`: when
the owner last answered), given to the gateway at every change and at each start of the service.

With a cloud model in the main slot, a workspace not yet answered is asked once (`ask`), before its agent starts (any
client calls `POST /workspaces/{name}/cloud/ask` first) or when the gateway holds one of its requests
(`gateway.cloud_wanted`): "Let <workspace>'s agent use the cloud model <title>?", what goes and what never does, and for
a workspace that existed before the provider was agreed, that its earlier sessions and folder may hold research. *Allow*
makes its bound `cloud`; *keep local* is kept, and it is not asked again until the owner changes it (`allow`); a
question no one answered in 30 minutes leaves it unanswered, asked again next time. Each answer is the event
`workspaces.cloud_answered`, saying who gave it."""

from datetime import timedelta
from typing import TYPE_CHECKING, Any

from clank.components.workspaces.cloudwords import bound_said, confirm_said
from clank.kernel.clock import to_text
from clank.kernel.events import Actor, Event, EventType, Subject
from clank.kernel.questions import Option, Question, QuestionDraft, QuestionError

if TYPE_CHECKING:
    from clank.components.gateway.service import Gateway
    from clank.kernel.core import Kernel

ASKER = Actor(kind="clank", via="workspaces")
QUESTION_MINUTES = 30
KIND = "workspace"
EVENT_TYPES = [
    EventType(
        "workspaces.cloud_answered",
        "A workspace was allowed the cloud model, or kept on this machine (design 0016 §9).",
        {"workspace": "The workspace.", "models": "Its bound now: this-machine or cloud.", "who": "Who answered."},
    )
]
GOES = (
    "What goes: every request of its agent's sessions, to the cloud provider and then the model's provider: your "
    "messages, what the agent reads of the folder, command output, and its instructions."
)
NEVER = (
    "What never goes: Notion pages, and the MCP servers marked local only (a session that used one stays on this "
    "machine). What the agent wrote into the folder's files from them goes with the folder."
)
OLDER = (
    "This workspace existed before the cloud provider was agreed: its earlier sessions and its folder may hold "
    "research. A workspace made for the purpose is recommended."
)


class CloudBounds:
    """The workspaces' bounds and their question."""

    def __init__(self, kernel: "Kernel") -> None:
        self.kernel = kernel
        kernel.questions.on_resolved(self._resolved)
        kernel.events.subscribe(self._heard)

    @property
    def gateway(self) -> "Gateway":
        """The gateway's service, which keeps the bounds the gateway follows (built after this component)."""
        found: Gateway = self.kernel.parts["gateway"]
        return found

    def give(self, name: str | None = None) -> None:
        """Give the gateway each workspace's bound (or one's), as its record says."""
        for loaded in self.kernel.settings.records(KIND):
            if name is None or loaded.id == name:
                values = loaded.record.model_dump()
                self.gateway.set_bound(loaded.id, models=values["models"], answered=values["cloud_answered"])

    def view(self, name: str) -> dict[str, Any]:
        """A workspace's bound as its views carry it: `models`, `cloud_answered`, `cloud_question`, with its words
        (`cloud_said`, its line; `cloud_confirm`, what allowing it or keeping it here does)."""
        values = self.kernel.settings.get(KIND, name).record.model_dump()
        bound = self.gateway.bound(name) or {}
        question = bound.get("question")
        if question and not self._waiting(str(question)):
            question = None
        return {"models": values["models"], "cloud_answered": values["cloud_answered"], "cloud_question": question,
                "cloud_said": bound_said(name, values["models"], values["cloud_answered"]),
                "cloud_confirm": confirm_said(name)}  # fmt: skip

    def ask(self, name: str, cloud: str = "") -> dict[str, Any]:
        """Whether a workspace must be asked before its agent uses the main slot's model, and the question when it
        must (the one open, when there is one), and whether its agent may start now (`start`: the slot runs no cloud
        model, or the workspace may use it); `cloud`, the title of a cloud preset about to be loaded for it (a flow's
        box), asks of that one whatever the slot runs now."""
        values = self.kernel.settings.get(KIND, name).record.model_dump()
        main = (self.gateway.routes().get("slots") or {}).get("main") or {}
        if cloud:
            main = {"provider": "endpoint", "title": cloud}
        if main.get("provider") != "endpoint":
            return {"needed": False, "allowed": values["models"] == "cloud", "question": None, "start": True,
                    "why": "the main slot runs no cloud model"}  # fmt: skip
        if values["models"] == "cloud":
            return {"needed": False, "allowed": True, "question": None, "start": True,
                    "why": f"{name} may use the cloud model"}  # fmt: skip
        if values["cloud_answered"]:
            why = (
                f"{name} is kept on this machine. Allow the cloud for it on This folder (u), or clank workspace "
                f"allow FOLDER --cloud; or load a local model"
            )
            return {"needed": False, "allowed": False, "question": None, "start": False, "why": why}
        open_question = (self.gateway.bound(name) or {}).get("question")
        if open_question and self._waiting(str(open_question)):
            return {"needed": True, "allowed": False, "question": open_question, "start": False,
                    "why": "asked: waiting for an answer"}  # fmt: skip
        title = str(main.get("title") or main.get("preset") or "the cloud model")
        detail = " ".join([*([OLDER] if self._older(name) else []), GOES, NEVER])
        draft = QuestionDraft(
            type="choice",
            title=f"Let {name}'s agent use the cloud model {title}?",
            detail=detail,
            options=[
                Option(id="allow", label="Allow", key="y", effect="its requests go to the cloud provider from now on"),
                Option(id="local", label="Keep local", key="n", effect="it stays on this machine; not asked again"),
            ],
            default="local",
            expires=self.kernel.clock.now() + timedelta(minutes=QUESTION_MINUTES),
            urgency="high",
            about=Subject(kind=KIND, id=name),
        )
        question = self.kernel.questions.ask(draft, asked_by=ASKER)
        self.gateway.set_bound(name, question=question.id)
        return {"needed": True, "allowed": False, "question": question.id, "start": False,
                "why": "asked: waiting for an answer"}  # fmt: skip

    def allow(self, name: str, allow: bool, *, actor: Actor) -> None:
        """The owner's answer, from a client: the bound written, given to the gateway, and announced; an open question
        withdrawn."""
        open_question = (self.gateway.bound(name) or {}).get("question")
        self._answer(name, allow, actor)
        if open_question and self._waiting(str(open_question)):
            self.kernel.questions.withdraw(str(open_question), reason="answered from a client", by=actor)

    def _answer(self, name: str, allow: bool, actor: Actor) -> None:
        loaded = self.kernel.settings.get(KIND, name)
        values = {
            **loaded.record.model_dump(),
            "models": "cloud" if allow else "this-machine",
            "cloud_answered": to_text(self.kernel.clock.now()),
        }
        self.kernel.settings.write(KIND, name, values, base=loaded.revision, actor=actor)
        self.gateway.set_bound(name, models=values["models"], answered=values["cloud_answered"], question=None)
        said = f"{name} may use the cloud model" if allow else f"{name} is kept on this machine"
        self.kernel.events.record(
            "workspaces.cloud_answered",
            summary=f"{said} ({actor.describe()})",
            actor=actor,
            subject=Subject(kind=KIND, id=name),
            data={"workspace": name, "models": values["models"], "who": actor.describe()},
        )

    def _resolved(self, question: Question) -> None:
        """The workspace's question answered, expired or withdrawn."""
        if question.about is None or question.about.kind != KIND or question.asked_by != ASKER:
            return
        name = question.about.id
        if question.status == "answered" and question.answer is not None:
            self._answer(name, question.answer.option == "allow", question.answer.by)
        elif (self.gateway.bound(name) or {}).get("question") == question.id:
            self.gateway.set_bound(name, question=None)  # unanswered this time: asked again next time

    def _heard(self, event: Event) -> None:
        """A workspace's record changed: its bound is given to the gateway. The gateway holds a request of a workspace
        not yet answered: it is asked (once)."""
        if event.type == "settings.changed" and event.data.get("kind") == KIND and "gateway" in self.kernel.parts:
            if any(loaded.id == event.data.get("id") for loaded in self.kernel.settings.records(KIND)):
                self.give(str(event.data["id"]))
            return
        if event.type != "gateway.cloud_wanted":
            return
        name = str(event.data.get("workspace") or "")
        if any(loaded.id == name for loaded in self.kernel.settings.records(KIND)):
            self.ask(name)

    def _waiting(self, id: str) -> bool:
        try:
            return self.kernel.questions.get(id).status == "waiting"
        except QuestionError:
            return False

    def _older(self, name: str) -> bool:
        """Whether a workspace existed before the latest cloud provider was agreed (or nothing says when it was
        made)."""
        added = self.kernel.events.latest(1, types=["runtime.endpoint_added"])
        made = self.kernel.events.latest(1000, types=["settings.changed"], subject=Subject(kind=KIND, id=name))
        if not added or not made:
            return bool(added) and not made
        return made[-1].time < added[0].time
