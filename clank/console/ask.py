"""A question of the service's over the console, answered in a window with its options' keys (design 0002 §2.5;
design 0016 §9, decision 0112: the workspace's question before its agent starts). It shows the question's title in its
border, its detail as written, and each option with its key and what it does; an option's key gives that option to the
page that asked, Esc gives nothing (the question stays waiting, answered elsewhere or by its default in time). The page
sends the answer; the window only asks. It is one panel (design 0011 §7).

Like the confirmation window, it never takes the key that opened it (`armed`), and its lines are never read as markup.
"""

from typing import Any, ClassVar

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import Label

from clank.console.panel import WindowPanel


class AskScreen(ModalScreen[str | None]):
    """A question and its options, until one of their keys or Esc."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "leave", "leave it")]

    def __init__(self, question: dict[str, Any]) -> None:
        super().__init__()
        self.question = question
        self.armed = False
        self.app.call_next(self._arm)

    def compose(self) -> ComposeResult:
        """The detail, then each option with its key, in a panel titled with the question."""
        lines = [Label(self.question.get("detail") or "", markup=False)] if self.question.get("detail") else []
        for option in self.question["options"]:
            effect = f": {option['effect']}" if option.get("effect") else ""
            lines.append(Label(f"{option['key'] or option['id']}  {option['label']}{effect}", markup=False))
        keys = " or ".join(option["key"] for option in self.question["options"] if option["key"])
        hint = Label(f"{keys} answers; Esc leaves it waiting." if keys else "Esc leaves it waiting.", classes="hint")
        yield WindowPanel(*lines, hint, title=self.question["title"], id="ask")

    def _arm(self) -> None:
        self.armed = True

    def on_key(self, event: events.Key) -> None:
        """An option's key: that option."""
        chosen = next((option for option in self.question["options"] if option["key"] and option["key"] == event.key),
                      None)  # fmt: skip
        if chosen is not None and self.armed:
            event.stop()
            self.dismiss(chosen["id"])

    def action_leave(self) -> None:
        """Esc: no answer."""
        self.dismiss(None)
