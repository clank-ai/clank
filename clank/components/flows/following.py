"""The next flow (design 0013 §3, §10, §11; decisions 0058 and 0091): made once a flow's last gate is approved.

When a run ends done after its last box, a GATE, was approved, the next flow is made from Clank's template
(`templates/flow.json`) with the brief that the last INTEGRATE before that gate wrote (`brief_of`: its `NEXT.md`, else
the last of its two or more files): kept as `<name>-<n>` in the same workspace (`next_name`), titled by the brief's
first heading (`title_of`), its values the template's with the workspace, this flow's model, its first box's words and
where it came from (`next_values`, `follows`); this flow's `next` names it, so the two are linked both ways. Nothing in
the folder changes then: when the next flow's first run starts, the brief is copied into its first box's file, unless
the owner changed that file since it was made (`follows.replaces`), and the YOU box asks the owner for it as for any
brief. The owner is asked whether to run it now (*run it now*, *later*), a question about the next flow that survives
a restart; the flow's `next_flow` says otherwise (`run`: it starts at once; `off`: none is made).

`Following` hears the runner's events (`flows.run_ended`, `flows.run_started`) and the questions' answers, so the
runner itself does not change; a failure here is logged and never stops the run's end. `view` and `make` serve `clank
flow next`.
"""

import contextlib
import json
import logging
import re
import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clank.components.flows.deliverables import fingerprint
from clank.components.flows.kinds import Flow
from clank.components.flows.runs import order
from clank.kernel.events import Actor, EventType, Subject
from clank.kernel.questions import Option, Question, QuestionDraft, QuestionError
from clank.kernel.settings import DEFAULTS, SettingsError, render

if TYPE_CHECKING:
    from clank.components.flows.service import Flows
    from clank.kernel.core import Kernel
    from clank.kernel.events import Event

log = logging.getLogger(__name__)
TEMPLATE = DEFAULTS / "templates" / "flow.json"
FOLLOWER = Actor(kind="clank", via="flow runner")
NUMBERED = re.compile(r"^(.*)-([0-9]+)$")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")
RUN_NEXT, LATER = "run-next", "later"
FLOW_DATA = {"flow": "The flow, <workspace>/<name>.", "run": "The run's number."}
EVENT_TYPES = [
    EventType(
        "flows.next_made",
        "A flow's last gate was approved: the next flow was made from its INTEGRATE's brief, or why none was (design "
        "0013 §3, decision 0091).",
        {
            **FLOW_DATA,
            "next": "The next flow made, <workspace>/<name>; empty when none was.",
            "brief": "The brief's file it was made from, if any.",
            "why": "Why none was made.",
        },
    ),
    EventType(
        "flows.next_brief",
        "A next flow's first run began: its brief was copied into its first box's file, or that file was kept as you "
        "left it (decision 0091).",
        {
            **FLOW_DATA,
            "follows": "The flow it follows.",
            "brief": "The brief's file.",
            "into": "Its first box's file.",
            "copied": "Whether the brief was copied (else the file was kept, or the brief is gone).",
        },
    ),
]


class NextError(Exception):
    """A next flow that cannot be made, shown or run as asked, and why."""


def last_gate(flow: Flow) -> str | None:
    """The flow's last gate: its last box in the order they run, when it is a GATE."""
    names = order(flow)
    last = next((box for box in flow.boxes if box.id == names[-1]), None) if names else None
    return last.id if last is not None and last.type == "gate" else None


def brief_of(flow: Flow, gate: str) -> tuple[str, str] | None:
    """The last INTEGRATE before `gate` and the brief it writes: its file named `NEXT.md`, else the last of its two or
    more files (the first is its summary); None when there is none."""
    names = order(flow)
    by_id = {box.id: box for box in flow.boxes}
    before = names[: names.index(gate)] if gate in names else []
    integrate = next((by_id[name] for name in reversed(before) if by_id[name].type == "integrate"), None)
    if integrate is None:
        return None
    named = [path for path in integrate.writes if path.rsplit("/", 1)[-1].lower() == "next.md"]
    if named:
        return integrate.id, named[-1]
    return (integrate.id, integrate.writes[-1]) if len(integrate.writes) >= 2 else None


