"""The Context view's Could be freed (design 0012 §4.6, §4.7; board C; §11 step 12): the Guide's actions that would free
room in the followed session's context, from the estimate (`freed`): the loop text in tool results and the earlier
results of calls made again, each dropped an item at a time by the Guide's Drop (design 0012 §9.7); the loop text the
model wrote, which no Drop clears, offered to compacting (`k`); and compacting now (the Guide's Compact now, `k`), each
with about what it frees. No row offers what its key refuses.

`line` draws one: its key (`k` for Compact now), what it frees in words (with how many items) and "frees about N" at the
right; narrower, the words are cut first, the figure stays. Enter on Compact now asks first, as `k` does; Enter on the
others opens the window of their items (`itemsscreen.py`), biggest first, where `x` drops the one highlighted
through the Guide's Drop (`freed_items`, `freed_notes`). `FreedList` holds the rows.
"""

from typing import Any

from textual import events
from textual.content import Content
from textual.widgets import ListView

from clank.console.lists import refill
from clank.console.style import current

NOTHING_FREED = "nothing to free: no loop text, no call made again, and the session within what a compaction keeps"
DROPPED = (
    "Each is dropped by the Guide's Drop (design 0012 §9.7), an item at a time; what follows it in the context is read "
    "again at the next step."
)
WIDTH = 120  # the width drawn for before the panel is laid out


def freed_rows(totals: dict[str, Any] | None) -> list[dict[str, Any]]:
    """What could be freed, from the estimate: the loop text, the earlier results of calls made again, compact now."""
    return list(((totals or {}).get("parts") or {}).get("freed") or [])


def line(row: dict[str, Any], width: int) -> Content:
    """One way to free room on one line, no wider than `width`: its key, its words (cut first), about what it frees."""
    key = "k" if row.get("how") == "compact" else " "
    count = int(row.get("items") or 0)
    words = str(row.get("words") or "")
    if count:
        words += f": {count} item{'' if count == 1 else 's'}"
    figure = f"frees about {int(row.get('tokens') or 0):,}"
    room = width - 3 - 2 - len(figure)
    shown = Content.assemble((f" {key} ", "$clank-key"), _fit(words, max(room, 0)).ljust(max(room, 0)), "  ", figure)
    return shown if shown.cell_length <= width else _cut(shown, width)


def freed(totals: dict[str, Any] | None, width: int) -> list[Content]:
    """Could be freed, a line each; what it says without the estimate or with nothing to free."""
    rows = freed_rows(totals)
    if not rows:
        return [_cut(Content.styled(NOTHING_FREED, "$clank-quiet"), width)]
    return [line(row, width) for row in rows]


def freed_items(totals: dict[str, Any] | None, row: dict[str, Any]) -> list[dict[str, Any]]:
    """The items a way of freeing would drop, biggest first; a result already cleared is not one."""
    found = (totals or {}).get("parts") or {}
    if row.get("what") == "loop":
        return [item for item in found.get("items") or []
                if item.get("loop") and item.get("of") == "results" and not item.get("cleared")]  # fmt: skip
    if row.get("what") == "again":
        return [item for item in found.get("items") or [] if item.get("again") and not item.get("cleared")]
    return []


def freed_notes(totals: dict[str, Any] | None, row: dict[str, Any]) -> list[str]:
    """What the window of a way of freeing says under its items: how many more the census did not keep, and how
    they are dropped."""
    more = int(row.get("items") or 0) - len(freed_items(totals, row))
    return [*([f"and {more} more the census did not keep"] if more > 0 else []), DROPPED]


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(width - 1, 0)].rstrip() + current().marks.cut


def _cut(shown: Content, width: int) -> Content:
    if shown.cell_length <= width:
        return shown
    return Content.assemble(shown.truncate(max(width - 1, 0)), current().marks.cut)


class FreedList(ListView):
    """Could be freed: a row each (↑↓ move in it); Enter on the page opens the one highlighted."""

    DEFAULT_CSS = """
    FreedList {
        height: auto;
    }
    FreedList > ListItem Label {
        text-wrap: nowrap;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.totals: dict[str, Any] | None = None
        self.shown: list[dict[str, Any]] = []

    def show(self, totals: dict[str, Any] | None) -> None:
        """Show what these totals could free, the highlight kept on its row."""
        kept = self.highlighted()
        self.totals = totals
        self.shown = freed_rows(totals)
        self._draw(str(kept["what"]) if kept else None)

    def highlighted(self) -> dict[str, Any] | None:
        """The row highlighted, the first when none is."""
        if not self.shown:
            return None
        index = self.index if self.index is not None and 0 <= self.index < len(self.shown) else 0
        return self.shown[index]

    def on_resize(self, event: events.Resize) -> None:
        """Draw the rows again for the new width."""
        kept = self.highlighted()
        self._draw(str(kept["what"]) if kept else None)

    def _draw(self, keep: str | None) -> None:
        width = self.content_size.width or WIDTH
        refill(self, [line(row, width) for row in self.shown], [str(row["what"]) for row in self.shown], keep)
        if self.shown and self.index is None:
            self.index = 0
        self.display = bool(self.shown)
