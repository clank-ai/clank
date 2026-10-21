"""The keys bar (design 0011 §7 and §12): the console's bottom row, in place of Textual's footer, and a group of buttons
(`buttons.Buttons`), one for each key it shows.

It shows the keys of the page on screen (`Page.shown_keys`), wherever the focus is, then the keys that act anywhere,
and the palette's at the right, as `keys.fit_keys` fits them to its width: each key a button, its key in `key` and its
words in `quiet`, the blank cells of two buttons side by side making the two spaces between keys, so each key stands
at the column it stood at before keys were buttons (the last button's blank cell at the right may fall past the bar's
edge). It takes the focus, last in the screen's order: → and ← move along it and stop at its ends, Enter and Space
press the key under its cursor, a click the key under it, each through the console's one door (`press_button`), so a
key pressed here does what the key typed does. ↑ goes back into the page, as Esc does (`into_page`).
"""

from collections.abc import Sequence

from textual import events
from textual.content import Content
from textual.geometry import Size

from clank.console.buttons import Button, Buttons, Place_, button
from clank.console.keys import PALETTE, PageKey, fit_keys


class KeysBar(Buttons):
    """The keys bar: the keys of the page on screen, then the keys that act anywhere, each a button."""

    DEFAULT_CSS = """
    KeysBar {
        width: 100%;
        height: 1;
        background: $clank-bars;
        text-wrap: nowrap;
        text-overflow: clip;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(place="bar", id=id)
        self.keys: tuple[PageKey, ...] = ()
        self._palette = False

    def show_keys(self, keys: Sequence[PageKey]) -> None:
        """Show these keys of a page, then the keys that act anywhere, as the bar's width lets it."""
        self.keys = tuple(keys)
        self._fit()

    def on_resize(self, event: events.Resize) -> None:
        """Fit the keys to the new width."""
        self._fit()

    def lines(self, width: int) -> tuple[list[Content], list[Place_]]:
        """One row: the keys from the left, the palette's at the right."""
        parts: list[Content] = []
        places: list[Place_] = []
        column = 0
        for index, each in enumerate(self.buttons):
            drawn = button(each.label, each.said, self.state(index), "bar")
            if self._palette and each.key is PALETTE:
                room = max(width - column - drawn.cell_length, 0)
                parts.append(Content(" " * room))
                column += room
            places.append((index, 0, column, column + drawn.cell_length))
            parts.append(drawn)
            column += drawn.cell_length
        return [Content.assemble(*parts)], places

    def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
        """Always one row."""
        return 1

    def across(self, up: bool) -> None:
        """↑ goes back into the page; ↓ stays."""
        into = getattr(self.app, "into_page", None)
        if up and into is not None:
            into()

    def _fit(self) -> None:
        width = self.size.width
        if not width:
            return
        fitted, self._palette = fit_keys(self.keys, width)
        self.show([Button(key) for key in [*fitted, *([PALETTE] if self._palette else [])]])
