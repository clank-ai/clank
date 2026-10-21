"""The Monitor's flow laid out in lines (design 0012 §6.3, §6.5): `render(view, width, cursor, folds, subagents)`, a
pure function, as the machine column's parts are drawn, returning lines of styled text no wider than `width`.

The flow's tree (`flowtree.py`) is drawn as board A draws it: time runs down, and the branches open to the right of
their node, joined by the style's tree glyphs in the `dim` color: `─┬─` where a node's children begin, `├─` and `└─`
for the next and the last, `│` down the column between them, so every junction of one node's children stands in one
column; a planned child is reached by the line not taken yet (`├┄`). Where what is left to the right of a node is
narrower than `CHILD_ROOM` columns, its children stand under it instead, a level in by three columns (`├─` under its
first cell), and under `STACK_BELOW` columns every node's children do (design 0012 §2: "under about 70 columns the flow
stacks its branches too"); what a band folds always stands under it, since a band runs across the flow. Beside its
children, a node takes at most `WORDS_SHARE` of the room and `WORDS_MOST` columns; when that cuts its words, its
children stand beside it only if it keeps `CUT_LEAST` columns (a long title cut reads well, a short label cut does
not), else under it.

Nothing spills (decision 0045): a node's line holds its mark, its words, the fold's arrow (▸) when it is folded, its
detail in `quiet` and the dead end's mark; when they do not fit, the detail goes first, then the arrow and the end, and
the words are cut with the style's cut mark; its whole text is one key away (its details). A group's calls (made at
once, a run, tries) line their details up in one column when there is room (board A's sizes). A compaction's band runs
across the rest of the line while it is folded. When the room under a node is too narrow for any child (`ROOM_LEAST`),
its children are left out and the node says so with its arrow (`Drawn.short`).

The node under the cursor is drawn on the `selection` color, its words in `selected-text`: the node `cursor`, or the
fold that hides it, or now when it is gone; with `follow`, now (`Drawn.cursor` says which). Which node that is comes
from the tree's folds before the layout, so a flow is laid out once, the cursor following now or not (laid out again
only when the layout left that node out for lack of room). `Drawn` says, for each line,
which node stands in which cells (`spans`), the nodes in reading order (`order`: each line from the top, each line from
the left, so a node comes before its children and a branch's work in time order), each node's line (`row`), its parent
(`parent`, every node's, drawn or not), and the newest node drawn (`now`: the flow's newest, or the fold that hides
it); `keys` lets the panel tell which lines changed.
"""

from dataclasses import dataclass, field
from datetime import tzinfo
from typing import Any

from rich.cells import cell_len, get_character_cell_size
from textual.content import Content

from clank.components.agents.console.flowtree import DIM, FAILED, QUIET, Node, tree
from clank.console.style import current

STACK_BELOW = 70  # columns: narrower, every node's children stand under it
CHILD_ROOM = 24  # columns a node's children need beside it; with less, they stand under it
WORDS_LEAST = 12  # columns a node beside its children may take at least, however narrow the share
WORDS_SHARE = 0.5  # of the room, at most, a node's own cells take when its children stand beside it
WORDS_MOST = 40  # columns, at most, a node's own cells take when its children stand beside it
CUT_LEAST = 24  # columns a node's cells keep when they are cut so its children stand beside it; else they stand under
ALIGNED = ("together", "run", "tries")  # the groups whose calls line their sizes up
ROOM_LEAST = 6  # columns a node needs to be drawn under its parent at all
DETAIL_GAP = 2  # columns between a node's words and its detail
HIGHLIGHT = "bold $clank-selected-text on $clank-selection"

Piece = tuple[str, str, str]  # its text, its style, the node it belongs to ("" for a line)


@dataclass(frozen=True)
class Span:
    """The cells of a line one node (or one run of line) stands in: from `start` up to `end`."""

    start: int
    end: int
    id: str  # the node's, "" for a line


@dataclass
class Drawn:
    """A flow laid out: its lines, what stands where, and how to move in it."""

    lines: list[Content] = field(default_factory=list)
    spans: list[list[Span]] = field(default_factory=list)
    keys: list[tuple[tuple[str, str], ...]] = field(default_factory=list)
    order: list[str] = field(default_factory=list)
    row: dict[str, int] = field(default_factory=dict)
    parent: dict[str, str] = field(default_factory=dict)
    nodes: dict[str, Node] = field(default_factory=dict)
    now: str = ""
    cursor: str = ""  # the node lit ("" for none)
    short: set[str] = field(default_factory=set)

    def shown(self, id: str) -> str:
        """The node drawn for this one: itself, or the nearest fold that hides it ("" when none is drawn)."""
        while id and id not in self.row:
            id = self.parent.get(id, "")
        return id


