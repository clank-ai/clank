"""The Requests page (design 0001 §6, built 2026-10-15): every model request through the gateway, newest first.

A line a request: when, who asked (OpenCode, a script) and for which role, its status, its prompt in tokens and how much
of it the engine had cached, its answer in tokens, how long until its first token and in all, its speed, and a mark
when the gateway sent it again after its engine broke off, stopped it because it repeated itself (`looped`), or told
OpenCode the context was full when its engine refused it so (`full`, decision 0090: OpenCode compacts on it). The
highlighted request shows what was asked (the last message the user wrote) and what was answered. The list is read
again when the gateway has served another request (its activity, which the console follows); `r` reads it now. The
records are the gateway's own (`logs/traffic`), so a request made while the console was closed is there too.

`v` switches to the live view and back: the newest request as the model writes it (a session started from the phone
too), read twice a second: what it does now (reading the prompt, writing, its tokens and speed), what was asked, and its
text as it comes, its thinking dimmed, its answer as it is, its tool calls in color, the view kept at its end while it
is there; when the request ends it stays until the next begins.

Its panels are board E16's (design 0011 §8): "Model requests through the gateway", the list, with how many it lists as
its note, and "The highlighted request"; the live view is one panel, shown in their place.
"""

from typing import Any

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.content import Content
from textual.widgets import Label, ListView

from clank.client import ClientError, NotRunning
from clank.console.data import ConsoleData
from clank.console.gauges import spinner
from clank.console.keys import PageKey
from clank.console.lists import refill, relabel
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.style import mark
from clank.console.text import count, live_text, painted, time_of

LIMIT = 100
NONE = "No request kept yet."  # the list's panel says it while the gateway has kept none
LIVE_SECONDS = 0.5
ASKED = 1500  # characters of the question shown under the list
ANSWERED = 3000


def request_line(request: dict[str, Any], zone: Any = None, cost: dict[str, Any] | None = None) -> str:
    """One request in a line: when, who, status, tokens in (cached), out, first token, total, speed; a cloud request's
    cost at its end, in the service's words (design 0016 §11)."""
    who = f"{request['client'] or '?'}/{request['role'] or '?'}"
    prompt, cached = request["prompt_tokens"], request["cached_tokens"]
    share = f" ({cached / prompt:.0%} cached)" if prompt and cached is not None else ""
    tokens_in = f"{prompt:,} in{share}" if prompt else "—"
    tokens_out = f"{request['completion_tokens']:,} out" if request["completion_tokens"] is not None else "—"
    first = f"{request['first_token_ms'] / 1000:.1f} s" if request["first_token_ms"] is not None else "—"
    total = f"{request['total_ms'] / 1000:.1f} s" if request["total_ms"] is not None else "—"
    speed = f"{request['per_second']:.0f}/s" if request["per_second"] else ""
    mark = " again" if request["again"] else (" broken" if request["broken"] else "")
    mark = " looped" if request.get("looped") else mark
    mark = " full" if request.get("full") else mark
    status = "failed" if request["error"] or (request["status"] or 0) >= 400 else str(request["status"] or "—")
    line = (
        f"{time_of(request['time'], zone)}  {who:<18} {status:<6} {tokens_in:<26} {tokens_out:<11} "
        f"first {first:<7} total {total:<8} {speed:<6}{mark}"
    )
    return f"{line}  {cost['said']}" if cost else line


def cost_line(cost: dict[str, Any]) -> str:
    """A cloud request's cost in the service's words, how it was known, and its tokens."""
    tokens = cost.get("tokens") or {}
    counted = (
        f"{tokens.get('in', 0):,} in ({tokens.get('cached', 0):,} cached), {tokens.get('out', 0):,} out, "
        f"{tokens.get('thinking', 0):,} thinking"
    )
    return f"cost {cost['said']}, {cost.get('how_said', '')} · tokens {counted} · {cost.get('model', '')}"


def detail_lines(found: dict[str, Any], zone: Any = None, cost: dict[str, Any] | None = None) -> list[Content]:
    """A request whole: where it went, its numbers (its cost, as the service knows it), what was asked, what was
    answered."""
    lines = [
        painted(request_line(found, zone, cost), "failed" if found["error"] else "done"),
        Content(
            f"{found['id']} · preset {found['preset'] or '—'} · {found['engine'] or '—'} · model sent "
            f"{found['model_sent'] or '—'} · {found['messages']} messages · {found['tools']} tools · waited "
            f"{(found['wait_ms'] or 0):.0f} ms for its slot"
        ),
    ]
    if cost:
        lines.append(Content(cost_line(cost)))
    if found["error"]:
        lines.append(Content.assemble(("error: ", "$clank-failed"), found["error"]))
    if found["notes"]:
        lines.append(Content(f"notes: {found['notes']}"))
    asked = found["asked"][:ASKED] + (f" {mark('cut')}" if len(found["asked"]) > ASKED else "")
    answer = found["answer"][:ANSWERED] + (f" {mark('cut')}" if len(found["answer"]) > ANSWERED else "")
    lines += [Content(""), Content.assemble(("asked", "bold")), Content(asked or "(no text)")]
    lines += [Content(""), Content.assemble(("answered", "bold")), Content(answer or "(no text: tool calls only)")]
    return lines