def next_name(flow: str, taken: set[str]) -> str:
    """The next flow's id: `<workspace>/<base>-<n>`, `<base>` this flow's name less a trailing `-<digits>`, `<n>` the
    first number after its own (or from 2) that no flow takes."""
    workspace, name = flow.split("/", 1)
    numbered = NUMBERED.match(name)
    base, number = (numbered.group(1), int(numbered.group(2)) + 1) if numbered else (name, 2)
    while f"{workspace}/{base}-{number}" in taken:
        number += 1
    return f"{workspace}/{base}-{number}"


def title_of(text: str, title: str) -> str:
    """The next flow's title: its brief's first Markdown heading, else "<this flow's title>, next"."""
    for line in text.replace("\r\n", "\n").split("\n"):
        found = HEADING.match(line.strip())
        if found is not None and found.group(1).strip():
            return found.group(1).strip()
    return f"{title}, next"


def next_values(
    template: Mapping[str, Any], flow: str, made: Flow, *, run: int, by: str, brief: str, replaces: str, title: str
) -> dict[str, Any]:
    """The next flow's values: Clank's template with its title, this flow's workspace and model, its first box saying
    where its brief comes from, and `follows`."""
    values: dict[str, Any] = json.loads(json.dumps(dict(template)))
    values.pop("schema", None)  # the file's, not a value
    values["title"] = title
    values["workspace"] = flow.split("/", 1)[0]
    if made.defaults.model:
        values.setdefault("defaults", {})["model"] = made.defaults.model
    first = values["boxes"][0]
    into = first["writes"][0] if first.get("writes") else ""
    came = f"Your brief starts as {brief}, which {by} wrote at the end of {made.title or flow} (run {run})"
    copied = f": Clank copies it into {into} when this flow first runs, unless you changed {into} since" if into else ""
    first["holds"] = f"{came}{copied}. {first.get('holds', '')}".strip()
    values["follows"] = {"flow": flow, "run": run, "by": by, "brief": brief, "replaces": replaces}
    return values


