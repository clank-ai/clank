"""The Presets page (design 0003 §8.2): each preset with its serving setup and model, its fit in the GPU's memory now or
why it cannot run, and its last start; the highlighted one's settings below the list, with the sampling it gives its
engine: the values it sets, then the engine's own defaults in words (design 0003 §4.1).

The fit comes from each preset's plan, read off the screen's thread when the page comes on screen and whenever the
presets, the slots or the launches change (a launch changes what the estimates learned). Enter switches the main slot
to the highlighted preset (when the slot runs nothing, the switch starts it); `c` checks it, its items in a window; `v`
shows its file: where it is, and its settings as the file holds them; `o` opens its launch options. Its panels,
"Presets" (the list) and "Settings", are board E10's (design 0011 §8). A cloud preset (design 0016 §15) shows its
provider (`cloud openrouter`) and its prices in place of a fit, since it takes none of this computer's GPU; a switch to
it is a switch like any.

`e` changes a cloud preset's context, most output and thinking effort (design 0016 §7, revised 2026-10-29): a form
filled with its settings as the service words them (its model's limits in the labels), sending only what was changed
(`PATCH /runtime/presets/{id}`); the service's answer, which says where the change applies and that an OpenCode window
open keeps the limits it started with until it starts again, shows in a window, a refusal on the message line. On a
local preset the key cannot act, and says where its options change instead (`unable`): its file, `o` then `e` on Launch
options. The form leaves Esc and Backspace to the window: Esc leaves it, Backspace erases in its fields.
"""

import json
from typing import Any
from urllib.parse import quote

from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label, ListView

from clank.client import ClientError, NotRunning
from clank.components.runtime.console.common import fit_text, last_start, show_check
from clank.components.runtime.console.options import LaunchOptionsPage
from clank.console import actions
from clank.console.data import ConsoleData
from clank.console.details import DetailsScreen
from clank.console.form import Field, FormScreen
from clank.console.keys import PageKey
from clank.console.lists import refill
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.pick import preset_setup
from clank.money import money

SETTINGS = ("title", "engine", "engine_version", "model", "slot", "host", "options", "notes")
IN_TOKENS = ("context", "max_output")  # a cloud preset's settings that are whole numbers of tokens
EXAMPLES = {"context": "131072", "max_output": "32768", "reasoning": "default"}  # each field's example when empty
CHANGE_NOTE = (
    "Ctrl+S, or Enter in the last field, sends what you changed; Esc leaves the preset as it is. The main slot follows "
    "at once when it runs it; an OpenCode window open keeps the limits it started with until it starts again."
)


def local_said(preset: dict[str, Any]) -> str:
    """Where a local preset's options change, as `e` says it: its file, which Launch options opens."""
    return f"{preset['title']} is a local preset: its options are in its file; o, then e on Launch options opens it"


def changes(fields: list[Field], values: dict[str, str]) -> dict[str, Any]:
    """What a cloud preset's form changed, as the service takes it: each field whose value is not what it was (an
    empty one left as it was), its tokens as a whole number; `ValueError`, in words, for one that is not."""
    found: dict[str, Any] = {}
    for field in fields:
        value = values.get(field.key, "").strip()
        if not value or value == field.value:
            continue
        if field.key in IN_TOKENS:
            digits = value.replace(",", "").replace("_", "").replace(" ", "")
            if not digits.isdigit():
                raise ValueError(f"{field.key} is a whole number of tokens, not {value!r}")
            found[field.key] = int(digits)
        else:
            found[field.key] = value
    return found


VERDICTS = (
    ("does not fit", "$clank-failed"),
    ("cannot run", "$clank-failed"),
    ("tight", "$clank-attention"),
    ("fits", "$clank-good"),
)


def preset_line(preset: dict[str, Any], plan: dict[str, Any] | None, launches: list[dict[str, Any]], zone: Any) -> str:
    """A preset: its title, serving setup and model, its fit or why it cannot run; then its last start."""
    if preset.get("endpoint"):
        head = f"{preset['title']:<24}  {preset_setup(preset)}"
    else:
        setup = f"{preset['engine']} {preset['engine_version']} · {preset['model']}"
        head = f"{preset['title']:<24}  {setup} · {fit_text(preset, plan)}"
    last = last_start(preset["id"], launches, zone)
    return f"{head}\n{'':<26}{last}" if last else head


def verdict_in_color(line: str) -> Content:
    """A preset's line with its fit verdict colored: green when it fits, yellow when tight, red when it does not or
    cannot run."""
    shown = Content(line)
    for verdict, style in VERDICTS:
        start = line.find(verdict)
        if start >= 0:
            return shown.stylize(style, start, start + len(verdict))
    return shown


