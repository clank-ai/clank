"""The Completion page (design 0006 §6, built 2026-10-15): completion in VS Code, served through Clank.

Served: the fast slot's state and what it runs; while it does not run, what loading it needs, each with a mark: its
engine installed on its host, its model's file downloaded there. `l` loads it, installing the engine and downloading the
model first when they are missing (each an operation, followed on the message line, done without a second question:
`l` is the asking); `u` unloads it; `x` turns completion off or on in VS Code. How fast: from the gateway's last
completions, how many in the last minute and hour, the median and 95th percentile time to an answer, how many a newer
keystroke broke off; then the newest ones. The settings: on, the wait after a keystroke, one line or a few, each with
what it does. Read every few seconds while on screen, and when a slot changes. Its panels, "Served", "How fast",
"Settings" and "Vision: the model that reads images", are board E17's (design 0011 §8).
"""

from collections.abc import Callable
from typing import Any

from textual.app import ComposeResult
from textual.content import Content
from textual.worker import get_current_worker

from clank.client import ClientError, NotRunning
from clank.console import actions
from clank.console.data import ConsoleData
from clank.console.gauges import size, spinner
from clank.console.keys import PageKey
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.rows import Rows
from clank.console.style import mark
from clank.console.text import time_of

READ_SECONDS = 3.0
SHOWN = 8  # the newest completions listed
NAME = 13  # the names' column


def marked(done: bool, text: str) -> Content:
    """A check or a cross, colored, then the text."""
    return Content.assemble(
        (f"{mark('done')} " if done else f"{mark('failed')} ", "$clank-good" if done else "$clank-failed"), text
    )


def served_rows(view: dict[str, Any]) -> list[tuple[str, Content]]:
    """Whether completion is served: the fast slot, what loading it needs while it does not run, and VS Code."""
    slot = view["slot"]
    if slot["status"] == "ready":
        rows = [("Fast slot", marked(True, f"ready: {view['title']} on {slot['host']}, since {slot['since'][11:19]}"))]
    elif slot["status"] in ("starting", "stopping"):
        rows = [
            (
                "Fast slot",
                Content.assemble((f"{mark('cut')} {slot['status']}", "$clank-attention"), f": {slot['reason']}"),
            )
        ]
    else:
        rows = [("Fast slot", marked(False, f"{slot['status']} ({slot['reason']}): l loads it"))]
    needs = view.get("needs")
    if needs:
        engine, model, host = needs["engine"], needs["model"], needs["host"] or "no host"
        what = f"{engine['label']} {engine['version']}"
        if engine["installed"]:
            rows.append(("Engine", marked(True, f"{what} installed on {host}")))
        elif engine["recipe"]:
            rows.append(("Engine", marked(False, f"{what} not installed on {host}: l installs it (on the CPU)")))
        else:
            rows.append(("Engine", marked(False, f"{what} not installed on {host}, and Clank has no recipe for it")))
        rows.append(("Model", model_line(model, host, "l downloads it")))
        rows += [("", Content.assemble((problem, "$clank-failed"))) for problem in needs["problems"]]
    settings = view["settings"]
    if settings["enabled"]:
        rows.append(("In VS Code", marked(True, "on: gray text after the cursor as you type; Tab takes it (x: off)")))
    else:
        rows.append(("In VS Code", marked(False, "off: nothing is asked (x: on)")))
    return rows


def model_line(model: dict[str, Any], host: str, how: str) -> Content:
    """A model's files on its host: downloaded, or not and how to get them."""
    files = model.get("files") or []
    total = sum(each["size"] or 0 for each in files) or model["size"] or 0
    weight = f" ({size(total)})" if total else ""
    missing = [each for each in files if not each["downloaded"]] or ([] if model["downloaded"] else [model])
    if not missing:
        return marked(True, f"{model['name']}{weight} downloaded to {host}")
    return marked(False, f"{model['name']}{weight} not downloaded to {host}: {how}")


MODES = ("off", "on-demand", "always")
SAID = {
    "off": "off: no image is read; annotations go as words and the agent's model is told it takes text only",
    "on-demand": "on demand: loaded when an image is to be read, unloaded after {idle} minutes without use",
    "always": "always: loaded and kept",
}


