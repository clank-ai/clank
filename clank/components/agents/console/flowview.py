"""The Monitor's Flow view (design 0013 §12, boards D1-D4): `FlowViewer`, the Flow view's part of the page, which the
Monitor (`monitor.py`) composes and hands its ticks and keys while the Flow view is on screen.

**Board D1, a flow running.** The flow the folder follows (`GET /flows/view`, made in the service by
`clank/components/flows/view.py`) is read once a second while the view is on screen (`FlowReading`, one reading at a
time, none drawn when its version did not move), and drawn on the page's next tick, so the page redraws at most four
times a second (design 0012 §2). Its panels: **Flow** (`BoxChart`, its note how many boxes are done, running and
waiting), **Selected** (the box chosen, with a **Live** box inside it while a model's box runs: what its session does
now, read on every tick while it works, as the Session view reads it, and its context window, read with the flow),
**Models in this flow** and **Waiting for you** beside it; under it **The brief, checked** (its note how many lines are
met), **Deliverables** and **Ahead** (`flowpanels.py`). Narrower than `STACK_BELOW` columns the panels beside the flow
move under it; narrower than 70 the flow is a list (`boxchart.LIST_BELOW`). With no flow, every panel says so and the
heading says why. Nothing is read while the page is not on screen or another view is.

**A flow built with the model** (design 0013 §15, decisions 0100 and 0101): `n` starts a planning beside the console,
never in its terminal (`clank.kernel.where.console_opening`: over SSH nothing opens and the view says to run `clank
flow attach` in another terminal; in Windows Terminal its window is split, OpenCode in the pane on the right; in VS
Code's terminal, or with `N`, Clank's VS Code window); a planning open already is set aside only once asked first, and
`n` pressed again while one starts does nothing. While the planning is open the view draws it (its steps in Selected's
place, its latest draft marked DRAFT, a Live box for its session; Enter opens that session). `r` on a flow that has
not run starts it from its first box, once confirmed.
"""

import os
import sys
import time
from collections.abc import Callable, Sequence
from datetime import tzinfo
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from textual.containers import Vertical
from textual.content import Content
from textual.widget import Widget

from clank.client import ClientError, NotRunning
from clank.components.agents.console import boxchart, boxpanel, flowboards, flowpanels
from clank.components.agents.console.boxchart import tag
from clank.components.agents.console.boxpanel import BoxChart, CardsView, FlowList
from clank.components.agents.console.following import FlowReading, Watching
from clank.console import actions
from clank.console.confirm import ConfirmScreen
from clank.console.details import DetailsScreen
from clank.console.editor import EditScreen
from clank.console.form import Field, FormScreen
from clank.console.keys import PageKey
from clank.console.panel import Panel, PanelGrid
from clank.console.pick import Choice, PickScreen
from clank.console.text import clock, parse
from clank.kernel import where as places

if TYPE_CHECKING:
    from clank.components.agents.console.monitor import MonitorPage

READ_SECONDS = 1.0  # how often the flow is read while the view is on screen, and what its running box does at rest
STACK_BELOW = 100  # columns: narrower, the panels beside the flow move under it (design 0013 §12, "Room")
OWNERS = ("you", "gate")
PLANNING = "planning"  # what the Session view was opened from: the planning's session, not a box's
BUILDING = "Building it with the model"  # Selected's title while a planning is shown (decision 0101)
DRAFTING = "the model has drafted no flow yet"  # the Flow panel, while a planning has no draft
NO_FLOW = ("No flow yet", "reading this folder's flows")
BOARDS = ("d1", "d2", "d3", "d4")  # board D1, the flow running; D2, a box's settings; D3, a gate; D4, proposals
BOARD_KEYS = {
    "d2": (
        *(PageKey(key, f"set_{field}", label.lower()) for key, field, label in flowboards.FIELDS),
        PageKey("v", "first_message", "first message", "the box's whole first message, as it would be sent now"),
        PageKey("s", "save", "save", "save the changes into the flow's file"),
        PageKey("escape", "back", "back to the flow", "board D1, asked first when a change is not saved"),
    ),
    "d3": (
        PageKey("a", "approve", "approve or go on", "approve the gate, or go on: the flow goes on"),
        PageKey(
            "e", "edit", "edit, then approve", "the file opens in Clank's VS Code window; a approves it once saved"
        ),
        PageKey("s", "send_back", "send back", "send the box back with a note: its next try gets it"),
        PageKey("d", "diff", "diff", "the file's last two tries, compared"),
        PageKey("x", "stop", "stop the flow", "the run ends here, asked first"),
        PageKey("escape", "back", "back to the flow", "board D1"),
    ),
    "d4": (
        PageKey("a", "accept", "accept", "the card highlighted joins the flow"),
        PageKey("e", "edit", "edit", "the card highlighted's prompt, in a window; it stays waiting"),
        PageKey("r", "reject", "reject", "the card highlighted never runs"),
        PageKey("A", "accept_all", "accept all", "every card still waiting joins the flow, in its order"),
        PageKey("escape", "back", "back to the flow", "board D1"),
    ),
}  # the keys each board's keys bar shows


FOCUS = {
    "d1": "#monitor-flow-chart-boxes",
    "d2": "#monitor-flow-d2-list-view",
    "d3": "#monitor-flow-d3-decision",
    "d4": "#monitor-flow-d4-cards-view",
}  # what has the focus when a board comes on screen
KEPT = "Ctrl+S keeps it, not saved until s; Esc leaves it."
TYPES = ("task", "plan", "verify", "decompose", "integrate", "gate", "you")
PICKS = {
    "type": [Choice(each, each.upper()) for each in TYPES],
    "mode": [
        Choice("", "the workspace's", "or its type's: plan for PLAN, VERIFY, DECOMPOSE and INTEGRATE"),
        *(Choice(each, each, flowboards.MODE_WORDS[each]) for each in ("plan", "review", "auto")),
    ],
    "when_done": [
        Choice("go on", "go on", "the box after it starts"),
        Choice("wait", "wait", "the flow waits for you"),
    ],
}  # board D2's fields picked from a list


def _listed(values: dict[str, Any], name: str) -> str:
    return ", ".join(str(each) for each in values.get(name) or [])


def _split(text: str) -> list[str]:
    return [part.strip() for part in text.split(",") if part.strip()]


def form_fields(field: str, label: str, values: dict[str, Any]) -> list[Field]:
    """The form that edits one of board D2's fields of words, numbers or lists."""
    if field == "writes":
        return [
            Field("writes", "The files it writes, from the folder, separated by commas", "runs/estimates.md",
                  _listed(values, "writes")),
            Field("holds", "What they hold, in words", "a table: grid point, CPU-hours, method",
                  str(values.get("holds") or "")),
        ]  # fmt: skip
    if field == "limits":
        limits = values.get("limits") or {}
        return [
            Field("minutes", "Minutes a try may run (empty: the flow's)", "30", str(limits.get("minutes") or "")),
            Field("tokens", "Tokens a try may write (empty: the flow's)", "200000", str(limits.get("tokens") or "")),
        ]
    if field == "tries":
        return [Field("tries", "Tries before a gate decides (empty: the flow's)", "3", str(values.get("tries") or ""))]
    if field == "mcp_servers":
        servers = values.get("mcp_servers")
        return [Field("servers", "Its MCP servers, separated by commas (empty: those the workspace's agent gets)",
                      "myproject-mcp", "" if servers is None else ", ".join(servers))]  # fmt: skip
    if field == "sees":
        name = "shows" if values.get("type") == "gate" else "sees"
        return [
            Field(name, "The files its first message hands it, separated by commas", "PLAN.md", _listed(values, name))
        ]
    return [Field(field, label, "", str(values.get(field) or ""))]


