"""The Monitor's Tool calls panel (design 0012 §2, §7; §11 step 7): the followed session's calls, newest first, from its
flow as the service keeps it (the bridge's watch forwards each call as it changes, step 4, so the panel is live and
costs no `docker exec`).

`rows` are the session's own calls, newest first, at most `SHOWN`; `line` draws one, cut to the panel's width: when it
started (the owner's clock), a mark (✗ for a call that failed, in the failed color, and what it does in that color too;
● for one pending or running, in the now color), its tool in its kind's color (design 0011 §2's `calls`), what it does
(its command, its title or its file: the flow's `what`) and its result's size in characters, as the flow keeps it (plan
s16's call 5: tokens come with step 12's estimate). A session followed with no call yet says so (`NO_CALL`).

Enter on a call reads it whole through the bridge (`GET
/agents/sessions/{workspace}/{port}/{session}/part/{message}/{part}`): a `docker exec` in the workspace's container,
so only on Enter, while the page is on screen (design 0012 §7). `whole` words what came back for a window
(`CallScreen`, which scrolls, since an output may run to the bridge's cap): its tool, state and title, its input, its
output (a long one's end, where a command says how it ended), its error and what was cut; when the bridge could not
give it (an older sandbox image, a container stopped), what the flow keeps of it and why.

`CallsList` is the panel's content: a list of the rows (↑↓ move in it), each line drawn again only when it changed
(`refill`), the highlight kept on the same call as calls come. It shows `ROWS` rows, scrolling beyond them, or fewer
when the page is short of rows (design 0012 §2: Tool calls gives up rows first; the Monitor's `CallsRow`).
"""

from datetime import UTC, datetime, tzinfo
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.content import Content
from textual.widgets import Label, ListView

from clank.components.agents.console.flowtree import chars, flat, tone_of, what
from clank.console.details import DetailsScreen
from clank.console.lists import refill
from clank.console.panel import WindowPanel
from clank.console.style import current, mark

SHOWN = 50  # the newest calls the panel lists
ROWS = 8  # the rows it shows, scrolling beyond them (fewer when the page is short of rows)
NO_CALL = "no tool call yet"  # a session followed that has made none
TOOL = 9  # the tool's column
SIZE = 11  # the size's column: "18.6K chars"
WIDTH = 46  # the width drawn for before the panel is laid out
RUNNING = ("pending", "running")


