"""The proposals of a flow's boxes, in the service (design 0013 §9; decision 0064): staged, submitted, decided.

`propose` gives a proposal to the box at work in the workspace its MCP server names (one box runs at a time, §6), while
its try runs, as a verdict is given: checked (each refusal naming the argument to fix, in words the model can act on:
`proposals.read`, then the preset, then the flow's rules with the batch's waiting proposals and this one joined), then
kept in that try's batch with an id of its own, waiting for the owner; with the flow's auto-accept on, it joins the flow
at once instead, accepted by the setting, while fewer than the flow's cap joined so in the run (past it, it waits). A
proposal while no box works is refused: a proposal from the workspace's own agent, naming its flow, comes later (plan
s26, call 1).

`submit` asks the owner one question about the batch's proposals still waiting, about its flow: *accept all* or
*reject all*, answered from any client. The owner also decides each alone (`decide`: accept, accept with an edit, or
reject; `edit` changes one and keeps it waiting), never the agent. An accepted proposal joins the flow's file at once,
written through the settings like any change, so an edit made on the version it replaced is refused with both versions
shown (design 0002 §2.2); when the last proposal the question asks about is decided, the question is withdrawn. The
first proposal of a try to join takes out of the flow the boxes its box added before that have not started in the run
(§9: a box run again proposes anew).

The driver holds a run at a box whose last try's proposals still wait (`hold`: the question asked, or asked again for
those staged since, and the run waiting for it), so the tasks accepted come next; an answer given while the box still
worked, or before a restart, is taken then. Each proposal and each decision is an event with its actor; none holds a
prompt's text. Batches are changed under this part's own lock, never under the runner's, and the flow's file is never
written while the runner's lock is held. That lock is held while the flow's file is written and the questions and
events told, whose listeners may wait for the service's event loop (the event stream does), so the loop never waits
for it: the driver calls `hold`, `answered` and `set_aside` on a thread, and what only reads a batch (`submitted`,
`pending`, `ended`) reads it without the lock, each batch file being replaced whole.
"""

import contextlib
import threading
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any, Literal

from clank.components.flows.kinds import Box, Flow
from clank.components.flows.proposals import (
    Batch,
    Batches,
    Proposal,
    ProposalRefused,
    edited,
    joined,
    next_id,
    read,
    refusals,
)
from clank.components.flows.runner import ACTIVE, RUNNER, RunError
from clank.components.flows.runs import Run, Try, Waiting, order
from clank.kernel.events import Actor, EventType, Subject
from clank.kernel.questions import Option, Question, QuestionDraft, QuestionError
from clank.kernel.settings import SettingsError

if TYPE_CHECKING:
    from clank.components.flows.runner import Runner

FLOW_DATA = {"flow": "The flow, <workspace>/<name>.", "run": "The run's number."}
EVENT_TYPES = [
    EventType(
        "flows.proposed",
        "A box of a running flow proposed a box for it (design 0013 §9): staged in its try's batch, waiting for you, "
        "or joined at once by auto-accept.",
        {
            **FLOW_DATA,
            "box": "The box that proposed it.",
            "try": "Its try.",
            "proposal": "The id the box takes in the flow.",
            "type": "Its type.",
            "after": "The box it comes after.",
            "state": "proposed (waiting for you) or accepted (by auto-accept).",
        },
    ),
    EventType(
        "flows.proposal_decided",
        "A box a model proposed was decided (design 0013 §9): accepted into the flow's file (as proposed, or edited), "
        "rejected, edited while it waits, or replaced when its box ran again.",
        {
            **FLOW_DATA,
            "box": "The box that proposed it.",
            "try": "Its try.",
            "proposal": "Its id.",
            "decision": "accepted, rejected, edited or replaced.",
            "edited": "Whether you changed it from what the model proposed.",
        },
    ),
]
NO_BOX = "only a box of a running flow proposes boxes, while it works"
IN_MODE = {  # a proposed box's own mode, said wherever you see it (in Auto it bypasses the workspace's review, §4)
    "plan": "in Plan",
    "review": "in Review",
    "auto": "in Auto: its changes are accepted without review",
}
AUTO_ACCEPT = Actor(kind="clank", via="auto-accept")  # who accepts a proposal by the flow's setting
Decision = Literal["accept", "reject"]
DECISIONS: tuple[Decision, ...] = ("accept", "reject")


