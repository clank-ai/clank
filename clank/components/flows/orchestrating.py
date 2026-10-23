"""The orchestrator (design 0013 §16, decisions 0123-0124): what a checkpoint is handed, what it may decide, and the
ledger Clank keeps of a run's checkpoints.

A checkpoint is a fresh Plan-mode session that steers a run while its flow's orchestrator is on: after each box a
model ran (`review`), and at each question the run asks (`question`). Its first message (`message`) hands it the
orchestrator's instructions (`prompts/orchestrator.md`), the box's report, the question with its answers, the run so
far, the brief, the budget left and the ledger; it decides once with `flow_decide`, which the runner checks here
(`decided`) and keeps on the run. The ledger is the run's own (`Orchestration`, kept in its file, and as
`orchestrator.md` beside it, `ledger_text`): never written by the model's hand, read whole by every checkpoint, so each
starts fresh yet knows the run, and none needs a long context. Its five answers per decision are Magentic-One's
progress ledger; the stall count rises with each checkpoint that answers "not progressing" or "looping" and returns to
0 at progress; at the flow's stall limit a review may not go on (docs/research/orchestration.md)."""

from datetime import datetime
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from clank.components.flows.kinds import Box, Flow
from clank.kernel.events import Actor

if TYPE_CHECKING:
    from clank.components.flows.runs import Run

ORCHESTRATOR = Actor(kind="clank", via="orchestrator")  # who answers a question the orchestrator decided
Kind = Literal["review", "question"]
REVIEW_CHOICES = ("go on", "change", "back", "pause", "stop")
WATCH_CHOICES = ("go on", "pause")  # after a box, while it only watches (its role `watch`)
LEAVE = "leave"  # at a question: left to the user, who is told why
TOLD = ("pause", LEAVE)  # the choices that must tell the user why
EDITABLE = ("title", "prompt", "sees", "writes", "holds", "accept_when", "accept_command", "model", "tries")
ADDABLE = ("task", "verify")
WHOLE = 40_000  # characters of the brief and of a box's handoff note handed whole
LEDGER_SHOWN = 30  # decisions the ledger shows in full; older ones by their line only
COSTLY = {"back", "retry", "skip"}  # a question's answers that count against the changes left


class DecisionRefused(ValueError):
    """A decision that cannot be kept as sent, and what to fix."""


class Part(BaseModel):
    """A part of the orchestrator's state: no field but its own."""

    model_config = ConfigDict(extra="forbid")


class Change(Part):
    """An edit of a box not yet run, or a box added after one (`after`)."""

    box: str = Field(description="The box edited, or the new box's id.")
    after: str = Field("", description="A new box: the box it comes after; empty: an edit of `box`.")
    type: str = Field("", description="A new box's type: task or verify.")
    title: str | None = None
    prompt: str | None = None
    sees: list[str] | None = None
    writes: list[str] | None = None
    holds: str | None = None
    accept_when: list[str] | None = None
    accept_command: str | None = None
    checks: str | None = None
    model: str | None = None
    tries: int | None = Field(None, ge=1)
    minutes: int | None = Field(None, ge=1)
    tokens: int | None = Field(None, ge=1)


class Decision(Part):
    """One checkpoint's decision, as kept in the ledger."""

    number: int = Field(ge=1, description="The checkpoint's number in the run.")
    kind: Kind
    box: str = Field(description="The box it followed, or the question was about.")
    question: str = Field("", description="The question decided, if any.")
    choice: str = Field(description="go on, change, back or stop; or the question's answer.")
    why: str
    met: list[str] = Field(default_factory=list, description="The brief's lines it judged met.")
    unmet: list[str] = Field(default_factory=list, description="The brief's lines not met yet.")
    looping: bool = False
    progressing: bool = True
    facts: str = Field("", description="What is known now, as this decision rewrote it.")
    plan: str = Field("", description="The plan from here, as this decision rewrote it.")
    note: str = Field("", description="What the next box is told.")
    back_to: str = Field("", description="A review's *back*: the box the work goes back to.")
    changes: list[Change] = Field(default_factory=list)
    tell_user: str = Field("", description="What the user should know now: asked at once, the run not waiting.")
    at: datetime
    applied: str = Field("", description="What Clank did with it.")


