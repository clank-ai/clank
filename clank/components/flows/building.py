"""A flow built with the model (design 0013 §15; decisions 0097-0099): the owner talks the work through with the model
in a planning session, the model drafts the flow with `flow_draft`, and Clank checks the draft and writes the flow.

**What Clank writes** (`built_values`): the draft's title, defaults, boxes and lines, with Clank's own settings over
whatever the draft says (`OWN`): the workspace; auto-accept on, with no cap (a built flow accepts every task its
DECOMPOSE proposes: the proposals' part reads its `built` mark); no wait after any box; the next flow asked; no
`follows` or `next`; the `built` mark (the planning session, when, the brief); and auto mode on a box that changes files
and names no mode (`rules.on_its_own`: a TASK, whose mode would be the workspace's, review by default), so nothing waits
for the owner on the way. A draft naming no model gets the template's (decision 0095). What Clank set over the draft is
said, for the model.

**A built flow's own rules** (`built_problems`, the owner's answers, decision 0098), held on the model's draft only,
each with its place in the file: its first box is a YOU whose first file is the brief, `BRIEF.md`, already in the folder
and changed since the planning began (an old brief is not the one written with the model; its fingerprint then is kept,
`before`, so the runner tells them apart too), each other file it writes in the folder as well; its last box, in the
order the boxes run, is a GATE, the final review, and no other box is one; no other box is a YOU; no box waits when
done; and no box runs in review, which would make each change it asks to make wait for the owner. The rules of every
flow (§3) are the kind's own, checked before these.

**A planning's name** (`free_name`), when none is given: `flow`, else `flow-2`, `flow-3`, the first that no flow of the
workspace has.

**A planning** (`Planning`, kept by `Plannings` as `state/flows/<workspace>/<name>/building.json`, beside the flow's
runs, with the first message its session is sent as `first-message.md`) is the owner's talk with the model that builds
one flow: where it opens (here, or in VS Code), its state (`waiting` for its OpenCode window, `opening` its session on
that window, `talking`, `built` once a draft was written, `failed`, `set aside` by a newer planning in the workspace,
`ran` once its flow ran), the window's port, its session, its drafts and the last one's problems and warnings, and the
question that told the owner the flow was built. `Building.begin` opens one (one open in a workspace at a time, a newer
one setting the older aside; a name an existing flow has refused), and `first_message` is what its session is sent:
`prompts/build.md` filled in with the flow, the workspace, the brief's file, each preset of the main slot with its
window, the template's model and Clank's template as the example, its gates but the last taken out (`example`). Each
step is a `flows.building` event.

**Where it opens** (`Building.open`, decision 0099): its session is started on the workspace's OpenCode window and shown
there, as `/implement` hands a plan over. Here, the planning gives the command that starts the window in the asking
terminal (`agents/prepare`); in VS Code, the window running there takes it, else the planning waits for the one VS
Code's extension prepares; beside the console (`where="attach"`, decision 0100), no window running is taken, and the
planning waits for the one `clank flow attach` prepares (`attach`, which shows a planning already talking on its new
window, the bridge's `show`, and starts no second session). The agents tell the planning each window prepared
(`Agents.on_prepared`), and its session is started on a thread of its own (the window starts after `prepare` answers):
the bridge waits up to `WINDOW_SECONDS` for the window's server, sends the first message to the planner, and shows the
session, then again. Where is the client's choice (`clank.kernel.where`: over SSH, always here).

**Watched** (decision 0101): a folder's Flow view shows its workspace's newest planning while it waits, opens or
talks, or failed with no run started since (`watched`): its steps (`steps`: started, what it waits for, the session's
tool calls, the owner's answer it waits for, `BRIEF.md` written, each draft kept in `history`) and its latest draft
(`draft.json`), drawn as far as it reads (`readable`).

**A draft** (`Building.draft`, `flow_draft`) goes to the planning open in the workspace the MCP server names. It is
refused with none open, once its flow ran, or when the flow changed since Clank wrote it (the owner's edit); else it is
checked (the kind's rules, its presets and workspace, a built flow's own rules) and, keeping them, written as the flow's
file, the owner asked to look, then run it (the next flow's answers, so every client shows it), the question for an
earlier draft withdrawn. The check's warnings come back either way. A run of the flow ends the planning (`ran`).
"""

import contextlib
import json
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, Field, ValidationError

from clank.components.flows import preparing
from clank.components.flows.deliverables import fingerprint
from clank.components.flows.kinds import Box, Flow, FlowDefaults, FlowLimits, Limits, Line
from clank.components.flows.rules import on_its_own
from clank.components.flows.runs import order, read_whole, write_whole
from clank.kernel.clock import to_text
from clank.kernel.events import Actor, EventType, Subject
from clank.kernel.questions import Option, QuestionDraft, QuestionError
from clank.kernel.settings import DEFAULTS

if TYPE_CHECKING:
    from clank.components.flows.service import Flows
    from clank.kernel.core import Kernel
    from clank.kernel.events import Event
    from clank.kernel.settings import Loaded

NAME = "flow"  # a planning's name when none is given, numbered on from 2 when taken
OWN: dict[str, Any] = {  # Clank's own settings of a built flow, over the draft's (decision 0098)
    "auto_accept": True,
    "wait_after_every_box": False,
    "next_flow": "ask",
}
NOT_DRAFTED = ("schema", "follows", "next", "auto_accept_cap")  # the file's, Clank's links, a cap a built flow has not
TEMPLATE = DEFAULTS / "templates" / "flow.json"
BRIEF = "BRIEF.md"  # the brief a planning writes with the owner, as Clank's template names it
SLOT = "main"  # every box runs on the main slot (design 0013 §7)
RUNNER = Actor(kind="clank", via="flow building")  # who asks the owner to look at a built flow
VIEW = "clank console --page monitor --view flow"  # the Flow view, for a terminal that keeps F10 (over SSH)
WINDOW_SECONDS = 60.0  # how long a planning's session waits for its OpenCode window's server to answer
NOT_IN_A_NAME = set('/\\:*?"<>|')
Place = tuple[str | int, ...]
Where = Literal["here", "vscode", "attach"]
Status = Literal["waiting", "opening", "talking", "built", "failed", "set aside", "ran"]
OPEN: tuple[Status, ...] = ("waiting", "opening", "talking", "built")  # a planning that takes drafts
WATCHED: tuple[Status, ...] = ("waiting", "opening", "talking", "failed")  # a planning the Flow view shows
EVENT_TYPES = [
    EventType(
        "flows.building",
        "A flow built with the model (design 0013 §15): a planning opened, set aside by a newer one, its OpenCode "
        "window waited for, its session started there (or why not), a draft of the flow written or refused, or its "
        "flow run.",
        {
            "flow": "The flow it builds, <workspace>/<name>.",
            "workspace": "The workspace.",
            "action": "opened, set aside, waits, opening, talking, attached, again (a planning that failed, "
            "tried again by `clank flow attach`), failed, written, refused or ran.",
            "where": "here (the terminal that asked), vscode (Clank's VS Code window) or attach (beside the console, "
            "the terminal that runs `clank flow attach`).",
            "port": "Its OpenCode window's port, once known.",
            "session": "Its session, once started.",
            "why": "Why it failed, was set aside or refused.",
        },
    )
]


