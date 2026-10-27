"""The Phone page (design 0005 §5): the phone page on the tailnet, pairing, the paired devices, what was sent.

"Remote access": whether it is on, listening and published, its address on the tailnet, and why not when it cannot be
(Tailscale not signed in, Funnel on for its port). `x` turns it on or off. `p` makes a pair link for a device (a form
asks its name): its QR code shows here, drawn as text to scan with the phone's camera (design 0025 §2, `qr.py`), with
the link and the code under it, good for fifteen minutes, and what to check on the iPhone when the page will not
load; `c` cancels it, `p` again makes a new one. While remote access is on, under them: how the phone reaches this
PC, checked from here (design 0025 §2, `checkup.py`): the phones on the tailnet, what reached the listener today,
Funnel, then this PC's side, each with what to do; `r` reads and checks again at once.
"Paired devices": each paired device with when it was paired and last used; Enter shows everything it and this
computer exchanged (`traffic.py`); `d` revokes the highlighted one. "Sent to the phone": the newest files the agents
sent. The page reads the remote component again every few seconds while it is on screen. Its panels, "Remote access",
"Paired devices" and "Sent to the phone", are board E18's (design 0011 §8).
"""

from datetime import tzinfo
from typing import Any

from textual.app import ComposeResult
from textual.content import Content
from textual.widgets import Label, ListView

from clank.client import ClientError, NotRunning
from clank.components.machine.service import MARKS
from clank.components.remote.checkup import HINT
from clank.components.remote.console.traffic import TrafficScreen
from clank.components.remote.qr import qr_lines
from clank.console import actions
from clank.console.data import ConsoleData
from clank.console.form import Field, FormScreen
from clank.console.keys import PageKey
from clank.console.lists import refill, relabel
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.style import mark
from clank.console.text import painted, time_of

READ_SECONDS = 3.0
TONES = {"passed": "$clank-good", "warning": "$clank-attention", "failed": "$clank-failed", "skipped": "$clank-quiet"}


def status_lines(found: dict[str, Any]) -> list[Content]:
    """Whether remote access is on, where, and why not."""
    if not found["on"]:
        return [painted("off: nothing listens for the phone (x turns it on)", "stopped")]
    if found["listening"] and found["published"]:
        lines = [painted(f"on: {found['url']}", "running"), Content(f"for {found['login']}'s devices on the tailnet")]
    else:
        lines = [painted("on, starting: Tailscale publishes it within a few seconds", "starting")]
    if found.get("problem"):
        lines.append(painted(f"not published: {found['problem']}", "failed"))
    return lines


def checkup_lines(checkup: dict[str, Any] | None, zone: tzinfo | None) -> list[Content]:
    """How the phone reaches this PC, as the service checked it: when, then each check's mark in its color, its
    title and what was found, and under one not passed what to do; nothing while remote access is off."""
    if not checkup or not checkup.get("checks"):
        return []
    checks = checkup["checks"]
    width = max(len(check["title"]) for check in checks)
    lines = [Content(""), Content(f"How the phone reaches it, checked {time_of(checkup['at'], zone)} (r checks again)")]
    for check in checks:
        mark = (f"{MARKS[check['status']]:<4}", TONES[check["status"]])
        lines.append(Content.assemble(mark, f"  {check['title']:<{width}}  {check['detail']}"))
        if check["fix"] and check["status"] != "passed":
            lines.append(Content(f"      {'':<{width}}  {check['fix']}"))
    return lines


