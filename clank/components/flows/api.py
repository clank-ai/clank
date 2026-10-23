"""The flows component's routes (design 0013 §6, §9, §11): flows listed, shown and checked; a flow run, paused,
stopped; a VERIFY's verdict; a box's proposals, and the owner's decisions on them.

They are included under `/api/v1/` behind the local token like every route (design 0002 §2.7). A client names the folder
it works in (`folder`) to learn its workspace; a check reads the file as it is on disk now. The runner's routes (step
2) run a flow, pause it and stop it, each recorded with the client that asked, and list its runs; they act on the
service's event loop, where the runner drives the runs, so a control and the driver never cross. A VERIFY's verdict
(step 3) comes from its model through the gateway, which forwards it as the client `agent` (and nothing else under
`/flows/`): it is recorded as the agent's session's, and what cannot be kept is `409 refused`, saying what to fix. So
do a box's reading of its flow and its proposals (step 4: `read`, `propose`, `submit`); the owner's decisions on them
(`proposals/accept|reject|edit`) are refused to the client `agent` (403), and the gateway never forwards them. A
planning's draft of a whole flow (step 10, design 0013 §15: `draft`) comes the same way, as the agent's.
"""

from typing import TYPE_CHECKING, Any

import anyio.to_thread
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from clank.components.flows.verdicts import AGENT
from clank.kernel.access import CLIENT_HEADER, client_actor
from clank.kernel.events import Actor

if TYPE_CHECKING:
    from clank.components.flows.service import Flows


class CheckAsked(BaseModel):
    """Which flow's file to check: a saved flow by its id, or a file by its path."""

    flow: str = Field("", description="A saved flow by its id, <workspace>/<name>.")
    file: str = Field("", description="Or a file on this machine, by its path (a draft, a copy).")


class RunAsked(BaseModel):
    """How to run a flow: from its first box, or its latest run again from a box."""

    model_config = ConfigDict(populate_by_name=True)

    start_from: str = Field("", alias="from", description="Run the flow's latest run again from this box.")


class VerdictGiven(BaseModel):
    """A VERIFY's verdict, as `flow_verdict` sends it."""

    workspace: str = Field(description="The workspace whose VERIFY gives it (its MCP server's).")
    result: str = Field(description="pass, or fail.")
    findings: list[str] = Field(default_factory=list, description="A fail's findings, each one thing to fix, in order.")
    criteria: list[Any] = Field(
        default_factory=list,
        description="Each line of the brief and of accept when the check touched: an object of its line, met (true or "
        "false) and evidence, read by the service, whose refusal names the criterion and the field to fix.",
    )


class OrchestratorGiven(BaseModel):
    """A change of a flow's orchestrator, each field left out unchanged."""

    on: bool | None = Field(None, description="true turns it on, false off.")
    final_review: str = Field("", description="orchestrator or owner: who decides the last gate.")
    model: str | None = Field(None, description="The preset its checkpoints run on; empty: the flow's.")
    role: str = Field("", description="steer (it decides the questions too) or watch (it checks each box only).")


class JobGiven(BaseModel):
    """A job, as `flow_job` sends it (design 0013 §17)."""

    workspace: str = Field(description="The workspace whose box at work starts it (its MCP server's).")
    command: str = Field("", description="The command, run in the folder.")
    title: str = Field("", description="What it computes, in a few words.")
    minutes: int = Field(0, description="How long it may run, at most the box's minutes.")