PHASES = {"waiting for its slot": "waiting for the model", "reading the prompt": "reading the prompt",
          "answering": "writing", "waiting for its engine to start again": "waiting for the engine"}  # fmt: skip


def live_head(found: dict[str, Any]) -> Content:
    """What the followed request does now (or how it ended), and what was asked."""
    meta = found.get("meta")
    if not meta:
        why = found.get("problem") or "the next model request shows here as it is written"
        return Content.assemble(("No model request yet: ", "bold"), why)
    if found["flying"]:
        speed = f" · {meta['per_second']:.0f} tok/s" if meta.get("per_second") else ""
        state = Content.assemble(
            (f"{mark('on')} ", "$clank-good"),
            (PHASES.get(meta["phase"], meta["phase"]), "bold"),
            f" · {meta['tokens']:,} tokens{speed} · {meta['seconds']:.0f} s · {meta['role']}",
        )
    else:
        speed = f" at {meta['per_second']:.0f} tok/s" if meta.get("per_second") else ""
        state = Content.assemble(
            (f"{mark('off')} ", "dim"),
            ("ended", "bold"),
            f" · {meta['tokens']:,} tokens{speed} in {meta['seconds']:.0f} s · {meta['role']}",
        )
    asked = found.get("asked") or "(no text: a tool's result, or the conversation so far)"
    return Content("\n").join([state, Content.assemble(("asked  ", "dim"), asked[:300])])


