"""A flow laid out for the Monitor's Flow view (design 0013 §12, board D1; decision 0057's shape): `render(view, width,
selected, live, zone)`, a pure function of what the service says of the flow (`GET /flows/view`), returning lines of
styled text no wider than `width`, as `flowchart.py` lays a session's flow out.

**Stages in rows.** A flow is a chain of boxes with two exceptions (design 0013 §3): a VERIFY's fail line back, and a
DECOMPOSE's tasks, which fan out from it and join at the box after them. So the flow is a list of **stages** (`stages`):
one box, or a DECOMPOSE's tasks stacked one above the other. The stages read left to right as board D1's first row
does, as many to a row as keep a box `BOX_LEAST` columns wide, and wrap to the next row as board D1 wraps its flow: a
line from the row's last stage down, back along a row of its own, and down into the next row's first (`▾`). A DECOMPOSE
and its fan stand in one row; the box they join at may begin the next, the fan's join line running down to the wrap.
Each row keeps `GAP` columns after its last stage for that line, so no row is ever wider than the chart.

**A box** is `BOX_ROWS` rows: its border, its tag (its type in the style's `boxes` color, a task's id, its tries when
it ran more than once) with its state at the right, its title, its model (and its speed while it runs), and its
deliverable or last result (a verdict, an approval, the tasks it proposed), each cut with the style's "…"; the whole is
one key away (Selected, `?`). Its border says its state: solid when done, heavier in the `now` color while it runs (in
`attention` while it asks the owner), dashed in `dim` while it waits, solid in `failed`, solid in `attention` when stale
or changed, dashed in the proposals' color (the DECOMPOSE color) while proposed. The box selected is drawn on the
`selection` color, its title in `selected-text`. The next flow (design 0013 §3) is a dashed box after the last gate.

**Lines** carry the state the service gives each (`ran`, `now`, `not yet`, `failed`): a then line that ran in `dim`, a
pass line that ran in `good`, the path being run in `now`, what has not run dashed (the style's `not_yet`), a fail line
taken in `failed`. A fan's shared trunk takes, between two tasks, the most active state of the lines it carries. A
VERIFY's fail line runs under its row, from the VERIFY's bottom back up into the box it checks (`▴`), its label set in
it ("fail ⟲ back with 3 findings · 2 of 3 tries"); when that box is not in the VERIFY's row, is part of a fan, or a line
there would cross another, a label alone says it, on a row of its own under the VERIFY's row. Every fail line has a row
of its own, so no label lies on a box or on another label. The legend follows the flow, wrapped by items.

Narrower than `LIST_BELOW` columns the flow is the list of board D2's left (`listed`): a line a box, a DECOMPOSE's
tasks indented under it. `Chart` says what stands where (each box's rectangle, each label's and legend item's cells),
the boxes in reading order (by row, then stage, then down a fan) and each line's key, so the panel draws again only the
lines that changed (design 0001 §5.7). The boxes and lines are drawn in box-drawing characters of the chart's own,
their corners the style's border kind; arrows and dashes are the style's tree glyphs, every color a style element.
"""

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import tzinfo
from typing import Any

from rich.cells import cell_len, get_character_cell_size
from textual.content import Content

from clank.components.agents.console.flowchart import cut
from clank.console.style import current, mark
from clank.console.text import clock, parse

LIST_BELOW = 70  # columns: narrower, the flow is a list (design 0013 §12)
GAP = 3  # columns between two stages: the line, its junction, its arrow
BOX_LEAST = 22  # columns a small box keeps at least; a row holds as many as keep it
BOX_MOST = 30  # columns a small box takes at most
BOX_ROWS = 6  # a small box's rows: its border, its tag, title, model and last result


@dataclass(frozen=True)
class Size:
    """A size of box: the columns it keeps at least (a row holds as many as keep it) and takes at most, its rows, its
    title's lines, and what it says besides (`tries`: its tries, time and tokens; `writes`: the files it writes)."""

    least: int
    most: int
    rows: int
    title_lines: int
    details: tuple[str, ...] = ()


SIZES = {  # the owner's request (2026-10-22): boxes "a bit more fleshed out" on a wide screen; `+` and `-` pick one
    "small": Size(BOX_LEAST, BOX_MOST, BOX_ROWS, 1),
    "medium": Size(32, 44, 8, 2, ("tries",)),
    "large": Size(44, 64, 10, 3, ("tries", "writes")),
}
FAN_GAP = 1  # rows between two tasks of a fan
TAGS = {"you": "YOU", "plan": "PLAN", "verify": "VERIFY", "decompose": "DECOMPOSE", "task": "TASK",
        "integrate": "INTEGRATE", "gate": "GATE"}  # fmt: skip
