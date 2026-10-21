"""The Monitor's Biggest in the context panel (design 0012 §2, §4.6; §11 step 12): the largest items in the followed
session's context, by the estimate the service made of its last finished step (`clank/components/agents/estimate.py`,
in the context totals' `parts`), biggest first, at most `SHOWN`.

`line` draws one: its tokens (about, as every figure of the estimate), a swatch in its part's color (`parts.py`), the
step it came with (the flow's number, by its call id; blank when the flow does not say), what it is (a result as its
call: `read src/grid.py`, the workspace's `/workspace/` left out; a call as `call: ...`; else the census's words), and
its marks: loop text, made again later (a newer call with the same arguments, so it could be freed), cleared (by you,
through the Guide's Drop, and about what that freed, as the flow says it; or by OpenCode), kept if compacted (inside the
tail a compaction keeps). Narrower than the line needs, what it is is cut first (with the style's "…", down to `LEAST`
characters), then its marks go, then its step; its tokens and swatch never. `whole` says an item whole, for the window
Enter opens: what it is, its part (and the one loop text came from), its tokens and characters, its step, its call id,
and why each mark, then how the estimate is made.

`BiggestList` is the panel's content: a list of the rows (↑↓ move in it), each line drawn again only when it changed,
the highlight kept on the same item as the estimate comes again; `ROWS` rows, scrolling beyond them, or fewer when the
page is short of rows (it gives up rows with Tool calls, the Monitor's `CallsRow`).
"""

from typing import Any

from textual import events
from textual.content import Content
from textual.widgets import ListView

from clank.components.agents.console.parts import SWATCH, tokens, tone
from clank.components.agents.estimate import LABELS
from clank.console.lists import refill
from clank.console.style import current

SHOWN = 12  # the biggest items listed
ROWS = 8  # the rows it shows, scrolling beyond them
NO_PARTS = "the parts come with the session's next finished step"
STEP = 8  # the step's column: "step 16 "
LEAST = 20  # characters of what an item is kept before its marks go, then its step (a file's name, mostly)
WIDTH = 74  # the width drawn for before the panel is laid out
WORKSPACE = "/workspace/"  # where a workspace's files are in its container: left out of what an item is


def rows(totals: dict[str, Any] | None) -> list[dict[str, Any]]:
    """The biggest items of the estimate, biggest first, at most `SHOWN`."""
    found = (totals or {}).get("parts") or {}
    return list(found.get("items") or [])[:SHOWN]


def said(row: dict[str, Any]) -> str:
    """What an item is, briefly (module docstring)."""
    what = str(row.get("what") or "")
    if row.get("of") == "results":
        what = what.removeprefix("the result of ")
    elif row.get("of") == "calls":
        what = f"call: {what}"
    return what.replace(WORKSPACE, "")


def cleared(row: dict[str, Any]) -> str:
    """Who cleared an item's result, and what that freed when it was the owner, through the Guide's Drop."""
    if row.get("cleared_by") != "you":
        return "cleared by OpenCode"
    freed = row.get("freed")
    return f"cleared by you, freed about {tokens(freed)}" if isinstance(freed, int) else "cleared by you"


def marks(row: dict[str, Any]) -> list[str]:
    """An item's marks, in words."""
    found = []
    if row.get("loop"):
        found.append("loop text")
    if row.get("again"):
        found.append("made again later")
    if row.get("cleared"):
        found.append(cleared(row))
    if row.get("kept"):
        found.append("kept if compacted")
    return found


def line(row: dict[str, Any], width: int) -> Content:
    """One item on one line, no wider than `width` (module docstring: what is cut first, then the marks, then the
    step)."""
    head = Content.assemble(f"{tokens(row.get('tokens')):>6} ", (SWATCH, tone(str(row.get("part")))), " ")
    step = f"step {row['step']}".ljust(STEP) if row.get("step") is not None else " " * STEP
    tail = " · ".join(marks(row))
    what = said(row)
    for stepped, marked in ((step, tail), (step, ""), ("", "")):
        ending = f" · {marked}" if marked else ""
        room = width - head.cell_length - len(stepped) - len(ending)
        if room >= min(LEAST, len(what)):
            break
    shown = Content.assemble(head, stepped, _fit(what, max(room, 0)), (ending, "$clank-quiet"))
    return shown if shown.cell_length <= width else _cut(shown, width)