class DecisionGiven(BaseModel):
    """A checkpoint's decision, as `flow_decide` sends it: read by the service, whose refusal says what to fix."""

    workspace: str = Field(description="The workspace whose checkpoint decides (its MCP server's).")
    choice: str = Field("", description="go on, change, back, pause or stop; or the question's answer, or leave.")
    why: str = Field("", description="Why, citing the evidence.")
    met: Any = Field(default_factory=list, description="The brief's lines judged met.")
    unmet: Any = Field(default_factory=list, description="The brief's lines not met yet.")
    looping: Any = Field(False, description="Whether the same failure came back for the same reason.")
    progressing: Any = Field(True, description="Whether the run made progress since the last checkpoint.")
    facts: str = Field("", description="What is known now, the ledger's facts rewritten.")
    plan: str = Field("", description="The plan from here, the ledger's plan rewritten.")
    note: str = Field("", description="What the next box is told, or the words of a question's answer.")
    back_to: str = Field("", description="A review's back: the box to do again.")
    changes: Any = Field(default_factory=list, description="A change's list: edits of boxes not run, or boxes added.")
    side: Any = Field(default_factory=list, description="A job's checkpoint's side tasks: title, prompt, reads.")
    tell_user: str = Field("", description="What the user should know now: it reaches them at once.")


class ProposalGiven(BaseModel):
    """A box proposed with `flow_propose_box`, as the model sent it: read by the service, whose refusal names the
    argument to fix."""

    workspace: str = Field(description="The workspace whose box proposes it (its MCP server's).")
    after: str = Field("", description="The box of the flow it comes after.")
    type: str = Field("", description="Its type: task, plan, verify, decompose, integrate, gate or you.")
    title: str = Field("", description="What it does, in a few words.")
    prompt: str = Field("", description="Everything its model must know.")
    deliverable: Any = Field(default_factory=list, description="The files it writes in the folder: one, or a list.")
    accept_when: Any = Field(default_factory=list, description="What makes it right: a line each, or a list.")
    model: str = Field("", description="The preset it runs on; empty: the flow's.")
    mode: str = Field("", description="plan, review or auto; empty: the box's own.")
    sees: Any = Field(default_factory=list, description="The files its first message hands it: one, or a list.")
    why: str = Field("", description="Why it is proposed.")
    flow: str = Field("", description="Its flow, when named: the flow of the box at work.")


class SubmitGiven(BaseModel):
    """A box's proposals submitted with `flow_submit`."""

    workspace: str = Field(description="The workspace whose box submits them (its MCP server's).")
    summary: str = Field("", description="What the proposals are, in a sentence or two.")
    flow: str = Field("", description="Its flow, when named: the flow of the box at work.")


class NewAsked(BaseModel):
    """Open a planning, a flow built with the model (design 0013 §15): in a workspace, or the one of a folder."""

    folder: str = Field("", description="The folder the client works in: its workspace's.")
    workspace: str = Field("", description="Or the workspace, by name.")
    name: str = Field("", description="The flow's name; empty: Clank's (flow, flow-2, ...).")
    where: str = Field(
        "here",
        description="here: OpenCode in the asking terminal; vscode: in Clank's VS Code window; attach: in the terminal "
        "that runs `clank flow attach`.",
    )
    aside: bool = Field(
        False, description="Set the planning open in the workspace aside; without it, one open there is refused (409)."
    )


class AttachAsked(BaseModel):
    """Attach a terminal to the planning open in a workspace, or in the one of a folder (design 0013 §15)."""

    folder: str = Field("", description="The folder the client works in: its workspace's.")
    workspace: str = Field("", description="Or the workspace, by name.")


class DraftGiven(BaseModel):
    """A whole flow drafted with `flow_draft` in a planning session (design 0013 §15), as the model sent it: read by
    the service, whose refusal names each field to fix."""

    workspace: str = Field(description="The workspace whose planning drafts it (its MCP server's).")
    flow: Any = Field(default_factory=dict, description="The flow: title, defaults, boxes and lines.")


class DecideAsked(BaseModel):
    """Which proposals to decide: by their ids, or all still waiting; an acceptance of one may edit it first."""

    proposals: list[str] = Field(default_factory=list, description="The proposals, by their ids (T1).")
    every: bool = Field(False, alias="all", description="Every proposal still waiting.")
    changes: dict[str, Any] = Field(default_factory=dict, description="An edit of the one proposal accepted.")
    run: int = Field(0, description="The run; 0: the flow's latest.")

    model_config = ConfigDict(populate_by_name=True)


