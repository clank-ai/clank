"""Rows of a name and its value, for the pages that must read well at any width (the owner uses the console in narrow
windows too): the names in a column of their own, each value beside its name and wrapping under itself, never back
under the name; when the values' column would be narrower than `VALUE_AT_LEAST`, each name stands above its value
instead. A value may hold several lines
(an option's value, what the engine receives, what it does).

`show` changes only what changed, as `lists.refill` does: the same rows again change nothing, a changed row is updated
in place, and the rows are made again only when their number changed, so a page that reads again every few seconds does
not flicker.
"""

from collections.abc import Sequence

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.events import Resize
from textual.widgets import Label

from clank.console.lists import Line, relabel

VALUE_AT_LEAST = 36  # columns: a narrower values' column stacks each name above its value


class Row(Horizontal):
    """A name and its value."""

    def __init__(self, name: Line, value: Line) -> None:
        super().__init__(classes="row")
        self.shown = (name, value)

    def compose(self) -> ComposeResult:
        """The name, then the value."""
        yield Label(self.shown[0], classes="name")
        yield Label(self.shown[1], classes="value")

    def update(self, name: Line, value: Line) -> None:
        """Show another name and value, changing only what changed (kept for its labels when not made yet)."""
        self.shown = (name, value)
        labels = list(self.query(Label).results(Label))
        if len(labels) == 2:
            relabel(labels[0], name)
            relabel(labels[1], value)


class Rows(Vertical):
    """Rows of a name and its value; the names' column as wide as `width`."""

    DEFAULT_CSS = """
    Rows { height: auto; }
    Rows > .row { height: auto; width: 1fr; margin-bottom: 0; }
    Rows .name { color: $clank-quiet; }
    Rows .value { width: 1fr; }
    Rows.-stacked > .row { layout: vertical; }
    Rows.-stacked .name { width: 1fr; }
    Rows.-gapped > .row { margin-bottom: 1; }
    """

    def __init__(self, width: int = 24, *, gapped: bool = False, id: str | None = None) -> None:
        super().__init__(id=id, classes="-gapped" if gapped else "")
        self.width = width

    def show(self, rows: Sequence[tuple[Line, Line]]) -> None:
        """Show these rows, changing only what changed."""
        found = list(self.query_children(Row))
        if len(found) == len(rows):
            for row, (name, value) in zip(found, rows, strict=True):
                row.update(name, value)
            return
        self.remove_children()
        self.mount_all([Row(name, value) for name, value in rows])
        self.call_after_refresh(self._fit)

    def on_resize(self, event: Resize) -> None:
        """Stack each name above its value when the page is narrow."""
        self.set_class(event.size.width - self.width < VALUE_AT_LEAST, "-stacked")
        self._fit()

    def on_mount(self) -> None:
        """The names' column as wide as asked."""
        self._fit()

    def _fit(self) -> None:
        """Each name as wide as the column, or the whole width when stacked."""
        stacked = self.has_class("-stacked")
        for name in self.query(".name"):
            name.styles.width = "1fr" if stacked else self.width
