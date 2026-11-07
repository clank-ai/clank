"""Lines of text whose wrapped part goes on under its value (design 0011 §5, a name and its value): for a page that
writes its rows as lines of text ("  account   key …") rather than in `Rows`, so that a value too long for its panel
wraps under itself, never back under its name, at whatever width the panel has.

Each line is read for its value's column: after its indent, a name of at most `NAME_AT_MOST` columns, then a gap of two
spaces or more (as the pages write their names, `f"  {name:<8}  {value}"`); the value starts there. A line with no
such name (a sentence, a question's words) goes on under its own start, and a heading (no indent) at the panel's edge,
as prose does. When the value's column would leave less than `VALUE_AT_LEAST` columns, the line goes on under its own
start instead, as `Rows` stacks a name above its value; so does a line holding a word longer than the value's column (a
file's source, `repository@revision`), so that the word stays whole. Each word keeps its colors: the line is cut at its
spaces, its styles with it.
"""

import re

from textual.content import Content
from textual.css.styles import RulesMap
from textual.strip import Strip
from textual.style import Style
from textual.visual import RenderOptions, Visual

NAME_AT_MOST = 24  # columns: a longer run of words before a double space is a sentence, not a name
VALUE_AT_LEAST = 16  # columns: a narrower value's column goes on under the line's start instead
NAMED = re.compile(r"( *)(\S(?:.*?\S)?)( {2,})(?=\S)")


def hang_of(line: str, width: int) -> int:
    """How far in a wrapped line of this text goes on: under its value, or under its own start."""
    indent = len(line) - len(line.lstrip(" "))
    found = NAMED.match(line)
    hang = found.end() if found and len(found.group(2)) <= NAME_AT_MOST else indent
    if width - hang < VALUE_AT_LEAST:
        hang = indent if width - indent >= VALUE_AT_LEAST else 0
    longest = max((len(word) for word in line[hang:].split()), default=0)
    if longest > width - hang:  # a word the value's column cannot hold: whole under the line's start, if that can
        hang = indent if longest <= width - indent else 0 if longest <= width else hang
    return hang


def cuts(line: str, width: int, hang: int) -> list[tuple[int, int]]:
    """Where each shown line of this text starts and ends: cut at a space where one is, else within a word."""
    pieces = []
    start, room = 0, width
    while len(line) - start > room:
        words_from = start + (len(line[start:]) - len(line[start:].lstrip(" ")))
        space = line.rfind(" ", words_from + 1, start + room + 1)
        word = line[space:].lstrip(" ").split(" ", 1)[0] if space != -1 else ""
        if space == -1 or len(word) > width - hang:
            end = after = start + room  # a word no line could hold: this line filled with its start
        else:
            end = space
            while end > start and line[end - 1] == " ":
                end -= 1
            after = space
            while after < len(line) and line[after] == " ":
                after += 1
        pieces.append((start, end))
        start, room = after, width - hang
    pieces.append((start, len(line)))
    return pieces


def hanging(content: Content, width: int) -> Content:
    """The text as a panel this wide shows it: each line that does not fit cut at its spaces, its wrapped part under
    its value (or its own start)."""
    shown = []
    for line in content.split("\n", allow_blank=True):
        plain = line.plain
        if len(plain) <= width or width < 1:
            shown.append(line)
            continue
        hang = hang_of(plain, width)
        for number, (start, end) in enumerate(cuts(plain, width, hang)):
            piece = line[start:end]
            shown.append(piece if number == 0 else Content(" " * hang) + piece)
    return Content("\n").join(shown)


class Hanging(Visual):
    """Text whose lines wrap under their values, for a `Label` (`label.update(Hanging(text))`)."""

    def __init__(self, text: str | Content) -> None:
        self.content = Content(text) if isinstance(text, str) else text
        self._shown: tuple[int, Content] | None = None

    def __str__(self) -> str:
        """Its words, as the text's own (what a test or a search reads of a label)."""
        return self.content.plain

    def shown(self, width: int) -> Content:
        """The text as this width shows it, kept for the next call at the same width."""
        if self._shown is None or self._shown[0] != width:
            self._shown = (width, hanging(self.content, width))
        return self._shown[1]

    def render_strips(self, width: int, height: int | None, style: Style, options: RenderOptions) -> list[Strip]:
        """The lines, drawn as the text they are at this width."""
        return self.shown(width).render_strips(width, height, style, options)

    def get_optimal_width(self, rules: RulesMap, container_width: int) -> int:
        """As wide as its longest line, as the text's own."""
        return self.content.get_optimal_width(rules, container_width)

    def get_minimal_width(self, rules: RulesMap) -> int:
        """As narrow as the text's own."""
        return self.content.get_minimal_width(rules)

    def get_height(self, rules: RulesMap, width: int) -> int:
        """As tall as its lines at this width."""
        return self.shown(width).get_height(rules, width)