class Checkpoint(Part):
    """The checkpoint at work."""

    number: int = Field(ge=1)
    kind: Kind
    box: str
    question: str = ""
    options: list[str] = Field(default_factory=list, description="A question's answers, by id.")
    operation: str = ""
    session: str = ""
    started: datetime
    decision: Decision | None = None


class Orchestration(Part):
    """What the orchestrator did in a run: the ledger, its limits used, the checkpoint at work."""

    checkpoints: int = Field(0, description="Checkpoints started.")
    changes: int = Field(0, description="Changes made: edits, boxes added, send backs, skips and extra tries.")
    stall: int = Field(0, description="Checkpoints in a row that answered not progressing, or looping.")
    extra: dict[str, int] = Field(default_factory=dict, description="Extra tries given, by box.")
    reviewed: dict[str, int] = Field(default_factory=dict, description="Each box's tries when last reviewed.")
    decided: list[str] = Field(default_factory=list, description="Questions decided or left to the owner.")
    working: Checkpoint | None = None
    facts: str = ""
    plan: str = ""
    decisions: list[Decision] = Field(default_factory=list)
    owner: str = Field(
        "", description="Why the run waits for the owner, when the orchestrator could not act or left it."
    )
    told: list[str] = Field(default_factory=list, description="The questions that told the owner its words, by id.")


def instructions() -> str:
    """The orchestrator's standing instructions, as shipped."""
    return resources.files("clank.components.flows").joinpath("prompts", "orchestrator.md").read_text("utf-8")


def failure_class(reason: str) -> str:
    """Why a try failed, in the three classes that decide its remedy: `outside the work` (try it again as it was), `a
    limit` (more of it, when the work was progressing), `its result` (a changed approach)."""
    said = reason.lower()
    if "past its limit" in said:
        return "a limit"
    outside = ("session is gone", "server stopped", "cannot be started", "switch", "preset", "not there",
               "container", "workspace", "timed out", "unavailable")  # fmt: skip
    if any(word in said for word in outside):
        return "outside the work"
    return "its result"


def choices(checkpoint: Checkpoint, role: str = "steer") -> list[str]:
    """What this checkpoint may choose: at a question, its answers or leaving it to the user; after a box, as its role
    allows."""
    if checkpoint.kind == "question":
        return [*checkpoint.options, LEAVE]
    return list(WATCH_CHOICES if role == "watch" else REVIEW_CHOICES)


def decided(
    checkpoint: Checkpoint, flow: Flow, run: "Run", given: dict[str, Any], *, limits: Any, at: datetime
) -> Decision:
    """The decision as it is kept; `DecisionRefused`, saying what to fix, when it cannot be."""
    state = run.orchestration
    choice = str(given.get("choice") or "").strip().lower()
    allowed = choices(checkpoint, limits.role)
    if choice not in allowed:
        raise DecisionRefused(f"choose one of: {', '.join(allowed)} (you sent {given.get('choice')!r})")
    why = str(given.get("why") or "").strip()
    if not why:
        raise DecisionRefused("say why, in a sentence or two: the user reads it")
    tell_user = str(given.get("tell_user") or "").strip()
    if choice in TOLD and not tell_user:
        raise DecisionRefused(f"{choice} hands the run to the user: say in tell_user what they must know, and why")
    try:
        changes = [Change.model_validate(each) for each in given.get("changes") or []]
    except ValidationError as error:
        first = error.errors()[0]
        raise DecisionRefused(f"a change's {'.'.join(str(part) for part in first['loc'])}: {first['msg']}") from error
    if choice == "change" and not changes:
        raise DecisionRefused("a change lists its changes: each a box not run yet and what changes in it")
    if choice != "change" and changes and checkpoint.kind == "question":
        raise DecisionRefused("at a question, answer it; changes are made after a box, with the choice change")
    left = limits.changes - state.changes
    cost = len(changes) + (1 if choice in COSTLY or choice == "back" else 0)
    if cost > left:
        raise DecisionRefused(
            f"{_count(left, 'change')} left of {limits.changes} in this run: choose what costs fewer, or stop"
        )
    if choice == "retry" and checkpoint.kind == "question":
        given_extra = state.extra.get(checkpoint.box, 0)
        if given_extra >= limits.extra_tries and past_cap(flow, run, checkpoint.box):
            raise DecisionRefused(
                f"{checkpoint.box} had its {limits.extra_tries} extra tries: take it as it is, skip it, or stop"
            )
    progressing = _yes(given.get("progressing"), True)
    looping = _yes(given.get("looping"), False)
    if checkpoint.kind == "review" and choice == "go on" and state.stall >= limits.stall:
        remedy = (
            "pause it for the user, saying why in tell_user"
            if limits.role == "watch"
            else "change the plan (back to the box to do again, or change the boxes ahead), pause it for the user, or "
            "stop"
        )
        raise DecisionRefused(f"the run made no progress at {_count(state.stall, 'checkpoint')} in a row: {remedy}")
    back_to = str(given.get("back_to") or "").strip()
    if checkpoint.kind == "review" and choice == "back":
        _ran(flow, run, back_to)
    for change in changes:
        _check_change(flow, run, change)
    if changes:
        changed(flow, changes)  # the flow as it would be: refused here when it breaks a rule
    return Decision(
        number=checkpoint.number, kind=checkpoint.kind, box=checkpoint.box, question=checkpoint.question,
        choice=choice, why=why, met=_lines(given.get("met")), unmet=_lines(given.get("unmet")), looping=looping,
        progressing=progressing, facts=str(given.get("facts") or "").strip(), plan=str(given.get("plan") or "").strip(),
        note=str(given.get("note") or "").strip(), back_to=back_to, changes=changes, tell_user=tell_user, at=at,
    )  # fmt: skip