def form_values(field: str, answer: dict[str, str]) -> dict[str, Any]:
    """A D2 form's answer as the box's fields it changes."""
    if field == "writes":
        return {"writes": _split(answer.get("writes", "")), "holds": answer.get("holds", "")}
    if field == "limits":
        return {"limits": {key: int(answer[key]) for key in ("minutes", "tokens") if answer.get(key, "").isdigit()}}
    if field == "tries":
        text = answer.get("tries", "")
        return {"tries": int(text) if text.isdigit() else None}
    if field == "mcp_servers":
        text = answer.get("servers", "")
        return {"mcp_servers": _split(text) if text.strip() else None}
    if field == "sees":
        name = next(iter(answer))
        return {name: _split(answer[name])}
    return {field: answer.get(field, "")}


class LiveBox(Vertical):
    """The Live box inside Selected (board D1): a box drawn in the panels' border, titled Live, shown while a model's
    box runs."""

    DEFAULT_CSS = """
    LiveBox {
        height: auto;
        border: $clank-border-kind $clank-border;
        border-title-color: $clank-now;
        padding: 0 1;
        margin: 1 0 0 0;
    }
    """


def panel(widget: Widget, title: str, id: str, board: str = "d1") -> Panel:
    """A panel of the Flow view's board."""
    return Panel(widget, title=title, id=id, classes=f"view-flow board-{board}")


def heading(view: dict[str, Any] | None, zone: tzinfo | None) -> Content:
    """The Flow view's heading line: the flow, its workspace, its run, its start and where it is; or, while it is built
    with the model, that, and the draft it shows; or why none is shown."""
    if view is None:
        return Content.assemble((NO_FLOW[0], "bold"), (f" · {NO_FLOW[1]}", "$clank-quiet"))
    if not view.get("flow"):
        return Content.assemble((NO_FLOW[0], "bold"), (f" · {view.get('why') or NO_FLOW[1]}", "$clank-quiet"))
    if view.get("planning"):
        draft = view.get("draft")
        shows = f"DRAFT {draft['number']}, {draft['state']}" if draft else "no draft yet"
        named = (f"“{view['title']}”", "$clank-name")  # what it is first: a narrow heading keeps the start
        return Content.assemble(("flow ", "bold"), named, (f" · building with the model · {shows}", "bold"),
                                " · workspace ", (str(view["workspace"]), "$clank-name"))  # fmt: skip
    run = view.get("run")
    facts = [f"run {run['number']}", f"started {clock(parse(run['created']), zone)}", _where(view)] if run else []
    cost = (view.get("cost") or {}).get("said")  # the cloud's, in the service's words (design 0016 §11)
    facts += [f"cost so far {cost}"] if cost else []
    said = (" · " + " · ".join(fact for fact in facts if fact)) if run else " · not run yet"
    said += f" · cost so far {cost}" if cost and not run else ""
    named = (f"“{view['title']}”", "$clank-name")
    workspace = (str(view["workspace"]), "$clank-name")
    return Content.assemble(("flow ", "bold"), named, " · workspace ", workspace, (said, "$clank-quiet"))


def _where(view: dict[str, Any]) -> str:
    run = view.get("run") or {}
    if run.get("status") == "queued":
        return f"queued behind {run.get('behind')}"
    if run.get("status") in ("done", "stopped"):
        return str(run["status"])
    asking = next((box for box in view.get("boxes") or [] if box.get("asks")), None)
    if asking is not None:
        return f"waiting for you: {asking['type'].upper()}"
    running = [box["id"] for box in view.get("boxes") or [] if box["state"] == "running"]
    paused = " · paused" if run.get("paused") else ""
    return (f"running: {', '.join(running)}" if running else f"at {run.get('at')}") + paused


def _when(text: str | None, zone: tzinfo | None) -> str:
    return clock(parse(text), zone) if text else ""


def counts(view: dict[str, Any] | None) -> str:
    """The Flow panel's note: how many boxes are done, running and waiting (and in the other states); while the flow is
    built with the model, the draft it shows."""
    if (view or {}).get("planning"):
        draft = (view or {}).get("draft")
        if not draft:
            return "no draft yet"
        problems = len(draft.get("problems") or [])
        many = f": {problems} problem{'s' if problems != 1 else ''}" if problems else ""
        return f"DRAFT {draft['number']} · {draft['state']}{many}"
    said = (view or {}).get("counts") or {}
    return " · ".join(f"{count} {state}" for state, count in said.items())


def now_box(view: dict[str, Any] | None) -> str:
    """The box the flow is at: the one running or asking you, else the box the run is at, else the first waiting."""
    boxes = (view or {}).get("boxes") or []
    for box in boxes:
        if box["state"] == "running" or box.get("asks"):
            return str(box["id"])
    at = str(((view or {}).get("run") or {}).get("at") or "")
    if at and any(box["id"] == at for box in boxes):
        return at
    return next((str(box["id"]) for box in boxes if box["state"] in ("waiting", "proposed")), "")


def running_box(view: dict[str, Any] | None) -> str | None:
    """The model's box running now, if any."""
    found = running_session(view)
    if found is None:
        return None
    return next((str(box["id"]) for box in (view or {}).get("boxes") or [] if box["state"] == "running"
                 and box["type"] not in OWNERS), None)  # fmt: skip


def running_session(view: dict[str, Any] | None) -> tuple[str, str, int] | None:
    """The session of the model's box running now, or of the planning shown (decision 0101): its workspace, its id and
    its server's port; None for none."""
    planned = ((view or {}).get("planning") or {}).get("session")
    if planned and planned.get("session"):
        return str(planned["workspace"]), str(planned["session"]), int(planned.get("port") or 0)
    for box in (view or {}).get("boxes") or []:
        if box["state"] == "running" and box["type"] not in OWNERS and box["tries"]:
            session = box["tries"][-1].get("session") or {}
            if session.get("session"):
                return str(session["workspace"]), str(session["session"]), int(session.get("port") or 0)
    return None


