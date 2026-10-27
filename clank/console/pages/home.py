"""The home page: what happens now, what runs, what waits for the user, and what happened last (design 0002 §3.2).

Happening now: each operation that runs, waits or is queued, with its step and the last line it wrote; each model
request in flight through the gateway, with what it waits for, its time, its tokens and its speed; and how the last
model request went (or why it failed). What runs: one line for each part that runs: the service (its version, its
address, the clients following it), Docker (its state and whose containers run; `s` starts or stops it), Clank's
workspace working now (the running one started last, with how many others run; F6 lists them all), the models (each
slot, what it runs and its state; 8 opens the Models page), the GPU's memory, the gateway (where it listens, its
requests in flight and served), the machine (as last detected, and the doctor's last result; `d` runs the doctor), and
the folder the console was started in (F4 gets it ready). What waits for you: the questions, oldest first, the first one
answered with its options' keys, which are buttons under it (design 0011 §12.1; `v` shows it whole; the questions page
shows them all). The history: the newest events, newest last.

Its panels are board E1's (design 0011 §8): Happening now beside Waiting for you, a third of the row, then What runs,
then the History. The two stack, Happening now above, when the row is narrower than `STACK_BELOW` columns, or when a
question waits and the row cannot give Waiting for you `QUESTION` columns inside its border and the style's padding,
past the style's room between panels (`asking_below`; design 0011 §9: what a panel holds may ask for room). Each row of
what runs that says a state is led by its state's mark, in its state's color (`run_mark`): ● as wanted (green) or
changing (yellow), ○ not running (quiet: a part may be off as the owner wants it), ✗ failed (red), … not read yet; the
models' row has a mark for each slot; the GPU, the machine and the folder say no state and have none. A row's name and
its key's hint are quiet; a row that does not fit wraps under its value, each mark kept with the words it leads, the
hint whole. A mark is colored where the row put it, never found by its glyph, which the style may make a letter of
the words before it (design 0011 §2).

Everything comes with the console's own data: the gateway's activity, read by the console every few seconds, and the
GPU from the machine's meters, read by the service every second. While an operation runs or a model request is in
flight, its line in "happening now" has a spinner that turns.
"""

import re
import textwrap
from datetime import tzinfo
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label

from clank.console.buttons import Buttons
from clank.console.data import ConsoleData
from clank.console.gauges import size, spinner
from clank.console.keys import PageKey
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.pages.questions import answer, details, option_buttons, question_lines
from clank.console.panel import Panel, PanelGrid
from clank.console.style import current, mark
from clank.console.text import count, duration, painted, time_of, tone
from clank.kernel.console_kinds import StyleSpacing

ROW = 10
COLUMNS = "2fr 1fr"  # Happening now beside Waiting for you, a third of the row (board E1)
STACK_BELOW = 80  # side by side at 120 and 170 columns (88 and 92 for the row), stacked at 130 and 80 (58 and 56)
QUESTION = 40  # the columns a question waiting asks for, inside Waiting for you's border and padding
WHERE = Content.assemble(("questions from the agent and from Clank land here", "$clank-quiet"))
UNKNOWN = ("not read yet", "being read")  # a part's state not known yet: the `cut` mark
FAILED = ("failed", "crashed", "problem", "refused", "cannot", "unsupported", "not installed")  # the `failed` mark
SHOWN_QUESTIONS = 3
SHOWN_EVENTS = 8
UNFINISHED = ("queued", "running", "waiting")
EDGE = "edge"


Part = tuple[str, str]  # a part's state (its mark and the mark's color; "" none) and what it says
HELD = 0xE000  # a mark's place while its row wraps: a character of Unicode's private use, the first part's
GLUE = "\u00a0"  # between a mark and its words while the row wraps: textwrap breaks lines only at ASCII whitespace


def asking_below(spacing: StyleSpacing) -> int:
    """The least row that sets a question waiting beside Happening now (design 0011 §9): Waiting for you, a third of
    the row past the room between the two, holds `QUESTION` columns inside its border and the style's padding."""
    return 3 * (QUESTION + 2 + 2 * spacing.panel_padding) + spacing.columns_between