def changed(flow: Flow, changes: list[Change]) -> Flow:
    """The flow with the changes made; `DecisionRefused` naming the rule a change breaks."""
    data = flow.model_dump(mode="json", by_alias=True, exclude_none=True)
    boxes: list[dict[str, Any]] = data["boxes"]
    lines: list[dict[str, Any]] = data["lines"]
    for change in changes:
        fields = {key: value for key, value in change.model_dump(exclude_none=True).items()
                  if key in (*EDITABLE, "checks")}  # fmt: skip
        limits = {key: getattr(change, key) for key in ("minutes", "tokens") if getattr(change, key) is not None}
        if change.after:
            new = {"id": change.box, "type": change.type, **fields}
            new.setdefault("title", change.box)
            if change.type == "verify":
                new.setdefault("checks", change.after)
            if limits:
                new["limits"] = limits
            index = next(i for i, box in enumerate(boxes) if box["id"] == change.after)
            boxes.insert(index + 1, new)
            for line in lines:
                if line["from"] == change.after and line.get("when") != "fail":
                    line["from"] = change.box
            lines.append({"from": change.after, "to": change.box})
            if change.type == "verify":  # its pass line on to what came after, its fail line back to the box it checks
                for line in lines:
                    if line["from"] == change.box and not line.get("when"):
                        line["when"] = "pass"
                lines.append({"from": change.box, "to": change.checks or change.after, "when": "fail"})
            continue
        box = next(each for each in boxes if each["id"] == change.box)
        box.update(fields)
        if limits:
            box["limits"] = {**(box.get("limits") or {}), **limits}
    try:
        return Flow.model_validate(data)
    except ValidationError as error:
        said = "; ".join(f"{'.'.join(str(part) for part in each['loc'])}: {each['msg']}" for each in error.errors()[:5])
        raise DecisionRefused(f"the flow would break a rule: {said}") from error