def sampling_text(sampling: list[dict[str, Any]]) -> str:
    """The sampling a preset gives its engine (design 0003 §4.1): the values it sets, then the engine's own defaults
    in words."""
    chosen = [f"{short(each)} {each['value']}" for each in sampling if each["value"] is not None]
    own = [f"{short(each)} {each['engine_default_words']}" for each in sampling if each["value"] is None]
    parts = [f"set: {' · '.join(chosen)}"] if chosen else []
    parts += [f"the engine's own: {' · '.join(own)}"] if own else []
    return "; ".join(parts)


def short(option: dict[str, Any]) -> str:
    """A sampling option's key without its prefix: temperature, top_p."""
    return str(option["key"]).removeprefix("sampling.")


def settings_text(preset: dict[str, Any], plan: dict[str, Any] | None) -> str:
    """The highlighted preset: where its file is, its settings, the sampling it gives its engine, and its memory
    estimate (a cloud preset: its provider and its prices)."""
    if preset.get("endpoint"):
        price = preset.get("price") or {}
        options = " · ".join(f"{key} {value}" for key, value in preset["options"].items())
        lines = [
            f"{preset['title']}  ({preset['source']}, {preset['file']})",
            f"provider       {preset.get('provider') or 'cloud ' + preset['endpoint']}: {preset['model']}",
            f"slot           {preset['slot']} (a cloud preset serves the main slot only; none of this computer's GPU)",
            f"options        {options}",
        ]
        if price:
            cached = f", {money(price['cached_in'])} cached in" if price.get("cached_in") else ""
            lines.append(
                f"prices         {money(price['in'])} in, {money(price['out'])} out{cached}, per million tokens"
            )
        if preset["notes"]:
            lines.append(f"notes          {preset['notes']}")
        return "\n".join(lines)
    host = preset["host"] or "the host it is installed on"
    options = (
        " · ".join(f"{key} {value}" for key, value in preset["options"].items()) or "its engine's and Clank's defaults"
    )
    lines = [
        f"{preset['title']}  ({preset['source']}, {preset['file']})",
        f"serving setup  {preset['engine']} {preset['engine_version']} on {host}",
        f"model          {preset['model']}",
        f"slot           {preset['slot']}",
        f"options        {options}",
    ]
    if preset.get("sampling"):
        lines.append(f"sampling       {sampling_text(preset['sampling'])}")
    if preset["notes"]:
        lines.append(f"notes          {preset['notes']}")
    if plan is not None and plan["fit"] is not None:
        lines.append(f"memory         {plan['fit']['lines'][0]}")
    return "\n".join(lines)


