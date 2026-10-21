"""Every key the console shows is a button (design 0011 §12, decision 0120): a key and its words, pressed by Enter or
Space while it has the focus, by its key from anywhere on its page, or by a click, all three the same way.

A button (`Button`) is a key the page declares (`PageKey`) and the words it shows here, the key's own unless a panel
says more. `button` draws one: a blank cell, its key in `key`, a space, its words (`quiet` on the keys bar, `text` in a
panel), a blank cell; each state (`STATES`) in its elements of the style (§12.8), its fill covering the blank cells, so
that no state changes its width and nothing on its row moves. `lay_out` sets a group's buttons in lines for a width: a
row goes on to its next line between two buttons, never inside one (a button wider than the row is cut with the
style's "…"), a column's button wraps its words under themselves, a row may lead with words of its own ("Next:"); it
says where each button's cells are, for a click.

`Buttons` is a group (decision 0120): one widget that takes the focus, with its own cursor, so Tab stops on it once
and the arrows move inside it (decision 0121). Its keys are its own handlers, never priority bindings, so a list or an
input keeps its own keys. A press goes through the console's one door (`ClankConsole.press_button`, which a key typed
takes too) unless a window gives its own; whether a button can act now is the console's to say (`unable_button`), and
the message line says what the focused one does (`hint`).
"""

import textwrap
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from rich.cells import cell_len
from textual import events
from textual.content import Content
from textual.geometry import Size
from textual.widget import Widget

from clank.console.gauges import fit
from clank.console.keys import PageKey, shown

State = Literal["normal", "hover", "focused", "pressed", "unable", "unable_focused"]
Place = Literal["bar", "panel"]
STATES: tuple[State, ...] = ("normal", "hover", "focused", "pressed", "unable", "unable_focused")
# Each state's fill, its key's color and its words' color ("": the place's words, `WORDS`), elements of the style.
LOOKS: dict[State, tuple[str, str, str]] = {
    "normal": ("", "$clank-key", ""),
    "hover": ("$clank-button-hover", "$clank-key", "$clank-text"),
    "focused": ("$clank-button-focused", "$clank-button-focused-text", "$clank-button-focused-text"),
    "pressed": ("$clank-button-pressed", "$clank-button-focused-text", "$clank-button-focused-text"),
    "unable": ("", "$clank-dim", "$clank-dim"),
    "unable_focused": ("$clank-button-unable-focused", "$clank-quiet", "$clank-quiet"),
}
WORDS: dict[Place, str] = {"bar": "$clank-quiet", "panel": "$clank-text"}
Place_ = tuple[int, int, int, int]  # a button's index, its line, its first column and the column after its last


@dataclass(frozen=True)
class Button:
    """A key the page declares, and the words it shows here (the key's own unless a panel says more)."""

    key: PageKey
    words: str = ""

    @property
    def said(self) -> str:
        """Its words as shown."""
        return self.words or self.key.words

    @property
    def label(self) -> str:
        """Its key as the console writes it ("?", "esc", "g")."""
        return shown(self.key.key)


def _styles(state: State, place: Place) -> tuple[str, str, str]:
    """The fill's style, the key's and the words', for a state in a place."""
    fill, key, words = LOOKS[state]
    words = words or WORDS[place]
    on = f" on {fill}" if fill else ""
    return (f"on {fill}" if fill else "", f"{key}{on}", f"{words}{on}")


def button(key: str, words: str, state: State = "normal", place: Place = "panel") -> Content:
    """One button on one line: a blank cell, its key, a space, its words, a blank cell, in its state's look."""
    pad, keyed, worded = _styles(state, place)
    return Content.assemble((" ", pad), (key, keyed), (f" {words}", worded), (" ", pad))


def _column_lines(key: str, words: str, state: State, place: Place, width: int) -> list[Content]:
    """A column's button, its words wrapped under themselves, every line as wide as its widest so its fill is whole."""
    room = max(width - 2 - cell_len(key) - 1, 1)
    parts = textwrap.wrap(words, room, break_long_words=True, break_on_hyphens=False) or [""]
    inner = cell_len(key) + 1 + max(cell_len(part) for part in parts)
    pad, keyed, worded = _styles(state, place)
    lines = []
    for number, part in enumerate(parts):
        lead = (key, keyed) if number == 0 else (" " * cell_len(key), worded)
        rest = f" {part}".ljust(inner - cell_len(key))
        lines.append(Content.assemble((" ", pad), lead, (rest, worded), (" ", pad)))
    return lines


