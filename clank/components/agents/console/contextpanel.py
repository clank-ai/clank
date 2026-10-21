"""The Monitor's Context window panel (design 0012 §2, §4.1, §4.4; §11 step 3): the followed session's context totals,
as the service gives them (`GET /agents/context/{workspace}/{session}`, made by `clank/components/agents/context.py`
from the loaded slot's facts), drawn from those alone, so the panel never names an engine's or a model's numbers of its
own (decision 0067).

`lines` draws them, a line each, each cut with the style's "…" to the panel's width:

- **The totals**: how much of the window the last finished step used and its share, how much is left before OpenCode
  compacts (and where), and the share of the prompt read from the cache, or "not reported by this engine" when the
  engine reports none (never a number), or that the last step's answer did not carry it. Before a step ended since the
  gateway started, the window and the line; when the last step's answer did not report its size, that; with no model
  in the slot, that; when the totals could not be read (`unavailable`), why.
- **The bar**: the room used (its color nearing the line goes from the style's `low` to `busy` and `full`), the room
  left to the compaction line, and the room kept beyond it, for a step's tool results (the margin OpenCode is not told
  of, decision 0089) and the answer (the style's `kept` cells). With the parts estimated (design 0012 §4.2, §11 step
  12), the room used is drawn by part, each in its color, and the line under it says what each part holds, "estimate"
  first (`parts.py`: narrower, it gives up its smallest parts first).
- **On the GPU**: what the engine attends exactly there and what waits in system memory, or that it attends its whole
  window (in system memory, for an engine on the CPU); or, when another session took the engine or the engine holds no
  conversation, that this session's tokens are read again at its next step.
- **Whose conversation the engine holds**: this session's, a subagent's, another session's or a request of no
  session's, since when, and what that costs; none, when the slot stopped, was switched or its engine started again;
  not known when nothing reached the engine since the gateway started.
- **Where the figures come from, and what a compaction keeps**: the engine and its version, the preset, the model and
  whether it is calibrated.
- **A switch**: when the slot runs another preset now, its window, from the next step.
- **Growth** (design 0012 §4.5, §11 step 7): under the GPU's line, "this session" and a spark of the session's size at
  each finished step, as OpenCode counts it (its prompt, the cache included, and its answer: `growth`, from the
  session's flow), scaled to the window, the newest that fit; a step the loop guard stopped leaves the size as it was
  and its cell is in the failed color; a compaction is the summary's cell, in the attention color (or a cell of its
  own where OpenCode said it compacted with no summary seen); then each mark said, when and by whom (`spark_line`).
  Where another session took the engine is not marked yet (the gateway keeps whose request each slot read only for
  now).

`ContextWindow` is the panel's content: it takes the focus (so `c`, Tab and Enter reach the panel), and draws again only
when what it shows changed (design 0001 §5.7).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, tzinfo
from typing import Any

from textual import events
from textual.content import Content
from textual.widgets import Label

from clank.components.agents.console import parts
from clank.components.agents.console.flowpanel import NO_SESSION
from clank.components.agents.watchfor.rules import LOOP_WORDS, size
from clank.console.gauges import level
from clank.console.style import current, mark

NOT_REPORTED = "not reported by this engine"
WIDTH = 80  # the width drawn for before the panel is laid out
PROGRAM = "OpenCode"  # the agent program of every session the watchers see


@dataclass(frozen=True)
class Point:
    """The session's size after one of its steps, as OpenCode counts it, and what marks it: "" for none, "looped" (the
    loop guard stopped that step's answer, which left the context) or "compacted" (with who compacted it)."""

    size: int
    n: int | None
    at: int | None  # when the step began, ms since the epoch
    mark: str = ""
    by: str = ""
    request: str = ""  # the gateway's request that answered the step, when the flow paired one


def lines(
    totals: dict[str, Any] | None, width: int, zone: tzinfo | None = None, view: dict[str, Any] | None = None
) -> list[Content]:
    """The panel's lines for a session's totals (module docstring), and its growth from its flow (`view`), none
    wider than `width`."""
    if totals is None:
        return [Content.styled(NO_SESSION, "$clank-quiet")]
    if totals.get("unavailable"):
        return [_cut(Content.styled(f"context totals not available: {totals['unavailable']}", "$clank-quiet"), width)]
    shown = [_totals(totals)]
    if totals.get("window") and totals.get("line"):
        shown.append(parts.bar(totals, width) if totals.get("parts") else bar(totals, width))
    said = parts.legend(totals, width)
    if said is not None:
        shown.append(said)
    points = growth(view)
    grew = spark_line(points, width, totals.get("window"), zone) if points else None
    for line in (gpu_line(totals), grew, _holder(totals, zone), _sources(totals), _switched(totals)):
        if line is not None:
            shown.append(line)
    return [_cut(line, width) for line in shown]


