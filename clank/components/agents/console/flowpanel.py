"""The Flow panel's drawing (design 0012 §6.5, §2): `FlowChart`, a widget of lines (Textual's line API) that shows a
session's flow as `flowchart.render` lays it out for the panel's width, with a cursor on one node.

It keeps each line it laid out (a strip) until that line changes: a new flow, or a cursor moved, is laid out whole by
`render`, once (the cursor on now while following it), compared line by line with what is shown, and only the lines
that differ are laid out again and redrawn (design 0001 §5.7, design 0012 §2: "only the rows that changed laid out
again"); the same flow again redraws nothing.
`laid_out` counts the lines laid out, for the tests.

Keys, while it has the focus: ↑ and ↓ move from node to node in reading order (a node, then its children; a branch's
work in time order); ← folds the node under the cursor, or on a node that does not fold goes to its parent; → opens a
folded node, or on an open one goes to its first child; End goes back to now (the newest node, or the fold that hides
it) and follows it: while following, the cursor moves with now as the flow grows, until the owner moves it. A key that
has nothing to do is left to the console (`SkipAction`), so ← on the root goes back to the menu and ↑ on the first node
scrolls the page. The owner's folds and the cursor belong to the session shown (`key`): another session starts afresh.
Enter shows the node under the cursor whole (`details`): its words, its state, what an inference about it rests on, and
the facts the flow keeps of it. With no flow it says what it waits for ("no session yet"). The lines are laid out a
column narrower than the widget (`SCROLL_BAR`), so they never lose their last cell to the scroll bar when it comes.
"""

from datetime import tzinfo
from typing import Any, ClassVar

from textual.actions import SkipAction
from textual.binding import Binding, BindingType
from textual.content import Content
from textual.events import Resize
from textual.geometry import Region, Size
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.visual import Visual

from clank.components.agents.console.flowchart import Drawn, render
from clank.components.agents.console.flowtree import Node, chars
from clank.console.details import DetailsScreen

NO_SESSION = "no session yet"
TITLES = {
    "root": "Your session", "branch": "A branch", "other": "Steps in no branch", "call": "A call",
    "together": "Calls made at once", "run": "A run of one tool", "tries": "Tries of one call",
    "subagent": "A subagent", "note": "Your note", "said": "Your message", "step": "A step", "end": "How a step ended",
    "undone": "Steps undone", "band": "A compaction",
}  # fmt: skip
SCROLL_BAR = 1  # the vertical scroll bar's columns, kept free