def run_mark(state: str) -> tuple[str, str]:
    """A part's state as its mark and the mark's color (design 0011 §8, board E1): `on` (●) as wanted, in `good`, or
    while it changes, in `attention`; `cut` (…) while it is not read yet, in `attention`; `failed` (✗) when it failed,
    in `failed`; `off` (○) when it does not run, in `quiet`, since a part may be off as the owner wants it."""
    word = state.strip().lower()
    if word.startswith(UNKNOWN):
        return mark("cut"), "$clank-attention"
    if word.startswith(FAILED):
        return mark("failed"), "$clank-failed"
    if tone(state) in ("$clank-good", "$clank-attention"):
        return mark("on"), tone(state)
    return mark("off"), "$clank-quiet"


def row(name: str, parts: str | list[Part], hint: str = "", width: int | None = None) -> Content:
    """A row of what runs: its name, in `quiet`; each part led by its state's mark, in its state's color; and the hint
    of the key that acts on it, in `quiet`. With a width, wrapped under the value (after its first mark), each mark kept
    with the first word it leads, the hint whole on the last line, or on a line of its own when it does not fit there.
    A row of one text says no state. While the row wraps, each mark (one character, design 0011 §2) is held by a
    character of its own (`HELD`), so it is colored where it stands once wrapped, whatever its glyph."""
    parts = [("", parts)] if isinstance(parts, str) else parts
    signs = [run_mark(state) if state else ("", "") for state, _ in parts]
    held = [chr(HELD + number) for number in range(len(parts))]
    value = "   ".join(
        f"{place}{GLUE}{text}" if sign else text for place, (sign, _), (_, text) in zip(held, signs, parts, strict=True)
    )
    indent = "  " if signs[0][0] else ""  # under the text after the first mark
    tail = f"   {hint}" if hint else ""
    if width is None:
        lines = [value + tail]
    else:
        room = max(width - ROW - 1, 20)
        lines = textwrap.wrap(value, room, subsequent_indent=indent) or [""]
        if tail and len(lines[-1]) + len(tail) <= room:
            lines[-1] += tail
        elif tail:
            lines.append(indent + hint)
    text = "\n".join([f"{name:<{ROW}} {lines[0]}", *(" " * (ROW + 1) + line for line in lines[1:])])
    placed = [(text.find(place), sign, color) for place, (sign, color) in zip(held, signs, strict=True) if sign]
    for place, (sign, _) in zip(held, signs, strict=True):
        text = text.replace(place, sign) if sign else text
    shown = Content(text.replace(GLUE, " ")).stylize("$clank-quiet", 0, len(name))
    for start, sign, color in placed:
        shown = shown.stylize(color, start, start + len(sign))
    if hint:
        shown = shown.stylize("$clank-quiet", len(text) - len(hint), len(text))
    return shown


def service_line(data: ConsoleData, width: int | None = None) -> Content:
    """The service: its version, where its API answers, and who follows it."""
    if not data.connected:
        said = "not running: `clank serve --background` starts it, or `clank console` does"
        return row("service", [("not running", said)], width=width)
    service = data.service
    clients: list[str] = service.get("clients", [])
    followers = f"{count(len(clients), 'client')} connected" + (f" ({', '.join(clients)})" if clients else "")
    address = service["url"].removeprefix("http://")
    return row("service", [("running", f"v{service['version']} · API on {address} · {followers}")], width=width)


def docker_line(docker: dict[str, Any] | None, width: int | None = None) -> Content:
    """Docker: its state and whose containers run, and the key that starts or stops it."""
    if not docker:
        return row("docker", [("not read yet", "not read yet")], width=width)
    key = "s stops it" if docker["state"] == "running" else "s starts it"
    return row("docker", [(docker["state"], docker["summary"])], key, width)


def machine_line(machine: dict[str, Any] | None, width: int | None = None) -> Content:
    """The machine as last detected, and the doctor's last result."""
    if not machine or not machine["profile"].get("detected"):
        return row("machine", "not detected yet", "d runs the doctor, which detects it", width)
    profile = machine["profile"]
    parts = [profile["system"]] + ([profile["wsl"]] if profile["wsl"] else [])
    parts += [
        f"{gpu['name'].removeprefix('NVIDIA GeForce ')} {gpu['memory_mib'] / 1024:.0f} GB" for gpu in profile["gpus"]
    ]
    parts.append(f"{profile['memory_gb']:.0f} GB RAM")
    doctor = machine["doctor"]
    if doctor:  # none yet: `clank doctor` runs without the service and keeps nothing here; `d` runs it here
        parts.append(f"doctor: {doctor['passed']} of {doctor['of']} passed")
    return row("machine", " · ".join(parts), "d runs the doctor", width)


