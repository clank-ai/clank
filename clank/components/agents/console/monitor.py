"""The Monitor (design 0012 §2, decision 0047): the page of the console's menu on F10 where the owner watches, and will
guide, everything the local model does in a session.

It has three views, in a row of tabs at its top: **Flow** (a flow, the work as a program of boxes: design 0013 §12),
**Session** (one OpenCode session as it works: board A, with board D's Watch for and Guide) and **Context** (the context
window whole: board C, design 0012 §4.7). F10 again, on the Monitor, moves to the next view, and a click on a tab shows
its view; Enter on the Session view's Context window panel opens the Context view, and Esc goes back from it (Esc on a
window over the page only closes the window; decision 0151). The page opens on the view last shown, Session the first
time. Under the tabs, one heading line names the session (or the flow) the view follows. The views' panels stand in the
page itself, each marked with its view's class (`view-session`), and the page's class (`-view-session`) shows one
view's: so the page scrolls sideways to a panel wider than it, as every page does.

Each section is a panel (design 0011 §4). The Session view: the Context window across the page; Now, Watch for and the
Guide beside the Flow; Tool calls beside Biggest in the context, in the same columns, so the borders line up
(`PanelGrid`); narrower than `STACK_BELOW` columns they stack, Now, Flow, Watch for, the Guide, Tool calls, Biggest, as
design 0012 §2 orders them. In the Session view each panel's letter (`LETTERS`, beside its title) moves the focus into
it, and Tab goes from panel to panel. The machine column is hidden on the page (`MACHINE_COLUMN`), whose panels take its
room, until F5 shows it.

Built so far: the page and its panels (design 0012's step 1), each saying "no session yet" (the Flow view's "no flow
yet") until it has content of its own, held by an `Empty` label that takes the focus, so the letters and Tab reach a
panel before then; the Context window panel's totals (step 3, `ContextWindow`); the session's flow (step 6); and the
context's parts (step 12): the bar by part, Biggest in the context (`biggestpanel.py`, Enter an item whole) and the
Context view's panels (`contextview.py` and its neighbors: What is in it, ↑↓ and Enter a part's items; On the GPU
exactly; Over this session; Where the room went; Could be freed, Enter on Compact now asking first, as `k` does
there; Where these figures come from). The
page follows the newest active root session of the console's folder (`following.py`, design 0012 §3), read off the
screen's thread once a second while the page is on screen, and names it in the heading line (OpenCode, the workspace,
the session's title, its agent, what it does, its steps and calls, since when, that it is the newest); without one, the
heading says why (the folder has no workspace, or none of its sessions has been seen working since the service started).
The Flow panel holds the session's flow (`FlowChart`, design 0012 §6), its keys in the panel's note. The Watch for panel
lists the newest marks the rules left in the service (step 8, `watchfor.py`); Enter on it opens them, each whole (§2's
keys: Enter opens a mark), which sees them; beside "Monitor" in the menu stands the count not seen yet (`badge`). The
marks come with the console's data. The Guide panel lists what the owner can do to the session followed (step 9,
`guidepanel.py`): on the Session view the page takes `.` (Stop now, at once), `m` (a note, in a window that names the
node under the flow's cursor as what it is about, the agent it goes to and what it costs) and `k` (Compact now, after a
window that says what it does, its call and its cost: Enter does it, Esc leaves it), `p` (Pause after this step, or
Resume while paused: step 11, after the same window), `u` (Undo the last step, or the turn, after a window with what it
takes back and why the step alone is refused, sending the revert that window showed; when it took back a message of
yours, the turn's, its words come back whole in a window of several lines, which Esc keeps for `m`; Redo while a revert
is pending: step 10) and `x` (Drop: the result of the call highlighted in Tool calls when that panel has the focus, else
of the call under the flow's cursor, after a window with what it frees, what it costs and that the drop is final, read
for that call); an action that cannot run says why on the message line. The Now panel says what the session does this
second (step 7, `nowpanel.py`, from `GET /agents/now/{workspace}/{session}`): its phase, its budgets, the prompt, the
call being written, its speed and the loop guard; its spinner turns in its own cell while the session works, on the
page's ticks (`TURN_SECONDS`), so at most four times a second. The session's work is not the console's own: the
console's spinner, in the header, turns only for its operations and model requests, as on every page. The Tool calls
panel lists the session's calls, newest first, from its flow (step 7, `callspanel.py`), or says the session has none
yet; Enter on one reads it whole through the bridge, a `docker exec`, so only then (design 0012 §7). When rows are
short, Tool calls gives up rows first (§2's room, `CallsRow`), so the Session view fits the page while it can. The page
draws what its readings brought on the console's redraw ticks (`tick`), so it redraws at most four times a second: it
reads the session and its flow once a second while on screen, what the session does now on every tick while it works and
once a second while it does not, the live text only while it is shown (on the Session view), and nothing while the page
is not on screen. What did not change is not drawn again (design 0001 §5.7).
"""

import time
from datetime import UTC, datetime, tzinfo
from typing import Any, ClassVar
from urllib.parse import quote

from textual import events
from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label

from clank.client import ClientError, NotRunning
from clank.components.agents.console.biggestpanel import NO_PARTS, BiggestList, item_line
from clank.components.agents.console.biggestpanel import whole as item_whole
from clank.components.agents.console.boxpanel import BoxChart, ChartView, FlowList
from clank.components.agents.console.callspanel import NO_CALL, ROWS, CallScreen, CallsList
from clank.components.agents.console.callspanel import title as call_title
from clank.components.agents.console.callspanel import whole as call_whole
from clank.components.agents.console.contextfreed import NOTHING_FREED, FreedList, freed_items, freed_notes
from clank.components.agents.console.contextpanel import ContextWindow
from clank.components.agents.console.contextview import DRAWINGS, Drawn, PartsList, part_notes, part_rows, waiting
from clank.components.agents.console.flowpanel import NO_SESSION, FlowChart
from clank.components.agents.console.flowview import FlowViewer
from clank.components.agents.console.flowview import heading as flow_heading
from clank.components.agents.console.following import Following, Seen, Watching
from clank.components.agents.console.guidepanel import PRESSED, GuideList, about
from clank.components.agents.console.guidepanel import whole as guide_whole
from clank.components.agents.console.itemsscreen import ItemsScreen, droppable
from clank.components.agents.console.livepanel import LiveView
from clank.components.agents.console.nowpanel import NowView
from clank.components.agents.console.watchfor import MarksList, lines, shown, whole
from clank.console import actions
from clank.console.confirm import ConfirmScreen
from clank.console.data import ConsoleData
from clank.console.details import DetailsScreen
from clank.console.editor import EditScreen
from clank.console.form import Field, FormScreen
from clank.console.keys import PageKey
from clank.console.keysbar import KeysBar
from clank.console.lists import relabel
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel, PanelGrid
from clank.console.style import mark

VIEWS = ("flow", "session", "context")  # the tabs, in board D1's order; F10 moves to the next
TITLES = {"flow": "Flow", "session": "Session", "context": "Context"}
FIRST_VIEW = "flow"  # the website's look (decision 0125); board A was the first pick, before the website
NO_FLOW = "no flow yet"
HEADINGS = {
    "flow": ("No flow yet", "reading this folder's flows"),
    "session": ("No session yet", "reading this folder's sessions"),
    "context": ("No session yet", "reading this folder's sessions"),
}
NO_WORKSPACE = "this folder has no workspace: This folder (F4) opens one"
NONE_SEEN = "none of {workspace}'s sessions has been seen working since the service started"
READ_SECONDS = 1.0  # how often the page reads its session's flow while on screen, and what it does while it rests
TURN_SECONDS = 0.2  # the Now panel's spinner turns at most this often: on each of the page's ticks, four a second
FLOW_KEYS = "↑↓ a node · ←→ fold · End now"
STATES = {"busy": "working", "retry": "retrying", "idle": "idle"}
BORDERS = 2  # a panel's top and bottom borders, in rows (the style's kinds, solid and round, both have them)
STACK_BELOW = 80  # side by side at 88 columns (the page beside the machine column at 160), stacked at 60
LETTERS = {
    "c": "monitor-session-context",
    "n": "monitor-session-now",
    "f": "monitor-session-flow",
    "t": "monitor-session-calls",
    "b": "monitor-session-biggest",
    "w": "monitor-session-watch",
    "g": "monitor-session-guide",
}  # design 0012 §2's keys, in its order


