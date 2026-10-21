"""Design 0012 §2, §4.2, §4.6 and §11 step 12: the Session view's Biggest in the context panel lists the largest items
of the followed session's context, by the estimate: each with its tokens, its part's color, the step it came with (the
flow's, by its call id) and what it is, marked when it is loop text, when a newer call made it one that could be freed,
when OpenCode cleared it and when a compaction would keep it; narrower, a line cuts what the item is first, then its
marks, then its step, never its tokens; Enter shows the item highlighted whole, with why it is marked. When rows are
short, Biggest gives up rows with Tool calls (§2's room). Frames: the Session view with board A's parts at 128, 88 and
60 columns. The session and its request are synthetic."""

from typing import Any

import pytest

from clank.client import Client
from clank.components.agents.adapters.opencode import OpenCode
from clank.components.agents.console.biggestpanel import BiggestList, line, rows, said, whole
from clank.components.agents.context import totals
from clank.console.app import ClankConsole
from clank.console.details import DetailsScreen
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.components.agents.test_monitor_context import doing, ended, facts_of, held, route
from tests.console.frames import assert_frame, settle, steady_frame
from tests.console.test_monitor_context import gateway_of
from tests.console.test_monitor_flow import board, chart, known, make, opened
from tests.support import flowlines
from tests.support.boards import board_a
from tests.support.requests import ANSWER, PROMPT, board_a_census

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]


def activity() -> dict[str, Any]:
    """The gateway's activity of board A's session: its last finished step's request, with its census."""
    step = ended("r-19", PROMPT, ANSWER, cached=PROMPT - 2000, census=board_a_census())
    return doing(step, slots={"main": held("r-19", flowlines.SESSION)})


def estimated() -> dict[str, Any]:
    """Board A's totals, its parts estimated, its items' steps from its flow."""
    return totals(flowlines.SESSION, activity(), route("daily-262k"), facts_of, OpenCode().compaction, board_a()[0])


def row(what: str) -> dict[str, Any]:
    return next(each for each in rows(estimated()) if said(each).startswith(what))


def test_the_biggest_items_are_listed_with_their_tokens_their_step_and_what_they_are() -> None:
    shown = [line(each, 100).plain for each in rows(estimated())[:3]]
    assert shown[0] == "  5.6K █ step 3  read src/simulator.py"
    assert shown[1] == "  4.3K █ step 16 read studies/notes.md · kept if compacted"
    assert shown[2] == "  3.3K █         the system prompt"
    assert row("read studies/notes.md")["tokens"] == 4303, "the newest read of it; the earlier is said made again"
    again = next(each for each in rows(estimated()) if each.get("again"))
    assert line(again, 100).plain == "  1.2K █ step 3  read studies/notes.md · made again later"
    swatch = next(span for span in line(row("read src/simulator.py"), 100).spans if span.start == 7)
    assert str(swatch.style) == "$clank-part-results", "the part's color"
    assert rows(None) == []
    assert len(rows(estimated())) <= 12


def test_an_item_the_guide_cleared_says_by_you_and_what_it_freed() -> None:
    row = {"tokens": 10, "part": "results", "of": "results", "step": 3, "call": "call_c05", "node": "c05",
           "what": "the result of read /workspace/studies/notes.md", "cleared": True, "cleared_by": "you",
           "freed": 18_600}  # fmt: skip
    assert line(row, 100).plain == "    10 █ step 3  read studies/notes.md · cleared by you, freed about 18.6K"
    said = "you cleared it with the Guide's Drop, which freed about 18,600 tokens"
    assert any(each.startswith(said) for each in whole(row, None))
    own = {**row, "cleared_by": "", "freed": None}
    assert line(own, 100).plain.endswith("· cleared by OpenCode")


def test_a_biggest_line_cuts_what_it_is_first_then_its_marks_then_its_step_never_its_tokens() -> None:
    looped = row("thinking: the energy gap")
    assert line(looped, 100).plain.endswith("… · loop text · kept if compacted"), "what it is, cut first"
    assert line(looped, 40).plain == "  2.0K █ step 8  thinking: the energy g…", "then the marks"
    assert line(looped, 24).plain == "  2.0K █ thinking: the…", "then the step"
    assert line(looped, 12).plain == "  2.0K █ th…", "the tokens stay"
    for width in range(1, 121):
        for each in rows(estimated()):
            assert line(each, width).cell_length <= width, (width, each["what"])


def test_enter_on_an_item_shows_it_whole_with_why_it_is_marked() -> None:
    said = whole(row("thinking: the energy gap"), estimated()["parts"])
    assert said[0].startswith("thinking: the energy gap is 0.0 and")
    assert "part: loop text (from the thinking sent back), about 2,048 tokens of the estimate; 6,760 characters" in said
    assert "step 8" in said
    assert "loop text: it compresses to 1.0% of its size" in said
    assert any(each.startswith("inside the last 15,000 tokens") for each in said)
    assert said[-1].startswith("How it is estimated: each part's characters, shared out")
    again = whole(next(each for each in rows(estimated()) if each.get("again")), estimated()["parts"])
    assert any("could be freed" in each for each in again)
    assert "call id: call_c05" in again


async def test_enter_on_biggest_opens_the_item_highlighted(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway_of(kernel, monkeypatch, activity(), "daily-262k")
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        listed = app.query_one(BiggestList)
        await settle(pilot, lambda: bool(listed.shown))
        await pilot.press("b")
        await settle(pilot, lambda: app.focused is listed)
        listed.index = next(index for index, each in enumerate(listed.shown) if each["part"] == "loop")
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, DetailsScreen))
        assert isinstance(app.screen, DetailsScreen)
        assert "loop text: it compresses to 1.0% of its size" in app.screen.lines


@pytest.mark.parametrize(
    ("size", "f5", "name"),
    [((160, 50), False, "monitor-session-parts-128"), ((160, 50), True, "monitor-session-parts-88"),
     ((82, 70), False, "monitor-session-parts-60")],
)  # fmt: skip
async def test_the_session_view_with_the_parts_at_128_88_and_60_columns(
    kernel: Kernel,
    client: Client,
    home: Home,
    monkeypatch: pytest.MonkeyPatch,
    size: tuple[int, int],
    f5: bool,
    name: str,
) -> None:
    gateway_of(kernel, monkeypatch, activity(), "daily-262k")
    board(kernel)
    app: ClankConsole = make(client, home)
    async with app.run_test(size=size) as pilot:
        await opened(pilot, app)
        if f5:
            await pilot.press("f5")
        await settle(pilot, lambda: any("Draft the parameter gr" in each.plain for each in chart(app).drawn.lines))
        await settle(pilot, lambda: bool(app.query_one(BiggestList).shown) and known(app))
        assert_frame(await steady_frame(pilot, app), name)
