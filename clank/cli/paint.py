"""Color in the terminal, for the commands that print for people (`clank setup` first): each kind of word has its
color, and the words never depend on it. click drops the color where the output is not a terminal (a pipe, a file, a
test's runner); `NO_COLOR` set to anything drops it everywhere (no-color.org)."""

import os
from collections.abc import Sequence

import click

BRAND = 215  # Clank's orange, in the terminal's 256 colors (#ff9e64 in the console's palette)
STYLES: dict[str, dict[str, object]] = {  # the color of each kind of word
    "brand": {"fg": BRAND, "bold": True},
    "title": {"bold": True},
    "good": {"fg": "green", "bold": True},
    "todo": {"fg": "yellow", "bold": True},
    "doing": {"fg": "cyan", "bold": True},
    "quiet": {"fg": "bright_black"},
    "optional": {"fg": "blue", "bold": True},
    "bad": {"fg": "red", "bold": True},
    "fix": {"fg": "cyan"},
    "command": {"bold": True},
}


def paint(text: str, kind: str) -> str:
    """`text` in its kind's color; as it is when `NO_COLOR` is set."""
    if not text or os.environ.get("NO_COLOR"):
        return text
    return click.style(text, **STYLES[kind])  # type: ignore[arg-type]


def commands(lines: Sequence[str], kind: str = "") -> list[str]:
    """Lines whose commands (between backticks, even across a line's end) are bold, the rest in `kind`'s color."""
    found, open_tick = [], False
    for line in lines:
        parts, start = [], 0
        for index, char in enumerate(line):
            if char == "`":
                if open_tick:
                    parts.append(paint(line[start : index + 1], "command"))
                    start = index + 1
                else:
                    parts.append(paint(line[start:index], kind) if kind else line[start:index])
                    start = index
                open_tick = not open_tick
        rest = line[start:]
        parts.append(paint(rest, "command") if open_tick else (paint(rest, kind) if kind else rest))
        found.append("".join(parts))
    return found
