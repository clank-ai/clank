"""The window of a part's items, or of what a way of freeing room would drop (design 0012 §4.6, §4.7; §11 step 12):
the items of the Context view's estimate, biggest first, each with its tokens, its step, what it is and its marks, then
what the window says about them (how many more the census did not keep, how they are dropped).

↑↓ highlight one, and `x` drops the one highlighted (design 0012 §4.7: "x drops the highlighted item"): the window
closes with that item, and the Monitor sends it through the Guide's Drop (step 10), the same path as the Session view's
`x`: the Guide is asked about that call first, then its own window asks, and only Enter there clears the result
(`droppable` says, before that, why an item is not a call's result Drop could clear). Enter does nothing here, and `x`
is taken only once the console has done with the message the window was made in (`armed`), so the key that opened
it never acts in it, and the next key, however soon, does; Esc closes it. It is one panel (design 0011 §7), its title in
its border.
"""

from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import Label, ListView

from clank.components.agents.estimate import LABELS
from clank.console.lists import LineItem
from clank.console.panel import WindowPanel

HINT = "↑↓ highlight one; x drops the result highlighted, through the Guide's Drop, which asks first; Esc closes this."


def droppable(row: dict[str, Any] | None) -> str:
    """Why the Guide's Drop cannot clear this item, "" when it is a call's result it may (the Guide says more)."""
    if row is None:
        return "no item is highlighted"
    if row.get("of") != "results":
        part = str(row.get("of") or row.get("part") or "")
        what = "the system prompt" if part == "system" else LABELS.get(part, part)
        return f"it clears a call's result, and this is {what}"
    if row.get("cleared"):
        return "this result is cleared already"
    if not row.get("node"):
        return "the session's flow does not know this call, so the Guide cannot name it"
    return ""


class ItemsScreen(ModalScreen[dict[str, Any] | None]):
    """Items to read, and to drop one of: closed with the item highlighted on `x`, with none on Esc."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("x", "drop", "drop"),
        Binding("escape", "close", "close"),
    ]

    DEFAULT_CSS = """
    ItemsScreen {
        align: center middle;
    }
    #items-list {
        height: auto;
        max-height: 20;
    }
    #items-list > ListItem Label {
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, title: str, rows: list[dict[str, Any]], lines: list[str], notes: list[str]) -> None:
        super().__init__()
        self.heading = title
        self.rows = list(rows)
        self.lines = list(lines)
        self.notes = list(notes)
        self.listed = ListView(*(LineItem(line) for line in self.lines), id="items-list")
        self.armed = False  # until the message it was made in is done: the key that opened it does nothing in it
        self.app.call_next(self._arm)

    def compose(self) -> ComposeResult:
        """The items in a list, what is said of them, and how to drop one, in a panel titled with the title."""
        notes = [Label(note, markup=False) for note in self.notes]
        yield WindowPanel(self.listed, *notes, Label(HINT, classes="hint"), title=self.heading, id="items")

    def on_mount(self) -> None:
        """The biggest highlighted, and the focus in the list."""
        if self.rows:
            self.listed.index = 0
        self.listed.focus()

    def _arm(self) -> None:
        self.armed = True

    def action_drop(self) -> None:
        """`x`: close with the item highlighted, for the Guide's Drop, unless it is the key that opened the window."""
        index = self.listed.index
        if self.armed and index is not None and 0 <= index < len(self.rows):
            self.dismiss(self.rows[index])

    def action_close(self) -> None:
        """Esc: close with none."""
        self.dismiss(None)
