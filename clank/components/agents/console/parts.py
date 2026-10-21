"""The context's parts as the Monitor draws them (design 0012 §4.2, §4.7; §11 step 12): each part's color (the style's
`$clank-part-<kind>`, decision 0044) and short name, tokens written briefly, the window's bar by part, and the line that
says what each part holds; from the estimate the service made (`clank/components/agents/estimate.py`), never a number
of the console's own.

- **The bar by part** (`bar`): the room used, each part's cells in its color, shared out by its tokens (the largest
  remainder, so the cells add up to the room used), the last step's answer after them in the color the room used takes
  as it nears the line (`gauges.level`); then the room left to the compaction line, and the room kept beyond it. A part
  too small for a cell has none; the legend still says it. Without the estimate, the room used is one color, as before
  (`contextpanel.bar`).
- **The legend** (`legend`): "estimate:", then each part that holds any tokens, its swatch, its short name and its
  tokens, in the bar's order. Narrower than it needs, it gives up its smallest parts first, loop text last (what the
  owner looks for after a session went wrong), keeping the others in the bar's order, and says how many it left out
  ("+3 more"); a line that still does not fit is cut with the style's "…".
"""

from typing import Any

from textual.content import Content

from clank.console.gauges import level
from clank.console.style import current

SHORT = {
    "system": "system", "tools": "tools", "yours": "you", "text": "text", "thinking": "thinking", "calls": "calls",
    "results": "results", "loop": "loop",
}  # fmt: skip
SWATCH = "█"
SAID = "estimate: "


TONES = {
    "system": "$clank-part-system", "tools": "$clank-part-tools", "yours": "$clank-part-yours",
    "text": "$clank-part-text", "thinking": "$clank-part-thinking", "calls": "$clank-part-calls",
    "results": "$clank-part-results", "loop": "$clank-part-loop",
}  # fmt: skip


def tone(part: str) -> str:
    """A part's color: the style's element for it."""
    return TONES.get(part, "$clank-data-1")


def tokens(count: int | float | None) -> str:
    """Tokens, briefly: 812, 12.4K, 152K, 1.2M."""
    shown = int(count or 0)
    if shown < 1000:
        return str(shown)
    if shown < 100_000:
        return f"{shown / 1000:.1f}K"
    if shown < 1_000_000:
        return f"{shown / 1000:.0f}K"
    return f"{shown / 1_000_000:.1f}M"


def bar(totals: dict[str, Any], width: int) -> Content:
    """The window as a bar (module docstring): the room used by part, the room left to the line, the room kept."""
    cells = current().bar
    window, line, used = int(totals["window"]), int(totals["line"]), int(totals.get("used") or 0)
    to_line = max(min(round(line / window * width), width), 0)
    filled = min(round(used / window * width), to_line) if used else 0
    color = level(used / line) if line else "$clank-low"
    found = totals.get("parts") or {}
    parts = [(str(part["part"]), int(part["tokens"])) for part in found.get("parts") or []]
    answer = int(totals.get("answer") or 0)
    shares = _cells([*parts, ("", answer)], filled) if parts and used else [("", filled)]
    drawn = [(cells.full * count, tone(part) if part else color) for part, count in shares if count]
    return Content.assemble(
        *drawn, (cells.empty * (to_line - filled), "$clank-border"), (cells.kept * (width - to_line), "$clank-quiet")
    )


def _cells(shares: list[tuple[str, int]], filled: int) -> list[tuple[str, int]]:
    """`filled` cells shared out by the tokens given, adding up to it (the largest remainder)."""
    total = sum(count for _, count in shares)
    if total <= 0:
        return [("", filled)]
    exact = [count * filled / total for _, count in shares]
    whole = [int(value) for value in exact]
    order = sorted(range(len(shares)), key=lambda index: exact[index] - whole[index], reverse=True)
    for index in order[: filled - sum(whole)]:
        whole[index] += 1
    return [(name, whole[index]) for index, (name, _) in enumerate(shares)]


def legend(totals: dict[str, Any] | None, width: int) -> Content | None:
    """What each part holds, on one line no wider than `width` (module docstring); None without the estimate."""
    found = (totals or {}).get("parts") or {}
    parts = [part for part in found.get("parts") or [] if part.get("tokens")]
    if not parts:
        return None
    kept = list(parts)
    while True:
        left = len(parts) - len(kept)
        shown = _legend(kept, left)
        if shown.cell_length <= width or len(kept) <= 1:
            return shown if shown.cell_length <= width else _cut(shown, width)
        kept.remove(min(kept, key=lambda part: (part["part"] == "loop", part["tokens"])))


def _legend(parts: list[dict[str, Any]], left: int) -> Content:
    pieces: list[tuple[str, str] | str] = [(SAID, "$clank-quiet")]
    for index, part in enumerate(parts):
        if index:
            pieces.append((" · ", "$clank-quiet"))
        name = str(part["part"])
        pieces += [(SWATCH, tone(name)), f" {SHORT.get(name, name)} {tokens(part['tokens'])}"]
    if left:
        pieces.append((f" · +{left} more", "$clank-quiet"))
    return Content.assemble(*pieces)


def _cut(line: Content, width: int) -> Content:
    """A line cut to `width` cells, ending in the style's mark of cut text."""
    if line.cell_length <= width:
        return line
    return Content.assemble(line.truncate(max(width - 1, 0)), current().marks.cut)