def slot_words(status: str, reason: str) -> str:
    """A slot that does not run, in words a newcomer reads: "not loaded" for stopped, its reason when it says more than
    that ("fast: stopped (unloaded (stopped))" read like a stutter, 2026-10-26)."""
    reason = reason.removesuffix(" (stopped)")
    if status != "stopped":
        return f"{status} ({reason})" if reason else status
    return f"not loaded ({reason})" if reason and reason != "unloaded" else "not loaded"


def models_line(data: ConsoleData, width: int | None = None) -> Content:
    """Each slot shown (`ConsoleData.shown_slots`), led by its state's mark: what it runs and its state, or why it runs
    nothing; and the key of the Models page."""
    if not data.slots:
        return row("models", [("not read yet", "not read yet")], "8 opens Models", width)
    titles = {preset["id"]: preset["title"] for preset in data.presets}
    parts: list[Part] = []
    for slot in data.shown_slots():
        title = titles.get(slot["preset"] or "", slot["preset"] or "")
        if slot["status"] in ("starting", "ready", "stopping") and title:
            parts.append((slot["status"], f"{slot['name']}: {title} · {slot['status']}"))
        else:
            parts.append((slot["status"], f"{slot['name']}: {slot_words(slot['status'], slot['reason'] or '')}"))
    return row("models", parts, "8 opens Models", width)


def now_lines(
    operations: list[dict[str, Any]],
    said: dict[str, str],
    activity: dict[str, Any] | None,
    zone: tzinfo | None,
    frame: int = 0,
) -> list[Content]:
    """What happens now: each operation that runs, waits or is queued, its step and the last line it wrote; each model
    request in flight; and how the last model request went. What runs has the spinner's glyph for `frame`."""
    lines = []
    for operation in operations:
        if operation["status"] not in UNFINISHED:
            continue
        status, steps = operation["status"], operation["steps"]
        sign = spinner(frame) if status == "running" else (mark("asks") if status == "waiting" else "·")
        text = f"{sign} {operation['title']} · {status}"
        if status == "waiting":
            text += ": it asks you, below"
        elif steps:
            text += f" · step {steps[-1]['number']} of {operation['planned_steps']}: {steps[-1]['name']}"
        lines.append(painted(text, status))
        if said.get(operation["id"]):
            lines.append(Content(f"    {said[operation['id']]}"))
    requests = activity["requests"] if activity else []
    for request in requests:
        slot = f", {request['slot']} slot" if request["slot"] else ""
        text = f"{spinner(frame)} Model request ({request['role']}{slot}) · {request['phase']} · "
        text += duration(request["seconds"])
        if request["tokens"]:
            text += f" · {request['tokens']:,} token{'s' if request['tokens'] != 1 else ''}"
        if request["per_second"]:
            text += f", {request['per_second']:g} per second"
        lines.append(painted(text, request["phase"]))
    if not lines:
        lines.append(Content("Nothing runs right now."))
    last = activity["last"] if activity else None
    if last:
        lines.append(last_line(last, zone))
    return lines


def last_line(last: dict[str, Any], zone: tzinfo | None) -> Content:
    """How the last model request went: its tokens, its time and its speed, or why it failed."""
    slot = f", {last['slot']} slot" if last["slot"] else ""
    head = f"Last model request at {time_of(last['time'], zone)} ({last['role']}{slot}): "
    if last["error"] or (last["status"] or 0) >= 400:
        return painted(f"{head}failed ({last['status']}): {last['error']}", "failed")
    told = f"{last['tokens']:,} tokens in {last['seconds']:g} s"
    if last["per_second"]:
        told += f", {last['per_second']:g} per second"
    if last["left"]:
        return Content(f"{head}its client left after {told}")
    if last["prompt_tokens"]:
        told += f", after a prompt of {last['prompt_tokens']:,} tokens"
    return Content(head + told)


