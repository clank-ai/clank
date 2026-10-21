"""The Models page (design 0003 §8.1, design 0001 §5.2): each slot, what it runs and since when, the memory it took,
and the last switches.

Each slot shows its state since when and why, and what it runs: the preset, the model, the serving setup at its
version on its host, the port and the process. The highlighted slot's memory: what its engine took once ready, what it
needed free to start when its engine says so, beside its estimate; and the GPU's use now, read every few
seconds while the page is on screen. The last switches are the newest launches. `l` loads a preset picked from a list
into the slot, `w` switches it to one, `u` unloads it, `c` checks its preset (or one picked, when it runs nothing),
each item of the check in a window. Every action is an operation of the service: the operations page follows it, and
the message line says what was asked, or why the service refused. Its panels, "Slots", "Memory" and "Last switches",
are board E9's (design 0011 §8). A slot that runs a cloud preset (design 0016 §15) says its provider and model, its
window, and its last health in its reason (a provider not reached says since when); its memory is none of this
computer's.
"""

from collections.abc import Callable
from typing import Any

from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label, ListView

from clank.components.runtime.console.common import show_check
from clank.console import actions
from clank.console.data import ConsoleData
from clank.console.gauges import fit, spinner
from clank.console.keys import PageKey
from clank.console.lists import refill
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.pick import PickScreen, preset_choices
from clank.console.style import mark
from clank.console.text import painted, time_of, tone

GPU_SECONDS = 5.0
SHOWN_LAUNCHES = 8
RUNS = ("starting", "ready", "stopping")
OUTCOME = {"ready": "runs"}  # a switch's outcome as the page says it, colored by its state


def slot_text(slot: dict[str, Any], presets: dict[str, dict[str, Any]], zone: Any) -> str:
    """A slot: its state since when and why; then what it runs and where."""
    head = f"{slot['name']}  {slot['status'].upper()} since {time_of(slot['since'], zone)}: {slot['reason']}"
    if not slot["preset"]:
        return head
    preset = presets.get(slot["preset"])
    what = [preset["title"] if preset else slot["preset"]]
    if preset is not None and preset.get("endpoint"):
        window = preset["options"].get("context")
        what += [preset["model"], preset.get("provider") or f"cloud {preset['endpoint']}"]
        what += [f"window {window:,}"] if window else []
        return f"{head}\n      {' · '.join(what)}"
    if preset is not None:
        setup = f"{preset['engine']} {preset['engine_version']}" + (f" on {slot['host']}" if slot["host"] else "")
        what += [preset["model"], setup]
    if slot["status"] in RUNS:
        what += [f"port {slot['port']}"] if slot["port"] else []
        what += [f"process {slot['pid']}"] if slot["pid"] else []
    return f"{head}\n      {' · '.join(what)}"


def memory_text(
    slot: dict[str, Any] | None,
    launches: list[dict[str, Any]],
    gpu: dict[str, int] | None,
    cloud: bool = False,
) -> str:
    """What the slot's engine took (and needed to start) beside its estimate; the GPU's use now. A cloud model takes
    none of it."""
    lines = []
    launch = next((each for each in launches if slot and each["id"] == slot["launch_id"]), None)
    if cloud and slot is not None and slot["status"] in RUNS:
        lines.append("It runs at OpenRouter's provider: none of this computer's GPU.")
    elif slot is None or slot["status"] not in RUNS or launch is None:
        lines.append("It runs nothing.")
    elif launch["measured_mib"] is None:
        estimate = launch["estimate_mib"]
        lines.append(f"Not measured yet (estimated {estimate:,} MiB)." if estimate is not None else "Not measured yet.")
    else:
        beside = [f"needed {launch['needed_mib']:,} MiB free to start"] if launch["needed_mib"] is not None else []
        beside += [f"estimated {launch['estimate_mib']:,}"] if launch["estimate_mib"] is not None else []
        lines.append(f"it took {launch['measured_mib']:,} MiB" + (f" ({'; '.join(beside)})" if beside else ""))
    if gpu is None:
        lines.append("the GPU's memory cannot be read: nvidia-smi does not answer")
    else:
        lines.append(f"the GPU: {gpu['used_mib']:,} of {gpu['total_mib']:,} MiB in use, {gpu['free_mib']:,} free")
    return "\n".join(lines)


def launch_line(launch: dict[str, Any], presets: dict[str, dict[str, Any]], zone: Any) -> str:
    """One switch: when, the preset, and how it went."""
    preset = presets.get(launch["preset"])
    title = preset["title"] if preset else launch["preset"]
    how = []
    if launch["seconds"] is not None:
        how.append(f"ready in {launch['seconds']:.0f} s")
    if launch["measured_mib"] is not None:
        how.append(f"{launch['measured_mib']:,} MiB")
    ended = launch["outcome"] if launch["outcome"] != "ready" else "runs"
    if launch["outcome"] == "failed" and launch["detail"]:
        ended = f"failed: {launch['detail']}"
    how.append(ended)
    line = f"{time_of(launch['started_at'], zone)}  {title:<22}  {' · '.join(how)}"
    return fit(line, 110)


