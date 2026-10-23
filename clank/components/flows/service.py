"""The flows component's part (design 0013 §6, §11): the flows, read from their files and checked.

A flow is a settings record kept by workspace (`config/flows/<workspace>/<name>.json`, decision 0066), read by the
kernel's settings files like any other, its own rules its kind's (`clank.components.flows.rules`). What needs other
records is checked here: each preset a flow names exists and is for the main slot, every box's (design 0013 §7), named
by its id or its title as presets are everywhere; and a flow is for the workspace whose folder keeps it, one Clank
knows. The settings files run that check too (`check_with`), so a flow that fails it is refused when saved, by any
client, and reported when its file is read, the last good flow staying in force (design 0013 §14, step 1). `check`
reads a file as it is on disk now, so a file edited a moment ago is checked before the service reads it again; it checks
a saved flow by its id, or any file on this machine (a draft) by its path. Clank's template, the shape a new flow starts
from, is `clank/defaults/templates/flow.json`. A flow's view and its check say the switches of the main slot a run of it
makes from what the slot runs now (`switches`, design 0013 §7, decision 0063: their cost shown before it runs), each
with how long its preset's last whole switch took here (its engine's last start, when no switch of it is kept).

A flow built with the model (design 0013 §15) is `building.py`'s: `new` opens a planning (the owner's only), `draft`
takes its model's drafts (`flow_draft`, through the gateway), `being_built` shows one, and the view follows a flow built
and not run yet as of when it was built, with its last draft's warnings (`_built`).
"""

import hashlib
import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any

from clank.components.flows import preparing
from clank.components.flows.building import EVENT_TYPES as BUILDING_EVENTS
from clank.components.flows.building import BuildError, Building, Planning, Where, session_title
from clank.components.flows.following import EVENT_TYPES as NEXT_EVENTS
from clank.components.flows.following import Following, NextError
from clank.components.flows.kinds import Flow
from clank.components.flows.models import switches
from clank.components.flows.proposing import EVENT_TYPES as PROPOSAL_EVENTS
from clank.components.flows.runner import ACTIVE, RunError, Runner
from clank.components.flows.runner import EVENT_TYPES as RUNNER_EVENTS
from clank.components.flows.runs import Run, order
from clank.components.flows.view import view
from clank.components.flows.waiting import shown
from clank.kernel.api import ApiError
from clank.kernel.clock import to_text
from clank.kernel.events import Actor, Subject
from clank.kernel.questions import QuestionError
from clank.kernel.records import Settings
from clank.kernel.settings import DEFAULTS, Loaded, SettingsError, SettingsProblem, line_of, read_record

if TYPE_CHECKING:
    from clank.components.gateway.service import Gateway
    from clank.components.runtime.service import Runtime
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel
    from clank.kernel.operations import OperationType
    from clank.kernel.questions import Question

TEMPLATE = DEFAULTS / "templates" / "flow.json"
SLOT = "main"  # every box's requests reach the main slot (design 0013 §7)
WHOLE = ("runtime.switch", "runtime.load")  # what brings a preset into a slot, from its start to its end
LOOKED = 200  # how many of the newest operations, and of the newest launches, say how long a preset took
EVENT_TYPES = [*RUNNER_EVENTS, *PROPOSAL_EVENTS, *NEXT_EVENTS, *BUILDING_EVENTS]  # the component declares them
Place = tuple[str | int, ...]


