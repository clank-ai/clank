"""Lists and labels that change without flicker. The console's pages read again every few seconds; a list made again
each time flickers, and its highlight jumps for a moment. `refill` shows a page's lines in a `ListView`: nothing happens
when they are what it shows; a line that changed is updated in place; the items are made again only when their number
changed; and the highlight stays on the same row (by its key, when the page gives keys). `relabel` updates a label only
when its text or colors change, since every update lays the page out again.

Textual's `Content` compares equal when only its colors differ, so lines are compared by their text and their spans.
"""

from collections.abc import Sequence
from typing import Any

from textual.content import Content
from textual.widgets import Label, ListItem, ListView

Line = str | Content


class LineItem(ListItem):
    """A list item of one line, which it keeps to compare with the next."""

    def __init__(self, line: Line) -> None:
        super().__init__(Label(line))
        self.line = line


def same(first: Line | Any, second: Line | Any) -> bool:
    """Whether two lines show the same: the same text, in the same colors."""
    return str(first) == str(second) and _spans(first) == _spans(second)


def refill(listed: ListView, lines: Sequence[Line], keys: Sequence[str] = (), keep: str | None = None) -> None:
    """Show these lines in the list, changing only what changed; then highlight the row of `keep` among `keys`."""
    items = [child for child in listed.children if isinstance(child, LineItem)]
    if len(items) == len(lines) == len(listed.children):
        for item, line in zip(items, lines, strict=True):
            if not same(item.line, line):
                item.line = line
                item.query_one(Label).update(line)
    else:
        index = listed.index
        listed.clear()
        listed.extend(LineItem(line) for line in lines)
        if index is not None and lines:
            listed.index = min(index, len(lines) - 1)
    if keep is not None and keep in keys:
        found = list(keys).index(keep)
        if listed.index != found:
            listed.index = found


def relabel(label: Label, text: Line) -> None:
    """Show this text in the label, unless it shows it already."""
    if not same(label.content, text):
        label.update(text)


def _spans(line: Any) -> tuple[Any, ...]:
    return tuple(line.spans) if isinstance(line, Content) else ()