def render(
    view: dict[str, Any] | None,
    width: int,
    cursor: str = "",
    folds: dict[str, bool] | None = None,
    subagents: dict[str, dict[str, Any]] | None = None,
    *,
    follow: bool = False,
    zone: tzinfo | None = None,
) -> Drawn:
    """The flow laid out in lines no wider than `width`, one node lit: with `follow`, now; else the node `cursor`, the
    fold that hides it, or now when it is gone from the flow; none when no cursor is given. Laid out once (again only
    when the layout left the node worked out from the folds out for lack of room)."""
    if not view or width < 1:
        return Drawn()
    root = tree(view, folds, subagents, zone)
    index = Drawn()
    _index(root, "", index)
    wanted = _hiding(cursor, index) if cursor and not follow else ""
    if follow or (cursor and not wanted):
        wanted = _hiding(root.now, index)
    drawn = _laid(root, width, wanted, index)
    lit = drawn.now if follow else (drawn.shown(cursor) or drawn.now) if cursor else ""
    if lit != wanted:
        drawn = _laid(root, width, lit, index)
    drawn.cursor = lit
    return drawn


def _laid(root: Node, width: int, lit: str, index: Drawn) -> Drawn:
    """The tree laid out, the node `lit` highlighted; its nodes and parents those of `index`."""
    drawn = Drawn(nodes=index.nodes, parent=index.parent)
    painter = _Painter(lit, width < STACK_BELOW, drawn)
    for pieces in painter.block(root, width):
        _line(pieces, drawn)
    drawn.now = drawn.shown(root.now) or (drawn.order[-1] if drawn.order else "")
    return drawn


def _hiding(id: str, index: Drawn) -> str:
    """The node drawn for this one by the folds alone: itself, or the outermost folded node above it ("" when it is
    not in the tree)."""
    if id not in index.nodes:
        return ""
    shown, above = id, index.parent.get(id, "")
    while above:
        if index.nodes[above].folded:
            shown = above
        above = index.parent.get(above, "")
    return shown


def plain(drawn: Drawn) -> str:
    """The lines as text, for snapshots and for reading."""
    return "\n".join(line.plain for line in drawn.lines)


def cut(text: str, room: int) -> str:
    """Text cut to `room` cells, ending in the style's cut mark when it was cut."""
    if cell_len(text) <= room:
        return text
    if room <= 0:
        return ""
    mark = current().marks.cut
    kept, used = [], cell_len(mark)
    for each in text:
        size = get_character_cell_size(each)
        if used + size > room:
            break
        kept.append(each)
        used += size
    return "".join(kept) + mark


def _index(node: Node, parent: str, drawn: Drawn) -> None:
    drawn.nodes[node.id] = node
    if parent:
        drawn.parent[node.id] = parent
    for child in node.children:
        _index(child, node.id, drawn)


def _line(pieces: list[Piece], drawn: Drawn) -> None:
    """One line: its content, its spans (a node's pieces merged into one span), its key; the nodes on it in order."""
    spans: list[Span] = []
    at = 0
    for text, _, id in pieces:
        size = cell_len(text)
        if size and spans and spans[-1].id == id and spans[-1].end == at:
            spans[-1] = Span(spans[-1].start, at + size, id)
        elif size:
            spans.append(Span(at, at + size, id))
        at += size
    row = len(drawn.lines)
    for span in spans:
        if span.id and span.id not in drawn.row:
            drawn.row[span.id] = row
            drawn.order.append(span.id)
    shown = tuple((text, style) for text, style, _ in pieces if text)
    drawn.lines.append(Content.assemble(*((text, style) if style else text for text, style in shown)))
    drawn.spans.append(spans)
    drawn.keys.append(shown)


