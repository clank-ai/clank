"""The machine column, the console's right side (the owner's request, 2026-10-14; design 0011 §7 and §9): the
machine's meters and what Clank is doing, always on screen while the terminal is wide enough
(`ClankConsole.HORIZONTAL_BREAKPOINTS`; F5 shows or hides it at any width). It is two panels, "Machine" and "Clank now"
(`MachineColumn`, `#machine`), and has no border of its own. Not the Monitor, the page on F10 (design 0012).

"Machine": the CPU (its use as a bar, its last seconds as a graph two cells tall, each logical processor as one cell
in its load's color), the memory (and its last seconds), each NVIDIA GPU (its use, its last seconds two cells tall, its
temperature and power, its clocks and fan, its memory), the disks (reads, writes, their last seconds, each drive's
space), the network (down, up, its last seconds),
each workspace's container (its CPU and memory) and the busiest and largest processes (an htop's first lines), from
the readings the service takes every second (`machine.meters`). "Clank now": each operation that runs, waits for an
answer or is queued, with its step, and each model request in flight, each with a spinner while it lasts; then how
the last model request went (its prompt and answer in tokens, and its speed).

Each part is a function in `MACHINE` or `NOW`: it takes what the column knows (`Seen`) and the width inside its panel,
and gives its lines. Adding a meter is adding a function to a list; the order of the list is the order on screen.
Colors are the style's (`gauges.py`), the column's width and when it shows are in `clank.tcss` (`#machine`). The
Machine panel's room is the column's height less the Clank now panel (its lines and its two borders), its own two
borders and the row between them: when that room holds them, a blank line parts one meter from the next; when it does
not, the blank lines go first, then the last meters, whole, and the panel's note says how many are hidden. The column
draws itself again when its size changes. Each graph says, in the names' column, how many seconds it covers (as many
as fit, one a cell), and after it its peak over those seconds ("max 62%", "max 1.2 MB/s"); the processors' row is marked
"thr". A rate's graph is scaled to its largest rate of those seconds, and never below `QUIET_DISK` or `QUIET_NET`, so an
idle machine's small traffic stays small.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import tzinfo
from typing import Any

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.content import Content
from textual.widgets import Label

from clank.console.gauges import bar, fit, level, rate, size, spark, spinner, tall_spark
from clank.console.panel import Panel
from clank.console.style import current, mark
from clank.console.text import time_of

NAME = 5  # the width of a meter's name: "CPU  "
QUIET_DISK = float(1 << 20)  # a sparkline of disk traffic is never scaled below a megabyte a second
QUIET_NET = float(100 << 10)  # nor one of network traffic below 100 KB a second
CRAMPED = 1 << 30  # less GPU memory free than this is said: Windows draws the desktop and its windows with it too
UNFINISHED = ("queued", "running", "waiting")
TOLD = 13  # a graph's peak, right-aligned in a column of its own: "max 14.2 MB/s"


@dataclass
class Seen:
    """What the panel draws from: the readings (oldest first), the operations, the gateway's activity, the spinner's
    frame and the user's time zone."""

    readings: list[dict[str, Any]] = field(default_factory=list)
    operations: list[dict[str, Any]] = field(default_factory=list)
    activity: dict[str, Any] | None = None
    frame: int = 0
    zone: tzinfo | None = None


Part = Callable[[Seen, int], list[Content]]


def named(name: str, rest: Content | str) -> Content:
    """A meter's line: its name, bold, in a column of its own, then the rest."""
    return Content.assemble((f"{name:<{NAME}}", "bold"), rest)


def gauge(name: str, share: float, width: int) -> Content:
    """A meter's first line: its name, a bar and the share in percent."""
    return named(name, Content.assemble(bar(share, max(width - NAME - 5, 4)), (f" {share * 100:3.0f}%", level(share))))


def below(text: str | Content, width: int) -> Content:
    """A meter's further line, under its bar."""
    content = Content(fit(text, width - NAME)) if isinstance(text, str) else text
    return Content.assemble(" " * NAME, content)


