"""The Monitor's Context view (design 0012 §4.7, board C; §11 step 12): the context window whole, from the followed
session's context totals and their estimate (`clank/components/agents/estimate.py`), never a number of the console's
own (decision 0067). Each panel's lines are a pure function of the totals and the width, none wider than the panel
(decision 0045); what is shortened first when room runs out is said with each.

- **Context window** (`contextpanel.summary`): the totals, the bar by part, what each part holds, whose conversation
  the engine holds.
- **What is in it** (`contents`): a header, then a row per part of the loaded model's (a template with no thinking has
  no thinking part), in the bar's order: its swatch and short name (the legend's: system, tools, you, text, thinking,
  calls, results, loop), its tokens, its share, its items, the biggest (its tokens
  and what it is) and a spark of its last ten steps (each step's parts, the gateway's census of it shared out by its own
  count). Narrower, the biggest's words are cut first (down to `LEAST` characters), then the last ten steps go, then
  the items, then the biggest; a part's name, tokens and share stay. `PartsList` holds the rows (↑↓ move through the
  parts), and Enter lists a part's items (`items_of`): each with its tokens, its step, what it is and its marks,
  biggest first, and how many more the part holds than the census kept.
- **Where the room went** (`room`): the biggest groups (the results by tool, OpenCode's system prompt and tool
  definitions, the thinking sent back, loop text, ...), each with its tokens and its share; the words are cut first.
- **Where these figures come from** (`sources`, lines that wrap): the engine adapter's context facts (its window, its
  output limit, its exact window or none, whether it counts tokens), the model's catalog entry (its template's parts,
  and where they were read) and how the estimate is made (its calibration, or that it has none).
- **On the GPU exactly**, **Over this session** and **Could be freed** are `contextgpu.py`'s, `contextchart.py`'s and
  `contextfreed.py`'s.

`Drawn` is a panel's content drawn by one of these functions for its width, again only when what it shows changed.
"""

from collections.abc import Callable
from datetime import tzinfo
from typing import Any

from textual import events
from textual.content import Content
from textual.widgets import Label, ListView

from clank.components.agents.console.biggestpanel import NO_PARTS, item_line, said
from clank.components.agents.console.contextchart import over_session
from clank.components.agents.console.contextgpu import gpu_drawn
from clank.components.agents.console.contextpanel import summary
from clank.components.agents.console.flowpanel import NO_SESSION
from clank.components.agents.console.parts import SHORT, SWATCH, tokens, tone
from clank.console.gauges import spark
from clank.console.lists import refill, relabel
from clank.console.style import current

NAME = 11  # a part's swatch and short name (the legend's)
TOKENS = 8
SHARE = 6
ITEMS = 6
TREND = 13  # "last 10 steps": its spark of ten cells, right-aligned
GAP = 2
LEAST = 16  # characters of the biggest kept before the last ten steps go, then the items
STEPS = 10  # the last steps a part's spark draws
WIDTH = 72  # the width drawn for before a panel is laid out
Drawing = Callable[[dict[str, Any] | None, int, tzinfo | None, dict[str, Any] | None], list[Content]]


def waiting(totals: dict[str, Any] | None) -> Content | None:
    """What a panel of the estimate says before it has one: no session, the totals not read, or no parts yet."""
    if totals is None:
        return Content.styled(NO_SESSION, "$clank-quiet")
    if totals.get("unavailable"):
        return Content.styled(f"context totals not available: {totals['unavailable']}", "$clank-quiet")
    if not totals.get("parts"):
        return Content.styled(NO_PARTS, "$clank-quiet")
    return None


def contents(totals: dict[str, Any] | None, width: int) -> list[Content]:
    """What is in it: a header, then a row per part, none wider than `width` (module docstring)."""
    said_first = waiting(totals)
    if said_first is not None or totals is None:
        return [_cut(said_first or Content(""), width)]
    found = totals["parts"]
    trends = _trends(totals)
    for trend, items, biggest in ((True, True, True), (False, True, True), (False, False, True), (False, False, False)):
        room = width - NAME - TOKENS - SHARE - (ITEMS if items else 0) - (GAP if biggest else 0)
        room -= GAP + TREND if trend else 0
        if not biggest or room >= LEAST:
            break
    head = ["part".ljust(NAME), "tokens".rjust(TOKENS), "share".rjust(SHARE)]
    if items:
        head.append("items".rjust(ITEMS))
    if biggest:
        head.append(" " * GAP + _fit("the biggest", room).ljust(room))
    if trend:
        head.append(" " * GAP + "last 10 steps".rjust(TREND))
    shown = [Content.styled("".join(head), "$clank-quiet")]
    for part in found["parts"]:
        name = str(part["part"])
        pieces: list[tuple[str, str] | str | Content] = [
            (SWATCH, tone(name)), " " + _fit(SHORT.get(name, name), NAME - 3).ljust(NAME - 2),
            f"{int(part['tokens']):,}".rjust(TOKENS), f"{part['share']:.0%}".rjust(SHARE),
        ]  # fmt: skip
        if items:
            pieces.append(str(part["items"]).rjust(ITEMS))
        if biggest:
            big = part.get("biggest")
            words = f"{tokens(big['tokens'])} {said(big)}" if big else ""
            pieces.append(" " * GAP + _fit(words, room).ljust(room))
        if trend:
            values = trends.get(name, [])
            top = max(values, default=0.0)
            pieces += [" " * GAP, spark(values, TREND, top=top, style=tone(name)) if top else " " * TREND]
        shown.append(Content.assemble(*pieces))
    return [_cut(line, width) for line in shown]