class ModelsPage(Page):
    """Each slot, what it runs, the memory it took, and the last switches."""

    ENTRY = MenuEntry(
        "models",
        "Models",
        "Each slot: what it runs and since when, the memory it took, the last switches; l loads, w switches, "
        "u unloads, c checks.",
        "design 0003 §8.1",
        key="8",
    )
    PANELS = ("models-slots-panel", "models-memory-panel", "models-switches")
    KEYS = (
        PageKey("l", "load", "load", "load a preset in the highlighted slot"),
        PageKey("w", "switch", "switch", "switch the highlighted slot to another preset"),
        PageKey("u", "unload", "unload"),
        PageKey("c", "check", "check", "check the preset the slot runs"),
    )
    _gpu: dict[str, int] | None = None

    def badge(self, frame: int) -> Content | None:
        """The main slot: a dot in its state's color, or a spinner while it starts or stops."""
        main = next((slot for slot in self.console.data.slots if slot["name"] == "main"), None)
        if main is None:
            return None
        if main["status"] in ("starting", "stopping"):
            return Content.assemble((spinner(frame), "$clank-now"))
        return Content.assemble((mark("on"), tone(main["status"]) or "$clank-quiet"))

    def compose(self) -> ComposeResult:
        """The slots; the highlighted one's memory; the last switches; the keys."""
        with Panel(title="Slots", id="models-slots-panel"):
            yield ListView(id="models-slots")
        with Panel(title="Memory", id="models-memory-panel"):
            yield Label(id="models-memory")
        with Panel(title="Last switches", id="models-switches"):
            yield Label(id="models-launches")

    def on_mount(self) -> None:
        """Draw what the console holds; read the GPU now and every few seconds while the page is on screen."""
        super().on_mount()
        self.set_interval(GPU_SECONDS, self._read_gpu)
        self._read_gpu()

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Draw the slots, the memory and the switches again when what they show changed."""
        if not changed & {"all", "slots", "presets", "launches", "gpu"}:
            return
        presets = {preset["id"]: preset for preset in data.presets}
        listed = self.query_one("#models-slots", ListView)
        if changed & {"all", "slots", "presets"}:
            lines = [
                painted(slot_text(slot, presets, self.console.zone), slot["status"].upper())
                for slot in data.shown_slots()
            ]
            refill(listed, lines)
        selected = self._selected()
        cloud = bool(presets.get((selected or {}).get("preset") or "", {}).get("endpoint"))
        self.query_one("#models-memory", Label).update(memory_text(selected, data.launches, self._gpu, cloud))
        lines = [
            painted(launch_line(launch, presets, self.console.zone), OUTCOME.get(launch["outcome"], launch["outcome"]))
            for launch in data.launches[:SHOWN_LAUNCHES]
        ]
        self.query_one("#models-launches", Label).update(Content("\n").join(lines) if lines else "No switch yet.")

    def press(self, key: str) -> bool:
        """`l` loads, `w` switches, `u` unloads, `c` checks."""
        slot = self._selected()
        if slot is None or key not in ("l", "w", "u", "c"):
            return False
        name, client = slot["name"], self.console.client
        if key == "u":
            done = f"asked to unload {name}"
            actions.call(self.console, lambda: client.post(f"runtime/slots/{name}/unload"), done=done)
        elif key in ("l", "w"):
            verb = "load" if key == "l" else "switch"

            def chosen(preset: str) -> None:
                def post() -> Any:
                    return client.post(f"runtime/slots/{name}/{verb}", {"preset": preset})

                actions.call(self.console, post, done=f"asked to {verb} {self._title(preset)} in {name}")

            title = f"Load a preset in {name}" if key == "l" else f"Switch {name} to a preset"
            self._pick(title, chosen)
        elif slot["preset"] and slot["status"] in RUNS:
            self._check(slot["preset"])
        else:
            self._pick("Check a preset", self._check)
        return True

    def explain(self) -> tuple[str, list[str]]:
        """What the highlighted slot is, and what the keys do."""
        slot = self._selected()
        if slot is None:
            return super().explain()
        return f"Slot {slot['name']}", [
            f"{slot['status']} since {time_of(slot['since'], self.console.zone)}: {slot['reason']}.",
            "A slot runs one preset at a time (design 0003 §6). l loads a preset into it when it runs nothing; w "
            "switches it, and goes back to the last configuration that worked when the new one fails; u unloads it; c "
            "checks its preset without starting anything.",
            "The memory is what the engine took once ready, and, for an engine that reserves more than it uses, "
            "what it needed free to start: the next estimate learns from that.",
        ]

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Show the highlighted slot's memory."""
        if event.list_view.id == "models-slots":
            self.draw(self.console.data, {"gpu"})

    def _selected(self) -> dict[str, Any] | None:
        slots = self.console.data.shown_slots()
        index = self.query_one("#models-slots", ListView).index
        if index is None or not 0 <= index < len(slots):
            return slots[0] if slots else None
        return slots[index]

    def _title(self, preset: str) -> str:
        return next((each["title"] for each in self.console.data.presets if each["id"] == preset), preset)

    def _pick(self, title: str, then: Callable[[str], None]) -> None:
        def picked(value: str | None) -> None:
            if value is not None:
                then(value)

        self.console.push_screen(PickScreen(title, preset_choices(self.console.data.presets)), picked)

    def _check(self, preset: str) -> None:
        show_check(self, preset, self._title(preset))

    def _read_gpu(self) -> None:
        if not self.display:
            return
        client = self.console.client

        def work() -> None:
            try:
                found = client.get("runtime/gpu")
            except Exception:
                return
            self.console.call_from_thread(self._show_gpu, found)

        self.run_worker(work, thread=True, group="gpu", exclusive=True, exit_on_error=False)

    def _show_gpu(self, found: dict[str, int] | None) -> None:
        self._gpu = found
        self.draw(self.console.data, {"gpu"})
