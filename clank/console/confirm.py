"""A window that asks before an action is taken (design 0012 §9.1: "a confirmation, Enter, or Esc to leave it"): a
title, then lines saying what the action will do, the exact call it makes and what it costs. Enter does it, Esc leaves
it; the page that asked is told which (True or False). It is one panel (design 0011 §7), its title in its border.

It never takes the key that opened it: a page that opens it on a key (Enter on a row that asks first) would otherwise
see that same Enter taken as "do it", since Textual reads the new window's bindings for the key that pushed it. So it is
`armed` only once the console has done with the message it was made in; the next key, however soon, it takes.

Its keys are its last line, a group of buttons (design 0011 §12.1 and §12.5): `enter do it` and `esc leave it`, the
focus on "do it" when it opens, so Enter keeps its meaning; → or Tab reach "leave it"; a button pressed runs its key's
action, guarded the same way.

Its lines are shown as written, never read as the console's markup, since they hold calls (`{"auto": true}`) where
square brackets are common (decision 0045)."""

from collections.abc import Sequence
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import Label

from clank.console.buttons import Button, Buttons
from clank.console.keys import PageKey
from clank.console.panel import WindowPanel


class ConfirmScreen(ModalScreen[bool]):
    """A title and its lines, over the console, until Enter or Esc."""

    KEYS = (PageKey("enter", "confirm", "do it"), PageKey("escape", "leave", "leave it"))
    BINDINGS: ClassVar[list[BindingType]] = [Binding(key.key, key.action, key.words) for key in KEYS]

    def __init__(self, title: str, lines: Sequence[str]) -> None:
        super().__init__()
        self.heading = title
        self.lines = list(lines)
        self.armed = False  # until the message it was made in is done: the key that opened it does nothing in it
        self.app.call_next(self._arm)

    def compose(self) -> ComposeResult:
        """The lines in a panel titled with the title, and what Enter and Esc do."""
        lines = [Label(line, markup=False) for line in self.lines]
        keys = Buttons([Button(key) for key in self.KEYS], press=self.pressed, classes="hint", id="confirm-keys")
        yield WindowPanel(*lines, keys, title=self.heading, id="confirm")

    def pressed(self, button: Button) -> None:
        """A button of the window, pressed: its key's action, as the key does (`armed` keeps its guard)."""
        getattr(self, f"action_{button.key.action}")()

    def _arm(self) -> None:
        self.armed = True

    def action_confirm(self) -> None:
        """Enter: do it, unless it is the key that opened the window."""
        if self.armed:
            self.dismiss(True)

    def action_leave(self) -> None:
        """Esc: leave it."""
        self.dismiss(False)