def part_rows(totals: dict[str, Any] | None, part: str) -> list[dict[str, Any]]:
    """A part's items the census kept, biggest first."""
    found = (totals or {}).get("parts") or {}
    return [item for item in found.get("items") or [] if item.get("part") == part]


def part_notes(totals: dict[str, Any] | None, part: str) -> list[str]:
    """What a part's window says under its items: that it holds nothing, or how many more it holds than the census
    kept."""
    found = (totals or {}).get("parts") or {}
    own = next((each for each in found.get("parts") or [] if each["part"] == part), None)
    if own is None or not own.get("tokens"):
        label = own["label"] if own else part
        return [f"{label} holds nothing in this step"]
    rows = part_rows(totals, part)
    more = int(own.get("items") or 0) - len(rows)
    if more <= 0:
        return []
    rest = max(int(own["tokens"]) - sum(int(row["tokens"]) for row in rows), 0)
    return [f"and {more} more of its {own['items']} items, about {rest:,} tokens in all"]


def items_of(totals: dict[str, Any] | None, part: str) -> list[str]:
    """A part's items, biggest first, each with its tokens, its step, what it is and its marks; and how many more the
    part holds than the census kept (its window's lines)."""
    return [item_line(row) for row in part_rows(totals, part)] + part_notes(totals, part)


def room(totals: dict[str, Any] | None, width: int) -> list[Content]:
    """Where the room went: the biggest groups, each with its tokens and its share, the words cut first."""
    said_first = waiting(totals)
    if said_first is not None or totals is None:
        return [_cut(said_first or Content(""), width)]
    shown = []
    for group in totals["parts"].get("groups") or []:
        figures = f"{int(group['tokens']):,}".rjust(8) + f"{group['share']:.0%}".rjust(5)
        words = _fit(str(group["words"]), max(width - len(figures), 0)).ljust(max(width - len(figures), 0))
        shown.append(_cut(Content.assemble(words, figures), width))
    return shown


def sources(totals: dict[str, Any] | None) -> list[Content]:
    """Where these figures come from: the engine's context facts, the model's catalog entry, how the estimate is made
    (lines that wrap in their panel)."""
    if totals is None or totals.get("unavailable"):
        return [waiting(totals) or Content("")]
    facts = totals.get("facts")
    if not facts:
        return [Content.styled("no model runs in the slot: no facts to read", "$clank-quiet")]
    engine, model = facts.get("engine") or {}, facts.get("model") or {}
    found = totals.get("parts") or {}
    estimate = found.get("how") or NO_PARTS
    shown = [
        Content.assemble(("the engine: ", "bold"), _engine(engine, str(facts.get("title") or ""))),
        Content.assemble(("the model: ", "bold"), _model(model)),
        Content.assemble(("the estimate: ", "bold"), estimate),
    ]
    if found.get("images"):
        count = int(found["images"])
        shown.append(Content(f"{count} image{'' if count == 1 else 's'} in the prompt: not counted by part, their "
                             "tokens shared among the parts"))  # fmt: skip
    return shown


def _engine(engine: dict[str, Any], title: str) -> str:
    exact = engine.get("exact")
    window, output = int(engine.get("window") or 0), int(engine.get("output") or 0)
    said_window = f"a window of {window:,} tokens, at most {output:,} an answer"
    if exact:
        attends = (f"it attends {int(exact['tokens']):,} tokens exactly on the GPU, its first block of "
                   f"{exact.get('first')} and blocks of {exact.get('block')} picked {exact.get('picks')}")  # fmt: skip
    elif engine.get("on_gpu"):
        attends = "it attends its whole window, on the GPU"
    else:
        attends = "it attends its whole window, in system memory (it runs on the CPU)"
    counts = "it counts tokens" if engine.get("counts_tokens") else "it does not count tokens"
    return f"{engine.get('label')} {engine.get('version')} (“{title}”): {said_window}; {attends}; {counts}"