def item_line(row: dict[str, Any]) -> str:
    """An item on one line of a window that lists items: its tokens, its step, what it is and its marks."""
    step = f"step {row['step']}" if row.get("step") is not None else ""
    marked = " · ".join(marks(row))
    return f"{int(row.get('tokens') or 0):>7,}  {step:<8} {said(row)}" + (f" · {marked}" if marked else "")


def whole(row: dict[str, Any], estimate: dict[str, Any] | None) -> list[str]:
    """An item whole, for its window: what it is, its part, its tokens, its step, its call id, why each mark, and how
    the estimate is made."""
    part, of = str(row.get("part") or ""), str(row.get("of") or "")
    came = f" (from the {LABELS.get(of, of)})" if part == "loop" and of and of != "loop" else ""
    said = [
        str(row.get("what") or ""),
        f"part: {LABELS.get(part, part)}{came}, about {int(row.get('tokens') or 0):,} tokens of the estimate; "
        f"{int(row.get('chars') or 0):,} characters",
        f"step {row['step']}" if row.get("step") is not None else "its step: the session's flow does not say",
    ]
    if row.get("call"):
        said.append(f"call id: {row['call']}")
    if row.get("loop"):
        said.append(f"loop text: {row['loop']}")
    if row.get("again"):
        said.append("a newer call with the same arguments came later: this result could be freed (the Guide's Drop)")
    if row.get("cleared") and row.get("cleared_by") == "you":
        freed = row.get("freed")
        which = f", which freed about {freed:,} tokens" if isinstance(freed, int) else ""
        said.append(f"you cleared it with the Guide's Drop{which}: a short note stands in its place")
    elif row.get("cleared"):
        said.append("OpenCode cleared it: a short note stands in its place")
    if row.get("kept"):
        keeps = (estimate or {}).get("keeps")
        said.append(f"inside the last {keeps:,} tokens a compaction keeps" if keeps else "kept by a compaction")
    said.append(f"How it is estimated: {(estimate or {}).get('how') or 'not known'}.")
    return said


def _fit(text: str, width: int) -> str:
    """Text cut to `width`, ending in the style's mark of cut text, no space before it."""
    return text if len(text) <= width else text[: max(width - 1, 0)].rstrip() + current().marks.cut


def _cut(shown: Content, width: int) -> Content:
    return Content.assemble(shown.truncate(max(width - 1, 0)), current().marks.cut)


class BiggestList(ListView):
    """The Biggest panel's content: the biggest items; Enter on the page opens the one highlighted."""

    DEFAULT_CSS = """
    BiggestList {
        height: auto;
        max-height: 8;  /* ROWS */
    }
    BiggestList > ListItem Label {
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.shown: list[dict[str, Any]] = []
        self.estimate: dict[str, Any] | None = None

    def show(self, totals: dict[str, Any] | None) -> None:
        """Show the biggest items of these totals, the highlight kept on its item."""
        kept = self.highlighted()
        self.estimate = (totals or {}).get("parts")
        self.shown = rows(totals)
        self._draw(_key(kept) if kept else None)

    def highlighted(self) -> dict[str, Any] | None:
        """The item highlighted, the biggest when none is."""
        if not self.shown:
            return None
        index = self.index if self.index is not None and 0 <= self.index < len(self.shown) else 0
        return self.shown[index]

    def on_resize(self, event: events.Resize) -> None:
        """Draw the lines again for the new width (or height: fewer rows may need its scroll bar)."""
        kept = self.highlighted()
        self._draw(_key(kept) if kept else None)

    def _draw(self, keep: str | None) -> None:
        rows_shown = self.size.height or ROWS
        scroll = self.styles.scrollbar_size_vertical if len(self.shown) > rows_shown else 0
        width = max((self.content_size.width or WIDTH) - scroll, 10)
        refill(self, [line(row, width) for row in self.shown], [_key(row) for row in self.shown], keep)
        if self.shown and self.index is None:
            self.index = 0
        self.display = bool(self.shown)


def _key(row: dict[str, Any]) -> str:
    """An item's key in the list: its call and part, else what it is."""
    return f"{row.get('of')}:{row.get('call') or row.get('what')}"