class Empty(Label):
    """What a panel says before it has content of its own ("no session yet"); it takes the focus, so a panel's letter,
    Tab and the arrows reach the panel."""

    can_focus = True

    DEFAULT_CSS = """
    Empty {
        color: $clank-quiet;
    }
    """


def empty(view: str, title: str, id: str, key: str = "") -> Panel:
    """A panel of a view, titled, saying only what it waits for."""
    return Panel(Empty(NO_FLOW if view == "flow" else NO_SESSION), title=title, id=id, key=key, classes=f"view-{view}")


def watch_for() -> Panel:
    """The Session view's Watch for panel: its empty label, and the list of the newest marks, hidden while none."""
    listed = MarksList()
    listed.display = False
    return Panel(Empty(NO_SESSION), listed, title="Watch for", id="monitor-session-watch", key="w",
                 classes="view-session")  # fmt: skip


def biggest() -> Panel:
    """The Session view's Biggest in the context panel: its empty label, and the list of the biggest items, hidden while
    none (design 0012 §4.6)."""
    listed = BiggestList(id="monitor-biggest-list")
    listed.display = False
    return Panel(Empty(NO_SESSION), listed, title="Biggest in the context", id="monitor-session-biggest", key="b",
                 classes="view-session")  # fmt: skip


def drawn(kind: str, title: str, id: str) -> Panel:
    """A panel of the Context view, drawn by one of its functions (`contextview.DRAWINGS`) for its width."""
    return Panel(Drawn(DRAWINGS[kind], id=f"{id}-lines"), title=title, id=id, classes="view-context")


def could_be_freed() -> Panel:
    """The Context view's Could be freed: its empty label, and what could be freed, hidden while nothing (§4.6)."""
    listed = FreedList(id="monitor-freed-list")
    listed.display = False
    return Panel(Empty(NO_SESSION), listed, title="Could be freed", id="monitor-context-freed", classes="view-context")


def what_is_in_it() -> Panel:
    """The Context view's What is in it: its empty label, its header and its parts, hidden while there are none."""
    head = Label(id="monitor-parts-head")
    head.display = False
    listed = PartsList(head, id="monitor-parts-list")
    listed.display = False
    return Panel(Empty(NO_SESSION), head, listed, title="What is in it", id="monitor-context-parts", note="estimate",
                 classes="view-context")  # fmt: skip


def tool_calls() -> Panel:
    """The Session view's Tool calls panel: its empty label, and the list of the session's calls, hidden while none."""
    listed = CallsList(id="monitor-calls-list")
    listed.display = False
    return Panel(Empty(NO_SESSION), listed, title="Tool calls", id="monitor-session-calls", key="t",
                 classes="view-session")  # fmt: skip


class CallsRow(PanelGrid):
    """Tool calls beside Biggest in the context. Side by side, the row is as tall as the rows the page has left, down to
    one row, and up to the more of what Tool calls and Biggest hold (design 0012 §2's room: Tool calls and Biggest give
    up rows first): Textual lays it out in the same pass as the panels above it, so no frame stands with the page
    scrolling for want of it. Stacked (a narrow window), it is as tall as its panels hold, and the page scrolls. (Watch
    for gives up rows next once it lists more.)"""

    held = 1  # the rows Tool calls and Biggest hold: the more of their rows, at most `ROWS`, or an empty label's one

    def on_mount(self) -> None:
        """Lay out its list too, now that it is mounted."""
        self._arrange(self.has_class("-stacked"))

    def hold(self, rows: int) -> None:
        """Tool calls now holds this many rows."""
        if rows != self.held:
            self.held = rows
            self._arrange(self.has_class("-stacked"))

    def _arrange(self, stacked: bool) -> None:
        super()._arrange(stacked)
        self.styles.height = "auto" if stacked else "1fr"
        self.styles.min_height = None if stacked else BORDERS + 1
        self.styles.max_height = None if stacked else BORDERS + self.held
        self.styles.grid_rows = "auto" if stacked else "1fr"
        for listed in [*self.query(CallsList), *self.query(BiggestList)]:  # its own style's height would come first
            listed.styles.height = "auto" if stacked else "1fr"


def tabs(view: str) -> Content:
    """The row of tabs, the view shown on `selection`, as the menu's highlighted entry, the others in `quiet`."""
    parts: list[tuple[str, str] | str] = []
    for name in VIEWS:
        style = "bold $clank-selected-text on $clank-selection" if name == view else "$clank-quiet"
        parts += [(f" {TITLES[name]} ", style), " "]
    return Content.assemble(*parts)


def view_at(column: int) -> str | None:
    """The view whose tab stands at this column of the row of tabs, if any."""
    start = 0
    for name in VIEWS:
        width = len(f" {TITLES[name]} ")
        if start <= column < start + width:
            return name
        start += width + 1
    return None


def heading(view: str, seen: Seen | None = None, zone: tzinfo | None = None) -> Content:
    """The view's one heading line: the session it follows (design 0012 §2: OpenCode, the workspace, the session's
    title, its agent, what it does, its steps and calls, since when, that it is the newest of the folder), or that none
    is, and why."""
    said, why = HEADINGS[view]
    if view != "flow" and seen is not None and seen.head is not None:
        head = seen.head
        since = head.get("since")
        when = datetime.fromtimestamp(since / 1000, UTC).astimezone(zone).strftime("%H:%M") if since else ""
        status = str(head.get("status") or "")
        pinned = seen.box if seen.box.startswith("the ") else f"the flow's box {seen.box}"
        newest = f"{pinned} (Esc goes back to it)" if seen.box else "the newest of this folder"
        cost = (head.get("cost") or {}).get("said")  # a cloud model's, in the service's words (design 0016 §11)
        facts = [str(head.get("agent") or ""), STATES.get(status, status),
                 f"{head.get('steps') or 0} steps, {head.get('calls') or 0} calls",
                 f"this session {cost}" if cost else "", f"since {when}" if when else "", newest]  # fmt: skip
        title = "“" + str(head.get("title") or "untitled") + "”"
        return Content.assemble(
            ("OpenCode", "bold"), " · workspace ", (str(seen.workspace), "$clank-name"), " · ", (title, "$clank-name"),
            (" · " + " · ".join(fact for fact in facts if fact), "$clank-quiet"),
        )  # fmt: skip
    if view != "flow" and seen is not None:
        why = NONE_SEEN.format(workspace=seen.workspace) if seen.workspace else NO_WORKSPACE
    return Content.assemble((said, "bold"), (f" · {why}", "$clank-quiet"))