def lay_out(
    buttons: Sequence[Button],
    states: Sequence[State],
    width: int,
    *,
    column: bool = False,
    lead: str = "",
    place: Place = "panel",
) -> tuple[list[Content], list[Place_]]:
    """A group's lines for `width` columns, and where each button's cells are: one entry per line it covers."""
    lines: list[Content] = []
    places: list[Place_] = []
    if column:
        for index, (each, state) in enumerate(zip(buttons, states, strict=True)):
            for part in _column_lines(each.label, each.said, state, place, width):
                places.append((index, len(lines), 0, part.cell_length))
                lines.append(part)
        return lines, places
    head = f"{lead} " if lead else ""
    indent = cell_len(head) if cell_len(head) <= width // 2 else 0
    parts: list[Content] = [Content(head)] if head else []
    x = cell_len(head)
    for index, (each, state) in enumerate(zip(buttons, states, strict=True)):
        drawn = button(each.label, each.said, state, place)
        if x > indent and x + drawn.cell_length > width:
            lines.append(Content.assemble(*parts))
            parts, x = ([Content(" " * indent)] if indent else []), indent
        if width > 0 and x + drawn.cell_length > width:  # wider than a whole line: its words cut
            room = max(width - x - 3 - cell_len(each.label), 1)
            drawn = button(each.label, fit(each.said, room), state, place)
        places.append((index, len(lines), x, x + drawn.cell_length))
        parts.append(drawn)
        x += drawn.cell_length
    if parts:
        lines.append(Content.assemble(*parts))
    return lines, places


PRESSED_SECONDS = 0.2  # how long a pressed button shows `pressed`
ALONG = {False: ("left", "right"), True: ("up", "down")}  # the arrows that move in a row, and in a column
Press = Callable[[Button], None]
Unable = Callable[[Button], str]


