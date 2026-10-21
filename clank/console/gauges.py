"""How the console draws numbers that move (the owner's request, 2026-10-14: the menu should be more dynamic): a bar
for a share of something, a sparkline for the last values, sizes and rates written briefly, and the spinner that turns
while something runs. Colors and glyphs are the style's (design 0011 §2): a bar is `$clank-low` below `BUSY`,
`$clank-busy` below `FULL` and `$clank-full` above (green, yellow and red in Clank's style), its empty cells
`$clank-border`, and a sparkline `$clank-data-1`; the spinner's frames, a bar's cells, a sparkline's steps and the mark
of cut text are read from the style in force (`current()`), so a style or `console.tcss` changes them all.
"""

from collections.abc import Sequence

from textual.content import Content

from clank.console.style import current
from clank.money import size as size  # sizes are written as the service writes them

BUSY = 0.6
FULL = 0.85


def spinner(frame: int) -> str:
    """The spinner's glyph for an animation frame."""
    frames = current().spinner
    return frames[frame % len(frames)]


def level(share: float) -> str:
    """The color of a share of something used (0 to 1): the style's `low`, `busy` when busy, `full` when nearly full."""
    if share >= FULL:
        return "$clank-full"
    return "$clank-busy" if share >= BUSY else "$clank-low"


def bar(share: float, width: int) -> Content:
    """A bar `width` cells wide, filled to `share` (0 to 1) in eighths of a cell, colored by `level`."""
    share = min(max(share, 0.0), 1.0)
    eighths = round(share * width * 8)
    whole, part = divmod(eighths, 8)
    cells = current().bar
    filled = cells.full * whole + (cells.eighths[part] if part and whole < width else "")
    empty = cells.empty * max(width - len(filled), 0)
    return Content.assemble((filled, level(share)), (empty, "$clank-border"))


def spark(values: Sequence[float], width: int, top: float = 100.0, style: str = "$clank-data-1") -> Content:
    """The last `width` values as a sparkline, each a cell from the style's lowest step (none) to its highest (`top`),
    padded on the left when there are fewer values than cells."""
    shown = list(values)[-width:] if width > 0 else []
    sparks = current().sparks
    cells = "".join(sparks[min(int(value / top * (len(sparks) - 1) + 0.5), len(sparks) - 1)] for value in shown)
    return Content.assemble(" " * (width - len(cells)), (cells, style))


def tall_spark(
    values: Sequence[float], width: int, top: float = 100.0, style: str = "$clank-data-1"
) -> tuple[Content, Content]:
    """The last `width` values as a graph two cells tall (its upper row, then its lower), twice a sparkline's steps; a
    value of nothing keeps the lowest step, so the graph's floor shows."""
    shown = list(values)[-width:] if width > 0 else []
    sparks = current().sparks
    steps = len(sparks) * 2
    upper, lower = [], []
    for value in shown:
        step = max(min(int(value / top * steps + 0.5), steps), 1) if top > 0 else 1
        lower.append(sparks[min(step, len(sparks)) - 1])
        upper.append(sparks[step - len(sparks) - 1] if step > len(sparks) else " ")
    pad = " " * (width - len(shown))
    return Content.assemble(pad, ("".join(upper), style)), Content.assemble(pad, ("".join(lower), style))


def rate(per_second: float) -> str:
    """Bytes a second, briefly: 0 B/s, 40 KB/s, 1.2 MB/s."""
    return f"{size(per_second)}/s"


def fit(text: str, width: int) -> str:
    """Text cut to `width` cells, ending in the style's mark of cut text (…) when it was cut."""
    return text if len(text) <= width else text[: max(width - 1, 0)] + current().marks.cut
