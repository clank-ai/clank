"""A window over the console with the whole of something: a question's detail and options (`v`), the explanation of
what has the focus (`?`), a check's findings, a node of the Monitor's flow (Enter). It is one panel (design 0011 §7),
its title in its border; Esc closes it.

Its lines are shown as written, never read as the console's markup: they hold what others wrote (a command, a file, a
question's text), where square brackets are common (`list[str]`, `s/[/]/_/g`), and the whole of a thing must be one
key away, unchanged (decision 0045). The title is shown as written too (`WindowPanel`)."""

from collections.abc import Sequence
from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import Label

from clank.console.panel import WindowPanel


class DetailsScreen(ModalScreen[None]):
    """A title and its lines, over the console."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "dismiss", "close"),
        Binding("v", "dismiss", "close", show=False),
    ]

    def __init__(self, title: str, lines: Sequence[str]) -> None:
        super().__init__()
        self.heading = title
        self.lines = list(lines)

    def compose(self) -> ComposeResult:
        """The lines in a panel titled with the title, and how to close it."""
        lines = [Label(line, markup=False) for line in self.lines]
        yield WindowPanel(*lines, Label("Esc closes this.", classes="hint"), title=self.heading, id="details")
