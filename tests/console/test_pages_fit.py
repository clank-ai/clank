"""Design 0011 §4, §7 and §11 (the owner's request of 2026-10-29: visual tests that catch what a person sees as wrong,
after a window opened in the console's top left corner): every page of the console, opened at 80, 120 and 170 columns,
fits the screen across: each of its panels starts at or after the screen's left edge and ends at or before its right
edge, and no two of its panels cover each other (one inside the other is a panel in a panel, and allowed). A page that
scrolls may run below the screen; across, nothing may."""

from datetime import UTC, datetime

import pytest
from textual.geometry import Region

from clank.client import Client
from clank.console.app import PAGES, ClankConsole
from clank.console.panel import Panel
from clank.kernel.home import Home
from tests.console.frames import FOLDER, settle, steady_frame

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 11, 13, 54, tzinfo=UTC)
SIZES = [(80, 30), (120, 36), (170, 48)]
IDS = [page.ENTRY.id for page in PAGES]


def overlapping(regions: list[tuple[str, Region]]) -> list[str]:
    """Each pair of panels that cover part of each other, neither inside the other."""
    found = []
    for i, (name, one) in enumerate(regions):
        for other_name, other in regions[i + 1 :]:
            shared = one.intersection(other)
            if shared.area and shared not in (one, other):
                found.append(f"{name} {one} and {other_name} {other}")
    return found


@pytest.mark.parametrize("size", SIZES, ids=[f"{cols}x{rows}" for cols, rows in SIZES])
@pytest.mark.parametrize("page", IDS)
async def test_every_page_fits_the_screen_across_and_its_panels_never_cover_each_other(
    client: Client, home: Home, page: str, size: tuple[int, int]
) -> None:
    app = ClankConsole(client, page=page, now=lambda: NOW, zone=UTC, home=home)
    app.folder = FOLDER
    async with app.run_test(size=size) as pilot:
        await settle(pilot, lambda: app.data.connected)
        await steady_frame(pilot, app)
        cols = size[0]
        panels = [(panel.id or type(panel).__name__, panel.region) for panel in app.screen.query(Panel)
                  if panel.display and panel.region.area]  # fmt: skip
        assert panels, f"{page} at {cols} columns shows no panel: the test would see nothing"
        outside = [f"{name} {region}" for name, region in panels if region.x < 0 or region.right > cols]
        assert not outside, f"{page} at {cols} columns: panels past the screen's edge: {outside}"
        covered = overlapping(panels)
        assert not covered, f"{page} at {cols} columns: panels covering each other: {covered}"
