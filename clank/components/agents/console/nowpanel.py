"""The Monitor's Now panel (design 0012 §2, §5; §11 step 7): what the followed session does this second, as the service
says it (`GET /agents/now/{workspace}/{session}`, made by `clank/components/agents/now.py`), drawn from that alone.

`head` is its first line, after the spinner: the phase in §5.1's words (in the `now` color while it works, `attention`
while it waits for you or is held, `failed` once the loop guard stopped it, `quiet` while idle), the step, its seconds
and its detail (the call running, what asks for approval, the retry's attempt, who paused it). `lines` are the others,
one each, a label then its figures, each cut with the style's "…" to the panel's width, so the panel keeps its height:

- **prompt**: this step's time to its first token (or how long it has been read, "or queued", never claimed queued);
- **last prompt**: the last prompt whose size is known (the step before, while a step runs: a prompt's size and the part
  read from the cache arrive only with its answer's end), read from the cache and new;
- **thinking** and **output**: a bar against the budget and the count, "about" while counted live (§5.2), the
  output being everything the answer writes (its thinking, its text and its calls), against the output limit;
- **writing**: the call whose arguments stream now (only the gateway sees them, §5.3), its first argument's name left
  out (`bash python -m …`);
- **speed**: tokens a second now, and a spark of each step's;
- **loop guard**: off, watching (each part's newest share, and the share under which it stops one), or what it
  stopped (§5.4).

`NowView` is the panel's content: it takes the focus (so `n`, Tab and the keys reach the panel). Its spinner is a
widget of its own, one cell wide (`NowSpin`), turned by the page on its ticks while the session works (`turn`, at most
four times a second), so a turn touches only that cell (design 0012 §2); the other lines are drawn again only when what
they show changed (design 0001 §5.7). While resting (waiting for you, held, stopped, idle) the spinner's cell holds the
state's mark. The loop guard is said as the running gateway applies it; a change to its settings file that waits for
the gateway's restart is said too.
"""

import re
from datetime import tzinfo
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.content import Content
from textual.widgets import Label, Static

from clank.components.agents.console.flowpanel import NO_SESSION
from clank.components.agents.console.flowtree import tone_of, what
from clank.console.gauges import bar, spark, spinner
from clank.console.style import current, mark

WIDTH = 48  # the width drawn for before the panel is laid out
LABEL = 12  # the labels' column: "loop guard" and two spaces
BAR = 12  # a budget's bar
TONES = {"you": "$clank-attention", "held": "$clank-attention", "looped": "$clank-failed", "idle": "$clank-quiet"}
RESTING = {"you": "asks", "held": "held", "looped": "failed", "idle": "off"}  # the mark in the spinner's cell
FIRST_KEY = re.compile(r'^\{\s*"[\w.-]{1,40}"\s*:\s*"?')  # a call's first argument's name, before its value


def head(now: dict[str, Any] | None) -> Content:
    """The first line, after the spinner: the phase, the step, its seconds and its detail."""
    if now is None:
        return Content.styled(NO_SESSION, "$clank-quiet")
    if now.get("unavailable") or not now.get("state"):
        return Content.styled("what it does now is not known", "$clank-quiet")
    state = str(now["state"])
    tone = TONES.get(state, "$clank-now")
    parts: list[tuple[str, str] | str] = [(str(now.get("phase") or state), f"bold {tone}")]
    if now.get("step"):
        parts.append(f" · step {now['step']}")
    if now.get("seconds") is not None:
        parts.append(f" · {seconds(float(now['seconds']))}")
    detail = str(now.get("detail") or "")
    call = now.get("call")
    if call:
        detail = " ".join(word for word in (str(call.get("tool") or ""), what(call)) if word)
    if detail:
        parts.append((f" · {detail}", "$clank-quiet"))
    return Content.assemble(*parts)


