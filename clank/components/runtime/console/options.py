"""The Launch options page (design 0003 §8.2, design 0001 §3.5): a preset's options and what each one becomes.

Each launch option of the preset's serving setup at its version: its value, where the value comes from (the preset, or
Clank's default for that engine), what the engine receives for it (its flags, or environment variables), or why it
receives nothing (the value is the engine's own default, or a requirement the preset does not meet), and what it does;
then the exact command line the preset produces and its memory estimate with its fit in the GPU's memory now. All of it
comes from the preset's plan, read off the screen's thread. The page shows the preset chosen with `o` on the Presets
page, else the one the main slot runs, else the first; `p` picks another, and `e` opens the preset's file in the
editor the system gives JSON files. Changing a value is M2's (with trials); until then, its file is where to change it.
Each option is a row (`console/rows.py`): its name, then its value and where it comes from, what the engine receives,
and what it does, each on a line of its own that wraps under itself, so the page reads well in a narrow window. It is
one panel, titled with the preset's name as board E12 writes it ("daily 262K: launch options"; design 0011 §8).
"""

import os
import subprocess
import sys
from typing import Any
from urllib.parse import quote

from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label

from clank.console.data import ConsoleData
from clank.console.keys import PageKey
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.pick import PickScreen, preset_choices
from clank.console.rows import Rows

SOURCES = {"preset": "the preset", "Clank's default": "Clank's default", "unset": "(not set)"}
TITLE = "Launch options"  # the panel's title until a preset's plan is read; then "<its title>: launch options"


def open_file(path: str) -> None:
    """Open a file in the editor the system gives its kind of file."""
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.run(["open", path], check=False)
    else:
        subprocess.run(["xdg-open", path], check=False)


def value_text(option: dict[str, Any]) -> str:
    """An option's value as people read it: 8,192 tokens, on, q4."""
    value = option["value"]
    if value is None:
        return "(none)"
    if isinstance(value, bool):
        return "on" if value else "off"
    if isinstance(value, int | float):
        number = f"{value:,}" if isinstance(value, int) or float(value).is_integer() else f"{value:g}"
        return f"{number} {option['unit']}".strip()
    return str(value)


def option_value(option: dict[str, Any]) -> Content:
    """An option's value and where it comes from; what the engine receives (or why nothing); what it does."""
    gives = " ".join(option["gives"])
    if gives:
        received = Content.assemble((gives, "$clank-text"))
    else:
        received = Content.assemble((f"({option['left_out']})" if option["left_out"] else "(nothing)", "dim"))
    source = SOURCES.get(option["source"], option["source"])
    first = Content.assemble((value_text(option), "bold"), ("  ·  ", "dim"), (source, "dim"))
    return Content("\n").join([first, received, Content.assemble((option["help"], "dim"))])


def plan_rest(plan: dict[str, Any] | None) -> str:
    """After the options: the command line and the memory, or why the preset cannot be planned."""
    if plan is None:
        return "Being read."
    if plan["problem"]:
        return f"It cannot be planned: {plan['problem']}"
    lines = ["the command line:", plan["command_line"], "", "memory:", *plan["fit"]["lines"]]
    lines += [f"  {note}" for note in plan["memory"]["notes"]]
    return "\n".join(lines)


class LaunchOptionsPage(Page):
    """A preset's options: each value, where it comes from, what the engine receives; the command line."""

    ENTRY = MenuEntry(
        "launch",
        "Launch options",
        "A preset's options: each value, where it comes from, what the engine receives and what it does; the command "
        "line and the memory. p picks a preset, e opens its file.",
        "design 0003 §8.2, design 0001 §3.5",
        key="F2",
    )
    PANELS = ("launch-options-panel",)
    KEYS = (
        PageKey("p", "pick", "pick a preset"),
        PageKey("e", "open_file", "open its file"),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.chosen: str | None = None
        self.plan: dict[str, Any] | None = None

    def compose(self) -> ComposeResult:
        """The preset's options, its command line and its memory; the keys."""
        with Panel(title=TITLE, id="launch-options-panel"):
            yield Rows(24, gapped=True, id="launch-options")
            yield Label(id="launch-plan")

    def choose(self, preset: str) -> None:
        """Show this preset's options from now on."""
        self.chosen = preset
        self.plan = None
        if self.is_mounted:
            self._read_plan()

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Read the plan again when the presets, the slots or the launches changed; draw it when it came."""
        if changed & {"all", "presets", "slots", "launches"}:
            self._read_plan()
        if changed & {"all", "plan"}:
            title = f"{self.plan['title']}: launch options" if self.plan else TITLE
            self.query_one("#launch-options-panel", Panel).title = title
            options = self.plan["options"] if self.plan else []
            self.query_one("#launch-options", Rows).show([(each["label"], option_value(each)) for each in options])
            self.query_one("#launch-plan", Label).update(plan_rest(self.plan))

    def press(self, key: str) -> bool:
        """`p` picks another preset; `e` opens the preset's file."""
        if key == "p":

            def picked(value: str | None) -> None:
                if value is not None:
                    self.choose(value)

            self.console.push_screen(
                PickScreen("Show the options of", preset_choices(self.console.data.presets)), picked
            )
            return True
        if key == "e":
            preset = next((each for each in self.console.data.presets if each["id"] == self._preset()), None)
            if preset is None:
                return False
            open_file(preset["file"])
            note = (
                ""
                if preset["source"] == "user"
                else ": a preset Clank ships; save a copy in config/presets to change it"
            )
            self.console.say(f"opened {preset['file']}{note}")
            return True
        return False

    def explain(self) -> tuple[str, list[str]]:
        """Where a value comes from, and what the keys do."""
        return "Launch options", [
            "Each value comes from the preset when it sets it, else from Clank's default for that engine (the "
            "engine's release profile); the engine receives nothing for a value that is its own default, or for an "
            "option whose requirement the preset does not meet (design 0001 §3.5).",
            "The command line is exactly what starts when the preset is loaded, and the memory its estimate beside "
            "the GPU's free memory now.",
            "p picks another preset; e opens the preset's file, where a value is changed until M2 brings editing "
            "with trials.",
        ]

    def _preset(self) -> str | None:
        """The preset shown: the one chosen, else the main slot's, else the first."""
        data = self.console.data
        if self.chosen and any(preset["id"] == self.chosen for preset in data.presets):
            return self.chosen
        main = next((slot for slot in data.slots if slot["name"] == "main"), None)
        if main is not None and main["preset"]:
            return str(main["preset"])
        return data.presets[0]["id"] if data.presets else None

    def _read_plan(self) -> None:
        preset, client = self._preset(), self.console.client
        if preset is None:
            return

        def work() -> None:
            try:
                found = client.get(f"runtime/presets/{quote(preset, safe='')}/plan")
            except Exception:
                return
            self.console.call_from_thread(self._show_plan, found)

        self.run_worker(work, thread=True, group="plan", exclusive=True, exit_on_error=False)

    def _show_plan(self, found: dict[str, Any]) -> None:
        self.plan = found
        self.draw(self.console.data, {"plan"})