def summary(totals: dict[str, Any] | None, width: int, zone: tzinfo | None = None) -> list[Content]:
    """The Context view's Context window (design 0012 §4.7): the totals, the bar (by part), what each part holds, whose
    conversation the engine holds and a switch; the GPU, the growth and the sources have panels of their own there."""
    if totals is None or totals.get("unavailable"):
        return lines(totals, width, zone)
    shown = [_totals(totals)]
    if totals.get("window") and totals.get("line"):
        shown.append(parts.bar(totals, width) if totals.get("parts") else bar(totals, width))
    for line in (parts.legend(totals, width), _holder(totals, zone), _switched(totals)):
        if line is not None:
            shown.append(line)
    return [_cut(line, width) for line in shown]


def growth(view: dict[str, Any] | None) -> list[Point]:
    """The session's size at each finished step, in time order (module docstring)."""
    points: list[Point] = []
    band: dict[str, Any] | None = None  # a compaction whose summary is not seen yet
    for node in (view or {}).get("nodes") or []:
        if node.get("undone"):
            continue
        last = points[-1].size if points else 0
        if node.get("kind") == "band":
            if band is not None:  # one said with no summary: a cell of its own
                points.append(Point(last, None, _at(band), "compacted", _who(band)))
            band = node
            continue
        if node.get("kind") != "step":
            continue
        looped = str((node.get("request") or {}).get("looped") or "") or str(node.get("error") or "").startswith(
            LOOP_WORDS
        )
        if looped:
            points.append(Point(last, node.get("n"), node.get("created"), "looped"))
        elif node.get("ended") == "finished" and size(node):
            if band is not None and not node.get("summary"):  # a compaction with no summary seen: a cell before
                points.append(Point(last, None, _at(band), "compacted", _who(band)))
                band = None
            compacted = band is not None
            by = _who(band) if band is not None else ""
            request = str((node.get("request") or {}).get("id") or "")
            points.append(
                Point(size(node), node.get("n"), node.get("created"), "compacted" if compacted else "", by, request)
            )
            band = None
    if band is not None and band.get("done"):
        points.append(Point(points[-1].size if points else 0, None, _at(band), "compacted", _who(band)))
    return points


def spark_line(points: list[Point], width: int, window: int | None, zone: tzinfo | None = None) -> Content:
    """ "this session", the spark of the newest points that fit (scaled to the window, else the largest), each marked
    cell in its color, then each mark said; no wider than `width`."""
    label = "this session "
    room = max(width - len(label), 0)
    shown = points[-room:] if room else []
    top = float(window or max((point.size for point in points), default=1) or 1)
    sparks = current().sparks
    cells: list[tuple[str, str]] = []
    for point in shown:
        step = min(int(point.size / top * (len(sparks) - 1) + 0.5), len(sparks) - 1)
        tone = {"looped": "$clank-failed", "compacted": "$clank-attention"}.get(point.mark, "$clank-data-1")
        cells.append((sparks[step], tone))
    said = [mark_words(point, zone) for point in shown if point.mark]
    legend = ("  " + " · ".join(said), "$clank-quiet") if said else ""
    return _cut(Content.assemble((label, "$clank-quiet"), *cells, legend), width)


def mark_words(point: Point, zone: tzinfo | None) -> str:
    """A marked point in words: when, and what (the loop guard's stop, or who compacted)."""
    when = _clock_ms(point.at, zone)
    if point.mark == "looped":
        return f"{mark('failed')} {when} the loop guard stopped step {point.n}"
    return f"{when} compacted by {point.by}"


def _who(band: dict[str, Any]) -> str:
    """Who compacted: OpenCode by itself, or the owner through the Guide (design 0012 §9.6)."""
    return "OpenCode" if band.get("auto") and not band.get("asked") else "you"


def _at(node: dict[str, Any]) -> int | None:
    at = node.get("at") or []
    return int(at[0]) if at and isinstance(at[0], int | float) else None


def _clock_ms(at: int | None, zone: tzinfo | None) -> str:
    """A moment in ms since the epoch on the owner's clock (HH:MM), "--:--" when not known."""
    if at is None or at <= 0:
        return "--:--"
    return datetime.fromtimestamp(at / 1000, UTC).astimezone(zone).strftime("%H:%M")


