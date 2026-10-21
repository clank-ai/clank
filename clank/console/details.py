"""A window over the console with the whole of something: a question's detail and options (`v`), the explanation of
what has the focus (`?`), a check's findings, a node of the Monitor's flow (Enter). It is one panel (design 0011 §7),
its title in its border; Esc closes it, and so does its last line, a button (`esc close`, design 0011 §12.1), which has
the focus when it opens.

Its lines are shown as written, never read as the console's markup: they hold what others wrote (a command, a file, a
question's text), where square brackets are common (`list[str]`, `s/[/]/_/g`), and the whole of a thing must be one
key away, unchanged (decision 0045). The title is shown as written too (`WindowPanel`)."""

from collections.abc import Sequence
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import Label

from clank.console.buttons import Button, Buttons
from clank.console.keys import PageKey
from clank.console.panel import WindowPanel


class DetailsScreen(ModalScreen[None]):
    """A title and its lines, over the console."""

    CLOSE = PageKey("escape", "close", "close")
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding(CLOSE.key, CLOSE.action, CLOSE.words),
        Binding("v", CLOSE.action, CLOSE.words, show=False),
    ]

    def __init__(self, title: str, lines: Sequence[str]) -> None:
        super().__init__()
        self.heading = title
        self.lines = list(lines)

    def compose(self) -> ComposeResult:
        """The lines in a panel titled with the title, and its key to close it, a button."""
        lines = [Label(line, markup=False) for line in self.lines]
        keys = Buttons([Button(self.CLOSE)], press=lambda _: self.action_close(), classes="hint", id="details-keys")
        yield WindowPanel(*lines, keys, title=self.heading, id="details")

    def action_close(self) -> None:
        """Esc, `v` or its button: close it."""
        self.dismiss()
