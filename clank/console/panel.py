"""The panel (design 0011 §4; design 0001 §5.6: the screens are made of panels): every section of every page, the
machine column's parts and the windows are each a `Panel`, a box with its title set in its top border.

The title stands at the left of the top border, in the style's `title` color (or another element, such as a planned
page's `planned`) and weight, its key letter after it in `quiet` when the page gives one; a page may change it (a count
in it, "Waiting for your answer · 3"). A note stands at the right of the same border, in `quiet`: Textual sets one label
in a border, so the label is the title, a run of the border's own line, and the note, drawn again for the panel's width
when it changes; the run carries no color of its own and the border's title color follows the border, so the run is the
border wherever the focus is. The note goes first when the panel is narrow, and the panel is never narrower than its
title, so the title is never cut. When the style centers or right-aligns titles, the note stands in the bottom border.
The panel that holds the focus draws its border in `border-focused`, by Textual's `:focus-within`, so a border changes
only when the focus moves and the console redraws nothing for it (design 0001 §5.7).

A `PanelRow` sets panels side by side as a grid row: each takes the row's height, so their borders line up, and the
row stacks them in reading order when it is narrower than `stack_below` columns; a page may set `stack_below` anew when
what a panel holds asks for more room, or less (a question waiting, design 0011 §9), and the row stacks or stands side
by side again at once. What a panel in a row holds must have its own height (a list's `height: auto`), or the row cannot
measure it. A `PanelGrid` is a row of columns of set widths
(`"2fr 3fr"`), a panel in it as tall as several rows beside it (the Monitor's Flow beside Now, Watch for and the Guide,
design 0012 §2); two grids of the same columns line their borders up; narrow, it stacks its panels in the order given,
so a page gives them in the order they read when stacked. A spanning panel is as tall as the rows it spans, which the
panels beside it set: what it holds beyond them is clipped.

A `WindowPanel` is a window's (design 0011 §7: the details window, the picker, the form, an MCP server's tools): its
border is always `border-focused`, since the window has the focus, and it is never wider than the screen allows, so a
title too long for it is cut in the border with "…" and shown whole as its first line (decision 0081: the one
exception to a panel's least width).

The border's kind, the padding and the room between panels are the style's (`$clank-border-kind`,
`$clank-panel-padding`, `$clank-rows-between`, `$clank-columns-between`, `$clank-title-align`).
"""

from collections.abc import Mapping

from textual import events
from textual.containers import Grid, Vertical
from textual.content import Content
from textual.dom import DOMNode
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Label

from clank.console.style import current

CORNERS = 6  # a title's corners, the run of line beside each, and the space each side: ┌─ title ─┐


class Panel(Vertical):
    """A section of a page: its title in its top border, its content inside."""

    class Resized(Message):
        """A panel's size changed (its page's scroll bar came or went too): a page that wraps text for the panel's
        width draws it again."""

        def __init__(self, panel: "Panel") -> None:
            super().__init__()
            self.panel = panel

    DEFAULT_CSS = """
    Panel {
        height: auto;
        border: $clank-border-kind $clank-border;
        border-title-color: $clank-border;
        border-subtitle-color: $clank-quiet;
        border-title-align: $clank-title-align;
        border-subtitle-align: right;
        padding: 0 $clank-panel-padding;
        margin: 0 0 $clank-rows-between 0;
    }
    Panel:focus-within {
        border: $clank-border-kind $clank-border-focused;
        border-title-color: $clank-border-focused;
    }
    """

    def __init__(
        self,
        *children: Widget,
        title: str,
        id: str,
        key: str = "",
        note: str = "",
        classes: str = "",
        title_color: str = "$clank-title",
    ) -> None:
        super().__init__(*children, id=id, classes=classes)
        self._title = title
        self.key = key
        self._note = note
        self.title_color = title_color
        self._fit()

    @property
    def title(self) -> str:
        """What the panel's top border says at its left ("What runs")."""
        return self._title

    @title.setter
    def title(self, title: str) -> None:
        if title != self._title:
            self._title = title
            self._fit()

    @property
    def note(self) -> str:
        """What the panel's top border says at its right ("100 newest requests")."""
        return self._note

    @note.setter
    def note(self, note: str) -> None:
        if note != self._note:
            self._note = note
            self._label(self.outer_size.width)

    def _fit(self) -> None:
        """Never narrower than the title; the title and the note drawn again for the panel's width."""
        self.styles.min_width = self._head().cell_length + CORNERS
        self._label(self.outer_size.width)

    def on_resize(self, event: events.Resize) -> None:
        """Draw the title and the note for the panel's new width, and say the size changed."""
        self._label(self.outer_size.width)
        self.post_message(self.Resized(self))

    def enter(self) -> None:
        """Move the focus into the panel: to the first thing in it that takes the focus and is shown (a panel's label
        that says it is empty is hidden once its list has rows)."""
        for widget in self.query("*"):
            if widget.focusable and self._shown(widget):
                widget.focus()
                return

    def _shown(self, widget: Widget) -> bool:
        """Whether a widget of the panel is shown: neither it nor a container of it inside the panel is hidden."""
        node: DOMNode | None = widget
        while node is not None and node is not self:
            if not node.display:
                return False
            node = node.parent
        return True

    def _head(self) -> Content:
        style = current()
        weight = "bold " if style.titles.style == "bold" else ""
        key = (" ", (self.key, "$clank-quiet")) if self.key else ()
        return Content.assemble((self._title, f"{weight}{self.title_color}"), *key)

    def _label(self, width: int) -> None:
        head = self._head()
        if current().titles.align != "left":
            self.border_title = head
            self.border_subtitle = self._note or None
            return
        run = width - CORNERS - head.cell_length - len(self._note) - 2  # a space each side of the run
        if self._note and run >= 1:
            self.border_title = Content.assemble(head, " " + "─" * run + " ", (self._note, "$clank-quiet"))
        else:
            self.border_title = head
        self.border_subtitle = None