class BuildError(Exception):
    """A planning that cannot be opened, or a draft that cannot be taken, and why."""


class Draft(BaseModel):
    """A draft of the flow as the model sent it (design 0013 §15, decision 0101): its number, when, and whether Clank
    wrote it or refused it, with each problem ("field: what is wrong")."""

    number: int
    at: datetime
    state: Literal["refused", "accepted"]
    problems: list[str] = Field(default_factory=list)


class Planning(BaseModel):
    """The owner's talk with the model that builds a flow (design 0013 §15)."""

    flow: str = Field(description="The flow it builds, <workspace>/<name>.")
    workspace: str
    name: str
    where: Where = Field(
        description="here: OpenCode in the terminal that asked; vscode: in Clank's VS Code window; attach: in the "
        "terminal that runs `clank flow attach` (beside the console)."
    )
    status: Status = "waiting"
    why: str = Field("", description="Why it failed or was set aside.")
    port: int | None = Field(None, description="Its OpenCode window's port, once known.")
    session: str = Field("", description="Its session, once started.")
    started: datetime
    by: Actor
    drafts: int = Field(0, description="Drafts the model sent.")
    written: int = Field(0, description="Drafts Clank wrote as the flow.")
    built: datetime | None = Field(None, description="When the flow was last written from a draft.")
    question: str = Field("", description="The question that told the owner the flow was built.")
    revision: str = Field("", description="The flow's revision as Clank last wrote it from a draft.")
    before: dict[str, str] = Field(
        default_factory=dict,
        description="The brief's fingerprint when the planning began; empty when it was not there.",
    )
    problems: list[str] = Field(default_factory=list, description="The last draft refused: each problem.")
    warnings: list[str] = Field(default_factory=list, description="The last draft: the check's warnings.")
    history: list[Draft] = Field(default_factory=list, description="Each draft the model sent, in order.")


