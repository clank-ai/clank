"""Design 0011 §12.5: the console stays quick to the keys. Showing or hiding the menu (Ctrl+B, and Esc to it) or the
machine column (F5), and opening a page beside which either hides, restyle the menu or the column alone, never every
widget of every page: their classes are theirs, not the screen's (decision 0160)."""

from collections.abc import Iterable
from typing import Any

import pytest

from clank.client import Client
from clank.console.app import ClankConsole
from clank.kernel.home import Home
from tests.console.frames import FOLDER, settle

pytestmark = pytest.mark.anyio
MOST = 150  # widgets restyled by one toggle: the menu's entries, or the machine column's panels


def counting(app: ClankConsole) -> list[int]:
    """How many widgets each restyle from now on touches."""
    counts: list[int] = []
    stylesheet = app.stylesheet
    update = stylesheet.update_nodes

    def counted(nodes: Iterable[Any], animate: bool = False) -> None:
        listed = list(nodes)
        counts.append(len(listed))
        update(listed, animate=animate)

    stylesheet.update_nodes = counted  # type: ignore[method-assign]
    return counts


async def test_the_menu_and_the_machine_column_show_and_hide_restyling_only_themselves(
    client: Client, home: Home
) -> None:
    app = ClankConsole(client, home=home, page="records")
    app.folder = FOLDER
    async with app.run_test(size=(160, 44)) as pilot:
        await settle(pilot, lambda: app.focused is not None and app.focused.id == "menu")
        screen_classes = set(app.screen.classes)
        menu, machine = app.query_one("#menu"), app.query_one("#machine")
        counts = counting(app)
        await pilot.press("ctrl+b")
        await settle(pilot, lambda: not menu.display)
        assert max(counts) <= MOST, f"Ctrl+B restyled {max(counts)} widgets"
        counts.clear()
        await pilot.press("escape")
        await settle(pilot, lambda: menu.display)
        assert max(counts) <= MOST, f"Esc restyled {max(counts)} widgets"
        counts.clear()
        shown = machine.display
        await pilot.press("f5")
        await settle(pilot, lambda: machine.display != shown)
        assert max(counts) <= MOST, f"F5 restyled {max(counts)} widgets"
        assert set(app.screen.classes) == screen_classes, "the screen's own classes never changed"