def vision_rows(view: dict[str, Any]) -> list[tuple[str, Content]]:
    """The vision model: its mode, its slot, and what getting it needs."""
    settings, slot = view["settings"], view["slot"]
    mode = settings["mode"]
    following = MODES[(MODES.index(mode) + 1) % len(MODES)]
    said = SAID[mode].format(idle=settings["idle_minutes"])
    rows = [("Mode", Content.assemble((said, "$clank-good" if mode != "off" else "$clank-attention"),
                                      (f"  (v: {following.replace('-', ' ')})", "dim")))]  # fmt: skip
    if slot["status"] == "ready":
        idle = view.get("idle_seconds")
        used = f", last used {idle // 60} min ago" if idle is not None else ""
        rows.append(("Model", marked(True, f"loaded: {view['title']} on {slot['host']}{used}")))
    elif slot["status"] in ("starting", "stopping"):
        rows.append(("Model", Content.assemble((f"{mark('cut')} {slot['status']}", "$clank-attention"))))
    else:
        rows.append(("Model", Content.assemble(("not loaded", "dim"), " (it loads when an image is to be read)"
                                               if mode == "on-demand" else "")))  # fmt: skip
    needs = view.get("needs")
    if needs:
        engine, model, host = needs["engine"], needs["model"], needs["host"] or "no host"
        if not engine["installed"]:
            rows.append(("Engine", marked(False, f"{engine['label']} {engine['version']} not installed on {host}: g "
                                                 "installs it")))  # fmt: skip
        rows.append(("Files", model_line(model, host, "g downloads them")))
    return rows


def speed_rows(view: dict[str, Any], zone: Any) -> list[tuple[str, Content]]:
    """How fast completions were answered: the counts, the times, what was broken off; then the newest."""
    counts = view.get("counts")
    if counts is None:
        return [("", Content.assemble((view.get("problem") or "not read yet", "dim")))]
    if not counts["count"]:
        return [("", Content.assemble(("none yet: they show here once VS Code asks for some", "dim")))]
    median, p95 = counts["median_ms"], counts["p95_ms"]
    times = f"median {median:,.0f} ms · 95% under {p95:,.0f} ms" if median is not None else "none answered yet"
    rows = [
        ("Asked", Content(f"{counts['last_minute']} in the last minute · {counts['last_hour']} in the last hour")),
        ("Answered in", Content(times)),
        (
            "Not answered",
            Content(
                f"{counts['broken_off']} broken off by a newer keystroke · {counts['failed']} failed · "
                f"{counts['refused']} refused"
            ),
        ),
    ]
    for entry in counts["recent"][:SHOWN]:
        rows.append((time_of(entry["time"], zone), recent_line(entry)))
    return rows


def recent_line(entry: dict[str, Any]) -> Content:
    """One completion: how it ended, its time, and its tokens."""
    outcome = entry["outcome"]
    color = {"answered": "$clank-good", "broken off": "dim", "failed": "$clank-failed", "refused": "$clank-failed"}.get(
        outcome, ""
    )
    said = f" {entry['total_ms']:,.0f} ms"
    if outcome == "answered":
        said += f" · read {entry.get('prompt_n') or 0} tokens · wrote {entry.get('predicted_n') or 0}"
    elif entry.get("error"):
        said += f" · {entry['error']}"
    return Content.assemble((outcome, color), said)


def settings_rows(settings: dict[str, Any]) -> list[tuple[str, Content]]:
    """The completion settings, each with what it does."""
    lines = (
        "a few after a line that opens a block (ending with :, {, ( or [), else the rest of the line"
        if settings["lines"] == "few"
        else "one: the rest of the line"
    )
    return [
        ("On", Content("yes" if settings["enabled"] else "no")),
        ("Wait", Content(f"{settings['delay_ms']} ms after you stop typing, before it asks")),
        ("Lines", Content(lines)),
    ]


