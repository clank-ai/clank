"""Read Markdown the way GitHub does, as far as the checks need: which lines are prose, and which are code.

A fenced code block opens with three or more backticks or tildes and closes with a line of the same character, at
least as long, and nothing after it; its lines and its fences are code. A fence may be indented however deep, as one
inside a list item is. Indented code blocks are not recognized, because nested list items in these documents are
indented the same way.
"""

import re

OPENING = re.compile(r"^\s*(`{3,}|~{3,})")
CLOSING = re.compile(r"^\s*(`{3,}|~{3,})\s*$")


def prose_lines(text: str) -> list[tuple[int, str]]:
    """The lines of `text` outside fenced code blocks, with their line numbers (from 1)."""
    lines: list[tuple[int, str]] = []
    fence = ""
    for number, line in enumerate(text.splitlines(), start=1):
        if fence:
            closing = CLOSING.match(line)
            if closing and closing.group(1)[0] == fence[0] and len(closing.group(1)) >= len(fence):
                fence = ""
            continue
        if opening := OPENING.match(line):
            fence = opening.group(1)
            continue
        lines.append((number, line))
    return lines