def _model(model: dict[str, Any]) -> str:
    name = str(model.get("name") or model.get("id") or "a model not in the catalog")
    template = model.get("template")
    if not template:
        return f"{name}: its chat template is not in the catalog, so the thinking sent back is counted whole"
    thinking = {
        "dropped": "thinking before your last message left out", "kept": "thinking before your last message kept",
        "none": "no thinking",
    }.get(str(template.get("earlier_thinking")), "thinking as its template renders it")  # fmt: skip
    calls = {"xml": "tool calls written as XML", "json": "tool calls written as JSON"}.get(
        str(template.get("tool_calls")), "tool calls as its template writes them"
    )
    said_parts = [thinking, calls]
    markers = list(template.get("reasoning") or [])
    if len(markers) == 2:
        said_parts.append(f"thinking between {markers[0]} and {markers[1]}")
    source = f" ({template['source']})" if template.get("source") else ""
    return f"{name}: {'; '.join(said_parts)}{source}"


def _trends(totals: dict[str, Any]) -> dict[str, list[float]]:
    """Each part's tokens at the last `STEPS` steps whose parts are known, oldest first."""
    steps = list(totals.get("steps") or [])[-STEPS:]
    names = {name for step in steps for name in step.get("parts") or {}}
    return {name: [float((step.get("parts") or {}).get(name, 0)) for step in steps] for name in names}


def _fit(text: str, width: int) -> str:
    return text if len(text) <= width else text[: max(width - 1, 0)].rstrip() + current().marks.cut


def _cut(line: Content, width: int) -> Content:
    if line.cell_length <= width:
        return line
    return Content.assemble(line.truncate(max(width - 1, 0)), current().marks.cut)


DRAWINGS: dict[str, Drawing] = {
    "summary": lambda totals, width, zone, view: summary(totals, width, zone),
    "room": lambda totals, width, zone, view: room(totals, width),
    "sources": lambda totals, width, zone, view: sources(totals),
    "gpu": gpu_drawn,
    "growth": lambda totals, width, zone, view: over_session(totals, width, view, zone),
}  # each panel's drawing, by its kind (the Monitor's `drawn`)


class Drawn(Label):
    """A panel's content of the Context view, drawn by its function for the panel's width, again only when what it
    shows changed (design 0001 §5.7); it takes the focus, so Tab reaches its panel."""

    can_focus = True

    DEFAULT_CSS = """
    Drawn {
        width: 1fr;
        height: auto;
    }
    """

    def __init__(self, drawing: Drawing, *, id: str | None = None) -> None:
        super().__init__(Content.styled(NO_SESSION, "$clank-quiet"), id=id)
        self.drawing = drawing
        self.totals: dict[str, Any] | None = None
        self.zone: tzinfo | None = None
        self.view: dict[str, Any] | None = None
        self.draws = 0
        self._drawn = ""

    def show(self, totals: dict[str, Any] | None, zone: tzinfo | None, view: dict[str, Any] | None = None) -> None:
        """Show these totals (None: no session followed), and the session's flow (`view`)."""
        self.totals, self.zone, self.view = totals, zone, view
        self._draw()

    def on_resize(self, event: events.Resize) -> None:
        """Draw again for the new width."""
        self._draw()

    def _draw(self) -> None:
        shown = Content("\n").join(self.drawing(self.totals, self.content_size.width or WIDTH, self.zone, self.view))
        if shown.markup != self._drawn:
            self._drawn = shown.markup
            self.draws += 1
            self.update(shown)


class PartsList(ListView):
    """What is in it: a row per part (↑↓ move through them); its header is the label given, drawn for the same
    width; Enter on the page lists the highlighted part's items."""

    DEFAULT_CSS = """
    PartsList {
        height: auto;
    }
    PartsList > ListItem Label {
        text-wrap: nowrap;
    }
    """

    def __init__(self, head: Label, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.head = head
        self.totals: dict[str, Any] | None = None
        self.shown: list[dict[str, Any]] = []

    def show(self, totals: dict[str, Any] | None) -> None:
        """Show the parts of these totals, the highlight kept on its part."""
        kept = self.highlighted()
        self.totals = totals
        self.shown = list(((totals or {}).get("parts") or {}).get("parts") or [])
        self._draw(str(kept["part"]) if kept else None)

    def highlighted(self) -> dict[str, Any] | None:
        """The part highlighted, the first when none is."""
        if not self.shown:
            return None
        index = self.index if self.index is not None and 0 <= self.index < len(self.shown) else 0
        return self.shown[index]

    def on_resize(self, event: events.Resize) -> None:
        """Draw the rows and the header again for the new width."""
        kept = self.highlighted()
        self._draw(str(kept["part"]) if kept else None)

    def _draw(self, keep: str | None) -> None:
        drawn = contents(self.totals, self.content_size.width or WIDTH) if self.shown else []
        refill(self, drawn[1:], [str(part["part"]) for part in self.shown], keep)
        if self.shown and self.index is None:
            self.index = 0
        if drawn:
            relabel(self.head, drawn[0])
        self.display = self.head.display = bool(self.shown)
