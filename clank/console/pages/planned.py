"""A planned page: what a later milestone brings, in red until it is built (the owner's request, 2026-10-11).

It says which milestone builds it, what it will do and where it is designed, so the menu shows the whole of Clank as
it will be: one panel, its name and milestone as its title (design 0011 §8). Its red is the style's `planned`, from the
style sheet (`.planned`) and its title's color, like every color.
"""

from textual.app import ComposeResult
from textual.widgets import Label

from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel


class PlannedPage(Page):
    """The page of a planned menu entry."""

    PANELS = ("planned",)

    def __init__(self, entry: MenuEntry) -> None:
        super().__init__(id=f"page-{entry.id}", classes="planned")
        self.entry = entry

    def explain(self) -> tuple[str, list[str]]:
        """Its milestone, what it will do, and where it is designed."""
        return self.entry.explanation()

    def compose(self) -> ComposeResult:
        """Its milestone, what it will do, and where it is designed."""
        title = f"{self.entry.label} · coming in {self.entry.milestone}"
        with Panel(title=title, id="planned", title_color="$clank-planned"):
            yield Label(self.entry.summary, classes="summary")
            yield Label(f"Designed in {self.entry.designed_in}; docs/ROADMAP.md says where each milestone stands.")