class MonitorPage(Page):
    """The Monitor: its tabs, its heading line, and its three views of panels."""

    ENTRY = MenuEntry(
        "monitor",
        "Monitor",
        "Everything the local model does in a session: its context window, what it does now, its branching flow and "
        "its tool calls; what to watch for, and the Guide. Three views: Flow, Session and Context.",
        "design 0012 §2",
        key="F10",
    )
    PANELS = (
        "monitor-flow-boxes",
        "monitor-flow-selected",
        "monitor-flow-thinking",
        "monitor-flow-calls",
        "monitor-flow-context",
        "monitor-flow-orchestrator",
        "monitor-flow-waiting",
        "monitor-flow-side",
        "monitor-flow-models",
        "monitor-flow-brief",
        "monitor-flow-deliverables",
        "monitor-flow-ahead",
        "monitor-flow-d4-flow",
        "monitor-flow-d4-cards",
        "monitor-flow-d4-calls",
        "monitor-flow-d2-list",
        "monitor-flow-d2-settings",
        "monitor-flow-d3-where",
        "monitor-flow-d3-file",
        "monitor-flow-d3-report",
        "monitor-flow-d3-brief",
        "monitor-flow-d3-decision",
        "monitor-session-context",
        "monitor-session-now",
        "monitor-session-flow",
        "monitor-session-watch",
        "monitor-session-guide",
        "monitor-session-live",
        "monitor-session-calls",
        "monitor-session-biggest",
        "monitor-context-totals",
        "monitor-context-parts",
        "monitor-context-gpu",
        "monitor-context-growth",
        "monitor-context-room",
        "monitor-context-freed",
        "monitor-context-sources",
    )
    KEYS = (
        PageKey("f10", "next_view", "next view", "F10 again, on the Monitor: its next view, Flow, Session, Context"),
        PageKey(
            "enter",
            "open",
            "open",
            "on the Session view's Context window panel (c): the Context view; on Watch for (w): its marks whole; on "
            "Tool calls (t): the call highlighted, whole; on Biggest in the context (b): the item highlighted, whole; "
            "on the Context view's What is in it: the part's items; on the Flow view: what the box chosen holds (a "
            "running box's session, in the Session view; a finished box's deliverable)",
        ),
        PageKey("escape", "back", "back", "from the Context view back to the Session view; from a session opened on "
                "a flow's box, back to the box; elsewhere Esc goes to the menu"),
        PageKey("full_stop", "stop", "stop", "on the Session view: stop the session the page follows, now (the Guide, "
                "design 0012 §9.2)"),
        PageKey("m", "note", "note", "on the Session view: a note to the model, about the node under the flow's "
                "cursor (§9.3)"),
        PageKey("k", "compact", "compact", "on the Session and Context views: compact the session at its next step, "
                "asked first (§9.6)"),
        PageKey("p", "pause", "pause", "on the Session view: pause the session after its step, or resume it, asked "
                "first (§9.4); on the Flow view: pause the flow (no box starts, the running one goes on), or "
                "resume it"),
        PageKey("u", "undo", "undo", "on the Session view: undo the session's last step, or the turn, asked first with "
                "what it takes back; while undone, redo it (§9.5)"),
        PageKey("x", "drop", "drop", "on the Session view: clear the result of the call under the flow's cursor, or "
                "highlighted in Tool calls or Biggest in the context, asked first (§9.7); on the Context view: the "
                "result highlighted in a part's items, or in what could be freed (§4.7)"),
        PageKey("l", "live", "live text", "on the Session view: the session's request as it is written, under the "
                "flow, or hidden again (§7)"),
        PageKey("O", "orchestrator", "orchestrator", "on the Flow view: the flow's orchestrator on steering, then "
                "watching, then off: a model that checks each box and tells you at once what you should know; "
                "steering, it also changes the boxes ahead and answers the run's questions, within its limits "
                "(design 0013 §16)"),
        PageKey("plus", "bigger_boxes", "bigger boxes", "on the Flow view: the flow's boxes larger (small, medium, "
                "large), kept in the console's settings"),
        PageKey("minus", "smaller_boxes", "smaller boxes", "on the Flow view: the flow's boxes smaller"),
        PageKey("L", "ledger", "ledger", "on the Flow view: the orchestrator's ledger, whole, in a window: its facts "
                "and plan, then each decision with why (design 0013 §16)"),
        PageKey("e", "edit_box", "edit the box", "on the Flow view: the box chosen's settings, each with its key "
                "(board D2)"),
        PageKey("o", "open_file", "open in VS Code", "on the Flow view: a deliverable in Clank's VS Code window, the "
                "one highlighted in Deliverables, else the newest the box chosen wrote"),
        PageKey("r", "run_from", "run from here", "on the Flow view: run the flow again from the box chosen, and every "
                "box after it, as new tries, asked first; a flow not run yet (one built with the model), from its "
                "start"),
        PageKey("h", "run_log", "run log", "on the Flow view: the run's log, whole, oldest first, in a window"),
        PageKey("n", "new_flow", "new flow", "on the Flow view: build a new flow with the model: a planning starts "
                "beside the console and the view shows it built (over SSH, talk with the model from another terminal: "
                "`clank flow attach`; in Windows Terminal, a pane split off on the right; in VS Code's terminal, "
                "Clank's VS Code window); a planning open already is set aside only once asked first (design 0013 "
                "§15)"),
        PageKey("N", "new_flow_vscode", "new flow in VS Code", "on the Flow view: the same, OpenCode in Clank's VS "
                "Code window (over SSH, from another terminal: `clank flow attach`)"),
    )  # fmt: skip
    VIEWS = VIEWS
    BOARDS = ("d2", "d3", "d4")  # the Flow view's boards beside D1 (design 0013 §12)
    VIEW_KEYS: ClassVar[dict[str, tuple[str, ...]]] = {
        "session": ("f10", "enter", "escape", "full_stop", "m", "k", "p", "u", "x", "l"),
        "flow": ("f10", "enter", "O", "L", "e", "o", "p", "r", "h", "n", "N", "plus", "minus"),
        "context": ("f10", "enter", "escape", "k", "x"),
    }  # the keys each view's keys bar shows, from `KEYS`
    BUILDING_KEYS = ("f10", "enter", "O", "n", "N")  # the Flow view's, while a flow is built with the model
    MACHINE_COLUMN = False  # its panels take the column's room (design 0012 §2); F5 shows it
    MENU_COLUMN = (
        False  # the flow takes the whole width, as the website draws it (decision 0125); Ctrl+B shows the menu
    )

    DEFAULT_CSS = """
    #monitor-tabs {
        height: 1;
    }
    /* The flow across the whole width (decision 0125), at most 60% of the window high, so Selected and Waiting for
       you stand under it on screen; a taller flow scrolls inside its panel. */
    #monitor-flow-boxes {
        max-height: 60vh;
    }
    #monitor-heading {
        height: 1;
        text-wrap: nowrap;
        text-overflow: ellipsis;
        margin-bottom: 1;
    }
    MonitorPage .view-flow, MonitorPage .view-session, MonitorPage .view-context {
        display: none;
    }
    MonitorPage.-view-flow .view-flow, MonitorPage.-view-session .view-session,
    MonitorPage.-view-context .view-context {
        display: block;
    }
    MonitorPage.-view-session .view-session.live-text {
        display: none;
    }
    MonitorPage.-view-session.-live .view-session.live-text {
        display: block;
    }
    #monitor-flow-chart {
        height: 1fr;
    }
    PanelGrid.-stacked #monitor-flow-chart {
        height: auto;
        max-height: 24;
    }
    #monitor-flow-chart-boxes {
        height: auto;
        max-height: 56vh;
    }
    MonitorPage.-view-flow .view-flow.board-d2, MonitorPage.-view-flow .view-flow.board-d3,
    MonitorPage.-view-flow .view-flow.board-d4 {
        display: none;
    }
    MonitorPage.-view-flow.-board-d2 .view-flow.board-d2, MonitorPage.-view-flow.-board-d3 .view-flow.board-d3,
    MonitorPage.-view-flow.-board-d4 .view-flow.board-d4 {
        display: block;
    }
    MonitorPage.-view-flow.-board-d2 .view-flow.board-d1, MonitorPage.-view-flow.-board-d3 .view-flow.board-d1,
    MonitorPage.-view-flow.-board-d4 .view-flow.board-d1 {
        display: none;
    }
    PanelGrid.-stacked #monitor-flow-chart-boxes {
        height: auto;
        max-height: 30;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id, classes=f"-view-{FIRST_VIEW}")
        self.view = FIRST_VIEW
        self.seen: Seen | None = None  # the session followed, as last read
        self._following: Following | None = None
        self._watching: Watching | None = None
        self._came: Seen | None = None  # a reading of the session and its flow, not drawn yet
        self._now_came: tuple[str, dict[str, Any]] | None = None  # what a session does now, not drawn yet
        self._live_came: tuple[str, str, dict[str, Any]] | None = None  # a reading of its live text: session, asked
        self._live_at = -READ_SECONDS
        self._live_reading = False  # a reading of the live text under way, whose answer is not in yet
        self._read_at = self._now_at = -READ_SECONDS  # when each was last read (`time.monotonic`)
        self._turned_at = time.monotonic()  # when the Now panel's spinner last turned
        self._calls_said = NO_SESSION  # what the Tool calls panel's empty label says
        self.redraws = 0  # the console's ticks on which the page drew what its readings brought: a test counts them
        self._head = ""  # the tabs and the heading as last drawn
        self._marks: list[dict[str, Any]] = []  # the marks the Watch for panel lists, as last drawn
        self._words_back: tuple[str, str, str] | None = None  # an undo's words given back and kept: session, words, why
        self.flows = FlowViewer(self)  # the Flow view (design 0013 §12)

    def compose(self) -> ComposeResult:
        """The tabs, the heading line, and each view's panels."""
        yield Label(id="monitor-tabs")
        yield Label(id="monitor-heading")
        yield from self.flows.compose()
        yield Panel(
            ContextWindow(id="monitor-context-window"),
            title="Context window",
            id="monitor-session-context",
            key="c",
            classes="view-session",
        )
        yield PanelGrid(
            Panel(
                NowView(id="monitor-now-view"), title="Now", id="monitor-session-now", key="n", classes="view-session"
            ),
            Panel(
                FlowChart(id="monitor-flow-chart"),
                title="Flow",
                id="monitor-session-flow",
                key="f",
                classes="view-session",
            ),
            watch_for(),
            Panel(
                GuideList(id="monitor-guide-list"),
                title="Guide",
                id="monitor-session-guide",
                key="g",
                classes="view-session",
            ),
            columns="2fr 3fr",
            spans={"monitor-session-flow": 3},
            stack_below=STACK_BELOW,
            classes="view-session",
        )
        yield Panel(LiveView(id="monitor-live-view"), title="Live text", id="monitor-session-live",
                    classes="view-session live-text")  # fmt: skip
        yield CallsRow(
            tool_calls(),
            biggest(),
            columns="2fr 3fr",
            stack_below=STACK_BELOW,
            classes="view-session",
        )
        yield drawn("summary", "Context window", "monitor-context-totals")
        yield PanelGrid(
            what_is_in_it(),
            drawn("gpu", "On the GPU exactly", "monitor-context-gpu"),
            columns="3fr 2fr",
            stack_below=STACK_BELOW,
            classes="view-context",
        )
        yield PanelGrid(
            drawn("growth", "Over this session", "monitor-context-growth"),
            drawn("room", "Where the room went", "monitor-context-room"),
            columns="3fr 2fr",
            stack_below=STACK_BELOW,
            classes="view-context",
        )
        yield could_be_freed()
        yield drawn("sources", "Where these figures come from", "monitor-context-sources")

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """The tabs and the heading when it comes on screen, and the session's flow and what it does now read at once;
        the Watch for panel's marks when they changed (the console's data)."""
        if "all" in changed:
            self._draw_head()
            self._read()
            self._read_now()
        if changed & {"all", "marks"}:
            self._draw_marks(list((data.marks or {}).get("marks") or []))

    def tick(self) -> None:
        """On each of the console's redraw ticks: draw what the readings brought since the last, together, so the page
        redraws no more often than the console does, four times a second (design 0012 §2); turn the Now panel's
        spinner while the session works; then start the readings due: the session followed and its flow once a second,
        what it does now on every tick while it works and once a second while it does not (design 0012 §5), and the
        live text as often while it is shown."""
        self.flows.tick()
        drew = False
        if self._came is not None:
            seen, self._came = self._came, None
            self._show(seen)
            drew = True
        if self._now_came is not None:
            (session, now), self._now_came = self._now_came, None
            if session == self._session():
                self.query_one("#monitor-now-view", NowView).show(now, self.console.zone)
                drew = True
        if self._live_came is not None:
            (session, asked, found), self._live_came = self._live_came, None
            if session == self._session() and self._live_shown:
                self.query_one("#monitor-live-view", LiveView).take(found, asked)
                drew = True
        if drew:
            self.redraws += 1
        if not self.display:
            return
        moment = time.monotonic()
        now_view = self.query_one("#monitor-now-view", NowView)
        working = now_view.working
        if working and moment - self._turned_at >= TURN_SECONDS:
            self._turned_at = moment
            now_view.turn()  # its cell alone (design 0012 §2)
        if moment - self._read_at >= READ_SECONDS:
            self._read()
        if working or moment - self._now_at >= READ_SECONDS:
            self._read_now()
        if self._live_shown and (working or moment - self._live_at >= READ_SECONDS):
            self._read_live()

    @property
    def _live_shown(self) -> bool:
        """Whether the live text is shown: `l` on the Session view, which shows it (design 0012 §7)."""
        return self.view == "session" and self.has_class("-live")

    def badge(self, frame: int) -> Content | None:
        """Beside "Monitor" in the menu: how many marks of Watch for are not seen yet (design 0012 §2, §8)."""
        unseen = int((self.console.data.marks or {}).get("unseen") or 0)
        return Content.assemble((str(unseen), "$clank-attention")) if unseen else None

    def _draw_marks(self, marks: list[dict[str, Any]]) -> None:
        """The Watch for panel: the newest marks, or its empty label while there are none; drawn only when they
        changed."""
        if marks == self._marks:
            return
        self._marks = marks
        listed = self.query_one(MarksList)
        listed.update(lines(marks))
        listed.display = bool(marks)
        self.query_one("#monitor-session-watch", Panel).query_one(Empty).display = not marks

    def _open_marks(self) -> None:
        """Enter on the Watch for panel: the marks it lists, each whole, in a window over the page; opened, they are
        seen. (A mark highlighted alone, with the flow's nodes, is the renderer's to add.)"""
        if not self._marks:
            return
        self.app.push_screen(DetailsScreen("Watch for: the newest marks", whole(self._marks)))
        ids = [str(mark["id"]) for mark in shown(self._marks) if not mark.get("seen")]
        if ids:
            client = self.console.client
            actions.call(self.console, lambda: client.post("agents/marks/seen", {"ids": ids}), quiet=True)

    def _toggle_live(self) -> None:
        """`l`: the live text under the Flow's row, read from now on, and the focus in it; again, hidden."""
        shown = not self.has_class("-live")
        self.set_class(shown, "-live")
        if shown:
            self._read_live()
            self.query_one("#monitor-session-live", Panel).enter()

    def _open_call(self) -> None:
        """Enter on the Tool calls panel: the call highlighted, read whole through the bridge (a `docker exec`, so
        only now, on Enter, design 0012 §7) and shown in a window; when the bridge cannot give it, what the flow keeps
        of it and why."""
        row = self.query_one("#monitor-calls-list", CallsList).highlighted()
        head = (self.seen.head if self.seen is not None else None) or {}
        if row is None or self.seen is None or not self.seen.workspace or not head.get("session"):
            return
        workspace, session, port = str(self.seen.workspace), str(head["session"]), int(head.get("port") or 0)
        path = f"agents/sessions/{quote(workspace)}/{port}/{quote(session)}/part/{quote(str(row['step']))}/"
        path += quote(str(row["id"]))
        client, zone = self.console.client, self.console.zone

        def opened(window: CallScreen) -> None:
            self.app.push_screen(window)

        def work() -> None:
            try:
                found, why = client.get(path), ""
            except (NotRunning, ClientError) as error:
                found, why = None, str(error)
            self.console.call_from_thread(opened, CallScreen(call_title(row), call_whole(row, found, why, zone)))

        self.run_worker(work, thread=True, group="monitor-call", exit_on_error=False)

    def _open_item(self) -> None:
        """Enter on Biggest in the context: the item highlighted, whole, with why it is marked, in a window."""
        listed = self.query_one("#monitor-biggest-list", BiggestList)
        row = listed.highlighted()
        if row is not None:
            self.app.push_screen(DetailsScreen(f"Biggest in the context: {row.get('what')}",
                                               item_whole(row, listed.estimate)))  # fmt: skip

    def _open_freed(self) -> None:
        """Enter on Could be freed: Compact now asks first, as `k` does; the others list their items and how each is
        dropped, in a window."""
        listed = self.query_one("#monitor-freed-list", FreedList)
        row = listed.highlighted()
        if row is None:
            return
        if row.get("how") == "compact":  # once this Enter is done: the window it opens takes Enter as "do it"
            self.call_later(self._guide, "compact")
            return
        rows = freed_items(listed.totals, row)
        self.call_later(self._items, f"Could be freed: {row['words']}", rows, freed_notes(listed.totals, row))

    def _open_part(self) -> None:
        """Enter or `x` on What is in it: the highlighted part's items, biggest first, in their window, where `x`
        drops one (opened once this key is done, so the key never acts in it)."""
        listed = self.query_one("#monitor-parts-list", PartsList)
        part = listed.highlighted()
        if part is not None:
            name = str(part["part"])
            title = f"{part['label']}, about {int(part['tokens']):,} tokens of the estimate"
            self.call_later(self._items, title, part_rows(listed.totals, name), part_notes(listed.totals, name))

    def _items(self, title: str, rows: list[dict[str, Any]], notes: list[str]) -> None:
        """Items in their window (`itemsscreen.py`); the one `x` closes it with goes to the Guide's Drop."""
        lines = [item_line(row) for row in rows]
        self.app.push_screen(ItemsScreen(title, rows, lines, notes), self._drop_item)

    def _drop_item(self, row: dict[str, Any] | None) -> None:
        """`x` on an item of the estimate (design 0012 §4.7): the Guide's Drop of that call's result, by the same path
        as the Session view's `x` (the Guide asked about that call, then its window); an item Drop cannot clear says
        why; the window closed with none (Esc) says nothing."""
        if row is None:
            return
        why = droppable(row)
        if why:
            self.console.say(f"Drop cannot run now: {why}", True)
            return
        self._guide("drop", str(row["node"]))

    def _context_drop(self) -> None:
        """`x` on the Context view: on What is in it, the part's items' window; on a row of Could be freed that drops,
        its items' window; `x` there drops the one highlighted."""
        panel = self._focused_panel()
        if panel == "monitor-context-parts":
            self._open_part()
            return
        row = (
            self.query_one("#monitor-freed-list", FreedList).highlighted() if panel == "monitor-context-freed" else None
        )
        if row is not None and row.get("how") == "drop":
            self._open_freed()
            return
        self.console.say("x drops a call's result: highlight a part in What is in it, or a row of Could be freed that "
                         "drops, then the result in its window", True)  # fmt: skip

    def show_view(self, name: str, into: str = "") -> None:
        """Bring a view on screen. When the focus was in the page, it goes to the panel `into`, else to the view's
        first panel, since what had it is hidden now."""
        inside = self.app.focused is not None and self in self.app.focused.ancestors
        self.view = name
        for each in VIEWS:
            self.set_class(each == name, f"-view-{each}")
        self._draw_head()
        self.draw_keys()
        if inside:
            (self.query_one(f"#{into}", Panel) if into else self.panels(name)[0]).enter()

    def show_board(self, name: str) -> None:
        """Bring a board of the Flow view on screen (D1, or D4), on the Flow view."""
        if self.view != "flow":
            self.show_view("flow")
        self.flows.show_board(name)

    def shown_keys(self) -> tuple[PageKey, ...]:
        """The keys of the view on screen (`VIEW_KEYS`); on the Flow view while a flow is built with the model, those
        that act then (`BUILDING_KEYS`)."""
        if self.view == "flow" and self.flows.board != "d1":
            return self.flows.board_keys()
        wanted = self.VIEW_KEYS.get(self.view, ())
        if self.view == "flow" and (self.flows.view or {}).get("planning"):
            wanted = self.BUILDING_KEYS
        if self.view == "session" and not self.flows.opened_from:
            wanted = tuple(key for key in wanted if key != "escape")  # no box to go back to: Esc is the menu's
        return tuple(key for key in self.KEYS if key.key in wanted)

    def draw_keys(self) -> None:
        """The keys bar shows the view's keys, while the page is on screen."""
        if self.display and self.is_mounted:
            self.console.query_one("#keys", KeysBar).show_keys(self.shown_keys())

    def panels(self, view: str) -> list[Panel]:
        """A view's panels, in order."""
        return list(self.query(f"Panel.view-{view}").results(Panel))

    def press(self, key: str) -> bool:
        """F10, the next view; Enter on the Context window panel, the Context view; Esc there, back; in the Session
        view, a panel's letter, that panel."""
        if key == "f10":
            self.show_view(VIEWS[(VIEWS.index(self.view) + 1) % len(VIEWS)])
            return True
        if self.view == "flow" and self.flows.press(key):
            return True
        if key == "escape" and self.view == "session" and self.flows.opened_from and self.app.screen is self.screen:
            self.back_to_box()
            return True
        if key == "escape" and self.view == "context" and self.app.screen is self.screen:  # no window over it
            self.show_view("session", into="monitor-session-context")
            return True
        if key == "enter" and self.view == "session" and self._focused_panel() == "monitor-session-context":
            self.show_view("context")
            return True
        if key == "enter" and self.view == "session" and self._focused_panel() == "monitor-session-watch":
            self._open_marks()
            return True
        if key == "enter" and self.view == "session" and self._focused_panel() == "monitor-session-calls":
            self._open_call()
            return True
        bare = self.app.screen is self.screen  # no window over the page: one takes its own keys, never the page too
        if bare and key == "enter" and self.view == "session" and self._focused_panel() == "monitor-session-biggest":
            self._open_item()
            return True
        if bare and key == "enter" and self.view == "context" and self._focused_panel() == "monitor-context-parts":
            self._open_part()
            return True
        if bare and key == "enter" and self.view == "context" and self._focused_panel() == "monitor-context-freed":
            self._open_freed()
            return True
        if bare and key == "k" and self.view == "context":
            self._guide("compact")
            return True
        if bare and key == "x" and self.view == "context":
            self._context_drop()
            return True
        if key == "l" and self.view == "session":
            self._toggle_live()
            return True
        if key in LETTERS and self.view == "session":
            self.query_one(f"#{LETTERS[key]}", Panel).enter()
            return True
        if key in PRESSED and self.view == "session":
            self._guide(PRESSED[key])
            return True
        return False

    def _guide(self, action: str, item: str = "") -> None:
        """One of the Guide's actions on the session followed (design 0012 §9.1): Stop at once; a note in its window;
        Compact now, the pause, Undo and Drop once confirmed. One that cannot run says why on the message line."""
        guide = (self.seen.guide if self.seen is not None else None) or {}
        found = next((each for each in guide.get("actions") or [] if each["action"] == action), None)
        if found is None:
            why = guide.get("unavailable") or "the page follows no session"
            self.console.say(f"the Guide acts on the session the page follows: {why}", True)
            return
        if not found["can"]:
            self.console.say(f"{found['title']} cannot run now: {found['why']}", True)
            return
        path = f"agents/guide/{quote(str(guide['workspace']))}/{quote(str(guide['session']))}/{action}"
        client = self.console.client
        if action == "stop":
            actions.call(self.console, lambda: client.post(path), done="stopping the session")
            return
        if action == "undo":
            self._undo(found, path)
            return
        if action == "drop":
            self._drop(path, item)
            return
        said = [
            f"{found['does']}.",
            f"The call: {'; '.join(found['calls'])}",
            f"What it costs: {found['cost']['words']}.",
        ]
        if action == "compact":

            def confirmed(yes: bool | None) -> None:
                if yes:
                    actions.call(self.console, lambda: client.post(path), done="compaction asked")

            self.app.push_screen(ConfirmScreen("Compact now", said), confirmed)
            return
        if action == "pause":
            resume = bool(found.get("paused"))
            path = path.removesuffix("/pause") + ("/resume" if resume else "/pause")

            def paused(yes: bool | None) -> None:
                if yes:
                    done = "resumed: the held request goes to the model" if resume else "pausing after this step"
                    actions.call(self.console, lambda: client.post(path), done=done)

            self.app.push_screen(ConfirmScreen("Resume" if resume else "Pause after this step", said), paused)
            return
        if self._words_back is not None and self._words_back[0] == self._session():  # kept when their window was left
            self._words_window(found, path, *self._words_back[1:])
            return
        self._note_window(found, path)

    def _note_window(self, found: dict[str, Any], path: str) -> None:
        """The note's window: its text, what it is about (the node under the flow's cursor), what it does and what it
        costs."""
        chart = self.query_one("#monitor-flow-chart", FlowChart)
        node = chart.drawn.nodes.get(chart.cursor) if chart.drawn is not None else None
        fields = [
            Field("text", "Your note", "what the model should know"),
            Field("about", "About (left empty, about nothing in particular)",
                  value=about(node, self.seen.view if self.seen is not None else None)),
        ]  # fmt: skip
        client = self.console.client

        def given(values: dict[str, str] | None) -> None:
            if values and values.get("text"):
                body = {"text": values["text"], "about": values.get("about", "")}
                actions.call(self.console, lambda: client.post(path, body), done="note sent")

        note = (
            f"{found['does']}. What it costs: {found['cost']['words']}. Enter in the last field, or Ctrl+S, sends it; "
        )
        self.app.push_screen(FormScreen("A note to the model", fields, note + "Esc leaves it."), given)

    def _words_window(self, found: dict[str, Any], path: str, text: str, warning: str = "") -> None:
        """The words of the owner's messages an undo took back, whole, in a window of several lines: their line breaks,
        their indentation and each message's text kept (messages a blank line apart). Ctrl+S sends them as a note,
        about nothing, since what they were about is taken back; Esc keeps them, and `m` opens them again, so no word
        of the owner's is lost. `warning`, when OpenCode took back more than the preview, leads the window's note."""
        self._words_back = (self._session(), text, warning)
        client = self.console.client

        def given(edited: str | None) -> None:
            if edited is None:
                self.console.say("your words are kept: m opens them again; your next message makes the undo final")
                return
            self._words_back = None
            if edited.strip():
                body = {"text": edited, "about": ""}
                actions.call(self.console, lambda: client.post(path, body), done="note sent: the undo is final")

        note = f"{warning}. " if warning else ""
        note += (f"{found['does']}. What it costs: {found['cost']['words']}. Ctrl+S sends them as your note, which "
                 "makes the undo final; Esc keeps them, and m opens them again.")  # fmt: skip
        self.app.push_screen(EditScreen("Your words, given back", text, note), given)

    def _undo(self, found: dict[str, Any], path: str) -> None:
        """`u` (design 0012 §9.5): Undo, or Undo turn, once confirmed, its window the preview (why the step alone is
        refused, what it takes back) and the exact call; what is sent is the revert the window showed, which the
        service refuses when the session moved on since. While a revert is pending, Redo."""
        client = self.console.client
        said = [
            f"{found['does']}.",
            f"The call: {'; '.join(found['calls'])}",
            f"What it costs: {found['cost']['words']}.",
        ]
        if found.get("mode") == "redo":
            redo = path.removesuffix("/undo") + "/redo"

            def redone(yes: bool | None) -> None:
                if yes:
                    actions.call(self.console, lambda: client.post(redo), done="brought back what the undo took back")

            self.app.push_screen(ConfirmScreen("Redo", said), redone)
            return
        revert = found.get("revert") or {}
        takes = found.get("takes") or {}
        body = {"message": str(revert.get("message") or ""), "part": str(revert.get("part") or ""),
                "steps": list(takes.get("steps") or []), "said": list(takes.get("said") or [])}  # fmt: skip

        def confirmed(yes: bool | None) -> None:
            if not yes:
                return

            def work() -> None:
                try:
                    answer = client.post(path, body)
                except (NotRunning, ClientError) as error:
                    self.console.call_from_thread(self.console.say, str(error), True)
                    return
                self.console.call_from_thread(self._undone, answer, path.removesuffix("/undo") + "/note")

            self.run_worker(work, thread=True, group="monitor-undo", exit_on_error=False)

        refused = [f"{found['refused']}."] if found.get("refused") else []
        self.app.push_screen(ConfirmScreen(str(found["title"]), refused + said), confirmed)

    def _undone(self, answer: dict[str, Any], path: str) -> None:
        """An undo done: said; when it took back a message of the owner's (the turn's, or one sent after the step), the
        window of its words, whole (`_words_window`; cut, said so, when OpenCode's history did not give them whole)."""
        why = str(answer.get("why") or "")  # OpenCode took back more than the preview: said in a window, which stays
        text = str(answer.get("text") or "")
        if not text.strip():
            self.console.say("undone: u redoes it until your next message")
            if why:
                self.app.push_screen(DetailsScreen("Undo took back more than it showed", [why]))
            return
        cut = "" if answer.get("whole", True) else " (cut: OpenCode's history did not give it whole)"
        undone = "your turn is undone" if answer.get("mode") == "turn" else "undone, your message with it"
        self.console.say(f"{undone}: its words are in their window{cut}; u redoes it until you send one")
        guide = (self.seen.guide if self.seen is not None else None) or {}
        found = next((each for each in guide.get("actions") or [] if each["action"] == "note"), None)
        if found is not None:
            self._words_window(found, path, text, "; ".join(each for each in (why, cut.strip(" ()")) if each))
        else:  # no note to send them with: kept, for m
            self._words_back = (self._session(), text, why)

    def _drop(self, path: str, item: str = "") -> None:
        """`x` (design 0012 §9.7): the call's Drop, read for that call (what it frees, what it costs, or why it cannot
        run), then its window, which asks first and says the drop is final. The call is the one named (`item`, an item
        of the estimate's), else the one under the flow's cursor or highlighted (`_call_under`)."""
        part, why = (item, "") if item else self._call_under()
        if not part:
            self.console.say(why, True)
            return
        client = self.console.client

        def work() -> None:
            try:
                found = client.get(path.removesuffix("/drop"), item=part)
            except (NotRunning, ClientError) as error:
                self.console.call_from_thread(self.console.say, str(error), True)
                return
            drop = next((each for each in found.get("actions") or [] if each["action"] == "drop"), None)
            self.console.call_from_thread(self._drop_asked, drop, path, part)

        self.run_worker(work, thread=True, group="monitor-drop", exit_on_error=False)

    def _drop_asked(self, drop: dict[str, Any] | None, path: str, part: str) -> None:
        """Drop's window for the call, once it can run; else why not, on the message line."""
        if drop is None or not drop["can"]:
            self.console.say(f"Drop cannot run now: {drop['why'] if drop else 'the Guide offers no Drop'}", True)
            return
        item = drop.get("item") or {}
        title = f"Drop step {item.get('step')}'s `{item.get('tool')}` result"
        said = [f"{drop['does']}.", f"The call: {'; '.join(drop['calls'])}", f"What it costs: {drop['cost']['words']}."]
        client = self.console.client

        def confirmed(yes: bool | None) -> None:
            if yes:
                done = f"step {item.get('step')}'s `{item.get('tool')}` result cleared"
                actions.call(self.console, lambda: client.post(path, {"part": part}), done=done)

        self.app.push_screen(ConfirmScreen(title, said), confirmed)

    def _call_under(self) -> tuple[str, str]:
        """The call `x` drops: the one highlighted in Tool calls when that panel has the focus, else the one under the
        flow's cursor; "" and why when there is none."""
        if self._focused_panel() == "monitor-session-calls":
            row = self.query_one("#monitor-calls-list", CallsList).highlighted()
            return (str(row["id"]), "") if row is not None else ("", "Tool calls lists no call yet")
        if self._focused_panel() == "monitor-session-biggest":
            item = self.query_one("#monitor-biggest-list", BiggestList).highlighted()
            why = droppable(item)
            return ("", f"Drop cannot run now: {why}") if why else (str((item or {})["node"]), "")
        chart = self.query_one("#monitor-flow-chart", FlowChart)
        node = chart.drawn.nodes.get(chart.cursor) if chart.drawn is not None else None
        if node is None or node.kind != "call":
            return "", ("x clears one call's result: put the flow's cursor on a call (→ opens a group), or highlight "
                        "one in Tool calls (t)")  # fmt: skip
        if "/" in node.id:
            return "", "a subagent's call: the Guide acts on the root session (design 0012 §3)"
        return node.id, ""

    def on_click(self, event: events.Click) -> None:
        """A click on a tab shows its view."""
        tabs = self.query_one("#monitor-tabs", Label)
        if event.widget is tabs and (name := view_at(event.screen_x - tabs.region.x)) is not None:
            self.show_view(name)

    def explain(self) -> tuple[str, list[str]]:
        """The view's heading line whole (a narrow page cuts it with "…"), what the view shows, how to move, and what
        is built so far."""
        views = {
            "flow": "The Flow view shows a flow, the work as a program of boxes (design 0013 §12): the flow this "
            "folder follows (its active run's, else the one run last), its boxes and their lines in rows read left to "
            "right, a DECOMPOSE's tasks stacked as one fan, a box's border saying its state (heavier while it runs, "
            "dashed while it waits or is proposed); the box chosen in Selected, with a Live box while it runs; the "
            "models it uses; what waits for you; its brief, checked; its deliverables; and the boxes ahead with what "
            "each costs. The arrows move from box to box, End back to the box at work; Enter opens what the box holds "
            "(a running box's session in the Session view, Esc coming back to the box; a finished box's "
            "deliverable; on Deliverables, the file highlighted); o opens a deliverable in Clank's VS Code window; e "
            "edits the box chosen; p pauses the flow or resumes it; r runs it again from the box chosen (a flow not "
            "run yet, from its start); h shows the run's log. n starts a planning beside the console, a flow built "
            "with the model (over SSH, talk with the model from another terminal: `clank flow attach`; in Windows "
            "Terminal, in a pane split off on the right; in VS Code's terminal, or with N, in Clank's VS Code window), "
            "and the view shows it built: its steps, its drafts, its session live; a planning open already is set "
            "aside only once asked first. A terminal that keeps F10 for itself reaches this view with `clank console "
            "--page monitor "
            "--view flow`.",
            "session": "The Session view follows one OpenCode session as it works: its context window (c), what it "
            "does now (n), its branching flow (f), its tool calls (t), the biggest items in its context (b), what to "
            "watch for (w) and the Guide (g). A panel's letter goes to it; Enter on the Context window opens the "
            "Context view, and Enter on Watch for opens the marks it lists, each whole, which sees them. l shows the "
            "live text under the flow: the session's model request as it is written (its thinking dimmed, its "
            "calls' arguments in color), from the gateway, the only one that sees it as it comes; l again hides it.",
            "context": "The Context view opens the context window whole, from the estimate of the last finished "
            "step's request (each part's characters, counted by the gateway, shared out to the engine's own count): "
            "what is in it, part by part, with its tokens, share, items, the biggest and its last ten steps (the "
            "arrows move through the parts, Enter lists a part's items); what sits on the GPU exactly; how the "
            "session grew, each step split by part, and where the room went; what could be freed (Enter on Compact "
            "now, or k, asks first); and where these figures come from. Enter or x on a part, or Enter on a row of "
            "what could be freed, opens the window of its items, where x drops the result highlighted through the "
            "Guide's Drop, which asks first. Esc goes back to the Session view.",
        }
        marks = (
            whole(self._marks) if self.view == "session" and self._focused_panel() == "monitor-session-watch" else []
        )
        if self.view == "session" and self._focused_panel() == "monitor-session-guide":
            marks = guide_whole(self.seen.guide if self.seen is not None else None)
        if self.view == "flow":
            marks = self.flows.explain()
        return f"Monitor · the {TITLES[self.view]} view", [
            heading(self.view, self.seen, self.console.zone).plain,
            *marks,
            self.ENTRY.summary,
            views[self.view],
            "F10 again moves to the next view: Flow, Session, Context. The machine column is hidden here; F5 shows it.",
            "The Flow panel (f) draws the session's branching flow (design 0012 §6): its branches (a plan's steps, the "
            "todo list's items or your messages) and their calls, opening to the right; in it, the up and down arrows "
            "move from node to node, left folds a branch (or goes to its parent), right opens it (or goes to its first "
            "child), End goes back to now and follows it.",
            "The Context window panel (c) shows the session's totals, from the facts of the model the slot runs "
            "(design 0012 §4): how much of the window its last finished step used, how much is left before OpenCode "
            "compacts, the share read from the cache, the bar by part with what each part holds (an estimate: the "
            "gateway counts each request's characters by part, shared out to the engine's own count), what sits on "
            "the GPU, whose conversation the engine holds, and where these figures come from.",
            "Biggest in the context (b) lists the largest items in the session's context, by the estimate: each with "
            "its tokens, its part's color, the step it came with and what it is, marked when it is loop text, made "
            "again later (so it could be freed), cleared by OpenCode, or kept if compacted; the arrows move in it, "
            "and Enter shows the item highlighted whole, with why each mark.",
            "The Now panel (n) says what the session does this second (design 0012 §5): its phase (from the gateway "
            "for its model requests: waiting for its slot, reading the prompt or queued, thinking, answering, writing "
            "a call; from OpenCode for the session: running a tool, waiting for you, retrying, compacting, idle), its "
            "step and its time; the prompt (this step's time to its first token, and the last prompt whose size is "
            "known, read from the cache and new); the thinking against its budget and everything the answer writes "
            "against the output limit, about while counted live, the engine's own count once the answer ended; the "
            "call being written; the speed, with each step's; and the loop guard: each part's newest share against "
            "the limit under which it stops an answer, or what it stopped.",
            "The Tool calls panel (t) lists the session's calls, newest first: when each started, its tool, what it "
            f"does and its result's size in characters, a failed one in red with {mark('failed')}, one running with "
            f"{mark('on')}; the arrows move in it, and Enter reads the call highlighted whole (its input and its "
            "output) from the session's OpenCode server, through the workspace's container, and shows it in a window.",
            "The Guide panel (g) lists what you can do to the session (design 0012 §9), each with its key, what it "
            "does and what it costs, or why it cannot run now: . stops it at once, m writes a note to the model about "
            "the node under the flow's cursor, k compacts it at its next step once you confirm, p pauses it after its "
            "step once you confirm (the gateway holds its next model request, and its subagents', until p again "
            "resumes it), u undoes its last step once you confirm (OpenCode's revert at the end of the step before, "
            "the files restored; the first step after your message only with your message, its text back in the note "
            "window; u again redoes it until your next message), x clears the result of the call under the flow's "
            "cursor, or highlighted in Tool calls, once you confirm (the call stays; the drop is final).",
            "Built so far: the page, its three views and their panels (design 0012 §11, step 1), the context totals "
            "(step 3), the session's flow (step 6), what it does now (step 7), Watch for's marks (step 8: the rules "
            "run in the service, config/monitor.json says what each does), the Guide's Stop, note and Compact now "
            "(step 9), its Undo and Drop (step 10) and its Pause (step 11), the context's parts, the biggest items "
            "and the Context view (step 12), and the Flow view (design 0013's step 6).",
        ]

    def _focused_panel(self) -> str:
        focused = self.app.focused
        if focused is None:
            return ""
        return next((node.id or "" for node in focused.ancestors_with_self if isinstance(node, Panel)), "")

    def _read(self) -> None:
        """Read the session followed and its flow, off the screen's thread, while the page is on screen; what changed
        is drawn on the next tick. A reading still under way is left to finish (`Following.read` runs one at a time),
        never canceled, so the page shows each reading in order."""
        if not self.display:
            return
        self._read_at = time.monotonic()
        if self._following is None:
            self._following = Following(self.console.client, self.console.folder)
        following = self._following

        def work() -> None:
            try:
                seen = following.read()
            except (NotRunning, ClientError):
                return  # the header says the service does not answer; the next reading tries again
            if seen is not None:
                self.console.call_from_thread(setattr, self, "_came", seen)

        self.run_worker(work, thread=True, group="monitor-read", exit_on_error=False)

    def _session(self) -> str:
        """The session the page follows, "" for none."""
        return str(((self.seen.head if self.seen is not None else None) or {}).get("session") or "")

    def _read_now(self) -> None:
        """Read what the session followed does now, off the screen's thread, while the page is on screen; what changed
        is drawn on the next tick (`Watching.read` runs one at a time)."""
        session = self._session()
        if not self.display or not session or self.seen is None or not self.seen.workspace:
            return
        self._now_at = time.monotonic()
        if self._watching is None:
            self._watching = Watching(self.console.client)
        watching, workspace = self._watching, self.seen.workspace

        def work() -> None:
            try:
                found = watching.read(workspace, session)
            except (NotRunning, ClientError):
                return  # the next reading tries again
            if found is not None:
                self.console.call_from_thread(setattr, self, "_now_came", (session, found))

        self.run_worker(work, thread=True, group="monitor-now", exit_on_error=False)

    def _read_live(self) -> None:
        """Read the live text of the session followed from the offset held, off the screen's thread, while it is shown
        and the page is on screen; what came is drawn on the next tick. One reading at a time, the next only once the
        last one's answer is in: a reading begun before it was drawn would ask again from the offset before it, and
        what both brought would be shown twice (a slower machine showed it)."""
        session = self._session()
        if not self.display or not session or not self._live_shown or self._live_reading:
            return
        self._live_at = time.monotonic()
        self._live_reading = True
        if self._watching is None:
            self._watching = Watching(self.console.client)
        view = self.query_one("#monitor-live-view", LiveView)
        watching, after, asked = self._watching, view.length, view.request

        def work() -> None:
            found: dict[str, Any] | None = None
            try:
                found = watching.text(session, after, asked)
            except (NotRunning, ClientError):
                pass  # the next reading tries again
            finally:
                self.console.call_from_thread(self._live_read, session, asked, found)

        self.run_worker(work, thread=True, group="monitor-live", exit_on_error=False)

    def _live_read(self, session: str, asked: str, found: dict[str, Any] | None) -> None:
        """A reading of the live text answered: drawn on the next tick, before the next reading begins."""
        self._live_reading = False
        if found is not None:
            self._live_came = (session, asked, found)

    def _show(self, seen: Seen) -> None:
        """The session followed: its heading, its flow, its context totals, what the Guide offers; when it is another
        than before, what it does now is read at once, and nothing is said of it meanwhile."""
        followed = self._session()
        self.seen = seen
        self._draw_head()
        session = str((seen.head or {}).get("session") or "")
        self.query_one("#monitor-session-flow", Panel).note = FLOW_KEYS if seen.view is not None else ""
        chart = self.query_one("#monitor-flow-chart", FlowChart)
        chart.zone = self.console.zone
        chart.show(seen.view, seen.subagents, key=session, empty=NO_SESSION)
        self.query_one("#monitor-context-window", ContextWindow).show(seen.context, self.console.zone, seen.view)
        self.query_one("#monitor-guide-list", GuideList).show(seen.guide, self.console.zone)
        calls = self.query_one("#monitor-calls-list", CallsList)
        calls.show(seen.view, self.console.zone)
        said = self.query_one("#monitor-session-calls", Panel).query_one(Empty)
        if self._calls_said != (NO_CALL if session else NO_SESSION):
            self._calls_said = NO_CALL if session else NO_SESSION
            said.update(self._calls_said)
        said.display = not calls.shown
        items = self.query_one("#monitor-biggest-list", BiggestList)
        items.show(seen.context)
        empty = self.query_one("#monitor-session-biggest", Panel).query_one(Empty)
        relabel(empty, NO_PARTS if session else NO_SESSION)
        empty.display = not items.shown
        self.query_one(CallsRow).hold(min(max(len(calls.shown), len(items.shown)), ROWS) or 1)
        for drawn in self.query(Drawn):
            drawn.show(seen.context, self.console.zone, seen.view)
        listed = self.query_one("#monitor-parts-list", PartsList)
        listed.show(seen.context)
        said = self.query_one("#monitor-context-parts", Panel).query_one(Empty)
        relabel(said, waiting(seen.context) or "")
        said.display = not listed.shown
        frees = self.query_one("#monitor-freed-list", FreedList)
        frees.show(seen.context)
        said = self.query_one("#monitor-context-freed", Panel).query_one(Empty)
        relabel(said, waiting(seen.context) or NOTHING_FREED)
        said.display = not frees.shown
        if session != followed:
            self.query_one("#monitor-live-view", LiveView).forget()
            self.query_one("#monitor-now-view", NowView).show(None)
            if self._watching is not None:
                self._watching.forget()  # what it shows was cleared: the next reading is drawn, though nothing changed
            self._read_now()  # another session: what it does now, at once

    def open_session(self, workspace: str, session: str, label: str) -> None:
        """Enter on a flow's running box: the Session view on its session, pinned to it (design 0013 §12)."""
        if self._following is None:
            self._following = Following(self.console.client, self.console.folder)
        self._following.pin(workspace, session, label)
        self.show_view("session")
        self._read()

    def back_to_box(self) -> None:
        """Esc on a session opened from a flow's box: the page follows the folder's newest session again, and the Flow
        view shows the box."""
        if self._following is not None:
            self._following.unpin()
        self.flows.back()
        self._read()

    def draw_heading(self) -> None:
        """The tabs and the heading line, drawn again only when they changed (the Flow view asks, as its flow comes)."""
        self._draw_head()

    def on_chart_view_chosen(self, message: ChartView.Chosen) -> None:
        """A box of the Flow view chosen (Selected shows it), or a card of board D4 (its prompt shows)."""
        if isinstance(message.chart, BoxChart):
            self.flows.chosen()
        elif isinstance(message.chart, FlowList):
            self.flows.list_chosen()
        else:
            self.flows.card_chosen()

    def on_mount(self) -> None:
        """Draw everything the console holds, and every panel of the Flow view says what it waits for."""
        super().on_mount()
        self.flows.mounted()

    def _draw_head(self) -> None:
        """The tabs and the heading line, drawn again only when they changed."""
        said = flow_heading(self.flows.view, self.console.zone) if self.view == "flow" else None
        shown = tabs(self.view), said or heading(self.view, self.seen, self.console.zone)
        if self._head != shown[0].markup + shown[1].markup:
            self._head = shown[0].markup + shown[1].markup
            self.query_one("#monitor-tabs", Label).update(shown[0])
            self.query_one("#monitor-heading", Label).update(shown[1])
