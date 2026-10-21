"""The Flow view's drawings of boxes (design 0013 §12): `BoxChart`, board D1's Flow panel, which shows a flow as
`boxchart.render` lays it out for the panel's width, one box selected; `FlowList`, the flow as a list (board D2's
left); and `CardsView`, board D4's proposals as cards
side by side (`flowboards.cards`), one card highlighted. Both are a `ChartView`: a widget of lines (Textual's line
API) whose layout is a pure function of what it shows and its width.

A `ChartView` keeps each line it laid out (a strip) until that line changes: what it shows read again, a box chosen,
the running box's step and speed (`live`), or the width, lays it out whole (the layout is quick and pure), compares it
line by line with what is shown, and draws again only the lines that differ (design 0001 §5.7, design 0013 §12: "a
running box redraws only its changed rows"); the same again redraws nothing. `laid_out` counts the lines laid out, for
the tests. The lines are laid out a column narrower than the widget (`SCROLL_BAR`), so they never lose their last cell
to the scroll bar when it comes; what is taller than the panel scrolls, the box selected kept in sight. With nothing to
show it says so ("no flow yet").

Keys, while it has the focus: the arrows move to the box drawn nearest in their direction (by rows, then columns); a
key that has nothing to do is left to the console (`SkipAction`), so Left on the first box goes back to the menu. Each
move tells the page (`Chosen`). In the flow, End goes back to the box the flow is at (the one running, or asking you)
and follows it: while following, the selection moves with the flow, until the owner moves it.
"""

from collections.abc import Callable
from datetime import tzinfo
from typing import Any, ClassVar

from textual.actions import SkipAction
from textual.binding import Binding, BindingType
from textual.content import Content
from textual.events import Resize
from textual.geometry import Region, Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.strip import Strip
from textual.visual import Visual

from clank.components.agents.console.boxchart import Chart, Rect, listed, render
from clank.components.agents.console.flowboards import cards

SCROLL_BAR = 1  # the vertical scroll bar's columns, kept free
NO_FLOW = "no flow yet"


class ChartView(ScrollView, can_focus=True):
    """Boxes laid out in lines, one selected, the arrows moving between them."""

    empty = NO_FLOW  # what it says with nothing to show

    class Chosen(Message):
        """The box selected changed."""

        def __init__(self, chart: "ChartView", box: str) -> None:
            super().__init__()
            self.chart = chart
            self.box = box

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("up", "move(0, -1)", "box above", show=False),
        Binding("down", "move(0, 1)", "box below", show=False),
        Binding("left", "move(-1, 0)", "box before", show=False),
        Binding("right", "move(1, 0)", "box after", show=False),
    ]

    DEFAULT_CSS = """
    ChartView {
        height: auto;
        max-height: 30;
        overflow-x: hidden;
        scrollbar-size-vertical: 1;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.view: dict[str, Any] | None = None
        self.selected = ""
        self.chart = Chart(width=1)
        self.laid_out = 0
        self._strips: dict[int, Strip] = {}
        self._width = 0

    def lay_out(self, width: int) -> Chart:
        """What it shows, laid out for the width."""
        raise NotImplementedError

    def on_mount(self) -> None:
        """Draw what it holds."""
        self._draw()

    def on_resize(self, event: Resize) -> None:
        """Lay it out again for the new width."""
        self._draw()

    def notify_style_update(self) -> None:
        """The style changed (another style, or the focus): every line is laid out again in it."""
        super().notify_style_update()
        self._strips.clear()

    def render_line(self, y: int) -> Strip:
        """A line, as laid out when it last changed."""
        row = self.scroll_offset.y + y
        width = self.scrollable_content_region.width
        if row >= len(self.chart.lines):
            return Strip.blank(width, self.visual_style.rich_style)
        strip = self._strips.get(row)
        if strip is None:
            strip = Visual.to_strips(self, self.chart.lines[row], width, 1, self.visual_style, pad=True)[0]
            self._strips[row] = strip
            self.laid_out += 1
        return strip

    def action_move(self, across: int, down: int) -> None:
        """The box drawn nearest in a direction."""
        boxes = self.chart.boxes
        here = boxes.get(self.selected)
        if here is None:
            raise SkipAction()
        found = _nearest(here, {name: rect for name, rect in boxes.items() if name != self.selected}, across, down)
        if found is None:
            raise SkipAction()
        self.moved()
        self.choose(found)
        self._draw()

    def moved(self) -> None:
        """The owner moved the selection (a flow stops following the box at work)."""

    def choose(self, box: str) -> None:
        """Select a box, telling the page."""
        if box != self.selected:
            self.selected = box
            self.post_message(self.Chosen(self, box))

    def _draw(self) -> None:
        """Lay it out for the width, and draw again the lines that changed."""
        width = self.size.width - SCROLL_BAR
        if width <= 0:
            return
        if self.view is None:
            said = ((self.empty, "$clank-quiet"),)
            chart = Chart(width=width, lines=[Content.styled(self.empty, "$clank-quiet")], keys=[said])
        else:
            chart = self.lay_out(width)
        before = self.chart.keys if width == self._width else []
        if width != self._width:
            self._strips.clear()
        changed = [row for row, key in enumerate(chart.keys) if row >= len(before) or before[row] != key]
        for row in [*changed, *range(len(chart.keys), len(before))]:
            self._strips.pop(row, None)
        grown = len(chart.lines) != len(before)
        self.chart, self._width = chart, width
        if grown:
            self.virtual_size = Size(width, len(chart.lines))
            self.refresh(layout=True)
        for row in changed:
            self.refresh_line(row)
        rect = chart.boxes.get(self.selected)
        if rect is not None:
            self.scroll_to_region(Region(rect.x, rect.y, 1, rect.h), animate=False, immediate=True)


class BoxChart(ChartView):
    """A flow's boxes and lines (board D1), one box selected; End back to the box at work."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("end", "now", "back to the box at work", show=False)]

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.live: dict[str, Any] = {}
        self.zone: tzinfo | None = None
        self.key = ""  # the flow shown: another starts afresh, following
        self.now = ""  # the box the flow is at
        self.following = True

    def show(self, view: dict[str, Any] | None, now: str, live: dict[str, Any] | None = None) -> None:
        """Show a flow (None for none), `now` the box it is at, `live` the running box's step and speed."""
        key = str((view or {}).get("flow") or "")
        if key != self.key:
            self.key, self.following, self.selected = key, True, ""
        self.view, self.now, self.live = view, now, dict(live or {})
        if self.following and now and now != self.selected:
            self.choose(now)
        elif not self.selected and view and view.get("boxes"):
            self.choose(now or str(view["boxes"][0]["id"]))
        self._draw()

    def lay_out(self, width: int) -> Chart:
        """The flow, as `boxchart.render` lays it out."""
        return render(self.view, width, self.selected, self.live, self.zone)

    def moved(self) -> None:
        """The owner moved the selection: the flow is no longer followed."""
        self.following = False

    def action_now(self) -> None:
        """Back to the box the flow is at, following it."""
        self.following = True
        if self.now:
            self.choose(self.now)
        self._draw()


