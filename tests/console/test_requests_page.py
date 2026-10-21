"""Design 0001 §6 (the Requests page, 2026-10-15): F7 shows the model requests the gateway kept, newest first, a line
each (when, who, status, tokens in and how much was cached, out, first token, total, speed), and the highlighted one
whole: where it went, what was asked and what was answered. `v` shows the newest request live as the model writes it:
what it does now, what was asked, and its text as it comes (asking only for what is new), following the next request
once it ended. Design 0004 §2: a request the loop guard stopped is marked so. Design 0012 §4.1 (decision 0090): so is
one whose engine refused it because the context was full, which OpenCode was told so that it compacts. Design 0011 §4
and §8 (board E16): how many requests are listed is the note in the top border of the list's panel; "No request kept
yet." shows in that panel only while there is none; the live view is one panel, which `v` shows in place of the other
two, and `v` again
brings them back. Design 0016 §11: each request's cost ends its line, in the service's words, an estimate marked ≈; the
highlighted one's details say the cost, how it was known, and its tokens in, cached, out and thinking. Design 0003 §4.1:
the highlighted request says the sampling it sent of its own beside its preset's (the values the preset sets, else the
engine's own defaults in words), none sent with the preset's in effect, or that it is not known when the gateway kept no
copy of the request."""

import json
import re
from datetime import UTC, datetime
from typing import Any

import pytest
from textual.widgets import Label

from clank.client import Client
from clank.components.gateway.console.requests import request_line, sampling_line
from clank.console.app import ClankConsole
from clank.console.panel import Panel
from clank.console.snapshot import render_text
from clank.kernel.core import Kernel
from tests.components.gateway.test_recent_requests import record
from tests.console.frames import settle, steady_frame
from tests.support.cloud import CloudBench

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 15, 2, 0, tzinfo=UTC)


def text(app: ClankConsole) -> str:
    """Every label's text on the page, hidden ones too: what was drawn, not what shows (`render_text` says that)."""
    return "\n".join(str(label.content) for label in app.query("#page-requests Label").results(Label))


def shown_panels(app: ClankConsole) -> list[str]:
    """The ids of the page's panels on screen, in order."""
    return [panel.id or "" for panel in app.query("#page-requests Panel").results(Panel) if panel.display]


async def test_f7_lists_the_requests_newest_first_and_shows_the_highlighted_one_whole(
    kernel: Kernel, client: Client
) -> None:
    folder = kernel.home.logs / "traffic"
    folder.mkdir(parents=True, exist_ok=True)
    rows = [record("r-1", "2026-10-15T01:00:00Z", asked="Explain censoring"),
            record("r-2", "2026-10-15T01:05:00Z", asked="Make the figure of tau versus p")]  # fmt: skip
    (folder / "2026-10-15.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=kernel.home, page="requests")
    async with app.run_test(size=(200, 50)) as pilot:
        await settle(pilot, lambda: "─ 2 newest requests ─┐" in render_text(app) and "Make the figure" in text(app))
        shown = text(app)
        assert not app.query_one("#requests-none", Label).display
    assert "01:05:00  opencode/agent     200    20,000 in (95% cached)" in shown
    assert "600 out" in shown
    assert "first 1.0 s" in shown
    assert "60/s" in shown
    assert shown.index("01:05:00") < shown.index("01:00:00"), "newest first"
    assert "Saved runs/figures/plot.png" in shown, "the highlighted one's answer"
    assert "model sent qwen3.8-27b" in shown


async def test_with_no_request_kept_the_lists_panel_says_so_and_has_no_note(kernel: Kernel, client: Client) -> None:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=kernel.home, page="requests")
    async with app.run_test(size=(200, 50)) as pilot:
        # The label shows on the first read; the frame is taken once the screen has caught up with it.
        await settle(pilot, lambda: app.query_one("#requests-none", Label).display)
        await settle(pilot, lambda: "No request kept yet." in render_text(app))
        frame = await steady_frame(pilot, app)
    assert "No request kept yet." in frame
    assert re.search(r"┌─ Model requests through the gateway ─+┐", frame), "no note"