class CompletionPage(Page):
    """Completion in VS Code: whether it is served, how fast, and its settings."""

    ENTRY = MenuEntry(
        "completion",
        "CPU models",
        "The small models on the CPU: completion in VS Code (whether it is served, l loads it, u unloads it; how "
        "fast it answers; x turns it off or on) and the model that reads images (v: off, on demand or always; g "
        "gets it).",
        "design 0006 §6, design 0008 §7",
        key="F8",
    )
    PANELS = ("completion-served-panel", "completion-speed-panel", "completion-settings-panel", "completion-vision")
    KEYS = (
        PageKey("l", "load", "loads", "load completion's model"),
        PageKey("u", "unload", "unloads", "unload completion's model"),
        PageKey("x", "switch", "turns it off or on in VS Code"),
        PageKey("v", "vision_mode", "vision's mode", "the vision model off, on demand or always"),
        PageKey("g", "get_vision", "gets vision's files"),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.view: dict[str, Any] | None = None
        self.vision: dict[str, Any] | None = None
        self.loading = False

    def badge(self, frame: int) -> Content | None:
        """A spinner while it loads; a check when completion is served and on."""
        if self.loading:
            return Content.assemble((spinner(frame), "$clank-now"))
        if self.view is None:
            return None
        served = self.view["slot"]["status"] == "ready" and self.view["settings"]["enabled"]
        return Content.assemble((mark("done"), "$clank-good")) if served else None

    def compose(self) -> ComposeResult:
        """Served, how fast, the settings, the vision model, and the keys."""
        with Panel(title="Served", id="completion-served-panel"):
            yield Rows(NAME, id="completion-served")
        with Panel(title="How fast", id="completion-speed-panel"):
            yield Rows(NAME, id="completion-speed")
        with Panel(title="Settings", id="completion-settings-panel"):
            yield Rows(NAME, id="completion-settings")
        with Panel(title="Vision: the model that reads images", id="completion-vision"):
            yield Rows(NAME, id="vision-rows")

    def on_mount(self) -> None:
        """Read now, and every few seconds while on screen."""
        super().on_mount()
        self.set_interval(READ_SECONDS, self._read)

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Read again when a slot changed (or on the first draw)."""
        if changed & {"all", "slots"} or self.view is None:
            self._read()

    def press(self, key: str) -> bool:
        """`l` loads, `u` unloads, `x` turns completion off or on in VS Code; `v` switches the vision model's mode,
        `g` gets its files."""
        actions_by_key: dict[str, Callable[[], None]] = {
            "l": self._load, "u": self._unload, "x": self._switch, "v": self._vision_mode, "g": self._get_vision,
        }  # fmt: skip
        if key in actions_by_key:
            actions_by_key[key]()
            return True
        return False

    def explain(self) -> tuple[str, list[str]]:
        """What the page shows, and what each key does."""
        return "Completion", [
            "As you type in VS Code, Clank's extension asks for the rest of the line (or a few lines after a line that "
            "opens a block) and shows it as gray text after the cursor: Tab takes it, typing on ignores it. It comes "
            "from a small coding model (Qwen2.5-Coder 0.5B) in the fast slot, on the CPU, through the gateway: the GPU "
            "and the agent's model are untouched, and nothing leaves this computer (design 0006).",
            "Served: the fast slot, and while it does not run, what loading it needs. l loads it: it installs the "
            "engine (llama.cpp's CPU build, about 18 MB) and downloads the model (about 530 MB) first when they are "
            "missing, each as an operation; u unloads it (its memory and threads freed).",
            "How fast: the gateway keeps its last 200 completions in memory. A newer keystroke breaks off the one in "
            "flight (a suggestion is worth something only until you type on), so broken-off ones are expected.",
            "x turns completion off or on in every VS Code window; the status bar item in VS Code does the same. The "
            "settings are kept in config/completion.json.",
            "Vision: a small model that reads images (Qwen3-VL 4B) on the CPU. It reads a figure you marked up when "
            "the agent's own model cannot see it, and the agent's look_at_figure tool asks it about a figure it made "
            "(design 0008). v switches it: off (no image is read, and the agent's model is told it takes text only), "
            "on demand (the default: loaded when an image is to be read, unloaded after its idle minutes, so the CPU "
            "is yours the rest of the time), always (loaded and kept). g downloads its files (about 2.7 GB) when they "
            "are missing. Its settings are in config/vision.json.",
        ]

    def _read(self) -> None:
        if not self.display:
            return
        client = self.console.client

        def work() -> None:
            try:
                view = client.get("gateway/completion")
                vision = client.get("gateway/vision")
            except (NotRunning, ClientError):
                return
            self.console.call_from_thread(self._show, view, vision)

        self.run_worker(work, thread=True, group="completion-read", exclusive=True, exit_on_error=False)

    def _show(self, view: dict[str, Any], vision: dict[str, Any] | None = None) -> None:
        self.view = view
        if vision is not None:
            self.vision = vision
            self.query_one("#vision-rows", Rows).show(vision_rows(vision))
        self.query_one("#completion-served", Rows).show(served_rows(view))
        self.query_one("#completion-speed", Rows).show(speed_rows(view, self.console.zone))
        self.query_one("#completion-settings", Rows).show(settings_rows(view["settings"]))

    def _unload(self) -> None:
        client = self.console.client
        actions.call(self.console, lambda: client.post("runtime/slots/fast/unload"), done="unloading the fast slot")

    def _switch(self) -> None:
        if self.view is None:
            return
        client, on = self.console.client, not self.view["settings"]["enabled"]

        def work() -> None:
            try:
                view = client.post("gateway/completion", {"enabled": on})
            except (NotRunning, ClientError) as error:
                self.console.call_from_thread(self.console.say, str(error), True)
                return
            said = "completion is on in VS Code" if on else "completion is off in VS Code"
            self.console.call_from_thread(self.console.say, said)
            self.console.call_from_thread(self._show, view)

        self.run_worker(work, thread=True, group="completion-switch", exclusive=True, exit_on_error=False)

    def _vision_mode(self) -> None:
        """The vision model's next mode: off, on demand, always."""
        if self.vision is None:
            return
        client = self.console.client
        mode = MODES[(MODES.index(self.vision["settings"]["mode"]) + 1) % len(MODES)]

        def work() -> None:
            try:
                vision = client.post("gateway/vision", {"mode": mode})
            except (NotRunning, ClientError) as error:
                self.console.call_from_thread(self.console.say, str(error), True)
                return
            said = SAID[mode].format(idle=vision["settings"]["idle_minutes"])
            self.console.call_from_thread(self.console.say, f"the vision model is {said}")
            self.console.call_from_thread(self._show, self.view or {}, vision)

        self.run_worker(work, thread=True, group="vision-mode", exclusive=True, exit_on_error=False)

    def _load(self) -> None:
        """Install the engine and download the model when missing, then load the preset: each followed to its end."""
        view = self.view
        if view is None or self.loading:
            return
        if view["slot"]["status"] in ("ready", "starting"):
            self.console.say("the fast slot runs already: u unloads it")
            return
        needs = view.get("needs")
        if not needs:
            self.console.say("Clank has no preset for the fast slot that can run here", True)
            return
        self._get(needs, "fast", "completion is served: gray text shows in VS Code as you type")

    def _get_vision(self) -> None:
        """The vision model's engine and files when missing; loaded too when its mode is always."""
        vision = self.vision
        if vision is None or self.loading:
            return
        needs = vision.get("needs")
        if not needs:
            self.console.say("the vision model is loaded: nothing to get")
            return
        always = vision["settings"]["mode"] == "always"
        done = "the vision model is loaded" if always else "the vision model is ready to load when an image is read"
        self._get(needs, "vision" if always else "", done)

    def _get(self, needs: dict[str, Any], slot: str, done: str) -> None:
        """Install the engine and download each missing file of the model, then load the preset into `slot` (none:
        not loaded); each an operation followed to its end."""
        client = self.console.client
        self.loading = True

        def stopped() -> bool:
            return bool(get_current_worker().is_cancelled)  # spelling: keep (Textual's own name)

        def step(said: str, request: Callable[[], Any]) -> bool:
            self.console.call_from_thread(self.console.say, said)
            try:
                operation = actions.started(request())
            except (NotRunning, ClientError) as error:
                self.console.call_from_thread(self.console.say, str(error), True)
                return False
            if operation is None:
                return True
            ended = actions.follow(client, operation, stopped)
            if ended is None or ended.get("status") != "done":
                why = (ended or {}).get("error") or (ended or {}).get("status") or "it did not end"
                self.console.call_from_thread(self.console.say, f"{said.rstrip('…')}: {why}", True)
                return False
            return True

        def work() -> None:
            engine, model, host = needs["engine"], needs["model"], needs["host"]
            install = {"setup": engine["setup"], "version": engine["version"], "host": host, "yes": True}
            files = model.get("files") or [{"role": model["role"], "downloaded": model["downloaded"]}]
            try:
                installing = f"installing {engine['label']} {engine['version']} on {host}…"
                if not engine["installed"] and not step(installing, lambda: client.post("runtime/installs", install)):
                    return
                for file in files:
                    if file["downloaded"]:
                        continue
                    body = {"model": model["id"], "format": model["format"], "role": file["role"], "host": host,
                            "yes": True}  # fmt: skip
                    said = f"downloading {model['name']} ({file['role']}) to {host}…"

                    def download(body: dict[str, Any] = body) -> Any:
                        return client.post("runtime/downloads", body)

                    if not step(said, download):
                        return
                if slot and not step(
                    f"loading {needs['title']}…",
                    lambda: client.post(f"runtime/slots/{slot}/load", {"preset": needs["preset"]}),
                ):
                    return
                self.console.call_from_thread(self.console.say, done)
            finally:
                self.loading = False
                self.console.call_from_thread(self._read)

        self.run_worker(work, thread=True, group="completion-load", exclusive=True, exit_on_error=False)
