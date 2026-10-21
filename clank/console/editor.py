"""A text to edit, over the console: a box's prompt, what it is accepted when (design 0013 §12, boards D2 and D4). The
text in an editor of several lines (Textual's own `TextArea`); Ctrl+S gives it back to the page that asked, Esc gives
nothing. The page checks the text and acts on it; the window only edits it. It is one panel (design 0011 §7), its
title in its border, a note under the text saying what happens with it.
"""

from typing import ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import Label, TextArea

from clank.console.panel import WindowPanel


class EditScreen(ModalScreen[str | None]):
    """A title, a text to edit, and a note."""

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("escape", "cancel", "close"),
        Binding("ctrl+s", "submit", "done"),
    ]

    DEFAULT_CSS = """
    EditScreen #edit-text {
        height: 12;
        border: none;
        padding: 0;
    }
    """

    def __init__(self, title: str, text: str, note: str = "") -> None:
        super().__init__()
        self.heading = title
        self.text = text
        self.note = note

    def compose(self) -> ComposeResult:
        """The text in a panel titled with the title, and the note."""
        note = Label(self.note or "Ctrl+S is done; Esc closes this, changing nothing.", classes="hint")
        yield WindowPanel(TextArea(self.text, id="edit-text", soft_wrap=True), note, title=self.heading, id="edit")

    def on_mount(self) -> None:
        """The text has the focus."""
        self.query_one("#edit-text", TextArea).focus()

    def action_submit(self) -> None:
        """Give the text back."""
        self.dismiss(self.query_one("#edit-text", TextArea).text)

    def action_cancel(self) -> None:
        """Esc: nothing."""
        self.dismiss(None)
