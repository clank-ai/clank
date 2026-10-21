"""Design 0016 §4 and §14: the hidden field a key is typed or pasted into. It draws dots as the key comes, then `…` and
its last four characters; the frame's text (and so a snapshot) and the console's log hold no other part of it; nothing
copies it to the clipboard; Esc clears it, and taking it to send clears it too. A key's field in a form gives the key
to the page that asked, and only once. Textual's own log (TEXTUAL_LOG) never holds it either: what is typed or pasted
into the field never reaches a logger, and the worker that sends it is described, so its repr is not the call holding
it; and `clank console` turns Textual's log file and devtools off."""

import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from textual import constants as textual_constants
from textual import events

from clank.cli import console as console_command
from clank.cli.main import main
from clank.client import Client
from clank.console import app as console_app
from clank.console.app import ClankConsole
from clank.console.form import Field, FormScreen, SecretField, hidden
from clank.console.snapshot import render_text
from clank.kernel.home import Home
from tests.console.frames import FOLDER, assert_frame, settle
from tests.support.cloud import CloudBench

pytestmark = pytest.mark.anyio

KEY = "made-up-openrouter-key"
HIDDEN = KEY[:-4]  # the part of the key no frame may hold
NOW = datetime(2026, 10, 21, 9, 14, tzinfo=UTC)


def make(client: Client, home: Home) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = FOLDER
    return app


def test_a_key_draws_as_dots_then_its_last_four() -> None:
    assert hidden("") == ""
    assert hidden("abc") == "•••", "a few characters: dots alone"
    assert hidden(KEY) == "••••••••••••••••••…-key"
    assert hidden("x" * 200).endswith("…xxxx")
    assert len(hidden("x" * 200)) <= 30, "a long key never draws wider than its field"


async def test_a_pasted_key_shows_as_dots_and_its_last_four_and_nothing_else_of_it(
    client: Client, home: Home, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    given: list[Any] = []
    app = make(client, home)
    async with app.run_test(size=(88, 30)) as pilot:
        await settle(pilot, lambda: "Fake Docker" in render_text(app))
        form = FormScreen("Your OpenRouter key", [Field("key", "paste your OpenRouter key", secret=True)])
        app.push_screen(form, given.append)
        await settle(pilot, lambda: bool(app.screen.query(SecretField)))
        app.post_message(events.Paste(KEY))
        await settle(pilot, lambda: "…-key" in render_text(app))
        frame = render_text(app)
        assert KEY not in frame
        assert HIDDEN not in frame
        assert_frame(frame, "secret-field-pasted")
        await pilot.press("ctrl+c", "ctrl+x", "ctrl+a", "ctrl+c")
        assert KEY not in (app.clipboard or ""), "nothing copies the key"
        await pilot.press("enter")
        await settle(pilot, lambda: bool(given))
    assert given == [{"key": KEY}], "the form gives it to the page that asked, once"
    assert KEY not in caplog.text
    assert HIDDEN not in caplog.text


async def test_typed_keys_stay_in_the_field_and_never_reach_the_consoles_own_keys(client: Client, home: Home) -> None:
    given: list[Any] = []
    app = make(client, home)
    async with app.run_test(size=(60, 30)) as pilot:
        app.push_screen(FormScreen("Your key", [Field("key", "paste your key", secret=True)]), given.append)
        await settle(pilot, lambda: bool(app.screen.query(SecretField)))
        await pilot.press(*"q1-made-up", "backspace", "backspace")
        field = app.screen.query_one(SecretField)
        assert app.is_running, "q in the field is a letter of the key, not quit"
        assert field.ends == "ade-"
        assert "q1-made-up" not in render_text(app)
        await pilot.press("enter")
        await settle(pilot, lambda: bool(given))
    assert given == [{"key": "q1-made-"}]
    assert not field.filled, "taking it to send clears it"


async def test_esc_clears_the_field_and_gives_nothing(client: Client, home: Home) -> None:
    given: list[Any] = []
    app = make(client, home)
    async with app.run_test(size=(60, 30)) as pilot:
        app.push_screen(FormScreen("Your key", [Field("key", "paste your key", secret=True)]), given.append)
        await settle(pilot, lambda: bool(app.screen.query(SecretField)))
        app.post_message(events.Paste(KEY))
        field = app.screen.query_one(SecretField)
        await settle(pilot, lambda: field.filled)
        await pilot.press("escape")
        await settle(pilot, lambda: bool(given))
    assert given == [None]
    assert not field.filled
    assert field.ends == ""


async def test_textuals_own_log_holds_no_key_typed_pasted_or_sent(
    client: Client, home: Home, cloud_api: CloudBench, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = tmp_path / "textual.log"
    monkeypatch.setattr(textual_constants, "LOG_FILE", str(log))  # as TEXTUAL_LOG would set it
    cloud_api.add(key=False)
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page="addmodel")
    app.folder = FOLDER
    async with app.run_test(size=(88, 34)) as pilot:
        await settle(pilot, lambda: bool(app.data.endpoints))
        await pilot.press("c")
        await settle(pilot, lambda: app.focused is app.query_one("#add-key-field", SecretField))
        await pilot.press(*KEY[:6])
        app.post_message(events.Paste(KEY[6:]))
        await settle(pilot, lambda: "…-key" in render_text(app))
        await pilot.press("enter")
        await settle(pilot, lambda: cloud_api.key() == KEY)
        await settle(pilot, lambda: "made-up key label" in render_text(app))
    written = log.read_text(encoding="utf-8")
    assert KEY not in written
    assert HIDDEN not in written
    assert KEY[6:] not in written, "the pasted part"


def test_clank_console_turns_textuals_log_file_and_devtools_off(monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[Any] = []

    class Recorded:
        def __init__(self, client: Any, **kwargs: Any) -> None:
            opened.append(kwargs)

        def run(self, **kwargs: Any) -> None:
            return None

    class Unused:
        def close(self) -> None:
            return None

    monkeypatch.setenv("TEXTUAL_LOG", "textual.log")
    monkeypatch.setenv("TEXTUAL", "devtools,debug")
    monkeypatch.setattr(textual_constants, "LOG_FILE", "textual.log")
    monkeypatch.setattr(console_app, "ClankConsole", Recorded)
    monkeypatch.setattr(console_command, "connect", lambda home, start: Unused())
    assert CliRunner().invoke(main, ["console", "--page", "home"]).exit_code == 0
    assert opened, "the console opened"
    assert "TEXTUAL_LOG" not in os.environ
    assert textual_constants.LOG_FILE is None
    assert "devtools" not in os.environ.get("TEXTUAL", "")
