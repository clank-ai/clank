"""The Monitor's Guide panel (design 0012 §2, §9.1; §11 steps 9 and 11): what the owner can do to the session the page
follows, as the service offers it (`GET /agents/guide/{workspace}/{session}`, `clank/components/agents/guide.py`).

`lines` draws one line for each action, cut with the style's "…" to the panel's width: its key (the page takes it on the
Session view: `.` Stop now, `m` a note, `k` Compact now, `p` Pause or Resume, `u` Undo, Undo turn or Redo, `x` Drop),
its title, what it does, briefly, and what it costs (Drop's cost is its call's, said in its window); an action that
cannot run now is drawn in the quiet color with the reason instead (when none can, for one reason, the keys on one line
and the reason once). Under an action that ran, its last state: when, by whom, and how it stands now (a stop stopping or
stopped; a note written, waiting, read by step n, answered, or not read, to send again; a compaction asked, compacting
or done; a pause pausing after this step, held with its timer, or resumed; an undo undone, the turn undone, final or
brought back; a drop clearing, then cleared), a failure in the failed color with its reason. The page's `?` says each
action whole: what it does (for the turn, why the step alone is refused), the exact call and what it costs (`whole`).

`about` words the node under the flow's cursor for a note ("step 12, `bash pytest -q`"), as the service puts it after
"About" at the note's start. `GuideList` is the panel's content: it takes the focus (so `g`, Tab and the keys reach the
panel), and draws again only when what it shows changed (design 0001 §5.7).
"""

from datetime import datetime, tzinfo
from typing import Any

from textual import events
from textual.content import Content
from textual.widgets import Label

from clank.components.agents.console.flowpanel import NO_SESSION
from clank.components.agents.console.flowtree import Node, flat
from clank.console.style import current

WIDTH = 60  # the width drawn for before the panel is laid out
PRESSED = {"full_stop": "stop", "m": "note", "k": "compact", "p": "pause", "u": "undo", "x": "drop"}  # Textual's names
ABOUT = 60  # characters of a call's words a note's "about" keeps
STATES = {
    "stopping": "stopping", "stopped": "stopped", "failed": "failed", "written": "your note is sent",
    "waiting": "your note waits for the next step", "read": "your note was read by step {step}",
    "answered": "your note was read by step {step}, and answered",
    "not read": "your note was not read: m sends it again",
    "sent": "your note answered the call waiting for approval", "asked": "a compaction is asked",
    "compacting": "compacting", "done": "compacted",
    "pausing after this step": "pausing after this step", "held": "held {held}: p resumes it", "resumed": "resumed",
    "undone": "{what} undone: u redoes {them} until your next message",
    "turn undone": "{what} undone, its text in the note line: u redoes {them} until your next message",
    "final": "{what} undone for good: your next message made it final", "redone": "{what} brought back",
    "clearing": "clearing {what} result", "cleared": "{what} result cleared, for good",
}  # fmt: skip
TONES = {"failed": "$clank-failed", "not read": "$clank-attention", "done": "$clank-good", "stopped": "$clank-good",
         "answered": "$clank-good", "pausing after this step": "$clank-attention",
         "held": "$clank-attention", "undone": "$clank-attention", "turn undone": "$clank-attention",
         "redone": "$clank-good", "cleared": "$clank-good"}  # fmt: skip


def lines(guide: dict[str, Any] | None, width: int, zone: tzinfo | None = None) -> list[Content]:
    """The panel's lines (module docstring), none wider than `width`."""
    if guide is None:
        return [Content.styled(NO_SESSION, "$clank-quiet")]
    if guide.get("unavailable"):
        return [_cut(Content.styled(f"the Guide is not available: {guide['unavailable']}", "$clank-quiet"), width)]
    offered = list(guide.get("actions") or [])
    reasons = {str(action["why"]) for action in offered if not action["can"]}
    if offered and not any(action["can"] for action in offered) and len(reasons) == 1:  # one reason: said once
        keys = Content("  ").join(
            Content.assemble((f"{action['key']} ", "bold $clank-key"), (str(action["title"]), "$clank-quiet"))
            for action in offered
        )
        return [_cut(keys, width), _cut(Content.styled(reasons.pop(), "$clank-quiet"), width)]
    shown: list[Content] = []
    for action in offered:
        key = (f"{action['key']} ", "bold $clank-key")
        title = (f"{action['title']:<12}", "bold" if action["can"] else "$clank-quiet")
        if action["can"] and action["action"] == "drop" and not action.get("item"):  # its cost is its call's
            said = Content.assemble(key, title, str(action["brief"]))
        elif action["can"]:
            said = Content.assemble(key, title, str(action["brief"]), (f" · {_cost(action['cost'])}", "$clank-quiet"))
        else:
            said = Content.assemble(key, title, (action["why"], "$clank-quiet"))
        shown.append(_cut(said, width))
        state = action.get("state")
        if state:
            shown.append(_cut(_state(state, zone), width))
    return shown