class Buttons(Widget, can_focus=True):
    """A group of buttons (design 0011 §12.2, decision 0120): one widget that takes the focus, a row or a column, with
    its own cursor. Along it the arrows move the cursor and stop at its ends, Home and End go to its first and last;
    across a row, ↑ ↓ go to the nearest group above or below; Enter and Space press the button under the cursor, a
    click the one clicked. A press goes to `press`, the console's one door unless a window gives its own; a button that
    cannot act now (`unable`, the console's unless given) is drawn dimmed and still takes the focus. The focused button
    is drawn focused only while the group has the focus. Its keys are its own handlers, never priority bindings, so a
    list or an input beside it keeps its own. A group made with `focusable=False` (in a list's row) is only clicked."""

    DEFAULT_CSS = """
    Buttons {
        width: 1fr;
        height: auto;
        text-wrap: nowrap;
        text-overflow: clip;
    }
    """

    def __init__(
        self,
        buttons: Sequence[Button] = (),
        *,
        column: bool = False,
        lead: str = "",
        place: Place = "panel",
        press: Press | None = None,
        unable: Unable | None = None,
        focusable: bool = True,
        id: str | None = None,
        classes: str = "",
    ) -> None:
        super().__init__(id=id, classes=classes)
        self.can_focus = focusable
        self.buttons: tuple[Button, ...] = tuple(buttons)
        self.column = column
        self.lead = lead
        self.place: Place = place
        self._press = press
        self._unable = unable
        self.cursor = 0
        self.hover: int | None = None
        self.pressed: int | None = None
        self._places: list[Place_] = []
        self._reasons: tuple[str, ...] = ()

    @property
    def current(self) -> Button | None:
        """The button under the cursor."""
        return self.buttons[self.cursor] if self.buttons else None

    def show(self, buttons: Sequence[Button], lead: str | None = None) -> None:
        """Show these buttons (and this lead), the cursor kept where it was; drawn again only when something changed."""
        shown_buttons, shown_lead = tuple(buttons), self.lead if lead is None else lead
        if (shown_buttons, shown_lead) == (self.buttons, self.lead):
            self.recheck()
            return
        self.buttons, self.lead = shown_buttons, shown_lead
        self.cursor = min(self.cursor, max(len(shown_buttons) - 1, 0))
        self.hover = None
        self.refresh(layout=True)
        if self.has_focus:
            self._hint()

    def recheck(self) -> None:
        """Draw again when whether a button can act now changed."""
        if self._reasons != tuple(self.reason(each) for each in self.buttons):
            self.refresh()
            if self.has_focus:
                self._hint()

    def reason(self, each: Button) -> str:
        """Why a button cannot act now ("" when it can)."""
        unable = self._unable or getattr(self.app, "unable_button", None)
        return str(unable(each)) if unable is not None else ""

    def state(self, index: int) -> State:
        """A button's state as drawn now."""
        unable = bool(self.reason(self.buttons[index]))
        if index == self.pressed and not unable:
            return "pressed"
        if self.has_focus and index == self.cursor:
            return "unable_focused" if unable else "focused"
        if unable:
            return "unable"
        return "hover" if index == self.hover else "normal"

    def lines(self, width: int) -> tuple[list[Content], list[Place_]]:
        """The group's lines for a width, and where each button's cells are (the keys bar sets its own)."""
        states = [self.state(index) for index in range(len(self.buttons))]
        return lay_out(self.buttons, states, width, column=self.column, lead=self.lead, place=self.place)

    def render(self) -> Content:
        """The group, as its width lets it."""
        self._reasons = tuple(self.reason(each) for each in self.buttons)
        lines, self._places = self.lines(self.size.width)
        return Content("\n").join(lines)

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        """As many rows as its lines for the width."""
        return len(self.lines(width)[0]) if self.buttons or self.lead else 0

    def press(self, index: int) -> None:
        """Press a button: through `press`, the console's one door unless given."""
        if not 0 <= index < len(self.buttons):
            return
        pressed = self.buttons[index]
        door = self._press or getattr(self.app, "press_button", None)
        if door is not None:
            door(pressed)
        if self._press is not None and not self.reason(pressed):  # the console's door flashes its own
            self.flash(pressed.key.key)

    def flash(self, key: str) -> None:
        """Show the button of this key pressed, for a moment."""
        index = next((index for index, each in enumerate(self.buttons) if each.key.key == key), None)
        if index is None:
            return
        self.pressed = index
        self.refresh()
        self.set_timer(PRESSED_SECONDS, self._unpress)

    def _unpress(self) -> None:
        self.pressed = None
        self.refresh()

    def move(self, index: int) -> None:
        """Put the cursor on a button; it stops at the group's ends."""
        index = min(max(index, 0), max(len(self.buttons) - 1, 0))
        if index != self.cursor:
            self.cursor = index
            self.refresh()
            self._hint()

    def on_key(self, event: events.Key) -> None:
        """Its keys: along it, Home and End, across a row, Enter and Space, Esc; the others go on."""
        back, forth = ALONG[self.column]
        key = event.key
        if key in (back, forth):
            self.move(self.cursor + (1 if key == forth else -1))
        elif key in ("home", "end"):
            self.move(0 if key == "home" else len(self.buttons) - 1)
        elif key in ("enter", "space"):
            self.press(self.cursor)
        elif key in ("up", "down") and not self.column:
            self.across(key == "up")
        elif key == "escape" and not self.screen.is_modal and hasattr(self.app, "to_main"):
            self.app.to_main()
        else:
            return
        event.stop()
        event.prevent_default()

    def across(self, up: bool) -> None:
        """↑ or ↓ in a row: the nearest group above or below on the screen, the one nearest the cursor's column first;
        when there is none, the focus stays."""
        here = self.region
        column = here.x + next((start for index, _, start, _ in self._places if index == self.cursor), 0)
        best: tuple[int, Widget] | None = None
        for widget in self.screen.focus_chain:
            area = widget.region
            if widget is self or not area.area or widget in self.ancestors:
                continue
            gap = here.y - area.bottom if up else area.y - here.bottom
            if gap < 0:
                continue
            aside = 0 if area.x <= column < area.right else min(abs(area.x - column), abs(area.right - 1 - column))
            score = gap + 2 * aside
            if best is None or score < best[0]:
                best = (score, widget)
        if best is not None:
            best[1].focus()

    def on_click(self, event: events.Click) -> None:
        """A click presses the button under it, the cursor (and the focus, for a group that takes it) moved to it."""
        index = self._at(event.x, event.y)
        if index is None:
            return
        event.stop()
        self.cursor = index
        if self.can_focus:
            self.focus()
        self.refresh()
        self.press(index)

    def on_mouse_move(self, event: events.MouseMove) -> None:
        """The button under the mouse takes the hover's ground; the focus stays where it is."""
        index = self._at(event.x, event.y)
        if index != self.hover:
            self.hover = index
            self.refresh()

    def on_leave(self, event: events.Leave) -> None:
        """The mouse left: no hover."""
        if self.hover is not None:
            self.hover = None
            self.refresh()

    def on_focus(self, event: events.Focus) -> None:
        """Draw the cursor's button focused, and say on the message line what it does."""
        self.refresh()
        self._hint()

    def on_blur(self, event: events.Blur) -> None:
        """Draw the cursor's button as the others; what the message line said of it goes."""
        self.refresh()
        unhint = getattr(self.app, "unhint", None)
        if unhint is not None:
            unhint()

    def _at(self, x: int, y: int) -> int | None:
        return next((index for index, line, start, end in self._places if line == y and start <= x < end), None)

    def _hint(self) -> None:
        hint = getattr(self.app, "hint", None)
        if hint is not None and self.current is not None and self.has_focus:
            hint(self.current, self.reason(self.current))