class _Painter:
    """Lays a tree out: each node's block of lines, its children beside it or under it."""

    def __init__(self, cursor: str, stacked: bool, drawn: Drawn) -> None:
        self.cursor, self.stacked, self.drawn = cursor, stacked, drawn
        self.glyphs = current().tree

    def block(self, node: Node, room: int, pad: int = 0) -> list[list[Piece]]:
        """A node's lines, each at most `room` cells wide: the node, then its children beside or under it."""
        kids = [] if node.folded else node.children
        if not kids:
            return [self.label(node, room, pad)]
        if room - 3 < ROOM_LEAST:
            self.drawn.short.add(node.id)
            return [self.label(node, room, short=True)]
        if not self.stacked and node.kind != "band":  # a band runs across the flow: what it folds stands under it
            whole = sum(cell_len(text) for text, _, _ in self.label(node, room))
            words = min(whole, room - 5 - CHILD_ROOM, max(min(int(room * WORDS_SHARE), WORDS_MOST), WORDS_LEAST))
            if (words >= 1 and whole <= words) or words >= CUT_LEAST:
                return self.beside(node, kids, room, words)
        return self.under(node, kids, room)

    def beside(self, node: Node, kids: list[Node], room: int, words: int) -> list[list[Piece]]:
        """Its children to its right: `─┬─` after it, `├─` and `└─` in the junction's column below."""
        head = self.label(node, words)
        width = sum(cell_len(text) for text, _, _ in head)
        inside = room - width - 5
        pads = _pads(node, kids, inside)
        lines: list[list[Piece]] = []
        glyphs = self.glyphs
        for index, kid in enumerate(kids):
            last = index == len(kids) - 1
            lead = glyphs.not_yet if kid.line == "not yet" else glyphs.across
            for row, line in enumerate(self.block(kid, inside, pads.get(kid.id, 0))):
                if index == 0 and row == 0:
                    split = glyphs.split if len(kids) > 1 else glyphs.across
                    prefix = [*head, (f" {glyphs.across}{split}{lead} ", DIM, "")]
                elif row == 0:
                    joint = glyphs.last if last else glyphs.branch
                    prefix = [(" " * (width + 2), "", ""), (f"{joint}{lead} ", DIM, "")]
                else:
                    prefix = [(" " * (width + 2), "", ""), (f"{' ' if last else glyphs.down}  ", DIM, "")]
                lines.append(prefix + line)
        return lines

    def under(self, node: Node, kids: list[Node], room: int) -> list[list[Piece]]:
        """Its children under it, a level in: `├─` and `└─` under its first cell, `│` down between them."""
        lines = [self.label(node, room)]
        inside = room - 3
        pads = _pads(node, kids, inside)
        glyphs = self.glyphs
        for index, kid in enumerate(kids):
            last = index == len(kids) - 1
            lead = glyphs.not_yet if kid.line == "not yet" else glyphs.across
            for row, line in enumerate(self.block(kid, inside, pads.get(kid.id, 0))):
                if row == 0:
                    prefix = f"{glyphs.last if last else glyphs.branch}{lead} "
                else:
                    prefix = f"{' ' if last else glyphs.down}  "
                lines.append([(prefix, DIM, ""), *line])
        return lines

    def label(self, node: Node, room: int, pad: int = 0, *, short: bool = False) -> list[Piece]:
        """A node's own cells, at most `room` wide: its mark, its words (padded to `pad`), its arrow when folded or
        cut short, its detail and its end; the detail goes first, then the arrow and the end, then the words are cut."""
        glyphs, id = self.glyphs, node.id
        lit = id == self.cursor
        words_style = HIGHLIGHT if lit else node.tone
        mark = (f"{node.mark} ", f"{node.mark_tone or node.tone}{' on $clank-selection' if lit else ''}", id)
        arrow = (f" {glyphs.arrow}", QUIET, id)
        detail = (" " * DETAIL_GAP + node.detail, node.detail_tone, id)
        end = (f" {node.end}", FAILED, id)
        band = node.kind == "band"
        parts = {
            "mark": mark if node.mark else None,
            "lead": (f"{glyphs.across * 2} ", DIM, id) if band else None,
            "arrow": arrow if node.folded or short else None,
            "detail": detail if node.detail else None,
            "end": end if node.end else None,
        }
        for drop in ("detail", "arrow", "end", "lead", "mark"):  # what goes first when the room is short
            fixed = sum(cell_len(part[0]) for part in parts.values() if part is not None)
            if fixed + min(cell_len(node.words), 1) <= room:
                break
            parts[drop] = None
        fixed = sum(cell_len(part[0]) for part in parts.values() if part is not None)
        if parts["detail"] is not None and fixed + cell_len(node.words) > room:
            parts["detail"] = None
            fixed = sum(cell_len(part[0]) for part in parts.values() if part is not None)
        words = cut(node.words, room - fixed)
        if pad and parts["detail"] is not None:  # line the details of leaves side by side up
            target = pad - (cell_len(parts["mark"][0]) if parts["mark"] is not None else 0)
            if cell_len(words) < target and fixed + target <= room:
                words += " " * (target - cell_len(words))
        pieces = [part for part in (parts["lead"], parts["mark"]) if part is not None]
        pieces.append((words, words_style, id))
        pieces += [part for part in (parts["arrow"], parts["detail"], parts["end"]) if part is not None]
        if band and (node.folded or not node.children):
            used = sum(cell_len(text) for text, _, _ in pieces)
            if room - used >= 2:
                pieces.append((" " + glyphs.across * (room - used - 1), DIM, id))
        return pieces


def _words(node: Node) -> str:
    """A node's own text, whole: its mark and its words, as `label` draws them before anything is cut."""
    return f"{node.mark} {node.words}" if node.mark else node.words


def _pads(node: Node, kids: list[Node], room: int) -> dict[str, int]:
    """For a group's calls (calls made at once, a run, tries): the width their mark and words are padded to, so their
    details line up in one column (board A's sizes), when every one fits with its detail."""
    if node.kind not in ALIGNED:
        return {}
    leaves = [kid for kid in kids if kid.detail and not kid.children]
    if len(leaves) < 2:
        return {}
    pad = max(cell_len(_words(kid)) for kid in leaves)
    fits = all(pad + DETAIL_GAP + cell_len(kid.detail) + (2 if kid.end else 0) <= room for kid in leaves)
    return {kid.id: pad for kid in leaves} if fits else {}
