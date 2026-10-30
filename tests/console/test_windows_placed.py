"""Design 0011 §7 (the owner's report of 2026-10-29: the workspace's cloud question opened in the console's top left
corner, not over its middle): every window over the console opens centered and whole on the screen. Every kind of
window Clank has is found by walking its modules for ModalScreen's subclasses, so a new kind cannot be left out of this
test: each is opened over the console at 60, 100 and 160 columns, and its box (the panels it shows) must lie inside the
screen, with as much room on its left as on its right and above as below, within a cell. The workspace's cloud
question, as This folder asks it before the agent starts, is a frame too."""

import importlib
import pkgutil
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from textual.content import Content
from textual.geometry import Region
from textual.screen import ModalScreen

import clank
from clank.client import Client
from clank.components.agents.console.callspanel import CallScreen
from clank.components.agents.console.itemsscreen import ItemsScreen
from clank.components.remote.console.traffic import TrafficScreen
from clank.components.tools.console.servers import ToolsScreen
from clank.components.workspaces.cloud import GOES, NEVER
from clank.console.app import ClankConsole
from clank.console.ask import AskScreen
from clank.console.confirm import ConfirmScreen
from clank.console.details import DetailsScreen
from clank.console.editor import EditScreen
from clank.console.form import Field, FormScreen
from clank.console.pick import Choice, PickScreen
from clank.console.snapshot import render_text
from clank.kernel.home import Home
from tests.console.frames import FOLDER, assert_frame, settle, steady_frame

pytestmark = pytest.mark.anyio
SIZES = [(60, 30), (100, 34), (160, 48)]
NOW = datetime(2026, 10, 11, 13, 54, tzinfo=UTC)  # the console's clock, so a frame is the same each time
CLOUD_QUESTION: dict[str, Any] = {
    "id": "q-000000",
    "title": "Let paper's agent use the cloud model cloud: Example Coder?",
    "detail": f"{GOES} {NEVER}",
    "options": [
        {"id": "allow", "label": "Allow", "key": "y", "effect": "its requests go to the cloud provider from now on"},
        {"id": "local", "label": "Keep local", "key": "n", "effect": "it stays on this machine; not asked again"},
    ],
}
WINDOWS: dict[type[ModalScreen[Any]], Callable[[ClankConsole], ModalScreen[Any]]] = {
    AskScreen: lambda app: AskScreen(CLOUD_QUESTION),
    ConfirmScreen: lambda app: ConfirmScreen("Stop Docker Desktop?", ["Two containers run.", "They stop with it."]),
    DetailsScreen: lambda app: DetailsScreen("What this does", ["One line.", "Another line."]),
    PickScreen: lambda app: PickScreen("Run in the main slot", [Choice("a", "daily 262K"), Choice("b", "frontier")]),
    FormScreen: lambda app: FormScreen("Add an MCP server", [Field("name", "Name", "myproject")]),
    ToolsScreen: lambda app: ToolsScreen("fake: 2 tools", [Content("fake-mcp 1.2.3")], [Content("add")]),
    TrafficScreen: lambda app: TrafficScreen(app, {"id": "d-0", "name": "my phone"}),
    CallScreen: lambda app: CallScreen("bash python -m unittest", ["$ python -m unittest", "Ran 9 tests", "OK"]),
    ItemsScreen: lambda app: ItemsScreen("Tool results", [{"id": "r-1", "said": "a result"}], ["a result"], []),
    EditScreen: lambda app: EditScreen("A note to the model", "Look at the tests first.", "Enter sends it."),
}


def every_kind_of_window() -> set[type[ModalScreen[Any]]]:
    """Every ModalScreen subclass in Clank's modules, each module imported first."""
    for found in pkgutil.walk_packages(clank.__path__, "clank."):
        importlib.import_module(found.name)
    kinds: set[type[ModalScreen[Any]]] = set()
    unseen: list[type[ModalScreen[Any]]] = [ModalScreen]
    while unseen:
        for kind in unseen.pop().__subclasses__():
            if kind.__module__.startswith("clank."):
                kinds.add(kind)
            unseen.append(kind)
    return kinds


def make(client: Client, home: Home) -> ClankConsole:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = FOLDER
    return app


def box(window: ModalScreen[Any]) -> Region:
    """What a window shows: the union of its children's regions, those it displays."""
    shown = [child.region for child in window.children if child.display and child.region.area]
    assert shown, f"{type(window).__name__} shows nothing"
    return Region.from_union(shown)


def test_every_kind_of_window_clank_has_is_opened_here() -> None:
    found = every_kind_of_window()
    assert found == set(WINDOWS), (
        f"windows to add to WINDOWS: {sorted(kind.__name__ for kind in found - set(WINDOWS))}; "
        f"gone: {sorted(kind.__name__ for kind in set(WINDOWS) - found)}"
    )


@pytest.mark.parametrize("size", SIZES, ids=[f"{cols}x{rows}" for cols, rows in SIZES])
@pytest.mark.parametrize("kind", list(WINDOWS), ids=[kind.__name__ for kind in WINDOWS])
async def test_a_window_opens_centered_and_whole_on_the_screen(
    client: Client, home: Home, kind: type[ModalScreen[Any]], size: tuple[int, int]
) -> None:
    app = make(client, home)
    async with app.run_test(size=size) as pilot:
        await settle(pilot, lambda: "f1 help" in render_text(app))
        window = WINDOWS[kind](app)
        app.push_screen(window)
        await settle(pilot, lambda: app.screen is window and bool(window.children))
        await steady_frame(pilot, app)
        shown, (cols, rows) = box(window), size
        whole = shown.x >= 0 and shown.y >= 0 and shown.right <= cols and shown.bottom <= rows
        assert whole, f"{kind.__name__} at {cols}x{rows}: {shown} is not whole on the screen"
        left, right = shown.x, cols - shown.right
        above, below = shown.y, rows - shown.bottom
        assert abs(left - right) <= 1, (
            f"{kind.__name__} at {cols}x{rows}: {left} columns on its left, {right} on its right"
        )
        assert abs(above - below) <= 1, f"{kind.__name__} at {cols}x{rows}: {above} rows above it, {below} below"


async def test_the_workspaces_cloud_question_opens_over_the_middle_of_the_console(client: Client, home: Home) -> None:
    app = make(client, home)
    async with app.run_test(size=(100, 34)) as pilot:
        await settle(pilot, lambda: app.data.connected and "f1 help" in render_text(app))
        await steady_frame(pilot, app)
        app.push_screen(AskScreen(CLOUD_QUESTION))
        await settle(pilot, lambda: "Let paper's agent use the cloud model" in render_text(app))
        assert_frame(await steady_frame(pilot, app), "ask-cloud-100")