class Flows:
    """The flows component, built on the kernel."""

    def __init__(self, kernel: "Kernel") -> None:
        self.kernel = kernel
        kernel.settings.check_with(Flow.KIND, self._saved)
        self.runner = Runner(kernel, self)
        self.following = Following(kernel, self)  # the next flows, made as the runner's runs end (decision 0091)
        self.building = Building(kernel, self)  # flows built with the model (design 0013 §15)
        self._took: dict[str, tuple[float, bool]] | None = None  # how long each preset last took to come in, kept
        kernel.events.subscribe(self._heard)

    def _heard(self, event: Any) -> None:
        """An operation finished (a switch, a load among them): how long each preset took is read again when asked."""
        if event.type == "operation.finished":
            self._took = None

    def operation_types(self) -> list["OperationType"]:
        """`flows.box`: a model box's try (design 0013 §6)."""
        return self.runner.operation_types()

    async def run(self) -> None:
        """While the service runs: the runner drives the flows' runs."""
        await self.runner.run()

    @property
    def folder(self) -> Path:
        """Where flows are kept: `config/flows/`, a folder for each workspace."""
        return self.kernel.home.config / Flow.folder()

    def flows(self, workspace: str = "", folder: str = "") -> dict[str, Any]:
        """Every flow (of one workspace, when given), each with its boxes and what is wrong with its file now; the files
        that do not read and stand for no flow; where flows are kept and the template; and the workspace of `folder`."""
        presets = self._presets()
        records = self.kernel.settings.records(Flow.KIND)
        kept = {loaded.path for loaded in records}
        unreadable = [
            _problem(problem)
            for problem in self.kernel.settings.problems()
            if problem.path not in kept
            and self.folder in problem.path.parents
            and (not workspace or problem.path.parent.name == workspace)
        ]
        return {
            "folder": str(self.folder),
            "template": str(TEMPLATE),
            "workspace": self.workspace_of(folder) if folder else None,
            "flows": [
                self._view(loaded, presets)
                for loaded in records
                if not workspace or loaded.id.split("/", 1)[0] == workspace
            ],
            "unreadable": unreadable,
        }

    def flow(self, workspace: str, name: str) -> dict[str, Any]:
        """One flow, by its name in its workspace or its title: its values as in force, and what is wrong with its
        file now."""
        loaded = self._find(workspace, name)
        assert isinstance(loaded.record, Flow)
        values = loaded.record.model_dump(mode="json")
        found = {**self._view(loaded, self._presets()), "values": values, **self.switches(loaded.record)}
        return {**found, "cost": self.cost(loaded.id)}

    def cost(self, flow: str) -> dict[str, Any] | None:
        """What the flow's latest run cost in the cloud (design 0016 §11): each box's sessions' cost, and the total;
        None when none of its sessions used the cloud."""
        run = self.runner.runs.latest(flow)
        if run is None:
            return None
        boxes = {name: [each.session for each in box.tries if each.session] for name, box in run.boxes.items()}
        gateway: Gateway = self.kernel.parts["gateway"]
        return gateway.cost_for({name: sessions for name, sessions in boxes.items() if sessions})

    def check(self, flow: str = "", file: str = "") -> dict[str, Any]:
        """Check a flow's file as it is on disk now: a saved flow by its id (`<workspace>/<name>`), or a file by its
        path; every problem with its file, line and field."""
        if file:
            path, id = Path(file), None
            if not path.is_file():
                raise ApiError(404, "not_found", f"there is no file {file}")
        else:
            workspace, slash, name = flow.partition("/")
            if not slash:
                raise ApiError(400, "invalid", f"name a flow by its workspace and its name, as in myproject/{flow}")
            loaded = self._find(workspace, name)
            path, id = loaded.path or loaded.user_file, loaded.id
        problems = self._problems(path, self._presets())
        warned = self._warnings(path, id) if not problems else []
        found = None if problems else read_record(Flow, path)
        made = found[0] if found is not None and not isinstance(found, list) else None
        planned = self.switches(made) if isinstance(made, Flow) else {}
        return {
            "file": str(path), "flow": id, "problems": [_problem(p) for p in problems], "warnings": warned, **planned,
        }  # fmt: skip

    def _warnings(self, path: Path, id: str | None) -> list[dict[str, Any]]:
        """What the check of a flow that keeps every rule warns of (decision 0087): each box's first message as it
        would be sent now past a quarter of its window, and a file a box sees or shows that nothing gives it; none when
        its workspace's folder is not known."""
        from clank.components.workspaces.service import WorkspaceUnavailable

        found = read_record(Flow, path)
        if isinstance(found, list):
            return []
        record, _, raw = found
        assert isinstance(record, Flow)
        kept_in = path.parent.name if path.parent.parent == self.folder else ""
        workspace = id.split("/", 1)[0] if id else record.workspace or kept_in
        if not workspace:
            return []
        try:
            folder = Path(self.kernel.parts["workspaces"].folder_of(workspace))
        except WorkspaceUnavailable:
            return []
        flow = id or f"{workspace}/{path.stem}"
        latest = self.runner.runs.latest(flow) if id else None
        run = latest if latest is not None and latest.status in ACTIVE else None
        shown = preparing.preview(self.runner.runs, run, flow, record, folder, self.kernel.parts["runtime"])
        text = raw.decode("utf-8-sig")
        return [
            _problem(SettingsProblem(path, line_of(text, place), ".".join(map(str, place)), message))
            for place, message in preparing.warnings(shown, record, folder)
        ]

    def switches(self, flow: Flow) -> dict[str, Any]:
        """The switches of the main slot a run of the flow makes (design 0013 §7, decision 0063: shown before it runs),
        from what the slot runs now (`running`, its preset's id, "" for none, and `running_title`): each before a box,
        to its preset, with how long that preset last took to come in here (`seconds`): its last whole switch or load
        into the slot, from the operation's start to its end (`whole`), else, when no such operation is among the
        newest, its engine's last start to ready (`whole` false); None when it never loaded here."""
        runtime: Runtime = self.kernel.parts["runtime"]
        slot = runtime.state.slot(SLOT)
        running = slot.preset if slot.status == "ready" and slot.preset else ""
        presets = self._presets()
        titles = {str(preset["id"]): str(preset["title"]) for preset in presets}

        def resolve(name: str) -> str:
            wanted = name.strip().lower()
            found = next((each for each in presets if wanted in (each["id"].lower(), str(each["title"]).lower())), None)
            return str(found["id"]) if found is not None else name

        took = self._took
        if took is None:  # read once, and again only after an operation finished (the Flow view asks every second)
            took = {}
            for operation in self.kernel.operations.find("done", limit=LOOKED):  # the newest first
                if operation.type in WHOLE and str(operation.params.get("slot") or SLOT) == SLOT:
                    ended = operation.finished or operation.updated
                    whole = round((ended - operation.created).total_seconds(), 1)
                    took.setdefault(resolve(str(operation.params.get("preset") or "")), (whole, True))
            for launch in runtime.state.launches(limit=LOOKED):  # the newest first
                if launch.slot == SLOT and launch.seconds is not None:
                    took.setdefault(launch.preset, (launch.seconds, False))
            self._took = took
        planned = []
        for box, preset in switches(flow, running, resolve):
            seconds, whole = took.get(preset, (None, False))
            planned.append({"box": box, "preset": preset, "title": titles.get(preset, preset), "seconds": seconds,
                            "whole": whole})  # fmt: skip
        return {"running": running, "running_title": titles.get(running, running), "switches": planned}

    def go(self, workspace: str, name: str, *, actor: Actor, start_from: str = "") -> dict[str, Any]:
        """Run a flow (design 0013 §6): its latest run again from a box (`start_from`), its paused run resumed, or a
        new run, queued behind another flow's when one is active; what was done, the run, and the order of its boxes."""
        flow = self._find(workspace, name).id
        try:
            if start_from:
                run, did = self.runner.run_from(flow, start_from, actor=actor), "from"
            else:
                latest = self.runner.runs.latest(flow)
                if latest is not None and latest.status in ACTIVE and latest.paused:
                    run, did = self.runner.resume(flow, actor=actor), "resumed"
                else:
                    run = self.runner.start(flow, actor=actor)
                    did = "queued" if run.status == "queued" else "started"
        except RunError as error:
            raise ApiError(409, "refused", str(error)) from error
        return {"did": did, **self._run_view(flow, run)}

    def pause(self, workspace: str, name: str, *, actor: Actor) -> dict[str, Any]:
        """Pause a flow's run: no box starts; the running one goes on."""
        flow = self._find(workspace, name).id
        try:
            return self._run_view(flow, self.runner.pause(flow, actor=actor))
        except RunError as error:
            raise ApiError(409, "refused", str(error)) from error

    def stop(self, workspace: str, name: str, *, actor: Actor) -> dict[str, Any]:
        """Stop a flow's run: its running box's session is stopped, and the run ends."""
        flow = self._find(workspace, name).id
        try:
            return self._run_view(flow, self.runner.stop(flow, actor=actor))
        except RunError as error:
            raise ApiError(409, "refused", str(error)) from error

    def verdict(
        self, workspace: str, result: str, findings: list[str], criteria: list[Any], *, actor: Actor
    ) -> dict[str, Any]:
        """A VERIFY's verdict (design 0013 §9), given to the VERIFY box at work in the workspace: what was kept, said
        for the model; `409 refused`, saying why, when it cannot be."""
        try:
            return self.runner.verdict(workspace, result, findings, criteria, actor=actor)
        except RunError as error:
            raise ApiError(409, "refused", str(error)) from error

    def orchestrator(
        self,
        workspace: str,
        name: str,
        *,
        actor: Actor,
        on: bool | None = None,
        final_review: str = "",
        model: str | None = None,
        role: str = "",
    ) -> dict[str, Any]:
        """A flow's orchestrator (design 0013 §16): turned on or off, its role, its final review or its model changed
        (a role given turns it on), written through the settings as any edit; then its settings, the checkpoint at
        work and the ledger of the flow's latest run. `409 refused`, saying why, when the change breaks a rule."""
        from clank.components.flows import orchestrating
        from clank.kernel.settings import SettingsError

        found = self._find(workspace, name)
        record = self.runner._record(found.id)
        if record is None:
            raise ApiError(404, "not_found", f"there is no flow {found.id}")
        made, revision = record
        if on is not None or final_review or model is not None or role:
            values = made.model_dump(mode="json")
            steering = dict(values.get("orchestrator") or {})
            if role:
                steering["role"] = role
                steering["on"] = True
            if on is not None:
                steering["on"] = on
            if final_review:
                steering["final_review"] = final_review
            if model is not None:
                steering["model"] = model
            values["orchestrator"] = steering
            try:
                self.kernel.settings.write(Flow.KIND, found.id, values, base=revision, actor=actor)
            except SettingsError as error:
                raise ApiError(409, "refused", str(error)) from error
            record = self.runner._record(found.id)
            assert record is not None
            made = record[0]
        latest = self.runner.runs.latest(found.id)
        state = latest.orchestration if latest is not None else None
        return {
            "flow": found.id,
            "title": made.title,
            "orchestrator": made.orchestrator.model_dump(mode="json"),
            "run": latest.number if latest is not None else None,
            "working": state.working.model_dump(mode="json") if state is not None and state.working else None,
            "changes": state.changes if state is not None else 0,
            "stall": state.stall if state is not None else 0,
            "owner": state.owner if state is not None else "",
            "ledger": orchestrating.ledger_text(latest) if latest is not None else "",
        }

    def job(self, workspace: str, command: str, title: str, minutes: int, *, actor: Actor) -> dict[str, Any]:
        """A job started by the box at work in the workspace (design 0013 §17): what was started, said for the model;
        `409 refused`, saying why, when it cannot be."""
        return _refused_as_409(lambda: self.runner.job(workspace, command, title, minutes, actor=actor))

    def steer(self, workspace: str, given: dict[str, Any], *, actor: Actor) -> dict[str, Any]:
        """A checkpoint's decision (design 0013 §16), given to the orchestrator's checkpoint at work in the workspace:
        what was kept, said for the model; `409 refused`, saying why, when it cannot be."""
        try:
            return self.runner.decide(workspace, given, actor=actor)
        except RunError as error:
            raise ApiError(409, "refused", str(error)) from error

    def read(self, workspace: str, flow: str = "") -> dict[str, Any]:
        """What a box's model reads of its flow (`flow_read`, design 0013 §9); `409 refused`, saying why."""
        return _refused_as_409(lambda: self.runner.proposing.read(workspace, flow))

    def propose(self, workspace: str, given: dict[str, Any], *, actor: Actor) -> dict[str, Any]:
        """A box proposed by the model of the box at work in the workspace (design 0013 §9): staged, or refused (409)
        saying what to fix."""
        return _refused_as_409(lambda: self.runner.proposing.propose(workspace, given, actor=actor))

    def submit(self, workspace: str, summary: str, *, actor: Actor, flow: str = "") -> dict[str, Any]:
        """The proposals of the box at work are ready for the owner: one question asks about them."""
        return _refused_as_409(lambda: self.runner.proposing.submit(workspace, summary, actor=actor, named=flow))

    def new(
        self, workspace: str, folder: str, name: str, where: str, *, actor: Actor, aside: bool = False
    ) -> dict[str, Any]:
        """Open a planning, a flow built with the model (design 0013 §15), in the workspace named or the one of
        `folder`, the planning open there set aside only with `aside`: the user's only (403 for the agent); `409
        refused`, saying why, when it cannot be."""
        _the_owners(actor)
        named = workspace or (self.workspace_of(folder) if folder else None)
        if not named:
            raise ApiError(409, "refused", "this folder has no workspace: This folder (F4) opens one")
        if where not in ("here", "vscode", "attach"):
            raise ApiError(400, "invalid", f"a planning opens here, in vscode, or for attach, not {where!r}")
        chosen: Where = "vscode" if where == "vscode" else "attach" if where == "attach" else "here"
        try:
            return self.building.open(named, name, chosen, actor=actor, aside=aside)
        except BuildError as error:
            raise ApiError(409, "refused", str(error)) from error

    def attach(self, workspace: str, folder: str, *, actor: Actor) -> dict[str, Any]:
        """`clank flow attach` (design 0013 §15): OpenCode's window for the planning open in the workspace (named, or of
        `folder`), its command for the asking terminal; the user's only (403 for the agent); `409 refused`, saying
        why (none open, an older sandbox image)."""
        _the_owners(actor)
        named = workspace or (self.workspace_of(folder) if folder else None)
        if not named:
            raise ApiError(409, "refused", "this folder has no workspace: This folder (F4) opens one")
        try:
            return self.building.attach(named, actor=actor)
        except BuildError as error:
            raise ApiError(409, "refused", str(error)) from error

    def being_built(self, workspace: str = "", folder: str = "", flow: str = "") -> dict[str, Any]:
        """A planning as the clients show it (design 0013 §15): the flow's, else the one open in the workspace (named,
        or of `folder`), else its newest; None and why when there is none."""
        named = flow.split("/", 1)[0] if flow else (workspace or (self.workspace_of(folder) if folder else None))
        if not named:
            return {"planning": None, "why": "this folder has no workspace: This folder (F4) opens one"}
        return self.building.view(named, flow)

    def draft(self, workspace: str, given: Any, *, actor: Actor) -> dict[str, Any]:
        """The model's draft of the flow the planning open in the workspace builds (design 0013 §15): written, said
        for the model; `409 refused`, in its words, when it cannot be (each problem with its field)."""
        try:
            return self.building.draft(workspace, given, actor=actor)
        except BuildError as error:
            raise ApiError(409, "refused", str(error)) from error

    def proposals(self, workspace: str, name: str, run: int = 0) -> dict[str, Any]:
        """The proposals of a flow's run (its latest unless `run` names one): each batch whole, and those waiting."""
        return self.runner.proposing.view(self._find(workspace, name).id, run)

    def decide(
        self,
        workspace: str,
        name: str,
        decision: str,
        proposals: list[str],
        *,
        every: bool,
        actor: Actor,
        changes: dict[str, Any] | None = None,
        run: int = 0,
    ) -> dict[str, Any]:
        """Accept or reject proposals of a flow's run, by their ids or all (`every`), an acceptance of one with an edit
        (`changes`): the owner's only (403 for the agent); `409 refused`, saying why, when they cannot be decided."""
        _the_owners(actor)
        if not proposals and not every:
            raise ApiError(400, "invalid", f"name the proposals to {decision}, or all of them (all: true)")
        flow = self._find(workspace, name).id
        ids = None if every else proposals
        return _refused_as_409(
            lambda: self.runner.proposing.decide(flow, decision, ids, actor=actor, changes=changes, run=run)
        )

    def edit(
        self, workspace: str, name: str, proposal: str, changes: dict[str, Any], *, actor: Actor, run: int = 0
    ) -> dict[str, Any]:
        """Change a proposal still waiting, checked as a proposal is: the owner's only (403 for the agent)."""
        _the_owners(actor)
        flow = self._find(workspace, name).id
        return _refused_as_409(lambda: self.runner.proposing.edit(flow, proposal, changes, actor=actor, run=run))

    def diff(
        self,
        workspace: str,
        name: str,
        box: str,
        *,
        path: str = "",
        a: int | None = None,
        b: int | None = None,
        run: int = 0,
    ) -> dict[str, Any]:
        """Two tries of a box compared (design 0013 §8): the unified diff of a deliverable's copies, and how many lines
        changed; `409 refused`, saying why, when they cannot be."""
        flow = self._find(workspace, name).id
        try:
            return self.runner.diff(flow, box, path=path, a=a, b=b, number=run)
        except RunError as error:
            raise ApiError(409, "refused", str(error)) from error

    def prepare(self, workspace: str, name: str, box: str = "") -> dict[str, Any]:
        """Each box a model runs (or `box` alone), its first message as it would be sent now, from the files as they
        are now and the active run's state, with its size against its preset's window (design 0013 §5, decision
        0087); `404 not_found` for a box the flow has not, `409 refused` for an owner's box or a folder not there."""
        from clank.components.workspaces.service import WorkspaceUnavailable

        loaded = self._find(workspace, name)
        assert isinstance(loaded.record, Flow)
        try:
            folder = Path(self.kernel.parts["workspaces"].folder_of(loaded.id.split("/", 1)[0]))
        except WorkspaceUnavailable as error:
            raise ApiError(409, "refused", str(error)) from error
        latest = self.runner.runs.latest(loaded.id)
        run = latest if latest is not None and latest.status in ACTIVE else None
        runtime = self.kernel.parts["runtime"]
        try:
            return preparing.preview(self.runner.runs, run, loaded.id, loaded.record, folder, runtime, only=box)
        except preparing.PrepareError as error:
            status, code = (404, "not_found") if error.missing else (409, "refused")
            raise ApiError(status, code, str(error)) from error

    def next(self, workspace: str, name: str) -> dict[str, Any]:
        """A flow's next flow (design 0013 §3, decision 0091): its id, title and brief, and whether it ran; else why
        there is none."""
        return self.following.view(self._find(workspace, name).id)

    def make_next(self, workspace: str, name: str, *, actor: Actor, run: bool = False) -> dict[str, Any]:
        """Make a flow's next flow when it has none (from its latest run's INTEGRATE), and with `run` start it; `409
        refused`, saying why, when it cannot be."""
        from clank.components.workspaces.service import WorkspaceUnavailable

        flow = self._find(workspace, name).id
        try:
            return self.following.make(flow, actor=actor, run=run)
        except (NextError, RunError, SettingsError, WorkspaceUnavailable) as error:
            raise ApiError(409, "refused", str(error)) from error

    def view(self, folder: str, flow: str = "") -> dict[str, Any]:
        """What the Monitor's Flow view shows (design 0013 §12, `view.py`): of the flow named (`<workspace>/<name>`),
        else the one a folder's Monitor follows: its workspace's flow whose run is active, else the one run last, else
        the first by name; with none, why (`flow` None, `why`). A flow named without its workspace is `400 invalid`,
        one the workspace has not `404 not_found`."""
        if flow and "/" not in flow.strip("/"):
            raise ApiError(400, "invalid", f"name a flow by its workspace and its name, as in myproject/{flow}")
        workspace = flow.split("/", 1)[0] if flow else (self.workspace_of(folder) if folder else None)
        if not workspace:
            return {"flow": None, "why": "this folder has no workspace: This folder (F4) opens one"}
        watched = self.building.watched(workspace) if not flow else None
        if watched is not None:  # the owner builds a flow with the model: shown as it is built (decision 0101)
            return self._planning_view(watched, workspace)
        records = [
            loaded for loaded in self.kernel.settings.records(Flow.KIND) if loaded.id.split("/", 1)[0] == workspace
        ]
        if flow:
            loaded = self._find(workspace, flow.split("/", 1)[1])
        elif not records:
            where = self.folder / workspace
            return {
                "flow": None,
                "why": f"{workspace} has no flow yet: a flow is a file in {where}, made from {TEMPLATE}",
            }
        else:
            loaded = _followed(records, {each.id: self.runner.runs.latest(each.id) for each in records})
        made = loaded.record
        assert isinstance(made, Flow)
        run = self.runner.runs.latest(loaded.id)
        batches = self.runner.proposing.batches.of_run(run) if run is not None else []
        from clank.components.workspaces.service import WorkspaceUnavailable

        try:
            place: Path | None = Path(self.kernel.parts["workspaces"].folder_of(workspace))
        except WorkspaceUnavailable:  # a workspace gone meanwhile: nothing of its folder is shown
            place = None
        runtime = self.kernel.parts["runtime"]
        slot = runtime.state.slot(SLOT)
        running = slot.preset if slot.status == "ready" and slot.preset else ""
        titles = {str(preset["id"]): str(preset["title"]) for preset in self._presets()}
        first = made.boxes[0]
        brief = _text_of(place, first.writes[0]) if place is not None and first.type == "you" and first.writes else ""
        ended: dict[str, tuple[Any, str]] = {}
        if run is not None:
            for event in self.kernel.events.latest(
                500, types=["flows.box_ended"], subject=Subject(kind="flow", id=loaded.id)
            ):
                box = str(event.data.get("box") or "")
                if event.data.get("run") == run.number and box and box not in ended:
                    ended[box] = (event.time, event.actor.describe())
        took = {str(each["preset"]): each["seconds"] for each in self.switches(made)["switches"]}
        following = next((each for each in self.kernel.settings.records(Flow.KIND) if each.id == made.next), None)
        found = view(
            loaded.id, made, run, batches, running=running, titles=titles, brief=brief, ended=ended,
            present=lambda path: place is not None and place.joinpath(*path.split("/")).is_file(),
            next_flow={"id": following.id, "title": following.record.title or following.id} if following else None,
            took=took, built=self._built(loaded.id, made),
        )  # fmt: skip
        for each in found["waiting"]:  # the question's own answers, as a client offers them
            try:
                asked = self.kernel.questions.get(str(each["question"]))
            except QuestionError:
                continue
            each["options"] = [{"id": option.id, "label": option.label, "effect": option.effect}
                               for option in asked.options]  # fmt: skip
        return {
            **found,
            "revision": loaded.revision,
            "folder": str(place) if place is not None else "",
        }  # fmt: skip

    def _planning_view(self, planning: Planning, workspace: str) -> dict[str, Any]:
        """The Flow view of a planning open in the workspace (design 0013 §15, decision 0101): its latest draft drawn
        with the view's own layout as far as it reads (nothing before the first), marked as a draft with its number,
        state and problems; the planning: its status, where it opens, the attach command, its session and its steps."""
        from clank.components.flows.building import readable, steps
        from clank.components.flows.kinds import Box
        from clank.components.workspaces.service import WorkspaceUnavailable

        try:
            place: Path | None = Path(self.kernel.parts["workspaces"].folder_of(workspace))
        except WorkspaceUnavailable:
            place = None
        values = self.building.plannings.draft(planning.flow)
        made = readable(values) if values is not None else None
        stand_in = Flow.model_construct(title=planning.name, boxes=[Box(id="brief", type="you", title="Your brief")])
        runtime = self.kernel.parts["runtime"]
        slot = runtime.state.slot(SLOT)
        running = slot.preset if slot.status == "ready" and slot.preset else ""
        titles = {str(preset["id"]): str(preset["title"]) for preset in self._presets()}
        brief = _text_of(place, "BRIEF.md") if place is not None else ""
        shown = made if made is not None else stand_in
        took = {str(each["preset"]): each["seconds"] for each in self.switches(shown)["switches"]}
        found = view(
            planning.flow, shown, None, [], running=running, titles=titles, brief=brief, ended={},
            present=lambda path: place is not None and place.joinpath(*path.split("/")).is_file(), took=took,
        )  # fmt: skip
        if made is None:
            found.update(boxes=[], lines=[], ahead=[], counts={}, deliverables=[], models=[], waiting=[], next_ask=None)
        found["title"] = (made.title if made is not None and made.title else "") or planning.name
        last = planning.history[-1] if planning.history else None
        found["draft"] = (
            {"number": last.number, "state": last.state, "problems": list(last.problems)}
            if values is not None and last is not None
            else None
        )
        session = {"workspace": workspace, "session": planning.session, "port": planning.port}
        session_flow = self.kernel.parts["agents"].flows.view(workspace, planning.session) if planning.session else None
        attach = f"cd {place if place is not None else '<the folder>'} then clank flow attach"
        found["planning"] = {
            "flow": planning.flow, "name": planning.name, "status": planning.status, "where": planning.where,
            "why": planning.why, "attach": attach, "title": session_title(planning),
            "session": session if planning.session else None,
            "steps": steps(planning, place if place is not None else Path("."), session_flow, attach),
        }  # fmt: skip
        found["folder"] = str(place) if place is not None else ""
        found["revision"] = ""
        found["version"] = hashlib.sha256(json.dumps(found, sort_keys=True, default=str).encode()).hexdigest()[:16]
        return found

    def _built(self, flow: str, made: Flow) -> dict[str, Any] | None:
        """A flow built with the model, as the Flow view shows it (design 0013 §15): when and from which session, its
        brief, and its planning's state, its last draft's warnings and the question that told the owner; None for a flow
        not built."""
        if made.built is None:
            return None
        planning = self.building.planning(flow)
        return {
            "at": to_text(made.built.at), "session": made.built.session, "brief": made.built.brief,
            "status": planning.status if planning is not None else "",
            "warnings": list(planning.warnings) if planning is not None else [],
            "question": planning.question if planning is not None else "",
        }  # fmt: skip

    def log(self, workspace: str, name: str, run: int = 0) -> dict[str, Any]:
        """A run's log (design 0013 §6, §12: the run log on `h`): its events, oldest first, each with its time, type,
        actor, summary, box and outcome; the flow's latest run unless `run` names one."""
        flow = self._find(workspace, name).id
        found = self.runner.runs.load(flow, run) if run else self.runner.runs.latest(flow)
        if found is None:
            return {"flow": flow, "run": None, "events": []}
        events = [
            event
            for event in self.kernel.events.latest(2000, subject=Subject(kind="flow", id=flow))
            if event.data.get("run") == found.number
        ]
        return {
            "flow": flow,
            "run": found.number,
            "events": [
                {"time": to_text(event.time), "type": event.type, "actor": event.actor.describe(),
                 "summary": event.summary, "box": str(event.data.get("box") or ""),
                 "outcome": str(event.data.get("outcome") or event.data.get("decision") or "")}
                for event in reversed(events)
            ],
        }  # fmt: skip

    def runs(self, workspace: str, name: str) -> dict[str, Any]:
        """A flow's runs, newest first, each with its boxes' states and tries, and the order its boxes run in."""
        loaded = self._find(workspace, name)
        assert isinstance(loaded.record, Flow)
        return {**self.runner.view(loaded.id), **_shape(loaded.record)}

    def _run_view(self, flow: str, run: Run) -> dict[str, Any]:
        loaded = self.kernel.settings.get(Flow.KIND, flow)
        assert isinstance(loaded.record, Flow)
        return {"flow": flow, "run": run.model_dump(mode="json"), **_shape(loaded.record)}

    def waiting(self) -> list[dict[str, Any]]:
        """What the flows wait for (design 0013 §10): each question a run waits for while it waits, oldest first, with
        its flow, run and box, the files it shows and the answers that take words (`waiting.py`)."""
        asked = {question.id: question for question in self.kernel.questions.waiting()}
        found = []
        for run in self.runner.runs.all():
            if run.status not in ACTIVE or run.waiting is None or run.waiting.question not in asked:
                continue
            view = self._waiting_view(run)
            if view is not None:
                found.append((asked[run.waiting.question].asked, view))
        return [view for _, view in sorted(found, key=lambda pair: pair[0])]

    def about(self, questions: list["Question"]) -> dict[str, dict[str, Any]]:
        """For each question about a flow, by its id, what it shows: its run's view (`waiting`), else its flow alone (a
        question that no run's file names, such as a batch of proposals: the flow and its title). The runs' files are
        read only when a question is about a flow: the phone asks every few seconds."""
        about = [question for question in questions if question.about is not None and question.about.kind == "flow"]
        views = {view["question"]: view for view in self.waiting()} if about else {}
        found: dict[str, dict[str, Any]] = {}
        for question in about:
            if question.about is not None:
                flow = question.about.id
                alone = {"flow": flow, "title": self._title(flow), "kind": "", "files": [], "notes": {}}
                found[question.id] = views.get(question.id, alone)
        return found

    def shown_file(self, question: str, index: int) -> dict[str, Any]:
        """A file that a question a flow waits for shows, by its place in the question's list, as it stands in the
        folder now (what an approval takes, design 0013 §8): its text up to the flow's `whole_up_to`, else why not (not
        written yet, larger, not text). `404 not_found` when no flow waits for that question, or it shows no such
        file."""
        view = next((each for each in self.waiting() if each["question"] == question), None)
        if view is None:
            raise ApiError(404, "not_found", f"no flow waits for {question} now")
        files: list[dict[str, Any]] = view["files"]
        if not 0 <= index < len(files):
            raise ApiError(404, "not_found", f"{question} shows {len(files)} file(s), not a file {index}")
        shown = files[index]
        place, limit = Path(shown["file"]), self._whole_up_to(view["flow"])
        said: dict[str, Any] = {"path": shown["path"], "box": shown["box"], "size": 0, "text": None, "why": ""}
        if not place.is_file():
            return {**said, "why": f"{shown['path']} is not in the folder yet"}
        folder = Path(view["folder"]).resolve()
        if folder not in place.resolve().parents:  # a link the folder holds, to a file elsewhere on this computer
            return {**said, "why": f"{shown['path']} leads out of the folder: read it on the computer"}
        size = place.stat().st_size
        said["size"] = size
        if size > limit:
            why = f"{shown['path']} is {size:,} bytes, more than the phone is shown ({limit:,})"
            return {**said, "why": f"{why}: read it on the computer"}
        try:
            return {**said, "text": place.read_bytes().decode("utf-8")}
        except UnicodeDecodeError:
            return {**said, "why": f"{shown['path']} is not text ({size:,} bytes)"}
        except OSError as error:
            return {**said, "why": f"{shown['path']} cannot be read: {error.strerror or error}"}

    def _title(self, flow: str) -> str:
        from clank.kernel.settings import SettingsError

        try:
            return self.kernel.settings.get(Flow.KIND, flow).record.title or flow
        except SettingsError:
            return flow

    def _whole_up_to(self, flow: str) -> int:
        loaded = self.kernel.settings.get(Flow.KIND, flow)
        assert isinstance(loaded.record, Flow)
        return loaded.record.defaults.whole_up_to

    def copy(self, workspace: str, name: str, *, box: str, path: str, attempt: int, run: int = 0) -> dict[str, Any]:
        """A try's copy of a deliverable (design 0013 §8), as the try kept it in its folder: its text. The flow's latest
        run unless `run` names one; `404 not_found` for a run or a try that does not exist, `409 refused`, saying why,
        for a file the try kept by its fingerprint only, did not write, or that is not text."""
        flow = self._find(workspace, name).id
        try:
            found = self.runner.runs.load(flow, run) if run else self.runner.runs.latest(flow)
        except (OSError, ValueError):
            found = None
        if found is None:
            raise ApiError(404, "not_found", f"{flow} has no run {run}" if run else f"{flow} has not run yet")
        tries = found.boxes[box].tries if box in found.boxes else []
        made = next((each for each in tries if each.number == attempt), None)
        if made is None:
            raise ApiError(404, "not_found", f"{box} has no try {attempt} in run {found.number} of {flow}")
        kept = next((each for each in made.deliverables if each.path == path and each.sha256), None)
        if kept is None:
            raise ApiError(409, "refused", f"try {attempt} of {box} did not write {path}")
        if not kept.copied:
            raise ApiError(
                409,
                "refused",
                f"try {attempt} of {box} kept {path} by its fingerprint only ({kept.size:,} bytes, more than the flow "
                "copies): open the file in the folder instead",
            )
        copies = self.runner.runs.try_folder(found, box, attempt) / "deliverables"
        source = copies.joinpath(*kept.path.split("/"))
        if copies.resolve() not in source.resolve().parents:
            raise ApiError(409, "refused", f"{path} lies outside the try's folder")
        try:
            text = source.read_bytes().decode("utf-8")
        except UnicodeDecodeError as error:
            raise ApiError(409, "refused", f"try {attempt}'s {path} is not text ({kept.size:,} bytes)") from error
        except OSError as error:
            raise ApiError(409, "refused", f"try {attempt}'s copy of {path} cannot be read: {error}") from error
        return {"flow": flow, "run": found.number, "box": box, "try": attempt, "path": path, "text": text}

    def _waiting_view(self, run: Run) -> dict[str, Any] | None:
        from clank.components.workspaces.service import WorkspaceUnavailable
        from clank.kernel.settings import SettingsError

        try:
            loaded = self.kernel.settings.get(Flow.KIND, run.flow)
            folder = Path(self.kernel.parts["workspaces"].folder_of(run.workspace))
        except (SettingsError, WorkspaceUnavailable):
            return None
        assert isinstance(loaded.record, Flow)
        return shown(run, loaded.record, folder)

    def workspace_of(self, folder: str) -> str | None:
        """The workspace whose folder is `folder` or holds it, the innermost when they nest; None for none."""
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        given = _comparable(folder)
        found = [
            (len(path), str(row["name"]))
            for row in workspaces.records()
            if given == (path := _comparable(row["path"])) or given.startswith(path.rstrip(os.sep) + os.sep)
        ]
        return max(found)[1] if found else None

    def router(self) -> Any:
        """The component's routes."""
        from clank.components.flows.api import router

        return router(self)

    def _find(self, workspace: str, name: str) -> Loaded:
        wanted = name.strip().lower()
        for loaded in self.kernel.settings.records(Flow.KIND):
            group, own = loaded.id.split("/", 1)
            if group == workspace and wanted in (own.lower(), loaded.record.title.lower()):
                return loaded
        where = self.folder / workspace
        raise ApiError(404, "not_found", f"there is no flow {name!r} in {workspace}: its flows are kept in {where}")

    def _view(self, loaded: Loaded, presets: list[dict[str, Any]]) -> dict[str, Any]:
        flow = loaded.record
        assert isinstance(flow, Flow)
        workspace, name = loaded.id.split("/", 1)
        problems = self._problems(loaded.path, presets) if loaded.path is not None else []
        return {
            "id": loaded.id,
            "workspace": workspace,
            "name": name,
            "title": flow.title or name,
            "boxes": len(flow.boxes),
            "source": loaded.source,
            "revision": loaded.revision,
            "file": str(loaded.path),
            "problems": [_problem(problem) for problem in problems],
        }

    def _problems(self, path: Path, presets: list[dict[str, Any]]) -> list[SettingsProblem]:
        """What is wrong with a flow's file as it is on disk now: its own rules, then what needs other records."""
        try:
            found = read_record(Flow, path)
        except FileNotFoundError:
            return [SettingsProblem(path, None, None, "is gone: Clank reads the flows' folder again within seconds")]
        except OSError as error:
            return [SettingsProblem(path, None, None, f"cannot be read: {error.strerror or error}")]
        if isinstance(found, list):
            return found
        record, _, raw = found
        assert isinstance(record, Flow)
        text = raw.decode("utf-8-sig")
        kept_in = path.parent.name if path.parent.parent == self.folder else ""
        return [
            SettingsProblem(path, line_of(text, place) if place else None, ".".join(map(str, place)) or None, message)
            for place, message in self._other_problems(record, kept_in, presets)
        ]

    def problems_of(self, id: str, record: Flow) -> list[tuple[Place, str]]:
        """What needs other records, of a flow `id` not saved yet (a draft, design 0013 §15): its workspace, then its
        presets, as a saved flow is checked."""
        return self._saved(id, record)

    def _saved(self, id: str, record: Settings) -> list[tuple[Place, str]]:
        """The settings files' check of a flow read or written, by its id `<workspace>/<name>`."""
        assert isinstance(record, Flow)
        return self._other_problems(record, id.split("/", 1)[0], self._presets())

    def _other_problems(self, flow: Flow, kept_in: str, presets: list[dict[str, Any]]) -> list[tuple[Place, str]]:
        """What needs other records: the workspace (`kept_in`: the one whose folder keeps the flow, if any), then the
        presets."""
        return self._workspace_problems(flow, kept_in) + _preset_problems(flow, presets)

    def _workspace_problems(self, flow: Flow, kept_in: str) -> list[tuple[Place, str]]:
        if kept_in and flow.workspace and flow.workspace != kept_in:
            return [
                (
                    ("workspace",),
                    f"names the workspace {flow.workspace}, but it is kept in {kept_in}'s folder: a flow is for the "
                    "workspace whose folder keeps it",
                )
            ]
        named = flow.workspace or kept_in
        if named and named not in {loaded.id for loaded in self.kernel.settings.records("workspace")}:
            place: Place = ("workspace",) if flow.workspace else ()
            return [(place, f"Clank has no workspace named {named}: `clank workspace open` in its folder makes it")]
        return []

    def preset_problem(self, name: str) -> str:
        """Why a box may not run on the preset `name` (it does not exist, or is for another slot); "" when it may."""
        found = _named_problems([((), name)], self._presets())
        return found[0][1] if found else ""

    def _presets(self) -> list[dict[str, Any]]:
        """Every preset's id, title and slot, from the records alone (the settings files check each flow they read)."""
        return [
            {"id": loaded.id, "title": loaded.record.title or loaded.id, "slot": getattr(loaded.record, "slot", SLOT)}
            for loaded in self.kernel.settings.records("preset")
        ]