class FlowViewer:
    """The Flow view of the Monitor: its panels, its readings, its ticks and its keys."""

    def __init__(self, page: "MonitorPage") -> None:
        self.page = page
        self.view: dict[str, Any] | None = None  # the flow as last drawn
        self.now: dict[str, Any] | None = None  # what the running box's session does now, as last read
        self.context: dict[str, Any] | None = None  # its context window, as last read
        self.redraws = 0  # ticks on which the view drew something: a test counts them
        self._reading: FlowReading | None = None
        self._watching: Watching | None = None
        self._came: dict[str, Any] | None = None
        self._now_came: tuple[str, dict[str, Any]] | None = None
        self._context_came: tuple[str, dict[str, Any]] | None = None
        self._read_at = self._now_at = -READ_SECONDS
        self.opened_from = ""  # the box whose session the Session view was opened on (Esc comes back to it)
        self.board = "d1"  # the board shown: D1, or a board of what a box holds
        self.gate = ""  # the gate board D3 shows
        self.edited = ""  # the box board D2 shows
        self.values: dict[str, Any] | None = None  # the flow's file as read for D2, and its revision
        self.revision = ""
        self.changed: dict[str, dict[str, Any]] = {}  # D2's changes not saved, by box: each field's new value
        self.copy: dict[str, Any] | None = None  # what it shows, as its try kept it, and how much it changed
        self.starting = False  # a planning being started: `n`, `N` and `f` do nothing meanwhile

    def compose(self) -> list[Widget]:
        """Board D1's panels, as the website draws them (decision 0125): the flow across the whole width; under it
        Selected (with its Live box) beside Waiting for you, then the Orchestrator beside Models in this flow; then The
        brief, checked, Deliverables and Ahead."""
        live = LiveBox(flowpanels.LinesView(id="monitor-flow-live-lines"), id="monitor-flow-live")
        live.border_title = "Live"
        live.display = False
        return [
            panel(BoxChart(id="monitor-flow-chart-boxes"), "Flow", "monitor-flow-boxes"),
            PanelGrid(
                Panel(
                    flowpanels.LinesView(id="monitor-flow-selected-lines"),
                    live,
                    title="Selected",
                    id="monitor-flow-selected",
                    classes="view-flow board-d1",
                ),
                panel(flowpanels.LinesView(id="monitor-flow-waiting-lines"), "Waiting for you", "monitor-flow-waiting"),
                columns="1fr 1fr",
                stack_below=STACK_BELOW,
                classes="view-flow board-d1",
            ),
            PanelGrid(
                panel(
                    flowpanels.LinesView(id="monitor-flow-orchestrator-lines"),
                    "Orchestrator",
                    "monitor-flow-orchestrator",
                ),
                panel(
                    flowpanels.LinesView(id="monitor-flow-models-lines"), "Models in this flow", "monitor-flow-models"
                ),
                columns="1fr 1fr",
                stack_below=STACK_BELOW,
                classes="view-flow board-d1",
            ),
            panel(flowpanels.LinesView(id="monitor-flow-brief-lines"), "The brief, checked", "monitor-flow-brief"),
            Panel(
                flowpanels.LinesView(id="monitor-flow-deliverables-lines"),
                flowpanels.DeliverablesList(id="monitor-flow-deliverables-list"),
                title="Deliverables",
                id="monitor-flow-deliverables",
                classes="view-flow board-d1",
            ),
            panel(flowpanels.LinesView(id="monitor-flow-ahead-lines"), "Ahead", "monitor-flow-ahead"),
            panel(
                flowpanels.LinesView(id="monitor-flow-d4-chain-lines"), "The flow so far", "monitor-flow-d4-flow", "d4"
            ),
            Panel(
                CardsView(id="monitor-flow-d4-cards-view"),
                flowpanels.LinesView(id="monitor-flow-d4-prompt-lines"),
                title="Proposed",
                id="monitor-flow-d4-cards",
                classes="view-flow board-d4",
            ),
            panel(
                flowpanels.LinesView(id="monitor-flow-d4-calls-lines"),
                "How it proposed them",
                "monitor-flow-d4-calls",
                "d4",
            ),
            PanelGrid(
                panel(FlowList(id="monitor-flow-d2-list-view"), "Flow", "monitor-flow-d2-list", "d2"),
                panel(
                    flowpanels.LinesView(id="monitor-flow-d2-settings-lines"),
                    "Settings",
                    "monitor-flow-d2-settings",
                    "d2",
                ),
                columns="1fr 2fr",
                stack_below=STACK_BELOW,
                classes="view-flow board-d2",
            ),
            PanelGrid(
                panel(
                    flowpanels.LinesView(id="monitor-flow-d3-where-lines"),
                    "Where the flow is",
                    "monitor-flow-d3-where",
                    "d3",
                ),
                panel(
                    flowpanels.LinesView(id="monitor-flow-d3-file-lines"), "What it shows", "monitor-flow-d3-file", "d3"
                ),
                panel(
                    flowpanels.LinesView(id="monitor-flow-d3-report-lines"),
                    "VERIFY's report",
                    "monitor-flow-d3-report",
                    "d3",
                ),
                panel(
                    flowpanels.LinesView(id="monitor-flow-d3-brief-lines"),
                    "Against the brief",
                    "monitor-flow-d3-brief",
                    "d3",
                ),
                panel(
                    flowpanels.LinesView(id="monitor-flow-d3-decision-lines"),
                    "Your decision",
                    "monitor-flow-d3-decision",
                    "d3",
                ),
                columns="1fr 2fr",
                spans={"monitor-flow-d3-where": 4},
                stack_below=STACK_BELOW,
                classes="view-flow board-d3",
            ),
        ]

    def show_board(self, name: str) -> None:
        """Bring a board of the Flow view on screen (D1 the flow, D2 a box's settings, D3 a gate, D4 proposals), drawn,
        what it acts on focused."""
        self.board = name if name in BOARDS else "d1"
        for each in BOARDS[1:]:
            self.page.set_class(each == self.board, f"-board-{each}")
        self._draw_board()
        self.page.draw_keys()
        focus = FOCUS[self.board]
        found = self.page.query_one(focus)
        if found.focusable:
            found.focus()
        else:
            self.page.focus()

    def board_keys(self) -> tuple[PageKey, ...]:
        """The keys of the board shown; D1's are the page's own (`MonitorPage.VIEW_KEYS`); D3's those of the answers its
        question offers, with `d` and Esc."""
        keys = BOARD_KEYS.get(self.board, ())
        if self.board == "d3":
            offered = flowboards.answers(self.view, self.gate)
            keys = tuple(key for key in keys if key.key in offered or key.key in ("d", "escape"))
        return keys

    def _draw_board(self) -> None:
        """The board shown, from the flow as last read."""
        view, zone = self.view, self.page.console.zone
        if self.board == "d2":
            self._draw_d2()
        if self.board == "d3":
            gate, copy = self.gate, self.copy
            self._lines(
                "#monitor-flow-d3-where-lines", lambda width: boxchart.listed(view, width, gate, None, zone).lines
            )
            files = flowboards.gate_files(view, gate)
            self.page.query_one("#monitor-flow-d3-file", Panel).title = files[0]["path"] if files else "What it shows"
            self._lines("#monitor-flow-d3-file-lines", lambda width: flowboards.shown(view, gate, copy, width, zone))
            self._lines("#monitor-flow-d3-report-lines", lambda width: flowboards.report(view, gate, width, zone))
            self._lines("#monitor-flow-d3-brief-lines", lambda width: flowpanels.brief(view, width))
            self._lines("#monitor-flow-d3-decision-lines", lambda width: flowboards.decision(view, gate, width))
        if self.board == "d4":
            cards = self.page.query_one("#monitor-flow-d4-cards-view", CardsView)
            cards.show(view if view and view.get("flow") else None)
            proposals = (view or {}).get("proposals") or {}
            boxes = {box["id"]: box for box in (view or {}).get("boxes") or []}
            by = boxes.get(str(proposals.get("box") or ""))
            when = _when(proposals.get("submitted"), zone)
            title = f"Proposed by {by['type'].upper() if by else 'a box'}" + (f" ({when})" if when else "")
            cards_panel = self.page.query_one("#monitor-flow-d4-cards", Panel)
            cards_panel.title, cards_panel.note = title, flowboards.counts(view) + " · A accept all"
            self._lines("#monitor-flow-d4-chain-lines", lambda width: flowboards.chain(view, width))
            self._lines("#monitor-flow-d4-calls-lines", lambda width: flowboards.calls(view, width, zone))
            self._draw_prompt()

    def _draw_prompt(self) -> None:
        view, chosen = self.view, self.page.query_one("#monitor-flow-d4-cards-view", CardsView).selected
        self._lines("#monitor-flow-d4-prompt-lines", lambda width: flowboards.prompt(view, chosen, width))

    def card_chosen(self) -> None:
        """The arrows highlighted another card: its prompt shows under the cards."""
        self._draw_prompt()

    def _board_press(self, key: str) -> bool:
        """A board's keys; Esc goes back to board D1 (from D2, asked first when a change is not saved)."""
        if key == "escape" and self.board == "d2" and any(self.changed.values()):
            self._leave_d2()
            return True
        if key == "escape":
            self.show_board("d1")
            return True
        if self.board == "d2":
            return self._d2(key)
        if self.board == "d4":
            return self._d4(key)
        if self.board == "d3":
            return self._d3(key)
        return False

    def open_gate(self, gate: str) -> None:
        """Board D3 on a gate: what it shows read (its copy, how much it changed), then drawn."""
        self.gate, self.copy = gate, None
        self.show_board("d3")
        files = flowboards.gate_files(self.view, gate)
        if not files or not files[0]["tries"]:
            return
        first, client, console = files[0], self.page.console.client, self.page.console
        copy, diff = self._path("copy"), self._path("diff")

        def work() -> None:
            found: dict[str, Any] = {"path": first["path"]}
            try:
                kept = client.get(copy, box=first["box"], file=first["path"], **{"try": first["tries"][-1]})
                found["text"] = kept.get("text")
            except (NotRunning, ClientError) as error:
                found["why"] = f"{first['path']} cannot be shown: {error}"
            try:
                compared = client.get(diff, box=first["box"], file=first["path"])
                found |= {key: compared.get(key) for key in ("a", "b", "changed", "diff")}
            except (NotRunning, ClientError) as error:
                found["no_diff"] = str(error)
            console.call_from_thread(self._copied, gate, found)

        self.page.run_worker(work, thread=True, group="monitor-flow-gate", exit_on_error=False)

    def _copied(self, gate: str, found: dict[str, Any]) -> None:
        if gate == self.gate:
            self.copy = found
            if self.board == "d3":
                self._draw_board()

    def _d3(self, key: str) -> bool:
        """Board D3's keys: approve, edit then approve, send back with a note, diff, stop the flow."""
        view, console = self.view or {}, self.page.console
        asked = next((each for each in view.get("waiting") or [] if each["box"] == self.gate), None)
        files = flowboards.gate_files(view, self.gate)
        if key == "d":
            copy = self.copy or {}
            if copy.get("diff"):
                title = f"{copy['path']}: try {copy['a']} against try {copy['b']}"
                self.page.app.push_screen(DetailsScreen(title, str(copy["diff"]).splitlines()))
            else:
                console.say(str(copy.get("no_diff") or "there is no try before to compare with"), True)
            return True
        offered = flowboards.answers(view, self.gate)
        if key not in ("a", "e", "s", "x", "r", "t", "k"):
            return False
        if asked is None:
            console.say("this gate does not wait for you now", True)
            return True
        if key not in offered:
            listed = ", ".join(f"{each} {option}" for each, option in offered.items() if each != "e")
            console.say(f"the question at this gate offers no such answer: its answers are {listed}", True)
            return True
        option = offered[key]
        answer = f"questions/{quote(str(asked['question']))}/answer"
        if key == "e":
            if not files:
                console.say("this gate shows no file to edit", True)
                return True
            path = files[0]["path"]
            body = {"folder": str(view.get("folder") or ""), "file": path}
            self._post(
                "agents/vscode", body, f"{path} opens in Clank's VS Code window: save it there, then a approves it"
            )
        elif option == "back":
            writer = files[0]["box"] if files else "the box before it"
            fields = [Field("note", f"Your note for {writer}'s next try: what to change (optional)", "what to change")]

            def noted(values: dict[str, str] | None) -> None:
                if values is not None:
                    body = {"option": "back", "text": values.get("note", "")}
                    self._post(answer, body, f"sent back to {writer} with your note", back=True)

            self.page.app.push_screen(FormScreen(f"Send back to {writer}", fields), noted)
        elif option == "stop":

            def stopping(yes: bool | None) -> None:
                if yes:
                    self._post(answer, {"option": "stop"}, "the flow stops here", back=True)

            said = [
                "The run ends here; nothing after this gate runs.",
                f'The call: POST /api/v1/{answer} {{"option": "stop"}}',
            ]
            self.page.app.push_screen(ConfirmScreen("Stop the flow", said), stopping)
        else:
            done = {"approve": "approved: the flow goes on", "go": "the flow goes on"}.get(
                option, f"answered: {option}"
            )
            self._post(answer, {"option": option}, done, back=True)
        return True

    def _d4(self, key: str) -> bool:
        """Board D4's keys: accept, edit or reject the card highlighted, or accept every card still waiting."""
        view = self.view or {}
        card = self.page.query_one("#monitor-flow-d4-cards-view", CardsView).selected
        items = {str(each["id"]): each for each in (view.get("proposals") or {}).get("items") or []}
        item = items.get(card)
        if key == "A":
            self._post(self._path("proposals/accept"), {"all": True}, "every proposal still waiting accepted")
            return True
        if key not in ("a", "e", "r"):
            return False
        if item is None:
            return True
        if item["state"] != "proposed":
            self.page.console.say(f"{card} is {item['state']} already: e on its box in the flow edits it", True)
            return True
        if key == "a":
            self._post(self._path("proposals/accept"), {"proposals": [card]}, f"{card} accepted: it joins the flow")
        elif key == "r":
            self._post(self._path("proposals/reject"), {"proposals": [card]}, f"{card} rejected: it never runs")
        else:

            def edited(text: str | None) -> None:
                if text is not None and text.strip() != str(item.get("prompt") or "").strip():
                    body = {"proposal": card, "changes": {"prompt": text.strip()}}
                    self._post(self._path("proposals/edit"), body, f"{card}'s prompt edited: it still waits for you")

            note = "Ctrl+S keeps it (the proposal still waits for you to accept it); Esc leaves it as it was."
            self.page.app.push_screen(EditScreen(f"{card} · its prompt", str(item.get("prompt") or ""), note), edited)
        return True

    # Board D2, a box's settings.

    def edit(self) -> None:
        """`e`: board D2 on the box chosen, its settings from the flow's file as it is now."""
        box = self._chosen()
        if box is None:
            return
        client, console, path = self.page.console.client, self.page.console, self._path("")[:-1]

        def work() -> None:
            try:
                found = client.get(path)
            except (NotRunning, ClientError) as error:
                console.call_from_thread(console.say, str(error), True)
                return
            console.call_from_thread(self._editing, str(box["id"]), found)

        self.page.run_worker(work, thread=True, group="monitor-flow-edit", exit_on_error=False)

    def _editing(self, box: str, found: dict[str, Any]) -> None:
        self.values, self.revision, self.edited = dict(found["values"]), str(found.get("revision") or ""), box
        self.show_board("d2")

    def _original(self, box: str) -> dict[str, Any]:
        """A box's values as they stand: its file's; for a box still proposed (not in the file), the proposal's."""
        found = next((dict(each) for each in (self.values or {}).get("boxes") or [] if each["id"] == box), None)
        if found is not None:
            return found
        shown = next((each for each in (self.view or {}).get("boxes") or [] if each["id"] == box), None)
        return dict(shown.get("settings") or {}) if shown is not None and shown["state"] == "proposed" else {}

    def _proposed(self, box: str) -> bool:
        """Whether a box is still a proposal, waiting for the owner: not in the flow's file."""
        return not any(each["id"] == box for each in (self.values or {}).get("boxes") or []) and bool(
            self._original(box)
        )

    def _box_values(self, box: str) -> dict[str, Any]:
        """A box's values as they would be saved: as they stand, with the changes not saved yet."""
        return self._original(box) | self.changed.get(box, {})

    def _draw_d2(self) -> None:
        view, box_id, zone, now = self.view, self.edited, self.page.console.zone, self.now
        box = next((each for each in (view or {}).get("boxes") or [] if each["id"] == box_id), None)
        listing = self.page.query_one("#monitor-flow-d2-list-view", FlowList)
        listing.zone = zone
        listing.show(
            view if view and view.get("flow") else None, box_id, {name for name, each in self.changed.items() if each}
        )
        settings = self.page.query_one("#monitor-flow-d2-settings", Panel)
        if box is None:
            settings.title = "Settings"
            self._lines(
                "#monitor-flow-d2-settings-lines", lambda width: [Content.styled("no box chosen", "$clank-quiet")]
            )
            return
        settings.title = f"{box_id} · {box['title']} · settings"
        values, changed = self._box_values(box_id), set(self.changed.get(box_id, {}))
        defaults = (self.values or {}).get("defaults") or {}
        shown = dict(view or {}) | {"defaults": defaults}
        running = box["state"] == "running" and box_id == (running_box(view) or "")
        found = now if running else None
        self._lines("#monitor-flow-d2-settings-lines",
                    lambda width: flowboards.settings(shown, box, values, changed, found, width, zone))  # fmt: skip

    def list_chosen(self) -> None:
        """The arrows chose another box in D2's list: its settings show."""
        chosen = self.page.query_one("#monitor-flow-d2-list-view", FlowList).selected
        if chosen and chosen != self.edited and chosen != "next-flow":
            self.edited = chosen
            self._draw_d2()

    def _change(self, field: str, value: Any) -> None:
        """A field changed, not saved yet: marked until `s`."""
        box = self.edited
        before = self._original(box)
        changes = self.changed.setdefault(box, {})
        if before.get(field) == value or (before.get(field) in (None, "", []) and value in (None, "", [])):
            changes.pop(field, None)
        else:
            changes[field] = value
        self._draw_d2()

    def _d2(self, key: str) -> bool:
        """Board D2's keys: each field's own key edits it; `v` the whole first message; `s` saves."""
        fields = {key_: (field, label) for key_, field, label in flowboards.FIELDS}
        if key == "s":
            self._save()
            return True
        if key == "v":
            self._first_message()
            return True
        if key not in fields:
            return False
        field, label = fields[key]
        values, title = self._box_values(self.edited), f"{self.edited} · {label}"
        if field == "network":
            self.page.console.say("a box reaches no network: network grants come with M7 (design 0013 §4)", True)
        elif field in PICKS:

            def picked(value: str | None) -> None:
                if value is not None:
                    self._change(field, (value or None) if field == "mode" else value)

            self.page.app.push_screen(PickScreen(title, PICKS[field]), picked)
        elif field in ("prompt", "accept_when"):
            text = str(values.get("prompt") or "") if field == "prompt" else "\n".join(values.get("accept_when") or [])
            note = ("One thing per line. " if field == "accept_when" else "") + KEPT

            def written(text: str | None) -> None:
                if text is not None:
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    self._change(field, text.strip() if field == "prompt" else lines)

            self.page.app.push_screen(EditScreen(title, text, note), written)
        else:
            self.page.app.push_screen(FormScreen(title, form_fields(field, label, values), KEPT), self._answered(field))
        return True

    def _answered(self, field: str) -> Callable[[dict[str, str] | None], None]:
        """What takes a field's form's answer: the change, not saved yet."""

        def answered(answer: dict[str, str] | None) -> None:
            if answer is not None:
                for name, value in form_values(field, answer).items():
                    self._change(name, value)

        return answered

    def _save(self) -> None:
        """`s`: the changes of the boxes in the flow's file into it, written on the revision read (a newer file refuses
        them, said, and they stay to save again); those of a box still proposed into its proposal (`proposals/edit`:
        it still waits for the owner). Only what was written is said saved."""
        if not any(self.changed.values()) or self.values is None:
            self.page.console.say("nothing to save: no change waits", True)
            return
        filed = {box: dict(each) for box, each in self.changed.items() if each and not self._proposed(box)}
        proposed = {box: dict(each) for box, each in self.changed.items() if each and self._proposed(box)}
        values = dict(self.values)
        values["boxes"] = [dict(each) | filed.get(each["id"], {}) for each in values.get("boxes") or []]
        for each in values["boxes"]:
            for field in [name for name, value in each.items() if value is None]:
                each.pop(field)
        view = self.view or {}
        path = f"records/flow/{quote(str(view.get('workspace')))}/{quote(str(view.get('name')))}"
        edit = self._path("proposals/edit")
        client, console, base = self.page.console.client, self.page.console, self.revision

        def work() -> None:
            if filed:
                try:
                    saved = client.put(path, {"values": values, "base": base})
                except (NotRunning, ClientError) as error:
                    console.call_from_thread(console.say, f"not saved: {error}", True)
                else:
                    console.call_from_thread(self._saved, saved, filed)
            for box, changes in proposed.items():
                try:
                    client.post(edit, {"proposal": box, "changes": changes})
                except (NotRunning, ClientError) as error:
                    console.call_from_thread(console.say, f"{box} not saved: {error}", True)
                else:
                    console.call_from_thread(self._edited, box, changes)

        self.page.run_worker(work, thread=True, group="monitor-flow-save", exit_on_error=False)

    def _saved(self, saved: dict[str, Any], filed: dict[str, dict[str, Any]]) -> None:
        """The flow's file written: its changes are no longer waiting."""
        count = sum(len(each) for each in filed.values())
        self.values, self.revision = dict(saved["values"]), str(saved.get("revision") or "")
        for box in filed:
            self.changed.pop(box, None)
        self.page.console.say(f"saved {count} change{'s' if count != 1 else ''} into the flow's file")
        self.reread()
        self._draw_d2()

    def _edited(self, box: str, changes: dict[str, Any]) -> None:
        """A proposal edited: its changes are no longer waiting; it still waits for the owner to accept it."""
        self.changed.pop(box, None)
        count = len(changes)
        self.page.console.say(f"saved {count} change{'s' if count != 1 else ''} into {box}'s proposal: it still waits "
                              "for you to accept it")  # fmt: skip
        self.reread()
        self._draw_d2()

    def _leave_d2(self) -> None:
        """Esc with changes not saved: asked first; leaving drops them."""
        names = ", ".join(sorted(name for name, each in self.changed.items() if each))

        def leaving(yes: bool | None) -> None:
            if yes:
                self.changed = {}
                self.show_board("d1")

        said = [f"The changes to {names} are not saved: leaving drops them.", "s saves them first."]
        self.page.app.push_screen(ConfirmScreen("Leave without saving", said), leaving)

    def _first_message(self) -> None:
        """`v`: the box's whole first message as it would be sent now (`clank flow prepare`), in a window."""
        box, client, console = self.edited, self.page.console.client, self.page.console
        path = self._path("prepare")

        def work() -> None:
            try:
                found = client.get(path, box=box)
                shown = (found.get("boxes") or [{}])[0]
                size = f"{shown.get('tokens', 0):,} tokens" + ("" if shown.get("exact") else " (an estimate)")
                window = f" of {shown['window']:,}" if shown.get("window") else ""
                title = f"{box}'s first message, as it would be sent now · {size}{window}"
                lines = str(shown.get("text") or "").splitlines()
            except (NotRunning, ClientError) as error:
                title, lines = f"{box}'s first message", [str(error)]
            console.call_from_thread(console.push_screen, DetailsScreen(title, lines))

        self.page.run_worker(work, thread=True, group="monitor-flow-first", exit_on_error=False)

    def _post(self, path: str, body: dict[str, Any], done: str, *, back: bool = False) -> None:
        """Ask the service, say what was done (or its refusal), and read the flow again at once; with `back`, board
        D1 again once it is done."""
        console, client = self.page.console, self.page.console.client

        def work() -> None:
            try:
                client.post(path, body)
            except (NotRunning, ClientError) as error:
                console.call_from_thread(console.say, str(error), True)
                return
            console.call_from_thread(console.say, done)
            console.call_from_thread(self.reread)
            if back:
                console.call_from_thread(self.show_board, "d1")

        self.page.run_worker(work, thread=True, group="monitor-flow-post", exit_on_error=False)

    def reread(self) -> None:
        """Read the flow again at once, drawn even if its version did not move."""
        if self._reading is not None:
            self._reading.forget()
        self._read()

    @property
    def chart(self) -> BoxChart:
        """The Flow panel's chart."""
        return self.page.query_one("#monitor-flow-chart-boxes", BoxChart)

    @property
    def shown(self) -> bool:
        """Whether the Flow view is on screen."""
        return bool(self.page.display) and self.page.view == "flow"

    def mounted(self) -> None:
        """Every panel says what it waits for until a flow comes."""
        self._draw(None)

    def tick(self) -> None:
        """On each of the console's redraw ticks while the page is on screen: draw what the readings brought since the
        last, together; then start the readings due (the flow once a second, the running box's session's now on every
        tick while it works, once a second while it rests)."""
        drew = False
        if self._came is not None:
            view, self._came = self._came, None
            self._draw(view)
            drew = True
        running = running_session(self.view)
        if self._now_came is not None:
            (session, found), self._now_came = self._now_came, None
            if running is not None and session == running[1]:
                self.now = found
                self._draw_box()
                drew = True
        if self._context_came is not None:
            (session, found), self._context_came = self._context_came, None
            if running is not None and session == running[1]:
                self.context = found
                self._draw_selected()
                drew = True
        if drew:
            self.redraws += 1
        if not self.shown:
            return
        moment = time.monotonic()
        if moment - self._read_at >= READ_SECONDS:
            self._read()
        working = bool((self.now or {}).get("working"))
        if running is not None and (working or moment - self._now_at >= READ_SECONDS):
            self._read_now(running)

    def _draw(self, view: dict[str, Any] | None) -> None:
        """The flow and every panel of board D1, each drawn again only where it changed."""
        before, building = running_session(self.view), bool((self.view or {}).get("planning"))
        self.view = view
        if bool((view or {}).get("planning")) != building:
            self.page.draw_keys()  # while a flow is built, only the keys that act then
        if running_session(view) != before:
            self.now = self.context = None
            if self._watching is not None:
                self._watching.forget()
        self.page.query_one("#monitor-flow-boxes", Panel).note = counts(view) if view and view.get("flow") else ""
        self.chart.empty = DRAFTING if (view or {}).get("planning") else boxpanel.NO_FLOW
        self.page.query_one("#monitor-flow-brief", Panel).note = flowpanels.brief_note(view) if view else ""
        self._draw_box()
        self._lines("#monitor-flow-models-lines", lambda width: flowpanels.models(view, width))
        self._lines("#monitor-flow-waiting-lines", lambda width: flowpanels.waiting(view, width))
        steering = (view or {}).get("orchestrator") or {}
        self.page.query_one("#monitor-flow-orchestrator", Panel).note = (
            ("on" if steering.get("on") else "off") if view and view.get("flow") else ""
        )
        frame = self.page.console.frame
        self._lines("#monitor-flow-orchestrator-lines", lambda width: flowpanels.orchestrator(view, width, frame))
        self._lines("#monitor-flow-brief-lines", lambda width: flowpanels.brief(view, width))
        files = self.page.query_one("#monitor-flow-deliverables-list", flowpanels.DeliverablesList)
        files.show(view if view and view.get("flow") else None)
        said = self.page.query_one("#monitor-flow-deliverables-lines", flowpanels.LinesView)
        said.display = not files.files
        self._lines("#monitor-flow-deliverables-lines", lambda width: flowpanels.deliverables(view, width))
        self._lines("#monitor-flow-ahead-lines", lambda width: flowpanels.ahead(view, width))
        self.page.draw_heading()
        if self.board != "d1":
            self._draw_board()

    def _draw_box(self) -> None:
        """The flow, the running box's step and speed in it, and Selected."""
        chart = self.chart
        chart.zone = self.page.console.zone
        found = self.now or {}
        speed = (found.get("speed") or {}).get("now")
        shown = self.view if self.view and self.view.get("flow") and self.view.get("boxes") else None
        chart.show(shown, now_box(self.view), {"step": found.get("step"), "speed": speed})
        self._draw_selected()

    def _draw_selected(self) -> None:
        """Selected, and its Live box while the box chosen is a model's box running; while the flow is built with the
        model, "Building it with the model" in its place: the planning's steps, and a Live box for its session."""
        view, chosen, zone = self.view, self.chart.selected, self.page.console.zone
        selected = self.page.query_one("#monitor-flow-selected", Panel)
        live = self.page.query_one("#monitor-flow-live", LiveBox)
        planning = (view or {}).get("planning")
        if planning:
            selected.title = BUILDING
            self._lines("#monitor-flow-selected-lines", lambda width: flowpanels.building(view, width, zone))
            live.display = bool(planning.get("session"))
            if live.display:
                now, context = self.now, self.context
                self._lines("#monitor-flow-live-lines",
                            lambda width: flowpanels.live({"id": "planning"}, now, context, width))  # fmt: skip
            return
        selected.title = "Selected"
        at = self.page.console.now()
        self._lines("#monitor-flow-selected-lines", lambda width: flowpanels.selected(view, chosen, width, zone, at))
        box = next((each for each in (view or {}).get("boxes") or [] if each["id"] == chosen), None)
        running = box is not None and box["state"] == "running" and box["type"] not in OWNERS
        live.display = running
        if running:
            now, context = self.now, self.context
            self._lines("#monitor-flow-live-lines", lambda width: flowpanels.live(box, now, context, width))

    def chosen(self) -> None:
        """The arrows chose another box: Selected shows it."""
        self._draw_selected()

    def _lines(self, id: str, making: Callable[[int], Sequence[Content]]) -> None:
        self.page.query_one(id, flowpanels.LinesView).show(making)

    def _read(self) -> None:
        """Read the flow the folder follows, off the screen's thread; drawn on the next tick when it changed. With it,
        the running box's context window."""
        if not self.shown:
            return
        self._read_at = time.monotonic()
        if self._reading is None:
            self._reading = FlowReading(self.page.console.client, self.page.console.folder)
        reading, client = self._reading, self.page.console.client
        running = running_session(self.view)
        console = self.page.console

        def work() -> None:
            try:
                found = reading.read()
            except (NotRunning, ClientError):
                return  # the header says the service does not answer; the next reading tries again
            if found is not None:
                console.call_from_thread(setattr, self, "_came", found)
            if running is not None:
                workspace, session, _ = running
                try:
                    context = client.get(f"agents/context/{quote(workspace)}/{quote(session)}")
                except (NotRunning, ClientError) as error:
                    context = {"session": session, "unavailable": str(error)}
                if context != self.context:
                    console.call_from_thread(setattr, self, "_context_came", (session, context))

        self.page.run_worker(work, thread=True, group="monitor-flow-read", exit_on_error=False)

    def _read_now(self, running: tuple[str, str, int]) -> None:
        """Read what the running box's session does now, off the screen's thread; drawn on the next tick."""
        self._now_at = time.monotonic()
        if self._watching is None:
            self._watching = Watching(self.page.console.client)
        watching, (workspace, session, _) = self._watching, running
        console = self.page.console

        def work() -> None:
            try:
                found = watching.read(workspace, session)
            except (NotRunning, ClientError):
                return
            if found is not None:
                console.call_from_thread(setattr, self, "_now_came", (session, found))

        self.page.run_worker(work, thread=True, group="monitor-flow-now", exit_on_error=False)

    def press(self, key: str) -> bool:
        """Board D1's keys: Enter opens what the box chosen holds, `h` the run log, `p` pauses the flow or resumes
        it, `r` runs it again from the box chosen (a flow not run yet, from its start), once confirmed; `n` builds a
        new flow with the model where the owner is, `N` in VS Code, a flow shown or not; another board's keys while it
        is shown."""
        if self.board != "d1":
            return self._board_press(key)
        if self.page.app.screen is not self.page.screen:
            return False  # a window over the page (a confirmation, a form) takes its own keys: Enter is its
        if key in ("n", "N"):
            self.new_flow("vscode" if key == "N" else "")
            return True
        acts = {"enter": self.open, "h": self.log, "p": self.pause, "r": self.run_from, "e": self.edit,
                "o": self.open_file, "O": self.orchestrator, "L": self.ledger}  # fmt: skip
        if key not in acts or not self.view or not self.view.get("flow"):
            return False
        if self.view.get("planning") and key not in ("enter", "O", "L"):
            self.page.console.say("the flow is being built with the model: r runs it, e edits it, once Clank wrote it",
                                  True)  # fmt: skip
            return True
        acts[key]()
        return True

    def new_flow(self, asked: str, aside: bool = False) -> None:
        """`n` (`N`: in VS Code): a planning, a flow built with the model (design 0013 §15), opened beside the console,
        never in its terminal (decision 0100): over SSH nothing opens, the view saying how to attach from another
        terminal; in Windows Terminal its window is split for `clank flow attach`; in VS Code's terminal, or with `N`
        anywhere but over SSH, Clank's VS Code window; else the message. The view then shows the planning. A planning
        open in the folder's workspace (the one the view shows) is never overwritten: asked first whether to set it
        aside (`aside`), Esc leaving it as it is. One start at a time: pressed again meanwhile, nothing happens."""
        if self.starting:
            return
        self.starting = True
        opening = places.console_opening(os.environ)
        if asked == "vscode" and not places.over_ssh(os.environ):
            opening = "vscode"
        console, client = self.page.console, self.page.console.client
        body = {"folder": console.folder, "where": "vscode" if opening == "vscode" else "attach", "aside": aside}

        def work() -> None:
            try:
                shown = {} if aside else client.get("flows/view", folder=console.folder)
                if shown.get("planning"):
                    console.call_from_thread(self._ask_aside, asked, shown["planning"])
                    return
                found = client.post("flows/new", body)
            except (NotRunning, ClientError) as error:
                console.call_from_thread(self._started, str(error), True)
                return
            said, failed = "", False
            if opening == "split":
                workspace = str(found["flow"]).split("/", 1)[0]
                argv = places.split_argv(str(found.get("folder") or console.folder), workspace, sys.executable,
                                         os.environ)  # fmt: skip
                why = places.launch_split(argv)
                said = f"{found['flow']}: {why}: talk with the model: in another terminal, {found['attach']}"
                if not why:
                    said = (f"{found['flow']}: OpenCode opens in a pane on the right, on the planning session: talk "
                            "with the model there, and watch the flow built here")  # fmt: skip
                failed = bool(why)
            elif opening == "message":
                said = f"{found['flow']}: talk with the model: in another terminal, {found['attach']}"
            console.call_from_thread(self._planning, found, said, failed)

        self.page.run_worker(work, thread=True, group="monitor-flow-new", exit_on_error=False)

    def _started(self, said: str, failed: bool) -> None:
        """A start over: said, and `n` acts again."""
        self.starting = False
        if said:
            self.page.console.say(said, failed)

    def _ask_aside(self, asked: str, planning: dict[str, Any]) -> None:
        """A planning is open: whether to start a new one and set it aside (Enter), or leave it (Esc)."""
        self.starting = False
        said = [
            f"a planning is open: {planning['flow']}, {planning['status']}.",
            "Start a new one and set it aside? Its session stays in OpenCode's list (/sessions); nothing in the folder "
            "changes. Esc leaves it open, as it is.",
            "The call: POST /api/v1/flows/new {folder, where, aside: true}",
        ]

        def confirmed(yes: bool | None) -> None:
            if yes:
                self.new_flow(asked, aside=True)

        self.page.app.push_screen(ConfirmScreen("Set the open planning aside", said), confirmed)

    def _planning(self, found: dict[str, Any], said: str, failed: bool) -> None:
        """A planning opened beside the console: in VS Code, Clank's VS Code window opened on the folder; else what was
        said of where OpenCode runs. The view then shows the planning as it is built."""
        self.starting = False
        flow, console = str(found["flow"]), self.page.console
        if found["where"] == "vscode":
            shows = "comes forward" if found.get("window") == "running" else "opens, OpenCode in its terminal"
            done = f"{flow}: Clank's VS Code window {shows} on the planning session; watch the flow built here"
            self._post("agents/vscode", {"folder": str(found.get("folder") or console.folder)}, done)
        elif said:
            console.say(said, failed)
        self.reread()

    def _chosen(self) -> dict[str, Any] | None:
        chosen = self.chart.selected
        return next((box for box in (self.view or {}).get("boxes") or [] if box["id"] == chosen), None)

    def _path(self, tail: str) -> str:
        view = self.view or {}
        return f"flows/{quote(str(view['workspace']))}/{quote(str(view['name']))}/{tail}"

    def _in_deliverables(self) -> bool:
        focused = self.page.app.focused
        return focused is not None and focused.id == "monitor-flow-deliverables-list"

    def open_file(self) -> None:
        """`o`: a deliverable in Clank's VS Code window (design 0013 §8): the one highlighted in Deliverables, else the
        newest the box chosen wrote."""
        view = self.view or {}
        files = self.page.query_one("#monitor-flow-deliverables-list", flowpanels.DeliverablesList)
        if self._in_deliverables():
            found = files.highlighted()
        else:
            chosen = self.chart.selected
            found = next((each for each in reversed(files.files) if each["box"] == chosen), None)
        if found is None:
            self.page.console.say("no file to open: the box chosen has written none yet", True)
            return
        path = str(found["path"])
        body = {"folder": str(view.get("folder") or ""), "file": path}
        self._post("agents/vscode", body, f"{path} opens in Clank's VS Code window")

    def open(self) -> None:
        """Enter: what the box chosen holds. A running box's session in the Session view, pinned to it (Esc comes
        back to the box); a finished box's deliverable, as its try kept it; else the box whole. On Deliverables, the
        file highlighted."""
        if self._in_deliverables():
            found = self.page.query_one("#monitor-flow-deliverables-list", flowpanels.DeliverablesList).highlighted()
            if found is not None and found.get("try"):
                self._show_copy(str(found["box"]), str(found["path"]), int(found["try"]))
            elif found is not None:
                self.page.console.say(f"{found['path']} is kept by no try: o opens it in Clank's VS Code window", True)
            return
        view, box = self.view or {}, self._chosen()
        planning = view.get("planning")
        if planning:  # the planning session, in the Session view (decision 0101)
            session = planning.get("session") or {}
            if not session.get("session"):
                self.page.console.say(f"its session has not started: talk with the model: {planning['attach']}", True)
                return
            self.opened_from = PLANNING
            self.page.open_session(
                str(session["workspace"]), str(session["session"]), f"the planning of {view['flow']}"
            )
            return
        if box is None:
            return
        tries = box.get("tries") or []
        session = (tries[-1].get("session") or {}) if tries else {}
        if box["type"] == "decompose" and ((view.get("proposals") or {}).get("box") == box["id"]):
            self.show_board("d4")
            return
        if box["type"] == "gate":
            self.open_gate(str(box["id"]))
            return
        if box["state"] == "running" and box["type"] not in OWNERS and session.get("session"):
            label = f"{view['title']} · {box['id']} · try {tries[-1]['number']}"
            self.opened_from = str(box["id"])
            self.page.open_session(str(session["workspace"]), str(session["session"]), label)
            return
        written = [(each["number"], path) for each in tries for path in each.get("written") or []]
        if written:
            number, path = written[-1]
            self._show_copy(str(box["id"]), path, number)
            return
        lines = [line.plain for line in flowpanels.selected(view, str(box["id"]), 1000, self.page.console.zone)]
        self.page.app.push_screen(DetailsScreen(f"{tag(box)} · {box['title']}", lines))

    def _show_copy(self, box: str, path: str, number: int) -> None:
        """A deliverable as its try kept it, read through the service and shown in a window."""
        client, console = self.page.console.client, self.page.console
        asked = self._path("copy")

        def work() -> None:
            try:
                found = client.get(asked, box=box, file=path, **{"try": number})
                lines = str(found.get("text") or "").splitlines() or ["(empty)"]
            except (NotRunning, ClientError) as error:
                lines = [f"{path} cannot be shown: {error}"]
            console.call_from_thread(console.push_screen, DetailsScreen(f"{path} · {box}, try {number}", lines))

        self.page.run_worker(work, thread=True, group="monitor-flow-copy", exit_on_error=False)

    def log(self) -> None:
        """`h`: the run's log whole, oldest first, in a window (design 0013 §12: not under the flow)."""
        client, console, zone = self.page.console.client, self.page.console, self.page.console.zone
        asked, title = self._path("log"), str((self.view or {}).get("title") or "")

        def work() -> None:
            try:
                found = client.get(asked)
                said = found.get("events") or []
                lines = [f"{clock(parse(each['time']), zone)}  {each['summary']}" for each in said]
                run = found.get("run")
            except (NotRunning, ClientError) as error:
                lines, run = [f"the run log cannot be read: {error}"], None
            heading = f"The run log · {title}" + (f", run {run}" if run else "")
            console.call_from_thread(console.push_screen, DetailsScreen(heading, lines or ["nothing yet"]))

        self.page.run_worker(work, thread=True, group="monitor-flow-log", exit_on_error=False)

    def orchestrator(self) -> None:
        """`O`: turn the flow's orchestrator on or off (design 0013 §16); a run goes on either way."""
        steering, console = (self.view or {}).get("orchestrator") or {}, self.page.console
        turning = not steering.get("on")
        client, path = console.client, self._path("orchestrator")
        done = (
            "the orchestrator is on: it reads what each box did and answers the run's questions, within its limits; "
            "O turns it off"
            if turning
            else "the orchestrator is off: the run waits for you where it would"
        )
        actions.call(console, lambda: client.post(path, {"on": turning}), done=done)

    def ledger(self) -> None:
        """`L`: the orchestrator's ledger of the latest run whole, in a window: its facts and plan, then each
        decision with why and what was done."""
        client, console = self.page.console.client, self.page.console
        asked, title = self._path("orchestrator"), str((self.view or {}).get("title") or "")

        def work() -> None:
            try:
                found = client.get(asked)
                lines = str(found.get("ledger") or "").splitlines()
                run = found.get("run")
            except (NotRunning, ClientError) as error:
                lines, run = [f"the ledger cannot be read: {error}"], None
            heading = f"The orchestrator's ledger · {title}" + (f", run {run}" if run else "")
            console.call_from_thread(console.push_screen, DetailsScreen(heading, lines or ["nothing yet"]))

        self.page.run_worker(work, thread=True, group="monitor-flow-ledger", exit_on_error=False)

    def pause(self) -> None:
        """`p`: pause the flow (no box starts; the running one goes on), or resume it while paused."""
        run, console = (self.view or {}).get("run") or {}, self.page.console
        if run.get("status") not in ("queued", "running"):
            console.say("the flow is not running: r on a box runs it again from there", True)
            return
        client = console.client
        body: dict[str, Any] | None = None
        if run.get("paused"):
            path, body, done = self._path("run"), {}, "resumed: the next box starts"
        else:
            path, done = self._path("pause"), "paused: no box starts; the running one goes on"
        actions.call(console, lambda: client.post(path, body), done=done)

    def run_from(self) -> None:
        """`r`: run the flow again from the box chosen, and every box after it, as new tries; a flow that has not run
        yet (a flow built with the model, design 0013 §15) from its first box; asked first."""
        box, view, console = self._chosen(), self.view or {}, self.page.console
        if not view.get("run"):
            self._start()
            return
        if box is None:
            return
        ids = [each["id"] for each in view.get("boxes") or []]
        after = ids[ids.index(box["id"]) :] if box["id"] in ids else [box["id"]]
        path = self._path("run")
        named = str(box["id"])
        said = [
            f"{named} and every box after it run again, as new tries: {', '.join(after)}.",
            "The boxes before it are taken as they stand.",
            "The call: POST /api/v1/" + path + ' {"from": "' + named + '"}',
        ]
        client = console.client

        def confirmed(yes: bool | None) -> None:
            if yes:
                actions.call(console, lambda: client.post(path, {"from": named}), done=f"runs again from {named}")

        self.page.app.push_screen(ConfirmScreen(f"Run again from {named}", said), confirmed)

    def _start(self) -> None:
        """`r` on a flow that has not run: its first run, from its first box, once confirmed."""
        view, console = self.view or {}, self.page.console
        boxes = [str(each["id"]) for each in view.get("boxes") or []]
        path, title = self._path("run"), str(view.get("title") or view.get("name") or "")
        said = [f"{title} runs from its first box, {boxes[0] if boxes else 'its brief'}: {', '.join(boxes)}."]
        if view.get("built"):
            said.append("Built with the model, it asks nothing on the way: it waits for you at its last box, your "
                        "review, or when a box runs out of tries.")  # fmt: skip
        said.append("The call: POST /api/v1/" + path + " {}")
        client = console.client

        def confirmed(yes: bool | None) -> None:
            if yes:
                actions.call(console, lambda: client.post(path, {}), done=f"{title} started")

        self.page.app.push_screen(ConfirmScreen(f"Run {title}", said), confirmed)

    def back(self) -> None:
        """Esc on a session opened from a box: back to the Flow view, that box chosen."""
        box, self.opened_from = self.opened_from, ""
        self.page.show_view("flow")
        if box and box != PLANNING:
            chart = self.chart
            chart.following, chart.selected = False, box
            shown = self.view if self.view and self.view.get("flow") else None
            chart.show(shown, now_box(self.view), chart.live)
            self._draw_selected()

    def explain(self) -> list[str]:
        """What `?` adds on the Flow view: the flow's heading, the box chosen whole."""
        lines = [heading(self.view, self.page.console.zone).plain]
        chosen = self.chart.selected
        lines += [line.plain for line in flowpanels.selected(self.view, chosen, 1000, self.page.console.zone)]
        return lines
