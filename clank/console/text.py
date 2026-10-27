"""How the console writes times, durations, counts and states: in the user's own time zone, briefly, the same on every
page; a state in color (`tone`, `painted`): the style's `good` when it is as wanted, `attention` while it changes,
`failed` when it is not (green, yellow and red in Clank's style).

The API speaks UTC (`2026-10-11T11:40:02.000Z`); the console shows local times (`11:40:02`), or those of the zone it
was given (tests use UTC, so a frame does not depend on the machine running them).

A model request's text as it is written (`live_text`: the Requests page's live view, the Monitor's live text) shows its
end, its thinking dimmed, its answer as it is, its tool calls in the calls' color.
"""

from datetime import datetime, tzinfo

from textual.content import Content

from clank.console.style import current

GOOD = ("running", "runs", "ready", "done", "built", "up")
CHANGING = ("starting", "stopping", "waiting", "queued", "being read", "not read yet", "connecting")
BAD = (
    "stopped",
    "exited",
    "failed",
    "not ",
    "none",
    "cannot",
    "crashed",
    "refused",
    "problem",
    "interrupted",
    "canceled",
    "cut off",  # a workspace whose container runs without its way to the model, the edge (design 0004 §3)
)


def parse(text: str) -> datetime:
    """A time as the API writes it."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def clock(moment: datetime, zone: tzinfo | None) -> str:
    """The time of day to the minute: 11:42."""
    return moment.astimezone(zone).strftime("%H:%M")


def time_of(text: str, zone: tzinfo | None) -> str:
    """An API time as the time of day to the second: 11:40:02."""
    return parse(text).astimezone(zone).strftime("%H:%M:%S")


def moment(text: str, zone: tzinfo | None) -> str:
    """An API time as a day and a time to the minute: 2026-10-21 09:12."""
    return parse(text).astimezone(zone).strftime("%Y-%m-%d %H:%M")


def duration(seconds: float) -> str:
    """A length of time, briefly: 40s, 5m, 2h14m, 3d2h."""
    whole = max(0, int(seconds))
    days, rest = divmod(whole, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, rest = divmod(rest, 60)
    if days:
        return f"{days}d{hours}h"
    if hours:
        return f"{hours}h{minutes:02d}m"
    if minutes:
        return f"{minutes}m"
    return f"{rest}s"


def count(number: int, word: str, plural: str = "") -> str:
    """A number with its word: 1 container, 2 containers."""
    return f"{number} {word if number == 1 else plural or word + 's'}"


def tone(state: str) -> str:
    """The color a state is shown in, a role of the style: `good` when it is as wanted, `attention` while it changes,
    `failed` when it is not; none for a word that is not a state. The style's marks say a state too, whatever glyphs
    the style draws them with: `done` is as wanted, `cut` (something under way) changes, `failed` is not."""
    word = state.strip()
    marks = current().marks
    first = word.split(" ", 1)[0]
    word = word.lower()
    if word.startswith(CHANGING) or first == marks.cut:
        return "$clank-attention"
    if word.startswith(GOOD) or first == marks.done:
        return "$clank-good"
    if word.startswith(BAD) or first == marks.failed:
        return "$clank-failed"
    return ""


def painted(text: str, *marks: str) -> Content:
    """Text shown as it is (no markup read in it), each mark (a state's word, a sign) colored by its tone where it
    next appears: the marks are found in order, so a state that appears twice is colored twice."""
    content = Content(text)
    after = 0
    for mark in marks:
        start = text.find(mark, after) if mark else -1
        if start < 0:
            continue
        after = start + len(mark)
        if tone(mark):
            content = content.stylize(tone(mark), start, after)
    return content


LIVE_SHOWN = 12000  # the most characters of a live text shown: its end
LIVE_STYLES = {"thinking": "dim italic", "answer": "", "tool": "$clank-part-calls"}


def live_text(parts: list[list[str]]) -> Content:
    """A request's text as written: its end, its thinking dimmed, its answer as it is, its tool calls in color."""
    shown: list[tuple[str, str]] = []
    room = LIVE_SHOWN
    for kind, text in reversed(parts):
        if room <= 0:
            break
        shown.insert(0, (text[-room:], LIVE_STYLES.get(kind, "")))
        room -= len(text)
    if not shown:
        return Content.assemble(("(nothing written yet)", "dim"))
    return Content.assemble(*shown)
