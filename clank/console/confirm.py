"""A window that asks before an action is taken (design 0012 §9.1: "a confirmation, Enter, or Esc to leave it"): a
title, then lines saying what the action will do, the exact call it makes and what it costs. Enter does it, Esc leaves
it; the page that asked is told which (True or False). It is one panel (design 0011 §7), its title in its border.

It never takes the key that opened it: a page that opens it on a key (Enter on a row that asks first) would otherwise
see that same Enter taken as "do it", since Textual reads the new window's bindings for the key that pushed it. So it is
`armed` only once the console has done with the message it was made in; the next key, however soon, it takes.

Its lines are shown as written, never read as the console's markup, since they hold calls (`{"auto": true}`) where
square brackets are common (decision 0045)."""

from collections.abc import Sequence
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import Label

from clank.console.panel import WindowPanel


class ConfirmScreen(ModalScreen[bool]):
    """A title and its lines, over the console, until Enter or Esc."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "confirm", "do it"),
        Binding("escape", "leave", "leave it"),
    ]

    def __init__(self, title: str, lines: Sequence[str]) -> None:
        super().__init__()
        self.heading = title
        self.lines = list(lines)
        self.armed = False  # until the message it was made in is done: the key that opened it does nothing in it
        self.app.call_next(self._arm)

    def compose(self) -> ComposeResult:
        """The lines in a panel titled with the title, and what Enter and Esc do."""
        lines = [Label(line, markup=False) for line in self.lines]
        yield WindowPanel(*lines, Label("Enter does it; Esc leaves it.", classes="hint"), title=self.heading,
                          id="confirm")  # fmt: skip

    def _arm(self) -> None:
        self.armed = True

    def action_confirm(self) -> None:
        """Enter: do it, unless it is the key that opened the window."""
        if self.armed:
            self.dismiss(True)

    def action_leave(self) -> None:
        """Esc: leave it."""
        self.dismiss(False)