def cloud_line(data: ConsoleData, width: int | None = None) -> Content | None:
    """Once a cloud provider is added: the cloud's spending today and this month and the limits, or its pause, in the
    service's words (design 0016 §11); None without a provider."""
    cost = data.cost or {}
    if not data.endpoints or not cost.get("said"):
        return None
    spent = f"{cost['today']['said']} · {cost['month']['said']}"
    if cost.get("paused"):
        return row("cloud", [("failed", f"{cost['paused']['said']}; {spent}")], "L raises it", width)
    return row("cloud", f"{spent} · {cost['limits']['said']}", "0: L sets them", width)


def gateway_line(activity: dict[str, Any] | None, width: int | None = None) -> Content:
    """The gateway: where it listens, its requests in flight and how many it has served; or why it does not run."""
    if activity is None:
        return row("gateway", [("not read yet", "not read yet")], width=width)
    if activity["state"] != "running":
        why = f": {activity['problem']}" if activity["problem"] else ""
        return row("gateway", [(activity["state"], f"{activity['state']}{why}")], "F4, then g, starts it", width)
    flying = len(activity["requests"])
    doing = f"{count(flying, 'request')} in flight" if flying else "idle"
    value = f"running on port {activity['port']} · {doing} · {count(activity['served'], 'request')} served"
    if activity["problem"]:
        value += f" · {activity['problem']}"
    return row("gateway", [("running", value)], width=width)


def gpu_line(readings: list[dict[str, Any]], width: int | None = None) -> Content:
    """Each GPU now, from the machine's last reading: its use, its memory, its temperature."""
    if not readings:
        return row("gpu", "not read yet", width=width)
    gpus = readings[-1]["gpus"]
    if not gpus:
        return row("gpu", "none: no NVIDIA GPU answered", width=width)
    told = []
    for gpu in gpus:
        facts = [gpu["name"].removeprefix("NVIDIA ").removeprefix("GeForce ")]
        if gpu["use"] is not None:
            facts.append(f"{gpu['use']:.0f}% busy")
        if gpu["memory_total"]:
            facts.append(f"{size(gpu['memory_used'])} of {size(gpu['memory_total'])} in use")
        if gpu["temperature"] is not None:
            facts.append(f"{gpu['temperature']}°C")
        told.append(" · ".join(facts))
    return row("gpu", "; ".join(told), width=width)


def workspaces_line(docker: dict[str, Any] | None, width: int | None = None) -> Content:
    """The workspace working now: the running one started last, and how many others run; the Workspaces page (F6)
    lists them all."""
    if not docker:
        return row("workspace", [("not read yet", "not read yet")], width=width)
    if docker["state"] != "running":
        return row("workspace", [("none", f"none: Docker is {docker['state']}")], width=width)
    running = [
        (container["clank"].get("clank.record") or container["name"], _uptime(str(container.get("status", ""))))
        for container in docker.get("containers", [])
        if container["owner"] == "clank" and container.get("clank", {}).get("clank.component") == "workspaces"
        and container["state"] == "running" and container["clank"].get("clank.record") != EDGE
    ]  # fmt: skip
    if not running:
        return row("workspace", [("none", "none running")], "F6 lists them", width)
    name = min(running, key=lambda found: found[1])[0]
    more = f" · {len(running) - 1} more running" if len(running) > 1 else ""
    return row("workspace", [("running", f"{name}: running{more}")], "F6 lists them", width)


UPTIME = re.compile(r"Up (?:(about an?|less than a)|(\d+)) (second|minute|hour|day|week|month)", re.IGNORECASE)
SECONDS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400, "week": 604800, "month": 2592000}


def _uptime(status: str) -> float:
    """How long a container has run, in seconds, from Docker's status ("Up 24 minutes"); a container whose status
    does not say counts as the oldest."""
    found = UPTIME.search(status)
    if found is None:
        return float("inf")
    count = 1.0 if found.group(1) else float(found.group(2))
    return count * SECONDS[found.group(3).lower()]


def folder_line(folder: str, width: int | None = None) -> Content:
    """The folder the console was started in, and the page that gets it ready."""
    return row("folder", folder, "F4: get ready and work here", width)