class Proposing:
    """The proposals of every run's boxes."""

    def __init__(self, runner: "Runner") -> None:
        self.runner = runner
        self.kernel = runner.kernel
        self.batches = Batches(runner.runs)
        self._lock = threading.RLock()

    # What the box's model asks, through the gateway.

    def propose(self, workspace: str, given: Mapping[str, Any], *, actor: Actor) -> dict[str, Any]:
        """A box proposed by the model of the box at work in the workspace (design 0013 §9): checked, then staged in
        its try's batch; what was kept, said for the model. `RunError`, saying what to fix, when it cannot be."""
        with self._lock:
            run, flow, box, attempt = self._working(workspace, str(given.get("flow") or ""))
            try:
                after, made, why = read(given, flow)
            except ProposalRefused as error:
                raise RunError(str(error)) from error
            problem = self.runner.flows.preset_problem(made.model) if made.model else ""
            if problem:
                raise RunError(f"model {problem}")
            batch = self.batches.load(run, box.id, attempt.number) or Batch(
                flow=run.flow, run=run.number, box=box.id, attempt=attempt.number
            )
            taken = {each.id for each in flow.boxes}
            taken |= {each.id for found in self.batches.of_run(run) for each in found.proposals}
            id = next_id(made.type, taken | {each.id for each in batch.proposals})
            proposal = Proposal(
                id=id,
                number=len(batch.proposals) + 1,
                after=after,
                box=made.model_copy(update={"id": id}),
                why=why,
                given=self.kernel.clock.now(),
                by=actor,
            )
            batch.proposals.append(proposal)
            waiting = [each.id for each in batch.waiting()]
            wrong = refusals(joined(flow, batch, waiting, removing=self._replacing(run, flow, batch)))
            if wrong:
                raise RunError(f"{id} would break the flow's rules: {'; '.join(wrong)}")
            self.batches.save(batch)
            uncapped = flow.built is not None  # a built flow accepts every task proposed (design 0013 §15)
            if flow.auto_accept and (uncapped or self._auto_accepted(run) < flow.auto_accept_cap):
                self._auto_accept(run, batch, proposal)
        said = f"{box.title} proposed {id} ({made.title}) after {after}" + (
            f", {IN_MODE[made.mode]}" if made.mode else ""
        )
        self.runner._record_event(
            "flows.proposed", run, said, actor, box=box.id, proposal=id, type=made.type, after=after,
            state=proposal.state, **{"try": attempt.number},
        )  # fmt: skip
        if proposal.state == "accepted":
            self._decided(run, batch, proposal, "accepted", AUTO_ACCEPT)
            then = "it joined the flow at once: auto-accept is on for this flow"
        else:
            then = "it waits for the user"
        return {
            "flow": run.flow,
            "run": run.number,
            "box": box.id,
            "try": attempt.number,
            "proposal": id,
            "number": proposal.number,
            "state": proposal.state,
            "said": f"Proposed {id} ({made.title}) after {after}, number {proposal.number} of your proposals: {then}. "
            "Propose the next, or call flow_submit once every one is proposed.",
        }

    def _auto_accepted(self, run: Run) -> int:
        """How many proposals auto-accept joined to the flow in the run (its cap counts them)."""
        return sum(
            1
            for batch in self.batches.of_run(run)
            for each in batch.proposals
            if each.state == "accepted" and each.decided_by == AUTO_ACCEPT
        )

    def _auto_accept(self, run: Run, batch: Batch, proposal: Proposal) -> None:
        """A proposal that passed the checks joins the flow at once, by the flow's setting (§9); one the flow does
        not take after all waits for the owner, saying why."""
        try:
            self._join(run, batch, [proposal.id], AUTO_ACCEPT, "auto-accept")
        except RunError as error:
            proposal.said = f"auto-accept could not join it, so it waits for you: {error}"
        else:
            proposal.state, proposal.decided, proposal.decided_by = "accepted", self.kernel.clock.now(), AUTO_ACCEPT
        self.batches.save(batch)

    def read(self, workspace: str, named: str = "") -> dict[str, Any]:
        """What a box's model reads of its flow (`flow_read`, design 0013 §9): the flow of the box at work in the
        workspace, each box in the order they run with its state in the run and the boxes after it, and the run's
        proposals; with no box at work, the flow `named` (its last run's states), else the workspace's flows listed."""
        try:
            run, flow, box = self.runner._at_work(workspace, NO_BOX)
        except RunError:
            run = None
        if run is not None:
            name = run.flow.split("/", 1)[1]
            if named and named.strip().lower() not in (name.lower(), run.flow.lower(), (flow.title or "").lower()):
                raise RunError(f"{box.id} works in the flow {name}, not {named}: a box reads its own flow")
            return self._read(run.flow, flow, run, box.id)
        flows = [
            (loaded.id, loaded.record)
            for loaded in self.kernel.settings.records(Flow.KIND)
            if loaded.id.split("/", 1)[0] == workspace and isinstance(loaded.record, Flow)
        ]
        wanted = named.strip().lower()
        found = next(
            (each for each in flows if wanted and wanted in (each[0].split("/", 1)[1].lower(), each[1].title.lower())),
            None,
        )
        if found is not None:
            return self._read(found[0], found[1], self.runner.runs.latest(found[0]), "")
        if named:
            listed = ", ".join(id for id, _ in flows) or "none"
            raise RunError(f"{workspace} has no flow {named}: its flows are {listed}")
        return {
            "workspace": workspace,
            "flows": [{"flow": id, "title": each.title, "boxes": len(each.boxes)} for id, each in flows],
            "said": f"No box of a flow works in {workspace} now: name one of these flows (`flow`) to read it.",
        }

    def _read(self, id: str, flow: Flow, run: Run | None, you_are: str) -> dict[str, Any]:
        states = run.boxes if run is not None else {}
        boxes = []
        for name in order(flow):
            box = next(each for each in flow.boxes if each.id == name)
            state = states.get(name)
            item: dict[str, Any] = {
                "id": name, "type": box.type, "title": box.title, "state": state.state if state else "waiting",
                "tries": len(state.tries) if state else 0, "sees": box.sees, "writes": box.writes,
                "next": [line.to for line in flow.lines if line.from_ == name and line.when != "fail"],
            }  # fmt: skip
            fail = next((line.to for line in flow.lines if line.from_ == name and line.when == "fail"), "")
            item.update({"fail": fail} if fail else {})
            item.update({"checks": box.checks} if box.checks else {})
            item.update({"proposed_by": box.proposed.by} if box.proposed is not None else {})
            boxes.append(item)
        proposals = [
            {"id": each.id, "after": each.after, "type": each.box.type, "title": each.box.title, "state": each.state,
             "by": batch.box}
            for batch in (self.batches.of_run(run) if run is not None else [])
            for each in batch.proposals
        ]  # fmt: skip
        return {
            "flow": id,
            "title": flow.title,
            "run": run.number if run is not None else None,
            "you_are": you_are,
            "boxes": boxes,
            "proposals": proposals,
            "said": "This is read-only: you change the flow only by proposals, with flow_propose_box for each box "
            "(after a box of the flow), then flow_submit; the user accepts them.",
        }

    def submit(self, workspace: str, summary: str, *, actor: Actor, named: str = "") -> dict[str, Any]:
        """The proposals of the box at work are ready for the owner (design 0013 §9): one question asks about those
        still waiting; what was done, said for the model."""
        with self._lock:
            run, _, box, attempt = self._working(workspace, named)
            batch = self.batches.load(run, box.id, attempt.number)
            if batch is None or not batch.proposals:
                raise RunError("you have proposed no box: propose each with flow_propose_box first, then flow_submit")
            batch.summary, batch.submitted = summary.strip(), self.kernel.clock.now()
            waiting = [each.id for each in batch.waiting()]
            if waiting:
                self._ask(run, box, batch)
            self.batches.save(batch)
        count = f"{len(waiting)} proposal" + ("" if len(waiting) == 1 else "s")
        said = (
            f"Submitted {count} ({', '.join(waiting)}): they wait for the user, who accepts, edits or rejects each."
            if waiting
            else "Submitted: each of your proposals is decided already."
        )
        return {
            "flow": run.flow,
            "run": run.number,
            "box": box.id,
            "try": attempt.number,
            "waiting": waiting,
            "said": f"{said} Stop now: the flow goes on when your session ends.",
        }

    # What the owner decides.

    def decide(
        self,
        flow: str,
        decision: str,
        ids: Sequence[str] | None,
        *,
        actor: Actor,
        changes: Mapping[str, Any] | None = None,
        run: int = 0,
    ) -> dict[str, Any]:
        """Accept or reject proposals of the flow's run (its latest unless `run` names one), each by its id or every
        one still waiting (`ids` None); an acceptance of one proposal may edit it first (`changes`). Accepted boxes
        join the flow's file. `RunError`, saying why, when they cannot be decided as asked."""
        _owners(actor)
        if decision not in DECISIONS:
            raise RunError(f"a proposal is accepted or rejected, not {decision!r}")
        if changes and (decision != "accept" or ids is None or len(ids) != 1):
            raise RunError("an edit names one proposal, accepted with it")
        with self._lock:
            found = self._run(flow, run)
            chosen = self._chosen(found, ids)
            if changes:
                self._edit(found, *chosen[0], changes)
            decided = self._decide(found, chosen, decision, actor)
        return {
            "flow": flow,
            "run": found.number,
            "title": found.title,
            "decision": decision,
            "decided": decided,
            "said": f"{'Accepted' if decision == 'accept' else 'Rejected'} {', '.join(decided)}.",
        }

    def edit(self, flow: str, id: str, changes: Mapping[str, Any], *, actor: Actor, run: int = 0) -> dict[str, Any]:
        """Change a proposal still waiting, checked as a proposal is: it stays waiting. `RunError`, saying why, when it
        cannot be."""
        _owners(actor)
        with self._lock:
            found = self._run(flow, run)
            [(batch, proposal)] = self._chosen(found, [id])
            self._edit(found, batch, proposal, changes)
            self.batches.save(batch)
        self._decided(found, batch, proposal, "edited", actor)
        return {
            "flow": flow,
            "run": found.number,
            "proposal": proposal.model_dump(mode="json"),
            "said": f"Edited {id}: it waits for you to accept or reject it.",
        }

    def view(self, flow: str, run: int = 0) -> dict[str, Any]:
        """The proposals of the flow's run (its latest unless `run` names one): each batch whole, and those waiting."""
        try:
            found = self._run(flow, run)
        except RunError:
            record = self.runner._record(flow)
            title = (record[0].title if record is not None else "") or flow.split("/", 1)[-1]
            return {"flow": flow, "run": None, "title": title, "batches": [], "waiting": []}
        batches = self.batches.of_run(found)
        return {
            "flow": flow,
            "run": found.number,
            "title": found.title,
            "batches": [batch.model_dump(mode="json") for batch in batches],
            "waiting": [each.id for batch in batches for each in batch.waiting()],
        }

    # What the runner asks.

    def submitted(self, run: Run, box: str, attempt: int) -> bool:
        """Whether a try submitted its proposals (a DECOMPOSE is done only then, §2)."""
        batch = self.batches.load(run, box, attempt)
        return batch is not None and batch.submitted is not None and bool(batch.proposals)

    def pending(self, run: Run, box: str) -> bool:
        """Whether a box's last try has proposals still waiting for the owner."""
        batch = self.batches.last(run, box)
        return batch is not None and bool(batch.waiting())

    def hold(self, run: Run, box: Box) -> bool:
        """Hold the run at a finished box while its last try's proposals still wait (design 0013 §9): the question
        asked about them (again, for those staged since it was asked), and the run waiting for it; an answer given
        meanwhile taken first. False when none waits."""
        with self._lock:
            batch = self.batches.last(run, box.id)
            if batch is None:
                return False
            self._take_answer(run, batch)
            if not batch.waiting():
                return False
            question = self._standing(run, box, batch)
        self.runner._wait_for(run, Waiting(question=question, kind="proposals", box=box.id))
        return True

    def set_aside(self, run: Run, box: str, reason: str, *, before: int | None = None) -> None:
        """The proposals of a box's tries (before try `before`, or all) still waiting are set aside, *replaced*: its
        box runs again and proposes anew, or was skipped (§9); their question is withdrawn."""
        aside: list[tuple[Batch, Proposal]] = []
        with self._lock:
            for batch in self.batches.of_run(run):
                if batch.box != box or (before is not None and batch.attempt >= before) or not batch.waiting():
                    continue
                now = self.kernel.clock.now()
                for each in batch.waiting():
                    each.state, each.decided, each.decided_by, each.said = "replaced", now, RUNNER, reason
                    aside.append((batch, each))
                self.batches.save(batch)
                if batch.question:
                    self._withdraw(batch.question, reason, RUNNER)
        for batch, each in aside:
            self._decided(run, batch, each, "replaced", RUNNER)

    def ended(self, run: Run, reason: str, actor: Actor) -> None:
        """A run ended: the questions about its batches still waiting are withdrawn (it no longer waits for them);
        their proposals stay waiting, decided from the command line, joining the flow's file for its next run."""
        questions = [batch.question for batch in self.batches.of_run(run) if batch.question and batch.waiting()]
        for question in questions:
            self._withdraw(question, reason, actor)

    def answered(self, question: Question) -> None:
        """A question about a flow was answered: when it asks about a batch of an active run, its answer decides the
        proposals it asks about that still wait."""
        if question.status != "answered":
            return
        with self._lock:
            for run in self.runner.runs.all():
                if run.status not in ACTIVE:
                    continue
                for batch in self.batches.of_run(run):
                    if batch.question == question.id:
                        self._take_answer(run, batch)

    # Inside.

    def _working(self, workspace: str, named: str) -> tuple[Run, Flow, Box, Try]:
        """The run, flow and box at work in the workspace, and the box's try while it runs; `RunError`, saying why,
        when none is, or when `named` is not that box's flow."""
        run, flow, box = self.runner._at_work(workspace, NO_BOX)
        name = run.flow.split("/", 1)[1]
        if named and named.strip().lower() not in (name.lower(), run.flow.lower(), (flow.title or "").lower()):
            raise RunError(f"{box.id} works in the flow {name}, not {named}: a box proposes boxes for its own flow")
        state = run.boxes.get(box.id)
        last = state.tries[-1] if state is not None and state.tries else None
        if last is None or last.sent is None or last.outcome is not None:
            raise RunError(f"{box.id}'s try has not begun, or has ended: nothing is proposed for it")
        return run, flow, box, last

    def _run(self, flow: str, number: int) -> Run:
        try:
            found = self.runner.runs.load(flow, number) if number else self.runner.runs.latest(flow)
        except (OSError, ValueError) as error:
            raise RunError(f"{flow} has no run {number}") from error
        if found is None:
            raise RunError(f"{flow} has not run yet: it has no proposals")
        return found

    def _chosen(self, run: Run, ids: Sequence[str] | None) -> list[tuple[Batch, Proposal]]:
        """The proposals still waiting that `ids` names (every one, for None), by batch and number."""
        waiting = [(batch, each) for batch in self.batches.of_run(run) for each in batch.waiting()]
        if ids is None:
            if not waiting:
                raise RunError(f"no proposal of {run.title}'s run {run.number} waits for you")
            return waiting
        known = {each.id: (batch, each) for batch, each in waiting}
        for id in ids:
            if id not in known:
                listed = ", ".join(known)
                then = f"{listed} wait{'s' if len(known) == 1 else ''}" if known else "none waits"
                raise RunError(f"{id} is no proposal of {run.title}'s run {run.number} that waits for you: {then}")
        wanted = set(ids)
        return [(batch, each) for batch, each in waiting if each.id in wanted]

    def _edit(self, run: Run, batch: Batch, proposal: Proposal, changes: Mapping[str, Any]) -> None:
        """The owner's changes to a proposal, checked as a proposal is; the model's own kept as `original`."""
        try:
            box = edited(proposal.box, changes)
        except ProposalRefused as error:
            raise RunError(str(error)) from error
        problem = self.runner.flows.preset_problem(box.model) if box.model else ""
        if problem:
            raise RunError(f"model {problem}")
        record = self.runner._record(batch.flow)
        if record is None:
            raise RunError(f"{batch.flow} is gone")
        before = proposal.box
        proposal.box = box
        waiting = [each.id for each in batch.waiting()]
        wrong = refusals(joined(record[0], batch, waiting, removing=self._replacing(run, record[0], batch)))
        if wrong:
            proposal.box = before
            raise RunError(f"{proposal.id}, edited, would break the flow's rules: {'; '.join(wrong)}")
        if proposal.original is None:
            proposal.original = before

    def _decide(
        self,
        run: Run,
        chosen: list[tuple[Batch, Proposal]],
        decision: Decision,
        actor: Actor,
        accepted: Literal["owner", "auto-accept"] = "owner",
    ) -> list[str]:
        """Decide proposals, batch by batch: accepted ones join the flow's file first, all of a batch in one write; then
        each is marked, its batch kept, and a question that asks about none still waiting withdrawn."""
        batches: dict[tuple[str, int], tuple[Batch, list[Proposal]]] = {}
        for batch, each in chosen:
            batches.setdefault((batch.box, batch.attempt), (batch, []))[1].append(each)
        decided: list[tuple[Batch, Proposal]] = []
        for batch, proposals in batches.values():
            if decision == "accept":
                self._join(run, batch, [each.id for each in proposals], actor, accepted)
            now = self.kernel.clock.now()
            for each in proposals:
                each.state = "accepted" if decision == "accept" else "rejected"
                each.decided, each.decided_by, each.said = now, actor, ""
                decided.append((batch, each))
            self.batches.save(batch)
        for batch, _ in batches.values():
            asked = set(batch.asked)
            if batch.question and not any(each.id in asked for each in batch.waiting()):
                self._withdraw(batch.question, f"{actor.describe()} decided each proposal it asks about", actor)
        for batch, each in decided:
            self._decided(run, batch, each, "accepted" if decision == "accept" else "rejected", actor)
        return [each.id for _, each in decided]

    def _join(
        self, run: Run, batch: Batch, ids: list[str], actor: Actor, accepted: Literal["owner", "auto-accept"]
    ) -> None:
        """Proposals of a batch into the flow's file, written through the settings as any change is, based on the
        version read here; the boxes the batch replaces taken out with the first to join."""
        record = self.runner._record(batch.flow)
        if record is None:
            raise RunError(f"{batch.flow} is gone: its proposals cannot join it")
        flow, revision = record
        removing = self._replacing(run, flow, batch)
        values = joined(flow, batch, ids, accepted=accepted, removing=removing)
        wrong = refusals(values)
        if wrong:
            raise RunError(f"{', '.join(ids)} cannot join the flow as it is now: {'; '.join(wrong)}")
        try:
            self.kernel.settings.write(Flow.KIND, batch.flow, values, base=revision, actor=actor)
        except SettingsError as error:
            raise RunError(f"{', '.join(ids)} cannot join the flow: {error}") from error
        if batch.replaced is None:
            batch.replaced = removing

    def _replacing(self, run: Run, flow: Flow, batch: Batch) -> list[str]:
        """The boxes the first of the batch's proposals to join takes out of the flow (§9: a box run again proposes
        anew): those its box added before that have not started in the run; none once one joined."""
        if batch.replaced is not None:
            return []
        return [
            each.id
            for each in flow.boxes
            if each.proposed is not None
            and each.proposed.by == batch.box
            and batch.find(each.id) is None
            and not (run.boxes[each.id].tries if each.id in run.boxes else [])
        ]

    def _take_answer(self, run: Run, batch: Batch) -> None:
        """The answer to the batch's question, if it was answered: it decides the proposals it asks about that still
        wait (accept all, or reject all)."""
        if not batch.question:
            return
        try:
            asked = self.kernel.questions.get(batch.question)
        except QuestionError:
            return
        option = asked.answer.option if asked.status == "answered" and asked.answer is not None else None
        if asked.answer is None or option not in DECISIONS:
            return
        listed = set(batch.asked)
        chosen = [(batch, each) for each in batch.waiting() if each.id in listed]
        if not chosen:
            return
        try:
            self._decide(run, chosen, option, asked.answer.by)
        except RunError as error:  # the flow no longer takes them: they wait, saying why, and are asked about again
            for _, each in chosen:
                each.said = str(error)
            batch.question, batch.asked = "", []
            self.batches.save(batch)

    def _standing(self, run: Run, box: Box, batch: Batch) -> str:
        """The question that asks about every proposal of the batch still waiting: the one asked, else a new one."""
        waiting = {each.id for each in batch.waiting()}
        if batch.question:
            try:
                asked = self.kernel.questions.get(batch.question)
            except QuestionError:
                asked = None
            if asked is not None and asked.status == "waiting" and waiting <= set(batch.asked):
                return batch.question
        self._ask(run, box, batch)
        self.batches.save(batch)
        return batch.question

    def _ask(self, run: Run, box: Box, batch: Batch) -> None:
        """Ask the owner about the batch's proposals still waiting (the one asked before withdrawn)."""
        if batch.question:
            self._withdraw(batch.question, "asked again with the proposals staged since", RUNNER)
        waiting = batch.waiting()
        count = f"{len(waiting)} box" + ("" if len(waiting) == 1 else "es")
        lines = [batch.summary, ""] if batch.summary else []
        for each in waiting:
            said = [f"{each.number} · {each.box.type.upper()} {each.id} · {each.box.title}"]
            said += [f"writes {', '.join(each.box.writes)}"] if each.box.writes else []
            said += [f"on {each.box.model}"] if each.box.model else []
            said += [IN_MODE[each.box.mode]] if each.box.mode else []
            lines.append(" · ".join(said))
            lines += [f"   why: {each.why}"] if each.why else []
            lines += [f"   {each.said}"] if each.said else []  # why it could not join when accepted
        lines += [
            "",
            "Decide each with `clank flow accept` or `clank flow reject` (`clank flow proposals --full` shows each "
            "whole, and `clank flow accept --prompt` edits one first), or all of them here.",
        ]
        draft = QuestionDraft(
            type="choice",
            title=f"{run.title}: {box.title} proposed {count}",
            detail="\n".join(lines),
            options=[
                Option(
                    id="accept",
                    label="Accept all",
                    effect=f"Each joins the flow after {_afters(waiting)}, in this order; they run one at a time.",
                    key="a",
                ),
                Option(
                    id="reject", label="Reject all", effect="None joins the flow; it goes on without them.", key="r"
                ),
            ],
            about=Subject(kind="flow", id=run.flow),
        )
        asked = self.kernel.questions.ask(draft, asked_by=RUNNER)
        batch.question, batch.asked = asked.id, [each.id for each in waiting]

    def _withdraw(self, question: str, reason: str, actor: Actor) -> None:
        with contextlib.suppress(QuestionError):  # answered or withdrawn meanwhile
            self.kernel.questions.withdraw(question, reason=reason, by=actor)

    def _decided(self, run: Run, batch: Batch, proposal: Proposal, decision: str, actor: Actor) -> None:
        was = proposal.original is not None and proposal.original != proposal.box.model_copy(
            update={"id": proposal.original.id}
        )
        proposer = self.runner._record(batch.flow)
        by = next((box.title for box in proposer[0].boxes if box.id == batch.box), batch.box) if proposer else batch.box
        summary = f"{actor.describe()} {decision} {proposal.id} ({proposal.box.title})"
        summary += (", edited" if was else "") + f", proposed by {by}"
        self.runner._record_event(
            "flows.proposal_decided", run, summary, actor, box=batch.box, proposal=proposal.id, decision=decision,
            edited=was, **{"try": batch.attempt},
        )  # fmt: skip


def _owners(actor: Actor) -> None:
    """Only the owner decides proposals: the agent's session never does (decision 0020)."""
    if actor.kind == "session":
        raise RunError("the agent proposes boxes; only the user decides them")


def _afters(waiting: list[Proposal]) -> str:
    named = sorted({each.after for each in waiting})
    return ", ".join(named)