def bar(totals: dict[str, Any], width: int) -> Content:
    """The window as a bar: the room used, the room left to the compaction line, the room kept beyond it (for a
    step's tool results and the answer)."""
    cells = current().bar
    window, line, used = int(totals["window"]), int(totals["line"]), int(totals.get("used") or 0)
    to_line = max(min(round(line / window * width), width), 0)
    filled = min(round(used / window * width), to_line) if used else 0
    color = level(used / line) if line else "$clank-low"
    return Content.assemble(
        (cells.full * filled, color),
        (cells.empty * (to_line - filled), "$clank-border"),
        (cells.kept * (width - to_line), "$clank-quiet"),
    )


def _totals(totals: dict[str, Any]) -> Content:
    window, used, line, left = totals.get("window"), totals.get("used"), totals.get("line"), totals.get("left")
    slot = totals.get("slot") or {}
    gateway = totals.get("gateway") or {}
    if not window:
        why = f" · {gateway['problem']}" if gateway.get("problem") else ""
        return Content.styled(f"no model runs in the {slot.get('name') or 'main'} slot{why}", "$clank-quiet")
    if used is None:
        said = "no step of this session has ended since the gateway started"
        if totals.get("step"):
            said = "the last step's answer did not report its size"
        if gateway.get("state") not in ("running", ""):
            said = f"the gateway is {gateway['state']}: no step's figures are known"
        compacts = f" · {PROGRAM} compacts at {line:,}" if line else ""
        return Content.assemble(f"window {window:,}{compacts} · ", (said, "$clank-quiet"))
    parts: list[tuple[str, str] | str] = [(f"{used:,}", "bold"), f" of {window:,} tokens ({used / window:.0%})"]
    if left is not None and left >= 0:
        parts += [" · ", (f"{left:,}", "bold"), f" left before {PROGRAM} compacts at {line:,}"]
    elif left is not None:
        parts += [" · ", (f"{-left:,} past the line where {PROGRAM} compacts ({line:,})", "$clank-attention")]
    parts += [" · ", *_cache(totals)]
    return Content.assemble(*parts)


def _cache(totals: dict[str, Any]) -> list[tuple[str, str] | str]:
    if totals.get("cache_share") is not None:
        return [f"{totals['cache_share']:.0%} read from the cache"]
    if not totals.get("cache_reported"):
        return ["read from the cache: ", (NOT_REPORTED, "$clank-quiet")]
    return ["read from the cache: ", ("not in the last step's answer", "$clank-quiet")]


def gpu_line(totals: dict[str, Any]) -> Content | None:
    """What the engine attends of the session, on one line (the Session view's; the Context view's when it holds no
    conversation of the session's, or has no exact window)."""
    gpu, holder = totals.get("gpu"), totals.get("holder") or {}
    if not gpu:
        return None
    if gpu.get("device") == "cloud":  # the service's words: a cloud model holds nothing here (design 0016 §13)
        return Content.assemble(("On the GPU exactly: ", "bold"), (str(gpu.get("said") or ""), "$clank-quiet"))
    stored, exact = gpu.get("stored"), gpu.get("exact")
    if holder.get("lost"):
        again = f"its {stored:,} tokens are read again at its next step" if stored is not None else ""
        return Content.assemble(
            ("On the GPU: ", "bold"), f"nothing of this session's ({_lost(totals)}){'; ' if again else ''}",
            (again, "$clank-attention"),
        )  # fmt: skip
    if holder.get("taken") and stored is not None:
        return Content.assemble(
            ("On the GPU: ", "bold"), "another conversation now; ",
            (f"this session's {stored:,} tokens are read again at its next step", "$clank-attention"),
        )  # fmt: skip
    if gpu.get("device") == "cpu":
        whole = f"all {stored:,} tokens; " if stored is not None else ""
        return Content.assemble(
            ("In system memory: ", "bold"), f"{whole}it attends its whole window (it runs on the CPU)"
        )
    if exact is None:
        whole = f"all {stored:,} tokens; " if stored is not None else ""
        return Content.assemble(("On the GPU: ", "bold"), f"{whole}it attends its whole window")
    picks = f"blocks of {gpu.get('block')} picked {gpu.get('picks')}"
    if stored is None:
        return Content.assemble(("On the GPU exactly: ", "bold"), f"up to {exact:,} tokens · {picks}")
    if not gpu.get("elsewhere"):
        return Content.assemble(("On the GPU exactly: ", "bold"), f"all {stored:,} tokens (up to {exact:,})")
    return Content.assemble(
        ("On the GPU exactly ", "bold"), (f"{gpu['attended']:,}", "bold"), " · ",
        (f"{gpu['elsewhere']:,} in system memory", "$clank-quiet"), f" · {picks}",
    )  # fmt: skip


