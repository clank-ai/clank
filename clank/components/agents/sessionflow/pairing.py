"""Which of the gateway's requests answered which step of a session (design 0012 §6.1, decision 0049).

A session makes one model call at a time, so its requests and its steps pair in order. Each answer's tool-call ids are
OpenCode's call ids: a request whose calls are one step's calls is that step's, confirmed. Otherwise a request pairs by
time, in order: with the step, after the one the request before it paired with, that began nearest to when the request
began, among those that began no later than `SKEW` after it (OpenCode makes a step a moment before it asks the model);
steps passed over had requests the gateway no longer keeps. When no later step began by then, the request is another try
of the step before it (OpenCode retrying, or the gateway sending it again), and the last request of a step is its
answer; but a held request a note closed (design 0012 §9.4) pairs only with an empty step of its own, and is left out
when OpenCode kept none, so it never takes the place of the step before's answer. A step's start is OpenCode's, on the
container's clock, and a request's the gateway's, on this machine's: `SKEW` allows them to differ (to measure, plan
s15). Steps the caller leaves out (those read from the history before Clank watched) are never paired.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

SKEW = 2000  # ms the two clocks may differ
CONFIRMED = "its answer's calls are this step's calls (their ids)"
BY_TIME = "paired in order by time: no call ids confirm it"


@dataclass
class Paired:
    """A step's request: its answer, whether call ids confirmed it and why it is thought so, and its earlier tries."""

    request: str
    confirmed: bool
    why: str
    tries: list[str] = field(default_factory=list)


def began(time: Any) -> float | None:
    """When a request began, in ms since the epoch, from the time the gateway wrote (None when it cannot be read)."""
    try:
        return datetime.fromisoformat(str(time)).timestamp() * 1000
    except ValueError:
        return None


def pair(steps: list[dict[str, Any]], requests: list[dict[str, Any]]) -> dict[str, Paired]:
    """Each step's request, by its id: `steps` in order, each with `id`, `created` (ms) and `calls` (call ids);
    `requests` in any order, each with `id`, `time` (as the gateway writes it) and `calls`."""
    timed = sorted(
        ((start, request) for request in requests if (start := began(request.get("time"))) is not None),
        key=lambda found: found[0],
    )
    calls = {str(call): index for index, step in enumerate(steps) for call in step.get("calls") or []}
    found: dict[int, list[tuple[str, bool]]] = {}
    last = -1
    for start, request in timed:
        anchored = {calls[call] for call in request.get("calls") or [] if call in calls}
        if len(anchored) == 1:
            index, confirmed = anchored.pop(), True
        else:
            candidates = [
                each for each in range(last + 1, len(steps)) if (steps[each].get("created") or 0) <= start + SKEW
            ]
            if not candidates and _released(request):
                continue  # its empty step was not kept: it is never another try of the step before (design 0012 §9.4)
            index = min(candidates, key=lambda each: abs((steps[each].get("created") or 0) - start), default=last)
            confirmed = False
        if index < 0:
            continue  # it began before every step: the step it answered is not among them
        found.setdefault(index, []).append((str(request.get("id")), confirmed))
        last = max(last, index)
    paired = {}
    for index, made in found.items():
        answer, confirmed = made[-1]
        paired[str(steps[index]["id"])] = Paired(answer, confirmed, CONFIRMED if confirmed else BY_TIME,
                                                 [id for id, _ in made[:-1]])  # fmt: skip
    return paired


def _released(request: dict[str, Any]) -> bool:
    """Whether a note closed the request while it was held: the gateway answered it with an empty step of its own."""
    held = request.get("held")
    return isinstance(held, dict) and held.get("how") == "released"