class EditAsked(BaseModel):
    """An edit of a proposal still waiting."""

    proposal: str = Field(description="The proposal, by its id.")
    changes: dict[str, Any] = Field(description="Its settings to change, as a box's file names them.")
    run: int = Field(0, description="The run; 0: the flow's latest.")


class NextAsked(BaseModel):
    """Make a flow's next flow when it has none, and maybe run it."""

    run: bool = Field(False, description="Start it too: its first run begins, and the question about it is withdrawn.")


def router(flows: "Flows") -> APIRouter:
    """The routes, over the flows component's part."""
    routes = APIRouter()

    @routes.get("/flows")
    async def every(workspace: str = "", folder: str = "") -> dict[str, Any]:
        """Every flow, by workspace, and the flow files that do not read.

        Also where flows are kept, Clank's template, and the workspace of the folder the client works in (`folder`);
        `workspace` keeps one workspace's flows only."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(flows.flows, workspace, folder)
        return found

    @routes.get("/flows/waiting")
    async def waiting() -> dict[str, Any]:
        """What the flows wait for: each question a run waits for, oldest first, with its flow, run and box, the files
        it shows (each with its place in the folder, the box that wrote it and the tries that kept a copy) and the
        answers that take words."""
        return {"waiting": await anyio.to_thread.run_sync(flows.waiting)}

    @routes.get("/flows/view")
    async def shown(folder: str = "", flow: str = "") -> dict[str, Any]:
        """What the Monitor's Flow view shows (design 0013 §12): the flow named (`<workspace>/<name>`), else the
        planning open in the folder's workspace (`planning`: its steps and session; its latest draft drawn, `draft` its
        state, §15), else the one the folder's Monitor follows (its workspace's active run's, else the one run last,
        else the first); its run, each box with its state, tries and verdicts, the lines, the proposals waiting, Models
        in this flow, Waiting for you, The brief, checked, Deliverables and Ahead, and a version that moves only when
        any of it changed. With no flow to show, `flow` is null and `why` says why."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: flows.view(folder, flow))
        return found

    @routes.get("/flows/{workspace}/{name}/log")
    async def log(workspace: str, name: str, run: int = 0) -> dict[str, Any]:
        """A run's log, shown by the Flow view on `h`: its events, oldest first; the flow's latest run unless `run`
        names one."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: flows.log(workspace, name, run))
        return found

    @routes.get("/flows/{workspace}/{name}/copy")
    async def copy(
        workspace: str,
        name: str,
        box: str,
        file: str,
        attempt: int = Query(alias="try", ge=1, description="The try, from 1."),
        run: int = 0,
    ) -> dict[str, Any]:
        """A try's copy of a deliverable, as the try kept it in its folder (its text): what VS Code's diff of two tries
        shows. The flow's latest run unless `run` names one; a file the try kept by its fingerprint only, or did not
        write, is refused, saying why."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: flows.copy(workspace, name, box=box, path=file, attempt=attempt, run=run)
        )
        return found

    @routes.get("/flows/{workspace}/{name}")
    async def one(workspace: str, name: str) -> dict[str, Any]:
        """One flow, by its name in its workspace or its title: its values, what is wrong with its file now, and the
        switches of the main slot a run of it makes from what the slot runs now (design 0013 §7)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(flows.flow, workspace, name)
        return found

    @routes.get("/flows/{workspace}/{name}/prepare")
    async def prepare(workspace: str, name: str, box: str = "") -> dict[str, Any]:
        """Each box's first message as it would be sent now, with its size against its model's window (design 0013 §5).

        Every box a model runs, in the order they run, or `box` alone: its first message built as the runner builds it,
        from the files as they are now and the active run's state, its next try; its tokens, counted by the engine
        when the main slot runs its preset and the engine counts, else an estimate (`exact` false, `counted` saying
        how); its preset's window and its share of it, `over` past a quarter. A box the flow has not is 404, an owner's
        box (it has no first message) 409."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: flows.prepare(workspace, name, box))
        return found

    @routes.get("/flows/{workspace}/{name}/next")
    async def next_flow(workspace: str, name: str) -> dict[str, Any]:
        """A flow's next flow (design 0013 §3, decision 0091): its id, title, the brief it was made from and how many
        times it ran, and the question still asking whether to run it; else why there is none."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: flows.next(workspace, name))
        return found

    @routes.post("/flows/{workspace}/{name}/next")
    async def make_next(workspace: str, name: str, asked: NextAsked, request: Request) -> dict[str, Any]:
        """Make a flow's next flow when it has none, from its latest run's INTEGRATE's brief, and with `run` start it.

        Refused (409, saying why) when its INTEGRATE wrote no brief, or when it exists already and is not to run."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: flows.make_next(workspace, name, actor=actor, run=asked.run)
        )
        return found

    @routes.get("/flows/{workspace}/{name}/runs")
    async def runs(workspace: str, name: str) -> dict[str, Any]:
        """A flow's runs, newest first, each with its boxes' states and tries, and the order its boxes run in."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(flows.runs, workspace, name)
        return found

    @routes.get("/flows/{workspace}/{name}/diff")
    async def diff(
        workspace: str, name: str, box: str, file: str = "", a: int | None = None, b: int | None = None, run: int = 0
    ) -> dict[str, Any]:
        """Two tries of a box compared: the unified diff of a deliverable's copies, and how many lines changed.

        By default the box's last two tries that kept a copy, of the file it wrote first, in the flow's latest run;
        `file`, `a`, `b` and `run` choose others."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: flows.diff(workspace, name, box, path=file, a=a, b=b, run=run)
        )
        return found

    @routes.post("/flows/{workspace}/{name}/run")
    async def run(workspace: str, name: str, asked: RunAsked, request: Request) -> dict[str, Any]:
        """Run a flow: a new run, its paused run resumed, or its latest run again from a box (`from`).

        A new run is queued behind another flow's when one is active; from a box, that box and every box after it run
        again, as new tries."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        return flows.go(workspace, name, actor=actor, start_from=asked.start_from)

    @routes.post("/flows/{workspace}/{name}/pause")
    async def pause(workspace: str, name: str, request: Request) -> dict[str, Any]:
        """Pause a flow's run: no box starts; the running one goes on (`run` resumes it)."""
        return flows.pause(workspace, name, actor=client_actor(request.headers.get(CLIENT_HEADER)))

    @routes.post("/flows/{workspace}/{name}/stop")
    async def stop(workspace: str, name: str, request: Request) -> dict[str, Any]:
        """Stop a flow's run: its running box's session is stopped, and the run ends."""
        return flows.stop(workspace, name, actor=client_actor(request.headers.get(CLIENT_HEADER)))

    @routes.post("/flows/verdict")
    async def verdict(given: VerdictGiven, request: Request) -> dict[str, Any]:
        """A VERIFY's verdict, given to the VERIFY box at work in the workspace (design 0013 §9).

        Kept on its try and as `verdict.md` in the try's folder; refused (409, saying why) while no VERIFY works there
        or when it cannot be kept as sent (a fail without findings)."""
        actor = _actor(request)
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: flows.verdict(given.workspace, given.result, given.findings, given.criteria, actor=actor)
        )
        return found

    @routes.get("/flows/{workspace}/{name}/orchestrator")
    async def orchestrator(workspace: str, name: str) -> dict[str, Any]:
        """A flow's orchestrator (design 0013 §16): its settings, the checkpoint at work and the latest run's ledger."""
        actor = Actor(kind="user", via="")
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: flows.orchestrator(workspace, name, actor=actor))
        return found

    @routes.post("/flows/{workspace}/{name}/orchestrator")
    async def steer_with(workspace: str, name: str, given: OrchestratorGiven, request: Request) -> dict[str, Any]:
        """Turn a flow's orchestrator on or off, or change its role, who decides its final review or its model (design
        0013 §16): written through the settings as any edit, and recorded with the client that asked; the run goes
        on."""
        actor = client_actor(request.headers.get(CLIENT_HEADER))
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: flows.orchestrator(
                workspace,
                name,
                actor=actor,
                on=given.on,
                final_review=given.final_review,
                model=given.model,
                role=given.role,
            )
        )
        return found

    @routes.post("/flows/job")
    async def job(given: JobGiven, request: Request) -> dict[str, Any]:
        """A job started by the box at work in the workspace (design 0013 §17): run detached in its container, kept on
        its try; refused (409, saying why) while no box works there, while its job runs, or past its box's minutes."""
        actor = _actor(request)
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: flows.job(given.workspace, given.command, given.title, given.minutes, actor=actor)
        )
        return found

    @routes.post("/flows/decide")
    async def decide(given: DecisionGiven, request: Request) -> dict[str, Any]:
        """A checkpoint's decision, given to the orchestrator's checkpoint at work in the workspace (design 0013 §16).

        Kept on the checkpoint and applied when its session ends; refused (409, saying what to fix) while no
        checkpoint works there or when it cannot be kept as sent."""
        actor = _actor(request)
        fields = given.model_dump(exclude={"workspace"})
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: flows.steer(given.workspace, fields, actor=actor)
        )
        return found

    @routes.get("/flows/read")
    async def read(workspace: str, flow: str = "") -> dict[str, Any]:
        """What a box's model reads of its flow (`flow_read`, design 0013 §9), read-only.

        The flow of the box at work in the workspace: each box in the order they run with its state, its tries and the
        boxes after it, and the run's proposals; with no box at work, the flow named (`flow`), else the workspace's
        flows listed."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: flows.read(workspace, flow))
        return found

    @routes.post("/flows/propose")
    async def propose(given: ProposalGiven, request: Request) -> dict[str, Any]:
        """A box proposed for its flow by the model of the box at work in the workspace (design 0013 §9).

        Checked, then staged in its try's batch, waiting for you (or joined at once by auto-accept, within its cap);
        refused (409) saying which argument to fix."""
        actor = _actor(request)
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: flows.propose(given.workspace, given.model_dump(), actor=actor)
        )
        return found

    @routes.post("/flows/submit")
    async def submit(given: SubmitGiven, request: Request) -> dict[str, Any]:
        """The proposals of the box at work are ready for you: one question asks about those still waiting."""
        actor = _actor(request)
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: flows.submit(given.workspace, given.summary, actor=actor, flow=given.flow)
        )
        return found

    @routes.post("/flows/new")
    async def new(asked: NewAsked, request: Request) -> dict[str, Any]:
        """Open a planning, your talk with the model that builds a flow (design 0013 §15); yours (403 to the agent).

        Here: the command that starts OpenCode's window in your terminal (`argv`), on whose port the planning session
        starts once it answers; in VS Code: the window running in the workspace takes it, else it waits for the one
        Clank's VS Code window starts (`window`: started, running or waits). A name a flow has is refused (409), as is
        a planning open in the workspace unless `aside` sets it aside: a planning is never overwritten."""
        actor = _actor(request)
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: flows.new(asked.workspace, asked.folder, asked.name, asked.where, actor=actor, aside=asked.aside)
        )
        return found

    @routes.post("/flows/attach")
    async def attach(asked: AttachAsked, request: Request) -> dict[str, Any]:
        """OpenCode's window for the planning open in the workspace, for the asking terminal (`clank flow attach`).

        Its command (`argv`) and port: a planning waiting for its window starts its session there, one talking already
        is shown there; the one-window rule closes another window first, said in `notes`. Yours (403 to the agent);
        refused (409, saying why) with no planning open."""
        actor = _actor(request)
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: flows.attach(asked.workspace, asked.folder, actor=actor)
        )
        return found

    @routes.get("/flows/building")
    async def being_built(workspace: str = "", folder: str = "", flow: str = "") -> dict[str, Any]:
        """A planning (design 0013 §15): the flow's, else the one open in the workspace (or the folder's), else its
        newest; its state, its window's port, its session, its drafts and the last one's problems and warnings."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: flows.being_built(workspace, folder, flow))
        return found

    @routes.post("/flows/draft")
    async def draft(given: DraftGiven, request: Request) -> dict[str, Any]:
        """A whole flow drafted by the model of the planning open in the workspace (design 0013 §15).

        Checked as a saved flow and against a built flow's own rules, then written as the flow's file with Clank's
        settings, and you asked to look, then run it; refused (409) naming each problem with its field, and the check's
        warnings, so the model fixes them and drafts again."""
        actor = _actor(request)
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: flows.draft(given.workspace, given.flow, actor=actor)
        )
        return found

    @routes.get("/flows/{workspace}/{name}/proposals")
    async def proposals(workspace: str, name: str, run: int = 0) -> dict[str, Any]:
        """The proposals of a flow's run (its latest unless `run` names one): each batch whole, and those waiting."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(lambda: flows.proposals(workspace, name, run))
        return found

    @routes.post("/flows/{workspace}/{name}/proposals/accept")
    async def accept(workspace: str, name: str, asked: DecideAsked, request: Request) -> dict[str, Any]:
        """Accept proposals, by their ids or all still waiting (`all`), one of them edited first (`changes`).

        They join the flow's file, marked with their run and the box that proposed them; yours only, never the
        agent's (403)."""
        return await _decide(flows, workspace, name, "accept", asked, request)

    @routes.post("/flows/{workspace}/{name}/proposals/reject")
    async def reject(workspace: str, name: str, asked: DecideAsked, request: Request) -> dict[str, Any]:
        """Reject proposals, by their ids or all still waiting (`all`): none of them ever runs; yours only."""
        return await _decide(flows, workspace, name, "reject", asked, request)

    @routes.post("/flows/{workspace}/{name}/proposals/edit")
    async def edit(workspace: str, name: str, asked: EditAsked, request: Request) -> dict[str, Any]:
        """Change a proposal still waiting, checked as a proposal is; it stays waiting. Yours only."""
        actor = _actor(request)
        found: dict[str, Any] = await anyio.to_thread.run_sync(
            lambda: flows.edit(workspace, name, asked.proposal, asked.changes, actor=actor, run=asked.run)
        )
        return found

    @routes.post("/flows/check")
    async def check(asked: CheckAsked) -> dict[str, Any]:
        """Check a flow's file as it is on disk now: each problem with its file, line and field.

        A flow that keeps every rule is then warned of, in the same shape (`warnings`, never a problem): a box's first
        message as it would be sent now past a quarter of its model's window, and a file a box sees or shows that is
        not in the folder and that neither it nor a box before it writes; and it is told the switches of the main slot a
        run of it makes (design 0013 §7)."""
        found: dict[str, Any] = await anyio.to_thread.run_sync(flows.check, asked.flow, asked.file)
        return found

    return routes


async def _decide(
    flows: "Flows", workspace: str, name: str, decision: str, asked: DecideAsked, request: Request
) -> dict[str, Any]:
    actor = _actor(request)
    found: dict[str, Any] = await anyio.to_thread.run_sync(
        lambda: flows.decide(
            workspace, name, decision, asked.proposals, every=asked.every, actor=actor,
            changes=asked.changes or None, run=asked.run,
        )
    )  # fmt: skip
    return found


def _actor(request: Request) -> Actor:
    """The agent's session for the gateway's requests on the agent's behalf, else the user through their client."""
    client = request.headers.get(CLIENT_HEADER)
    return AGENT if (client or "").lower() == "agent" else client_actor(client)