class FlowList(ChartView):
    """The flow as a list (board D2's left), one box chosen, the boxes with a change not saved marked."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.zone: tzinfo | None = None
        self.noted: set[str] = set()

    def show(self, view: dict[str, Any] | None, selected: str, noted: set[str]) -> None:
        """Show a flow's boxes as a list, the box `selected` lit, those `noted` marked."""
        self.view, self.noted = view, set(noted)
        self.choose(selected)
        self._draw()

    def lay_out(self, width: int) -> Chart:
        """The list, as `boxchart.listed` lays it out."""
        return listed(self.view, width, self.selected, None, self.zone, self.noted)


class CardsView(ChartView):
    """Board D4's proposals as cards side by side, one highlighted."""

    def __init__(self, *, id: str | None = None, layout: Callable[..., Chart] = cards) -> None:
        super().__init__(id=id)
        self._cards = layout

    def show(self, view: dict[str, Any] | None) -> None:
        """Show the proposals of a flow's view (None for none); the first card highlighted until another is."""
        self.view = view
        ids = [str(each["id"]) for each in ((view or {}).get("proposals") or {}).get("items") or []]
        if self.selected not in ids:
            self.choose(ids[0] if ids else "")
        self._draw()

    def lay_out(self, width: int) -> Chart:
        """The cards, as `flowboards.cards` lays them out."""
        return self._cards(self.view, width, self.selected)


def _nearest(here: Rect, others: dict[str, Rect], across: int, down: int) -> str | None:
    """The box nearest `here` in a direction: those whose middle lies that way, the nearest along it first, then the
    nearest across it."""
    cx, cy = here.x + here.w / 2, here.y + here.h / 2
    found: list[tuple[bool, float, str]] = []
    for name, rect in others.items():
        dx, dy = rect.x + rect.w / 2 - cx, rect.y + rect.h / 2 - cy
        along, aside = (dx * across, abs(dy)) if across else (dy * down, abs(dx))
        if along > 0:
            found.append((aside > (here.h if across else here.w) / 2, along + aside * 2, name))
    return min(found)[2] if found else None