class RequestsPage(Page):
    """Every model request through the gateway, newest first."""

    ENTRY = MenuEntry(
        "requests",
        "Requests",
        "Every model request through the gateway, newest first: who asked, its tokens in and out, how much of the "
        "prompt was cached, its first token and its speed; the highlighted one shows what was asked and answered.",
        "design 0001 §6",
        key="F7",
    )
    PANELS = ("requests-list-panel", "requests-detail", "requests-live")
    KEYS = (
        PageKey("v", "live", "live view or the list", "watch the newest request live, or show the list again"),
        PageKey("r", "read", "reads the requests again"),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.rows: list[dict[str, Any]] = []
        self.costs: dict[str, dict[str, Any]] = {}  # each cloud request's cost, by its id (design 0016 §11)
        self.served: int | None = None
        self.live = False
        self.live_id = ""
        self.live_parts: list[list[str]] = []
        self.live_length = 0

    def badge(self, frame: int) -> Content | None:
        """A spinner while a request is in flight."""
        activity = self.console.data.activity
        return Content.assemble((spinner(frame), "$clank-now")) if activity and activity.get("requests") else None

    def compose(self) -> ComposeResult:
        """The newest requests, then the highlighted one whole; the live view, hidden until `v`."""
        with Panel(title="Model requests through the gateway", id="requests-list-panel"):
            none = Label(NONE, id="requests-none")
            none.display = False  # until the first read says there is none
            yield none
            yield ListView(id="requests-list")
        with Panel(title="The highlighted request", id="requests-detail"):
            yield Label(id="request-detail")
        with Panel(title="Live: the newest request as it is written", id="requests-live"):
            yield Label(id="live-head")
            with VerticalScroll(id="live-scroll"):
                yield Label(id="live-text")

    def on_mount(self) -> None:
        """Follow the newest request twice a second while the live view shows."""
        super().on_mount()
        self.query_one("#requests-live").display = False
        self.set_interval(LIVE_SECONDS, self._read_live)

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Read the requests again when the gateway has served another one (or on the first draw)."""
        served = (data.activity or {}).get("served")
        if "all" in changed or self.served is None or ("activity" in changed and served != self.served):
            self.served = served
            self._read()

    def press(self, key: str) -> bool:
        """`r` reads the requests again; `v` switches between the list and the live view."""
        if key == "r":
            self._read()
            return True
        if key == "v":
            self.live = not self.live
            for name in ("#requests-list-panel", "#requests-detail"):
                self.query_one(name).display = not self.live
            self.query_one("#requests-live").display = self.live
            self._read_live()
            return True
        return False

    def explain(self) -> tuple[str, list[str]]:
        """What a line says."""
        return "Requests", [
            "Each model request through the gateway, newest first, from its own records (logs/traffic: kept for "
            "config/gateway.json's keep_days).",
            "A line: when; who asked (OpenCode, a script) and for which role; its status; its prompt in tokens and how "
            "much of it the engine had cached from the conversation before (a high share makes the first token "
            "fast); its answer in tokens (thinking included); the time to its first token and in all; its speed. "
            "'again' marks a request the gateway sent again after its engine broke off; 'looped' one the loop guard "
            "stopped because the answer repeated itself (its error says what repeated); 'full' one its engine refused "
            "because the context was full, which OpenCode was told so that it compacts the session and goes on.",
            "The highlighted request shows what was asked (the last message the user wrote) and what was answered.",
            "v shows the newest request live, as the model writes it: its thinking (dimmed), its answer and its tool "
            "calls (in color), with what it does now and its speed; v again goes back to the list.",
        ]

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Show the highlighted request whole."""
        if event.list_view.id == "requests-list":
            self._read_one()

    def _read(self) -> None:
        if not self.display:
            return
        client = self.console.client

        def work() -> None:
            try:
                rows = client.get("gateway/requests", limit=LIMIT)["requests"]
                costs = {each["id"]: each for each in client.get("gateway/cost/requests", limit=LIMIT)}
            except ClientError as error:
                if error.status != 404:
                    return
                costs = {}  # a service without the cloud's routes
            except NotRunning:
                return
            self.console.call_from_thread(self._show, rows, costs)

        self.run_worker(work, thread=True, group="requests-read", exclusive=True, exit_on_error=False)

    def _show(self, rows: list[dict[str, Any]], costs: dict[str, dict[str, Any]] | None = None) -> None:
        listed = self.query_one("#requests-list", ListView)
        kept = self._selected()
        self.rows, self.costs = rows, costs or {}
        lines = [
            painted(
                request_line(row, self.console.zone, self.costs.get(row["id"])),
                "failed" if row["error"] or (row["status"] or 0) >= 400 else "",
            )
            for row in rows
        ]
        refill(listed, lines, [row["id"] for row in rows], kept["id"] if kept else None)
        self.query_one("#requests-list-panel", Panel).note = count(len(rows), "newest request") if rows else ""
        self.query_one("#requests-none", Label).display = not rows
        self._read_one()

    def _read_live(self) -> None:
        if not (self.display and self.live):
            return
        client, asked, after = self.console.client, self.live_id, self.live_length

        def work() -> None:
            try:
                found = client.get("gateway/live", after=after, id=asked)
            except (NotRunning, ClientError):
                return
            self.console.call_from_thread(self._show_live, found, asked)

        self.run_worker(work, thread=True, group="requests-live", exclusive=True, exit_on_error=False)

    def _show_live(self, found: dict[str, Any], asked: str) -> None:
        if found["id"] != asked:  # another request: read it from its start
            self.live_id, self.live_parts, self.live_length = found["id"], [], 0
            if asked:
                return
        for kind, text in found["parts"]:
            if self.live_parts and self.live_parts[-1][0] == kind:
                self.live_parts[-1][1] += text
            else:
                self.live_parts.append([kind, text])
        self.live_length = found["length"]
        if not found["flying"] and found.get("newest") and found["newest"] != self.live_id:
            self.live_id, self.live_parts, self.live_length = found["newest"], [], 0  # the next began
        relabel(self.query_one("#live-head", Label), live_head(found))
        scroll = self.query_one("#live-scroll", VerticalScroll)
        at_end = scroll.scroll_y >= scroll.max_scroll_y - 1
        relabel(self.query_one("#live-text", Label), live_text(self.live_parts))
        if at_end:
            scroll.call_after_refresh(scroll.scroll_end, animate=False)

    def _selected(self) -> dict[str, Any] | None:
        index = self.query_one("#requests-list", ListView).index
        if index is None or not 0 <= index < len(self.rows):
            return self.rows[0] if self.rows else None
        return self.rows[index]

    def _read_one(self) -> None:
        selected = self._selected()
        if selected is None:
            self.query_one("#request-detail", Label).update("")
            return
        id, client = selected["id"], self.console.client

        def work() -> None:
            try:
                found = client.get(f"gateway/requests/{id}")
            except (NotRunning, ClientError):
                return
            self.console.call_from_thread(self._show_one, id, found)

        self.run_worker(work, thread=True, group="request-one", exclusive=True, exit_on_error=False)

    def _show_one(self, id: str, found: dict[str, Any]) -> None:
        selected = self._selected()
        if selected is None or selected["id"] != id:
            return
        detail = detail_lines(found, self.console.zone, self.costs.get(id))
        self.query_one("#request-detail", Label).update(Content("\n").join(detail))