class WindowPanel(Panel):
    """A window's panel, over the console (design 0011 §7): its title in its top border, its border in
    `border-focused`, since the window has the focus, on the page's `background`. A window is never wider than the
    screen allows (90%): a title too long for it is cut in the border with "…" and shown whole as its first line."""

    DEFAULT_CSS = """
    WindowPanel {
        width: 90;
        max-width: 90%;
        max-height: 80%;
        margin: 0;
        background: $clank-background;
        border: $clank-border-kind $clank-border-focused;
        border-title-color: $clank-border-focused;
    }
    WindowPanel Label {
        width: 1fr;
    }
    WindowPanel > .window-title {
        text-style: bold;
        display: none;
    }
    WindowPanel > .window-title.-cut {
        display: block;
    }
    """

    def __init__(self, *children: Widget, title: str, id: str, classes: str = "") -> None:
        self._whole = Label(title, classes="window-title", markup=False)  # shown when the border cuts the title
        super().__init__(self._whole, *children, title=title, id=id, classes=classes)

    def _fit(self) -> None:
        """No least width: the title is cut, and shown whole inside, rather than the window wider than the screen."""
        if self.is_mounted:
            self._whole.update(self.title)
        self._label(self.outer_size.width)

    def _label(self, width: int) -> None:
        super()._label(width)
        self._whole.set_class(width > 0 and self._head().cell_length + CORNERS > width, "-cut")


class PanelRow(Grid):
    """Panels side by side, each the row's height; stacked in reading order when the row is narrower than
    `stack_below` columns."""

    DEFAULT_CSS = """
    PanelRow {
        height: auto;
        grid-rows: auto;
        grid-gutter: 0 $clank-columns-between;
        margin: 0 0 $clank-rows-between 0;
    }
    PanelRow > Panel {
        height: 100%;
        margin: 0;
    }
    PanelRow.-stacked {
        grid-gutter: $clank-rows-between 0;
    }
    """

    def __init__(self, *panels: Panel, stack_below: int, id: str | None = None) -> None:
        super().__init__(*panels, id=id)
        self._stack_below = stack_below
        self.styles.grid_size_columns = len(panels)

    @property
    def stack_below(self) -> int:
        """The row's least width for its panels side by side, in columns."""
        return self._stack_below

    @stack_below.setter
    def stack_below(self, columns: int) -> None:
        """What a panel holds may ask for more room, or less (a question waiting, design 0011 §9): the row stacks, or
        sets its panels side by side again, at once for its width now."""
        self._stack_below = columns
        if self.size.width:
            self._stack(self.size.width)

    def on_resize(self, event: events.Resize) -> None:
        """Stack the panels when the row is too narrow for them side by side, and set them side by side again."""
        self._stack(event.size.width)

    def _stack(self, width: int) -> None:
        stacked = width < self._stack_below
        if stacked != self.has_class("-stacked"):
            self.set_class(stacked, "-stacked")
            self._arrange(stacked)

    def _arrange(self, stacked: bool) -> None:
        self.styles.grid_size_columns = 1 if stacked else len(self.children)


class PanelGrid(PanelRow):
    """Panels in columns of set widths, each panel named in `spans` as tall as that many rows; one column, in the order
    given, when the grid is narrower than `stack_below` columns."""

    DEFAULT_CSS = """
    PanelGrid {
        grid-gutter: $clank-rows-between $clank-columns-between;
    }
    """

    def __init__(
        self,
        *panels: Panel,
        columns: str,
        stack_below: int,
        spans: Mapping[str, int] | None = None,
        id: str | None = None,
        classes: str = "",
    ) -> None:
        super().__init__(*panels, stack_below=stack_below, id=id)
        self.set_classes(classes)
        self.columns = columns
        self.spans = dict(spans or {})
        self._panels = panels  # not yet its children, which are mounted later
        self._arrange(stacked=False)

    def _arrange(self, stacked: bool) -> None:
        widths = self.columns.split()
        self.styles.grid_size_columns = 1 if stacked else len(widths)
        self.styles.grid_columns = "1fr" if stacked else self.columns
        for panel in self._panels:
            panel.styles.row_span = 1 if stacked else self.spans.get(panel.id or "", 1)
