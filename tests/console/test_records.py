"""Design 0002 §2.2 and design 0001 §5.4: the records page lists every kind of record (settings and state), the
records of the chosen kind and the chosen record's values, each with its field's title. `?` explains what has the
focus: a value (what it is, its value, where it comes from, the file that holds it or would, when a change applies,
where its kind is defined), a planned menu entry (its milestone and design section), or the page itself. The command
palette (Ctrl+P) finds every page and action by name and runs it."""

from datetime import UTC, datetime

import pytest
from textual.widgets import Label, ListView

from clank.client import Client
from clank.console.app import ClankConsole
from clank.console.details import DetailsScreen
from clank.console.snapshot import render_text
from clank.kernel.home import Home
from tests.console.frames import assert_frame, focus_on, frame_when, settle

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 10, 11, 13, 54, tzinfo=UTC)


def make(client: Client, home: Home, page: str = "home") -> ClankConsole:
    return ClankConsole(client, now=lambda: NOW, zone=UTC, home=home, page=page)


def items(app: ClankConsole, list_id: str) -> list[str]:
    listed = app.query_one(f"#{list_id}", ListView)
    return [" ".join(str(label.content) for label in item.query(Label).results(Label)) for item in listed.children]


async def choose(app: ClankConsole, pilot: object, list_id: str, starts: str) -> None:
    await settle(pilot, lambda: any(item.startswith(starts) for item in items(app, list_id)))  # type: ignore[arg-type]
    listed = app.query_one(f"#{list_id}", ListView)
    wanted = next(n for n, item in enumerate(items(app, list_id)) if item.startswith(starts))
    await focus_on(pilot, app, listed, wanted)  # type: ignore[arg-type]


async def open_service_record(app: ClankConsole, pilot: object) -> None:
    await choose(app, pilot, "records-kinds", "service")
    await choose(app, pilot, "records-list", "service")
    await settle(pilot, lambda: any(item.startswith("port") for item in items(app, "records-fields")))  # type: ignore[arg-type]


async def test_the_records_page_lists_the_kinds_then_a_kinds_records_then_a_records_values(
    client: Client, home: Home
) -> None:
    app = make(client, home, "records")
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: len(items(app, "records-kinds")) >= 6)
        kinds = " ".join(items(app, "records-kinds"))
        for kind in ("service", "docker", "machine", "event", "question", "operation"):
            assert kind in kinds
        await open_service_record(app, pilot)
        fields = items(app, "records-fields")
        assert any(field.startswith("port") and "7720" in field for field in fields)
        assert "built-in" in str(app.query_one("#records-record", Label).content)
        assert_frame(await frame_when(pilot, app, "events_kept_days"), "records")


async def test_question_mark_on_a_value_explains_it_and_where_it_is_kept(client: Client, home: Home) -> None:
    app = make(client, home, "records")
    async with app.run_test(size=(120, 40)) as pilot:
        await open_service_record(app, pilot)
        await choose(app, pilot, "records-fields", "port")
        await pilot.press("question_mark")
        await settle(pilot, lambda: "The TCP port the API listens on." in render_text(app))
        frame = render_text(app)
        for words in ("7720", "config", "service.json", "next start", "clank.kernel.service_kinds.ServiceSettings"):
            assert words in frame, words
        await pilot.press("escape")
        await settle(pilot, lambda: "The TCP port the API listens on." not in render_text(app))


async def test_question_mark_on_a_planned_menu_entry_names_its_milestone_and_design(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        menu = app.query_one("#menu", ListView)
        await focus_on(pilot, app, menu, next(n for n, item in enumerate(menu.children) if item.id == "menu-agents"))
        await pilot.press("question_mark")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        explained = " ".join(str(label.content) for label in app.screen.query(Label).results(Label))
        assert "coming in M5" in explained
        assert "design 0002 §3.3" in explained


async def test_the_command_palette_finds_pages_and_actions_by_name_and_runs_them(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(120, 40)) as pilot:
        await settle(pilot, lambda: app.data.connected)
        await pilot.press("ctrl+p", *"run the doctor")
        await pilot.pause(0.3)
        await pilot.press("enter")
        await settle(pilot, lambda: any(each["type"] == "machine.doctor" for each in client.get("operations")))
        await pilot.press("ctrl+p", *"open docker")
        await pilot.pause(0.3)
        await pilot.press("enter")
        await settle(pilot, lambda: app.query_one("#pages").current == "page-docker")  # type: ignore[attr-defined]