TONES = {  # each type's color: the style's `boxes` group
    "you": "$clank-box-you", "plan": "$clank-box-plan", "verify": "$clank-box-verify",
    "decompose": "$clank-box-decompose", "task": "$clank-box-task", "integrate": "$clank-box-integrate",
    "gate": "$clank-box-gate",
}  # fmt: skip
NEXT = "next-flow"  # the next flow's box, in `Chart.boxes`
RANK = {"now": 3, "failed": 2, "ran": 1, "not yet": 0}
LIST_INDENT = 3
ACTIVE_LINE = "now"

Cell = tuple[str, str]  # its character ("" for the second cell of a wide one), its style


@dataclass(frozen=True)
class Rect:
    """The cells a box stands in."""

    x: int
    y: int
    w: int
    h: int


@dataclass
class Chart:
    """A flow laid out: its lines, what stands where, and the boxes in reading order."""

    width: int
    lines: list[Content] = field(default_factory=list)
    keys: list[tuple[tuple[str, str], ...]] = field(default_factory=list)
    cells: list[list[Cell]] = field(default_factory=list)
    boxes: dict[str, Rect] = field(default_factory=dict)
    labels: list[tuple[int, int, int]] = field(default_factory=list)  # each label's line, first cell and end
    legend: list[tuple[int, int, int]] = field(default_factory=list)  # each legend item's line, first cell and end
    order: list[str] = field(default_factory=list)
    listed: bool = False
    box_rows: int = BOX_ROWS

    def style_at(self, x: int, y: int) -> str:
        """The style of a cell ("" for none)."""
        row = self.cells[y] if 0 <= y < len(self.cells) else []
        return row[x][1] if 0 <= x < len(row) else ""


class Canvas:
    """Cells, a line at a time, never wider than the chart: what would pass its right edge is not put."""

    def __init__(self, width: int) -> None:
        self.width = width
        self.rows: list[list[Cell]] = []

    def put(self, x: int, y: int, text: str, style: str) -> int:
        """Put text from the cell `x` of the line `y`; the cell after it."""
        while len(self.rows) <= y:
            self.rows.append([])
        row = self.rows[y]
        for character in text:
            size = get_character_cell_size(character)
            if x < 0 or x + size > self.width:
                break
            while len(row) < x + size:
                row.append((" ", ""))
            row[x] = (character, style)
            if size == 2:
                row[x + 1] = ("", style)
            x += size
        return x

    def chart(self, chart: Chart) -> Chart:
        """The cells as lines of styled text, trailing blanks left out, and each line's key."""
        for row in self.rows:
            while row and row[-1] == (" ", ""):
                row.pop()
            pieces: list[tuple[str, str]] = []
            for character, style in row:
                if not character:
                    continue
                if pieces and pieces[-1][1] == style:
                    pieces[-1] = (pieces[-1][0] + character, style)
                else:
                    pieces.append((character, style))
            chart.lines.append(Content.assemble(*((text, style) if style else text for text, style in pieces)))
            chart.keys.append(tuple(pieces))
            chart.cells.append(list(row))
        return chart


def stages(view: Mapping[str, Any]) -> list[list[str]]:
    """The flow's stages in the order they run: one box, or the tasks a DECOMPOSE fans out to (each leading on to the
    same box); a box no walk reaches stands alone at the end."""
    boxes = {box["id"]: box for box in view.get("boxes") or []}
    if not boxes:
        return []
    found: list[list[str]] = []
    placed: set[str] = set()
    current_ = [next(iter(boxes))]
    while current_:
        found.append(current_)
        placed.update(current_)
        after = [name for name in boxes[current_[0]]["next"] if name in boxes]
        if len(current_) > 1:  # a fan: the box its tasks join at
            joins = {name for task in current_ for name in boxes[task]["next"] if name in boxes}
            after = sorted(joins)[:1]
        if len(after) > 1:
            fan = [name for name in boxes if name in after and name not in placed]
            current_ = fan if fan else []
        elif after and after[0] not in placed:
            current_ = [after[0]]
        else:
            current_ = []
    found += [[name] for name in boxes if name not in placed]
    return found


def render(
    view: Mapping[str, Any] | None,
    width: int,
    selected: str = "",
    live: Mapping[str, Any] | None = None,
    zone: tzinfo | None = None,
    size: str = "small",
) -> Chart:
    """The flow laid out in lines no wider than `width`, the box `selected` lit, `live` (the running box's `step` and
    `speed`) in the running box, its boxes of a `size` of `SIZES`; the list below `LIST_BELOW` columns."""
    chart = Chart(width=max(width, 1))
    if not view or not view.get("boxes") or width < 1:
        return chart
    if width < LIST_BELOW:
        return _Listed(view, chart, selected, live or {}, zone).draw()
    return _Laid(view, chart, selected, live or {}, zone, fitting(size, chart.width)).draw()