async def test_one_request_kept_is_counted_in_the_singular(kernel: Kernel, client: Client) -> None:
    folder = kernel.home.logs / "traffic"
    folder.mkdir(parents=True, exist_ok=True)
    row = record("r-1", "2026-10-15T01:00:00Z", asked="Explain censoring")
    (folder / "2026-10-15.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=kernel.home, page="requests")
    async with app.run_test(size=(200, 50)) as pilot:
        await settle(pilot, lambda: "─ 1 newest request ─┐" in render_text(app))


def test_a_request_resent_after_its_engine_broke_off_says_so() -> None:
    brief = {"time": "2026-10-15T01:00:00Z", "client": "opencode", "role": "agent", "status": 200, "error": "",
             "prompt_tokens": 100, "cached_tokens": 0, "completion_tokens": 5, "first_token_ms": 900.0,
             "total_ms": 1000.0, "per_second": 50.0, "again": True, "broken": False}  # fmt: skip
    assert request_line(brief, UTC).endswith("50/s   again")
    assert "failed" in request_line({**brief, "again": False, "status": 502, "error": "the engine broke off"}, UTC)


def test_a_request_the_loop_guard_stopped_says_so() -> None:
    brief = {"time": "2026-10-18T16:04:17Z", "client": "opencode", "role": "agent", "status": 200,
             "error": "Clank's loop guard stopped the answer: its tool call bash repeated itself (…); ask again",
             "prompt_tokens": 85078, "cached_tokens": 83274, "completion_tokens": None, "first_token_ms": 3500.0,
             "total_ms": 18000.0, "per_second": None, "again": False, "broken": False, "looped": True}  # fmt: skip
    line = request_line(brief, UTC)
    assert line.endswith(" looped")
    assert "failed" in line


def test_a_request_refused_because_the_context_was_full_says_so() -> None:
    brief = {"time": "2026-10-20T09:12:40Z", "client": "opencode", "role": "agent", "status": 400,
             "error": "the context was full: prompt + max_tokens exceeds n_ctx (the request exceeds the available "
             "context size; OpenCode compacts the session on this error)", "prompt_tokens": None,
             "cached_tokens": None, "completion_tokens": None, "first_token_ms": None, "total_ms": 40.0,
             "per_second": None, "again": False, "broken": False, "looped": False, "full": True}  # fmt: skip
    line = request_line(brief, UTC)
    assert line.endswith(" full")
    assert "failed" in line


async def test_v_follows_the_newest_request_live_as_the_model_writes_it(
    kernel: Kernel, client: Client, monkeypatch: pytest.MonkeyPatch
) -> None:
    flying = {"id": "r-9", "role": "agent", "slot": "main", "phase": "answering", "seconds": 12.0, "tokens": 340,
              "per_second": 61.0}  # fmt: skip
    said = [["thinking", "The figure exists. "], ["answer", "Sending it now."], ["tool", "\n→ send_to_phone "]]
    asked: list[tuple[int, str]] = []

    def live(after: int = 0, id: str = "", session: str = "", subagents: bool = False) -> dict[str, object]:
        asked.append((after, id))
        whole = "".join(text for _, text in said)
        parts, start = [], 0
        for kind, text in said:
            if start + len(text) > after:
                parts.append([kind, text[max(0, after - start) :]])
            start += len(text)
        return {"id": "r-9", "newest": "r-9", "flying": True, "meta": flying, "asked": "send me the figure",
                "length": len(whole), "parts": parts, "problem": ""}  # fmt: skip

    monkeypatch.setattr(kernel.parts["gateway"], "live", live)
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=kernel.home, page="requests")
    async with app.run_test(size=(160, 50)) as pilot:
        await settle(pilot, lambda: "v live view or the list" in render_text(app).splitlines()[-1])
        await pilot.press("tab")
        await pilot.press("v")
        await settle(pilot, lambda: "Sending it now." in text(app), seconds=10)
        assert shown_panels(app) == ["requests-live"], "the live view in place of the list and the request"
        assert "┌─ Live: the newest request as it is written" in render_text(app)
        shown = text(app)
        assert "writing · 340 tokens · 61 tok/s · 12 s · agent" in shown
        assert "send me the figure" in shown
        assert "The figure exists." in shown
        assert "→ send_to_phone" in shown
        await settle(pilot, lambda: any(after > 0 for after, _ in asked), seconds=10)
        assert "r-9" in [id for _, id in asked], "it asks for what is new of the request it follows"
        await pilot.press("v")  # v again brings the list and the request back
        await settle(pilot, lambda: shown_panels(app) == ["requests-list-panel", "requests-detail"])
        assert "Live: the newest request" not in render_text(app)


