"""The agents component's part in the service (design 0004 §4): making a workspace's agent ready to work.

`plan` says what the agent program would be given (its model and limits), writing nothing; `prepare` writes the
agent program's configuration into the workspace's container, as the container's user, in its home (a volume, never
the user's folder): the model is the gateway's, reached through the edge
(`http://edge:<gateway port>/v1`), under the role `agent` (decision 0008), with the limits of the preset the role's
slot runs, its window less the margin `config/opencode.json` keeps for one step's tool results (decision 0089), so the
program compacts a conversation before the engine refuses it; when no model runs, it falls back to modest limits and
says so. What it is told and the engine's window are both in `limits`, and the Monitor's compaction line counts the
same margin. It returns the command a terminal runs to start the program in the container, in the
workspace's folder, with the program's environment and as many threads as the container's CPUs. It uses the
workspaces (the container, the platform) and the gateway (its port, its routes) through their services.

The MCP servers the agent gets (design 0004 §10) are written into its configuration too: yours (the tools component's)
unless held back from the workspace (its record's `mcp_off`), and the folder's own (`.mcp.json`) once allowed for the
workspace (`mcp_allowed`, with the fingerprint of the entry as allowed: an entry changed since is not given until
allowed again). One reached by address is not given (the container reaches nothing but the model), nor a folder's
server that has the name of one of yours. `servers` lists them with whether the agent gets each and why not; `allow`
gives one or takes it away. With `live`, each server also has its state (the console's MCP servers page): while agents
run in the workspace's container, running, stopped or failed (and why) as OpenCode says; while none runs, on or off (it
starts with the agent, or not); and the tools of its last check. `switch` starts or stops one: it is given or taken
away as `allow` does, and the agents running in the container connect or disconnect it at once. A flow's box gets
its own on the flow's server alone (`box_tools`, design 0013 §4): those it names, and Clank's own always.

The agent's changes to files are reviewed (design 0007, `review.py`): while the service runs, it watches the agents of
every running workspace and asks the owner about each change, or answers at once in auto mode. From the same watchers'
lines it keeps a flow for every session they see (design 0012 §6.1, `sessionflow/`), for the Monitor, runs the
Monitor's Watch for rules over each as it changes (design 0012 §8, `watchfor/`), and gives a session's context totals
(`context`, design 0012 §4.1: `context.py`) from the gateway's figures and the loaded slot's facts. A figure the owner
marked up is sent to the agent with each mark in words (design 0008, `annotations.py`); the files the agent opens for
the owner open in Clank's VS Code window (design 0018 §7, `showing.py`).

When a flow's box switched the main slot (design 0013 §7, decision 0062), the owner's window in the workspace is told
its model changed (`model_changed`): the event `agents.model_changed`, which VS Code shows, and a notice the review's
view carries for This folder (`model_notice`) until OpenCode is next started there (`prepare`, which writes its
configuration with the new model's limits). It names each of the owner's own sessions there (root sessions that are no
box's) whose context holds more than the new model's context as too small for it. The window itself is left as it is.

A flow built with the model (design 0013 §15) starts its planning session on the workspace's OpenCode window once it
answers: `prepare` tells whoever asked (`on_prepared`) the workspace and port of each window it gives a command for.

Each time an agent starts in a workspace (`prepare`, `configure`), Clank's files for it are written into its home in
the container first (design 0018 §7.5: Clank's MCP server and its instructions, as this Clank has them), so its tools
are always this Clank's whatever image its container was made from; and its way to the model is put right first (design
0004 §3: the edge running, forwarding the gateway's and the proxy's ports, on the workspace's network), what was put
right said in `prepare`'s notes.

Each workspace's OpenCode, and Clank's MCP server in its container, send the workspace's own key to the gateway (design
0016 §9, from the gateway's service); a workspace allowed the cloud gets no MCP server marked local only, and Clank's
server there lists no Notion tool; the gateway is given the names of the tools that never go to the cloud
(`give_local_only`, design 0016 §10) at each start of the service and each change of an MCP server.
"""

import hashlib
import json
import logging
import threading
from collections.abc import AsyncGenerator, Callable, Collection
from typing import TYPE_CHECKING, Any

import anyio