RUNS = {"service", "docker", "machine", "slots", "activity", "meters", "folder"}  # the topics of what runs


class HomePage(Page):
    """What happens now, what runs, what waits for you, and what happened last."""

    ENTRY = MenuEntry(
        "home",
        "Home",
        "What happens now, what runs, what waits for you, and what happened last.",
        "design 0002 §3.2",
        key="1",
    )
    PANELS = ("now", "waiting", "runs", "history")
    KEYS = (
        PageKey("s", "docker", "start or stop Docker"),
        PageKey("d", "doctor", "run the doctor"),
        PageKey("v", "question", "the question whole", "the first question waiting, shown whole"),
        PageKey("y n …", "answer", "answer it with an option's key", "answer the first question waiting with one of "
                "its options' keys"),
    )  # fmt: skip

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.said: dict[str, str] = {}

    def compose(self) -> ComposeResult:
        """What happens now beside what waits for you, what runs, the history (board E1)."""
        yield PanelGrid(
            Panel(Label(id="now-text"), title="Happening now", id="now"),
            Panel(
                Label(id="waiting-text"),
                Buttons(id="waiting-options"),
                Label(id="waiting-more"),
                Label(WHERE, id="waiting-where"),
                title="Waiting for you",
                id="waiting",
            ),
            columns=COLUMNS,
            stack_below=STACK_BELOW,
            id="home-top",
        )
        with Panel(title="What runs", id="runs"):
            yield Label(id="run-service")
            yield Label(id="run-docker")
            yield Label(id="run-workspaces")
            yield Label(id="run-models")
            yield Label(id="run-cloud")
            yield Label(id="run-gpu")
            yield Label(id="run-gateway")
            yield Label(id="run-machine")
            yield Label(id="run-folder")
        with Panel(title="History", id="history"):
            yield Label(id="history-text")

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Draw the parts whose topics changed."""
        every = "all" in changed
        width = self.query_one("#runs").content_size.width or None
        if "log" in changed and data.last_log is not None:
            subject = (data.last_log.get("subject") or {}).get("id")
            if subject:
                self.said[subject] = str(data.last_log.get("summary") or "")
        if every or changed & {"operations", "log", "activity"}:
            ids = {operation["id"] for operation in data.operations}
            self.said = {id: line for id, line in self.said.items() if id in ids}
            self._draw_now(data)
        if every or changed & {"service", "connection"}:
            self.query_one("#run-service", Label).update(service_line(data, width))
        if every or "docker" in changed:
            self.query_one("#run-docker", Label).update(docker_line(data.docker, width))
            self.query_one("#run-workspaces", Label).update(workspaces_line(data.docker, width))
        if every or "activity" in changed:
            self.query_one("#run-gateway", Label).update(gateway_line(self.console.activity, width))
        if every or "meters" in changed:
            self.query_one("#run-gpu", Label).update(gpu_line(data.meters, width))
        if every or "folder" in changed:
            self.query_one("#run-folder", Label).update(folder_line(self.console.folder, width))
        if every or "machine" in changed:
            self.query_one("#run-machine", Label).update(machine_line(data.machine, width))
        if every or changed & {"slots", "presets"}:
            self.query_one("#run-models", Label).update(models_line(data, width))
        if every or changed & {"cost", "endpoints"}:
            shown = cloud_line(data, width)
            self.query_one("#run-cloud", Label).display = shown is not None
            self.query_one("#run-cloud", Label).update(shown or "")
        if every or "questions" in changed:
            first, rest = self._waiting(data)
            self.query_one("#waiting-text", Label).update(first)
            options = self.query_one("#waiting-options", Buttons)
            options.show(option_buttons(data.questions[0], self.KEYS) if data.questions else [])
            options.display = bool(data.questions)
            more = self.query_one("#waiting-more", Label)
            more.update(rest)
            more.display = bool(rest.plain)
            self.query_one("#waiting-where", Label).display = not data.questions
            asking = asking_below(current().spacing) if data.questions else STACK_BELOW
            self.query_one("#home-top", PanelGrid).stack_below = asking
        if every or "history" in changed:
            events = data.history[-SHOWN_EVENTS:]
            lines = [f"{time_of(event['time'], self.console.zone)}  {event['summary']}" for event in events]
            self.query_one("#history-text", Label).update(Content("\n".join(lines) or "Nothing recorded yet."))

    def on_resize(self, event: events.Resize) -> None:
        """Wrap the rows of what runs again for the new width."""
        self.show(self.console.data, RUNS)

    def on_panel_resized(self, message: Panel.Resized) -> None:
        """Wrap the rows of what runs again when their panel's width changes without the page's (its scroll bar)."""
        if message.panel.id == "runs":
            self.show(self.console.data, RUNS)

    def spin(self, frame: int) -> None:
        """Turn the spinners of what runs."""
        self._draw_now(self.console.data, frame)

    def press(self, key: str) -> bool:
        """`s` starts or stops Docker, `d` runs the doctor, `v` shows the first question whole, and an option's key
        answers it."""
        console, data = self.console, self.console.data
        if key == "s" and data.docker:
            console.ask_docker(data.docker["state"] == "running")
            return True
        if key == "d":
            console.run_doctor()
            return True
        if not data.questions:
            return False
        if key == "v":
            details(console, data.questions[0])
            return True
        return answer(console, data.questions[0], key)

    def explain(self) -> tuple[str, list[str]]:
        """Where each part of the home page comes from."""
        return "Home", [
            "happening now: each operation that runs, waits for your answer or is queued, with its step and the last "
            "line it wrote (the operations page, 6, shows them whole); each model request in flight through the "
            "gateway: what it waits for (its slot, while a model loads; the first token, while the engine reads the "
            "prompt), its time, its tokens and its speed; and how the last model request went.",
            f"what runs: each row that says a state is led by its mark: {mark('on')} it runs (green as wanted, yellow "
            f"while it starts or stops), {mark('off')} it does not run, {mark('failed')} it failed, {mark('cut')} not "
            "read yet; the models' row has one for each slot.",
            "service: the Clank service, its version and address, and the clients following its event stream.",
            "docker: Docker as the workspaces component reads it every few seconds (config/docker.json, "
            "poll_seconds); s starts or stops it.",
            "workspaces: Clank's workspace containers, by workspace, and the edge their agents reach the gateway "
            "through.",
            "models: each slot, what it runs and its state, or why it runs nothing; the Models page (8) shows more, "
            "and loads, switches and unloads.",
            "gpu: each GPU's use, memory and temperature, from the machine's meters (read every second; the panel "
            "on the right shows them over the last minute).",
            "gateway: where every model request goes through, its requests in flight and how many it has served.",
            "machine: the machine profile (config/machine.json), written by the doctor, and its last result; d runs "
            "the doctor.",
            "folder: the folder the console was started in; F4 shows each step of getting it ready, and a starts "
            "OpenCode there.",
            "waiting for you: the questions any part of Clank asks; answer here, on the questions page, in VS Code "
            "or with `clank questions answer`.",
            "history: the newest events; the history page (3) shows more.",
            "Designed in design 0002 §3.2.",
        ]

    def _waiting(self, data: ConsoleData) -> tuple[Content, Content]:
        """The first question waiting, but its options (a group of buttons under it, design 0011 §12.1), then the
        others, whole, and how many more wait."""
        if not data.questions:
            return Content.assemble((mark("done"), "$clank-good"), " Nothing waits for you."), Content()
        first, *others = data.questions[:SHOWN_QUESTIONS]
        lines = question_lines(first, self.console.zone)[:-1]
        shown = ["> " + lines[0], *[f"  {line}" for line in lines[1:]]]
        rest = []
        for question in others:
            lines = question_lines(question, self.console.zone)
            rest += ["  " + lines[0], *[f"  {line}" for line in lines[1:]]]
        more = len(data.questions) - SHOWN_QUESTIONS
        if more > 0:
            rest.append(f"  and {count(more, 'more question')}: the questions page (2) shows them all")
        return Content("\n".join(shown)), Content("\n".join(rest))

    def _draw_now(self, data: ConsoleData, frame: int | None = None) -> None:
        shown = self.console.frame if frame is None else frame
        happening = now_lines(data.operations, self.said, self.console.activity, self.console.zone, shown)
        self.query_one("#now-text", Label).update(Content("\n").join(happening))