def fitting(size: str, width: int) -> Size:
    """The size asked for, or the largest smaller one that keeps two boxes to a row at this width (a DECOMPOSE and its
    tasks stand side by side); small at the least."""
    names = list(SIZES)
    index = names.index(size) if size in names else 0
    while index > 0 and width // (SIZES[names[index]].least + GAP) < 2:
        index -= 1
    return SIZES[names[index]]


def listed(
    view: Mapping[str, Any] | None,
    width: int,
    selected: str = "",
    live: Mapping[str, Any] | None = None,
    zone: tzinfo | None = None,
    noted: Collection[str] = (),
) -> Chart:
    """The flow as the list of board D2's left at any width (board D3's "Where the flow is" too), the boxes `noted`
    marked as changed and not saved."""
    chart = Chart(width=max(width, 1))
    if not view or not view.get("boxes") or width < 1:
        return chart
    return _Listed(view, chart, selected, live or {}, zone, noted).draw()


def _glyphs(dashed: bool) -> dict[str, str]:
    tree = current().tree
    return {"across": tree.not_yet if dashed else tree.across, "down": "┆" if dashed else tree.down}


def corners(kind: str) -> str:
    """A box's corners and sides: top left, top right, bottom left, bottom right, across, down."""
    round_ = current().border == "round"
    if kind == "heavy":
        return "┏┓┗┛━┃"
    corners = "╭╮╰╯" if round_ else "┌┐└┘"
    return corners + ("┄┆" if kind == "dashed" else "─│")


def _line_style(state: str, passing: bool = False) -> str:
    if state == "now":
        return "$clank-now"
    if state == "failed":
        return "$clank-failed"
    if state == "ran":
        return "$clank-good" if passing else "$clank-dim"
    return "$clank-dim"


def _most(states: Sequence[str]) -> str:
    return max(states, key=lambda state: RANK.get(state, 0)) if states else "not yet"


def _border(box: Mapping[str, Any]) -> tuple[str, str]:
    """A box's border: its kind and its color, by its state."""
    state = box["state"]
    if state == "running":
        return "heavy", "$clank-attention" if box["type"] in ("you", "gate") else "$clank-now"
    if state == "failed":
        return "solid", "$clank-failed"
    if state in ("stale",) or box.get("changed"):
        return "solid", "$clank-attention"
    if state == "proposed":
        return "dashed", "$clank-box-decompose"
    if state in ("waiting", "skipped"):
        return "dashed", "$clank-dim"
    return "solid", "$clank-border"


def tag(box: Mapping[str, Any]) -> str:
    """A box's tag: its type, a task's id after it (`TASK T2`), a question mark while proposed."""
    said = TAGS.get(str(box["type"]), str(box["type"]).upper())
    if box["type"] == "task" or box["state"] == "proposed":
        said += f" {box['id']}"
    return said + ("?" if box["state"] == "proposed" else "")


