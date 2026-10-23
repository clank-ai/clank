"""The runner (design 0013 §5-§8, §10; decisions 0060-0063, 0065): flows run in the service, one box after another.

**A driver, nudged.** `run`, the flows component's background task, looks at every active run whenever something
changes (an operation ended, a question answered, the owner's control, a flow's file) and does its next thing: start
its box, ask its question, go on to the next box, or end the run. It decides from the run's file alone (`runs.py`), so
after a restart it goes on the same way. One flow runs at a time (§6): a run started while another is active is queued
behind it and begins when it ends.

**A model box is an operation**, `flows.box`, with five steps: *model* (the box's preset, `models.named`, switched into
the main slot by the runtime's own `runtime.switch` when the slot does not run it: only once no operation changes the
slot, no session of the workspace that is no box's works (the owner's own) and the gateway says no request is in flight
on the slot, the run's file and a `flows.model` event saying what it waits for meanwhile; once switched, the owner's
window in the workspace is told (`Agents.model_changed`), even when the owner's stop came while the switch ran (the
stop waits for its end); a switch that fails fails the box, the slot back on the last configuration that worked; a box
that names none runs on what the slot runs), *server* (the run's own OpenCode server, without a
terminal, with the limits of the model the slot runs for the box: reused while it runs with them, else started with
Clank's configuration written for the slot as it runs now, the server it replaces ended once no session works on it,
a `flows.server` event saying so; then the box's MCP servers connected on it alone, `Agents.box_tools`), *session* (a
new session titled after the
flow, the box and the try; its first message, built by `first.py` and kept as `first-message.md` in the try's folder,
sent with the box's agent, the planner in Plan mode and `build` otherwise, and the gateway's model; a box in Review or
Auto has its session's changes answered by that mode), *work* (it follows the session through the watcher's lines,
`Sessions.listen`, to its first `idle`, stopping it at the box's time or token limit or the owner's stop) and *collect*
(its deliverables fingerprinted, counted only when written during the try; then the box's accept command, if any, run
in the container, ended there at once by the owner's stop, a cancel or the service's stop: it passes on exit 0; the
deliverables fingerprinted again and copied into the try's folder as it left them; a PLAN's, TASK's or INTEGRATE's
handoff note, when written during the try, copied beside it as `handoff.md`, a missing one said in its end's event and
never a failure, decision 0086). Every step but *session* is safe to run again. A VERIFY is done only with its
verdict, which its model gives with `flow_verdict` while it works: `verdict` keeps it on the VERIFY's try (the newest
counts) and as `verdict.md` in the try's folder. `diff` compares two tries' copies of a deliverable, and a gate says
how much of each file it shows changed since the try before (counted in a thread before it is asked, never on the
service's event loop).

**What waits for the owner is a question**, asked outside any operation so it survives a restart (design 0002 §2.5): a
YOU box (*done*, *stop*; a built flow's first YOU is done by itself when the brief written with the model is in the
folder, decision 0098), a gate (*approve*, *send back* with a note, *stop*), a failed box (*try again* with a note,
*take it as it is*, *skip the box*, *stop*), and a box whose *when done* waits (*go on*, *stop*). A finished box goes
on by itself otherwise (decision 0065), unless its last try's proposals still wait for the owner (`proposing.py`): the
run is held there, waiting for their question, until each is decided, so the tasks accepted come next. A DECOMPOSE is
done only once it submitted its proposals. The driver calls the proposals' part on a thread, never on the event loop:
a decision holds that part's lock while it writes the flow and tells the questions and events, whose listeners may
wait for the loop (the event stream does).

**A VERIFY's loop** (§3): a VERIFY whose verdict is a fail is *failed*, and the driver takes its fail line from the
run's file: while the box it checks has tries, that box runs its next try handed the findings, and every box after it
up to the VERIFY runs again (the VERIFY handed its own findings, to check how each was answered); when they are used
up, the fail waits at the loop's gate instead: *one more try* past the cap, *take it as it is* (the checked box's files
as the owner left them), *skip the check*, *stop*.

**The owner's controls:** pause (no box starts; the running one goes on), resume, stop (the running box's session is
stopped, its try counts as stopped, and the run ends), and run from here (the box and every box after it run again, as
new tries, told why; the boxes before it taken as they stand, as *send back* takes them). **After a restart**, an
interrupted box is reconciled through the bridge: its session, still working or ended, is followed and collected by a
new `flows.box` that runs only *work* and *collect*; a session gone fails the box. No session is ever started again on
its own. Each step is an event with its actor; none holds a prompt's or a deliverable's text.
"""

import contextlib
import functools
import hashlib
import json
import logging
import math
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

import anyio
import anyio.from_thread
import anyio.lowlevel
import anyio.to_thread
from anyio.streams.memory import MemoryObjectSendStream

from clank.components.agents.service import BUILD, PLANNER, SESSION_MODEL, AgentError, SessionError
from clank.components.flows import accepting, handoff, jobs, orchestrating, preparing
from clank.components.flows.deliverables import fingerprint, written
from clank.components.flows.diffs import LARGEST_SHOWN, compare, text_of
from clank.components.flows.first import came_from
from clank.components.flows.kinds import Box, Flow
from clank.components.flows.models import named
from clank.components.flows.rules import effective_mode
from clank.components.flows.runs import Job, Kept, Run, Runs, ServerLimits, Try, Waiting, WaitingFor, after, order
from clank.components.flows.verdicts import Verdict, VerdictRefused, given
from clank.components.flows.verdicts import text as verdict_text
from clank.components.workspaces.service import WorkspaceUnavailable
from clank.kernel.events import Actor, EventType, Subject
from clank.kernel.operations import (
    UNFINISHED,
    Busy,
    Canceled,
    Operation,
    OperationContext,
    OperationError,
    OperationType,
    Reconciliation,
    StepSpec,
)
from clank.kernel.questions import Option, Question, QuestionDraft, QuestionError

if TYPE_CHECKING:
    from clank.components.agents.service import Agents
    from clank.components.flows.service import Flows
    from clank.components.gateway.service import Gateway
    from clank.components.runtime.service import Runtime
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel

log = logging.getLogger(__name__)
RUNNER = Actor(kind="clank", via="flow runner")
TICK = 0.25  # seconds between looks at a working box's limits, and at what the owner asked
WAIT = 1.0  # seconds between looks at what a switch of the main slot waits for (design 0013 §7)
LOOK = 60.0  # seconds between the runner's own looks at a session's status, should its watcher not say it ended
BOX = "flows.box"
ORCHESTRATE = "flows.orchestrate"  # a checkpoint of the orchestrator (design 0013 §16)
REMINDER = (
    "Clank has not received your decision. A decision counts only when it is given with the tool `flow_decide`: "
    "writing it in your answer does nothing. Call `flow_decide` now, once, with the decision you made (its choice, "
    "why, and the other fields), then stop."
)  # sent once to a checkpoint that ended without deciding
SWITCH = "runtime.switch"
CHANGING = ("runtime.load", "runtime.switch", "runtime.unload", "runtime.restart")  # what changes a slot
ROLE = "agent"  # the gateway's role a box's requests come as: its slot is the main slot
STEPS = (
    StepSpec("model"),
    StepSpec("server"),
    StepSpec("session", repeatable=False),
    StepSpec("work"),
    StepSpec("collect"),
)
CHECKPOINT_STEPS = (
    StepSpec("model"),
    StepSpec("server"),
    StepSpec("session", repeatable=False),
    StepSpec("work"),
    StepSpec("apply"),
)
MODEL_TYPES = ("plan", "verify", "decompose", "task", "integrate")  # the boxes a model runs, which a checkpoint follows
ACTIVE = ("queued", "running")
AT_WORK = ("status", "message", "part", "delta", "todo", "compacted", "error")  # the watch's lines of a session's run
FLOW_DATA = {"flow": "The flow, <workspace>/<name>.", "run": "The run's number."}
EVENT_TYPES = [
    EventType(
        "flows.run_started",
        "A run of a flow began (design 0013 §6); one flow runs at a time.",
        {**FLOW_DATA, "workspace": "The workspace.", "version": "The flow's revision it runs."},
    ),
    EventType(
        "flows.box_started",
        "A box of a running flow started: a model's session, or a question to you (a YOU box, a gate).",
        {
            **FLOW_DATA,
            "box": "The box.",
            "type": "Its type.",
            "try": "Its try.",
            "session": "Its session, if any.",
            "agent": "The agent its first message went to, if any.",
            "mode": "Its session's mode, if any.",
        },
    ),
    EventType(
        "flows.box_ended",
        "A box of a running flow ended: done, failed, stopped or skipped, and why.",
        {
            **FLOW_DATA,
            "box": "The box.",
            "try": "Its try.",
            "outcome": "done, failed, stopped or skipped.",
            "reason": "Why it failed or was stopped, or what you decided.",
        },
    ),
    EventType(
        "flows.verdict",
        "A VERIFY gave its verdict on the deliverable of the box it checks (design 0013 §9): pass, or fail with "
        "findings; the newest of a try counts.",
        {
            **FLOW_DATA,
            "box": "The VERIFY.",
            "try": "Its try.",
            "checks": "The box it checks.",
            "checked": "The try of that box it is on.",
            "result": "pass or fail.",
            "findings": "How many findings it gave.",
            "criteria": "How many lines of the brief and of accept when it checked.",
            "met": "How many of them are met.",
        },
    ),
    EventType(
        "flows.model",
        "A box's preset and the main slot (design 0013 §7, decision 0062): the box waits before its preset is loaded "
        "(an operation changing the slot, your own session at work, a request in flight on it, or the gateway's word "
        "on what is in flight), the slot switches to it, or the switch is done or failed.",
        {
            **FLOW_DATA,
            "box": "The box.",
            "preset": "Its preset's id.",
            "action": "waits, switching, switched or failed.",
            "why": "What it waits for, or why the switch failed.",
            "seconds": "How long the switch took, once switched.",
            "operation": "The switch (runtime.switch).",
        },
    ),
    EventType(
        "flows.server",
        "The flow's own OpenCode server (design 0013 §5): started for a box with the limits of the model it runs on, "
        "started again for a box whose model has other limits (the old one ended, and what its MCP servers ran in the "
        "background with it), or waiting for a session at work on it before it is started again.",
        {
            **FLOW_DATA,
            "box": "The box.",
            "port": "The server's port in the workspace's container (the one waited for, while it waits).",
            "context": "The context it was started with, in tokens.",
            "output": "The output limit it was started with, in tokens.",
            "images": "Whether it was started for a model that reads images.",
            "replaced": "The port of the server it replaced, if any.",
            "action": "started, started again or waits.",
            "why": "What it did, or what it waits for.",
        },
    ),
    EventType(
        "flows.stale",
        "A finished box changed (its settings, or its deliverable in the folder), so the boxes after it that ran are "
        "stale; nothing runs again on its own (design 0013 §8).",
        {**FLOW_DATA, "box": "The box that changed.", "boxes": "The boxes now stale.", "why": "What changed."},
    ),
    EventType(
        "flows.job",
        "A box's job (design 0013 §17): a long computation it started with flow_job, run detached in the workspace's "
        "container; started, or ended (how, in words).",
        {
            **FLOW_DATA,
            "box": "The box that started it.",
            "try": "Its try.",
            "job": "The job's number among the box's jobs in the run.",
            "action": "started or ended.",
            "minutes": "How long it may run.",
            "status": "Its exit status, once ended; empty when its process was gone.",
        },
    ),
    EventType(
        "flows.run_steered",
        "You steered a run: queued it behind another flow's, paused it, resumed it, or ran it again from a box.",
        {**FLOW_DATA, "action": "queue, pause, resume or from.", "box": "The box, for from."},
    ),
    EventType(
        "flows.run_ended",
        "A run of a flow ended: done, or stopped (by you, or because its flow is gone).",
        {**FLOW_DATA, "outcome": "done or stopped.", "reason": "Why it stopped, if it did."},
    ),
    EventType(
        "flows.orchestrator",
        "The orchestrator steered a run (design 0013 §16): a checkpoint started, decided (what, and why), was applied "
        "or set aside, or left a question to you.",
        {
            **FLOW_DATA,
            "checkpoint": "The checkpoint's number in the run.",
            "kind": "review (after a box) or question.",
            "box": "The box it followed, or the question was about.",
            "action": "started, decided, applied, set aside, or yours.",
            "choice": "What it chose, once decided.",
            "why": "Why, in its words, or why it could not act.",
        },
    ),
]


class RunError(Exception):
    """A run that cannot be started or steered as asked, and why."""


class Stopped(Exception):
    """A box whose run was stopped while it was starting."""


@dataclass
class Working:
    """A box's session as the work step follows it: what the watcher's lines said, and what the owner asked."""

    workspace: str
    session: str
    port: int | None
    seen: bool = False  # it was seen at work: busy, or a message, a part or an error of its answer
    sent: bool = False  # its first message was sent
    idle: bool = False
    gone: bool = False
    stop: str = ""
    stopped_by: Actor | None = None
    steps: dict[str, int] = field(default_factory=dict)  # each finished step's tokens written, by its part
    wake: anyio.Event = field(default_factory=anyio.Event)

    def tokens(self) -> int:
        """The tokens its model wrote so far, thinking included."""
        return sum(self.steps.values())


