"""A paired device's exchanges with this computer, over the console (design 0005 §5, transparency): opened from the
Phone page (F9) with Enter on a device. The list, newest first, reads again every few seconds: each exchange's time,
method and path, status, size and time taken ("same" when its answer was the same as the one before). The highlighted
exchange shows below whole: what the device sent, and what it was sent back, JSON laid out to read. Esc closes it. The
window is two panels (design 0011 §7): the exchanges, their count and size in its note, and the highlighted exchange.
"""

import json
from typing import TYPE_CHECKING, Any, ClassVar

from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Vertical, VerticalScroll
from textual.content import Content
from textual.screen import ModalScreen
from textual.widgets import Label, ListView

from clank.client import ClientError, NotRunning
from clank.console.lists import refill, relabel
from clank.console.panel import Panel
from clank.console.style import mark
from clank.console.text import count, time_of

if TYPE_CHECKING:
    from clank.console.app import ClankConsole

READ_SECONDS = 3.0
SHOWN = 300
BODY_LINES = 400  # the most lines of a body shown


def size(count: int) -> str:
    """Bytes, briefly."""
    return f"{count / 1024:.1f} KB" if count >= 1024 else f"{count} B"


def exchange_line(exchange: dict[str, Any], zone: Any) -> Content:
    """An exchange in the list: when, what, how it went, how big, how long."""
    status = int(exchange["status"])
    color = "$clank-good" if status < 300 else "$clank-attention" if status < 500 else "$clank-failed"
    target = exchange["path"] + (f"?{exchange['query']}" if exchange["query"] else "")
    same = "  same" if exchange.get("same_as") else ""
    return Content.assemble(
        (time_of(exchange["time"], zone), "dim"),
        "  ",
        (f"{exchange['method']:<5}", "bold"),
        f"{target[:44]:<45}",
        (f"{status}", color),
        f"  {size(exchange['bytes_out']):>8}  {exchange['ms']:>6.0f} ms",
        (same, "dim"),
    )


def body_text(value: Any) -> str:
    """A body as read: JSON laid out, text as it is, cut after `BODY_LINES` lines."""
    if value is None:
        return "(nothing)"
    text = value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False)
    lines = text.splitlines()
    more = f"\n{mark('cut')} {len(lines) - BODY_LINES:,} more lines" if len(lines) > BODY_LINES else ""
    return "\n".join(lines[:BODY_LINES]) + more


class TrafficScreen(ModalScreen[None]):
    """A device's exchanges with this computer, the highlighted one whole."""

    BINDINGS: ClassVar[list[BindingType]] = [Binding("escape", "dismiss", "close")]

    def __init__(self, console: "ClankConsole", device: dict[str, Any]) -> None:
        super().__init__()
        self.console = console
        self.device = device
        self.exchanges: list[dict[str, Any]] = []
        self.shown = ""

    def compose(self) -> ComposeResult:
        """The device's exchanges in a panel, the highlighted one in another, and how to close."""
        with Vertical(id="traffic"):
            title = f"{self.device['name']} · everything it and this computer exchanged"
            yield Panel(ListView(id="traffic-list"), title=title, id="traffic-list-panel")
            yield Panel(
                VerticalScroll(Label("", id="traffic-exchange"), id="traffic-body"),
                Label("Up and Down choose an exchange · Esc closes this.", classes="hint"),
                title="The highlighted exchange",
                id="traffic-body-panel",
            )

    def on_mount(self) -> None:
        """Read now, and every few seconds."""
        self._read()
        self.set_interval(READ_SECONDS, self._read)
        self.query_one("#traffic-list", ListView).focus()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Show the highlighted exchange whole."""
        self._read_one()

    def _read(self) -> None:
        client, device = self.console.client, self.device["id"]

        def work() -> None:
            try:
                found = client.get("remote/traffic", device=device, limit=SHOWN)["exchanges"]
            except (NotRunning, ClientError):
                return
            self.app.call_from_thread(self._show, found)

        self.run_worker(work, thread=True, group="traffic-read", exclusive=True, exit_on_error=False)

    def _show(self, exchanges: list[dict[str, Any]]) -> None:
        listed = self.query_one("#traffic-list", ListView)
        kept = self._selected()
        self.exchanges = exchanges
        lines = [exchange_line(each, self.console.zone) for each in exchanges] or [Content("Nothing exchanged yet.")]
        refill(listed, lines, [each["id"] for each in exchanges], kept["id"] if kept else None)
        if listed.index is None and exchanges:
            listed.index = 0
        sent = sum(each["bytes_out"] for each in exchanges)
        told = f"{count(len(exchanges), 'newest exchange')} · {size(sent)} sent to it" if exchanges else ""
        self.query_one("#traffic-list-panel", Panel).note = told
        self._read_one()

    def _selected(self) -> dict[str, Any] | None:
        index = self.query_one("#traffic-list", ListView).index
        return self.exchanges[index] if index is not None and 0 <= index < len(self.exchanges) else None

    def _read_one(self) -> None:
        chosen = self._selected()
        if chosen is None or chosen["id"] == self.shown:
            return
        self.shown = chosen["id"]
        client = self.console.client

        def work() -> None:
            try:
                found = client.get(f"remote/traffic/{chosen['id']}")
            except (NotRunning, ClientError):
                return
            self.app.call_from_thread(self._show_one, found)

        self.run_worker(work, thread=True, group="traffic-one", exclusive=True, exit_on_error=False)

    def _show_one(self, found: dict[str, Any]) -> None:
        target = found["path"] + (f"?{found['query']}" if found["query"] else "")
        head = f"{found['method']} {target}  →  {found['status']}"
        kind = found.get("response_type") or "no type"
        parts = [
            Content.assemble((head, "bold")),
            Content.assemble(("sent by the device", "$clank-title"), f"  ({size(found['bytes_in'])})"),
            Content(body_text(found.get("request"))),
            Content(""),
            Content.assemble(("sent to the device", "$clank-title"), f"  ({size(found['bytes_out'])}, {kind})"),
            Content(body_text(found.get("response"))),
        ]
        relabel(self.query_one("#traffic-exchange", Label), Content("\n").join(parts))
