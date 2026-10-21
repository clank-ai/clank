"""The history page: everything the console holds of what Clank recorded, newest last (design 0001 §4.8).

The console keeps the newest 500 events; `clank events` and the API's history reach further back. `/` shows the
filter and moves into it; it keeps the events whose summary or type holds what is typed. Esc leaves it: a filter in
effect stays in sight, an empty one hides again. New events join at the bottom as they happen.
"""

from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Input, Label

from clank.console.data import ConsoleData
from clank.console.keys import PageKey
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.text import time_of

HINT = Content.assemble(
    ("/", "$clank-key"), (" filters the history by what you type; Esc leaves the filter", "$clank-quiet")
)


class HistoryPage(Page):
    """What happened, newest last."""

    ENTRY = MenuEntry(
        "history",
        "History",
        "Everything Clank recorded, newest last; / filters it by what you type.",
        "design 0001 §4.8",
        key="3",
    )
    PANELS = ("history-filter-panel", "history-events")
    KEYS = (
        PageKey("slash", "filter", "filter by what you type"),
        PageKey("escape", "leave_filter", "leave the filter"),
    )

    def compose(self) -> ComposeResult:
        """The filter, then the events."""
        with Panel(title="Filter", id="history-filter-panel"):
            yield Label(HINT, id="history-filter-hint")
            typing = Input(placeholder="what to look for; Esc leaves the filter", id="history-filter")
            typing.display = False
            yield typing
        with Panel(title="Everything Clank recorded, newest last", id="history-events"):
            yield Label(id="history-lines")

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Draw the events again when the history changed."""
        if changed & {"all", "history"}:
            self._draw_lines(data)

    def press(self, key: str) -> bool:
        """`/` shows the filter and moves into it; Esc leaves it, hiding it when it is empty."""
        typing = self.query_one("#history-filter", Input)
        hint = self.query_one("#history-filter-hint", Label)
        if key == "slash":
            typing.display, hint.display = True, False
            typing.focus()
            return True
        if key == "escape" and typing.has_focus:
            typing.display = bool(typing.value.strip())
            hint.display = not typing.display
            self.console.query_one("#menu").focus()
            return True
        return False

    def explain(self) -> tuple[str, list[str]]:
        """Where the history comes from and how long it is kept."""
        return "History", [
            "Every change Clank makes or sees is recorded as an event (design 0001 §4.8): who did what, through which "
            "client, and when.",
            "The console holds the newest 500; `clank events` and the API's history reach further back, and events "
            "are kept for the days config/service.json says (events_kept_days, 30 unless changed).",
        ]

    def on_input_changed(self, event: Input.Changed) -> None:
        """Filter again as the filter changes."""
        self._draw_lines(self.console.data)

    def _draw_lines(self, data: ConsoleData) -> None:
        typed = self.query_one("#history-filter", Input).value.strip().lower()
        shown = [event for event in data.history if typed in f"{event['summary']} {event['type']}".lower()]
        lines = [f"{time_of(event['time'], self.console.zone)}  {event['summary']}" for event in shown]
        empty = "Nothing matches the filter." if typed else "Nothing recorded yet."
        self.query_one("#history-lines", Label).update("\n".join(lines) or empty)
        self.scroll_end(animate=False)