from clank.components.agents import streaming
from clank.components.agents.adapters import AGENT_PROGRAMS
from clank.components.agents.adapters.opencode import PROVIDER, UNSAFE
from clank.components.agents.adapters.program import AgentModel, AgentProgram, Compaction, kept_margin
from clank.components.agents.annotations import EVENT_TYPES as ANNOTATION_EVENTS
from clank.components.agents.annotations import AnnotationError as AnnotationError  # for the routes
from clank.components.agents.annotations import Annotations
from clank.components.agents.artifacts import EVENT_TYPES as ARTIFACT_EVENTS
from clank.components.agents.artifacts import ArtifactError as ArtifactError  # for the routes
from clank.components.agents.artifacts import Artifacts
from clank.components.agents.boards import EVENT_TYPES as BOARD_EVENTS
from clank.components.agents.boards import BoardError as BoardError  # for the routes
from clank.components.agents.boards import Boards
from clank.components.agents.context import totals
from clank.components.agents.guide import Guide, Ruled
from clank.components.agents.guide import GuideError as GuideError  # for the routes
from clank.components.agents.jobs import EVENT_TYPES as JOB_EVENTS
from clank.components.agents.jobs import AgentJobs
from clank.components.agents.jobs import JobsError as JobsError  # for the routes
from clank.components.agents.kinds import MonitorSettings, OpenCodeSettings
from clank.components.agents.latex.answers import Answers
from clank.components.agents.latex.checks import EVENT_TYPES as LATEX_EVENTS
from clank.components.agents.latex.comments import EVENT_TYPES as COMMENT_EVENTS
from clank.components.agents.latex.comments import CommentError as CommentError  # for the routes
from clank.components.agents.latex.comments import Comments
from clank.components.agents.latex.pages import PageError as PageError  # for the routes
from clank.components.agents.latex.pages import PageMarks
from clank.components.agents.mirror import Mirror
from clank.components.agents.modes import BUILD as BUILD  # the agent a flow's box in review or auto is sent to
from clank.components.agents.modes import EVENT_TYPES as MODE_EVENTS
from clank.components.agents.modes import PLANNER as PLANNER  # and a box in plan mode
from clank.components.agents.modes import ModeError as ModeError  # for the routes
from clank.components.agents.modes import Modes
from clank.components.agents.now import now
from clank.components.agents.pausing import PauseError as PauseError  # for the routes
from clank.components.agents.pausing import Pausing
from clank.components.agents.plans import INSTRUCTIONS as INSTRUCTIONS  # for the flows: no box delivers them (0013 §9)
from clank.components.agents.plans import SETTINGS as SETTINGS  # for the flows: no box delivers in them (0013 §9)
from clank.components.agents.plans import is_plan as is_plan  # for the flows: a plan's progress (design 0013 §8)
from clank.components.agents.readout import gpu_view, slot_view
from clank.components.agents.review import EVENT_TYPES as REVIEW_EVENTS
from clank.components.agents.review import Review
from clank.components.agents.review import ReviewError as ReviewError  # for the components that use this one
from clank.components.agents.sessionflow.kept import SessionFlows, gateway_asker, plan_reader
from clank.components.agents.sessions import EVENT_TYPES as SESSION_EVENTS
from clank.components.agents.sessions import SessionError as SessionError  # for the components that use this one
from clank.components.agents.sessions import Sessions
from clank.components.agents.showing import EVENT_TYPES as SHOWING_EVENTS
from clank.components.agents.showing import ShowError as ShowError  # for the routes
from clank.components.agents.showing import Showing
from clank.components.agents.watchfor.marks import EVENT_TYPES as WATCH_EVENTS
from clank.components.agents.watchfor.marks import Marks, slot_facts
from clank.kernel.adapters import AdapterError
from clank.kernel.clock import to_text
from clank.kernel.core import Kernel
from clank.kernel.events import Actor, EventType, Subject
from clank.kernel.settings import SettingsError

if TYPE_CHECKING:
    from clank.components.gateway.service import Gateway
    from clank.components.machine.service import Machine
    from clank.components.runtime.service import Runtime
    from clank.components.tools.service import Server, Tools
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.operations import OperationType
    from clank.kernel.settings import Loaded

MODEL_EVENTS = [
    EventType(
        "agents.model_changed",
        "The model your OpenCode window in a workspace talks to changed: a flow's box switched the main slot (design "
        "0013 §7, decision 0062). The window's configuration, with the model's limits, is refreshed when it next "
        "starts.",
        {
            "workspace": "The workspace.",
            "title": "The model the main slot runs now: its preset's title.",
            "context": "Its context, in tokens.",
            "output": "Its output limit, in tokens.",
            "window": "Whether an OpenCode window runs in the workspace.",
            "by": "What switched it: the flow and its box.",
            "too_small": "Each of your sessions there whose context holds more than the new model's, with how much.",
        },
    )
]
EVENT_TYPES = [
    *SESSION_EVENTS,
    *REVIEW_EVENTS,
    *MODE_EVENTS,
    *ANNOTATION_EVENTS,
    *SHOWING_EVENTS,
    *WATCH_EVENTS,
    *MODEL_EVENTS,
    *LATEX_EVENTS,
    *COMMENT_EVENTS,
    *JOB_EVENTS,
    *ARTIFACT_EVENTS,
    *BOARD_EVENTS,
]
ROLE = "agent"
SESSION_MODEL = {"providerID": PROVIDER, "modelID": ROLE}  # the model a message names: the gateway's role
FALLBACK = (32768, 8192)  # context and output, in tokens, when no model runs to say its own
log = logging.getLogger(__name__)
CLANK_SERVER = "clank"  # Clank's own MCP server, given to every agent: send_to_phone (design 0005 §3)
NOTION_PREFIX = "clank_notion_"  # Clank's Notion tools, as OpenCode names them: never to the cloud (design 0016 §10)
LOCAL_ONLY = "held back: local only, it never goes to the cloud model"
# Its tools that only read, which the planner may use (design 0010 §4): Notion's reading, never its proposals; and
# finding figures and opening files for the owner to see (design 0018 §7).
CLANK_READ_ONLY = (
    "notion_databases", "notion_page", "notion_query", "notion_search", "show_files", "find_figures", "job_status",
)  # fmt: skip
# Its tools of a box's flow, which write nothing in the folder, so the planner may use them too (design 0013 §9); a
# planning's draft of a whole flow, which the planner sends (design 0013 §15); and an orchestrator's decision, which a
# checkpoint, a Plan-mode session, gives (design 0013 §16).
CLANK_FLOW_TOOLS = ("flow_read", "flow_propose_box", "flow_submit", "flow_verdict", "flow_draft", "flow_decide")
STATES = {  # OpenCode's word for an MCP server's state, as the MCP servers page says it
    "connected": "running", "disabled": "stopped", "failed": "failed", "needs_auth": "needs sign-in",
    "needs_client_registration": "needs sign-in",
}  # fmt: skip