class Following:
    """The next flows, made and started as the runner's runs end and begin."""

    def __init__(self, kernel: "Kernel", flows: "Flows") -> None:
        self.kernel = kernel
        self.flows = flows
        kernel.events.subscribe(self._heard)
        kernel.questions.on_resolved(self._answered)

    def view(self, flow: str) -> dict[str, Any]:
        """A flow's next flow, for `clank flow next`: its id, title, brief and runs; else why there is none."""
        made = self._flow(flow)
        said: dict[str, Any] = {"flow": flow, "title": made.title, "next": None, "why": "", "waiting": ""}
        found = self._existing(made.next)
        if found is not None:
            follows = found.follows
            runs = len([run for run in self.flows.runner.runs.all() if run.flow == made.next])
            said["next"] = {
                "id": made.next, "title": found.title, "brief": follows.brief if follows else "",
                "by": follows.by if follows else "", "run": follows.run if follows else None, "runs": runs,
            }  # fmt: skip
            said["waiting"] = self._asked(made.next)
            return said
        said["why"] = self._why_none(flow, made)
        return said

    def make(self, flow: str, *, actor: Actor, run: bool = False) -> dict[str, Any]:
        """Make the flow's next flow when it has none, from its latest run's INTEGRATE (`NextError` saying why it
        cannot); with `run`, start it too, answering the question that asks."""
        made = self._flow(flow)
        if self._existing(made.next) is None:
            latest = self.flows.runner.runs.latest(flow)
            if latest is None:
                raise NextError(f"{flow} has not run yet: its INTEGRATE has written no brief")
            self._make(flow, latest.number, actor, asking=not run, forced=True)
            made = self._flow(flow)
        elif not run:
            raise NextError(f"{flow}'s next flow is {made.next} already: `clank flow next {flow} --run` runs it")
        if run:  # its question, if one waits, is withdrawn as its run starts
            self.flows.runner.start(made.next, actor=actor)
        return self.view(flow)

    # Heard.

    def _heard(self, event: "Event") -> None:
        data = event.data or {}
        try:
            if event.type == "flows.run_ended" and data.get("outcome") == "done":
                self._ended(str(data["flow"]), int(data["run"]))
            elif event.type == "flows.run_started":
                self._started(str(data["flow"]), int(data["run"]), event.actor)
        except Exception:  # a next flow never stops a run's end or start
            log.exception("the next flow of %s, run %s, could not be made or begun", data.get("flow"), data.get("run"))

    def _answered(self, question: Question) -> None:
        if question.about is None or question.about.kind != "flow" or question.status != "answered":
            return
        if {option.id for option in question.options} != {RUN_NEXT, LATER} or question.answer is None:
            return
        if question.answer.option == RUN_NEXT:
            try:
                self.flows.runner.start(question.about.id, actor=question.answer.by)
            except Exception:
                log.exception("the next flow %s could not be started", question.about.id)

    def _ended(self, flow: str, number: int) -> None:
        """A run ended done: its next flow made when its last box was a gate it approved."""
        made = self._flow(flow, quiet=True)
        if made is None or made.next_flow == "off":
            return
        gate = last_gate(made)
        run = self.flows.runner.runs.load(flow, number)
        if gate is None or run.box(gate).state != "done":
            return
        existing = self._existing(made.next)
        if existing is not None and existing.follows is not None and existing.follows.run == number:
            return  # made already for this run (run again from a box, and approved again)
        name = self._make(flow, number, FOLLOWER, asking=made.next_flow == "ask", forced=False)
        if name and made.next_flow == "run":
            self.flows.runner.start(name, actor=FOLLOWER)

    def _make(self, flow: str, number: int, actor: Actor, *, asking: bool, forced: bool) -> str:
        """Make the next flow from run `number`'s INTEGRATE, link it, say so, and ask about it when `asking`: its id;
        "" when none can be made (`NextError` when `forced`)."""
        made = self._flow(flow)
        gate = last_gate(made)
        found = brief_of(made, gate) if gate is not None else None
        if found is None:
            why = "its last box is no gate" if gate is None else f"no INTEGRATE before {gate} writes a brief (NEXT.md)"
            self._said(flow, number, "", "", why, actor)
            return raise_or_return(forced, f"{flow} makes no next flow: {why}")
        by, brief = found
        folder = Path(self.kernel.parts["workspaces"].folder_of(flow.split("/", 1)[0]))
        source = folder.joinpath(*brief.split("/"))
        if not source.is_file():
            why = f"{by} wrote no {brief}"
            self._said(flow, number, "", brief, why, actor)
            return raise_or_return(forced, f"{flow} makes no next flow: {why}")
        text = source.read_bytes().decode("utf-8-sig", errors="replace")
        template: dict[str, Any] = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        taken = {loaded.id for loaded in self.kernel.settings.records(Flow.KIND)}
        name = next_name(flow, taken)
        first = template["boxes"][0].get("writes") or [""]
        replaces = fingerprint(folder, first[0]).sha256 if first[0] else ""
        values = next_values(
            template, flow, made, run=number, by=by, brief=brief, replaces=replaces,
            title=title_of(text, made.title or flow.split("/", 1)[1]),
        )  # fmt: skip
        self.kernel.settings.write(Flow.KIND, name, values, base=None, actor=actor)
        self._link(flow, name, actor)
        title = str(values["title"])
        self._said(flow, number, name, brief, "", actor, title=title)
        if asking:
            self._ask(made, flow, name, title, by, brief, str(first[0]))
        return name

    def _link(self, flow: str, name: str, actor: Actor) -> None:
        """This flow's `next`, written through the settings; tried once more when its file changed meanwhile."""
        for attempt in range(2):
            loaded = self.kernel.settings.get(Flow.KIND, flow)
            values: dict[str, Any] = json.loads(render(loaded.record))
            values.pop("schema", None)  # the file's, not a value
            values["next"] = name
            try:
                self.kernel.settings.write(Flow.KIND, flow, values, base=loaded.revision, actor=actor)
                return
            except SettingsError:
                if attempt:
                    raise

    def _ask(self, made: Flow, flow: str, name: str, title: str, by: str, brief: str, into: str) -> None:
        copy = f"Clank copies it into {into} when it first runs, unless you changed {into} since; " if into else ""
        detail = (
            f"{made.title or flow} is done, and its next flow is made: {title} ({name}). Its brief is {brief}, which "
            f"{by} wrote; {copy}you edit it there, then say it is done. Later: `clank flow run {name}` starts it."
        )
        self.kernel.questions.ask(
            QuestionDraft(
                type="choice",
                title=f"{made.title or flow} is done: run the next flow, {title}, now?",
                detail=detail,
                options=[
                    Option(id=RUN_NEXT, label="Run it now", effect="Its first run starts, at its brief.", key="y"),
                    Option(id=LATER, label="Later", effect=f"It waits for `clank flow run {name}`.", key="n"),
                ],
                about=Subject(kind="flow", id=name),
            ),
            asked_by=FOLLOWER,
        )

    def _started(self, flow: str, number: int, actor: Actor) -> None:
        """A flow's run began: a question still asking to run it is withdrawn; its first run copies its brief in."""
        waiting = self._asked(flow)
        if waiting:
            with contextlib.suppress(QuestionError):  # answered meanwhile
                self.kernel.questions.withdraw(waiting, reason="it was started", by=actor)
        made = self._flow(flow, quiet=True)
        if number != 1 or made is None or made.follows is None:
            return
        first = made.boxes[0]
        into = first.writes[0] if first.type == "you" and first.writes else ""
        brief = made.follows.brief
        if not into or into == brief:
            return
        folder = Path(self.kernel.parts["workspaces"].folder_of(flow.split("/", 1)[0]))
        source, target = folder.joinpath(*brief.split("/")), folder.joinpath(*into.split("/"))
        follows = made.follows.flow
        if not source.is_file():
            said, copied = f"{brief} is no longer in the folder: {into} is kept as it is", False
        elif fingerprint(folder, into).sha256 != made.follows.replaces:
            said, copied = f"you changed {into} since {flow} was made: it is kept as you left it", False
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            said, copied = f"{into} now holds {brief}, the brief {made.follows.by} of {follows} wrote", True
        self._record(
            "flows.next_brief", flow, number, f"{made.title or flow}: {said}", FOLLOWER,
            follows=follows, brief=brief, into=into, copied=copied,
        )  # fmt: skip

    # Small helpers.

    def _flow(self, flow: str, *, quiet: bool = False) -> Any:
        try:
            record = self.kernel.settings.get(Flow.KIND, flow).record
        except SettingsError as error:
            if quiet:
                return None
            raise NextError(f"there is no flow {flow}: `clank flow list` lists them") from error
        assert isinstance(record, Flow)
        return record

    def _existing(self, name: str) -> Flow | None:
        if not name:
            return None
        found: Flow | None = self._flow(name, quiet=True)
        return found

    def _asked(self, name: str) -> str:
        """The question still asking whether to run the next flow `name`, if one waits."""
        for question in self.kernel.questions.waiting():
            about = question.about
            ours = {option.id for option in question.options} == {RUN_NEXT, LATER}
            if about is not None and about.kind == "flow" and about.id == name and ours:
                return question.id
        return ""

    def _why_none(self, flow: str, made: Flow) -> str:
        if made.next:
            return f"its next flow, {made.next}, is gone: `clank flow next {flow} --make` makes another"
        if made.next_flow == "off":
            return f"its next_flow is off: `clank flow next {flow} --make` makes one all the same"
        gate = last_gate(made)
        if gate is None:
            return "its last box is no gate: a next flow is made once a last gate is approved"
        found = brief_of(made, gate)
        if found is None:
            return f"no INTEGRATE before {gate} writes a brief (NEXT.md)"
        latest = self.flows.runner.runs.latest(flow)
        if latest is not None and latest.status == "done" and latest.box(gate).state == "done":
            return f"none was made: `clank flow next {flow} --make` makes it from {found[1]}, which {found[0]} wrote"
        return f"its last gate, {gate}, has not been approved in a run yet"

    def _said(self, flow: str, number: int, name: str, brief: str, why: str, actor: Actor, title: str = "") -> None:
        summary = f"{flow}'s next flow is made: {title} ({name}), from {brief}" if name else f"{flow}: {why}"
        self._record("flows.next_made", flow, number, summary, actor, next=name, brief=brief, why=why)

    def _record(self, event_type: str, flow: str, number: int, summary: str, actor: Actor, **data: Any) -> None:
        self.kernel.events.record(
            event_type, summary=summary, actor=actor, subject=Subject(kind="flow", id=flow),
            data={"flow": flow, "run": number, **data},
        )  # fmt: skip


def raise_or_return(forced: bool, said: str) -> str:
    """When the owner asked for it (`clank flow next --make`), a next flow that cannot be made is refused, saying why;
    on a run's end it is only said, and none is made ("")."""
    if forced:
        raise NextError(said)
    return ""