class FlowChart(ScrollView, can_focus=True):
    """A session's flow, its cursor and its folds."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "step(-1)", "previous node", show=False),
        Binding("down", "step(1)", "next node", show=False),
        Binding("left", "fold", "fold", show=False),
        Binding("right", "unfold", "open", show=False),
        Binding("end", "now", "back to now", show=False),
        Binding("enter", "details", "its details", show=False),
    ]

    DEFAULT_CSS = """
    FlowChart {
        height: auto;
        max-height: 24;
        overflow-x: hidden;
        scrollbar-size-vertical: 1;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.view: dict[str, Any] | None = None
        self.subagents: dict[str, dict[str, Any]] = {}
        self.key = ""  # the session shown
        self.empty = NO_SESSION
        self.folds: dict[str, bool] = {}  # the owner's, by node
        self.cursor = ""
        self.following = True
        self.zone: tzinfo | None = None  # the console's, for the times it shows (a hold's)
        self.drawn = Drawn()
        self.laid_out = 0
        self._strips: dict[int, Strip] = {}
        self._width = 0

    def show(
        self,
        view: dict[str, Any] | None,
        subagents: dict[str, dict[str, Any]] | None = None,
        *,
        key: str = "",
        empty: str = NO_SESSION,
    ) -> None:
        """Show a flow (None for none, saying `empty`); another session's (`key`) starts unfolded, following now."""
        if key != self.key:
            self.key, self.folds, self.cursor, self.following = key, {}, "", True
        self.view, self.subagents, self.empty = view, dict(subagents or {}), empty
        self._draw()

    def on_mount(self) -> None:
        """Say what it waits for until a flow comes."""
        self._draw()

    def on_resize(self, event: Resize) -> None:
        """Lay the flow out again for the new width."""
        self._draw()

    def notify_style_update(self) -> None:
        """The style changed (another style, or the focus): every line is laid out again in it."""
        super().notify_style_update()
        self._strips.clear()

    def render_line(self, y: int) -> Strip:
        """A line of the flow, as laid out when it last changed."""
        row = self.scroll_offset.y + y
        width = self.scrollable_content_region.width
        if row >= len(self.drawn.lines):
            return Strip.blank(width, self.visual_style.rich_style)
        strip = self._strips.get(row)
        if strip is None:
            strip = Visual.to_strips(self, self.drawn.lines[row], width, 1, self.visual_style, pad=True)[0]
            self._strips[row] = strip
            self.laid_out += 1
        return strip

    def action_step(self, by: int) -> None:
        """The previous or the next node in reading order."""
        order = self.drawn.order
        index = order.index(self.cursor) if self.cursor in order else len(order) - 1
        target = min(max(index + by, 0), len(order) - 1)
        if not order or target == index:
            raise SkipAction()
        self.cursor, self.following = order[target], False
        self._draw()

    def action_fold(self) -> None:
        """Fold the node under the cursor, or go to its parent."""
        node = self.drawn.nodes.get(self.cursor)
        if node is None:
            raise SkipAction()
        if node.folds and not node.folded:
            self.folds[node.id] = True
        elif self.drawn.parent.get(node.id):
            self.cursor = self.drawn.shown(self.drawn.parent[node.id])
        else:
            raise SkipAction()
        self.following = False
        self._draw()

    def action_unfold(self) -> None:
        """Open the node under the cursor, or go to its first child."""
        node = self.drawn.nodes.get(self.cursor)
        if node is None:
            raise SkipAction()
        if node.folds and node.folded:
            self.folds[node.id] = False
        elif node.children and not node.folded and node.children[0].id in self.drawn.row:
            self.cursor = node.children[0].id
        else:
            raise SkipAction()
        self.following = False
        self._draw()

    def action_now(self) -> None:
        """Back to now, following it."""
        self.following = True
        self._draw()

    def action_details(self) -> None:
        """The node under the cursor, whole, and what an inference about it rests on."""
        node = self.drawn.nodes.get(self.cursor)
        if node is None or self.view is None:
            raise SkipAction()
        flows = {str(each["id"]): each for view in (self.view, *self.subagents.values())
                 for each in view.get("nodes") or []}  # fmt: skip
        self.app.push_screen(DetailsScreen(*details(node, flows)))

    def _draw(self) -> None:
        """Lay the flow out for the width, the cursor on now while following, and draw again the lines that changed."""
        width = self.size.width - SCROLL_BAR
        if width <= 0:
            return
        if self.view is None:
            drawn = Drawn(lines=[Content(self.empty).stylize("$clank-quiet")], keys=[((self.empty, "quiet"),)])
        else:
            following = self.following or not self.cursor
            drawn = render(self.view, width, self.cursor, self.folds, self.subagents, follow=following,
                           zone=self.zone)  # fmt: skip
            self.cursor = drawn.cursor
        before = self.drawn.keys if width == self._width else []
        if width != self._width:
            self._strips.clear()
        changed = [row for row, key in enumerate(drawn.keys) if row >= len(before) or before[row] != key]
        for row in [*changed, *range(len(drawn.keys), len(before))]:
            self._strips.pop(row, None)
        grown = len(drawn.lines) != len(before)
        self.drawn, self._width = drawn, width
        if grown:
            self.virtual_size = Size(width, len(drawn.lines))
            self.refresh(layout=True)
        for row in changed:
            self.refresh_line(row)
        row = drawn.row.get(self.cursor)
        if row is not None:
            self.scroll_to_region(Region(0, row, 1, 1), animate=False, immediate=True)


def details(node: Node, flows: dict[str, dict[str, Any]]) -> tuple[str, list[str]]:
    """A node's details: its kind, its words whole, its state, what an inference about it rests on, and the facts the
    flow keeps of it (a call's input and result, a step's request and how it was paired, what a group holds)."""
    title = TITLES.get(node.kind, "A node")
    if node.end:
        title += ": a dead end"
    elif node.kind == "step" and node.mark and node.tone == "$clank-now":
        title = "The step working now"
    lines = [node.words]
    if node.detail:
        lines.append(node.detail)
    if node.why:
        lines.append(f"Why: {node.why}")
    fact = flows.get(node.id.rsplit("/", 1)[-1].removesuffix(":end"), {})
    if node.kind in ("call", "subagent") and fact:
        call = flows.get(str(fact.get("call") or ""), fact) if node.kind == "subagent" else fact
        lines.append(f"Its tool: {call.get('tool')} · {call.get('status') or 'no state yet'}"
                     + (f" · exit status {call['exit']}" if isinstance(call.get("exit"), int) else ""))  # fmt: skip
        if call.get("input"):
            lines.append(f"Its input: {call['input']}")
        if call.get("output"):
            size = f" ({chars(int(call['length']))})" if isinstance(call.get("length"), int) else ""
            lines.append(f"What it gave back{size}: {call['output']}")
        if call.get("error"):
            lines.append(f"Its error: {call['error']}")
    if node.kind in ("step", "end") and fact:
        lines.append(f"Step {fact.get('n')} · {fact.get('agent') or 'its agent'} · ended: {fact.get('ended')}"
                     + (" · not in the context" if fact.get("context") == "left" else ""))  # fmt: skip
        request = fact.get("request") or {}
        if request.get("flying"):
            lines.append(f"Its request at the gateway: {request.get('phase')}, about {request.get('tokens') or 0:,} "
                         "tokens")  # fmt: skip
        elif request:
            lines.append(f"Its request at the gateway: {request.get('seconds')} s, {request.get('per_second')} "
                         f"tokens a second, a prompt of {request.get('prompt_tokens')} tokens")  # fmt: skip
        if request:
            lines.append(f"Paired with it: {request.get('why')}")
        elif fact.get("before"):
            lines.append("Done before Clank watched: no request of the gateway's is paired with it")
    if node.kind in ("together", "run", "tries", "undone", "band", "branch", "other") and node.children:
        lines.append("It holds: " + "; ".join(child.words for child in node.children))
    return title, lines