class PresetsPage(Page):
    """Each preset with its fit now and its last start."""

    ENTRY = MenuEntry(
        "presets",
        "Presets",
        "Each preset with its fit now and its last start; Enter switches the main slot to it, c checks it, v shows its "
        "file, o its launch options, e changes a cloud preset's context, most output and thinking effort.",
        "design 0003 §8.2, design 0016 §7",
        key="9",
    )
    PANELS = ("presets-list-panel", "presets-settings")
    KEYS = (
        PageKey("enter", "switch", "switch the main slot to it"),
        PageKey("c", "check", "check"),
        PageKey("v", "file", "its file"),
        PageKey("o", "options", "its options"),
        PageKey("e", "change", "change", "change a cloud preset's context, most output and thinking effort, in a form"),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.plans: dict[str, dict[str, Any]] = {}

    def compose(self) -> ComposeResult:
        """The presets; the highlighted one's settings; the keys."""
        with Panel(title="Presets", id="presets-list-panel"):
            yield ListView(id="presets-list")
        with Panel(title="Settings", id="presets-settings"):
            yield Label(id="presets-detail")

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Draw the list and the settings again when what they show changed; read the plans again when the presets, the
        slots or the launches changed."""
        if changed & {"all", "presets", "slots", "launches"}:
            self._read_plans()
        if not changed & {"all", "presets", "launches", "plans"}:
            return
        listed = self.query_one("#presets-list", ListView)
        lines = [
            verdict_in_color(preset_line(preset, self.plans.get(preset["id"]), data.launches, self.console.zone))
            for preset in data.presets
        ]
        refill(listed, lines)
        self._draw_settings()

    def press(self, key: str) -> bool:
        """`c` checks the highlighted preset; `v` shows its file; `o` opens its launch options; `e` changes a cloud
        preset's settings in a form."""
        preset = self._selected()
        if preset is None or key not in ("c", "v", "o", "e"):
            return False
        if key == "e":
            self._change(preset)
        elif key == "o":
            self.console.query_one("#page-launch", LaunchOptionsPage).choose(preset["id"])
            self.console.show_page("launch")
        elif key == "c":
            show_check(self, preset["id"], preset["title"])
        else:
            values = {name: preset[name] for name in SETTINGS if name in preset}
            lines = json.dumps(values, indent=2, ensure_ascii=False).splitlines()
            window = DetailsScreen(f"{preset['title']}: {preset['file']}", lines)
            self.console.call_later(
                self.console.push_screen, window
            )  # once the key is handled: the window's v closes it
        return True

    def unable(self, key: str) -> str:
        """`e` cannot change a local preset: it says where its options change instead (design 0011 §12.7)."""
        preset = self._selected()
        if key == "e" and preset is not None and not preset.get("endpoint"):
            return local_said(preset)
        return ""

    def explain(self) -> tuple[str, list[str]]:
        """What the highlighted preset is, and what the keys do."""
        preset = self._selected()
        if preset is None:
            return super().explain()
        what = (
            f"A cloud preset of {preset.get('provider') or 'cloud ' + preset['endpoint']}"
            if preset.get("endpoint")
            else f"A preset of {preset['engine']} {preset['engine_version']}"
        )
        change = (
            "e changes its context, its most output and its thinking effort in a form, within its model's limits: its "
            "thinking and its answer share the most output. The main slot follows at once when it runs it; an OpenCode "
            "window open keeps the limits it started with until it starts again."
            if preset.get("endpoint")
            else "e says where a local preset's options change: in its file, which e on Launch options opens."
        )
        return preset["title"], [
            f"{what} with {preset['model']}, in {preset['file']} "
            f"({preset['source']}: {'yours' if preset['source'] == 'user' else 'Clank shipped it'}).",
            "Its fit is its memory estimate beside the GPU's free memory now (design 0003 §6.5); the estimate learns "
            "from what its engine took, or needed, at its last start.",
            "Enter switches the main slot to it, going back to the last configuration that worked if it fails; c "
            "checks it, starting nothing; v shows its file. Its launch options and where each value comes from are "
            "on the Launch options page.",
            change,
        ]

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Show the highlighted preset's settings."""
        if event.list_view.id == "presets-list":
            self._draw_settings()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Enter: switch the main slot to the highlighted preset."""
        preset = self._selected()
        if event.list_view.id != "presets-list" or preset is None:
            return
        client, id, title = self.console.client, preset["id"], preset["title"]
        actions.call(
            self.console,
            lambda: client.post("runtime/slots/main/switch", {"preset": id}),
            done=f"asked to switch main to {title}",
        )

    def _change(self, preset: dict[str, Any]) -> None:
        """A cloud preset's settings in a form, as the service words them; what was changed is sent once it is taken."""
        fields = [Field(each["id"], each["said"], EXAMPLES.get(each["id"], ""), each["value"])
                  for each in preset.get("settings") or []]  # fmt: skip
        if not fields:
            self.console.say(f"{preset['title']}'s settings are not read yet", True)
            return

        def given(values: dict[str, str] | None) -> None:
            if values is None:
                return
            try:
                wanted = changes(fields, values)
            except ValueError as error:
                self.console.say(str(error), True)
                return
            if not wanted:
                self.console.say(f"nothing changed: {preset['title']} keeps its settings")
                return
            self._send(preset, wanted)

        self.console.push_screen(FormScreen(f"{preset['title']}: its settings", fields, CHANGE_NOTE), given)

    def _send(self, preset: dict[str, Any], wanted: dict[str, Any]) -> None:
        """Send a cloud preset's change; the service's answer in a window, or its refusal on the message line."""
        client, id, title = self.console.client, preset["id"], preset["title"]

        def work() -> None:
            try:
                found = client.patch(f"runtime/presets/{quote(id, safe='')}", wanted)
            except (NotRunning, ClientError) as error:
                self.console.call_from_thread(self.console.say, str(error), True)
                return
            self.console.call_from_thread(self._changed, title, found)

        self.run_worker(work, thread=True, group="preset-change", exit_on_error=False)

    def _changed(self, title: str, found: dict[str, Any]) -> None:
        said = [str(line) for line in found.get("said") or []]
        if not found.get("changed"):
            self.console.say(said[0] if said else f"nothing changed: {title} keeps its settings")
            return
        self.console.say(f"{title} changed")
        self.console.push_screen(DetailsScreen(f"{title}: changed", said))

    def _selected(self) -> dict[str, Any] | None:
        presets = self.console.data.presets
        index = self.query_one("#presets-list", ListView).index
        if index is None or not 0 <= index < len(presets):
            return presets[0] if presets else None
        return presets[index]

    def _draw_settings(self) -> None:
        preset = self._selected()
        text = settings_text(preset, self.plans.get(preset["id"])) if preset else "No preset yet."
        self.query_one("#presets-detail", Label).update(text)

    def _read_plans(self) -> None:
        client = self.console.client
        ids = [preset["id"] for preset in self.console.data.presets]

        def work() -> None:
            plans = {}
            for id in ids:
                try:
                    plans[id] = client.get(f"runtime/presets/{quote(id, safe='')}/plan")
                except Exception:
                    continue
            self.console.call_from_thread(self._show_plans, plans)

        self.run_worker(work, thread=True, group="plans", exclusive=True, exit_on_error=False)

    def _show_plans(self, plans: dict[str, dict[str, Any]]) -> None:
        self.plans = plans
        self.draw(self.console.data, {"plans"})