def limits(model: AgentModel) -> dict[str, int]:
    """What the program is told (`context`, `output`), the engine's own window and the margin kept free in it."""
    return {"context": model.context - model.margin, "output": model.output, "window": model.context,
            "margin": model.margin}  # fmt: skip


def _fingerprint(entry: dict[str, Any]) -> str:
    """A server's entry, as allowed: an entry changed since has another (design 0004 §10)."""
    return hashlib.sha256(json.dumps(entry, sort_keys=True).encode("utf-8")).hexdigest()[:16]


class AgentError(Exception):
    """An agent that cannot be made ready, and why."""


class Agents:
    """The agents component, built on the kernel."""

    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel
        self.sessions = Sessions(kernel)
        self.review = Review(kernel, self.sessions)
        self.sessions.channel = self.review.watchers.request  # the actions the owner waits on (design 0023 §4)
        self.modes = Modes(kernel, self.sessions, self.review)
        self.review.modes = self.modes
        self.annotations = Annotations(kernel, self.sessions, self.reads_images, self._read_image)
        self.showing = Showing(kernel)  # files opened for the owner (design 0018 §7)
        self.jobs = AgentJobs(kernel, self.sessions)  # long computations the agent starts (design 0021 §6)
        self.artifacts = Artifacts(kernel, self.sessions)  # pages the agent makes for the owner (design 0021 §5)
        self.boards = Boards(kernel)  # canvases the owner and the agent share (design 0022)
        self.pages = PageMarks(self.review.latex.run)  # a PDF's pages to mark up (design 0020 §10)
        self.answers = Answers(self.sessions)  # every number answered (design 0020 §12)
        self.annotations.pages, self.annotations.answers = self.pages, self.answers
        self.comments = Comments(kernel, self.sessions, self.annotations, self.answers)  # design 0020 §11
        self.flows = SessionFlows(self.sessions, gateway_asker(kernel), plan_reader(kernel))
        self.mirror = Mirror()  # the conversations held for the sessions clients follow (design 0023 §2)
        self.sessions.listen(self.mirror.heard)
        self.pausing = Pausing(kernel, self.sessions)  # the Guide's pause (design 0012 §9.4)
        now = lambda: to_text(kernel.clock.now())  # noqa: E731
        self.guide = Guide(self.sessions, self.flows, self.review, self.figures, now, self.pausing)
        self.marks = Marks(self.monitor_settings, kernel.clock, kernel.events, Ruled(self.guide))
        self._notices: dict[str, dict[str, Any]] = {}  # each workspace's window told its model changed (design 0013 §7)
        self._notices_lock = threading.Lock()
        self._prepared: list[Callable[[str, int], None]] = []  # told each window prepared (design 0013 §15)
        kernel.events.subscribe(self._heard_tools)  # the tools that never go to the cloud, given to the gateway

    def on_prepared(self, told: Callable[[str, int], None]) -> None:
        """Be told each OpenCode window `prepare` gives a command for: its workspace and its port (a flow's planning
        waits for one, design 0013 §15), after its configuration is written and before the window starts."""
        self._prepared.append(told)

    async def run(self) -> None:
        """Watch the agents of every running workspace while the service runs (design 0007 §4), keep their
        sessions' flows (design 0012 §6.1), and run the Watch for rules over them as they change (design 0012 §8)."""
        try:
            await anyio.to_thread.run_sync(self.give_local_only)
        except Exception:
            log.exception("giving the gateway the tools that never go to the cloud failed")
        async with anyio.create_task_group() as group:
            group.start_soon(self.review.watchers.run)
            group.start_soon(self.flows.run)
            group.start_soon(self.jobs.run)
            group.start_soon(self.marks.run, self.flows, slot_facts(self.kernel))

    def monitor_settings(self) -> MonitorSettings:
        """What each Watch for rule does, as `config/monitor.json` says now (design 0012 §8)."""
        return MonitorSettings.model_validate(self.kernel.settings.get("monitor", "monitor").record.model_dump())

    def context(self, workspace: str, session: str) -> dict[str, Any]:
        """A session's context totals (design 0012 §4.1, §4.4; `context.py`), from the gateway's figures of its own
        requests, its routes and the facts of the presets that answered them, by OpenCode's compaction rule (the
        program of every session the watchers see)."""
        found, _ = self.figures(workspace, session)
        return {"workspace": workspace, **found}

    def now(self, workspace: str, session: str) -> dict[str, Any]:
        """What a session does now (design 0012 §5; `now.py`), from the gateway's figures of its own requests, its flow,
        the routes and the facts of the presets that answered it, and the loop guard as the running gateway applies it
        (§5.4: its settings file is read when it starts), with what the file says now; while the gateway does not run
        (or one from before it said so runs), the file's, which its next start applies."""
        gateway: Gateway = self.kernel.parts["gateway"]
        doing = gateway.activity(session, False, True)
        settings = gateway.settings()
        written = {"on": settings.loop_guard, "ratio": settings.loop_ratio}
        applied = doing.get("guard")
        guard = {**applied, "file": written} if isinstance(applied, dict) else written
        moment = self.kernel.clock.now().timestamp()
        found = now(session, doing, self.flows.view(workspace, session), gateway.routes(), gateway.facts, guard, moment)
        return {"workspace": workspace, **found}

    def start_job(self, workspace: str, command: str, title: str, minutes: int) -> dict[str, Any]:
        """Start the agent's job (design 0021 §6; `jobs.py`), the session told when it ends being the workspace's
        newest kept, the one that asked."""
        kept = self.flows.flows(workspace)
        session = str(kept[0].get("session") or "") if kept else ""
        return self.jobs.start(workspace, command, title, minutes, session=session)

    def make_artifact(
        self, workspace: str, name: str, title: str, kind: str, files: list[str], note: str
    ) -> dict[str, Any]:
        """Make the agent's artifact (design 0021 §5; `artifacts.py`), the session that made it being the workspace's
        newest kept, the one that asked."""
        kept = self.flows.flows(workspace)
        session = str(kept[0].get("session") or "") if kept else ""
        return self.artifacts.make(workspace, name, title, kind, files, note=note, session=session)

    def all_jobs(self, workspace: str = "") -> list[dict[str, Any]]:
        """The jobs of a workspace's agent, or of every workspace's (`jobs.py`), newest first."""
        if workspace:
            return self.jobs.list(workspace)
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        found = [job for record in workspaces.records() for job in self.jobs.list(str(record["name"]))]
        return sorted(found, key=lambda job: -float(job["started"]))

    def readout(self, folder: str, session: str = "") -> dict[str, Any]:
        """The model's readout for a folder (design 0021 §3; `readout.py`): its workspace's session (the one named,
        else the newest kept), that session's `now` and context totals, and the machine: the main slot, the GPU, the
        drafts."""
        try:
            workspace: str | None = self.annotations.workspace_of(folder)[0]
        except AnnotationError:
            workspace = None
        kept = self.flows.flows(workspace) if workspace else []
        chosen = session or (str(kept[0].get("session") or "") if kept else "")
        named = next((flow for flow in kept if flow.get("session") == chosen), {})
        runtime: Runtime = self.kernel.parts["runtime"]
        machine: Machine = self.kernel.parts["machine"]
        slot = runtime.state.slot("main")
        options = runtime.state.launch(slot.launch_id).options if slot.launch_id is not None else None
        followed = workspace is not None and bool(chosen)
        return {
            "folder": folder,
            "workspace": workspace,
            "session": {"id": chosen, "title": str(named.get("title") or "")} if followed else None,
            "now": self.now(str(workspace), chosen) if followed else None,
            "context": self.context(str(workspace), chosen) if followed else None,
            "slot": slot_view(slot, runtime.title(slot.preset), options),
            "gpu": gpu_view(machine.meters()),
            "drafts": runtime.drafts("main"),
            "jobs": [job for job in self.jobs.list(workspace) if job["state"] != "ended"] if workspace else [],
        }

    def conversation_stream(
        self,
        folder: str,
        session: str,
        limit: int,
        after: int | None,
        closers: set[Callable[[], None]],
        after_session: str = "",
    ) -> AsyncGenerator[str, None]:
        """The conversation pushed as it happens (design 0023 §3, `streaming.py`), for a client of another part (the
        phone's listener, design 0025 §7): a snapshot, then each change of the mirror with its version, the readout
        while the session works; `after` resumes from a version of the session `after_session`."""
        return streaming.conversation_stream(self, folder, session, limit, after, closers, after_session=after_session)

    def conversation(self, folder: str, session: str = "", limit: int = 30, before: str = "") -> dict[str, Any]:
        """The agent panel's conversation for a folder (design 0021 §4), read from the mirror (design 0023 §2,
        decision 0139): its workspace's session (the one named, else the newest kept, else the newest root session
        the watcher saw), the server that reaches it, a page of its messages (the newest `limit`, or those before the
        message `before`) with the message to read before, whether it is busy, and the permissions and questions
        waiting in it. The session is followed from the first read; its history is read from OpenCode once, whole,
        and once more for what the mirror does not hold when a client reads back; the servers are listed once, when
        the watcher has not named the sessions yet. Nothing else starts a process in the container."""
        try:
            workspace: str | None = self.annotations.workspace_of(folder)[0]
        except AnnotationError:
            workspace = None
        nothing: dict[str, Any] = {"folder": folder, "workspace": workspace, "session": None, "messages": [],
                                   "next": "", "waiting": {"permissions": [], "questions": []}}  # fmt: skip
        if workspace is None:
            return nothing
        for gone in {ws for ws, _ in self.mirror.forget()}:
            self.review.watchers.follow(gone, self.mirror.followed(gone))
        kept = self.flows.flows(workspace)
        known = self.mirror.sessions(workspace)
        chosen = session or str((kept[0] if kept else {}).get("session") or (known[0]["id"] if known else ""))
        port = self.sessions.runs(workspace, chosen) if chosen else None
        if port is None and chosen:
            port = self.mirror.port(workspace, chosen)
        if port is None:  # the watcher has not named the sessions (the service just started): list them once
            try:
                self.mirror.learn(workspace, self.sessions.servers(workspace))
            except Exception:  # the container does not answer: nothing to read
                return nothing
            known = self.mirror.sessions(workspace)
            chosen = chosen or (str(known[0]["id"]) if known else "")
            port = self.mirror.port(workspace, chosen) if chosen else None
        if not chosen or port is None:
            return nothing
        if chosen not in self.mirror.followed(workspace):
            self.mirror.follow(workspace, chosen)
            self.review.watchers.follow(workspace, self.mirror.followed(workspace))
        found = self.mirror.conversation(workspace, chosen, limit, before)
        if found is None:  # its history, once
            self.mirror.merge(workspace, chosen, self.sessions.page(workspace, port, chosen, limit=limit, whole=True))
            found = self.mirror.conversation(workspace, chosen, limit, before)
        if found is not None and before and found["from_opencode"] and len(found["messages"]) < limit:
            # a client reads back past what the mirror holds: that page from OpenCode, once, kept
            older = self.sessions.page(workspace, port, chosen, limit=limit, before=found["from_opencode"], whole=True)
            self.mirror.merge(workspace, chosen, older)
            found = self.mirror.conversation(workspace, chosen, limit, before)
        if found is None:
            return nothing
        named: dict[str, Any] = next((flow for flow in kept if flow.get("session") == chosen), {})
        return {
            **nothing,
            "session": {
                "id": chosen,
                "title": str(found["title"] or named.get("title") or ""),
                "port": port,
                "busy": found["busy"],
            },
            "messages": found["messages"],
            "next": found["next"],
            "waiting": found["waiting"],
        }

    def figures(self, workspace: str, session: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """A session's context totals, with its parts (their items' steps from its flow, design 0012 §4.2), and the
        gateway's requests of it that ended (the Guide's costs, design 0012 §9.1)."""
        gateway: Gateway = self.kernel.parts["gateway"]
        doing = gateway.activity(session, False, True)
        adapter, margin = self._adapter("opencode"), self.opencode_settings().context_margin

        def rule(window: int, output: int) -> Compaction | None:
            return adapter.compaction(window, output, kept_margin(margin, window))

        found = totals(session, doing, gateway.routes(), gateway.facts, rule, self.flows.view(workspace, session))
        return found, list(doing.get("ended") or [])

    def opencode_settings(self) -> OpenCodeSettings:
        """What OpenCode is told of its model, as `config/opencode.json` says now (decision 0089)."""
        return OpenCodeSettings.model_validate(self.kernel.settings.get("opencode", "opencode").record.model_dump())

    def model_changed(self, workspace: str, *, by: str, besides: Collection[str] = (), actor: Actor) -> dict[str, Any]:
        """Tell the owner's window in the workspace that the model it talks to changed (design 0013 §7, decision
        0062): `by` (a flow's box, in words) switched the main slot. The model now and its limits, whether a window
        runs there, and each root session of the workspace's servers that is not one of `besides` (the flows' boxes')
        whose context holds more tokens than the model's context, as too small for it: said in the event
        `agents.model_changed` and kept as the workspace's notice until OpenCode is next started there."""
        model, _ = self._model()
        try:
            window = any(server.get("terminal") for server in self.sessions.servers(workspace))
        except SessionError:
            window = False
        too_small = []
        for seen in self.sessions.seen(workspace):
            if seen["parent"] or seen["port"] is None or seen["session"] in besides:
                continue
            holds = self.context(workspace, str(seen["session"])).get("used")
            if isinstance(holds, int) and holds > model.context:
                title = seen["title"] or seen["session"]
                too_small.append({"session": seen["session"], "title": title, "holds": holds})
        sizes = f"{model.context:,} tokens of context, {model.output:,} out"
        said = f"{by} switched the main slot to {model.title} ({sizes}): " + (
            f"your OpenCode window in {workspace} talks to it from its next step, with the limits it started with "
            "until it next starts"
            if window
            else f"the next OpenCode started in {workspace} gets it"
        )
        for each in too_small:
            said += f"; {model.title} is too small for your session {each['title']}, which holds "
            said += f"{each['holds']:,} tokens"
        notice = {"workspace": workspace, "title": model.title, "context": model.context, "output": model.output,
                  "window": window, "by": by, "too_small": too_small, "said": said,
                  "time": to_text(self.kernel.clock.now())}  # fmt: skip
        with self._notices_lock:
            self._notices[workspace] = notice
        self.kernel.events.record(
            "agents.model_changed",
            summary=said,
            actor=actor,
            subject=Subject(kind="workspace", id=workspace),
            data={key: notice[key] for key in ("workspace", "title", "context", "output", "window", "by", "too_small")},
        )
        return notice

    def model_notice(self, workspace: str) -> dict[str, Any] | None:
        """What the owner's window in the workspace was told of its model's last change, until OpenCode is next started
        there; None when nothing is to be told."""
        with self._notices_lock:
            found = self._notices.get(workspace)
            return dict(found) if found is not None else None

    def plan(self, program: str = "opencode") -> dict[str, Any]:
        """What the program would be given, writing nothing: its model, that model's limits, and notes."""
        adapter = self._adapter(program)
        model, notes = self._model()
        return {"program": adapter.LABEL, "model": model.title, "limits": limits(model), "notes": notes}

    def prepare(self, workspace: str, program: str = "opencode") -> dict[str, Any]:
        """Write the program's configuration into the workspace's container; the command that starts it there. With one
        window at a time (the workspace's record, design 0004 §5), the OpenCode windows open there are closed first.
        The edge, the agent's way to the model, is put right first (design 0004 §3), and what was put right is said in
        the notes. The container is asked of Docker once and every file goes in one `docker exec` (a VS Code window
        waits for this answer before OpenCode starts: nine writes of one `docker exec` each took most of it,
        2026-10-26)."""
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        adapter = self._adapter(program)
        container = workspaces.container_of(workspace)
        model, notes = self._model(workspace)
        notes += workspaces.reach(workspace)
        servers = self._given(workspace, model.key)
        configuration = adapter.configuration(model, servers, self._read_only(workspace))
        workspaces.put_files(workspace, [*self._agent_files(), *adapter.files(), configuration], container=container)
        with self._notices_lock:  # its configuration has the model's limits now: nothing more to tell its window
            self._notices.pop(workspace, None)
        one_window = bool(self.kernel.settings.get("workspace", workspace).record.model_dump().get("one_window", True))
        closed = self.sessions.close_windows(workspace) if one_window else 0
        if closed:
            windows = "the OpenCode window" if closed == 1 else f"the {closed} OpenCode windows"
            notes.append(f"closed {windows} open in {workspace} first: one at a time (w on This folder changes that)")
        port = self._port(workspace, notes)
        env = {**adapter.env(), **workspaces.agent_env(workspace)}
        argv = workspaces.exec_argv(workspace, adapter.argv(port), env, container=container)
        if port is not None:
            for told in list(self._prepared):
                told(workspace, port)
        return {
            "workspace": workspace,
            "container": container,
            "program": adapter.LABEL,
            "model": model.title,
            "limits": limits(model),
            "servers": sorted(servers),
            "port": port,
            "argv": argv,
            "one_window": one_window,
            "closed": closed,
            "notes": notes,
        }

    def agent_env(self, workspace: str, program: str = "opencode") -> dict[str, str]:
        """The environment an agent program runs with in the workspace (one started without a terminal too)."""
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        return {**self._adapter(program).env(), **workspaces.agent_env(workspace)}

    def configure(self, workspace: str, program: str = "opencode") -> dict[str, str]:
        """Write the program's configuration (the model, the MCP servers it gets) as `prepare` does, for one started
        without a terminal (design 0005 §2), the edge put right first as there; the environment it runs with."""
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        adapter = self._adapter(program)
        model, _ = self._model(workspace)
        container = workspaces.container_of(workspace)  # refused first when its container does not run
        workspaces.reach(workspace)
        configuration = adapter.configuration(model, self._given(workspace, model.key), self._read_only(workspace))
        workspaces.put_files(workspace, [*self._agent_files(), *adapter.files(), configuration], container=container)
        return self.agent_env(workspace, program)

    def _agent_files(self) -> list[tuple[str, str]]:
        """Clank's MCP server and instructions, as this Clank has them, for the agent's home in the container."""
        from clank.components.workspaces.service import agent_files

        return list(agent_files())

    def _port(self, workspace: str, notes: list[str]) -> int | None:
        """A port of its own for the program's API, so its session can be reached (design 0005 §2); None, and why in
        the notes, when the container cannot say (an image from before the bridge)."""
        try:
            return self.sessions.free_port(workspace)
        except SessionError as error:
            notes.append(f"its session cannot be followed from other clients: {error}")
            return None

    def servers(self, workspace: str) -> list[dict[str, Any]]:
        """The MCP servers of a workspace's agent: yours, then its folder's, each with whether the agent gets it and,
        when not, why (design 0004 §10)."""
        from clank.components.workspaces.service import PHONE_PROGRAM

        loaded = self._workspace(workspace)
        record = loaded.record.model_dump()
        tools: Tools = self.kernel.parts["tools"]
        held = CLANK_SERVER in record["mcp_off"]
        rows: list[dict[str, Any]] = [{
            "name": CLANK_SERVER, "scope": "clank", "transport": "stdio", "shown": f"python3 {PHONE_PROGRAM}",
            "given": not held, "why": "held back from this workspace (m gives it)" if held else "",
        }]  # fmt: skip
        mine = {view["name"] for view in tools.servers() if view["scope"] == "user"} | {CLANK_SERVER}
        for view in tools.servers(record["path"]):
            if view["name"] == CLANK_SERVER:
                continue  # Clank's own has the name

            name, scope = view["name"], view["scope"]
            fingerprint = ""
            if scope == "project":  # a project's server has no secret: reading it records no use
                fingerprint = _fingerprint(tools.runnable(name, record["path"], scope, why="").entry())
            if view["transport"] != "stdio":
                why = "reached by address: nothing but the model is reachable from the container yet"
            elif scope == "user" and view.get("local_only") and record.get("models") == "cloud":
                why = LOCAL_ONLY  # design 0016 §10: what it gives the agent never goes to the cloud model
            elif scope == "user":
                why = "held back from this workspace (m gives it)" if name in record["mcp_off"] else ""
            elif name in mine:
                why = "it has the name of one of yours, which the agent gets instead"
            elif name not in record["mcp_allowed"]:
                why = "this folder's own (.mcp.json): not allowed yet (m allows it)"
            elif record["mcp_allowed"][name] != fingerprint:
                why = "its entry changed since you allowed it: allow it again (m)"
            else:
                why = ""
            shown = view["command"] if view["transport"] == "stdio" else view["url"]
            rows.append({
                "name": name, "scope": scope, "transport": view["transport"], "shown": " ".join([shown, *view["args"]]),
                "given": not why, "why": why,
            })  # fmt: skip
        return rows

    def live(self, workspace: str) -> list[dict[str, Any]]:
        """The servers with their state and their last check's tools (`state`, `problem`, `agents`, `checked`)."""
        rows = self.servers(workspace)
        tools: Tools = self.kernel.parts["tools"]
        folder = self._workspace(workspace).record.model_dump()["path"]
        try:
            running, problem = self.sessions.mcp(workspace), ""
        except SessionError as error:
            running, problem = None, str(error)
        for row in rows:
            status = (running or {}).get(row["name"], {})
            row["agents"] = running is not None
            row["problem"] = row["why"] or status.get("error", "") or (problem if row["given"] else "")
            if running is None:
                row["state"] = "on" if row["given"] else "off"
            else:
                row["state"] = STATES.get(status.get("status", ""), "stopped")
            row["checked"] = tools.checked(row["name"], row["scope"], folder)
        return rows

    def switch(self, workspace: str, name: str, on: bool, *, actor: Actor) -> dict[str, Any]:
        """Start an MCP server for the workspace's agent or stop it: given or taken away for its next start, and
        connected or disconnected now in the agents that run (`applied`: now, or at the agent's next start)."""
        row = self.allow(workspace, name, on, actor=actor)
        if on and not row["given"]:
            return {**row, "applied": "", "problem": row["why"]}
        config: dict[str, Any] = {}
        if on:
            config = dict(self._adapter("opencode").server_entry(self._given(workspace)[name]))
        try:
            count = self.sessions.mcp_switch(workspace, name, on, config, actor=actor)
        except SessionError as error:
            return {**row, "applied": "at the agent's next start", "problem": str(error)}
        return {**row, "applied": "now" if count else "at the agent's next start", "problem": ""}

    def box_tools(self, workspace: str, port: int, wanted: list[str] | None) -> dict[str, Any]:
        """A flow's box's MCP servers, on the flow's OpenCode server on `port` alone (design 0013 §4): those it names
        (`wanted`; None or empty: every one the workspace's agent gets), Clank's own always (it carries the flow's
        tools), connected, every other disconnected; only what differs from that server's state now is changed. A name
        the workspace's agent does not get is refused (`AgentError`), saying why; one the bridge fails to connect or
        disconnect is said and the others still change. What is connected now, what was started and stopped, each that
        failed to connect with why (`failed`), and each that stays connected as it failed to disconnect (`kept`)."""
        rows = self.servers(workspace)
        given = {row["name"] for row in rows if row["given"]}
        for name in wanted or []:
            if name not in given:
                row = next((row for row in rows if row["name"] == name), None)
                why = row["why"] if row is not None else "it is no MCP server of yours or of the folder"
                raise AgentError(f"it names the MCP server {name}, which {workspace}'s agent does not get: {why}")
        chosen = set(wanted) | ({CLANK_SERVER} & given) if wanted else given
        state = self.sessions.mcp_on(workspace, port)
        started: list[str] = []
        stopped: list[str] = []
        said: dict[str, str] = {}  # what the bridge said of one it could not connect or disconnect
        entries: dict[str, Server] | None = None
        for name in sorted(given | set(state)):
            connected = state.get(name, {}).get("status") == "connected"
            on = name in chosen
            if on == connected:
                continue
            config: dict[str, Any] = {}
            if on and name not in state:  # not in its configuration: added with its entry
                entries = entries if entries is not None else self._given(workspace)
                config = dict(self._adapter("opencode").server_entry(entries[name]))
            try:
                self.sessions.mcp_switch_on(workspace, port, name, on, config)
            except SessionError as error:  # an HTTP error of OpenCode's, or a connect past its time
                said[name] = str(error)
                continue
            (started if on else stopped).append(name)
        now = self.sessions.mcp_on(workspace, port) if started or stopped or said else state
        connected_now = sorted(name for name, status in now.items() if status.get("status") == "connected")
        failed = {
            name: said.get(name) or now.get(name, {}).get("error") or now.get(name, {}).get("status")
            or "it did not connect"
            for name in sorted(chosen)
            if name not in connected_now
        }  # fmt: skip
        kept = {name: why for name, why in sorted(said.items()) if name not in chosen and name in connected_now}
        return {"connected": connected_now, "started": started, "stopped": stopped, "failed": failed, "kept": kept}

    def allow(self, workspace: str, name: str, given: bool, *, actor: Actor) -> dict[str, Any]:
        """Give a server to a workspace's agent, or take it away: one of yours is held back or not; the folder's own is
        allowed as its entry is now (its fingerprint kept), or not."""
        loaded = self._workspace(workspace)
        record = loaded.record.model_dump()
        row = next((row for row in self.servers(workspace) if row["name"] == name), None)
        if row is None:
            raise AgentError(f"{name} is not an MCP server of yours or of {record['path']}")
        if row["scope"] in ("user", "clank"):
            off = [held for held in record["mcp_off"] if held != name]
            record["mcp_off"] = off if given else sorted({*off, name})
        else:
            tools: Tools = self.kernel.parts["tools"]
            allowed = {key: value for key, value in record["mcp_allowed"].items() if key != name}
            if given:
                allowed[name] = _fingerprint(tools.runnable(name, record["path"], "project", why="").entry())
            record["mcp_allowed"] = allowed
        self.kernel.settings.write("workspace", workspace, record, base=loaded.revision, actor=actor)
        return next(row for row in self.servers(workspace) if row["name"] == name)

    def _given(self, workspace: str, key: str | None = None) -> dict[str, "Server"]:
        """The servers the agent gets, each with its secrets' values (each use recorded); Clank's own with the
        workspace's key at the gateway (`key`, else read), and told to list no Notion tool when the workspace may use
        the cloud model (design 0016 §10)."""
        from clank.components.tools.service import Server
        from clank.components.workspaces.service import CURRENT_PHONE

        tools: Tools = self.kernel.parts["tools"]
        record = self._workspace(workspace).record.model_dump()
        folder = record["path"]
        given = {}
        for row in self.servers(workspace):
            if not row["given"]:
                continue
            if row["scope"] == "clank":  # it reaches the gateway (vision, Notion) as the agent does: by the edge
                gateway: Gateway = self.kernel.parts["gateway"]
                address = {
                    "CLANK_GATEWAY": f"http://edge:{gateway.settings().port}/v1",
                    "CLANK_WORKSPACE_NAME": workspace,
                    "CLANK_GATEWAY_KEY": key or gateway.workspace_key(workspace, why=f"Clank's server in {workspace}"),
                    **({"CLANK_NOTION": "off"} if record.get("models") == "cloud" else {}),
                }
                given[row["name"]] = Server("stdio", command="python3", args=[CURRENT_PHONE], env=address)
            else:
                given[row["name"]] = tools.runnable(row["name"], folder, row["scope"], why=f"the agent of {workspace}")
        return given

    def _read_only(self, workspace: str) -> dict[str, list[str]]:
        """Each server the agent gets, with the tools its last check marks read-only: all the planner may use of it
        (design 0009 §3); none for a server never checked, or changed since its check; Clank's own, its reading of
        Notion (design 0010 §4) and a box's tools of its flow (design 0013 §9)."""
        tools: Tools = self.kernel.parts["tools"]
        folder = self._workspace(workspace).record.model_dump()["path"]
        found: dict[str, list[str]] = {}
        for row in self.servers(workspace):
            if row["given"] and row["scope"] == "clank":
                found[row["name"]] = [*CLANK_READ_ONLY, *CLANK_FLOW_TOOLS]  # Clank's own: known, never checked
            elif row["given"]:
                checked = tools.checked(row["name"], row["scope"], folder) or {}
                found[row["name"]] = [tool["name"] for tool in checked.get("tools", []) if tool.get("read_only")]
        return found

    def _workspace(self, workspace: str) -> "Loaded":
        try:
            return self.kernel.settings.get("workspace", workspace)
        except SettingsError as error:
            raise AgentError(f"there is no workspace {workspace!r}: `clank workspace open` makes one") from error

    def _adapter(self, program: str) -> AgentProgram:
        try:
            return AGENT_PROGRAMS.get(program)()
        except AdapterError as error:
            raise AgentError(str(error)) from error

    def _model(self, workspace: str | None = None) -> tuple[AgentModel, list[str]]:
        """The model the role's slot runs, reached at the gateway through the edge, with its limits; modest limits,
        said, when no model runs; for a workspace, with its own key at the gateway (design 0016 §9)."""
        gateway: Gateway = self.kernel.parts["gateway"]
        routes = gateway.routes()
        slot = routes["slots"].get(routes["roles"].get(ROLE, routes["default_slot"])) or {}
        notes: list[str] = []
        context, output = slot.get("context"), slot.get("output")
        if not context or not output:
            context, output = FALLBACK
            notes.append(f"no model runs: its limits are {context:,} and {output:,} tokens until one does")
        model = AgentModel(
            url=f"http://edge:{gateway.settings().port}/v1",
            name=ROLE,
            title=str(slot.get("title") or "the model Clank runs"),
            context=int(context),
            output=int(output),
            images=self.reads_images(),
            margin=kept_margin(self.opencode_settings().context_margin, int(context)),
            key=gateway.workspace_key(workspace, why=f"OpenCode's configuration in {workspace}")
            if workspace
            else "local",
        )
        return model, notes

    def add_model_guide(self, preset: str = "", folder: str = "") -> dict[str, Any]:
        """Add a model's steps and words (design 0016 §14, `GET /runtime/guide`): served here, where the runtime, this
        computer, the MCP servers (the folder's too), Docker and the limits can all be read; the words are the
        runtime's."""
        runtime: Runtime = self.kernel.parts["runtime"]
        machine: Machine = self.kernel.parts["machine"]
        tools: Tools = self.kernel.parts["tools"]
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        gateway: Gateway = self.kernel.parts["gateway"]
        from clank.components.runtime.service import machine_said

        readings = machine.meters()
        said = machine_said(readings[-1] if readings else None, machine.profile().model_dump(mode="json"))
        limits = gateway.cost_settings().model_dump()
        servers = [server["name"] for server in tools.servers(folder)]
        return runtime.guide(servers=servers, machine=said, docker=str(workspaces.docker()["state"]), limits=limits,
                             preset=preset)  # fmt: skip

    def give_local_only(self) -> list[str]:
        """Give the gateway the names of the tools that never go to a cloud model (design 0016 §10, decision 0111):
        Clank's Notion tools, and each tool of a server marked local only, as OpenCode names them (`<server>_<tool>`,
        its unsafe characters made `_`); the prefixes given."""
        tools: Tools = self.kernel.parts["tools"]
        prefixes = [NOTION_PREFIX, *sorted(f"{UNSAFE.sub('_', name)}_" for name in tools.local_only())]
        gateway: Gateway = self.kernel.parts["gateway"]
        gateway.set_local_only(prefixes)
        return prefixes

    def _heard_tools(self, event: Any) -> None:
        """An MCP server added, removed or changed (its local mark among them): the gateway is given the names again."""
        if event.type == "mcp.changed" or (event.type == "settings.changed" and event.data.get("kind") == "mcp-server"):
            self.give_local_only()

    def reads_images(self) -> bool:
        """Whether the agent's model reads images: its slot's preset sees them, and vision is not off (design 0008
        §5, §7)."""
        gateway: Gateway = self.kernel.parts["gateway"]
        routes = gateway.routes()
        slot = routes["slots"].get(routes["roles"].get(ROLE, routes["default_slot"])) or {}
        return bool(slot.get("images")) and gateway.vision_settings().mode != "off"

    def _read_image(self, image: bytes, question: str) -> str:
        """The vision model's reading of an image (design 0008 §7), "" when there is none."""
        gateway: Gateway = self.kernel.parts["gateway"]
        return gateway.look(image, question)

    def operation_types(self) -> list["OperationType"]:
        """Opening a folder in Clank's VS Code window (`vscode.py`)."""
        from clank.components.agents import vscode

        return vscode.operation_types(self.kernel)

    def router(self) -> Any:
        """The agents' routes."""
        from clank.components.agents.api import router

        return router(self)