def message(
    flow: Flow,
    run: "Run",
    checkpoint: Checkpoint,
    *,
    limits: Any,
    folder: Path,
    report: str,
    question: str,
    elapsed: str,
) -> str:
    """A checkpoint's first message."""
    state = run.orchestration
    left = limits.changes - state.changes
    stalled = state.stall >= limits.stall
    said = [instructions().strip(), "", f"# Checkpoint {checkpoint.number} of the run {run.name} ({run.title})", ""]
    if limits.role == "watch":
        said += ["Your role here: watch. You check that the run is on track: go on, or pause it for the user (with "
                 "tell_user saying why); you change nothing and decide no question.", ""]  # fmt: skip
    if checkpoint.kind == "review":
        said += [f"The box {checkpoint.box} has ended. Its report:", "", report, ""]
    else:
        said += [f"The run asks a question about {checkpoint.box}; you answer it for the user.", "", question, ""]
        if report:
            said += ["What the box did:", "", report, ""]
    said += ["## The run so far", "", run_table(flow, run), "", f"The run has worked {elapsed}.", ""]
    said += ["## The brief", "", _brief(flow, folder), ""]
    said += ["## The ledger", "", ledger_text(run, limit=LEDGER_SHOWN), ""]
    said += [
        "## The budget",
        "",
        f"- {_count(left, 'change')} left of {limits.changes} in this run (each change, send back, skip and extra "
        "try counts one).",
        f"- Extra tries past a box's cap: {limits.extra_tries} per box"
        + (f"; given so far: {', '.join(f'{box} {n}' for box, n in state.extra.items())}" if state.extra else "")
        + ".",
        f"- Stall: stall {state.stall} of {limits.stall}" + (" (stalled: you may not go on)" if stalled else "") + ".",
        f"- This checkpoint: {limits.limits.minutes} minutes, {limits.limits.tokens:,} tokens written.",
        "",
        "## Your decision",
        "",
        f"Call `flow_decide` once, with `choice` one of: {', '.join(choices(checkpoint, limits.role))}; then stop.",
        "If the user should know something now (a surprise, a result against the plan, a failure that keeps coming "
        "back, a risk to their time, machine or money), say it in `tell_user`: it reaches them at once, and the run "
        "does not wait for it."
        + (" `pause` and `leave` need it." if checkpoint.kind == "review" else " `leave` needs it."),
    ]
    if stalled and checkpoint.kind == "review":
        said.append("The run is stalled: change the plan (back to the box to do again, or change the boxes ahead), or "
                    "stop.")  # fmt: skip
    return "\n".join(said) + "\n"


def run_table(flow: Flow, run: "Run") -> str:
    """Each box in the order it runs: its type, title, state, tries and why."""
    from clank.components.flows.runs import order

    rows = ["| Box | Type | Title | State | Tries | Tokens | Why |", "| --- | --- | --- | --- | --- | --- | --- |"]
    found = {box.id: box for box in flow.boxes}
    for name in order(flow):
        box, state = found.get(name), run.box(name)
        if box is None:
            continue
        tokens = sum(each.tokens for each in state.tries)
        cap = box.tries or flow.defaults.tries
        rows.append(
            f"| {name} | {box.type} | {box.title} | {state.state} | {len(state.tries)} of {cap} | {tokens:,} | "
            f"{(state.why or '').replace('|', '/')[:200]} |"
        )
    return "\n".join(rows)


def report(flow: Flow, run: "Run", box: Box, folder: Path, note: str) -> str:
    """What a box did, for a checkpoint: its last try's outcome and why (with its failure's class), its deliverables
    with their sizes, a VERIFY's findings, its accept command's result, and its handoff note."""
    state = run.box(box.id)
    last = state.tries[-1] if state.tries else None
    said = [f"- {box.id}, {box.type}: {box.title}", f"- Its prompt: {_cut(box.prompt or box.holds or '(none)', 600)}"]
    if last is None:
        said.append("- It has not run.")
        return "\n".join(said)
    cap = box.tries or flow.defaults.tries
    said.append(
        f"- Try {last.number} of {cap}: {last.outcome or 'running'}" + (f": {last.reason}" if last.reason else "")
    )
    if last.outcome == "failed" and last.reason:
        said.append(f"- Its failure's class: {failure_class(last.reason)}")
    said.append(f"- Tokens written: {last.tokens:,}")
    for path in box.writes:
        file = folder.joinpath(*path.split("/"))
        size = file.stat().st_size if file.is_file() else 0
        said.append(f"- Deliverable {path}: " + (f"{size:,} bytes" if size else "not written"))
    if last.verdict is not None:
        said.append(f"- Its verdict: {last.verdict.result}")
        said += [f"  {number}. {finding}" for number, finding in enumerate(last.verdict.findings, start=1)]
    if last.command is not None:
        from clank.components.flows import accepting

        verdict = "passed" if last.command.passed else "failed"
        said.append(f"- Its accept command (a machine check) {verdict}: {_cut(accepting.told(last.command), 1500)}")
    if note:
        said += ["- Its handoff note:", "", _cut(note, WHOLE)]
    return "\n".join(said)