def lines(now: dict[str, Any] | None, width: int) -> list[Content]:
    """The lines after the first (module docstring), none wider than `width`."""
    if now is None:
        return []
    if now.get("unavailable"):
        return [_cut(Content.styled(f"not available: {now['unavailable']}", "$clank-quiet"), width)]
    shown = [
        _labeled("prompt", _prompt(now)),
        _labeled("last prompt", _last_prompt(now)),
        _labeled("thinking", _budget(now.get("thinking"), "thinking")),
        _labeled("output", _budget(now.get("output"), "output")),
        _labeled("writing", _writing(now.get("writing"))),
        _labeled("speed", _speed(now.get("speed") or {}, width)),
        _labeled("loop guard", _guard(now.get("guard") or {})),
    ]
    return [_cut(line, width) for line in shown]


def seconds(value: float) -> str:
    """A step's time: 36.1 s, then 3 min 20 s."""
    if value < 60:
        return f"{value:.1f} s"
    minutes, rest = divmod(int(value), 60)
    return f"{minutes} min {rest} s"


def _labeled(label: str, said: Content) -> Content:
    return Content.assemble((f"{label:<{LABEL}}", "$clank-quiet"), said)


def _prompt(now: dict[str, Any]) -> Content:
    prompt = now.get("prompt") or {}
    if prompt.get("reading"):
        return Content(f"being read for {seconds(float(now.get('seconds') or 0))} (or queued)")
    if prompt.get("first_ms") is not None:
        return Content(f"read in {seconds(float(prompt['first_ms']) / 1000)}")
    return Content.styled("no first token yet", "$clank-quiet")


def _last_prompt(now: dict[str, Any]) -> Content:
    prompt = now.get("prompt") or {}
    size, cached = prompt.get("tokens"), prompt.get("cached")
    if size is None:
        return Content.styled("none ended since the gateway started", "$clank-quiet")
    return Content(f"{cached:,} cached, {size - cached:,} new" if cached is not None else f"{size:,} tokens")


def _budget(found: dict[str, Any] | None, kind: str) -> Content:
    if not found:
        return Content.styled("nothing written yet", "$clank-quiet")
    tokens, budget = int(found.get("tokens") or 0), found.get("budget")
    about = "about " if found.get("about") else ""
    if not budget:
        none = "no thinking budget" if kind == "thinking" else "no output limit reported"
        return Content.assemble(f"{about}{tokens:,} ", (f"({none})", "$clank-quiet"))
    return Content.assemble(bar(tokens / budget, BAR), f" {about}{tokens:,} of {budget:,}")


def _writing(found: dict[str, Any] | None) -> Content:
    if not found:
        return Content.styled("no call being written", "$clank-quiet")
    written = " ".join(str(found.get("arguments") or "").split())
    arguments = FIRST_KEY.sub("", written, count=1).removesuffix("}").removesuffix('"')
    tool = str(found.get("tool") or "a call")
    return Content.assemble((f"{tool} ", f"bold {tone_of(tool)}"), arguments)


def _speed(speed: dict[str, Any], width: int) -> Content:
    current_speed = speed.get("now")
    said = f"{current_speed:.0f} tok/s" if current_speed else "—"
    steps = [float(each) for each in speed.get("steps") or []]
    room = max(width - LABEL - len(said) - 2, 0)
    if not steps or not room:
        return Content(said)
    return Content.assemble(said, "  ", spark(steps[-room:], min(room, len(steps)), top=max(steps)))


def _guard(guard: dict[str, Any]) -> Content:
    restart = guard.get("restart")
    if not guard.get("on"):
        if restart:
            return Content.styled(
                "off in the running gateway; on once it restarts (config/gateway.json)", "$clank-quiet"
            )
        return Content.styled("off (config/gateway.json, applied when the gateway restarts)", "$clank-quiet")
    waiting = (" · changed in config/gateway.json: at its restart", "$clank-quiet") if restart else ""
    if guard.get("stopped"):
        return Content.assemble(("stopped ", "bold $clank-failed"), str(guard["stopped"]), waiting)
    parts = [part for part in guard.get("parts") or [] if part.get("share") is not None]
    if not parts:
        return Content.assemble(str(guard.get("said") or "watching"), waiting)
    shares = ", ".join(f"{_part(part)} {part['share']:.0%}" for part in parts)
    return Content.assemble(shares, (f" · limit {float(guard.get('ratio') or 0):.0%}", "$clank-quiet"), waiting)