class Plannings:
    """The plannings, each a JSON file beside its flow's runs (`state/flows/<workspace>/<name>/building.json`)."""

    def __init__(self, folder: Path) -> None:
        self.folder = folder

    def path(self, flow: str) -> Path:
        """A planning's file."""
        workspace, name = flow.split("/", 1)
        return self.folder / workspace / name / "building.json"

    def save(self, planning: Planning) -> None:
        """Write a planning's file whole, at once."""
        text = json.dumps(planning.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"
        write_whole(self.path(planning.flow), text)

    def keep_message(self, planning: Planning, text: str) -> Path:
        """Its session's first message, beside it, for the owner to read; its path."""
        path = self.path(planning.flow).with_name("first-message.md")
        write_whole(path, text)
        return path

    def keep_draft(self, planning: Planning, values: Mapping[str, Any]) -> Path:
        """The latest draft's values, as Clank would write them, beside the planning (never in the folder); its path."""
        path = self.path(planning.flow).with_name("draft.json")
        write_whole(path, json.dumps(dict(values), indent=2, ensure_ascii=False, default=str) + "\n")
        return path

    def forget_draft(self, planning: Planning) -> None:
        """No draft kept beside a planning just begun: one there is an earlier planning's of the same name."""
        self.path(planning.flow).with_name("draft.json").unlink(missing_ok=True)

    def draft(self, flow: str) -> dict[str, Any] | None:
        """The latest draft's values, if one was kept and reads."""
        try:
            found = json.loads(read_whole(self.path(flow).with_name("draft.json")))
        except (OSError, ValueError):
            return None
        return found if isinstance(found, dict) else None

    def load(self, flow: str) -> Planning | None:
        """A flow's planning, if it has one that reads."""
        try:
            return Planning.model_validate_json(read_whole(self.path(flow)))
        except (OSError, ValueError):
            return None

    def all(self) -> list[Planning]:
        """Every planning that reads, oldest first."""
        found = []
        if self.folder.is_dir():
            for path in self.folder.glob("*/*/building.json"):
                try:
                    found.append(Planning.model_validate_json(read_whole(path)))
                except (OSError, ValueError):
                    continue
        return sorted(found, key=lambda each: (each.started, each.flow))


def built_values(
    draft: Mapping[str, Any], *, workspace: str, model: str, built: Mapping[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """The values Clank writes for the model's draft, and what Clank set over the draft, in words."""
    values: dict[str, Any] = {key: value for key, value in draft.items() if key not in NOT_DRAFTED}
    said = [f"{key} (yours: {json_text(draft[key])})" for key in ("follows", "next") if draft.get(key)]
    if "auto_accept_cap" in draft:
        said.append("no auto_accept_cap: a built flow accepts every task its DECOMPOSE proposes, so none stops its run")
    wanted = {"workspace": workspace, **OWN}
    for key, value in wanted.items():
        if key in draft and draft[key] != value:
            said.append(f"{key} to {json_text(value)} (yours: {json_text(draft[key])})")
        values[key] = value
    values["built"] = dict(built)
    boxes = values.get("boxes")
    for index, box in enumerate(boxes if isinstance(boxes, list) else []):
        if isinstance(box, dict) and box.get("mode") != "review" and on_its_own(box):
            said.append(f'boxes.{index}.mode to "auto" (a built flow runs on its own: its changes are not asked)')
    defaults = values.get("defaults")
    if defaults is None:
        values["defaults"] = defaults = {}
    if isinstance(defaults, dict) and model and not str(defaults.get("model") or "").strip():
        values["defaults"] = {**defaults, "model": model}
        said.append(f"defaults.model to {model!r}, Clank's template's (the draft named none)")
    return values, said


def json_text(value: Any) -> str:
    """A value as JSON writes it: true, "ask"."""
    return json.dumps(value, ensure_ascii=False)


def built_problems(flow: Flow, folder: Path, before: Mapping[str, str] | None = None) -> list[tuple[Place, str]]:
    """Each place where a built flow breaks its own rules (decision 0098), in the order of the file; `before`, each
    file's fingerprint when the planning began ("" for one not there), so a brief left from before is not taken."""
    found: list[tuple[Place, str]] = []
    first = flow.boxes[0]
    if first.type == "you" and not first.writes:
        found.append((("boxes", 0, "writes"), f"the first box, the user's YOU, writes the brief: {BRIEF}"))
    elif first.type == "you" and first.writes[0] != BRIEF:
        found.append(
            (
                ("boxes", 0, "writes", 0),
                f"the brief is {BRIEF}, written with the user in this planning: name it first in the YOU box's "
                f"writes, not {first.writes[0]}",
            )
        )
    for index, path in enumerate(first.writes if first.type == "you" else []):
        now = fingerprint(folder, path)
        if now.size == 0:
            found.append(
                (
                    ("boxes", 0, "writes", index),
                    f"{path} is not in the folder yet: write it with the user first (the brief: the goal, the "
                    "limits, what done means), then draft the flow again",
                )
            )
        elif index == 0 and before is not None and path in before and now.sha256 == before[path]:
            found.append(
                (
                    ("boxes", 0, "writes", 0),
                    f"{path} is as it was when the planning began: it is not the brief written with the user; "
                    "write it with them now, then draft the flow again",
                )
            )
    names = order(flow)
    last = names[-1] if names else ""
    for index, box in enumerate(flow.boxes):
        if index and box.type == "you":
            found.append(
                (
                    ("boxes", index, "type"),
                    f"a built flow has one YOU, its first box, the brief; {box.id} would stop the run for the user "
                    "midway: make it a TASK, or leave it out",
                )
            )
        if box.type == "gate" and box.id != last:
            found.append(
                (
                    ("boxes", index, "type"),
                    f"a built flow waits for the user only at its end: its one GATE is its last box, the final "
                    f"review; take {box.id} out (a VERIFY checks the work on its own)",
                )
            )
        if box.mode == "review":
            found.append(
                (
                    ("boxes", index, "mode"),
                    f"review would make each change {box.id} asks to make wait for the user, and a built flow runs "
                    "on its own: leave its mode out (Clank runs it in auto), or plan for Markdown only",
                )
            )
        if box.when_done == "wait":
            found.append(
                (
                    ("boxes", index, "when_done"),
                    f"a built flow waits only at its end: leave {box.id}'s when_done out (go on)",
                )
            )
    by_id = {box.id: index for index, box in enumerate(flow.boxes)}
    if last and flow.boxes[by_id[last]].type != "gate":
        found.append(
            (
                ("boxes", by_id[last], "type"),
                f"a built flow ends with a GATE, the user's final review: add one after {last}, which shows what "
                "the flow delivered (an INTEGRATE's summary)",
            )
        )
    return sorted(found, key=lambda each: tuple((0, part) if isinstance(part, int) else (1, part) for part in each[0]))


def free_name(workspace: str, taken: set[str]) -> str:
    """The name a planning takes when none is given: `flow`, else the first of `flow-2`, `flow-3`, ... that no flow of
    the workspace has (`taken`: every flow's id)."""
    if f"{workspace}/{NAME}" not in taken:
        return NAME
    number = 2
    while f"{workspace}/{NAME}-{number}" in taken:
        number += 1
    return f"{NAME}-{number}"


def example(template: Mapping[str, Any]) -> dict[str, Any]:
    """Clank's template as a built flow's example: its gates but the last taken out, each line into one led on to the
    box after it; no `schema` (the file's)."""
    values: dict[str, Any] = json.loads(json.dumps(dict(template)))
    values.pop("schema", None)
    boxes = values.get("boxes") or []
    last = boxes[-1]["id"] if boxes else ""
    for gate in [box["id"] for box in boxes if box.get("type") == "gate" and box["id"] != last]:
        after = next((line["to"] for line in values["lines"] if line["from"] == gate), "")
        values["lines"] = [
            {**line, "to": after} if line["to"] == gate else line for line in values["lines"] if line["from"] != gate
        ]
        values["boxes"] = [box for box in values["boxes"] if box["id"] != gate]
    return values


def steps(
    planning: Planning, folder: Path, session_flow: Mapping[str, Any] | None, attach: str
) -> list[dict[str, Any]]:
    """A planning's steps as the Flow view says them (decision 0101): started; what it waits for; reading the folder,
    with the session's tool calls so far; `BRIEF.md` written or changed since it began, with its time; each draft, its
    number, time, state and problems; then what it waits for now (the owner's answer) or why it failed."""
    found: list[dict[str, Any]] = [
        {"kind": "started", "at": to_text(planning.started), "said": f"started by {planning.by.describe()}"}
    ]
    if planning.status == "waiting":
        said = {
            "attach": f"waits for its OpenCode window: {attach}",
            "vscode": "waits for OpenCode in Clank's VS Code window",
        }.get(planning.where, "waits for OpenCode in its terminal")
        found.append({"kind": "waits", "said": said})
    elif planning.status == "opening":
        found.append({"kind": "opening", "said": f"its session starts on the OpenCode window at port {planning.port}"})
    head = dict((session_flow or {}).get("head") or {})
    nodes = list((session_flow or {}).get("nodes") or [])
    calls = int(head.get("calls") or 0)
    if planning.session and (calls or head.get("status") == "busy"):
        found.append(
            {"kind": "reading", "said": f"reading the folder: {calls} tool call{'s' if calls != 1 else ''} so far"}
        )
    brief = fingerprint(folder, BRIEF)
    if brief.size and brief.sha256 != planning.before.get(BRIEF, ""):
        written = to_text(datetime.fromtimestamp(brief.modified / 1e9, UTC)) if brief.modified else ""
        said = f"{BRIEF} {'changed' if planning.before.get(BRIEF) else 'written'}"
        found.append({"kind": "brief", "at": written, "said": said})
    found += [
        {"kind": "draft", "number": each.number, "at": to_text(each.at), "state": each.state,
         "problems": list(each.problems)}
        for each in planning.history
    ]  # fmt: skip
    if planning.status == "failed":
        found.append({"kind": "failed", "said": f"failed: {planning.why}"})
    else:
        if planning.why:
            found.append({"kind": "note", "said": planning.why})
        if planning.session and waits_for_the_owner(head, nodes):
            found.append({"kind": "waiting", "said": "waiting for your answer"})
    return found


def waits_for_the_owner(head: Mapping[str, Any], nodes: list[dict[str, Any]]) -> bool:
    """Whether a session waits for the owner: a question of its waits, or it is idle after a message of the model's
    that called no tool."""
    if any(node.get("kind") == "call" and node.get("tool") == "question" and node.get("status") in ("running",
           "pending") for node in nodes):  # fmt: skip
        return True
    said = [node for node in nodes if node.get("kind") == "step"]
    return head.get("status") == "idle" and bool(said) and said[-1].get("finish") != "tool-calls"


def readable(values: Mapping[str, Any]) -> Flow | None:
    """A draft as the Flow view draws it (decision 0101): the flow when it reads whole; else what of it reads, each
    box that reads (its id not seen before) and each line that reads between two of them; None with no box."""
    try:
        return Flow.model_validate(dict(values))
    except ValidationError:
        pass
    given_boxes, given_lines, given_title = values.get("boxes"), values.get("lines"), values.get("title")
    boxes: list[Box] = []
    for each in given_boxes if isinstance(given_boxes, list) else []:
        try:
            box = Box.model_validate(each)
        except (ValidationError, TypeError, ValueError):
            continue
        if box.id not in {kept.id for kept in boxes}:
            boxes.append(box)
    if not boxes:
        return None
    ids = {box.id for box in boxes}
    lines: list[Line] = []
    for each in given_lines if isinstance(given_lines, list) else []:
        try:
            line = Line.model_validate(each)
        except (ValidationError, TypeError, ValueError):
            continue
        if line.from_ in ids and line.to in ids:
            lines.append(line)
    try:
        defaults = FlowDefaults.model_validate(values.get("defaults") or {})
    except (ValidationError, TypeError, ValueError):
        defaults = FlowDefaults()
    title = given_title if isinstance(given_title, str) else ""
    return Flow.model_construct(title=title, defaults=defaults, boxes=boxes, lines=lines, auto_accept=True)


def session_title(planning: Planning) -> str:
    """The planning session's title, as OpenCode lists it: "<name> · building the flow"."""
    return f"{planning.name} · building the flow"


def compact(values: Mapping[str, Any]) -> str:
    """A flow as JSON, each box and each line on a line of its own, for a model to read and copy."""
    parts = []
    for key, value in values.items():
        if key in ("boxes", "lines") and isinstance(value, list):
            items = ",\n".join(f"    {json.dumps(each, ensure_ascii=False)}" for each in value)
            parts.append(f"  {json.dumps(key)}: [\n{items}\n  ]")
        else:
            parts.append(f"  {json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}")
    return "{\n" + ",\n".join(parts) + "\n}"


def prompt() -> str:
    """The planning session's instructions, `prompts/build.md`, its placeholders not filled in."""
    return resources.files("clank.components.flows").joinpath("prompts", "build.md").read_text(encoding="utf-8")


class Building:
    """The plannings: flows built with the model (design 0013 §15)."""

    def __init__(self, kernel: "Kernel", flows: "Flows") -> None:
        self.kernel = kernel
        self.flows = flows
        self.plannings = Plannings(kernel.home.state / "flows")
        self._lock = threading.RLock()
        kernel.events.subscribe(self._heard)
        kernel.parts["agents"].on_prepared(self._prepared)  # a window's port, for a planning that waits for one

    def draft(self, workspace: str, given: Any, *, actor: Actor) -> dict[str, Any]:
        """The model's draft of the flow the planning open in the workspace builds (`flow_draft`, design 0013 §15):
        checked as a saved flow and against a built flow's own rules, then written as the flow's file with Clank's
        settings, and the owner told; what was done, said for the model. `BuildError`, in words for the model, when no
        planning is open there, its flow ran or changed since, or the draft breaks a rule (each problem with its field,
        and the check's warnings)."""
        planning = self.open_in(workspace)
        if planning is None:
            raise BuildError(
                f"no flow is being built in {workspace}: the user opens a planning (n in Clank's Flow view, or "
                "`clank flow new`), and its session drafts the flow"
            )
        flow = planning.flow
        if self.flows.runner.runs.latest(flow) is not None:
            said = f"{flow} has run: the user changes it in Clank's Flow view (e on a box)"
            self._change(flow, status="ran", drafts=planning.drafts + 1,
                         history=[*planning.history, self._noted(planning, [said])])  # fmt: skip
            raise BuildError(said)
        if not isinstance(given, dict):
            said = "send the whole flow as an object: {title, defaults, boxes, lines}"
            self._change(flow, drafts=planning.drafts + 1, history=[*planning.history, self._noted(planning, [said])])
            raise BuildError(said)
        existing = self._existing(flow)
        if existing is not None and (not planning.written or existing.revision != planning.revision):
            whose = f"the user changed {flow} since you drafted it" if planning.written else f"a flow {flow} exists"
            said = f"{whose}: tell the user, who changes it in Clank's Flow view (e on a box)"
            self._change(flow, drafts=planning.drafts + 1, history=[*planning.history, self._noted(planning, [said])])
            raise BuildError(said)
        template: dict[str, Any] = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        model = str((template.get("defaults") or {}).get("model") or "")
        boxes = given.get("boxes") if isinstance(given.get("boxes"), list) else []
        writes = (boxes[0].get("writes") if boxes and isinstance(boxes[0], dict) else None) or ["BRIEF.md"]
        brief = str(writes[0]) if isinstance(writes, list) and writes else "BRIEF.md"
        mark = {"session": planning.session, "at": self.kernel.clock.now(), "brief": brief,
                "before": planning.before.get(brief, "")}  # fmt: skip
        values, set_over = built_values(given, workspace=workspace, model=model, built=mark)
        self.plannings.keep_draft(planning, values)
        problems, warnings, made = self._checked(flow, values, planning.before)
        if problems:
            refused = self._change(
                flow, drafts=planning.drafts + 1, problems=problems, warnings=warnings,
                history=[*planning.history, self._noted(planning, problems)],
            )  # fmt: skip
            said = "Not written. Fix each, then call flow_draft again:\n" + "\n".join(f"- {each}" for each in problems)
            if warnings:
                said += "\n\nWarnings of Clank's check (fix those you can):\n" + "\n".join(f"- {w}" for w in warnings)
            if refused is not None:
                self._said(refused, "refused", f"a draft of {flow} was refused: {len(problems)} problem(s)", actor)
            raise BuildError(said)
        assert made is not None
        from clank.kernel.settings import SettingsError

        try:
            written = self.kernel.settings.write(
                Flow.KIND, flow, values, base=existing.revision if existing is not None else None, actor=actor
            )
        except SettingsError as error:
            raise BuildError(f"Not written: {error}") from error
        question = self._tell(planning, made, warnings, actor)
        done = self._change(
            flow, status="built", drafts=planning.drafts + 1, written=planning.written + 1, problems=[],
            warnings=warnings, built=self.kernel.clock.now(), question=question, revision=written.revision,
            history=[*planning.history, self._noted(planning, [])],
        )  # fmt: skip
        if done is not None:
            self._said(done, "written", f"{made.title or flow} ({flow}) was written from the model's draft", actor)
        return {"flow": flow, "revision": written.revision, "warnings": warnings, "said": _written(flow, made,
                set_over, warnings)}  # fmt: skip

    def _noted(self, planning: Planning, problems: list[str]) -> Draft:
        """A draft's place in the planning's history: refused with its problems, or accepted with none."""
        state: Literal["refused", "accepted"] = "refused" if problems else "accepted"
        number = len(planning.history) + 1
        return Draft(number=number, at=self.kernel.clock.now(), state=state, problems=list(problems))

    def _checked(
        self, flow: str, values: dict[str, Any], before: Mapping[str, str]
    ) -> tuple[list[str], list[str], Flow | None]:
        """A draft's problems (§3's rules, its presets and workspace, a built flow's own rules) and the check's
        warnings, each "field: what is wrong"; and the flow, when it reads."""
        try:
            made = Flow.model_validate(values)
        except ValidationError as error:
            said = [f"{'.'.join(map(str, each['loc']))}: {_message(each)}" for each in error.errors()]
            return said, [], None
        workspace = flow.split("/", 1)[0]
        folder = Path(self.kernel.parts["workspaces"].folder_of(workspace))
        found = self.flows.problems_of(flow, made) + built_problems(made, folder, before)
        problems = [f"{'.'.join(map(str, place))}: {message}" if place else message for place, message in found]
        shown = preparing.preview(self.flows.runner.runs, None, flow, made, folder, self.kernel.parts["runtime"])
        warnings = [message for _, message in preparing.warnings(shown, made, folder)]
        return problems, warnings, made

    def _tell(self, planning: Planning, made: Flow, warnings: list[str], actor: Actor) -> str:
        """Ask the owner to look, then run (the next flow's answers, so every client shows it): the question's id; the
        one asked for an earlier draft withdrawn."""
        from clank.components.flows.following import LATER, RUN_NEXT

        if planning.question:
            with contextlib.suppress(QuestionError):  # answered or withdrawn meanwhile
                self.kernel.questions.withdraw(planning.question, reason="the model drafted the flow again", by=actor)
        title = made.title or planning.name
        lines = [
            f"The model built {title} ({planning.flow}) with you: {len(made.boxes)} boxes, each on "
            f"{made.defaults.model or 'what the main slot runs'} unless it names its own. Look at it in Clank's Flow "
            f"view (F10, or `{VIEW}`): its boxes, their models and the check's warnings; change any box first "
            f"(e). Then run it: r there, Run it now here, or `clank flow run {planning.flow}`. It stops only at its "
            "last box, your review.",
        ]
        if warnings:
            lines += ["", "The check warns:", *(f"- {each}" for each in warnings)]
        asked = self.kernel.questions.ask(
            QuestionDraft(
                type="choice",
                title=f"{title}: flow built: look, then r to run",
                detail="\n".join(lines),
                options=[
                    Option(id=RUN_NEXT, label="Run it now", effect="Its first run starts, at its brief.", key="y"),
                    Option(id=LATER, label="Later", effect="It waits for r in the Flow view.", key="n"),
                ],
                about=Subject(kind="flow", id=planning.flow),
            ),
            asked_by=RUNNER,
        )
        return asked.id

    def _existing(self, flow: str) -> "Loaded | None":
        from clank.kernel.settings import SettingsError

        try:
            return self.kernel.settings.get(Flow.KIND, flow)
        except SettingsError:
            return None

    def _heard(self, event: "Event") -> None:
        """A flow's run began: its planning, if open, takes no more drafts."""
        if event.type != "flows.run_started":
            return
        flow = str((event.data or {}).get("flow") or "")
        planning = self.plannings.load(flow) if "/" in flow else None
        if planning is None or planning.status not in OPEN:
            return
        ran = self._change(flow, status="ran")
        if ran is not None:
            self._said(ran, "ran", f"{flow} ran: its planning takes no more drafts", event.actor)

    def begin(self, workspace: str, name: str, where: Where, *, actor: Actor, aside: bool = False) -> Planning:
        """Open a planning in the workspace, its first message kept beside it: named `name`, else the first name no
        flow and no planning there has, so no planning is ever overwritten. A planning open there (waiting, opening,
        talking, or failed with no run since: the one the Flow view shows) is set aside only when `aside` says so; a
        built one, not run yet, always. `BuildError` for a workspace Clank does not have, a name an existing flow has,
        a planning open there and no `aside`, or the open planning's own name."""
        workspaces = {loaded.id for loaded in self.kernel.settings.records("workspace")}
        if workspace not in workspaces:
            raise BuildError(f"Clank has no workspace {workspace}: `clank workspace open` in its folder makes it")
        taken = {loaded.id for loaded in self.kernel.settings.records(Flow.KIND)}
        planned = {each.flow for each in self.plannings.all() if each.workspace == workspace}
        name = name.strip() or free_name(workspace, taken | planned)
        if not _plain(name):
            raise BuildError(f"{name!r} cannot name a flow: a plain name, without '/', '..' or a leading '.'")
        flow = f"{workspace}/{name}"
        if flow in taken:
            raise BuildError(f"a flow {flow} exists: name another, or change it in the Flow view (e on a box)")
        with self._lock:
            shown = self.watched(workspace)
            if shown is not None and not aside:
                raise BuildError(
                    f"a planning is open in {workspace}: {shown.flow} ({shown.status}); to start another, set it "
                    "aside (n in the Flow view asks first; `clank flow new --set-aside`), or talk with it: `clank flow "
                    "attach`"
                )
            older = shown or self.open_in(workspace)
            if older is not None and older.flow == flow:
                raise BuildError(f"{flow} is the planning open: name another")
            folder = Path(self.kernel.parts["workspaces"].folder_of(workspace))
            planning = Planning(
                flow=flow, workspace=workspace, name=name, where=where, started=self.kernel.clock.now(), by=actor,
                before={BRIEF: fingerprint(folder, BRIEF).sha256},
            )  # fmt: skip
            self.plannings.save(planning)
            self.plannings.forget_draft(planning)  # a new planning starts with no draft
            self.plannings.keep_message(planning, self.first_message(planning))
        if older is not None and older.flow != flow:
            put = self._change(older.flow, status="set aside", why=f"{actor.describe()} opened a newer one, {flow}")
            if put is not None:
                self._said(put, "set aside", f"the planning of {older.flow} is set aside: {flow} is opened", actor)
        where_said = {"vscode": "in Clank's VS Code window", "attach": "beside the console (clank flow attach)"}.get(
            where, "in this terminal"
        )
        self._said(planning, "opened", f"{actor.describe()} opened a planning of {flow}, {where_said}", actor)
        return planning

    def open(self, workspace: str, name: str, where: Where, *, actor: Actor, aside: bool = False) -> dict[str, Any]:
        """Open a planning (`begin`) and its session on the workspace's OpenCode window (decision 0099): here, the
        command that starts that window in the asking terminal, written by `agents/prepare`, whose port the planning is
        told; in VS Code, the window running there, else none yet (`waits`: VS Code's extension prepares one). The
        session itself is started on a thread of its own once the window answers (`_start`). `BuildError` when the
        planning cannot be opened, the window's command cannot be made, or the workspace's container runs an older
        sandbox image (without the bridge's planner start and `flow_draft`), naming the fix."""
        from clank.components.agents.service import AgentError, SessionError
        from clank.components.workspaces.service import WorkspaceUnavailable

        self._current_image(workspace)
        planning = self.begin(workspace, name, where, actor=actor, aside=aside)
        said = {"flow": planning.flow, "name": planning.name, "where": where, "title": session_title(planning),
                "folder": str(self.kernel.parts["workspaces"].folder_of(workspace)),
                "first_message": str(self.plannings.path(planning.flow).with_name("first-message.md"))}  # fmt: skip
        if where == "here":
            try:  # the agents tell `_prepared` its port, which starts the session once the window answers
                prepared = self.kernel.parts["agents"].prepare(workspace)
            except (AgentError, SessionError, WorkspaceUnavailable) as error:
                self._failed(planning.flow, f"OpenCode's window cannot be started: {error}")
                raise BuildError(f"OpenCode's window cannot be started in {workspace}: {error}") from error
            if prepared["port"] is None:
                self._failed(planning.flow, "its window's session cannot be reached: " + "; ".join(prepared["notes"]))
            keys = ("argv", "program", "port", "model", "notes")
            return {**said, "window": "started", **{key: prepared[key] for key in keys}}
        if where == "attach":  # beside the console: the window `clank flow attach` prepares (decision 0100)
            command = f"cd {said['folder']} then clank flow attach"
            waits = self.plannings.load(planning.flow)
            if waits is not None:
                text = f"the planning of {planning.flow} waits for its OpenCode window: {command}"
                self._said(waits, "waits", text, RUNNER)
            return {**said, "window": "waits", "port": None, "attach": command}
        running = self._window(workspace)
        if running is not None:
            self._start(planning.flow, running)
            return {**said, "window": "running", "port": running}
        waits = self.plannings.load(planning.flow)
        if waits is not None:
            text = (
                f"the planning of {planning.flow} waits for an OpenCode window in {workspace} (Clank's VS Code window)"
            )
            self._said(waits, "waits", text, RUNNER)
        return {**said, "window": "waits", "port": None}

    def attach(self, workspace: str, *, actor: Actor) -> dict[str, Any]:
        """`clank flow attach` (design 0013 §15, decision 0100): OpenCode's window for the planning open in the
        workspace, prepared for the asking terminal (`agents/prepare`: the one-window rule closes another window there
        first, said in its notes). A planning waiting for its window starts its session there (`_prepared`); one
        talking already is shown there (`_show`), no second session started; one that failed, with no run in the
        workspace since (the Flow view still shows it), is tried again there (`_again`). `BuildError` with none open,
        a container from an older sandbox image, or a session still starting on the window prepared before (it is not
        closed for another: once it answers the session talks there, and attach shows it; once it gives up, the
        planning fails, and attach tries it again)."""
        from clank.components.agents.service import AgentError, SessionError
        from clank.components.workspaces.service import WorkspaceUnavailable

        planning = self.open_in(workspace)
        shown = self.watched(workspace) if planning is None else None
        failed = shown if shown is not None and shown.status == "failed" else None
        if planning is None and failed is None:
            raise BuildError(
                f"no planning is open in {workspace}: n on the console's Flow view (or f on This folder), or `clank "
                "flow new`, opens one"
            )
        if planning is not None and planning.status == "opening":
            raise BuildError(
                f"the planning of {planning.flow} is starting its session on the OpenCode window at port "
                f"{planning.port}: leave that window open and wait for it (up to {WINDOW_SECONDS:.0f} seconds); then "
                "`clank flow attach` shows it here, or tries it again if that window is gone"
            )
        self._current_image(workspace)
        if failed is not None:
            planning = self._again(failed, actor)
        if planning is None:
            raise BuildError(f"the planning of {failed.flow if failed else workspace} is gone: n opens another")
        try:
            prepared = self.kernel.parts["agents"].prepare(workspace)
        except (AgentError, SessionError, WorkspaceUnavailable) as error:
            raise BuildError(f"OpenCode's window cannot be started in {workspace}: {error}") from error
        port = prepared["port"]
        if port is not None and planning.session and planning.status in ("talking", "built"):
            threading.Thread(
                target=self._show, args=(planning.flow, port, planning.session, actor), name=f"flows: {planning.flow}",
                daemon=True,
            ).start()  # fmt: skip
        keys = ("argv", "program", "port", "model", "notes", "closed", "one_window")
        return {"flow": planning.flow, "name": planning.name, "title": session_title(planning),
                "status": planning.status, **{key: prepared.get(key) for key in keys}}  # fmt: skip

    def _again(self, planning: Planning, actor: Actor) -> Planning | None:
        """A planning that failed, tried again on the window `clank flow attach` prepares: waiting for it again (its
        session starts there), or talking when its session had started (shown there); why it failed cleared."""
        again = self._change(planning.flow, status="talking" if planning.session else "waiting", why="")
        if again is not None:
            text = f"the planning of {planning.flow} is tried again (it failed: {planning.why or 'no reason given'})"
            self._said(again, "again", text, actor)
        return again

    def watched(self, workspace: str) -> Planning | None:
        """The planning a folder's Flow view shows (decision 0101): the workspace's newest, while it waits, opens or
        talks, or failed with no run of a flow there started since; None otherwise (built: the built flow is shown)."""
        found = [each for each in self.plannings.all() if each.workspace == workspace]
        newest = found[-1] if found else None
        if newest is None or newest.status not in WATCHED:
            return None
        if newest.status == "failed" and any(
            run.workspace == workspace and run.created > newest.started for run in self.flows.runner.runs.all()
        ):
            return None
        return newest

    def _show(self, flow: str, port: int, session: str, actor: Actor) -> None:
        """A talking planning's session shown on a window just prepared for it, once that window answers."""
        planning = self.plannings.load(flow)
        if planning is None:
            return
        try:
            shown = self.kernel.parts["agents"].sessions.show_in_window(
                planning.workspace, port, session, actor=actor, wait=WINDOW_SECONDS
            )
        except Exception as error:  # said, never lost on this thread
            self._said(planning, "attached", f"the planning session of {flow} could not be shown: {error}", RUNNER)
            return
        title = session_title(planning)
        pick = "" if shown else f"OpenCode did not show it: pick “{title}” from OpenCode's session list (/sessions)"
        moved = self._change(flow, port=port, why=pick)
        if moved is not None:
            text = f"the planning session of {flow} is shown on the OpenCode window at port {port}" + (
                f": {pick}" if pick else ""
            )
            self._said(moved, "attached", text, RUNNER)

    def _current_image(self, workspace: str) -> None:
        """`BuildError`, naming the fix, when the workspace's container runs an older sandbox image."""
        if self.kernel.parts["workspaces"].runs_current_image(workspace) is False:
            raise BuildError(
                f"{workspace}'s container runs an older sandbox image, without what a planning needs (its bridge, "
                "flow_draft): stop the workspace and open it again (`clank workspace stop`, then `clank workspace open "
                "--yes` in its folder; or Workspaces, F6: x, then o), then open the planning again"
            )

    def view(self, workspace: str, flow: str = "") -> dict[str, Any]:
        """A planning as the clients show it: the flow's (`flow`), else the one open in the workspace, else its newest;
        with its first message's file; None and why when there is none."""
        if flow:
            found = self.plannings.load(flow)
        else:
            found = self.open_in(workspace) or next(
                (each for each in reversed(self.plannings.all()) if each.workspace == workspace), None
            )
        if found is None:
            where = f"{flow}" if flow else workspace
            return {
                "planning": None,
                "why": f"no planning of {where}: n in the Flow view, or `clank flow new`, opens one",
            }
        path = self.plannings.path(found.flow).with_name("first-message.md")
        return {"planning": found.model_dump(mode="json"), "first_message": str(path), "why": ""}

    def _window(self, workspace: str) -> int | None:
        """The port of an OpenCode window running in the workspace (a terminal interface), if any."""
        from clank.components.agents.service import SessionError

        try:
            servers = self.kernel.parts["agents"].sessions.servers(workspace)
        except SessionError:
            return None
        found = [int(server["port"]) for server in servers if server.get("terminal")]
        return found[0] if found else None

    def _prepared(self, workspace: str, port: int) -> None:
        """`agents/prepare` gave a window's command in the workspace: the planning waiting there starts on it."""
        planning = self.open_in(workspace)
        if planning is not None and planning.status == "waiting":
            self._start(planning.flow, port)

    def _start(self, flow: str, port: int) -> None:
        """Start the planning's session on the window on `port`, on a thread of its own, since the window may still be
        starting (here, it starts once `prepare` has answered): the bridge waits for it up to `WINDOW_SECONDS`."""
        with self._lock:
            planning = self.plannings.load(flow)
            if planning is None or planning.status != "waiting":
                return  # started already, or set aside meanwhile
            planning = self._change(flow, status="opening", port=port)
        if planning is None:
            return
        self._said(
            planning, "opening", f"the planning of {flow} starts its session on the window at port {port}", RUNNER
        )
        threading.Thread(target=self._session, args=(flow, port), name=f"flows: planning {flow}", daemon=True).start()

    def _session(self, flow: str, port: int) -> None:
        """The planning's session started on the window, its first message sent to the planner and shown there."""
        from clank.components.agents.service import PLANNER

        planning = self.plannings.load(flow)
        if planning is None:
            return
        kept = self.plannings.path(flow).with_name("first-message.md")
        title = session_title(planning)
        try:
            text = read_whole(kept).decode("utf-8") if kept.is_file() else self.first_message(planning)
            session, shown = self.kernel.parts["agents"].sessions.start_in_window(
                planning.workspace, port, text, title=title, actor=planning.by, agent=PLANNER, wait=WINDOW_SECONDS
            )
        except Exception as error:  # anything that stops the session is said, never lost on this thread
            self._failed(flow, str(error) or type(error).__name__)
            return
        pick = "" if shown else f"OpenCode did not show it: pick “{title}” from OpenCode's session list (/sessions)"
        with self._lock:
            now = self.plannings.load(flow)
            status = "talking" if now is not None and now.status == "opening" else (now.status if now else "talking")
            talking = self._change(flow, status=status, session=session, why=pick)
        if talking is not None:
            said = f"the planning session of {flow} runs on the OpenCode window at port {port}: " + (
                pick or "talk it through there"
            )
            self._said(talking, "talking", said, RUNNER)

    def _failed(self, flow: str, why: str) -> None:
        failed = self._change(flow, status="failed", why=why)
        if failed is not None:
            self._said(failed, "failed", f"the planning of {flow} failed: {why}", RUNNER)

    def planning(self, flow: str) -> Planning | None:
        """A flow's planning, if it has one."""
        return self.plannings.load(flow)

    def open_in(self, workspace: str) -> Planning | None:
        """The planning open in the workspace (it takes drafts), if any: the newest."""
        found = [each for each in self.plannings.all() if each.workspace == workspace and each.status in OPEN]
        return found[-1] if found else None

    def first_message(self, planning: Planning) -> str:
        """What its session is sent: `prompts/build.md` filled in (design 0013 §15)."""
        template: dict[str, Any] = json.loads(TEMPLATE.read_text(encoding="utf-8"))
        model = (
            str((template.get("defaults") or {}).get("model") or "") or "what the main slot runs when the box starts"
        )
        first = (template.get("boxes") or [{}])[0]
        brief = str((first.get("writes") or ["BRIEF.md"])[0])
        filled = prompt()
        for key, value in (
            ("$FLOW", planning.flow), ("$WORKSPACE", planning.workspace), ("$BRIEF", brief),
            ("$PRESETS", "\n".join(self._presets())), ("$MODEL", model),
            ("$EXAMPLE", compact(example(template))),
        ):  # fmt: skip
            filled = filled.replace(key, value)
        return filled

    def _presets(self) -> list[str]:
        """Each preset of the main slot, by its title, with its window, and the one the slot runs now."""
        runtime = self.kernel.parts["runtime"]
        slot = runtime.state.slot(SLOT)
        running = slot.preset if slot.status == "ready" else None
        lines = []
        for loaded in self.kernel.settings.records("preset"):
            if getattr(loaded.record, "slot", SLOT) != SLOT:
                continue
            title = loaded.record.title or loaded.id
            facts = runtime.facts(loaded.id)
            window = ((facts or {}).get("engine") or {}).get("window")
            said = f"{int(window):,} tokens of context" if window else "its window is not known here"
            now = ", loaded now" if loaded.id == running else ""
            lines.append(f"- {title}: {said}{now}")
        return lines or ["- none: Clank has no preset for the main slot yet"]

    def _change(self, flow: str, **changes: Any) -> Planning | None:
        """Change a planning's file, under the lock; the planning as written, None when it is gone."""
        with self._lock:
            planning = self.plannings.load(flow)
            if planning is None:
                return None
            planning = planning.model_copy(update=changes)
            self.plannings.save(planning)
            return planning

    def _said(self, planning: Planning, action: str, summary: str, actor: Actor, **data: Any) -> None:
        self.kernel.events.record(
            "flows.building",
            summary=summary,
            actor=actor,
            subject=Subject(kind="flow", id=planning.flow),
            data={"flow": planning.flow, "workspace": planning.workspace, "action": action, "where": planning.where,
                  "port": planning.port, "session": planning.session, "why": planning.why, **data},
        )  # fmt: skip


def _message(error: Any) -> str:
    """A draft's error, as the settings files word it: a field it does not have, named with the fields of what it is in
    (a box, a line, the defaults, the flow), else pydantic's or the rule's own."""
    if error["type"] != "extra_forbidden":
        return str(error["msg"])
    place = [part for part in error["loc"][:-1] if not isinstance(part, int)]
    what, fields = {
        ("boxes",): ("a box", [name for name in Box.model_fields if name != "proposed"]),
        ("boxes", "limits"): ("a box's limits", list(Limits.model_fields)),
        ("lines",): ("a line", ["from", "to", "when"]),
        ("defaults",): ("the defaults", list(FlowDefaults.model_fields)),
        ("defaults", "limits"): ("the defaults' limits", list(FlowLimits.model_fields)),
    }.get(tuple(place), ("a flow", ["title", "defaults", "boxes", "lines"]))
    return f"is not a field of {what} (its fields: {', '.join(fields)})"


def _written(flow: str, made: Flow, set_over: list[str], warnings: list[str]) -> str:
    """What the model is told once its draft is written."""
    model = made.defaults.model or "what the main slot runs"
    said = f"Written as {flow}: {len(made.boxes)} boxes, on {model} unless a box names its own."
    if set_over:
        said += " Clank set " + "; ".join(set_over) + ": the user's answers."
    if warnings:
        said += "\n\nWarnings of Clank's check (fix those you can, then draft again):\n"
        said += "\n".join(f"- {each}" for each in warnings)
    return said + (
        "\n\nTell the user, in a few lines, what the flow does box by box, and that they can look at it in Clank's "
        f"Flow view (F10, or `{VIEW}` in a terminal that keeps F10 for itself), change any box, and press r to "
        "run it. A draft sent again replaces it until it runs."
    )


def _plain(name: str) -> bool:
    """Whether a flow's name is a plain name of a file: no folder, nothing hidden."""
    return bool(name) and not name.startswith(".") and not set(name) & NOT_IN_A_NAME and ".." not in name