def ledger_text(run: "Run", *, limit: int = 0) -> str:
    """The ledger as the owner and each checkpoint read it."""
    state = run.orchestration
    said = ["### Facts", "", state.facts or "(none yet)", "", "### Plan", "", state.plan or "(none yet)", "",
            "### Decisions", ""]  # fmt: skip
    if not state.decisions:
        said.append("(none yet)")
    shown = state.decisions[-limit:] if limit else state.decisions
    if limit and len(state.decisions) > limit:
        said.append(f"({len(state.decisions) - limit} earlier, kept in the run's orchestrator.md)")
    for each in shown:
        where = f"after {each.box}" if each.kind == "review" else f"at {each.box}'s question"
        said.append(f"{each.number}. {where}: {each.choice} ({each.at:%H:%M}). {each.why}")
        marks = [] if each.progressing else ["not progressing"]
        marks += ["looping"] if each.looping else []
        if marks:
            said.append(f"   {', '.join(marks)}")
        if each.unmet:
            said.append(f"   not met yet: {'; '.join(each.unmet)}")
        if each.note:
            said.append(f"   told the next box: {each.note}")
        if each.tell_user:
            said.append(f"   told you: {each.tell_user}")
        for change in each.changes:
            said.append(f"   changed {change.box}" + (f" (added after {change.after})" if change.after else ""))
        if each.applied:
            said.append(f"   {each.applied}")
    if state.owner:
        said += ["", f"Waits for the user: {state.owner}"]
    return "\n".join(said)


def stalled_after(state: Orchestration, decision: Decision) -> int:
    """The stall count once the decision is kept."""
    return state.stall + 1 if (decision.looping or not decision.progressing) else 0


def _check_change(flow: Flow, run: "Run", change: Change) -> None:
    ids = {box.id for box in flow.boxes}
    if change.after:
        if change.type not in ADDABLE:
            raise DecisionRefused(f"a new box is a task or a verify, not {change.type!r}")
        if change.box in ids:
            raise DecisionRefused(f"{change.box} is a box already: name the new box otherwise")
        if change.after not in ids:
            raise DecisionRefused(f"there is no box {change.after} to add {change.box} after")
        if not (change.prompt or "").strip():
            raise DecisionRefused(f"{change.box} needs its prompt: everything its model must know")
        return
    if change.box not in ids:
        raise DecisionRefused(f"there is no box {change.box}: name one of {', '.join(sorted(ids))}")
    state = run.box(change.box)
    if state.tries or state.state not in ("waiting", "stale"):
        raise DecisionRefused(f"{change.box} has run: only a box not run yet changes")


def _ran(flow: Flow, run: "Run", box: str) -> None:
    ids = [each.id for each in flow.boxes]
    if box not in ids:
        raise DecisionRefused(f"back_to names the box to do again: one of {', '.join(ids)}")
    if not run.box(box).tries:
        raise DecisionRefused(f"{box} has not run: send back to a box that ran")


def past_cap(flow: Flow, run: "Run", box: str) -> bool:
    """Whether the box used the tries its cap gives (its own, else the flow's): one more is an extra try."""
    found = next((each for each in flow.boxes if each.id == box), None)
    cap = (found.tries if found is not None and found.tries else None) or flow.defaults.tries
    return len(run.box(box).tries) >= cap


def _brief(flow: Flow, folder: Path) -> str:
    first = flow.boxes[0]
    texts = []
    for path in first.writes:
        file = folder.joinpath(*path.split("/"))
        text = file.read_text(encoding="utf-8", errors="replace") if file.is_file() else ""
        texts.append(f"{path}:\n\n{_cut(text, WHOLE)}" if text else f"{path}: not written")
    return "\n\n".join(texts) or "(the flow's first box writes no brief)"


def _lines(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [str(each).strip() for each in value or [] if str(each).strip()]


def _yes(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "yes", "1")
    return default


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit] + f" … [{len(text):,} characters]"


def _count(number: int, word: str) -> str:
    return f"{number} {word}" + ("" if number == 1 else "s")
