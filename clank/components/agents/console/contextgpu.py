"""The Context view's On the GPU exactly (design 0012 §4.4, §4.7; board C; §11 step 12): what the engine attends of
the followed session's context, from the slot's facts and the estimate, never a number of the console's own.

Under an engine with an exact window (KVMem): how many tokens it reads exactly, then a row each, about: its first block
(the prompt's start), the newest (after the cached part, or from the last user message on, the later: the estimate's
`suffix` and `since`), what it picked (the rest of its exact window, by its picks, which the engine's facts word), and
the rest, in system memory (attended when picked); when the whole conversation fits, that it is all on the GPU and
nothing is picked. Then the time of the owner's message the steps pick by (design 0012 §4.4: the flow's newest message
of the owner's), and that the engine does not report its picks by part (the engine patch of §4.4 would). Under an
engine without one, the Session view's line (it attends its whole window) and that every part is attended. When the
engine holds no conversation of the session's, or another took it, the Session view's line too. The words are kept
short, since the panel is the narrower of its row; a line still too wide is cut with the style's "…" (`gpu_drawn`).
"""

from datetime import UTC, datetime, tzinfo
from typing import Any

from textual.content import Content

from clank.components.agents.console.contextpanel import gpu_line
from clank.components.agents.console.flowpanel import NO_SESSION
from clank.console.style import current

NAME = 11  # a row's name
FIGURE = 8  # its tokens
NOT_PICKED = "its picks by part: not reported by this engine"  # the KVMem patch of design 0012 §4.4 would say


def gpu(totals: dict[str, Any] | None, view: dict[str, Any] | None, zone: tzinfo | None) -> list[Content]:
    """On the GPU exactly, line by line (module docstring)."""
    if totals is None:
        return [Content.styled(NO_SESSION, "$clank-quiet")]
    if totals.get("unavailable"):
        return [Content.styled(f"context totals not available: {totals['unavailable']}", "$clank-quiet")]
    found, holder = totals.get("gpu"), totals.get("holder") or {}
    line = gpu_line(totals)
    if not found or line is None:
        return [Content.styled("no model runs in the slot: nothing is on the GPU", "$clank-quiet")]
    if holder.get("lost") or holder.get("taken") or found.get("device") == "cloud":
        return [line]
    exact, stored = found.get("exact"), found.get("stored")
    if exact is None:
        return [line, Content("which parts were picked: all of them, every step")]
    if stored is None:
        return [line]
    if stored <= exact:
        return [
            Content(f"All {stored:,} tokens are on the GPU: it reads up to {exact:,} exactly"),
            Content.styled("nothing is picked: the whole conversation fits", "$clank-quiet"),
        ]
    parts = totals.get("parts") or {}
    first, newest = int(found.get("first") or 0), parts.get("suffix")
    cells = current().bar
    shown = [
        Content(f"The model reads {exact:,} tokens exactly:"),
        _row(cells.full, "$clank-part-system", "the first", f"{first:,}", "the prompt's start"),
    ]
    if newest is not None:
        since = "after the cached part" if parts.get("since") == "cache" else "your last message on"
        shown.append(_row(cells.full, "$clank-now", "the newest", f"~{int(newest):,}", since))
    picked = max(exact - first - int(newest or 0), 0)
    shown.append(_row(cells.full, "$clank-data-1", "picked", f"~{picked:,}", str(found.get("picks") or "")))
    shown.append(_row(cells.empty, "$clank-quiet", "the rest", f"{int(found.get('elsewhere') or 0):,}",
                      "in system memory"))  # fmt: skip
    said = _last_said(view, zone)
    if said:
        shown.append(Content(f"steps pick by your message of {said}"))
    shown.append(Content.styled(NOT_PICKED, "$clank-quiet"))
    return shown


def gpu_drawn(
    totals: dict[str, Any] | None, width: int, zone: tzinfo | None, view: dict[str, Any] | None
) -> list[Content]:
    """On the GPU exactly, each line cut to `width`."""
    return [_cut(line, width) for line in gpu(totals, view, zone)]


def _row(glyph: str, tone: str, name: str, figure: str, words: str) -> Content:
    return Content.assemble((glyph, tone), f" {name:<{NAME}}{figure:>{FIGURE}}  ", (words, "$clank-quiet"))


def _last_said(view: dict[str, Any] | None, zone: tzinfo | None) -> str:
    """When the owner's newest message was written (HH:MM), "" when the flow holds none."""
    said = [node for node in (view or {}).get("nodes") or [] if node.get("kind") == "said" and node.get("created")]
    if not said:
        return ""
    created = float(said[-1]["created"]) / 1000
    return datetime.fromtimestamp(created, UTC).astimezone(zone).strftime("%H:%M")


def _cut(line: Content, width: int) -> Content:
    if line.cell_length <= width:
        return line
    return Content.assemble(line.truncate(max(width - 1, 0)), current().marks.cut)