def _preset_problems(flow: Flow, presets: list[dict[str, Any]]) -> list[tuple[Place, str]]:
    """Each preset the flow names that does not exist, or is for another slot than the main one."""
    named: list[tuple[Place, str]] = [(("defaults", "model"), flow.defaults.model)]
    named += [(("boxes", i, "model"), box.model) for i, box in enumerate(flow.boxes)]
    return _named_problems(named, presets)


def _named_problems(named: list[tuple[Place, str]], presets: list[dict[str, Any]]) -> list[tuple[Place, str]]:
    """Each preset named that does not exist, or is for another slot than the main one."""
    usable = ", ".join(sorted(str(preset["title"]) for preset in presets if preset.get("slot", SLOT) == SLOT))
    found: list[tuple[Place, str]] = []
    for place, name in named:
        if not name:
            continue
        wanted = name.strip().lower()
        preset = next((each for each in presets if wanted in (each["id"].lower(), str(each["title"]).lower())), None)
        if preset is None:
            found.append((place, f"names the preset {name!r}, which does not exist; the main slot's are: {usable}"))
        elif preset.get("slot", SLOT) != SLOT:
            found.append(
                (place, f"{name} is a preset for the {preset['slot']} slot, and a box runs on the main slot: {usable}")
            )
    return found