class PhonePage(Page):
    """The phone page on the tailnet: on or off, pairing, the devices, what was sent."""

    ENTRY = MenuEntry(
        "phone",
        "Phone",
        "Your phone page on the tailnet: x turns it on or off, p pairs a device (a code to type on it), d revokes one; "
        "from the phone, drive the agents' sessions, reply to what waits, and see the files they send.",
        "design 0005",
        key="F9",
    )
    PANELS = ("phone-access", "phone-devices-panel", "phone-sent")
    KEYS = (
        PageKey("x", "switch", "on or off", "remote access on or off"),
        PageKey("p", "pair", "pairs", "pair a device: a QR to scan on it (p again: a new one)"),
        PageKey("c", "cancel", "cancels the code"),
        PageKey("enter", "traffic", "what a device exchanged"),
        PageKey("d", "revoke", "revokes", "revoke the highlighted device"),
        PageKey("r", "read", "reads again", "read again, and check again how the phone reaches this PC"),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.found: dict[str, Any] | None = None
        self.files: list[dict[str, Any]] = []
        self.code: dict[str, Any] | None = None
        self.fresh = False  # the next read checks the phone's way in again at once (r)

    def badge(self, frame: int) -> Content | None:
        """A dot: green while the phone page is published, muted while it is off."""
        if self.found is None:
            return None
        published = self.found["on"] and self.found["listening"] and self.found["published"]
        return Content.assemble(
            (mark("on"), "$clank-good" if published else ("$clank-attention" if self.found["on"] else "$clank-quiet"))
        )

    def compose(self) -> ComposeResult:
        """Remote access, the code, the devices, the files sent."""
        with Panel(title="Remote access", id="phone-access"):
            yield Label(id="phone-status")
            yield Label(id="phone-code")
            yield Label(id="phone-checkup")
        with Panel(title="Paired devices", id="phone-devices-panel"):
            yield ListView(id="phone-devices")
        with Panel(title="Sent to the phone", id="phone-sent"):
            yield Label(id="phone-files")

    def on_mount(self) -> None:
        """Read now, and every few seconds while on screen."""
        super().on_mount()
        self.set_interval(READ_SECONDS, self._read)

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Read the remote component again when anything changed."""
        if changed & {"all", "connection", "operations"}:
            self._read()

    def press(self, key: str) -> bool:
        """The page's keys."""
        client = self.console.client
        if key == "x" and self.found is not None:
            wanted = not self.found["on"]
            done = f"remote access {'on' if wanted else 'off'}: it applies within a few seconds"
            actions.call(self.console, lambda: client.post("remote/switch", {"on": wanted}), done=done)
            self._read()
            return True
        if key == "p":
            self._pair()
            return True
        if key == "c" and self.found is not None and self.found.get("pairing"):
            self.code = None
            actions.call(self.console, lambda: client.post("remote/pair/cancel"), done="the pairing code is canceled")
            self._read()
            return True
        if key == "d":
            device = self._selected()
            if device is not None:
                actions.call(self.console, lambda: client.post(f"remote/devices/{device['id']}/revoke"),
                             done=f"{device['name']} is revoked")  # fmt: skip
                self._read()
            return True
        if key == "r":
            self.fresh = True
            self._read()
            return True
        return False

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Enter on a device: everything it and this computer exchanged."""
        if event.list_view.id == "phone-devices" and (device := self._selected()) is not None:
            self.console.push_screen(TrafficScreen(self.console, device))

    def explain(self) -> tuple[str, list[str]]:
        """What the phone page is, and who may reach it."""
        return "Phone", [
            "Your phone page: from the phone, watch the agents' sessions, send them messages (the same session you see "
            "in VS Code), start a task in any running workspace, stop one, allow or refuse what an agent asks to do, "
            "answer questions, and see the files the agents send you (ask one to send you a figure).",
            "It is published on your tailnet only, through Tailscale (never Funnel), and answers only your own "
            "Tailscale login, then only paired devices: a device is paired with a code made here (p), typed on it "
            "within fifteen minutes, once. A device's pairing lasts 30 days from its last use; d revokes it.",
            "x turns it on or off (config/remote.json); while it is off nothing listens for the phone.",
            "While it is on, the page says how the phone reaches this PC, checked from here: the phones on your "
            "tailnet (online, or when last seen), what reached the listener today and why it was refused, Funnel "
            "(it gives this PC's name a public address that leads a phone not using Tailscale's DNS astray: iCloud "
            "Private Relay off, then), Tailscale here, where the port goes, MagicDNS, the certificates, and this PC "
            "opening its own address; r checks again.",
        ]

    def _read(self) -> None:
        if not self.display:
            return
        client = self.console.client
        fresh, self.fresh = self.fresh, False

        def work() -> None:
            try:
                found = client.get("remote")
                files = client.get("remote/files", limit=8)["files"]
                checkup = client.get("remote/checkup", fresh=fresh) if found["on"] else None
            except (NotRunning, ClientError):
                return
            self.console.call_from_thread(self._show, found, files, checkup)

        self.run_worker(work, thread=True, group="phone-read", exclusive=True, exit_on_error=False)

    def _show(self, found: dict[str, Any], files: list[dict[str, Any]], checkup: dict[str, Any] | None = None) -> None:
        self.found, self.files = found, files
        relabel(self.query_one("#phone-status", Label), Content("\n").join(status_lines(found)))
        relabel(self.query_one("#phone-checkup", Label), Content("\n").join(checkup_lines(checkup, self.console.zone)))
        waiting = found.get("pairing")
        if self.code is not None and waiting is not None:
            code = self.code["code"]
            shown = [Content(line) for line in qr_lines(self.code["link"])] if self.code.get("link") else []
            shown += [
                Content.assemble(("Scan it with the iPhone's camera", "bold"),
                                 f"   for {waiting['name']}, until {time_of(waiting['expires'], self.console.zone)}"
                                 "   (c cancels it)"),
                Content(f"or open {self.code.get('link') or self.code['url'] or 'the phone page'}"),
                Content.assemble(
                    "or type the code ", (f"{code[:4]} {code[4:]}", "bold $clank-now"), " on the phone page"
                ),
                Content(HINT),
            ]  # fmt: skip
        else:
            self.code = None
            shown = [Content("p makes a code to pair a device")]
        relabel(self.query_one("#phone-code", Label), Content("\n").join(shown))
        listed = self.query_one("#phone-devices", ListView)
        kept = self._selected()
        devices = [device for device in found["devices"] if not device["revoked"]]
        lines = [
            f"{device['name']:<20} paired {time_of(device['paired'], self.console.zone)}   last used "
            f"{time_of(device['last_seen'], self.console.zone)}"
            for device in devices
        ]
        ids = [device["id"] for device in devices]
        refill(listed, lines or ["No paired device yet: p makes a code."], ids, kept["id"] if kept else None)
        sent = [f"{time_of(file['time'], self.console.zone)}  {file['workspace']}: {file['caption'] or file['from']}"
                for file in files]  # fmt: skip
        relabel(self.query_one("#phone-files", Label), "\n".join(sent) or "Nothing sent yet.")

    def _selected(self) -> dict[str, Any] | None:
        if self.found is None:
            return None
        devices: list[dict[str, Any]] = [device for device in self.found["devices"] if not device["revoked"]]
        index = self.query_one("#phone-devices", ListView).index
        if index is None or not 0 <= index < len(devices):
            return None
        return devices[index]

    def _pair(self) -> None:
        client = self.console.client

        def named(values: dict[str, str] | None) -> None:
            if values is None:
                return
            name = values["name"] or "phone"

            def work() -> None:
                try:
                    found = client.post("remote/pair", {"name": name})
                except (NotRunning, ClientError) as error:
                    self.console.call_from_thread(self.console.say, str(error), True)
                    return
                self.code = found
                self.console.call_from_thread(self._read)

            self.run_worker(work, thread=True, group="phone-pair", exclusive=True, exit_on_error=False)

        fields = [Field("name", "The device's name, as the history will call it", "my phone", "phone")]
        note = "The code shows on this page; type it on the phone page within fifteen minutes. Esc closes this."
        self.console.push_screen(FormScreen("Pair a device", fields, note), named)