def _part(part: dict[str, Any]) -> str:
    name = str(part.get("part") or "")
    return str(part.get("name") or "a call") if name.startswith("tool") else name


def _cut(line: Content, width: int) -> Content:
    """A line cut to `width` cells, ending in the style's mark of cut text when it was cut."""
    if line.cell_length <= width:
        return line
    return Content.assemble(line.truncate(max(width - 1, 0)), current().marks.cut)


class NowSpin(Static):
    """The spinner's cell: it turns while the session works, and holds the state's mark while it rests (a `Static`, so
    the console's rule that a page's labels take their whole row leaves it its two cells)."""

    DEFAULT_CSS = """
    NowSpin {
        width: 2;
        height: 1;
    }
    """


class NowView(Vertical):
    """The Now panel's content: the spinner, the first line and the others, each drawn again only when it changed."""

    can_focus = True

    DEFAULT_CSS = """
    NowView {
        width: 1fr;
        height: auto;
    }
    NowView > Horizontal {
        height: 1;
    }
    NowView #now-head {
        width: 1fr;
        text-wrap: nowrap;
        text-overflow: ellipsis;
    }
    NowView #now-lines {
        width: 1fr;
        height: auto;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(id=id)
        self.now: dict[str, Any] | None = None
        self.zone: tzinfo | None = None
        self.draws = 0  # the lines drawn again: a test counts them
        self.turns = 0  # the spinner's cell drawn again
        self.frame = 0  # the spinner's turn
        self._drawn = ""
        self._spun = ""

    def compose(self) -> ComposeResult:
        """The spinner and the first line, then the other lines."""
        with Horizontal():
            cell = NowSpin(id="now-spin")
            cell.display = False  # until what a session does is known
            yield cell
            yield Label(Content.styled(NO_SESSION, "$clank-quiet"), id="now-head")
        others = Label(id="now-lines")
        others.display = False  # until a session is followed
        yield others

    @property
    def working(self) -> bool:
        """Whether the session works now, so the spinner turns."""
        return bool((self.now or {}).get("working"))

    def show(self, now: dict[str, Any] | None, zone: tzinfo | None = None) -> None:
        """Show what the session does now (None: no session followed)."""
        self.now, self.zone = now, zone
        self._draw()
        self.spin(self.frame)

    def turn(self) -> None:
        """Turn the spinner one step (the page does, on its ticks, while the session works)."""
        self.spin(self.frame + 1)

    def spin(self, frame: int) -> None:
        """Turn the spinner to `frame` while the session works; else hold the state's mark. Only its cell changes."""
        self.frame = frame
        cell = self.query_one(NowSpin)
        state = str((self.now or {}).get("state") or "")
        cell.display = bool(state)  # none before a session is followed and what it does is known
        if not state:
            shown = Content("")
        elif self.working:
            shown = Content.styled(spinner(frame), "$clank-now")
        else:
            shown = Content.styled(mark(RESTING.get(state, "off")), TONES.get(state, "$clank-quiet"))
        if shown.markup != self._spun:
            self._spun = shown.markup
            self.turns += 1
            cell.update(shown)

    def on_resize(self, event: events.Resize) -> None:
        """Draw again for the new width."""
        self._draw()

    def _draw(self) -> None:
        others = self.query_one("#now-lines", Label)
        width = others.content_size.width or self.content_size.width or WIDTH
        said = lines(self.now, width)
        first, rest = head(self.now), Content("\n").join(said)
        if first.markup + "\n" + rest.markup != self._drawn:
            self._drawn = first.markup + "\n" + rest.markup
            self.draws += 1
            self.query_one("#now-head", Label).update(first)
            others.update(rest)
            others.display = bool(said)  # no empty row before a session is followed