class Runner:
    """The runs of every flow, driven in the service."""

    def __init__(self, kernel: "Kernel", flows: "Flows") -> None:
        from clank.components.flows.proposing import Proposing  # here: it builds on this module

        self.kernel = kernel
        self.flows = flows
        self.runs = Runs(kernel.home)
        self.proposing: Proposing = Proposing(self)
        self._lock = threading.RLock()
        self._send: MemoryObjectSendStream[None] | None = None
        self._token: Any = None
        self._loop: int | None = None
        self._working: dict[tuple[str, str], Working] = {}
        self._found: dict[str, str] = {}  # what reconciling an interrupted box found: working, ended or gone
        self._stopping: dict[str, Actor] = {}  # runs stopped while their box works, by name: who stopped them
        kernel.questions.on_resolved(self._resolved)
        kernel.events.subscribe(self._event)
        self._agents.sessions.listen(self._heard)

    @property
    def _agents(self) -> "Agents":
        agents: Agents = self.kernel.parts["agents"]
        return agents

    @property
    def _workspaces(self) -> "Workspaces":
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        return workspaces

    @property
    def _runtime(self) -> "Runtime":
        runtime: Runtime = self.kernel.parts["runtime"]
        return runtime

    @property
    def _gateway(self) -> "Gateway":
        gateway: Gateway = self.kernel.parts["gateway"]
        return gateway

    def operation_types(self) -> list[OperationType]:
        """`flows.box`: a model box's try, its five steps; `flows.orchestrate`: a checkpoint of the orchestrator."""
        return [
            OperationType(
                BOX, "A flow's box", STEPS, self._box, reconcile=self._reconcile, cancelable=True, owner="flows"
            ),
            OperationType(
                ORCHESTRATE,
                "A flow's orchestrator",
                CHECKPOINT_STEPS,
                self._orchestrate,
                reconcile=self._reconcile_checkpoint,
                cancelable=True,
                owner="flows",
            ),
        ]

    # The owner's controls.

    def start(self, flow: str, *, actor: Actor) -> Run:
        """A new run of the flow, at its first box; queued behind another flow's run when one is active."""
        record = self._record(flow)
        if record is None:
            raise RunError(f"there is no flow {flow}: `clank flow list` lists them")
        made, revision = record
        with self._lock:
            active = [run for run in self.runs.all() if run.status in ACTIVE]
            same = next((run for run in active if run.flow == flow), None)
            if same is not None:
                raise RunError(f"{flow} already runs (run {same.number}): pause or stop it, or run it again from a box")
            ahead = next((run for run in active if run.status == "running"), None) or (active[0] if active else None)
            last = self.runs.latest(flow)  # its server, reused while it still runs without a terminal (§5)
            run = Run(
                flow=flow,
                number=self.runs.next_number(flow),
                title=made.title or flow.split("/", 1)[1],
                workspace=flow.split("/", 1)[0],
                version=revision,
                status="queued" if ahead is not None else "running",
                behind=ahead.name if ahead is not None else "",
                at=order(made)[0],
                server=last.server if last is not None else None,
                server_limits=last.server_limits if last is not None else None,
                started_by=actor,
                created=self.kernel.clock.now(),
            )
            self.runs.save(run)
        if ahead is not None:
            self._record_event(
                "flows.run_steered",
                run,
                f"{actor.describe()} started {run.title}: it waits behind {ahead.title} ({ahead.name})",
                actor,
                action="queue",
                box="",
            )
        else:
            self._began(run, actor)
        self.nudge()
        return run

    def pause(self, flow: str, *, actor: Actor) -> Run:
        """Pause the flow's run: no box starts; the running one goes on."""
        run = self._active(flow)
        if run.paused:
            return run
        run = self._change(run, lambda each: setattr(each, "paused", True))
        self._record_event("flows.run_steered", run, f"{actor.describe()} paused {run.title}", actor, action="pause")
        return run

    def resume(self, flow: str, *, actor: Actor) -> Run:
        """Let a paused run go on."""
        run = self._active(flow)
        if not run.paused:
            return run
        run = self._change(run, lambda each: setattr(each, "paused", False))
        self._record_event("flows.run_steered", run, f"{actor.describe()} resumed {run.title}", actor, action="resume")
        self.nudge()
        return run

    def stop(self, flow: str, *, actor: Actor) -> Run:
        """Stop the flow's run: its running box's session is stopped (a stopped try), and the run ends."""
        run = self._active(flow)
        if run.operation:  # the box's operation stops its session, at once or as soon as it has one
            with self._lock:
                self._stopping[run.name] = actor
                last = run.box(run.at).tries[-1] if run.box(run.at).tries else None
                working = self._working.get((run.workspace, last.session)) if last is not None else None
                if working is not None:
                    working.stop, working.stopped_by = f"stopped by {actor.describe()}", actor
            if working is not None:
                self._call(working.wake.set)
        self._end(run, "stopped", actor, f"stopped by {actor.describe()}")
        self.nudge()
        return self.runs.load(run.flow, run.number)

    def run_from(self, flow: str, box: str, *, actor: Actor) -> Run:
        """Run the flow's latest run again from `box`: it and every box after it run again, as new tries."""
        record = self._record(flow)
        if record is None:
            raise RunError(f"there is no flow {flow}: `clank flow list` lists them")
        made = record[0]
        if box not in order(made):
            raise RunError(f"{flow} has no box {box}: its boxes are {', '.join(order(made))}")
        latest = self.runs.latest(flow)
        if latest is None:
            raise RunError(f"{flow} has not run yet: start it first")
        if latest.operation:
            raise RunError(f"a box of {flow} works now ({latest.at}): stop the run first, or wait for the box")
        if latest.waiting is not None:
            self._withdraw(latest.waiting.question, f"{actor.describe()} ran {flow} again from {box}", actor)
        now = self._standing(latest, made, box)
        with self._lock:
            active = [each for each in self.runs.all() if each.status in ACTIVE and each.flow != flow]
            ahead = next((each for each in active if each.status == "running"), None)
            run = self.runs.load(flow, latest.number)
            told = (
                "the user ran the flow again from this box",
                f"the user ran the flow again from {box}, a box before this one",
            )
            _again(run, made, box, told, now)
            run.at, run.waiting, run.paused, run.ended = box, None, False, None
            if run.status not in ACTIVE:
                run.status = "queued" if ahead is not None else "running"
                run.behind = ahead.name if ahead is not None else ""
            self.runs.save(run)
        self._record_event(
            "flows.run_steered",
            run,
            f"{actor.describe()} ran {run.title} again from {box}",
            actor,
            action="from",
            box=box,
        )
        self.nudge()
        return run

    def view(self, flow: str) -> dict[str, Any]:
        """The flow's runs, newest first, each with its boxes' states."""
        found = [run for run in self.runs.all() if run.flow == flow]
        return {"flow": flow, "runs": [run.model_dump(mode="json") for run in reversed(found)]}

    def diff(
        self, flow: str, box: str, *, path: str = "", a: int | None = None, b: int | None = None, number: int = 0
    ) -> dict[str, Any]:
        """Two tries of a box compared (design 0013 §8): the copies of a deliverable they kept, by default the box's
        last two tries that kept one, of the file it kept last, in the flow's latest run (or run `number`); `RunError`,
        saying why, when they cannot be."""
        try:
            run = self.runs.load(flow, number) if number else self.runs.latest(flow)
        except (OSError, ValueError) as error:
            raise RunError(f"{flow} has no run {number}") from error
        if run is None:
            raise RunError(f"{flow} has not run yet: start it first")
        state = run.box(box)
        if not path:  # the file it kept a copy of last, else the one it wrote last
            written = [kept for each in reversed(state.tries) for kept in each.deliverables if kept.sha256]
            path = next((kept.path for kept in written if kept.copied), written[0].path if written else "")
        if a is None or b is None:
            kept = [each.number for each in state.tries if any(k.path == path and k.copied for k in each.deliverables)]
            if len(kept) < 2:
                what = f"{path} in fewer than two tries" if path else "no copies of a file twice"
                raise RunError(f"{box} kept {what}: nothing to compare")
            a, b = (kept[-2], kept[-1]) if a is None and b is None else (a or kept[-2], b or kept[-1])
        record = self._record(flow)
        largest = record[0].defaults.copied_up_to if record is not None else 0
        before, after_ = (self._copy(run, box, path, each, largest) for each in (a, b))
        compared = compare(path, before, after_, a, b)
        return {
            "flow": flow, "run": run.number, "box": box, "path": path, "a": a, "b": b, "changed": compared.changed,
            "added": compared.added, "removed": compared.removed, "diff": compared.diff,
            "said": f"{path} of {box}: {compared.said}",
            "copies": [str(self._copy_path(run, box, path, each)) for each in (a, b)],
        }  # fmt: skip

    def _copy_path(self, run: Run, box: str, path: str, number: int) -> Path:
        return self.runs.try_folder(run, box, number).joinpath("deliverables", *path.split("/"))

    def _copy(self, run: Run, box: str, path: str, number: int, largest: int) -> str:
        """A try's copy of a deliverable, as text; `RunError` when it has none."""
        state = run.box(box)
        found = next((each for each in state.tries if each.number == number), None)
        if found is None:
            numbers = ", ".join(str(each.number) for each in state.tries) or "none yet"
            raise RunError(f"{box} has no try {number}: its tries are {numbers}")
        kept = next((each for each in found.deliverables if each.path == path), None)
        if kept is None or not kept.sha256:
            raise RunError(f"try {number} of {box} wrote no {path}")
        if not kept.copied:
            raise RunError(
                f"try {number} of {box} kept {path} by its fingerprint only ({kept.size:,} bytes, more than the "
                f"{largest:,} a run copies): there is no copy to compare"
            )
        place = self._copy_path(run, box, path, number)
        try:
            text = text_of(place.read_bytes())
        except OSError as error:
            raise RunError(f"the copy of {path} from try {number} of {box} cannot be read: {error}") from error
        if text is None:
            raise RunError(f"{path} is not text: compare its copies with your own tools ({place.parent})")
        return text

    def _since(self, run: Run, flow: Flow, box: Box, path: str) -> str:
        """How much of a file a gate shows changed since the try before, of the box before it that wrote it: "" when
        it was written once, or its copies are too large to compare in passing (design 0013 §10, board D3)."""
        writer = came_from(flow, box, path)
        if not writer:
            return ""
        tries = [
            each.number
            for each in run.box(writer).tries
            if any(kept.path == path and kept.copied and kept.size <= LARGEST_SHOWN for kept in each.deliverables)
        ]
        if len(tries) < 2:
            return ""
        try:
            before, after_ = (self._copy(run, writer, path, each, 0) for each in tries[-2:])
        except RunError:
            return ""
        return compare(path, before, after_, tries[-2], tries[-1]).said

    # What a box's model gives its flow.

    def verdict(
        self, workspace: str, result: str, findings: list[str], criteria: list[Any], *, actor: Actor
    ) -> dict[str, Any]:
        """A VERIFY's verdict (design 0013 §9), given to the VERIFY box at work in the workspace while its try runs:
        kept on its try (the newest counts) and as `verdict.md` in the try's folder; what was kept, said for the model.
        `RunError`, saying why, when no VERIFY works there or the verdict cannot be kept as sent."""
        with self._lock:
            run, _, box = self._at_work(workspace, "a verdict is a VERIFY's, while it works")
            if box.type != "verify":
                raise RunError(f"{box.id} works now, and it is {_tag(box)}: only a VERIFY gives a verdict")
            state = run.box(box.id)
            last = state.tries[-1] if state.tries else None
            if last is None or last.sent is None or last.outcome is not None:
                raise RunError(f"{box.id}'s try has not begun, or has ended: no verdict is kept for it")
            checked = run.box(box.checks).tries
            try:
                kept = given(
                    result,
                    findings,
                    criteria,
                    checked=checked[-1].number if checked else None,
                    at=self.kernel.clock.now(),
                    by=actor,
                )
            except VerdictRefused as error:
                raise RunError(str(error)) from error
            run = self._change(run, functools.partial(_set_verdict, box=box.id, verdict=kept))
            number = last.number
            folder = self.runs.try_folder(run, box.id, number)
            folder.mkdir(parents=True, exist_ok=True)
            words = verdict_text(kept, box=box.id, title=box.title, number=number, checks=box.checks)
            (folder / "verdict.md").write_bytes(words.encode("utf-8"))
        on = f"{box.checks}'s try {kept.checked}" if kept.checked else box.checks
        many = f", with {_count(len(kept.findings), 'finding')}" if kept.findings else ""
        self._record_event(
            "flows.verdict", run, f"{box.title} gave its verdict on {on}: {kept.result}{many}", actor, box=box.id,
            checks=box.checks, checked=kept.checked, result=kept.result, findings=len(kept.findings),
            criteria=len(kept.criteria), met=sum(1 for each in kept.criteria if each.met), **{"try": number},
        )  # fmt: skip
        return {
            "flow": run.flow,
            "run": run.number,
            "box": box.id,
            "try": number,
            "result": kept.result,
            "findings": len(kept.findings),
            "said": f"Your verdict on {on} is kept: {kept.result}{many}. Stop now: the flow goes on when your session "
            "ends.",
        }

    def job(self, workspace: str, command: str, title: str, minutes: int, *, actor: Actor) -> dict[str, Any]:
        """A job (design 0013 §17), started with `flow_job` by the box at work in the workspace while its try runs: one
        at a time, within the box's minutes, started detached in the container and kept on the try; what was started,
        said for the model. `RunError`, saying why, when it cannot be started."""
        run, flow, box = self._at_work(workspace, "a job is started by a box, while it works")
        limit = box.limits.minutes or flow.defaults.limits.minutes
        if not command.strip():
            raise RunError("a job needs a command to run: give flow_job the command, as you would run it in bash")
        if not 1 <= minutes <= limit:
            raise RunError(f"a job runs at least 1 minute and at most its box's {limit} minutes: give minutes again")
        with self._lock:
            state = self.runs.load(run.flow, run.number).box(box.id)
            last = state.tries[-1] if state.tries else None
            if last is None or last.sent is None or last.outcome is not None:
                raise RunError(f"{box.id}'s try has not begun, or has ended: no job starts for it")
            running = next((each for each in last.jobs if each.ended is None), None)
            if running is not None:
                raise RunError(
                    f"job {running.number} ({running.title or running.command}) still runs: one job at a time; end "
                    "your turn and wait for its end, which Clank sends you"
                )
            number = sum(len(each.jobs) for each in state.tries) + 1
        folder = jobs.folder_of(run.flow, run.number, box.id, number)
        try:
            jobs.start(self.kernel.parts["workspaces"], workspace, folder, command, minutes)
        except jobs.JobError as error:
            raise RunError(str(error)) from error
        job = Job(
            number=number, title=title.strip(), command=command, minutes=minutes, folder=folder,
            started=self.kernel.clock.now(),
        )  # fmt: skip
        run = self._change(run, functools.partial(_add_job, box=box.id, job=job))
        self._record_event(
            "flows.job", run, f"{box.title} started job {number}: {job.title or command}", actor, box=box.id,
            job=number, action="started", minutes=minutes, **{"try": last.number},
        )  # fmt: skip
        return {
            "flow": run.flow,
            "run": run.number,
            "box": box.id,
            "job": number,
            "folder": folder,
            "said": f"Job {number} started: {job.title or command}. It runs in the folder, its output in {folder}/log, "
            f"for at most {minutes} minutes. End your turn now, saying what you expect it to give: Clank sends its end "
            "to this session (its exit code, its time, its log's last lines), and you go on from there.",
        }

    def decide(self, workspace: str, given: dict[str, Any], *, actor: Actor) -> dict[str, Any]:
        """A checkpoint's decision (design 0013 §16), given with `flow_decide` while it works in the workspace: checked
        (`orchestrating.decided`) and kept on the checkpoint, the newest counting, then applied once its session ends.
        `RunError`, saying why, when no checkpoint works there or the decision cannot be kept as sent."""
        with self._lock:
            run = next(
                (
                    each
                    for each in self.runs.all()
                    if each.workspace == workspace and each.status in ACTIVE and each.orchestration.working is not None
                ),
                None,
            )
            if run is None or run.orchestration.working is None:
                raise RunError(f"no checkpoint of an orchestrator works in {workspace} now: only a checkpoint decides")
            record = self._record(run.flow)
            if record is None:
                raise RunError(f"{run.flow} is gone: nothing to decide")
            checkpoint = run.orchestration.working
            try:
                kept = orchestrating.decided(
                    checkpoint, record[0], run, given, limits=record[0].orchestrator, at=self.kernel.clock.now()
                )
            except orchestrating.DecisionRefused as error:
                raise RunError(str(error)) from error

            def keep(each: Run) -> None:
                if each.orchestration.working is not None and each.orchestration.working.number == kept.number:
                    each.orchestration.working.decision = kept

            run = self._change(run, keep)
        self._record_event(
            "flows.orchestrator", run, f"the orchestrator of {run.title} chose {kept.choice} at checkpoint "
            f"{kept.number}: {kept.why}", actor, checkpoint=kept.number, kind=kept.kind, box=kept.box,
            action="decided", choice=kept.choice, why=kept.why,
        )  # fmt: skip
        return {
            "flow": run.flow,
            "run": run.number,
            "checkpoint": kept.number,
            "choice": kept.choice,
            "said": f"Your decision is kept: {kept.choice}. Stop now: Clank applies it when your session ends.",
        }

    def _at_work(self, workspace: str, why: str) -> tuple[Run, Flow, Box]:
        """The run whose box works in the workspace now (one box at a time, §6), its flow and that box; `RunError`,
        saying `why` a box must be at work, when none is."""
        with self._lock:
            run = next(
                (each for each in self.runs.all() if each.workspace == workspace and each.status == "running"),
                None,
            )
        if run is None or not run.operation:
            raise RunError(f"no box of a flow works in {workspace} now: {why}")
        record = self._record(run.flow)
        box = _box_of(record[0], run.at) if record is not None else None
        if record is None or box is None:
            raise RunError(f"{run.at} of {run.title} is no longer in its flow")
        return run, record[0], box

    # The driver.

    async def run(self) -> None:
        """While the service runs: reconcile what a restart interrupted, then drive every active run whenever something
        changes."""
        send, receive = anyio.create_memory_object_stream[None](math.inf)
        with self._lock:
            self._send, self._token, self._loop = send, anyio.lowlevel.current_token(), threading.get_ident()
        try:
            await self._recover()
            await self._drive()
            async with receive:
                async for _ in receive:
                    while True:  # one look for every nudge waiting
                        try:
                            receive.receive_nowait()
                        except anyio.WouldBlock:
                            break
                    await self._drive()
        finally:
            with self._lock:
                self._send = self._token = self._loop = None
            send.close()

    def nudge(self) -> None:
        """Ask the driver to look at every active run again, from any thread, never waiting: from another thread the
        nudge is handed to a thread of its own, since its caller may hold a lock the event loop waits for (a flow
        written from another thread tells the runner while the settings' lock is held, and the driver reads the flows
        under that lock)."""

        def send() -> None:
            if self._send is not None:
                self._send.send_nowait(None)

        if self._token is None:
            return  # the runner does not run: its driver looks at every run when it starts
        if threading.get_ident() == self._loop:
            send()
            return
        threading.Thread(target=self._call, args=(send,), name="flows: a nudge", daemon=True).start()

    def _call(self, function: Callable[[], Any]) -> None:
        """Run `function` on the service's event loop, from any thread (never while holding the runner's lock)."""
        with self._lock:
            token, loop = self._token, self._loop
        if token is None:
            return
        if threading.get_ident() == loop:
            function()
            return
        try:
            anyio.from_thread.run_sync(function, token=token)
        except RuntimeError:
            log.debug("the service's event loop has ended")

    async def _drive(self) -> None:
        self._promote()
        runs = self.runs.all()
        latest = {run.flow: run for run in runs}  # sorted by number: each flow's newest
        for run in latest.values():
            try:
                self._mark_stale(run)
            except Exception:
                log.exception("looking for stale boxes in %s failed", run.name)
        for run in runs:
            if run.status in ACTIVE:
                try:
                    await self._advance(run.flow, run.number)
                except Exception:
                    log.exception("driving %s failed", run.name)
        self._promote()

    def _promote(self) -> None:
        """When no run is running, the oldest queued one begins."""
        with self._lock:
            runs = self.runs.all()
            if any(run.status == "running" for run in runs):
                return
            queued = sorted((run for run in runs if run.status == "queued"), key=lambda run: run.created)
            if not queued:
                return
            run = queued[0]
            run.status, run.behind = "running", ""
            self.runs.save(run)
        self._began(run, run.started_by)

    async def _advance(self, flow_id: str, number: int) -> None:
        """Do the run's next thing, as many times as it moves on without waiting."""
        for _ in range(10_000):  # each pass moves the run on, or returns
            with self._lock:
                run = self.runs.load(flow_id, number)
            if run.status != "running" or run.operation:
                return
            record = self._record(run.flow)
            if record is None:
                self._end(run, "stopped", RUNNER, "its flow's file is gone")
                return
            flow = record[0]
            if run.waiting is not None:
                asked = self.kernel.questions.get(run.waiting.question)
                if asked.status == "waiting":
                    if self._steers(run, flow, run.waiting):
                        await self._checkpoint(run, flow, "question", run.waiting.box, asked)
                    return
                await self._settle(run, flow, asked)
                continue
            box = _box_of(flow, run.at)
            if box is None:
                self._end(run, "stopped", RUNNER, f"its box {run.at} is no longer in the flow")
                return
            state = run.box(box.id)
            if state.state in ("done", "skipped", "stale"):  # stale: it ran, and a box before it changed since
                if state.state != "skipped" and await anyio.to_thread.run_sync(self.proposing.hold, run, box):
                    return  # its proposals wait for the owner: the tasks accepted come next (§9)
                if state.state == "done" and self._reviews(run, flow, box):
                    await self._checkpoint(run, flow, "review", box.id, None)
                    return  # the orchestrator reads what it did first (§16)
                if state.state != "skipped" and self._waits(flow, box):
                    self._ask(run, flow, box, "done")
                    continue  # the next pass finds it waiting: the orchestrator may decide it (§16)
                self._move_on(run, flow, RUNNER)
                continue
            if state.state == "failed":
                if box.type == "verify" and _found_wrong(state) and self._tries_left(run, flow, box.checks):
                    self._loop_back(run, flow, box)  # its fail line, back to the box it checks (§3)
                    continue
                await self._ask_showing(run, flow, box, "failed")  # a failed box, or a loop at its cap (§10)
                continue  # asked, or the run changed meanwhile: the next pass looks again
            if state.state == "running" or run.paused:
                return  # a box whose operation a restart interrupted waits for `_recover`; a paused run starts none
            if box.type == "you" and self._briefed(run, flow, box):
                continue  # a built flow's brief, written with the model (decision 0098)
            if box.type in ("you", "gate"):
                await self._ask_showing(run, flow, box, "you" if box.type == "you" else "gate")
                continue  # asked, or the run changed meanwhile: the next pass looks again
            operation = await self.kernel.operations.start(
                BOX, {"flow": run.flow, "run": run.number, "box": box.id}, actor=RUNNER
            )
            self._change(run, functools.partial(_working_on, box=box.id, operation=operation.id))
            return

    def _mark_stale(self, run: Run) -> None:
        """A finished box whose settings were edited, or whose deliverable no longer matches its fingerprint, is
        changed, and every box after it that has run is stale; nothing runs again (design 0013 §8). Files shown by a
        gate the run waits at are the owner's to edit: they are not looked at until the gate is answered."""
        record = self._record(run.flow)
        if record is None:
            return
        flow = record[0]
        try:
            folder = self._folder(run)
        except WorkspaceUnavailable:
            return  # its workspace is gone: nothing of it to look at
        names = order(flow)
        editing: set[str] = set()
        if run.waiting is not None and run.waiting.kind == "gate":
            gate = _box_of(flow, run.waiting.box)
            editing = set((gate.shows or _before_writes(flow, gate)) if gate is not None else [])
        elif run.waiting is not None and run.waiting.kind == "failed":
            editing = set(_loop_files(run, flow, run.waiting.box))
        found: list[tuple[str, str, list[str]]] = []

        def mark(each: Run) -> None:
            working = _task_at_work(each, flow)
            for index, name in enumerate(names):
                state, box = each.box(name), _box_of(flow, name)
                if box is None or state.state != "done" or state.changed:
                    continue
                why = _changed(box, state.settings, state.kept, folder, editing, working)
                if not why:
                    continue
                state.changed = why
                stale = []
                for later in names[index + 1 :]:
                    other = each.box(later)
                    current = later == each.at and each.status in ACTIVE
                    if other.state in ("done", "skipped") or (other.state == "failed" and not current):
                        other.state, other.why = "stale", f"{name} changed: {why}"
                        stale.append(later)
                found.append((name, why, stale))

        working = _task_at_work(run, flow)
        if not any(
            _changed(box, run.box(box.id).settings, run.box(box.id).kept, folder, editing, working)
            for box in flow.boxes
            if run.box(box.id).state == "done" and not run.box(box.id).changed
        ):
            return
        run = self._change(run, mark)
        for name, why, stale in found:
            said = f"{name} of {run.title} changed ({why})" + (f": {', '.join(stale)} stale" if stale else "")
            self._record_event("flows.stale", run, said, RUNNER, box=name, boxes=stale, why=why)

    def _waits(self, flow: Flow, box: Box) -> bool:
        """Whether a finished box waits for the owner before the next: its *when done*, or the flow's *wait after every
        box*, unless a gate follows it anyway (decision 0065)."""
        later = after(flow, box.id)
        if not later:
            return False
        following = _box_of(flow, later[0])
        if following is not None and following.type == "gate":
            return False
        return box.when_done == "wait" or flow.wait_after_every_box

    def _move_on(self, run: Run, flow: Flow, actor: Actor) -> None:
        later = after(flow, run.at)
        if not later:
            self._end(run, "done", actor)
            return
        self._change(run, lambda each: setattr(each, "at", later[0]))

    def _end(self, run: Run, outcome: str, actor: Actor, reason: str = "") -> None:
        with self._lock:
            run = self.runs.load(run.flow, run.number)
            if run.status not in ACTIVE:
                return
            waited = run.waiting.question if run.waiting is not None else ""
            run.status = "done" if outcome == "done" else "stopped"
            run.waiting, run.ended, run.paused = None, self.kernel.clock.now(), False
            self.runs.save(run)
        if waited:  # outside the lock: its listeners may wait for the service's event loop
            self._withdraw(waited, reason or "the run ended", actor)
        self.proposing.ended(run, reason or "the run ended", actor)
        said = f"{run.title} ({run.name}) is done" if outcome == "done" else f"{run.title} ({run.name}) {reason}"
        self._record_event("flows.run_ended", run, said, actor, outcome=run.status, reason=reason)

    def _began(self, run: Run, actor: Actor) -> None:
        self._record_event(
            "flows.run_started",
            run,
            f"{actor.describe()} started {run.title} ({run.name})",
            actor,
            workspace=run.workspace,
            version=run.version,
        )

    # Questions: YOU boxes, gates, a failed box, a box whose *when done* waits.

    async def _ask_showing(self, run: Run, flow: Flow, box: Box, kind: WaitingFor) -> bool:
        """Ask the box's question, saying how much each file it shows changed since the try before: counted in a
        thread, since comparing two copies may take a second, never on the service's event loop (design 0004's no
        stutter). False, asking nothing, when the run changed meanwhile: the driver looks at it again."""
        looped = kind == "failed" and box.type == "verify" and _found_wrong(run.box(box.id))
        found = _box_of(flow, box.checks) if looped else None
        paths = (box.shows or _before_writes(flow, box)) if kind == "gate" else (found.writes if found else [])
        if not paths:
            self._ask(run, flow, box, kind)
            return True
        since = await anyio.to_thread.run_sync(lambda: {path: self._since(run, flow, box, path) for path in paths})
        with self._lock:
            fresh = self.runs.load(run.flow, run.number)
        if _where(fresh, box.id) != _where(run, box.id):
            return False
        self._ask(run, flow, box, kind, since=since)
        return True

    def _ask(
        self, run: Run, flow: Flow, box: Box, kind: WaitingFor, detail: str = "", since: dict[str, str] | None = None
    ) -> None:
        state = run.box(box.id)
        draft = self._question(run, flow, box, kind, detail, since or {})
        asked = self.kernel.questions.ask(draft, asked_by=RUNNER)
        with self._lock:
            fresh = self.runs.load(run.flow, run.number)
            fresh.waiting = Waiting(question=asked.id, kind=kind, box=box.id)
            started = kind in ("you", "gate") and fresh.box(box.id).state != "running"
            if started:
                fresh.box(box.id).state = "running"
            self.runs.save(fresh)
        if started:
            self._record_event(
                "flows.box_started",
                fresh,
                f"{run.title} waits for you at {box.title}",
                RUNNER,
                box=box.id,
                type=box.type,
                **{"try": len(state.tries) + 1},
            )

    def _question(
        self, run: Run, flow: Flow, box: Box, kind: WaitingFor, detail: str, since: dict[str, str]
    ) -> QuestionDraft:
        about = Subject(kind="flow", id=run.flow)
        stop = Option(id="stop", label="Stop the flow", effect="The run ends here; nothing after it runs.", key="s")
        state = run.box(box.id)
        if kind == "you":
            files = ", ".join(box.writes) or "your part"
            return QuestionDraft(
                type="choice",
                title=f"{run.title}: {box.title}: write {files}, then say it is done",
                detail=detail or (box.holds or box.prompt or f"The flow waits for {files}."),
                options=[
                    Option(id="done", label="Done", effect="The flow goes on with what you wrote.", key="y"),
                    stop,
                ],
                about=about,
            )
        if kind == "gate":
            shown = box.shows or _before_writes(flow, box)
            target = _sent_back_to(flow, box)
            lines = [f"The flow {run.title} waits at {box.title}."]
            lines += [f"- {path}" + (f" ({since[path]})" if since.get(path) else "") for path in shown]
            return QuestionDraft(
                type="choice",
                title=f"{run.title}: {box.title}",
                detail="\n".join(lines),
                options=[
                    Option(id="approve", label="Approve and go on", effect="The next box starts.", key="y"),
                    Option(
                        id="back",
                        label="Send back with a note",
                        effect=_back(run, flow, target),
                        key="b",
                    ),
                    stop,
                ],
                about=about,
            )
        if kind == "failed" and box.type == "verify" and _found_wrong(state):
            return self._loop_question(run, flow, box, about, stop, since)
        if kind == "failed":
            tries = box.tries or flow.defaults.tries
            used = len(state.tries)
            again = "Try again" + (f" (past its {tries} tries)" if used >= tries else f" ({used} of {tries} used)")
            return QuestionDraft(
                type="choice",
                title=f"{run.title}: {box.title} failed: {state.why}",
                detail=f"Try {used} of {box.id} failed: {state.why}.",
                options=[
                    Option(id="retry", label=again, effect="Its next try starts, with your words if any.", key="r"),
                    Option(
                        id="take",
                        label="Take it as it is",
                        effect="Its files stand as they are; the flow goes on.",
                        key="t",
                    ),
                    Option(id="skip", label="Skip the box", effect="The flow goes on without it.", key="k"),
                    stop,
                ],
                about=about,
                urgency="high",
            )
        return QuestionDraft(
            type="approval",
            title=f"{run.title}: {box.title} is done; go on?",
            detail=f"{box.id} is done, and its *when done* says to wait for you before the next box.",
            options=[Option(id="go", label="Go on", effect="The next box starts.", key="y"), stop],
            about=about,
        )

    def _loop_question(
        self, run: Run, flow: Flow, box: Box, about: Subject, stop: Option, since: dict[str, str]
    ) -> QuestionDraft:
        """The gate the runner asks on its own when a VERIFY's loop has used its tries (design 0013 §3, §10): one more
        try past the cap, take the checked box's work as it is, skip the check, or stop."""
        state = run.box(box.id)
        verdict = state.tries[-1].verdict
        assert verdict is not None
        checked = box.checks
        found = _box_of(flow, checked)
        cap = (found.tries if found is not None else None) or flow.defaults.tries
        used = len(run.box(checked).tries)
        tries = f"its {_count(cap, 'try', 'tries')}" if used == cap else f"{used} tries, past its {cap}"
        on = f"{checked}'s try {verdict.checked}" if verdict.checked else checked
        lines = [f"{box.title} ({box.id}) found {on} wrong:"]
        lines += [f"{number}. {finding}" for number, finding in enumerate(verdict.findings, start=1)]
        written = [(path, since.get(path, "")) for path in (found.writes if found is not None else [])]
        if any(since for _, since in written):
            lines.append("")
            lines += [f"- {path} ({since})" for path, since in written if since]
        if verdict.criteria:
            lines.append("")
            lines += [
                f"- {'met' if each.met else 'not met'}: {each.line}" + (f": {each.evidence}" if each.evidence else "")
                for each in verdict.criteria
            ]
        lines += ["", f"Each try's verdict is kept in its folder ({box.id}/try-<k>/verdict.md)."]
        return QuestionDraft(
            type="choice",
            title=f"{run.title}: {box.title}: {checked} used {tries}, and the check still fails",
            detail="\n".join(lines),
            options=[
                Option(
                    id="retry",
                    label=f"One more try ({checked}'s try {used + 1}, past its {cap})",
                    effect=f"{checked} runs again with the findings and your words, if any; {box.id} checks it again.",
                    key="r",
                ),
                Option(
                    id="take",
                    label=f"Take {checked} as it is",
                    effect="Its files stand as they are now, your edits included; the flow goes on past the check.",
                    key="t",
                ),
                Option(id="skip", label="Skip the check", effect=f"The flow goes on past {box.id}.", key="k"),
                stop,
            ],
            about=about,
            urgency="high",
        )

    def _loop_back(self, run: Run, flow: Flow, box: Box, note: str = "", steer: str = "") -> None:
        """A VERIFY's fail line (design 0013 §3): the box it checks runs its next try, handed the findings (and the
        owner's note), and every box after it up to the VERIFY runs again, the boxes before taken as they stand; the
        VERIFY's own next try is handed its findings, to check how each was answered."""
        verdict = run.box(box.id).tries[-1].verdict
        assert verdict is not None
        checked = box.checks
        number = len(run.box(checked).tries)
        now = self._standing(run, flow, checked)
        told = (
            f"{box.title} ({box.id}) found it wrong, each finding one thing to fix",
            f"{checked}, a box before this one, runs again: {box.title} ({box.id}) found it wrong",
        )

        def back(each: Run) -> None:
            _again(each, flow, checked, told, now)
            each.box(checked).findings, each.box(checked).note = list(verdict.findings), note
            each.box(checked).steer = steer  # the orchestrator's words, when it gave the try (§16)
            mine = each.box(box.id)
            mine.findings = list(verdict.findings)
            mine.again = (
                f"you found {checked}'s try {number} wrong, and {checked} has run its try {number + 1} since: check "
                "it afresh, and say how each of your findings was answered"
            )
            each.at = checked

        self._change(run, back)

    def _tries_left(self, run: Run, flow: Flow, box: str) -> bool:
        """Whether a box may run again on its own: it has tries left in the run (design 0013 §4)."""
        found = _box_of(flow, box)
        if found is None:
            return False
        return len(run.box(box).tries) < (found.tries or flow.defaults.tries)

    async def _settle(self, run: Run, flow: Flow, asked: Question) -> None:
        """Act on the answer to the question the run waited for."""
        waiting = run.waiting
        assert waiting is not None
        self._change(run, lambda each: setattr(each, "waiting", None))
        box = _box_of(flow, waiting.box)
        if box is None:
            return
        if waiting.kind == "proposals":  # decided by its answer, or one by one; the driver holds the run for any left
            await anyio.to_thread.run_sync(self.proposing.answered, asked)
            return
        if asked.status == "withdrawn" or asked.answer is None:
            if waiting.kind in ("you", "gate"):
                self._change(run, lambda each: _set_state(each, box.id, "waiting"))
            return
        option, by, words = asked.answer.option, asked.answer.by, asked.answer.text.strip()
        if option == "stop":
            self._end(run, "stopped", by, f"stopped by {by.describe()} at {box.title}")
            return
        if waiting.kind == "you":
            self._settle_you(run, flow, box, by)
        elif waiting.kind == "gate":
            self._settle_gate(run, flow, box, option or "", words, by)
        elif waiting.kind == "failed":
            await self._settle_failed(run, flow, box, option or "", words, by)
        else:
            self._move_on(run, flow, by)

    def _settle_you(self, run: Run, flow: Flow, box: Box, by: Actor) -> None:
        folder = self._folder(run)
        missing = [path for path in box.writes if fingerprint(folder, path).size == 0]
        if missing:
            said = "; ".join(f"{path} is not in the folder yet" for path in missing)
            self._ask(run, flow, box, "you", detail=f"{said}: write it, then say it is done.")
            return
        kept = [fingerprint(folder, path) for path in box.writes]
        self._change(run, lambda each: _done(each, box, kept))
        self._record_event(
            "flows.box_ended", run, f"{by.describe()} did {box.title}", by, box=box.id, outcome="done", reason="",
            **{"try": len(run.box(box.id).tries) + 1},
        )  # fmt: skip
        self._move_on(run, flow, by)

    def _briefed(self, run: Run, flow: Flow, box: Box) -> bool:
        """A flow built with the model (design 0013 §15, decision 0098): its first box, a YOU, is done by itself when
        each of its files is in the folder and not empty, the brief the owner wrote with the model (changed since the
        planning began, `built.before`); False, doing nothing, for any other box, a flow not built, a file missing, or
        the brief as it was before (the YOU then asks, as any)."""
        if flow.built is None or box is not flow.boxes[0] or not box.writes:
            return False
        folder = self._folder(run)
        kept = [fingerprint(folder, path) for path in box.writes]
        if any(each.size == 0 for each in kept) or (flow.built.before and kept[0].sha256 == flow.built.before):
            return False  # a file missing, or the brief as it was before the planning: not the one written with it
        self._change(run, lambda each: _done(each, box, kept))
        files = ", ".join(box.writes)
        self._record_event(
            "flows.box_ended", run, f"{box.title} is done by {files}, the brief written with the model", RUNNER,
            box=box.id, outcome="done", reason="the brief written with the model", **{"try": 1},
        )  # fmt: skip
        self._move_on(run, flow, RUNNER)
        return True

    def _settle_gate(self, run: Run, flow: Flow, box: Box, option: str, words: str, by: Actor) -> None:
        if option == "back":
            target = _sent_back_to(flow, box)
            if target is None:
                self._ask(run, flow, box, "gate", detail="There is no box before it to send back to.")
                return
            steered = by == orchestrating.ORCHESTRATOR  # the orchestrator decided the gate (§16): its words, so said
            who = "the orchestrator" if steered else "the user"
            note = words or f"{'it' if steered else 'you'} sent it back at {box.title}"
            now = self._standing(run, flow, target)

            def back(each: Run) -> None:
                told = (
                    f"{who} sent it back at {box.title}",
                    f"{who} sent {target}, a box before this one, back at {box.title}",
                )
                _again(each, flow, target, told, now)
                if steered:
                    each.box(target).steer = note
                else:
                    each.box(target).note = note
                each.at = target

            self._change(run, back)
            self._record_event(
                "flows.box_ended", run, f"{by.describe()} sent {target} back at {box.title}", by, box=box.id,
                outcome="done", reason=f"sent back to {target}", **{"try": 1},
            )  # fmt: skip
            return
        folder = self._folder(run)
        shown = set(box.shows or _before_writes(flow, box))

        def approve(each: Run) -> None:
            for name in order(flow):  # the files shown, as the owner approved them (an edit at a gate is theirs, §8)
                if name == box.id:
                    break
                state = each.box(name)
                state.kept = [fingerprint(folder, kept.path) if kept.path in shown else kept for kept in state.kept]
            _done(each, box, [])

        self._change(run, approve)
        self._record_event(
            "flows.box_ended", run, f"{by.describe()} approved {box.title}", by, box=box.id, outcome="done",
            reason="approved", **{"try": 1},
        )  # fmt: skip
        self._move_on(run, flow, by)

    async def _settle_failed(self, run: Run, flow: Flow, box: Box, option: str, words: str, by: Actor) -> None:
        tries = len(run.box(box.id).tries)
        loop = box.type == "verify" and _found_wrong(run.box(box.id))
        steered = by == orchestrating.ORCHESTRATOR  # the orchestrator's words go to its own note (§16)
        if option == "retry" and loop:  # one more try of the box it checks, past its cap
            self._loop_back(run, flow, box, note="" if steered else words, steer=words if steered else "")
            return
        if option == "retry":

            def again(each: Run) -> None:
                each.box(box.id).state = "waiting"
                if steered:
                    each.box(box.id).steer = words
                else:
                    each.box(box.id).note = words

            self._change(run, again)
            return
        if option == "take":
            folder = self._folder(run)
            kept = [fingerprint(folder, path) for path in box.writes]

            def take(each: Run) -> None:
                _done(each, box, kept)
                if loop:  # the box it checks taken as it stands, the owner's edits at the gate theirs (§8)
                    checked = each.box(box.checks)
                    checked.kept = [fingerprint(folder, found.path) for found in checked.kept]
                    checked.changed = ""

            self._change(run, take)
            outcome, said = "done", "taken as it is"
        else:
            self._change(run, lambda each: _set_state(each, box.id, "skipped"))
            reason = f"{by.describe()} skipped {box.id}: the flow goes on without it"
            await anyio.to_thread.run_sync(lambda: self.proposing.set_aside(run, box.id, reason))
            outcome, said = "skipped", "skipped"
        self._record_event(
            "flows.box_ended", run, f"{by.describe()}: {box.title} {said}", by, box=box.id, outcome=outcome,
            reason=said, **{"try": tries},
        )  # fmt: skip
        if outcome == "done" and self.proposing.pending(self.runs.load(run.flow, run.number), box.id):
            return  # what it proposed is asked about first: the driver holds the run for it (§9)
        self._move_on(run, flow, by)

    def _wait_for(self, run: Run, waiting: Waiting) -> None:
        """The run waits for a question asked outside the driver's own (a batch of proposals)."""
        self._change(run, lambda each: setattr(each, "waiting", waiting))

    def _withdraw(self, question: str, reason: str, actor: Actor) -> None:
        with contextlib.suppress(QuestionError):  # answered meanwhile: the answer is read and set aside
            self.kernel.questions.withdraw(question, reason=reason, by=actor)

    # A model box's operation.

    async def _box(self, context: OperationContext) -> dict[str, Any]:
        flow_id, number, box_id = str(context.params["flow"]), int(context.params["run"]), str(context.params["box"])
        working: Working | None = None
        try:
            run = self.runs.load(flow_id, number)
            record = self._record(flow_id)
            box = _box_of(record[0], box_id) if record is not None else None
            if record is None or box is None:
                raise RunError(f"{flow_id} has no box {box_id} any more")
            flow = record[0]
            if context.params.get("follow"):
                working = await self._follow(run, box, bool(context.params.get("ended")))
            else:
                working = await self._begin(context, run, flow, box)
            outcome, reason = await self._work(context, run, flow, box, working)
            async with context.step("collect"):
                ran = None
                if outcome == "ended" and box.accept_command.strip():
                    outcome, reason, ran = await self._accept(context, run, flow, box)
                result = await context.run_blocking(
                    self._collect, flow_id, number, box_id, outcome, reason, working, ran
                )
        except anyio.get_cancelled_exc_class():  # spelling: keep (AnyIO's own name)
            self._forget(working)
            raise  # the service stops: after its restart, the box is reconciled and followed
        except Canceled:
            await self._stop_session(working, RUNNER)
            self._settle_anyway(flow_id, number, box_id, "stopped", "canceled from the Operations page", working)
            raise
        except Stopped as stopped:
            self._settle_anyway(flow_id, number, box_id, "stopped", str(stopped), working)
            return {"outcome": "stopped", "reason": str(stopped)}
        except Exception as error:
            self._settle_anyway(flow_id, number, box_id, "failed", str(error) or type(error).__name__, working)
            raise
        self._finished(flow_id, number, working)
        return result

    def _settle_anyway(
        self, flow_id: str, number: int, box_id: str, outcome: str, reason: str, working: Working | None
    ) -> None:
        """A box that ended otherwise than by its session's end: its try settled as far as it can be, and its run freed
        for the driver, whatever happens."""
        try:
            self._collect(flow_id, number, box_id, outcome, reason, working)
        except Exception:
            log.exception("settling %s of %s#%s failed", box_id, flow_id, number)
        finally:
            self._finished(flow_id, number, working)

    # The orchestrator's checkpoints (design 0013 §16, decisions 0123-0124).

    def _steers(self, run: Run, flow: Flow, waiting: Waiting) -> bool:
        """Whether the orchestrator decides the question the run waits for: while it is on and no checkpoint works, a
        gate, a failed box or a box whose *when done* waits, not decided before; the last gate only when it is its."""
        steering = flow.orchestrator
        if steering.role == "watch":  # it decides no question
            return False
        if not steering.on or run.orchestration.working is not None or waiting.question in run.orchestration.decided:
            return False
        if waiting.kind not in ("gate", "failed", "done"):
            return False
        return not (waiting.kind == "gate" and steering.final_review == "owner" and not after(flow, waiting.box))

    def _reviews(self, run: Run, flow: Flow, box: Box) -> bool:
        """Whether the orchestrator reads what a box did before the run goes on: a box a model ran, not read since its
        last try."""
        if not flow.orchestrator.on or box.type not in MODEL_TYPES or run.orchestration.working is not None:
            return False
        return run.orchestration.reviewed.get(box.id) != len(run.box(box.id).tries)

    async def _checkpoint(
        self, run: Run, flow: Flow, kind: orchestrating.Kind, box: str, asked: Question | None
    ) -> None:
        """Start a checkpoint: kept on the run first (after a box, holding the run as a box's operation does), then
        its operation started."""
        number = run.orchestration.checkpoints + 1
        options = [option.id for option in asked.options] if asked is not None else []
        checkpoint = orchestrating.Checkpoint(
            number=number, kind=kind, box=box, question=asked.id if asked is not None else "", options=options,
            started=self.kernel.clock.now(),
        )  # fmt: skip

        def begun(each: Run) -> None:
            each.orchestration.checkpoints = number
            each.orchestration.working = checkpoint
            each.orchestration.owner = ""
            if asked is not None:
                each.orchestration.decided.append(asked.id)
            if kind == "review":
                each.operation = f"checkpoint-{number}"  # held until the checkpoint is applied or let go

        run = self._change(run, begun)
        operation = await self.kernel.operations.start(
            ORCHESTRATE, {"flow": run.flow, "run": run.number, "checkpoint": number}, actor=RUNNER
        )

        def started(each: Run) -> None:
            if each.orchestration.working is not None and each.orchestration.working.number == number:
                each.orchestration.working.operation = operation.id
                if kind == "review":
                    each.operation = operation.id

        self._change(run, started)
        where = f"after {box}" if kind == "review" else f"at {box}'s question"
        self._record_event(
            "flows.orchestrator", run, f"the orchestrator of {run.title} reads the run {where} (checkpoint {number})",
            RUNNER, checkpoint=number, kind=kind, box=box, action="started", choice="", why="",
        )  # fmt: skip

    async def _orchestrate(self, context: OperationContext) -> dict[str, Any]:
        """A checkpoint's operation: the model, the flow's server (no box's try kept on it), a fresh Plan-mode session
        handed `_checkpoint_message`, followed to its end within the checkpoint's limits, then its decision applied."""
        flow_id, number, cp = str(context.params["flow"]), int(context.params["run"]), int(context.params["checkpoint"])
        working: Working | None = None
        run = self.runs.load(flow_id, number)
        try:
            with anyio.fail_after(10):  # the checkpoint is kept on the run just before its operation starts
                while (found := self.runs.load(flow_id, number).orchestration.working) is None or found.number != cp:
                    await anyio.sleep(0.02)
            record = self._record(flow_id)
            if record is None:
                raise RunError(f"{flow_id} is gone")
            flow, checkpoint = record[0], found
            box = self._orchestrator_box(flow)
            async with context.step("model"):
                await self._load(context, run, flow, box)
            async with context.step("server"):
                port = await self._serve(context, run, box, keep=False)
            async with context.step("session"):
                folder = self._folder(run)
                fresh = self.runs.load(flow_id, number)
                text = await context.run_blocking(self._checkpoint_message, fresh, flow, checkpoint, folder)
                kept = self.runs.run_folder(run) / "orchestrator" / f"checkpoint-{cp}" / "first-message.md"
                kept.parent.mkdir(parents=True, exist_ok=True)
                kept.write_bytes(text.encode("utf-8"))
                sessions = self._agents.sessions
                title = f"{run.title} · orchestrator · {cp}"
                session = await context.run_blocking(
                    functools.partial(sessions.new, run.workspace, port, title, actor=RUNNER)
                )
                working = self._watch(run.workspace, session, port)

                def opened(each: Run) -> None:
                    if each.orchestration.working is not None and each.orchestration.working.number == cp:
                        each.orchestration.working.session = session

                self._change(run, opened)
                await context.run_blocking(
                    functools.partial(
                        sessions.send, run.workspace, port, session, text, actor=RUNNER, agent=PLANNER,
                        model=SESSION_MODEL,
                    )
                )  # fmt: skip
                working.sent = True
            async with context.step("work"):
                await self._checkpoint_work(context, run, flow, checkpoint, working)
            async with context.step("apply"):
                await context.run_blocking(self._apply, flow_id, number, cp)
        except anyio.get_cancelled_exc_class():  # spelling: keep (AnyIO's own name)
            self._forget(working)
            raise  # the service stops: after its restart, the checkpoint is let go (`_recover`)
        except Canceled:
            await self._stop_session(working, RUNNER)
            self._let_go(self.runs.load(flow_id, number), "it was canceled from the Operations page")
            raise
        except Exception as error:
            await self._stop_session(working, RUNNER)
            self._let_go(self.runs.load(flow_id, number), f"it failed: {error or type(error).__name__}")
            raise
        finally:
            self._forget(working)
            self.nudge()
        return {"checkpoint": cp}

    def _orchestrator_box(self, flow: Flow) -> Box:
        """What a checkpoint runs as, for the model and server steps: a Plan-mode box of the orchestrator's preset (the
        flow's when it names none), with the workspace's MCP servers; never a box of the flow."""
        return Box.model_construct(
            id="orchestrator", type="plan", title="The orchestrator", model=flow.orchestrator.model, mcp_servers=None
        )

    def _checkpoint_message(self, run: Run, flow: Flow, checkpoint: orchestrating.Checkpoint, folder: Path) -> str:
        """A checkpoint's first message: the box's report with its handoff note, the question with its answers, the
        run, the brief, the ledger and the budget (`orchestrating.message`)."""
        box = _box_of(flow, checkpoint.box)
        note_file = folder.joinpath(*handoff.path(run.flow, checkpoint.box).split("/"))
        note = (
            note_file.read_text(encoding="utf-8", errors="replace") if box is not None and note_file.is_file() else ""
        )
        report = orchestrating.report(flow, run, box, folder, note) if box is not None else ""
        question = ""
        if checkpoint.question:
            try:
                asked = self.kernel.questions.get(checkpoint.question)
            except QuestionError:
                asked = None
            if asked is not None:
                answers = [f"- `{option.id}`: {option.label}. {option.effect}".rstrip() for option in asked.options]
                question = "\n".join([f"**{asked.title}**", "", asked.detail or "", "", "Its answers:", *answers])
        minutes = max(0, int((self.kernel.clock.now() - run.created).total_seconds() // 60))
        elapsed = f"{minutes // 60} h {minutes % 60} min" if minutes >= 60 else f"{minutes} min"
        return orchestrating.message(
            flow, run, checkpoint, limits=flow.orchestrator, folder=folder, report=report, question=question,
            elapsed=elapsed,
        )  # fmt: skip

    async def _checkpoint_work(
        self,
        context: OperationContext,
        run: Run,
        flow: Flow,
        checkpoint: orchestrating.Checkpoint,
        working: Working,
    ) -> None:
        """Follow the checkpoint's session to its end: idle, gone, past its limits, its run stopped, or its question
        answered by the owner meanwhile (its session then stopped). A session that ends without deciding is reminded
        once, in the same session, to give its decision with `flow_decide` (a local model wrote its decision as text
        on 2026-10-22), and followed again."""
        limits = flow.orchestrator.limits
        deadline = self.kernel.clock.now() + timedelta(minutes=limits.minutes)
        looked = time.monotonic()
        reminded = False
        while True:
            context.check_canceled()
            fresh = self.runs.load(run.flow, run.number)
            with self._lock:
                stopper = self._stopping.get(run.name)
            answered = False
            if checkpoint.question:
                with contextlib.suppress(QuestionError):
                    answered = self.kernel.questions.get(checkpoint.question).status != "waiting"
            if stopper is not None or fresh.status not in ACTIVE or answered:
                await self._stop_session(working, stopper or RUNNER)
                return
            if working.gone:
                return
            if working.idle:
                if reminded or working.port is None or self._decided(run, checkpoint.number):
                    return
                reminded, looked = True, time.monotonic()
                with self._lock:
                    working.idle = working.seen = False  # an idle before the reminder's answer began is not its end
                await context.run_blocking(
                    functools.partial(
                        self._agents.sessions.send, working.workspace, working.port, working.session, REMINDER,
                        actor=RUNNER, agent=PLANNER, model=SESSION_MODEL,
                    )
                )  # fmt: skip
                continue
            if working.tokens() > limits.tokens or self.kernel.clock.now() >= deadline:
                await self._stop_session(working, RUNNER)
                return
            if time.monotonic() - looked >= LOOK:
                looked = time.monotonic()
                await self._look(working)
                continue
            wake = working.wake
            with anyio.move_on_after(TICK):
                await wake.wait()
            if wake.is_set():
                working.wake = anyio.Event()

    def _decided(self, run: Run, number: int) -> bool:
        """Whether the checkpoint `number` of the run has given its decision."""
        working = self.runs.load(run.flow, run.number).orchestration.working
        return working is not None and working.number == number and working.decision is not None

    def _apply(self, flow_id: str, number: int, cp: int) -> None:
        """A checkpoint's decision, applied once its session ended: a question answered through the questions API by
        the orchestrator (set aside when the owner answered first); after a box, a note for the next box, changes to the
        boxes not yet run (through the settings, as any edit), the work sent back, or the run stopped. The ledger keeps
        it, with what was done."""
        run = self.runs.load(flow_id, number)
        checkpoint = run.orchestration.working
        if checkpoint is None or checkpoint.number != cp:
            return
        decision = checkpoint.decision
        if run.status not in ACTIVE:
            self._let_go(run, "its run ended")
            return
        if decision is None:
            self._let_go(run, "it ended without deciding")
            return
        record = self._record(flow_id)
        if record is None:
            self._let_go(run, "its flow is gone")
            return
        flow, revision = record
        cost, extra, applied, stop, pause, left, withdraw = 0, False, "", False, False, "", False
        if decision.kind == "question":
            try:
                asked: Question | None = self.kernel.questions.get(decision.question)
            except QuestionError:
                asked = None
            if asked is None or asked.status != "waiting":
                applied = "set aside: the question was answered first"
            elif decision.choice == orchestrating.LEAVE:
                applied = "left it to you"
                left = f"checkpoint {cp} left it to you: {decision.tell_user}"
            elif decision.choice == "back" and asked.option("back") is None:  # a failed box's: back to an earlier one
                target = decision.back_to
                standing = self._standing(run, flow, target)

                def back_from(each: Run) -> None:
                    told = (
                        "the orchestrator sent it back",
                        f"the orchestrator sent {target}, a box before this one, back",
                    )
                    _again(each, flow, target, told, standing)
                    each.box(target).steer = decision.note
                    each.at, each.waiting = target, None

                self._change(run, back_from)
                cost, applied, withdraw = 1, f"sent the work back to {target}", True
            else:
                cost = 1 if decision.choice in orchestrating.COSTLY else 0
                extra = decision.choice == "retry" and orchestrating.past_cap(flow, run, decision.box)
                applied = f"answered: {decision.choice}"
        elif decision.choice == "stop":
            applied, stop = "stopped the run", True
        elif decision.choice == "pause":
            applied, pause = "paused the run for you", True
        elif decision.choice == "back":
            target = decision.back_to
            now = self._standing(run, flow, target)

            def back(each: Run) -> None:
                told = ("the orchestrator sent it back", f"the orchestrator sent {target}, a box before this one, back")
                _again(each, flow, target, told, now)
                each.box(target).steer = decision.note
                each.at = target

            self._change(run, back)
            cost, applied = 1, f"sent the work back to {target}"
        else:
            if decision.choice == "change":
                try:
                    made = orchestrating.changed(flow, decision.changes)
                    self.kernel.settings.write(
                        Flow.KIND,
                        flow_id,
                        made.model_dump(mode="json"),
                        base=revision,
                        actor=orchestrating.ORCHESTRATOR,
                    )
                    flow = made
                    cost = len(decision.changes)
                    applied = f"changed {', '.join(change.box for change in decision.changes)}"
                except Exception as error:  # a rule broken, or the flow changed meanwhile: said, never lost
                    applied = f"its changes could not be made: {error}"
            following = self._next_model_box(flow, decision.box)
            if decision.note and following:
                self._change(run, lambda each: setattr(each.box(following), "steer", decision.note))
            applied = applied or "went on" + (f"; {following} is told its note" if decision.note and following else "")

        def keep(each: Run) -> None:
            state = each.orchestration
            state.stall = orchestrating.stalled_after(state, decision)
            state.facts = decision.facts or state.facts
            state.plan = decision.plan or state.plan
            state.changes += cost
            if extra:
                state.extra[decision.box] = state.extra.get(decision.box, 0) + 1
            if decision.kind == "review":
                state.reviewed[decision.box] = len(each.box(decision.box).tries)
            state.decisions.append(decision.model_copy(update={"applied": applied}))
            if left:
                state.owner = left
            if each.operation == checkpoint.operation or each.operation == f"checkpoint-{cp}":
                each.operation = ""
            state.working = None

        run = self._change(run, keep)
        if withdraw:
            self._withdraw(decision.question, f"the orchestrator sent the work back to {decision.back_to}", RUNNER)
        if decision.tell_user:
            run = self._tell(run, decision)
        self._write_ledger(run)
        self._record_event(
            "flows.orchestrator", run, f"the orchestrator of {run.title}, checkpoint {cp}: {applied}",
            orchestrating.ORCHESTRATOR, checkpoint=cp, kind=decision.kind, box=decision.box,
            action="set aside" if applied.startswith("set aside") else "applied", choice=decision.choice,
            why=decision.why,
        )  # fmt: skip
        if decision.kind == "question" and applied.startswith("answered"):
            with contextlib.suppress(QuestionError):  # the owner may answer in the same moment: theirs then counts
                self.kernel.questions.answer(
                    decision.question, by=orchestrating.ORCHESTRATOR, option=decision.choice, text=decision.note
                )
        if stop:
            self._end(run, "stopped", orchestrating.ORCHESTRATOR, f"stopped by the orchestrator: {decision.why}")
        if pause:
            with contextlib.suppress(RunError):  # it ended meanwhile: nothing to pause
                self.pause(run.flow, actor=orchestrating.ORCHESTRATOR)
        self.nudge()

    def _tell(self, run: Run, decision: orchestrating.Decision) -> Run:
        """The orchestrator's word for the owner (design 0013 §16): a question of high urgency, so it reaches the phone
        at once, which the run does not wait for; its answers pause or stop the run (`_told`)."""
        where = f"after {decision.box}" if decision.kind == "review" else f"at {decision.box}'s question"
        first = decision.tell_user.splitlines()[0].strip()
        asked = self.kernel.questions.ask(
            QuestionDraft(
                type="choice",
                title=f"The orchestrator of {run.title}: {first if len(first) <= 160 else first[:157] + '...'}",
                detail=f"{decision.tell_user}\n\nCheckpoint {decision.number}, {where}: {decision.choice}. "
                f"{decision.why}",
                options=[
                    Option(id="seen", label="Seen", effect="The run goes on.", key="y"),
                    Option(
                        id="pause",
                        label="Pause the run",
                        effect="The box at work finishes; nothing new starts until you go on.",
                        key="p",
                    ),
                    Option(id="stop", label="Stop the run", effect="The run ends here.", key="s"),
                ],
                urgency="high",
                about=Subject(kind="flow", id=run.flow),
            ),
            asked_by=orchestrating.ORCHESTRATOR,
        )
        return self._change(run, lambda each: each.orchestration.told.append(asked.id))

    def _told(self, question: Question) -> None:
        """The owner's answer to the orchestrator's word: pause or stop its run (one that ended meanwhile is left)."""
        if question.status != "answered" or question.answer is None or question.answer.option not in ("pause", "stop"):
            return
        run = next((each for each in self.runs.all() if question.id in each.orchestration.told), None)
        if run is None or run.status not in ACTIVE:
            return
        with contextlib.suppress(RunError):
            if question.answer.option == "pause":
                self.pause(run.flow, actor=question.answer.by)
            else:
                self.stop(run.flow, actor=question.answer.by)

    def _let_go(self, run: Run, why: str) -> None:
        """A checkpoint that cannot decide: after a box, the run goes on as its flow says; at a question, the question
        waits for the owner; said in the ledger and an event."""
        checkpoint = run.orchestration.working
        if checkpoint is None:
            return
        yours = (
            f"checkpoint {checkpoint.number} {why}: the question waits for you"
            if checkpoint.kind == "question"
            else f"checkpoint {checkpoint.number} {why}: the run went on as its flow says"
        )

        def go(each: Run) -> None:
            state = each.orchestration
            if state.working is None or state.working.number != checkpoint.number:
                return
            if checkpoint.kind == "review":
                state.reviewed[checkpoint.box] = len(each.box(checkpoint.box).tries)
            state.owner = yours
            if each.operation in (checkpoint.operation, f"checkpoint-{checkpoint.number}") and each.operation:
                each.operation = ""
            state.working = None

        run = self._change(run, go)
        self._write_ledger(run)
        self._record_event(
            "flows.orchestrator", run, f"the orchestrator of {run.title}: {yours}", RUNNER,
            checkpoint=checkpoint.number, kind=checkpoint.kind, box=checkpoint.box, action="yours", choice="", why=why,
        )  # fmt: skip
        self.nudge()

    async def _reconcile_checkpoint(self, operation: Operation) -> Reconciliation:
        """A checkpoint a restart interrupted: let go by `_recover` (no session is started again on its own)."""
        return Reconciliation("a checkpoint the service's stop interrupted: it is let go, the run going on without it")

    def _next_model_box(self, flow: Flow, box: str) -> str:
        """The next box after `box` that a model runs, which a review's note is told; "" when none."""
        for name in after(flow, box):
            found = _box_of(flow, name)
            if found is not None and found.type in MODEL_TYPES:
                return name
        return ""

    def _write_ledger(self, run: Run) -> None:
        """The run's ledger, `orchestrator.md` beside its file, for the owner to read."""
        path = self.runs.run_folder(run) / "orchestrator.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        text = f"# The orchestrator of {run.title} ({run.name})\n\n" + orchestrating.ledger_text(run) + "\n"
        path.write_bytes(text.encode("utf-8"))

    async def _begin(self, context: OperationContext, run: Run, flow: Flow, box: Box) -> Working:
        """The steps model, server and session: the box's session started, its first message sent."""
        state = run.box(box.id)
        number = len(state.tries) + 1
        mode = effective_mode(box)
        agent = PLANNER if mode == "plan" else BUILD
        told = _told(state)
        attempt = Try(number=number, started=self.kernel.clock.now(), operation=context.id, agent=agent,
                      mode=mode or "", told=told)  # fmt: skip

        def begun(each: Run) -> None:
            each.box(box.id).tries.append(attempt)
            each.box(box.id).state = "running"
            each.box(box.id).note = each.box(box.id).again = each.box(box.id).steer = ""
            each.box(box.id).findings = []
            each.operation = context.id

        self._change(run, begun)
        if number > 1:  # it proposes anew (§9): what its earlier tries proposed and is still waiting is set aside
            reason = f"{box.id} runs again (try {number}) and proposes anew"
            await context.run_blocking(lambda: self.proposing.set_aside(run, box.id, reason, before=number))
        async with context.step("model"):
            preset = await self._load(context, run, flow, box)
            self._change(run, lambda each: setattr(each.box(box.id).tries[-1], "preset", preset))
        async with context.step("server"):
            port = await self._serve(context, run, box)
        self._unless_stopped(run)
        async with context.step("session"):
            folder = self._folder(run)
            fresh = self.runs.load(run.flow, run.number)
            text = preparing.message(self.runs, fresh, run.flow, flow, box, folder, number=number, told=told)
            kept = self.runs.try_folder(run, box.id, number) / "first-message.md"
            kept.parent.mkdir(parents=True, exist_ok=True)
            kept.write_bytes(text.encode("utf-8"))
            before = [fingerprint(folder, path) for path in box.writes]
            note = None
            if handoff.writes_note(box):  # its handoff note counts only when written during this try (§5)
                handoff.keep_out_of_git(folder, run.flow)
                note = fingerprint(folder, handoff.path(run.flow, box.id))
            earlier = self._earlier(run, flow, box, folder)
            title = f"{run.title} · {box.id} · try {number}"
            sessions = self._agents.sessions
            session = await context.run_blocking(
                functools.partial(sessions.new, run.workspace, port, title, actor=RUNNER)
            )
            working = self._watch(run.workspace, session, port)
            if mode in ("review", "auto"):
                self._agents.review.session_mode(run.workspace, session, mode)

            def started(each: Run) -> None:
                found = each.box(box.id).tries[-1]
                found.session, found.before, found.earlier = session, before, earlier
                found.handoff_before = note

            self._change(run, started)
            await context.run_blocking(
                functools.partial(
                    sessions.send, run.workspace, port, session, text, actor=RUNNER, agent=agent, model=SESSION_MODEL
                )
            )
            working.sent = True  # before the run's file says so, so a reader of the file finds it said here too
            self._change(run, lambda each: setattr(each.box(box.id).tries[-1], "sent", self.kernel.clock.now()))
        self._record_event(
            "flows.box_started", run, f"{box.title} started: {title}", RUNNER, box=box.id, type=box.type,
            session=session, agent=agent, mode=mode or "", **{"try": number},
        )  # fmt: skip
        return working

    async def _load(self, context: OperationContext, run: Run, flow: Flow, box: Box) -> str:
        """The step model (design 0013 §7, decision 0062): the box's preset switched into the main slot when the slot
        does not run it, by the runtime's own switch, started once nothing it waits for is left and waited for to its
        end; the preset the slot runs then ("" for none). The owner's stop, or a cancel, ends the wait at once; one
        heard once the switch started is held until the switch ends (`_switched`); a failed switch is a `RunError` in
        its own words. What it reads of the slots and the operations is read off the service's event loop."""
        slot = await context.run_blocking(self._slot)
        wanted = named(flow, box)
        if not wanted:
            now = self._runtime.state.slot(slot)
            running = now.preset if now.status == "ready" and now.preset else ""
            what = self._runtime.title(running) if running else "nothing yet"
            context.log(f"{box.id} names no preset: it runs on what the {slot} slot runs ({what})")
            return running
        try:
            found = self._runtime.preset(wanted)
        except Exception as error:  # the runtime's PresetNotFound: the flow named a preset since gone
            raise RunError(f"its preset {wanted} is not there: {error}") from error
        preset, title = str(found["id"]), str(found["title"])
        if found.get("endpoint"):  # a cloud preset: the workspace is asked first (design 0016 §9, decision 0112)
            await self._cloud_allowed(context, run, box, title)
        said = ""
        try:
            while True:
                context.check_canceled()
                self._unless_stopped(run)
                route = await context.run_blocking(self._runtime.route, slot)
                if route["status"] == "ready" and route["preset"] == preset and not route["busy"]:
                    if not said:
                        context.log(f"the {slot} slot runs {title} already: no switch")
                    return preset
                why = await context.run_blocking(self._switch_waits, run.workspace, slot, title, bool(route["busy"]))
                if not why:
                    try:
                        switch = await self.kernel.operations.start(SWITCH, {"slot": slot, "preset": preset},
                                                                     actor=RUNNER)  # fmt: skip
                    except Busy:  # an operation took the slot a moment ago: it is waited for
                        await anyio.sleep(WAIT)
                        continue
                    if said:
                        said = ""
                        self._change(run, functools.partial(_set_waits, why=""))
                    return await self._switched(context, run, box, slot, preset, title, switch)
                if why != said:
                    said = why
                    context.log(why)
                    self._change(run, functools.partial(_set_waits, why=why))
                    self._record_event(
                        "flows.model", run, f"{box.id} of {run.title} is {why}", RUNNER, box=box.id, preset=preset,
                        action="waits", why=why, seconds=None, operation="",
                    )  # fmt: skip
                await anyio.sleep(WAIT)
        finally:
            if said:
                self._change(run, functools.partial(_set_waits, why=""))

    async def _cloud_allowed(self, context: OperationContext, run: Run, box: Box, title: str) -> None:
        """Before a box's cloud preset is loaded, its workspace's answer (design 0016 §9): asked once, the run saying
        it waits for it; a `RunError`, saying how to allow it, when the workspace is kept on this machine or no one
        answered in time."""
        asked = await context.run_blocking(self._workspaces.ask_cloud, run.workspace, title)
        if asked["allowed"]:
            return
        if not asked["needed"]:
            raise RunError(str(asked["why"]))
        why = f"waiting for your answer: may {run.workspace} use the cloud model {title}?"
        context.log(why)
        self._change(run, functools.partial(_set_waits, why=why))
        self._record_event(
            "flows.model", run, f"{box.id} of {run.title} is {why}", RUNNER, box=box.id, preset=title,
            action="waits", why=why, seconds=None, operation="",
        )  # fmt: skip
        try:
            while True:
                context.check_canceled()
                self._unless_stopped(run)
                bound = await context.run_blocking(self._workspaces.cloud_view, run.workspace)
                if bound["models"] == "cloud":
                    return
                if bound["cloud_answered"]:
                    raise RunError(
                        f"{run.workspace} is kept on this machine, and {box.id} runs on the cloud model {title}: "
                        "allow the cloud for it on This folder (u), or clank workspace allow FOLDER --cloud; or give "
                        f"{box.id} a local preset"
                    )
                if bound["cloud_question"] != asked["question"]:
                    raise RunError(
                        f"no one answered whether {run.workspace} may use the cloud model {title}: run the flow again "
                        "to be asked again"
                    )
                await anyio.sleep(WAIT)
        finally:
            self._change(run, functools.partial(_set_waits, why=""))

    async def _switched(
        self, context: OperationContext, run: Run, box: Box, slot: str, preset: str, title: str, switch: Operation
    ) -> str:
        """Follow a switch the step model started to its end: the preset, once the slot runs it; else a `RunError` in
        the switch's own words. The owner's stop, or a cancel, heard meanwhile is held until the switch ends (it goes on
        to its end in the runtime): the run log says how it ended, the owner's window is told of a switch done, and
        its try names the preset loaded for it, before the stop or the cancel is raised."""
        context.log(f"switching the {slot} slot to {title} for {box.id}: {switch.id}")
        self._record_event(
            "flows.model", run, f"the {slot} slot switches to {title} for {box.id} of {run.title}", RUNNER,
            box=box.id, preset=preset, action="switching", why="", seconds=None, operation=switch.id,
        )  # fmt: skip
        held: Canceled | Stopped | None = None
        while True:
            if held is None:
                try:
                    context.check_canceled()
                    self._unless_stopped(run)
                except (Canceled, Stopped) as heard:
                    held = heard
                    context.log(f"{heard or 'canceled'}: the switch to {title} goes on to its end first ({switch.id})")
            with anyio.move_on_after(WAIT):
                await self.kernel.operations.wait(switch.id)
            ended = self.kernel.operations.get(switch.id)
            if ended.status not in UNFINISHED:
                break
        seconds = round(((ended.finished or ended.updated) - ended.created).total_seconds(), 1)
        if ended.status != "done":
            why = ended.error or ended.status
            self._record_event(
                "flows.model", run, f"the {slot} slot did not switch to {title} for {box.id} of {run.title}: {why}",
                RUNNER, box=box.id, preset=preset, action="failed", why=why, seconds=seconds, operation=switch.id,
            )  # fmt: skip
            if held is not None:
                raise held
            raise RunError(f"the {slot} slot did not switch to {title}: {why}")
        context.log(f"the {slot} slot runs {title}: switched in {seconds:.0f} s")
        self._record_event(
            "flows.model", run, f"the {slot} slot switched to {title} for {box.id} of {run.title} in {seconds:.0f} s",
            RUNNER, box=box.id, preset=preset, action="switched", why="", seconds=seconds, operation=switch.id,
        )  # fmt: skip
        await context.run_blocking(self._tell_window, run, box)
        if held is not None:
            self._change(run, lambda each: setattr(each.box(box.id).tries[-1], "preset", preset))
            raise held
        return preset

    def _tell_window(self, run: Run, box: Box) -> None:
        """Tell the owner's window in the run's workspace that its model changed (decision 0062): a box goes on whether
        or not the telling worked, which the log says."""
        try:
            self._agents.model_changed(
                run.workspace, by=f"The flow {run.title}, for its box {box.id},",
                besides=self._box_sessions(run.workspace), actor=RUNNER,
            )  # fmt: skip
        except Exception:
            log.exception("telling %s's window its model changed failed", run.workspace)

    def _switch_waits(self, workspace: str, slot: str, title: str, busy: bool) -> str:
        """What a switch of `slot` to `title` waits for now, in words; "" for nothing (decision 0062): an operation that
        changes the slot, a session of the workspace at work that is no box's (the owner's own), or a request in flight
        on the slot (one held for a paused session too), or the gateway's answer when it runs but did not say what it
        has in flight (no answer is not none in flight)."""
        if busy:
            changing = next(
                (
                    each for each in self.kernel.operations.find(limit=50)
                    if each.type in CHANGING and str(each.params.get("slot") or "main") == slot
                    and each.status in UNFINISHED
                ),
                None,
            )  # fmt: skip
            if changing is not None:
                return f"waiting for {changing.title} ({changing.id}) on the {slot} slot to end, to load {title}"
        mine = self._agents.sessions.working(workspace, besides=self._box_sessions(workspace))
        if mine:
            titles = [str(each["title"] or each["session"]) for each in mine if not each["parent"]] or ["a subagent"]
            yours = "your session " + titles[0] if len(titles) == 1 else "your sessions " + ", ".join(titles)
            return f"waiting for {yours} to be idle, to load {title}"
        routes = self._gateway.routes()
        roles, default = routes.get("roles") or {}, str(routes.get("default_slot") or "main")
        activity = self._gateway.activity()
        if activity.get("state") == "running" and activity.get("problem"):
            return f"waiting for the gateway to say what is in flight on the {slot} slot, to load {title}"
        flying = [
            each
            for each in activity.get("requests") or []
            if str(each.get("slot") or roles.get(str(each.get("role") or ""), default)) == slot
        ]
        if flying:
            return f"waiting for {_count(len(flying), 'request')} in flight on the {slot} slot to end, to load {title}"
        return ""

    def _box_sessions(self, workspace: str) -> set[str]:
        """The sessions of every flow's boxes in the workspace: never the owner's own."""
        return {
            each.session
            for run in self.runs.all()
            if run.workspace == workspace
            for state in run.boxes.values()
            for each in state.tries
            if each.session
        }

    def _slot(self) -> str:
        """The slot a box's requests reach: the one the gateway routes the role `agent` to (design 0013 §7)."""
        routes = self._gateway.routes()
        return str((routes.get("roles") or {}).get(ROLE) or routes.get("default_slot") or "main")

    async def _follow(self, run: Run, box: Box, ended: bool) -> Working:
        """A session a restart interrupted, followed again: its watch, its mode, and its status read once."""
        last = run.box(box.id).tries[-1]
        working = self._watch(run.workspace, last.session, last.port)
        working.seen = working.sent = True  # it was sent its first message before the restart
        if last.tokens:
            working.steps["before the restart"] = last.tokens  # what it wrote then counts toward its limit
        if last.mode in ("review", "auto"):
            self._agents.review.session_mode(run.workspace, last.session, last.mode)
        status = (
            "ended" if ended else await anyio.to_thread.run_sync(self._status, run.workspace, last.port, last.session)
        )
        if status == "ended":
            working.idle = True
        elif status == "gone":
            working.gone = True
        return working

    async def _work(
        self, context: OperationContext, run: Run, flow: Flow, box: Box, working: Working
    ) -> tuple[str, str]:
        """Follow the session to its end: idle, gone, stopped, or past a limit (its session then stopped)."""
        minutes = box.limits.minutes or flow.defaults.limits.minutes
        tokens = box.limits.tokens or flow.defaults.limits.tokens
        last = self.runs.load(run.flow, run.number).box(box.id).tries[-1]
        deadline = (last.sent or last.started) + timedelta(minutes=minutes)
        saved = last.tokens
        looked = time.monotonic()
        async with context.step("work"):
            while True:
                context.check_canceled()
                if working.tokens() > saved:  # kept as it grows, so a restart goes on counting from it
                    saved = working.tokens()
                    self._change(run, functools.partial(_set_tokens, box=box.id, tokens=saved))
                with self._lock:
                    stopper = self._stopping.get(run.name)
                if stopper is not None and not working.stop:
                    working.stop, working.stopped_by = f"stopped by {stopper.describe()}", stopper
                if working.stop:
                    await self._stop_session(working, working.stopped_by or RUNNER)
                    return "stopped", working.stop
                if working.gone:
                    return "failed", "its session is gone: its OpenCode server stopped"
                if working.idle:
                    return "ended", ""
                if working.tokens() > tokens:
                    await self._stop_session(working, RUNNER)
                    return (
                        "failed",
                        f"it wrote {working.tokens():,} tokens, past its limit of {tokens:,}: Clank "
                        "stopped its session",
                    )
                if self.kernel.clock.now() >= deadline:
                    await self._stop_session(working, RUNNER)
                    span = f"{minutes} minute" + ("" if minutes == 1 else "s")
                    return "failed", f"it ran past its limit of {span}: Clank stopped its session"
                if time.monotonic() - looked >= LOOK:
                    looked = time.monotonic()
                    await self._look(working)
                    continue
                wake = working.wake
                with anyio.move_on_after(TICK):
                    await wake.wait()
                if wake.is_set():
                    working.wake = anyio.Event()

    async def _accept(
        self, context: OperationContext, run: Run, flow: Flow, box: Box
    ) -> tuple[str, str, accepting.Ran | None]:
        """*Accept when* as a command (design 0013 §4), once the session's deliverables were found written: run in a
        thread of its own while the step looks at the run's stop and the operation's cancel a few times a second. On
        either, or when the service stops, it is ended in the container and its thread let go (§6: a stopped box's try
        counts as stopped). The try's outcome so far, why, and how the command ran."""
        before = await context.run_blocking(self._written, run, box)
        if before is None:
            return "ended", "", None  # a deliverable is not written: collect says which, and the command does not run
        minutes = box.limits.minutes or flow.defaults.limits.minutes
        answer: list[tuple[accepting.Commanded, str]] = []
        failure: list[Exception] = []
        finished = threading.Event()

        def command() -> None:
            try:
                answer.append(
                    accepting.accept(self._workspaces, run.workspace, box.accept_command, minutes, context.id)
                )
            except Exception as error:  # raised in the step, below
                failure.append(error)
            finally:
                finished.set()

        threading.Thread(target=command, name=f"accept command of {run.name} {box.id}", daemon=True).start()
        try:
            while not finished.is_set():
                context.check_canceled()
                with self._lock:
                    stopper = self._stopping.get(run.name)
                if stopper is not None:
                    await self._end_command(run, context.id)
                    words = f"stopped by {stopper.describe()} while its accept command ran"
                    ended = accepting.Commanded(command=box.accept_command, status=None, ended=f"was ended: {words}")
                    return "stopped", words, accepting.Ran(ended, "", before)
                await anyio.sleep(TICK)
        except BaseException:  # canceled from the Operations page, or the service stops: ended in the container too
            with anyio.CancelScope(shield=True):
                await self._end_command(run, context.id)
            raise
        if failure:
            raise failure[0]
        commanded, said = answer[0]
        return "ended", "", accepting.Ran(commanded, said, before)

    async def _end_command(self, run: Run, tag: str) -> None:
        with anyio.move_on_after(accepting.ENDING + 5):
            await anyio.to_thread.run_sync(
                functools.partial(accepting.end, self._workspaces, run.workspace, tag), abandon_on_cancel=True
            )

    def _written(self, run: Run, box: Box) -> dict[str, str] | None:
        """The fingerprints of the box's deliverables, by path, when its session wrote each during the try; else
        None."""
        fresh = self.runs.load(run.flow, run.number)
        attempt = fresh.box(box.id).tries[-1]
        folder = self._folder(fresh)
        now = [fingerprint(folder, path) for path in box.writes]
        submitted = self.proposing.submitted(fresh, box.id, attempt.number)
        if _unfinished(box, now, {kept.path: kept for kept in attempt.before}, attempt.verdict, submitted):
            return None
        return {kept.path: kept.sha256 for kept in now}

    def _collect(
        self,
        flow_id: str,
        number: int,
        box_id: str,
        outcome: str,
        reason: str,
        working: Working | None,
        ran: accepting.Ran | None = None,
    ) -> dict[str, Any]:
        """The step collect: the deliverables fingerprinted and copied as the session and the box's accept command, if
        it ran (`ran`), left them; the try and the box settled."""
        run = self.runs.load(flow_id, number)
        record = self._record(flow_id)
        box = _box_of(record[0], box_id) if record is not None else None
        state = run.box(box_id)
        if box is None or record is None or not state.tries:
            return {"outcome": "failed"}
        flow = record[0]
        attempt = state.tries[-1]
        folder = self._folder(run)
        now = [fingerprint(folder, path) for path in box.writes]
        commanded = None
        if ran is not None:  # *accept when* as a command (§4): all it said kept, and the deliverables it changed
            changed = [kept.path for kept in now if ran.before.get(kept.path, "") != kept.sha256]
            commanded = ran.commanded.model_copy(update={"changed": changed})
            place = self.runs.try_folder(run, box_id, attempt.number) / "accept-command.txt"
            place.parent.mkdir(parents=True, exist_ok=True)
            place.write_bytes(accepting.kept(commanded, ran.said).encode("utf-8"))
        if outcome == "ended":
            submitted = self.proposing.submitted(run, box_id, attempt.number)
            reason = _unfinished(box, now, {kept.path: kept for kept in attempt.before}, attempt.verdict, submitted)
            outcome = "failed" if reason else "done"
            if outcome == "done" and box.accept_command.strip() and commanded is None:
                outcome, reason = "failed", f"its accept command `{box.accept_command}` did not run"
            elif outcome == "done" and commanded is not None and not commanded.passed:
                outcome, reason = "failed", commanded.reason
        copies = self.runs.try_folder(run, box_id, attempt.number) / "deliverables"
        for kept in now:
            if kept.sha256 and kept.size <= flow.defaults.copied_up_to:
                target = copies.joinpath(*kept.path.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(folder.joinpath(*kept.path.split("/")), target)
                kept.copied = True
        note = self._handoff(run, flow, box, attempt, folder)
        tokens = working.tokens() if working is not None else 0

        # a TASK's own progress in a plan before it is no change (design 0013 §8)
        absorbed = _progress(attempt.earlier, folder) if box.type == "task" else {}
        verdict = attempt.verdict if outcome == "done" and box.type == "verify" else None
        wrong = _wrong(box, verdict) if verdict is not None and verdict.result == "fail" else ""

        def settled(each: Run) -> None:
            for name in order(flow):
                if name == box_id:
                    break
                state = each.box(name)
                state.kept = [_absorbed(kept, absorbed) for kept in state.kept]
            found = each.box(box_id)
            last = found.tries[-1]
            last.ended, last.outcome, last.reason = self.kernel.clock.now(), outcome, reason  # type: ignore[assignment]
            last.deliverables, last.tokens = now, max(last.tokens, tokens)
            last.command = commanded or last.command
            last.handoff = note
            if outcome == "done" and wrong:
                found.state, found.why = "failed", wrong  # its fail line is the driver's to take (§3)
            elif outcome == "done":
                _done(each, box, now)
            else:
                found.state, found.why = "failed", reason

        run = self._change(run, settled)
        actor = working.stopped_by if working is not None and working.stopped_by else RUNNER
        said = f"{box.title} is done" if outcome == "done" else f"{box.title} {outcome}: {reason}"
        if outcome == "done" and note is None and handoff.writes_note(box):
            said += " (it left no handoff note)"  # marked, never a failure: the note is not the deliverable
        if wrong:
            checked = box.checks
            cap = (_box_of(flow, checked) or box).tries or flow.defaults.tries
            used = len(run.box(checked).tries)
            then = (
                f"back to {checked}, for its try {used + 1} of {cap}"
                if self._tries_left(run, flow, checked)
                else f"{checked} used its tries: a gate decides"
            )
            said, reason = f"{box.title} {wrong.removeprefix('it ')}: {then}", f"{wrong}: {then}"
        self._record_event(
            "flows.box_ended", run, said, actor, box=box_id, outcome=outcome, reason=reason,
            **{"try": attempt.number},
        )  # fmt: skip
        return {"outcome": outcome, "reason": reason}

    def _handoff(self, run: Run, flow: Flow, box: Box, attempt: Try, folder: Path) -> Kept | None:
        """A box's handoff note, when it wrote one during its try: copied beside the try as `handoff.md` (decision
        0086); None when it wrote none, or is no box that writes one."""
        if not handoff.writes_note(box) or attempt.handoff_before is None:  # no session started: no note to take
            return None
        now = fingerprint(folder, handoff.path(run.flow, box.id))
        if not written(attempt.handoff_before, now):
            return None
        if now.size <= flow.defaults.copied_up_to:
            target = self.runs.try_folder(run, box.id, attempt.number) / "handoff.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(folder.joinpath(*now.path.split("/")), target)
            now.copied = True
        return now

    def _finished(self, flow_id: str, number: int, working: Working | None) -> None:
        self._forget(working)
        with self._lock:
            run = self.runs.load(flow_id, number)
            run.operation = run.waits_for = ""
            self.runs.save(run)
            self._stopping.pop(run.name, None)
        self.nudge()

    def _unless_stopped(self, run: Run) -> None:
        """Stop a box still starting when its run was stopped meanwhile: no session is started for it."""
        with self._lock:
            stopper = self._stopping.get(run.name)
        if stopper is not None:
            raise Stopped(f"stopped by {stopper.describe()} before its session started")

    def _forget(self, working: Working | None) -> None:
        if working is None:
            return
        with self._lock:
            self._working.pop((working.workspace, working.session), None)
        self._agents.review.session_mode(working.workspace, working.session, None)

    async def _serve(self, context: OperationContext, run: Run, box: Box, *, keep: bool = True) -> int:
        """The step server (design 0013 §4, §5): the run's own OpenCode server, without a terminal, with the box's
        limits (the model the main slot runs for it, `_limits`): reused while it runs with them; else started with
        Clank's configuration, written for the slot as it runs now, after the server it replaces is ended once no
        session at work on it is left (the run log saying so), the limits read again once the wait is over so the run
        keeps those the server is started with; then the box's MCP servers on it alone. Its port."""
        workspace = run.workspace
        limits = await context.run_blocking(self._limits)
        fresh = self.runs.load(run.flow, run.number)
        known, had = fresh.server, fresh.server_limits
        listed = await context.run_blocking(self._agents.sessions.servers, workspace)
        running = known is not None and any(int(each["port"]) == known and not each.get("terminal") for each in listed)
        if running and known is not None and had != limits:
            await self._server_free(context, run, box, known)
            limits = await context.run_blocking(self._limits)  # the slot may have changed while its sessions worked
        if running and had == limits:
            context.log(f"the flow's OpenCode server on port {known} has {box.id}'s limits: {_sizes(limits)}")
            port = int(known or 0)
        else:
            replaced = None
            if running and known is not None:
                ended = await context.run_blocking(self._agents.sessions.end_server, workspace, known)
                context.log(f"the flow's OpenCode server on port {known} {ended}: {box.id}'s limits differ")
                replaced = known
            env = await context.run_blocking(self._agents.configure, workspace)
            port = await context.run_blocking(self._agents.sessions.serve, workspace, env)

            def served(each: Run) -> None:
                each.server, each.server_limits = port, limits

            self._change(run, served)
            if replaced is None:
                said = f"the OpenCode server of {run.title} started on port {port} for {box.id}: {_sizes(limits)}"
            else:
                before = f"the server had {had.context:,} and {had.output:,}" if had else "the server's were not kept"
                if had is not None and had.images != limits.images:
                    before += ", reading images" if had.images else ", reading none"
                said = (
                    f"the OpenCode server of {run.title} started again on port {port} for {box.id}, whose model has "
                    f"other limits ({_sizes(limits)}; {before}): the server on port {replaced} ended, and what its MCP "
                    "servers ran in the background with it"
                )
            context.log(said)
            self._record_event(
                "flows.server", run, said, RUNNER, box=box.id, port=port, context=limits.context, output=limits.output,
                images=limits.images, replaced=replaced, action="started" if replaced is None else "started again",
                why=said,
            )  # fmt: skip
        if keep:  # a checkpoint's server is the flow's own, and no box's try keeps it (§16)
            self._change(run, lambda each: _on_server(each, box.id, port))
        try:
            tools = await context.run_blocking(self._agents.box_tools, workspace, port, box.mcp_servers)
        except AgentError as error:
            raise RunError(str(error)) from error
        changed = [f"connected {', '.join(tools['started'])}"] if tools["started"] else []
        changed += [f"disconnected {', '.join(tools['stopped'])}"] if tools["stopped"] else []
        context.log(f"its MCP servers: {', '.join(tools['connected']) or 'none'}" + (f" ({'; '.join(changed)})"
                                                                                       if changed else ""))  # fmt: skip
        for name, why in tools["failed"].items():
            context.log(f"its MCP server {name} did not connect: {why}")
        for name, why in tools["kept"].items():
            context.log(f"its MCP server {name} stays connected, as it did not disconnect: {why}")
        if keep:
            self._change(run, lambda each: setattr(each.box(box.id).tries[-1], "tools", list(tools["connected"])))
        return port

    def _limits(self) -> ServerLimits:
        """What Clank's configuration gives the model the main slot runs now (`Agents.plan`: its context and output,
        else Clank's fallback), and whether it reads images: what a flow's server is started with."""
        planned = self._agents.plan()["limits"]
        images = self._agents.reads_images()
        return ServerLimits(context=int(planned["context"]), output=int(planned["output"]), images=images)

    async def _server_free(self, context: OperationContext, run: Run, box: Box, port: int) -> None:
        """Wait until no session works on the flow's server on `port` (one the owner started there from the phone,
        say), saying so in the run's file and the run log, before it is ended."""
        said = ""
        try:
            while True:
                context.check_canceled()
                self._unless_stopped(run)
                working = await context.run_blocking(self._agents.sessions.working, run.workspace)
                there = [each for each in working if each["port"] == port and not each["parent"]]
                if not there and not any(each["port"] == port for each in working):
                    return
                titles = [str(each["title"] or each["session"]) for each in there] or ["a subagent"]
                yours = "your session " + titles[0] if len(titles) == 1 else "your sessions " + ", ".join(titles)
                why = (
                    f"waiting for {yours} on the flow's OpenCode server to be idle, to start it again with {box.id}'s "
                    "limits"
                )
                if why != said:
                    said = why
                    context.log(why)
                    self._change(run, functools.partial(_set_waits, why=why))
                    self._record_event(
                        "flows.server", run, f"{box.id} of {run.title} is {why}", RUNNER, box=box.id, port=port,
                        context=None, output=None, images=None, replaced=None, action="waits", why=why,
                    )  # fmt: skip
                await anyio.sleep(WAIT)
        finally:
            if said:
                self._change(run, functools.partial(_set_waits, why=""))

    def _watch(self, workspace: str, session: str, port: int | None) -> Working:
        working = Working(workspace, session, port)
        with self._lock:
            self._working[(workspace, session)] = working
        return working

    async def _stop_session(self, working: Working | None, actor: Actor) -> None:
        if working is None or working.port is None:
            return
        try:
            await anyio.to_thread.run_sync(
                functools.partial(
                    self._agents.sessions.stop, working.workspace, working.port, working.session, actor=actor
                )
            )
        except SessionError as error:
            log.warning("stopping %s's session %s failed: %s", working.workspace, working.session, error)

    async def _look(self, working: Working) -> None:
        """The session's status read through the bridge, every `LOOK` seconds while it works: its end is taken from
        there should its watcher not say it (OpenCode's stream went silent on 2026-10-22, and a run waited out each
        box's time limit after the box had ended). Only an end is taken; a server gone is the watcher's to say."""
        try:
            status = await anyio.to_thread.run_sync(self._status, working.workspace, working.port, working.session)
        except Exception:  # a bridge's answer not as expected: the next look, or the watcher, says what follows
            log.exception("reading %s's session %s failed", working.workspace, working.session)
            return
        if status == "ended":
            with self._lock:
                working.idle = True

    def _status(self, workspace: str, port: int | None, session: str) -> str:
        """A session's status through the bridge: working, ended, or gone (its server, or the container, stopped)."""
        try:
            listed = self._agents.sessions.servers(workspace)
        except SessionError:
            return "gone"
        server = next((each for each in listed if int(each["port"]) == port), None)
        found = next((each for each in (server or {}).get("sessions", []) if each["id"] == session), None)
        if found is None:
            return "gone"
        return "ended" if found.get("status", "idle") == "idle" else "working"

    def _standing(self, run: Run, flow: Flow, box: str) -> dict[str, Kept] | None:
        """The deliverables of the boxes before `box` as they stand in the folder, by path; None when the folder is not
        there to look at."""
        try:
            folder = self._folder(run)
        except WorkspaceUnavailable:
            return None
        found = {}
        for name in order(flow):
            if name == box:
                break
            for kept in run.box(name).kept:
                found[kept.path] = fingerprint(folder, kept.path)
        return found

    def _earlier(self, run: Run, flow: Flow, box: Box, folder: Path) -> list[Kept]:
        """The deliverables of the boxes before `box` that are done, as they are now."""
        found = []
        for name in order(flow):
            if name == box.id:
                break
            for kept in run.box(name).kept:
                found.append(fingerprint(folder, kept.path))
        return found

    # After a restart.

    async def _reconcile(self, operation: Operation) -> Reconciliation:
        """What an interrupted box's session did meanwhile, read through the bridge."""
        try:
            run = self.runs.load(str(operation.params["flow"]), int(operation.params["run"]))
        except (OSError, ValueError, KeyError):
            return Reconciliation("its run's file does not read: nothing is followed")
        state = run.box(str(operation.params["box"]))
        last = state.tries[-1] if state.tries else None
        if run.status not in ACTIVE:
            self._found[operation.id] = "stopped"
            return Reconciliation(
                "its run was stopped meanwhile: the runner stops its session, and its try ends stopped"
            )
        if last is None or not last.session or last.sent is None:
            self._found[operation.id] = "unstarted"
            return Reconciliation("it was interrupted before its first message was sent: its box waits at a gate")
        found = await anyio.to_thread.run_sync(self._status, run.workspace, last.port, last.session)
        self._found[operation.id] = found
        return Reconciliation(
            {
                "working": f"its session {last.session} still works: the runner follows it",
                "ended": f"its session {last.session} ended meanwhile: the runner collects it",
                "gone": f"its session {last.session} is gone: its box failed and waits at a gate",
            }[found]
        )

    async def _recover(self) -> None:
        """Each run whose box a restart interrupted: its session followed again, or its box failed at a gate; in a run
        stopped meanwhile, its session stopped and its try ended stopped. A checkpoint a restart interrupted is let go
        (§16): after a box, the run goes on as its flow says; at a question, the question waits for the owner."""
        for run in self.runs.all():
            working = run.orchestration.working
            if working is not None:
                try:
                    found_operation = self.kernel.operations.get(working.operation) if working.operation else None
                except OperationError:
                    found_operation = None
                if found_operation is None or found_operation.status not in UNFINISHED:
                    self._let_go(run, "the service stopped while it worked")
                    run = self.runs.load(run.flow, run.number)
            if not run.operation:
                continue
            try:
                operation = self.kernel.operations.get(run.operation)
            except OperationError:
                operation = None
            if operation is not None and operation.status in UNFINISHED:
                continue  # this service's own
            found = self._found.pop(run.operation, "unstarted") if operation is not None else "unstarted"
            state = run.box(run.at)
            if run.status not in ACTIVE:
                await self._stopped_meanwhile(run)
                continue
            if found in ("working", "ended") and state.tries:
                follow = await self.kernel.operations.start(
                    BOX,
                    {"flow": run.flow, "run": run.number, "box": run.at, "follow": True, "ended": found == "ended"},
                    actor=RUNNER,
                )
                self._change(run, functools.partial(_set_operation, operation=follow.id))
                continue
            reason = (
                "its session is gone: the service stopped while it worked, and its OpenCode server stopped since"
                if found == "gone"
                else "the service stopped before its first message was sent"
            )
            self._change(run, functools.partial(_set_operation, operation=""))
            if state.tries:
                self._collect(run.flow, run.number, run.at, "failed", reason, None)
            else:
                self._change(run, functools.partial(_set_failed, box=run.at, reason=reason))

    async def _stopped_meanwhile(self, run: Run) -> None:
        """A run stopped while its box was ending when the service stopped: its box's session stopped (again), its try
        ended stopped, and its operation let go, so it can run again from a box."""
        state = run.box(run.at)
        last = state.tries[-1] if state.tries else None
        if last is not None and last.session and last.port is not None:
            await self._stop_session(Working(run.workspace, last.session, last.port), RUNNER)
        self._change(run, functools.partial(_set_operation, operation=""))
        if last is not None and last.outcome is None:
            reason = "its run was stopped, and the service stopped before its box ended"
            self._collect(run.flow, run.number, run.at, "stopped", reason, None)
        elif state.state == "running":
            self._change(run, functools.partial(_set_failed, box=run.at, reason="its run was stopped"))

    # What the runner hears.

    def _heard(self, workspace: str, line: dict[str, Any]) -> None:
        """A line of a workspace's watcher: a box's session went idle, finished a step, or is gone."""
        kind = line.get("type")
        touched: list[Working] = []
        looked: list[Working] = []
        with self._lock:
            found = self._working.get((workspace, str(line.get("session") or ""))) if kind in AT_WORK else None
            if found is not None and kind == "status" and line.get("status") == "idle":
                if found.seen:  # an idle before its answer began is not its end
                    found.idle = True
                    touched.append(found)
            elif found is not None:
                found.seen = True
                part = line.get("part") or {}
                if kind == "part" and part.get("type") == "step-finish":
                    said = part.get("tokens") or {}
                    found.steps[str(part.get("id"))] = int(said.get("output") or 0) + int(said.get("reasoning") or 0)
                    touched.append(found)
            elif kind in ("gone", "synced"):
                followed = {int(port) for port in line.get("ports") or []}
                for each in self._working.values():
                    if each.workspace != workspace:
                        continue
                    if (kind == "gone" and each.port == line.get("port")) or (
                        kind == "synced" and each.port is not None and each.port not in followed
                    ):
                        each.gone = True
                        touched.append(each)
                    elif kind == "synced" and each.sent:
                        looked.append(each)
            elif kind == "session" and line.get("deleted"):
                found = self._working.get((workspace, str((line.get("session") or {}).get("id") or "")))
                if found is not None:
                    found.gone = True
                    touched.append(found)
        for each in touched:
            self._call(each.wake.set)
        if looked:  # a watcher started again: a session that ended while none ran is said idle by none
            threading.Thread(
                target=self._look_again, args=(looked,), name="flows: sessions read again", daemon=True
            ).start()

    def _look_again(self, looked: list[Working]) -> None:
        """The status of each box's session, read once through the bridge after its workspace's watcher started again:
        one that ended meanwhile has ended."""
        for each in looked:
            try:
                if self._status(each.workspace, each.port, each.session) != "ended":
                    continue
            except Exception:  # a bridge's answer not as expected: the watcher's lines still say what follows
                log.exception("reading %s's session %s again failed", each.workspace, each.session)
                continue
            with self._lock:
                each.idle = True
            self._call(each.wake.set)

    def _resolved(self, question: Question) -> None:
        """A question about a flow was answered or withdrawn: an answer about a batch of proposals decides them at
        once (from any client, design 0013 §9), then the driver looks again; on a thread of its own when it was
        answered on the event loop, which never waits for the proposals' lock."""
        if question.about is None or question.about.kind != "flow":
            return
        if question.status == "answered" and threading.get_ident() == self._loop:
            threading.Thread(target=self._answered, args=(question,), name="flows: an answer", daemon=True).start()
            return
        self._answered(question)

    def _answered(self, question: Question) -> None:
        try:
            self.proposing.answered(question)
        except Exception:  # the driver takes the answer when it holds the run, so nothing is lost
            log.exception("taking the answer to %s failed", question.id)
        try:
            self._told(question)
        except Exception:
            log.exception("taking the answer to the orchestrator's word %s failed", question.id)
        self.nudge()

    def _event(self, event: Any) -> None:
        if event.type == "settings.changed" and (event.data or {}).get("kind") == "flow":
            self.nudge()

    # Small helpers.

    def _record(self, flow: str) -> tuple[Flow, str] | None:
        """The flow in force, with its revision; None when there is none."""
        from clank.kernel.settings import SettingsError

        try:
            loaded = self.kernel.settings.get(Flow.KIND, flow)
        except SettingsError:
            return None
        assert isinstance(loaded.record, Flow)
        return loaded.record, loaded.revision

    def _active(self, flow: str) -> Run:
        latest = self.runs.latest(flow)
        if latest is None or latest.status not in ACTIVE:
            raise RunError(f"{flow} does not run now: `clank flow run` starts it")
        return latest

    def _folder(self, run: Run) -> Path:
        return Path(self._workspaces.folder_of(run.workspace))

    def _change(self, run: Run, change: Callable[[Run], Any]) -> Run:
        """Change a run's file: read it as it is now, change it, write it whole."""
        with self._lock:
            fresh = self.runs.load(run.flow, run.number)
            change(fresh)
            self.runs.save(fresh)
            return fresh

    def _record_event(self, event_type: str, run: Run, summary: str, actor: Actor, **data: Any) -> None:
        self.kernel.events.record(
            event_type,
            summary=summary,
            actor=actor,
            subject=Subject(kind="flow", id=run.flow),
            data={"flow": run.flow, "run": run.number, **data},
        )


def _box_of(flow: Flow, id: str) -> Box | None:
    return next((box for box in flow.boxes if box.id == id), None)


def _before_writes(flow: Flow, gate: Box) -> list[str]:
    """What a gate that names no file shows: the deliverable of the box before it that writes one."""
    target = _sent_back_to(flow, gate)
    box = _box_of(flow, target) if target else None
    return list(box.writes) if box is not None else []


def _sent_back_to(flow: Flow, gate: Box) -> str | None:
    """The box a gate sends back to: the latest before it that writes a file it shows, else the latest before it that
    writes any file."""
    before: list[str] = []
    for name in order(flow):
        if name == gate.id:
            break
        before.append(name)
    shown = set(gate.shows)
    by_id = {box.id: box for box in flow.boxes}
    for name in reversed(before):
        if shown & set(by_id[name].writes):
            return name
    return next((name for name in reversed(before) if by_id[name].writes), None)


def _back(run: Run, flow: Flow, target: str | None) -> str:
    """What sending back at a gate does: the box it sends back to runs its next try, which the gate says (its last, or
    past its tries: design 0013 §10), with the note; every box after it runs again."""
    found = _box_of(flow, target) if target else None
    if target is None or found is None:
        return "The box before runs its next try with your note; every box after it runs again."
    cap = found.tries or flow.defaults.tries
    number = len(run.box(target).tries) + 1
    which = f"try {number} of {cap}"
    if number == cap:
        which += ", its last,"
    elif number > cap:
        which = f"try {number}, past its {cap} tries,"
    return f"{target} runs {which} with your note; every box after it runs again."


def _told(state: Any) -> str:
    """What a box's next first message says of its last try: how it ended, why it runs again, a VERIFY's findings,
    and the owner's note."""
    said = []
    end = ":" if state.findings else "."
    if state.tries:
        last = state.tries[-1]
        if last.outcome == "failed":
            said.append(f"Try {last.number} failed: {last.reason}.")
            if last.command is not None and not last.command.passed:
                said.append(accepting.told(last.command))
        elif last.outcome == "stopped":
            said.append(f"Try {last.number} was stopped: {last.reason}.")
        elif last.outcome == "done":
            said.append(f"Try {last.number} was done" + (f"; {state.again}{end}" if state.again else "."))
        if last.outcome != "done" and state.again:
            said.append(f"{state.again[0].upper()}{state.again[1:]}{end}")
    if state.findings:
        said += [f"{number}. {finding}" for number, finding in enumerate(state.findings, start=1)]
    if state.note.strip():
        said.append(f"The user's note: {state.note.strip()}")
    if state.steer.strip():
        said.append(f"The orchestrator's note: {state.steer.strip()}")
    return "\n".join(said)


def _again(run: Run, flow: Flow, box: str, told: tuple[str, str], now: dict[str, Kept] | None) -> None:
    """`box` and every box after it to run again, their next first messages told why (`told`: for the box, for those
    after it); the boxes before it taken as they stand (`now`, their deliverables in the folder): what the boxes that
    run again start from, so a later change to them marks those boxes stale again (design 0013 §8)."""
    for name in [box, *after(flow, box)]:
        state = run.box(name)
        if state.state != "waiting" or state.tries:
            state.state = "waiting"
        state.again = told[0] if name == box else told[1]
        state.findings = []
    if now is None:
        return
    for name in order(flow):
        if name == box:
            break
        state, found = run.box(name), _box_of(flow, name)
        state.kept = [now.get(kept.path, kept) for kept in state.kept]
        if state.settings and found is not None:
            state.settings = _settings_fingerprint(found)
        state.changed = ""


def _unfinished(
    box: Box, now: list[Kept], before: dict[str, Kept], verdict: Verdict | None = None, submitted: bool = False
) -> str:
    """Why a box that ended is not done; "" when it is. A VERIFY is done only with its verdict, a DECOMPOSE only once
    it submitted its proposals (design 0013 §2)."""
    reasons = []
    if box.type == "decompose" and not submitted:
        reasons.append(
            "it ended without submitting its tasks: a DECOMPOSE proposes each with flow_propose_box, then calls "
            "flow_submit"
        )
    if box.type == "verify" and verdict is None:
        reasons.append("it ended without a verdict: a VERIFY ends by calling flow_verdict")
    for kept in now:
        if written(before.get(kept.path), kept):
            continue
        if kept.sha256:
            reasons.append(f"{kept.path} is left from before: it was not written during this try")
        else:
            reasons.append(f"it ended without writing {kept.path}")
    return "; ".join(reasons)


def _changed(
    box: Box, settings: str, kept: list[Kept], folder: Path, editing: set[str], working: dict[str, Kept]
) -> str:
    """Why a finished box is changed: its settings edited, or a file it delivered changed; "" when it is not. A plan
    whose progress alone changed since the TASK at work found it as delivered (`working`: what it found) is not changed
    yet: its end takes that progress as its own (`_absorbed`)."""
    if settings and settings != _settings_fingerprint(box):
        return "its settings were edited"
    for each in kept:
        if each.path in editing or not each.sha256:
            continue
        try:
            stat = folder.joinpath(*each.path.split("/")).stat()
            if (stat.st_size, stat.st_mtime_ns) == (each.size, each.modified):
                continue  # as delivered: not read again
        except OSError:
            pass
        now = fingerprint(folder, each.path)
        if now.sha256 == each.sha256:
            continue
        found = working.get(each.path)
        if found is not None and found.sha256 == each.sha256 and each.rest and now.rest == each.rest:
            continue  # the TASK's own progress, while it works
        return f"{each.path} changed in the folder" if now.sha256 else f"{each.path} is gone from the folder"
    return ""


def _task_at_work(run: Run, flow: Flow) -> dict[str, Kept]:
    """The earlier boxes' deliverables as the TASK the run is at found them when it started, while it works, by path;
    empty when no TASK works (design 0013 §8: a change to a plan's progress during a TASK is its progress)."""
    box = _box_of(flow, run.at)
    state = run.box(run.at)
    if not run.operation or box is None or box.type != "task" or state.state != "running" or not state.tries:
        return {}
    last = state.tries[-1]
    return {} if last.outcome is not None else {kept.path: kept for kept in last.earlier}


def _progress(earlier: list[Kept], folder: Path) -> dict[str, tuple[str, Kept]]:
    """The plans a TASK was handed that changed during it in their progress alone: by path, the fingerprint it found
    when it started, and the file as it is now."""
    found = {}
    for before in earlier:
        if not before.rest:
            continue
        now = fingerprint(folder, before.path)
        if now.rest == before.rest and now.sha256 != before.sha256:
            found[before.path] = (before.sha256, now)
    return found


def _absorbed(kept: Kept, absorbed: dict[str, tuple[str, Kept]]) -> Kept:
    """A delivered plan as it stands after a TASK: its progress during the TASK taken as no change, when the TASK found
    it as delivered (a change made between boxes counts)."""
    found = absorbed.get(kept.path)
    if found is None:
        return kept
    started, now = found
    return now if kept.sha256 == started and kept.rest == now.rest else kept


def _settings_fingerprint(box: Box) -> str:
    """A box's settings as it ran, fingerprinted (where it came from left out)."""
    values = box.model_dump(mode="json", exclude={"proposed"})
    return hashlib.sha256(json.dumps(values, sort_keys=True).encode("utf-8")).hexdigest()


def _done(run: Run, box: Box, kept: list[Kept]) -> None:
    state = run.box(box.id)
    state.state, state.kept, state.why, state.changed, state.again = "done", kept, "", "", ""
    state.settings = _settings_fingerprint(box)


def _set_state(run: Run, box: str, state: str) -> None:
    run.box(box).state = state  # type: ignore[assignment]


def _set_failed(run: Run, *, box: str, reason: str) -> None:
    run.box(box).state, run.box(box).why = "failed", reason


def _working_on(run: Run, *, box: str, operation: str) -> None:
    run.operation = operation
    run.box(box).state = "running"


def _set_tokens(run: Run, *, box: str, tokens: int) -> None:
    last = run.box(box).tries[-1]
    last.tokens = max(last.tokens, tokens)


def _set_operation(run: Run, *, operation: str) -> None:
    run.operation = operation
    if not operation:  # its box's operation let go: what it waited for is said no more (a kill skips its own end)
        run.waits_for = ""


def _set_waits(run: Run, *, why: str) -> None:
    run.waits_for = why


def _sizes(limits: ServerLimits) -> str:
    images = ", reading images" if limits.images else ""
    return f"{limits.context:,} tokens of context, {limits.output:,} out{images}"


def _found_wrong(state: Any) -> bool:
    """Whether a VERIFY's last try was done with a fail: its fail line is still to take, or its loop's gate."""
    last = state.tries[-1] if state.tries else None
    return last is not None and last.outcome == "done" and last.verdict is not None and last.verdict.result == "fail"


def _wrong(box: Box, verdict: Verdict) -> str:
    """Why a VERIFY that gave a fail is failed: what it found wrong."""
    on = f"{box.checks}'s try {verdict.checked}" if verdict.checked else box.checks
    return f"it found {on} wrong, with {_count(len(verdict.findings), 'finding')}"


def _loop_files(run: Run, flow: Flow, box: str) -> list[str]:
    """The files of the box a VERIFY checks, while the run waits at its loop's gate: the owner's to edit there."""
    found = _box_of(flow, box)
    if found is None or found.type != "verify" or not _found_wrong(run.box(box)):
        return []
    checked = _box_of(flow, found.checks)
    return list(checked.writes) if checked is not None else []


def _add_job(run: Run, *, box: str, job: Job) -> None:
    run.box(box).tries[-1].jobs.append(job)


def _set_verdict(run: Run, *, box: str, verdict: Verdict) -> None:
    run.box(box).tries[-1].verdict = verdict


def _where(run: Run, box: str) -> tuple[Any, ...]:
    """Where a run stands, as far as asking `box`'s question goes: when any of it changed, the driver looks again."""
    state = run.box(box)
    waiting = run.waiting.question if run.waiting is not None else ""
    return run.status, run.paused, run.at, waiting, run.operation, state.state, len(state.tries)


def _tag(box: Box) -> str:
    return f"{'an' if box.type == 'integrate' else 'a'} {box.type.upper()}"


def _count(number: int, word: str, words: str = "") -> str:
    return f"{number:,} {word if number == 1 else (words or word + 's')}"


def _on_server(run: Run, box: str, port: int) -> None:
    run.server = port
    run.box(box).tries[-1].port = port