async def test_each_requests_cost_shows_in_the_services_words_an_estimate_marked_and_its_details_say_how(
    kernel: Kernel, client: Client, cloud_api: CloudBench
) -> None:
    folder = kernel.home.logs / "traffic"
    folder.mkdir(parents=True, exist_ok=True)
    rows = [record("r-1", "2026-10-15T01:00:00Z", asked="Explain censoring"),
            record("r-2", "2026-10-15T01:05:00Z", asked="Make the figure of tau versus p")]  # fmt: skip
    (folder / "2026-10-15.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    tokens = {"in": 20000, "cached": 19000, "out": 600, "thinking": 120}
    kernel.parts["gateway"].costs.keep_entries("run-a", [
        {"seq": 1, "id": "r-2", "time": "2026-10-15T01:05:00.000Z", "session": "ses_1", "workspace": "paper",
         "preset": "cloud-example-coder", "model": "example-vendor/example-coder", "tokens": tokens, "usd": 0.0123,
         "how": "usage", "status": 200},
        {"seq": 2, "id": "r-1", "time": "2026-10-15T01:00:00.000Z", "session": "ses_1", "workspace": "paper",
         "preset": "cloud-example-coder", "model": "example-vendor/example-coder", "tokens": tokens, "usd": 0.03,
         "how": "estimate", "status": 200},
    ])  # fmt: skip
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=kernel.home, page="requests")
    async with app.run_test(size=(200, 50)) as pilot:
        await settle(pilot, lambda: "≈ $0.03" in text(app) and "cost $0.01, " in text(app))  # the details read too
        shown = text(app)
    assert re.search(r"01:05:00 .* \$0\.01$", shown, re.MULTILINE)
    assert re.search(r"01:00:00 .* ≈ \$0\.03$", shown, re.MULTILINE)
    assert "cost $0.01, OpenRouter's own figure, from the answer · tokens 20,000 in (19,000 cached), 600 out, 120 " in (
        shown
    )


PRESET_SAMPLING: list[dict[str, Any]] = [
    {"key": "sampling.temperature", "value": None, "engine_default_words": "1.0 thinking, 0.7 not thinking"},
    {"key": "sampling.top_p", "value": 0.9, "engine_default_words": "0.95 thinking, 0.80 not thinking"},
    {"key": "sampling.repeat_penalty", "value": None, "engine_default_words": "1 (none)"},
]


def test_the_sampling_a_request_sent_is_shown_beside_its_presets() -> None:
    sent = {"temperature": 0.55, "top_p": 1, "repetition_penalty": 1.1}
    assert sampling_line(sent, PRESET_SAMPLING) == (
        "sampling  sent: temperature 0.55, top_p 1, repetition_penalty 1.1, which win over the preset's: temperature "
        "1.0 thinking, 0.7 not thinking (the engine's own) · top_p 0.9 · repeat_penalty 1 (none) (the engine's own)"
    )
    assert sampling_line({}, PRESET_SAMPLING) == (
        "sampling  none sent; the preset's: temperature 1.0 thinking, 0.7 not thinking (the engine's own) · top_p 0.9 "
        "· repeat_penalty 1 (none) (the engine's own)"
    )
    assert sampling_line(sent, None) == "sampling  sent: temperature 0.55, top_p 1, repetition_penalty 1.1"
    assert sampling_line(None, PRESET_SAMPLING) == "sampling  not known: the gateway kept no copy of the request"


async def test_f7_shows_the_sampling_a_request_sent_beside_its_presets(kernel: Kernel, client: Client) -> None:
    folder = kernel.home.logs / "traffic"
    folder.mkdir(parents=True, exist_ok=True)
    row = record("r-1", "2026-10-15T01:00:00Z", asked="Explain censoring")
    row["request"] = {**row["request"], "temperature": 0.55}
    (folder / "2026-10-15.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=kernel.home, page="requests")
    async with app.run_test(size=(200, 50)) as pilot:
        await settle(pilot, lambda: "which win over the preset's" in text(app), seconds=10)
        shown = text(app).splitlines()
    assert (
        "sampling  sent: temperature 0.55, which win over the preset's: temperature 1.0 thinking, 0.7 not thinking "
        "(the engine's own)"
    ) in shown