def running_job(box: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The job a box's last try waits on, if any (design 0013 §17)."""
    tries = box.get("tries") or []
    jobs = (tries[-1].get("jobs") or []) if tries else []
    return next((each for each in jobs if not each.get("ended")), None)


def state_mark(box: Mapping[str, Any], live: Mapping[str, Any]) -> tuple[str, str]:
    """What a box's tag line says at its right: its state's mark (and a running box's step, or the job it waits on),
    and its color."""
    state = box["state"]
    if state == "running" and box["type"] in ("you", "gate"):
        return mark("on"), "$clank-attention"
    job = running_job(box) if state == "running" else None
    if job is not None:
        return f"{mark('on')} job {job['number']}", "$clank-now"
    if state == "running":
        step = live.get("step")
        return (f"{mark('on')} step {step}" if step else mark("on")), "$clank-now"
    if box.get("changed") and state == "done":
        return "changed", "$clank-attention"
    return {
        "done": (mark("done"), "$clank-good"),
        "failed": (mark("failed"), "$clank-failed"),
        "stale": ("stale", "$clank-attention"),
        "skipped": ("skipped", "$clank-quiet"),
        "proposed": ("proposed", "$clank-box-decompose"),
    }.get(state, (mark("off"), "$clank-quiet"))


def last_said(box: Mapping[str, Any], view: Mapping[str, Any], zone: tzinfo | None) -> str:
    """A box's last line: its deliverable, or what it last did (a verdict, an approval, the tasks it proposed)."""
    state, kind = box["state"], box["type"]
    when = clock(parse(box["ended"]), zone) if box.get("ended") else ""
    at = f" · {when}" if when else ""
    first = box["writes"][0] if box["writes"] else ""
    if state == "failed":
        return box.get("why") or "failed"
    if state == "stale":
        return f"stale: {box.get('why') or 'what it saw changed'}"
    if state == "skipped":
        return "skipped"
    if box.get("asks"):
        return "waits for you"
    if kind == "verify":
        given = [(each["number"], each["verdict"]) for each in box["tries"] if each.get("verdict")]
        if given:
            number, verdict = given[-1]
            return f"{verdict['result']}, try {number}{at}"
        return "a verdict: pass or findings"
    if kind == "gate":
        return f"approved{' ' + when if when else ''}" if state == "done" else "you decide"
    if kind == "decompose":
        waiting = len((view.get("proposals") or {}).get("waiting") or []) if _proposes(view, box) else 0
        if waiting:
            return f"{waiting} proposed"
        made = [each for each in view["boxes"] if (each.get("proposed") or {}).get("by") == box["id"]]
        return f"{len(made)} {'task' if len(made) == 1 else 'tasks'}{at}" if made else "proposes tasks"
    if state == "done":
        return f"{first}{at}" if first else f"done{at}"
    return first or ("your part" if kind == "you" else "")


def _proposes(view: Mapping[str, Any], box: Mapping[str, Any]) -> bool:
    proposals = view.get("proposals") or {}
    return bool(proposals.get("box") == box["id"])


def model_said(box: Mapping[str, Any], live: Mapping[str, Any]) -> str:
    """A box's model line: its preset (or you), after its speed while it runs."""
    if box["type"] in ("you", "gate"):
        return "you"
    said = str(box.get("preset_title") or "main slot's model")
    speed = live.get("speed")
    if box["state"] == "running" and isinstance(speed, int | float) and speed:
        return f"{speed:.0f} tok/s · {said}"  # the speed first: a narrow box cuts the preset's name
    return said


def wrapped_title(title: str, width: int, count: int) -> list[str]:
    """A box's title over `count` lines of `width` cells, the last cut with the style's "…" when it does not fit; as
    many lines as it takes, so a short title leaves the rest empty."""
    words, lines = title.split(), list[str]()
    while words and len(lines) < count - 1:
        line = ""
        while words and cell_len(f"{line} {words[0]}".strip()) <= width:
            line = f"{line} {words.pop(0)}".strip()
        if not line:  # a word longer than the line: cut on the last line
            break
        lines.append(line)
    if words:
        lines.append(cut(" ".join(words), width))
    while len(lines) < count:
        lines.append("")
    return lines


def details(box: Mapping[str, Any], wanted: Sequence[str], zone: tzinfo | None) -> list[str]:
    """What a larger box says besides: its tries, time and tokens (or what one try may use, before it ran); the files
    it writes, or the box a VERIFY checks."""
    said = []
    for each in wanted:
        if each == "tries":
            said.append(tries_said(box, zone))
        elif each == "writes":
            if box["type"] == "verify" and box.get("checks"):
                said.append(f"checks {box['checks']}")
            else:
                said.append(f"writes {', '.join(box['writes'])}" if box["writes"] else "")
    return said


def tries_said(box: Mapping[str, Any], zone: tzinfo | None) -> str:
    """A box's tries, time and tokens: "try 1 of 3 · 26 min · 48.3K tokens", "try 2 of 3 · since 23:45 · 12K tokens";
    before it ran, what one try may use; nothing for a box of yours."""
    if box["type"] in ("you", "gate"):
        return ""
    tries, cap, limits = box["tries"], box.get("cap"), box.get("limits") or {}
    if not tries:
        return f"up to {cap} {'try' if cap == 1 else 'tries'} · {limits.get('minutes', '?')} min each" if cap else ""
    last = tries[-1]
    started = parse(last["started"]) if last.get("started") else None
    ended = parse(last["ended"]) if last.get("ended") else None
    if started is not None and ended is not None:
        when = f"{max(int((ended - started).total_seconds() // 60), 0)} min"
    else:
        when = f"since {clock(started, zone)}" if started is not None else ""
    tokens = int(last.get("tokens") or 0)
    count = f"{tokens / 1000:.1f}K tokens" if tokens >= 1000 else f"{tokens} tokens"
    return " · ".join(part for part in (f"try {last['number']} of {cap}" if cap else "", when, count) if part)


class _Laid:
    """Lays a flow out in rows of stages."""

    def __init__(
        self,
        view: Mapping[str, Any],
        chart: Chart,
        selected: str,
        live: Mapping[str, Any],
        zone: tzinfo | None,
        size: Size,
    ) -> None:
        self.view, self.chart, self.selected, self.live, self.zone = view, chart, selected, live, zone
        self.canvas = Canvas(chart.width)
        self.boxes = {box["id"]: box for box in view["boxes"]}
        self.lines = {(line["from"], line["to"]): line for line in view.get("lines") or []}
        self.size, self.rows = size, size.rows
        chart.box_rows = size.rows
        self.per_row = max(1, chart.width // (size.least + GAP))
        self.box_w = min(size.most, (chart.width - self.per_row * GAP) // self.per_row)
        self.stages = stages(view)
        if view.get("next_flow"):
            self.stages.append([NEXT])

    def draw(self) -> Chart:
        rows = self._rows()
        y = 0
        for index, row in enumerate(rows):
            top = y
            height = max(self._height(stage) for stage in row)
            for column, stage in enumerate(row):
                self._stage(stage, column * (self.box_w + GAP), top)
                if column:
                    self._join(row[column - 1], stage, (column - 1) * (self.box_w + GAP), top)
            y = top + height
            y = self._loops(row, top, y, wraps=index + 1 < len(rows))
            if index + 1 < len(rows):
                y = self._wrap(row, rows[index + 1], top, y)
        self._legend(y + 1)
        self.chart.order = [name for row in rows for stage in row for name in stage]
        return self.canvas.chart(self.chart)

    def _rows(self) -> list[list[list[str]]]:
        """The stages in rows: as many to a row as fit, a DECOMPOSE with its fan in one row."""
        units: list[list[list[str]]] = []
        for stage in self.stages:
            if len(stage) > 1 and units and len(units[-1]) == 1 and self._type(units[-1][0][0]) == "decompose":
                units[-1].append(stage)
            else:
                units.append([stage])
        rows: list[list[list[str]]] = [[]]
        for unit in units:
            if rows[-1] and len(rows[-1]) + len(unit) > self.per_row:
                rows.append([])
            rows[-1].extend(unit)
        return [row for row in rows if row]

    def _type(self, name: str) -> str:
        return str(self.boxes[name]["type"]) if name in self.boxes else ""

    def _height(self, stage: list[str]) -> int:
        return len(stage) * self.rows + (len(stage) - 1) * FAN_GAP

    def _stage(self, stage: list[str], x: int, top: int) -> None:
        for index, name in enumerate(stage):
            self._box(name, Rect(x, top + index * (self.rows + FAN_GAP), self.box_w, self.rows))

    def _box(self, name: str, rect: Rect) -> None:
        self.chart.boxes[name] = rect
        lit = name == self.selected
        if name == NEXT:
            following = self.view["next_flow"]
            source = following.get("from") or ""
            source = f"brief from {tag(self.boxes[source])}" if source in self.boxes else ""
            lines = [
                [(f"{current().tree.arrow} next flow", "$clank-quiet")],
                [(cut(following.get("title") or "made when approved", rect.w - 3), "$clank-text")],
                [(cut(source, rect.w - 3), "$clank-quiet")],
            ]
            self._frame(rect, ("dashed", "$clank-quiet"), lines, lit=lit)
            return
        box = self.boxes[name]
        inner = rect.w - 3
        right, right_tone = state_mark(box, self.live)
        tries = len(box["tries"])
        left = tag(box) + (f" ⟲{tries}" if tries > 1 else "")
        for shorter in (right, right.replace(" step ", " "), right.split(" ")[0]):  # its step shortened, then left out
            right = shorter
            if cell_len(left) + 1 + cell_len(right) <= inner:
                break
        left = cut(left, max(inner - cell_len(right) - 1, 1))  # its type and tries kept whole while they fit
        pad = " " * max(inner - cell_len(left) - cell_len(right), 1)
        tone = TONES.get(str(box["type"]), "$clank-text")
        quiet = box["state"] == "skipped"
        title_tone = "bold $clank-selected-text" if lit else ("$clank-quiet" if quiet else "$clank-text")
        lines = [
            [(left, f"bold {tone}"), (pad, ""), (right, right_tone)],
            *([(line, title_tone)] for line in wrapped_title(box["title"], inner, self.size.title_lines)),
            [(cut(model_said(box, self.live), inner), "$clank-quiet")],
            [(cut(last_said(box, self.view, self.zone), inner), "$clank-quiet")],
            *([(cut(said, inner), "$clank-quiet")] for said in details(box, self.size.details, self.zone)),
        ]
        self._frame(rect, _border(box), lines, lit=lit)

    def _frame(self, rect: Rect, border: tuple[str, str], lines: list[list[tuple[str, str]]], *, lit: bool) -> None:
        """A box's border and its lines, one cell in from its left side; lit on the selection color."""
        kind, color = border
        sides = corners(kind)
        on = "on $clank-selection" if lit else ""
        canvas, x, y, w = self.canvas, rect.x, rect.y, rect.w
        canvas.put(x, y, sides[0] + sides[4] * (w - 2) + sides[1], color)
        for row in range(1, rect.h - 1):
            canvas.put(x, y + row, sides[5], color)
            canvas.put(x + 1, y + row, " " * (w - 2), on)
            at = x + 2
            for text, style in lines[row - 1] if row - 1 < len(lines) else []:
                at = canvas.put(at, y + row, text, f"{style} {on}".strip())
            canvas.put(x + w - 1, y + row, sides[5], color)
        canvas.put(x, y + rect.h - 1, sides[2] + sides[4] * (w - 2) + sides[3], color)

    def _line(self, source: str, target: str) -> tuple[str, bool]:
        """The state of the line from one box to another, and whether it is a pass line."""
        if target == NEXT:
            following = self.view.get("next_flow") or {}
            done = self.boxes[source]["state"] == "done" and following.get("id")
            return ("ran" if done else "not yet"), False
        line = self.lines.get((source, target))
        if line is None:
            return "not yet", False
        return str(line.get("state") or "not yet"), line.get("when") == "pass"

    def _ports(self, top: int, count: int) -> list[int]:
        """The lines a stage's boxes are joined at: each box's tag line."""
        return [top + index * (self.rows + FAN_GAP) + 1 for index in range(count)]

    def _join(self, before: list[str], stage: list[str], x: int, top: int) -> None:
        """The lines from one stage to the next in the row: across, a fan's split, or its join."""
        canvas = self.canvas
        c0 = x + self.box_w
        arrow = current().tree.arrow
        if len(before) == 1 and len(stage) == 1:
            state, passing = self._line(before[0], stage[0])
            across = _glyphs(state == "not yet")["across"]
            canvas.put(c0, self._ports(top, 1)[0], across * (GAP - 1) + arrow, _line_style(state, passing))
            return
        if len(before) == 1:  # a split: down the trunk, an arrow into each task
            states = [self._line(before[0], name)[0] for name in stage]
            ports = self._ports(top, len(stage))
            self._trunk(c0, ports, states, "split")
            for port, state in zip(ports, states, strict=True):
                canvas.put(c0 + 2, port, arrow, _line_style(state))
            return
        states = [self._line(name, stage[0])[0] for name in before]  # a join: into the trunk, up, on to the box
        self._trunk(c0, self._ports(top, len(before)), states, "join")
        canvas.put(c0 + 2, self._ports(top, 1)[0], arrow, _line_style(_most(states)))

    def _trunk(self, c0: int, ports: list[int], states: list[str], how: str, down_to: int = 0) -> None:
        """A fan's trunk, in the column after `c0`: its junction at each port and `│` between, each part in the most
        active state of the lines it carries. `split`: from the DECOMPOSE at the first port down to each task; `join`:
        from each task up to the first port and on; `down`: from each task down to the wrap at the line `down_to`."""
        canvas, trunk, last = self.canvas, c0 + 1, len(ports) - 1

        def put(column: int, row: int, glyph: str, carried: list[str]) -> None:
            state = _most(carried)
            if glyph in ("─", "│"):
                glyph = _glyphs(state == "not yet")["across" if glyph == "─" else "down"]
            canvas.put(column, row, glyph, _line_style(state))

        if how == "split":
            put(c0, ports[0], "─", states)
        for index, port in enumerate(ports):
            if how != "split":
                put(c0, port, "─", [states[index]])
            if how == "split":
                glyph, carried = ("┬" if index == 0 else "└" if index == last else "├"), states[index:]
                between = states[index + 1 :]
            elif how == "join":
                glyph, carried = ("┬" if index == 0 else "┘" if index == last else "┤"), states[index:]
                between = states[index + 1 :]
            else:
                glyph, carried = ("┐" if index == 0 else "┤"), states[: index + 1]
                between = states[: index + 1]
            put(trunk, port, glyph, states if (how == "join" and index == 0) else carried)
            below = ports[index + 1] if index < last else (down_to if how == "down" else port)
            for row in range(port + 1, below):
                put(trunk, row, "│", between)

    def _loops(self, row: list[list[str]], top: int, y: int, *, wraps: bool) -> int:
        """Each fail line of the row's VERIFYs, on a line of its own under the row: drawn back up into the box it
        checks and labeled, when that box is a box alone in the row and the line crosses none drawn before; else a
        label alone. The line after them."""
        singles = {stage[0]: index for index, stage in enumerate(row) if len(stage) == 1}
        fails = [
            line for line in self.view.get("lines") or [] if line.get("when") == "fail" and line["from"] in singles
        ]
        fails.sort(key=lambda line: singles[line["from"]] - singles.get(line["to"], -len(row)))
        step = self.box_w + GAP
        drawn: list[tuple[Mapping[str, Any], int, int]] = []
        alone: list[Mapping[str, Any]] = []
        for line in fails:
            verify, checked = line["from"], line["to"]
            if checked not in singles or singles[checked] >= singles[verify]:
                alone.append(line)
                continue
            into = singles[checked] * step + 2
            out = singles[verify] * step + self.box_w - 4
            crossing = any(start <= column <= end for _, start, end in drawn for column in (into, out))
            crossing = crossing or any(into <= column <= out for _, start, end in drawn for column in (start, end))
            if crossing:
                alone.append(line)
                continue
            drawn.append((line, into, out))
        canvas, bottom = self.canvas, top + self.rows - 1
        for band, (line, into, out) in enumerate(drawn, start=y):
            state = str(line.get("state") or "not yet")
            style, glyphs = _line_style(state), _glyphs(state == "not yet")
            canvas.put(into, bottom, "▴", style)
            canvas.put(out, bottom, "┬", style)
            for row_ in range(bottom + 1, band):
                canvas.put(into, row_, glyphs["down"], style)
                canvas.put(out, row_, glyphs["down"], style)
            canvas.put(into, band, "╰" + glyphs["across"] * (out - into - 1) + "╯", style)
            room = out - into - 3
            if room >= 4:
                said = cut(f" {_fail_words(line, self.boxes)} ", room)
                canvas.put(into + 2, band, said, style)
                self.chart.labels.append((band, into + 2, into + 2 + cell_len(said)))
        y += len(drawn)
        edge = self._exit(row) if wraps else self.chart.width + 1
        for line in alone:
            words = f"{self.boxes[line['from']]['title']}: {_fail_words(line, self.boxes, back=True)}"
            said = cut(words, max(edge - 1, 1))
            canvas.put(0, y, said, _line_style(str(line.get("state") or "not yet")))
            self.chart.labels.append((y, 0, cell_len(said)))
            y += 1
        return y

    def _exit(self, row: list[list[str]]) -> int:
        """The column a row's wrap leaves its last stage by: near a box's right side, or a fan's trunk."""
        x = (len(row) - 1) * (self.box_w + GAP)
        return x + self.box_w + 1 if len(row[-1]) > 1 else x + self.box_w - 2

    def _wrap(self, row: list[list[str]], following: list[list[str]], top: int, y: int) -> int:
        """The line from a row's last stage down, back along a line of its own, and down into the next row's first
        stage; the line after it."""
        last, first = row[-1], following[0]
        found = [self._line(name, first[0]) for name in last]
        state = _most([each for each, _ in found])
        style, glyphs = _line_style(state, any(passing for _, passing in found)), _glyphs(state == "not yet")
        canvas, out, into = self.canvas, self._exit(row), self.box_w // 2
        if len(last) > 1:  # the fan's join trunk, carried down to the wrap
            x = (len(row) - 1) * (self.box_w + GAP)
            self._trunk(x + self.box_w, self._ports(top, len(last)), [each for each, _ in found], "down", down_to=y)
        else:
            bottom = top + self.rows - 1
            canvas.put(out, bottom, "┬", style)
            for row_ in range(bottom + 1, y):
                canvas.put(out, row_, glyphs["down"], style)
        canvas.put(into, y, "╭" + glyphs["across"] * (out - into - 1) + "╯", style)
        canvas.put(into, y + 1, "▾", style)
        return y + 2

    def _legend(self, y: int) -> None:
        """The legend under the flow, wrapped by items (board D1's)."""
        tree = current().tree
        items = [
            [(mark("done"), "$clank-good"), (" done", "$clank-quiet")],
            [(mark("on"), "$clank-now"), (" running", "$clank-quiet")],
            [(mark("off"), "$clank-quiet"), (" waiting", "$clank-quiet")],
            [(mark("failed"), "$clank-failed"), (" failed", "$clank-quiet")],
            [(tree.not_yet * 2, "$clank-box-decompose"), (" proposed", "$clank-quiet")],
            [(tree.across * 2, "$clank-good"), (" pass", "$clank-quiet")],
            [(tree.across * 2, "$clank-failed"), (" fail ⟲ back", "$clank-quiet")],
            [(tree.across * 2, "$clank-now"), (" now", "$clank-quiet")],
            [(tree.not_yet * 2, "$clank-dim"), (" not yet", "$clank-quiet")],
        ]
        _wrap_items(self.canvas, self.chart, items, y)


def _wrap_items(canvas: Canvas, chart: Chart, items: list[list[tuple[str, str]]], y: int) -> None:
    """Items set in lines, two spaces apart, a line ending before an item that would pass the chart's edge."""
    x = 0
    for item in items:
        size = sum(cell_len(text) for text, _ in item)
        if x and x + size > chart.width:
            x, y = 0, y + 1
        start = x
        for text, style in item:
            x = canvas.put(x, y, cut(text, chart.width - x) if size > chart.width else text, style)
        chart.legend.append((y, start, x))
        x += 2


def _fail_words(line: Mapping[str, Any], boxes: Mapping[str, Mapping[str, Any]], back: bool = False) -> str:
    """What a fail line says: taken, with its findings and the tries the checked box used; or waiting to be. `back`
    names the box it leads back to (a label alone, a line of the list)."""
    to = boxes.get(line["to"], {})
    where = f" back to {TAGS.get(str(to.get('type', '')), line['to'])}" if back else ""
    if line.get("state") == "failed":
        findings = int(line.get("findings") or 0)
        noun = "finding" if findings == 1 else "findings"
        tries = f"{line.get('used')} of {line.get('cap')} tries used"
        return f"fail ⟲{where} with {findings} {noun} · {tries}" if back else f"fail ⟲ {findings} {noun} · {tries}"
    return f"fail ⟲{where or ' back'}"


class _Listed:
    """The flow as a list (board D2's left): a line a box, a DECOMPOSE's tasks indented under it."""

    def __init__(
        self,
        view: Mapping[str, Any],
        chart: Chart,
        selected: str,
        live: Mapping[str, Any],
        zone: tzinfo | None,
        noted: Collection[str] = (),
    ) -> None:
        self.view, self.chart, self.selected, self.live, self.zone = view, chart, selected, live, zone
        self.noted = set(noted)
        self.canvas = Canvas(chart.width)
        self.boxes = {box["id"]: box for box in view["boxes"]}

    def draw(self) -> Chart:
        chart, canvas = self.chart, self.canvas
        chart.listed, chart.box_rows = True, 1
        y = 0
        fails = {line["from"]: line for line in self.view.get("lines") or [] if line.get("when") == "fail"}
        for stage in stages(self.view):
            for name in stage:
                indent = LIST_INDENT if len(stage) > 1 else 0
                self._line(name, indent, y)
                y += 1
                line = fails.get(name)
                if line is not None and line.get("state") == "failed":
                    said = cut(" " * LIST_INDENT + _fail_words(line, self.boxes, back=True), chart.width)
                    canvas.put(0, y, said, "$clank-failed")
                    chart.labels.append((y, LIST_INDENT, cell_len(said)))
                    y += 1
        following = self.view.get("next_flow")
        if following:
            words = f"{current().tree.arrow} next flow: {following.get('title') or 'made when approved'}"
            lit = self.selected == NEXT
            said = cut(words, chart.width)
            canvas.put(0, y, said, "bold $clank-selected-text on $clank-selection" if lit else "$clank-quiet")
            chart.boxes[NEXT] = Rect(0, y, cell_len(said), 1)
            chart.order.append(NEXT)
            y += 1
        _wrap_items(canvas, chart, [
            [(mark("done"), "$clank-good"), (" done", "$clank-quiet")],
            [(mark("on"), "$clank-now"), (" running", "$clank-quiet")],
            [(mark("off"), "$clank-quiet"), (" waiting", "$clank-quiet")],
            [(mark("failed"), "$clank-failed"), (" failed", "$clank-quiet")],
            [("proposed", "$clank-box-decompose")],
        ], y + 1)  # fmt: skip
        return canvas.chart(chart)

    def _line(self, name: str, indent: int, y: int) -> None:
        box, canvas, chart = self.boxes[name], self.canvas, self.chart
        lit = name == self.selected
        on = " on $clank-selection" if lit else ""
        right, tone = state_mark(box, self.live)
        pieces = [
            (" " * indent, ""), (right.split(" ")[0] + " ", f"{tone}{on}"),
            (tag(box) + " ", f"bold {TONES.get(str(box['type']), '$clank-text')}{on}"),
            (box["title"], f"bold $clank-selected-text{on}" if lit else "$clank-text"),
        ]  # fmt: skip
        detail = last_said(box, self.view, self.zone)
        if name in self.noted:
            pieces.append((f" {mark('note')} not saved", f"$clank-attention{on}"))
        x = 0
        for text, style in pieces:
            room = chart.width - x
            if room <= 0:
                break
            x = canvas.put(x, y, cut(text, room), style)
        if detail and chart.width - x > 6:
            x = canvas.put(x, y, cut("  " + detail, chart.width - x), "$clank-quiet")
        chart.boxes[name] = Rect(indent, y, max(x - indent, 1), 1)
        chart.order.append(name)
