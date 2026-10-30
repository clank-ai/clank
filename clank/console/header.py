"""The console's header (design 0001 §5, design 0004 §9, design 0011 §7): one row on `bars`, the same on every page:
"◆ CLANK" bold in `brand`, the name of the folder the console was started in, in `name`, then a pill for each part that
runs, its dot and its few words whole in its state's color (the service and how long it has been up, Docker, the model
in the main slot, dev mode while it is on (decisions 0149 and 0152, in `attention`: "dev mode: any provider, any host",
whatever providers there are), the gateway, the cloud's spending once a provider is added (in the service's words,
design 0016 §11, a pause in `failed`), the questions waiting), then a spinner in `now` while something runs. The clock
is on the right, a label of its own, in `quiet` (`clank.tcss`). When the header is too narrow for every pill's words,
the model's advice says its short words first, then the cloud's pill, then dev mode's, then every pill does.

Each pill is a function in `PILLS`: it takes the console's data, the gateway's activity and the time now, and gives a
`Said`: its words, its short words, and the state the pill is colored by (`text.tone`); or nothing when it has nothing
to say. The order of the list is the order on screen.
"""

from collections.abc import Callable
from datetime import datetime
from pathlib import PureWindowsPath
from typing import Any, NamedTuple

from textual.content import Content

from clank.console.data import ConsoleData
from clank.console.gauges import spinner
from clank.console.style import mark
from clank.console.text import duration, parse, tone


class Said(NamedTuple):
    """What a pill says: its words, its short words, and its state."""

    words: str
    short: str
    state: str


Pill = Callable[[ConsoleData, dict[str, Any] | None, datetime], Said | None]


def service(data: ConsoleData, activity: dict[str, Any] | None, now: datetime) -> Said:
    """The service: up, and for how long; or not running."""
    if not data.connected:
        return Said("service not running", "service", "stopped")
    started = data.service.get("started")
    up = f" {duration((now - parse(started)).total_seconds())}" if started else ""
    return Said(f"service up{up}", "service", "running")


def docker(data: ConsoleData, activity: dict[str, Any] | None, now: datetime) -> Said | None:
    """Docker's state."""
    if not data.connected or not data.docker:
        return None
    return Said(f"docker {data.docker['state']}", "docker", data.docker["state"])


def model(data: ConsoleData, activity: dict[str, Any] | None, now: datetime) -> Said | None:
    """What the main slot runs, and its state."""
    main = next((slot for slot in data.slots if slot["name"] == "main"), None)
    if not data.connected or main is None:
        return None
    titles = {preset["id"]: preset["title"] for preset in data.presets}
    title = titles.get(main["preset"] or "", main["preset"] or "")
    if main["status"] == "ready":
        return Said(title, title, "ready")
    if main["status"] in ("starting", "stopping") and title:
        return Said(f"{title} {main['status']}", title, main["status"])
    if data.usable is not None and not data.usable.get("usable", True):  # design 0016 §14
        return Said("no model: Add a model", "no model", "stopped")
    return Said("no model", "no model", "stopped")


def dev(data: ConsoleData, activity: dict[str, Any] | None, now: datetime) -> Said | None:
    """Dev mode, while it is on (decisions 0149 and 0152): every cloud provider asked for any of a model's providers,
    and every public host open to the agent. As the console reads it (`data.dev`), whatever providers there are; as
    each provider's view says, from a service that does not say it alone."""
    if data.dev is not None:
        on = bool(data.dev.get("on"))
    else:
        on = any(each.get("dev_mode") for each in data.endpoints or [])
    if not data.connected or not on:
        return None
    return Said("dev mode: any provider, any host", "dev mode", "waiting")


def gateway(data: ConsoleData, activity: dict[str, Any] | None, now: datetime) -> Said | None:
    """The gateway: running (and its requests in flight), or not."""
    if not data.connected or activity is None:
        return None
    if activity["state"] != "running":
        return Said(f"gateway {activity['state']}", "gateway", activity["state"])
    flying = len(activity["requests"])
    return Said(f"gateway · {flying} in flight" if flying else "gateway", "gateway", "running")


def questions(data: ConsoleData, activity: dict[str, Any] | None, now: datetime) -> Said | None:
    """The questions waiting for the user, when there are some."""
    waiting = len(data.questions)
    if not waiting:
        return None
    return Said(f"{waiting} question{'s' if waiting > 1 else ''} waiting", f"{waiting} waiting", "waiting")


def cloud(data: ConsoleData, activity: dict[str, Any] | None, now: datetime) -> Said | None:
    """Once a cloud provider is added and the cloud was used this month: its spending today and this month, in the
    service's words (design 0016 §11); a pause, and its key."""
    cost = data.cost or {}
    said = cost.get("said")
    if not data.connected or not data.endpoints or not said:
        return None
    paused, warned = cost.get("paused"), cost.get("warned")
    if not ((cost.get("month") or {}).get("requests") or paused or warned):
        return None  # nothing sent to the cloud this month: nothing to say yet
    if paused:
        return Said(f"{paused['said']} · L raise", "cloud paused", "failed")
    return Said(str(said), "cloud", "waiting" if warned else "")


PILLS: list[Pill] = [service, docker, model, dev, gateway, cloud, questions]


def header(
    data: ConsoleData,
    activity: dict[str, Any] | None,
    now: datetime,
    heard: bool,
    frame: int | None,
    folder: str = "",
    width: int = 0,
) -> Content:
    """The header's left part: Clank's name, the folder's name, the pills, and the spinner's glyph while something runs
    (`frame`); each pill's short words when the whole would be wider than `width` (0: as wide as it is)."""
    name = PureWindowsPath(folder).name if folder else ""
    head: list[Content | tuple[str, str] | str] = [(f" {mark('brand')} CLANK", "bold $clank-brand")]
    if name:
        head += ["  ", (name, "$clank-name")]
    if not heard:
        return Content.assemble(*head, "   ", (mark("on"), "$clank-attention"), " connecting")
    found = [(pill, told) for pill in PILLS if (told := pill(data, activity, now)) is not None]
    said = [told for _, told in found]
    tail: list[Content | tuple[str, str] | str] = []
    if frame is not None:
        tail += ["  ", (f"{spinner(frame)} working", "$clank-now")]
    advice = {index for index, (pill, told) in enumerate(found) if pill is model and told.words != told.short
              and told.state == "stopped"}  # "no model: Add a model" goes short first  # fmt: skip
    longest = {index for index, (pill, _) in enumerate(found) if pill is cloud}  # then the cloud's words
    devs = {index for index, (pill, _) in enumerate(found) if pill is dev}  # then dev mode's
    for shortened in (set(), advice, advice | longest, advice | longest | devs, set(range(len(said)))):
        parts = list(head)
        for index, pill in enumerate(said):
            words = pill.short if index in shortened else pill.words
            parts += ["   " if index == 0 else "  ", (f"{mark('on')} {words}", tone(pill.state) or "$clank-quiet")]
        shown = Content.assemble(*parts, *tail)
        if not width or len(shown.plain) <= width:
            break
    return shown
