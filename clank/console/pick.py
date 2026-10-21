"""A list to choose one thing from, over the console: a preset to load, an engine to install (design 0001 §5.1). Each
choice has its label and a line on it (a preset's fit, or why it cannot run); Enter takes the highlighted one, Esc
takes none. The page that asked acts on the choice; the picker only chooses. It is one panel (design 0011 §7), its
title in its border. `preset_choices` is the list every page that picks a preset shows: a cloud preset says its
provider (`cloud openrouter`) and its prices per million tokens (design 0016 §15)."""

from dataclasses import dataclass
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.screen import ModalScreen
from textual.widgets import Label, ListItem, ListView

from clank.console.panel import WindowPanel
from clank.money import money


@dataclass(frozen=True)
class Choice:
    """One thing to choose: what the page gets back, what the list shows, and a line on it."""

    value: str
    label: str
    detail: str = ""


def preset_setup(preset: dict[str, Any]) -> str:
    """What a preset runs: its serving setup and model; a cloud preset's provider, its prices (before the model's long
    id, so a line cut short keeps them) and its model."""
    if not preset.get("endpoint"):
        return f"{preset['engine']} {preset['engine_version']} · {preset['model']}"
    price = preset.get("price") or {}
    prices = f" · {money(price['in'])} in, {money(price['out'])} out per million" if price else ""
    return f"{preset.get('provider') or 'cloud ' + preset['endpoint']}{prices} · {preset['model']}"


def preset_choices(presets: list[dict[str, Any]]) -> list[Choice]:
    """Each preset to pick: its title, and what it runs or why it cannot."""
    found = []
    for preset in presets:
        setup = preset_setup(preset)
        problems = f" · cannot run: {'; '.join(preset['problems'])}" if preset["problems"] else ""
        found.append(Choice(preset["id"], preset["title"], setup + problems))
    return found


class PickScreen(ModalScreen[str | None]):
    """A title, its choices, and how to choose."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "cancel", "close")]

    def __init__(self, title: str, choices: list[Choice]) -> None:
        super().__init__()
        self.heading = title
        self.choices = choices

    def compose(self) -> ComposeResult:
        """The choices in a panel titled with the title, and how to choose."""
        items = [ListItem(Label(_line(choice))) for choice in self.choices]
        keys = Label("Enter takes the highlighted one; Esc closes this.", classes="hint")
        yield WindowPanel(ListView(*items, id="pick-list"), keys, title=self.heading, id="pick")

    def on_mount(self) -> None:
        """The list has the focus, so the arrows and Enter act on it."""
        self.query_one("#pick-list", ListView).focus()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Enter: the highlighted choice."""
        index = event.list_view.index
        if index is not None and 0 <= index < len(self.choices):
            self.dismiss(self.choices[index].value)

    def action_cancel(self) -> None:
        """Esc: no choice."""
        self.dismiss(None)


def _line(choice: Choice) -> str:
    return f"{choice.label}\n  {choice.detail}" if choice.detail else choice.label