def _holder(totals: dict[str, Any], zone: tzinfo | None) -> Content | None:
    holder = totals.get("holder")
    if not totals.get("facts"):
        return None
    if not holder:
        return Content.styled(
            "whose conversation the engine holds: not known since the gateway started", "$clank-quiet"
        )
    if holder.get("lost"):
        return Content.assemble(
            ("▲", "$clank-attention"), f" {_lost(totals)}: the engine holds no conversation; ",
            ("this session's next step reads its whole prompt again", "$clank-attention"),
        )  # fmt: skip
    if holder.get("this"):
        return Content.assemble((mark("on"), "$clank-good"), " the engine holds this session's conversation")
    since = _clock(str(holder.get("time") or ""), zone)
    who = "a subagent of this session" if holder.get("subagent") else (
        "another session" if holder.get("session") else "a request of no session"
    )  # fmt: skip
    named = f" ({holder['session']})" if holder.get("session") else ""
    if holder.get("taken"):
        verb = "has the engine now" if holder.get("flying") else "took the engine"
        return Content.assemble(
            ("▲", "$clank-attention"), f" {who} {verb} at {since}: ",
            ("this session's next step reads its whole prompt again", "$clank-attention"), named,
        )  # fmt: skip
    return Content.assemble(f"the engine's newest request is {who}'s ({since}); it may keep this one's too", named)


def _lost(totals: dict[str, Any]) -> str:
    """Why the engine holds no conversation, in words."""
    lost, name = (totals.get("holder") or {}).get("lost"), (totals.get("slot") or {}).get("name") or "main"
    if lost == "switched":
        return f"the {name} slot was switched"
    if lost == "restarted":
        return "its engine started again"
    return f"the {name} slot is {lost}"


def _sources(totals: dict[str, Any]) -> Content | None:
    facts = totals.get("facts")
    if not facts:
        return None
    engine, model = facts.get("engine") or {}, facts.get("model") or {}
    calibrated = "calibrated" if model.get("calibration") else "not calibrated"
    keeps = f" · after compacting: a summary and the last {totals['keeps']:,} tokens" if totals.get("keeps") else ""
    return Content.assemble(
        "figures from ", (f"{engine.get('label')} {engine.get('version')}", "$clank-name"),
        f", “{facts.get('title')}” · ",
        (str(model.get("name") or model.get("id") or "a model not in the catalog"), "$clank-name"), f", {calibrated}",
        (keeps, "$clank-quiet"),
    )  # fmt: skip


def _switched(totals: dict[str, Any]) -> Content | None:
    switched = totals.get("switched")
    if not switched:
        return None
    name = (totals.get("slot") or {}).get("name") or "main"
    window = f" ({switched['window']:,} tokens)" if switched.get("window") else ""
    return Content.assemble(
        ("▲", "$clank-attention"), f" the {name} slot now runs “{switched.get('title')}”{window}: its window applies ",
        "from the next step",
    )  # fmt: skip


def _clock(time: str, zone: tzinfo | None) -> str:
    """A record's time as the owner's clock reads it (HH:MM), or as it was written when it does not read."""
    try:
        return datetime.fromisoformat(time).astimezone(zone).strftime("%H:%M")
    except ValueError:
        return time


def _cut(line: Content, width: int) -> Content:
    """A line cut to `width` cells, ending in the style's mark of cut text when it was cut."""
    if line.cell_length <= width:
        return line
    return Content.assemble(line.truncate(max(width - 1, 0)), current().marks.cut)


class ContextWindow(Label):
    """The Context window panel's content: the session's totals, drawn for the panel's width, again only when they
    changed."""

    can_focus = True

    DEFAULT_CSS = """
    ContextWindow {
        width: 1fr;
        height: auto;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(Content.styled(NO_SESSION, "$clank-quiet"), id=id)
        self.totals: dict[str, Any] | None = None
        self.zone: tzinfo | None = None
        self.view: dict[str, Any] | None = None
        self.draws = 0  # how often it was drawn: a test counts them
        self._drawn = Content.styled(NO_SESSION, "$clank-quiet").markup

    def show(self, totals: dict[str, Any] | None, zone: tzinfo | None, view: dict[str, Any] | None = None) -> None:
        """Show these totals (None: no session followed), and the session's growth from its flow (`view`)."""
        self.totals, self.zone, self.view = totals, zone, view
        self._draw()

    def on_resize(self, event: events.Resize) -> None:
        """Draw again for the new width."""
        self._draw()

    def _draw(self) -> None:
        shown = Content("\n").join(lines(self.totals, self.content_size.width or WIDTH, self.zone, self.view))
        if shown.markup != self._drawn:
            self._drawn = shown.markup
            self.draws += 1
            self.update(shown)