def whole(guide: dict[str, Any] | None) -> list[str]:
    """What `?` says of the Guide: each action whole, its exact call and its cost, or why it cannot run."""
    if not guide or guide.get("unavailable"):
        return []
    said = []
    for action in guide.get("actions") or []:
        key = action["key"]
        if action["can"]:
            refused = f"{action['refused']}: " if action.get("refused") else ""
            line = (f"{key} {action['title']}: {refused}{action['does']}. The call: {'; '.join(action['calls'])}. "
                    f"What it costs: {action['cost']['words']}.")  # fmt: skip
        else:
            line = f"{key} {action['title']} cannot run now: {action['why']}."
        state = action.get("state") or {}
        if state.get("why"):  # the panel cuts its state line to its width: here it is whole
            line += f" Its last run: {_state(state, None).plain.strip()}."
        said.append(line)
    return said


def about(node: Node | None, view: dict[str, Any] | None) -> str:
    """What a note is about, from the node under the flow's cursor: a call, its step and its words; a step's other
    node, its step; the owner's message or note, its words; a branch, its words; "" for the root, a band, or none."""
    if node is None or node.kind in ("root", "band", "other"):
        return ""
    numbers = {str(each["id"]): each.get("n") for each in (view or {}).get("nodes") or [] if each.get("kind") == "step"}
    step = f"step {numbers[node.step]}" if node.step in numbers else ""
    words = flat(node.words)
    words = words if len(words) <= ABOUT else words[: ABOUT - 1] + "…"
    if node.kind == "call":
        return f"{step}, `{words}`" if step else f"`{words}`"
    if step:
        return step
    if node.kind in ("said", "note"):
        return words
    return f"“{words}”"


def _cost(cost: dict[str, Any]) -> str:
    """What the action costs, briefly: the tokens read again and the time, or that it is not known."""
    tokens, seconds = cost.get("tokens"), cost.get("seconds")
    if tokens == 0:
        return "nothing read again"
    if tokens is None:
        return "its cost to measure"
    if seconds is None:
        return f"about {tokens:,} tokens read again"
    return f"about {tokens:,} tokens read again, about {seconds:,} s"


def _state(state: dict[str, Any], zone: tzinfo | None) -> Content:
    """An action's last state: how it stands, when and by whom, and a failure's reason."""
    name = str(state.get("state") or "")
    what = str(state.get("what") or "")
    them = "them" if what.startswith("steps") or " and " in what else "it"
    words = STATES.get(name, name).format(step=state.get("step") or "?", held=_timer(state.get("seconds")),
                                          what=what or "it", them=them)  # fmt: skip
    when = ""
    if state.get("time"):
        when = datetime.fromisoformat(str(state["time"]).replace("Z", "+00:00")).astimezone(zone).strftime("%H:%M")
    told = " · ".join(part for part in (when, str(state.get("by") or "")) if part)
    why = f": {state['why']}" if state.get("why") else ""
    return Content.assemble(
        "  ", (words + why, TONES.get(name, "$clank-text")), (f" · {told}" if told else "", "$clank-quiet")
    )


def _timer(seconds: Any) -> str:
    """How long a request has been held: 42 s, 3:07, 1:02:15."""
    if not isinstance(seconds, int | float):
        return ""
    whole = int(seconds)
    if whole < 60:
        return f"{whole} s"
    hours, rest = divmod(whole, 3600)
    return f"{hours}:{rest // 60:02}:{rest % 60:02}" if hours else f"{rest // 60}:{rest % 60:02}"


def _cut(line: Content, width: int) -> Content:
    """A line cut to `width` cells, ending in the style's mark of cut text when it was cut."""
    if line.cell_length <= width:
        return line
    return Content.assemble(line.truncate(max(width - 1, 0)), current().marks.cut)


class GuideList(Label):
    """The Guide panel's content: each action and its last state, drawn for the panel's width, again only when they
    changed."""

    can_focus = True

    DEFAULT_CSS = """
    GuideList {
        width: 1fr;
        height: auto;
    }
    """

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(Content.styled(NO_SESSION, "$clank-quiet"), id=id)
        self.guide: dict[str, Any] | None = None
        self.zone: tzinfo | None = None
        self.draws = 0  # how often it was drawn: a test counts them
        self._drawn = Content.styled(NO_SESSION, "$clank-quiet").markup

    def show(self, guide: dict[str, Any] | None, zone: tzinfo | None) -> None:
        """Show what the Guide offers (None: no session followed)."""
        self.guide, self.zone = guide, zone
        self._draw()

    def on_resize(self, event: events.Resize) -> None:
        """Draw again for the new width."""
        self._draw()

    def _draw(self) -> None:
        shown = Content("\n").join(lines(self.guide, self.content_size.width or WIDTH, self.zone))
        if shown.markup != self._drawn:
            self._drawn = shown.markup
            self.draws += 1
            self.update(shown)