def _followed(records: list[Loaded], latest: dict[str, Run | None]) -> Loaded:
    """The flow a folder's Monitor follows: the one whose run is running, else one queued, else the one run last (its
    run's end, else its start, the latest; a flow built with the model and not run yet as of when it was built, design
    0013 §15), else the first."""
    active = [each for each in records if (run := latest[each.id]) is not None and run.status in ACTIVE]
    if active:  # the one running before one queued behind it
        return min(active, key=lambda each: (latest[each.id].status != "running", each.id))  # type: ignore[union-attr]
    ran = [(run.ended or run.created, each.id, each) for each in records if (run := latest[each.id]) is not None]
    ran += [
        (built.at, each.id, each)
        for each in records
        if latest[each.id] is None and isinstance(each.record, Flow) and (built := each.record.built) is not None
    ]
    if ran:
        return max(ran, key=lambda found: (found[0], found[1]))[2]
    return min(records, key=lambda each: each.id)


def _text_of(folder: Path, path: str, largest: int = 65_536) -> str:
    """A text file of the folder, up to `largest` bytes; "" when it is not there, or is a link that leads out of the
    folder (as the phone reads a file a gate shows)."""
    place = folder.joinpath(*path.split("/"))
    try:
        if folder.resolve() not in place.resolve().parents:
            return ""
        return place.read_bytes()[:largest].decode("utf-8", errors="replace")
    except OSError:
        return ""


def _shape(flow: Flow) -> dict[str, Any]:
    """The order a flow's boxes run in, and each box's type."""
    return {"order": order(flow), "types": {box.id: box.type for box in flow.boxes}}


def _problem(problem: SettingsProblem) -> dict[str, Any]:
    return {"file": str(problem.path), "line": problem.line, "field": problem.field, "message": problem.message}


def _refused_as_409(action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """What the runner answers; its refusal as `409 refused`, in its words."""
    try:
        return action()
    except RunError as error:
        raise ApiError(409, "refused", str(error)) from error


def _the_owners(actor: Actor) -> None:
    """Deciding proposals is the owner's: a request from the agent (the gateway's client) is refused (decision 0020)."""
    if actor.kind == "session":
        raise ApiError(403, "forbidden", "the agent proposes boxes; only the user decides them")


def _comparable(folder: str) -> str:
    return os.path.normcase(os.path.abspath(folder))