def rows(view: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The session's own calls, newest first (the flow keeps them in time order), at most `SHOWN`."""
    found = [node for node in (view or {}).get("nodes") or [] if node.get("kind") == "call" and not node.get("undone")]
    return list(reversed(found))[:SHOWN]


def line(row: dict[str, Any], width: int, zone: tzinfo | None = None) -> Content:
    """One call on one line, no wider than `width`: when, a mark, its tool, what it does, its result's size."""
    failed = bool(row.get("failed")) or row.get("status") == "error"
    running = row.get("status") in RUNNING
    sign = (mark("failed"), "$clank-failed") if failed else ((mark("on"), "$clank-now") if running else (" ", ""))
    tool = str(row.get("tool") or "")
    size = chars(int(row["length"])) if row.get("length") is not None and not running else ""
    head = Content.assemble(
        (_clock(row.get("started"), zone), "$clank-quiet"), " ", sign, " ", (f"{tool:<{TOOL}}", tone_of(tool)), " "
    )
    room = width - head.cell_length - (len(size) + 1 if size else 0)
    said = what(row) or str(row.get("error") or "")
    if room < 4:  # too narrow for what it does: the time, the mark and the tool, cut
        return _cut(head, width, failed)
    words = said if len(said) <= room else said[: max(room - 1, 0)] + current().marks.cut
    shown = Content.assemble(head, (f"{words:<{room}}", "$clank-failed" if failed else ""))
    if size:
        shown = Content.assemble(shown, " ", (size.rjust(min(SIZE, len(size))), "$clank-quiet"))
    return _cut(shown, width, failed)


def whole(row: dict[str, Any], found: dict[str, Any] | None, why: str = "", zone: tzinfo | None = None) -> list[str]:
    """A call whole for its window: what the bridge gave (`found`), or what the flow keeps and why (`why`)."""
    tool = str(row.get("tool") or "a call")
    said = [
        f"{tool} · {row.get('status') or '?'} · started {_clock(row.get('started'), zone)} · step {row.get('step')}"
    ]
    if found is None:
        said += [f"Not read whole: {why}", "What the flow keeps of it, cut:", ""]
        said += [f"Its input: {row.get('input') or '(none)'}", "", f"Its output: {row.get('output') or '(none)'}"]
        if row.get("error"):
            said += ["", f"Its error: {row['error']}"]
        return said
    length, cut = found.get("length") or {}, found.get("cut") or {}
    if found.get("title"):
        said.append(f"Its title: {found['title']}")
    given = f"Its input ({int(length.get('input') or 0):,} characters{', its start' if cut.get('input') else ''}):"
    written = f"Its output ({int(length.get('output') or 0):,} characters{', its end' if cut.get('output') else ''}):"
    said += ["", given, str(found.get("input") or "(none)"), "", written, str(found.get("output") or "(none)")]
    if found.get("error"):
        said += ["", "Its error:", str(found["error"])]
    return said


def _clock(started: Any, zone: tzinfo | None) -> str:
    """When a call started, on the owner's clock; "--:--:--" when not known."""
    if not isinstance(started, int | float) or isinstance(started, bool) or started <= 0:
        return "--:--:--"
    return datetime.fromtimestamp(float(started) / 1000, UTC).astimezone(zone).strftime("%H:%M:%S")


def _cut(shown: Content, width: int, failed: bool) -> Content:
    if shown.cell_length <= width:
        return shown
    return Content.assemble(shown.truncate(max(width - 1, 0)), (current().marks.cut, "$clank-failed" if failed else ""))


class CallsList(ListView):
    """The Tool calls panel's content: the calls, newest first; Enter on the page opens the one highlighted."""

    DEFAULT_CSS = """
    CallsList {
        height: auto;
        max-height: 8;  /* ROWS */
    }
    CallsList > ListItem Label {
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.shown: list[dict[str, Any]] = []
        self.zone: tzinfo | None = None

    def show(self, view: dict[str, Any] | None, zone: tzinfo | None = None) -> None:
        """Show these calls (the flow of the session followed), the highlight kept on its call."""
        self.zone = zone
        kept = self.highlighted()
        self.shown = rows(view)
        self._draw(kept["id"] if kept else None)

    def highlighted(self) -> dict[str, Any] | None:
        """The call highlighted, the newest when none is."""
        if not self.shown:
            return None
        index = self.index if self.index is not None and 0 <= self.index < len(self.shown) else 0
        return self.shown[index]

    def on_resize(self, event: events.Resize) -> None:
        """Draw the lines again for the new width (or height: fewer rows may need its scroll bar)."""
        kept = self.highlighted()
        self._draw(kept["id"] if kept else None)

    def _draw(self, keep: str | None) -> None:
        rows = self.size.height or ROWS  # the rows it shows: fewer than `ROWS` when the page is short of them
        scroll = self.styles.scrollbar_size_vertical if len(self.shown) > rows else 0  # its scroll bar's columns
        width = max((self.content_size.width or WIDTH) - scroll, 10)
        refill(self, [line(row, width, self.zone) for row in self.shown], [str(row["id"]) for row in self.shown], keep)
        if self.shown and self.index is None:
            self.index = 0  # the newest highlighted, so ↓ goes to the one before it
        self.display = bool(self.shown)


class CallScreen(DetailsScreen):
    """A call whole over the console, in a scroll: an output may run to the bridge's cap."""

    DEFAULT_CSS = """
    #call-scroll {
        height: auto;
        max-height: 30;
    }
    """

    def compose(self) -> ComposeResult:
        """The lines in a scroll, in a panel titled with the call, and how to close it."""
        scroll = VerticalScroll(*(Label(each, markup=False) for each in self.lines), id="call-scroll")
        hint = Label("Esc closes this; the arrows, Page Up and Page Down scroll it.", classes="hint")
        yield WindowPanel(scroll, hint, title=self.heading, id="details")


def title(row: dict[str, Any]) -> str:
    """A call's window's title: its tool and what it does, briefly."""
    return flat(f"{row.get('tool') or 'a call'} {what(row)}".strip())
