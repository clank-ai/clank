"""The Context view's Over this session (design 0012 §4.5, §4.7; board C; §11 step 12): a chart of the followed
session's size at each finished step, as OpenCode counts it (`contextpanel.growth`), against the window, each column
split by part where the gateway's census of that step's request is known (the totals' `steps`, joined by the request
the flow paired with the step), so the owner sees what grew.

`CHART_ROWS` rows, the window at the top: a row is filled where the step's size passes it, its top cell in eighths (the
style's sparks); each cell takes the color of the part that covers most of it (the parts of the step scaled to its size,
in the bar's order from the bottom), the plain data color for a step whose parts are not known, the failed color for a
step the loop guard stopped and the attention color for a compaction, as the Session view's spark draws them. On the
left, the axis (`AXIS` columns): the window, half of it, and 0. Under the chart: a mark under each column the loop guard
stopped (✗) or that compacted (▲), the time of the first step and of the last, and each mark said. The newest steps
that fit are drawn; narrower, fewer steps; no line wider than the panel. Before a step ended, it says so.
"""

from datetime import UTC, datetime, tzinfo
from typing import Any

from textual.content import Content

from clank.components.agents.console.contextpanel import Point, growth, mark_words
from clank.components.agents.console.flowpanel import NO_SESSION
from clank.components.agents.console.parts import tokens, tone
from clank.console.style import current, mark

CHART_ROWS = 8
AXIS = 6  # the axis's columns: " 262K "
NO_STEP = "no step of this session has ended since Clank watched it"


def over_session(
    totals: dict[str, Any] | None, width: int, view: dict[str, Any] | None, zone: tzinfo | None
) -> list[Content]:
    """The chart and its marks, line by line, none wider than `width` (module docstring)."""
    if totals is None:
        return [Content.styled(NO_SESSION, "$clank-quiet")]
    if totals.get("unavailable"):
        return [_cut(Content.styled(f"context totals not available: {totals['unavailable']}", "$clank-quiet"), width)]
    points = growth(view)
    if not points:
        return [_cut(Content.styled(NO_STEP, "$clank-quiet"), width)]
    top = float(totals.get("window") or max(point.size for point in points) or 1)
    room = max(width - AXIS, 0)
    shown = points[-room:] if room else []
    parts = {str(step.get("request")): dict(step.get("parts") or {}) for step in totals.get("steps") or []}
    lines = []
    for row in reversed(range(CHART_ROWS)):
        label = tokens(top) if row == CHART_ROWS - 1 else ("0" if row == 0 else "")
        if row == CHART_ROWS // 2 - 1:
            label = tokens(top / 2)
        cells = [_cell(point, row, top, parts.get(point.request)) for point in shown]
        lines.append(Content.assemble((f"{label:>{AXIS - 1}} ", "$clank-quiet"), *cells))
    marked = [point for point in shown if point.mark]
    if marked:
        signs = [(" ", "") if not point.mark else ((mark("failed"), "$clank-failed") if point.mark == "looped"
                 else ("▲", "$clank-attention")) for point in shown]  # fmt: skip
        lines.append(Content.assemble(" " * AXIS, *signs))
    lines.append(Content.styled(" " * AXIS + _times(shown, zone), "$clank-quiet"))
    if marked:
        lines.append(Content.styled(" · ".join(mark_words(point, zone) for point in marked), "$clank-quiet"))
    return [_cut(line, width) for line in lines]


def _cell(point: Point, row: int, top: float, parts: dict[str, int] | None) -> tuple[str, str]:
    """One cell of a column: its glyph (full, eighths at the top, or none) and its color."""
    step = top / CHART_ROWS
    low, high = row * step, (row + 1) * step
    sparks = current().sparks
    if point.size >= high:
        glyph = current().bar.full
    elif point.size > low:
        index = round((point.size - low) / step * len(sparks)) - 1
        glyph = sparks[index] if index >= 0 else " "
    else:
        glyph = " "
    if point.mark == "looped":
        return glyph, "$clank-failed"
    if point.mark == "compacted":
        return glyph, "$clank-attention"
    return glyph, _part(parts, point.size, low, min(high, float(point.size))) if parts else "$clank-data-1"


def _part(parts: dict[str, int], size: int, low: float, high: float) -> str:
    """The color of the part that covers most of a cell's range, the step's parts scaled to its size."""
    total = sum(parts.values())
    if total <= 0 or high <= low:
        return "$clank-data-1"
    start, best, most = 0.0, "", -1.0
    for name, count in parts.items():
        end = start + count * size / total
        covered = max(0.0, min(end, high) - max(start, low))
        if covered > most:
            best, most = name, covered
        start = end
    return tone(best)


def _times(points: list[Point], zone: tzinfo | None) -> str:
    """The first step's time at the left, the last's under its column when there is room."""
    if not points:
        return ""
    first, last = _clock(points[0].at, zone), _clock(points[-1].at, zone)
    return first.ljust(len(points) - len(last)) + last if len(points) >= len(first) + len(last) + 1 else first


def _clock(at: int | None, zone: tzinfo | None) -> str:
    if at is None or at <= 0:
        return "--:--"
    return datetime.fromtimestamp(at / 1000, UTC).astimezone(zone).strftime("%H:%M")


def _cut(line: Content, width: int) -> Content:
    if line.cell_length <= width:
        return line
    return Content.assemble(line.truncate(max(width - 1, 0)), current().marks.cut)