def recent(values: list[float], width: int, top: float, told: str, tall: bool = False) -> list[Content]:
    """A meter's last seconds as a graph under it (two cells tall when `tall`): how many seconds it covers in the names'
    column, then the graph, then `told` (its peak)."""
    room = max(width - NAME - TOLD - 1, 4)
    shown = values[-room:]
    seconds = Content.assemble((f"{len(shown)}s".ljust(NAME), "dim"))
    after = Content.assemble((f" {told:>{TOLD}}", "dim"))
    if not tall:
        return [Content.assemble(seconds, spark(shown, room, top), after)]
    upper, lower = tall_spark(shown, room, top)
    return [Content.assemble(" " * NAME, upper), Content.assemble(seconds, lower, after)]


def peak(values: list[float], width: int, told: Callable[[float], str]) -> str:
    """The largest of the values a graph of this width shows, as `told` says it."""
    room = max(width - NAME - TOLD - 1, 4)
    return told(max(values[-room:], default=0))


def cpu(seen: Seen, width: int) -> list[Content]:
    """The CPU: its use, its last seconds two cells tall with their peak, and each logical processor as one cell."""
    last = seen.readings[-1]
    history = [r["cpu"] for r in seen.readings]
    lines = [gauge("CPU", last["cpu"] / 100, width)]
    lines += recent(history, width, 100.0, peak(history, width, lambda top: f"max {top:.0f}%"), tall=True)
    cores, room = last["cores"], width - NAME
    if cores:
        group = -(-len(cores) // room)  # threads a cell, so they fit: the busiest of each group shows
        cells = [max(cores[start : start + group]) for start in range(0, len(cores), group)]
        told = f" {len(cores)} threads" if len(cells) + len(f" {len(cores)} threads") <= room else ""
        sparks = current().sparks
        glyphs = [(sparks[min(int(cell / 100 * len(sparks)), len(sparks) - 1)], level(cell / 100)) for cell in cells]
        lines.append(Content.assemble(("thr".ljust(NAME), "dim"), *glyphs, (told, "$clank-quiet")))
    return lines


def memory(seen: Seen, width: int) -> list[Content]:
    """The memory in use, and the page file when it is used."""
    last = seen.readings[-1]
    used, total = last["memory_used"], last["memory_total"]
    told = f"{size(used)} of {size(total)}"
    page = f" · page file {size(last['swap_used'])}" if last.get("swap_used") else ""
    if len(told) + len(page) <= width - NAME:
        told += page
    history = [r["memory_used"] / r["memory_total"] * 100 for r in seen.readings if r.get("memory_total")]
    lines = [gauge("RAM", used / total if total else 0, width), below(told, width)]
    return lines + recent(history, width, 100.0, peak(history, width, lambda top: f"max {top:.0f}%"))


def gpus(seen: Seen, width: int) -> list[Content]:
    """Each GPU: its use and last minute, its name, temperature and power, its memory."""
    lines: list[Content] = []
    for index, gpu in enumerate(seen.readings[-1]["gpus"]):
        if gpu["use"] is not None:
            history = [r["gpus"][index]["use"] or 0 for r in seen.readings if len(r["gpus"]) > index]
            lines.append(gauge("GPU", gpu["use"] / 100, width))
            lines += recent(history, width, 100.0, peak(history, width, lambda top: f"max {top:.0f}%"), tall=True)
        facts = [gpu["name"].removeprefix("NVIDIA ").removeprefix("GeForce ")]
        if gpu["temperature"] is not None:
            facts.append(f"{gpu['temperature']}°C")
        if gpu["power"] is not None:
            facts.append(f"{gpu['power']:.0f} W")
        lines.append(below(" · ".join(facts), width))
        clocks = []
        if gpu.get("clock"):
            clocks.append(f"{gpu['clock']:,} MHz")
        if gpu.get("memory_clock"):
            clocks.append(f"memory {gpu['memory_clock'] / 1000:.1f} GHz")
        if gpu.get("fan") is not None:
            clocks.append(f"fan {gpu['fan']}%")
        if clocks:
            lines.append(below(Content.assemble((fit(" · ".join(clocks), width - NAME), "$clank-quiet")), width))
        if gpu["memory_total"]:
            share = gpu["memory_used"] / gpu["memory_total"]
            lines += [
                gauge("VRAM", share, width),
                below(f"{size(gpu['memory_used'])} of {size(gpu['memory_total'])}", width),
            ]
            if gpu["memory_total"] - gpu["memory_used"] < CRAMPED:
                lines.append(
                    below(
                        Content.assemble((fit("little room for the desktop", width - NAME), "$clank-attention")), width
                    )
                )
    return lines


def disks(seen: Seen, width: int) -> list[Content]:
    """The disks' reads and writes, and each fixed drive's space."""
    last = seen.readings[-1]
    lines = [named("Disk", fit(f"read {rate(last['disk_read'])} · write {rate(last['disk_write'])}", width - NAME))]
    lines += traffic([r["disk_read"] + r["disk_write"] for r in seen.readings], width, QUIET_DISK)
    for drive in last["drives"]:
        mount = drive["mount"].rstrip("\\/") or "/"
        share = drive["used"] / drive["total"] if drive["total"] else 0
        room = width - NAME - len(mount) - 6
        if room >= 4:
            lines.append(
                below(Content.assemble(f"{mount} ", bar(share, room), (f" {share * 100:3.0f}%", level(share))), width)
            )
    return lines


def network(seen: Seen, width: int) -> list[Content]:
    """The network's traffic, down and up."""
    last = seen.readings[-1]
    history = [r["net_down"] + r["net_up"] for r in seen.readings]
    return [named("Net", fit(f"↓ {rate(last['net_down'])}  ↑ {rate(last['net_up'])}", width - NAME)),
            *traffic(history, width, QUIET_NET)]  # fmt: skip


def processes(seen: Seen, width: int) -> list[Content]:
    """The busiest processes, then the largest: each one's name, its share of the CPU and its memory."""
    rows = seen.readings[-1].get("processes") or []
    if not rows:
        return []
    name = max(width - NAME - 14, 6)
    lines = [named("Top", Content.assemble((fit(f"{'':<{name}}  cpu   memory", width - NAME), "$clank-quiet")))]
    for row in rows:
        busy = Content.assemble((f"{row['cpu']:4.0f}%", level(row["cpu"] / 100)))
        lines.append(below(Content.assemble(f"{fit(row['name'].removesuffix('.exe'), name):<{name}} ", busy,
                                            f" {size(row['memory']):>7}"), width))  # fmt: skip
    return lines


def containers(seen: Seen, width: int) -> list[Content]:
    """Each workspace's container: its share of the CPU and its memory (Docker says it every ten seconds)."""
    rows = seen.readings[-1].get("containers") or []
    lines = []
    for number, row in enumerate(rows):
        share = row["memory_used"] / row["memory_total"] if row["memory_total"] else 0
        room = max(width - NAME - 21, 6)
        told = Content.assemble(
            f"{fit(row['name'], room):<{room}} ",
            (f"{row['cpu']:3.0f}%", level(row["cpu"] / 100)),
            (f" {size(row['memory_used'])}", level(share)),
            (f" of {size(row['memory_total'])}", "$clank-quiet"),
        )
        lines.append(named("Work", told) if number == 0 else below(told, width))
    return lines


def traffic(rates: list[float], width: int, quiet: float) -> list[Content]:
    """A rate's last seconds as a graph, scaled to its largest rate, never below `quiet`, with its peak after it."""
    told = peak(rates, width, lambda top: f"max {rate(top)}")
    room = max(width - NAME - TOLD - 1, 4)
    return recent(rates, width, max([quiet, *rates[-room:]]), told)


def operations(seen: Seen, width: int) -> list[Content]:
    """Each operation that runs, waits for an answer or is queued, with its step."""
    lines = []
    for operation in seen.operations:
        status = operation["status"]
        if status not in UNFINISHED:
            continue
        steps = operation["steps"]
        if status == "waiting":
            sign, told, style = mark("asks"), "asks you", "$clank-attention"
        elif status == "queued":
            sign, told, style = "·", "queued", "$clank-quiet"
        else:
            sign, style = spinner(seen.frame), "$clank-now"
            told = f"{steps[-1]['number']}/{operation['planned_steps']} {steps[-1]['name']}" if steps else "starting"
        text = fit(f"{operation['title']} · {told}", width - 2)
        lines.append(Content.assemble((sign, style), " ", text))
    return lines


def requests(seen: Seen, width: int) -> list[Content]:
    """Each model request in flight through the gateway, and how the last one went."""
    activity = seen.activity
    if activity is None:
        return []
    if activity["state"] != "running":
        return [Content.assemble((mark("on"), "$clank-failed"), f" gateway {activity['state']}")]
    lines = []
    for request in activity["requests"]:
        told = ([request["role"]] if request["role"] != "agent" else []) + [
            request["phase"]
        ]  # the agent is the usual one
        if request["tokens"]:
            told.append(f"{request['tokens']:,} tok")
        if request["per_second"]:
            told.append(f"{request['per_second']:.0f}/s")
        lines.append(Content.assemble((spinner(seen.frame), "$clank-now"), " ", fit(" · ".join(told), width - 2)))
    last = activity["last"]
    if last:
        if last["error"] or (last["status"] or 0) >= 400:
            failed = f"last request failed ({last['status']})"
            lines.append(Content.assemble((mark("failed"), "$clank-failed"), " ", fit(failed, width - 2)))
        else:
            parts = [f"last {time_of(last['time'], seen.zone)}"]
            if last.get("prompt_tokens"):
                parts.append(f"{last['prompt_tokens']:,} in")
            parts.append(f"{last['tokens']:,} out")
            if last["per_second"]:
                parts.append(f"{last['per_second']:.0f}/s")
            lines.append(
                Content.assemble(
                    (mark("done"), "$clank-good"), " ", (fit(" · ".join(parts), width - 2), "$clank-quiet")
                )
            )
    return lines


MACHINE: list[Part] = [cpu, memory, gpus, disks, network, containers, processes]
NOW: list[Part] = [operations, requests]


def busy(seen: Seen) -> bool:
    """Whether something runs that a spinner shows: an operation running, or a model request in flight."""
    running = any(operation["status"] == "running" for operation in seen.operations)
    return running or bool(seen.activity and seen.activity.get("requests"))


def stacked(blocks: list[list[Content]], room: int) -> tuple[list[Content], int]:
    """The meters' lines in `room` rows, and how many meters were left out: a blank line between two meters when they
    all fit so; else none; else without the last meters, whole, the first always kept."""
    if sum(len(block) for block in blocks) + len(blocks) - 1 <= room:
        return [line for number, block in enumerate(blocks) for line in ([Content("")] if number else []) + block], 0
    shown = list(blocks)
    while len(shown) > 1 and sum(len(block) for block in shown) > room:
        shown.pop()
    return [line for block in shown for line in block], len(blocks) - len(shown)


class MachineColumn(Vertical):
    """The machine's meters and what Clank is doing, at the console's right: the panels "Machine" and "Clank now"."""

    def __init__(self, id: str | None = None) -> None:
        super().__init__(id=id)
        self._seen: Seen | None = None  # as last drawn, to draw again for a new size
        self._now = 0  # the lines of Clank now as last drawn

    def compose(self) -> ComposeResult:
        """The machine, then Clank now."""
        yield Panel(Label(id="machine-meters"), title="Machine", id="machine-meters-panel")
        yield Panel(Label(id="machine-now"), title="Clank now", id="machine-now-panel")

    def on_resize(self, event: events.Resize) -> None:
        """Draw both panels again for the column's new size (the terminal's changed)."""
        if self.display and self._seen is not None:
            self.draw(self._seen)

    def draw(self, seen: Seen, machine: bool = True) -> None:
        """Draw both panels, each line for the inside of its panel (only Clank now when `machine` is False, a turn of
        the spinner, unless Clank now's lines changed in number, which changes the Machine panel's room). The Machine
        panel's room is the column's height less the Clank now panel (its lines and its two borders), its own two
        borders and the row between them; its note says how many meters that room left out."""
        self._seen = seen
        meters = self.query_one("#machine-meters-panel", Panel)
        spacing = current().spacing
        width = max(meters.content_size.width or self.size.width - 2 - 2 * spacing.panel_padding, 20)
        now = [line for part in NOW for line in part(seen, width)]
        if machine or max(len(now), 1) != self._now:
            blocks = [lines for part in MACHINE if (lines := part(seen, width))] if seen.readings else []
            room = self.size.height - (max(len(now), 1) + 2) - 2 - spacing.rows_between
            lines, hidden = stacked(blocks, room)
            shown = Content("\n").join(lines) if lines else Content("the meters are being read")
            self.query_one("#machine-meters", Label).update(shown)
            meters.note = f"{hidden} {'meter' if hidden == 1 else 'meters'} hidden" if hidden else ""
        self._now = max(len(now), 1)
        self.query_one("#machine-now", Label).update(Content("\n").join(now) if now else Content("idle"))
