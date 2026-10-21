"""Every key the console shows is a button (design 0011 §12, decision 0120): a key and its words, pressed by Enter or
Space while it has the focus, by its key from anywhere on its page, or by a click, all three the same way.

A button (`Button`) is a key the page declares (`PageKey`) and the words it shows here, the key's own unless a panel
says more. `button` draws one: a blank cell, its key in `key`, a space, its words (`quiet` on the keys bar, `text` in a
panel), a blank cell; each state (`STATES`) in its elements of the style (§12.8), its fill covering the blank cells, so
that no state changes its width and nothing on its row moves. `lay_out` sets a group's buttons in lines for a width: a
row goes on to its next line between two buttons, never inside one (a button wider than the row is cut with the
style's "…"), a column's button wraps its words under themselves, a row may lead with words of its own ("Next:"); it
says where each button's cells are, for a click.
"""

import textwrap
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from rich.cells import cell_len
from textual.content import Content

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
