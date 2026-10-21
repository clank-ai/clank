"""Design 0012 §2, §4.2, §4.4, §4.5, §4.6, §4.7 and §11 step 12: the Monitor's Context view (board C), opened with Enter
on the Session view's Context window panel. Its Context window: the totals, the bar by part and what each part holds,
whose conversation the engine holds. What is in it: each part of the loaded model's (a template with no thinking has no
thinking part) with its tokens, its share, its items, the biggest and its last ten steps, from the estimate; narrower,
the biggest's words are cut first, then the last ten steps go, then the items, then the biggest, never a part's name,
tokens or share; ↑↓ move through the parts and Enter lists a part's items, biggest first, and says how many more it
holds. Where the room went: the biggest groups in words, with their tokens and share, the words cut first. Where these
figures come from: the engine adapter's context facts (the window, the output limit, the exact window or none, whether
it counts tokens), the model's catalog entry (its template's parts) and its calibration, or that it has none, and how
the estimate is made. On the GPU exactly: under KVMem, its first block, the newest tokens (from where the cache stopped
matching, or the last user message), what it picked and the rest in system memory, about, and that its picks are not
reported; under an engine without an exact window, that it attends its whole window. Over this session: a chart of the
session's size at each step against the window, each column split by part where the step's parts are known, the steps
the loop guard stopped and the compactions marked under it and said. Could be freed: the loop text, the earlier results
of calls made again and compacting now, each with about what it frees; Enter on Compact now asks first, as `k` does on
the view, and Enter on the others lists their items and how they are dropped. Frames: the Context view with board A's
parts at 128, 88 and 60 columns. Synthetic sessions."""

from datetime import UTC
from typing import Any

import pytest
from textual.content import Content

from clank.client import Client
from clank.components.agents.adapters.opencode import OpenCode
from clank.components.agents.console.contextchart import AXIS, CHART_ROWS, over_session
from clank.components.agents.console.contextfreed import FreedList, freed, freed_items
from clank.components.agents.console.contextgpu import gpu, gpu_drawn
from clank.components.agents.console.contextview import PartsList, contents, items_of, room, sources
from clank.components.agents.console.itemsscreen import ItemsScreen
from clank.components.agents.console.monitor import MonitorPage
from clank.components.agents.context import totals
from clank.console.confirm import ConfirmScreen
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.components.agents.test_monitor_context import doing, ended, facts_of, held, route
from tests.console.frames import assert_frame, settle, steady_frame
from tests.console.test_monitor_context import gateway_of
from tests.console.test_monitor_flow import board, chart, known, make, opened
from tests.support import flowlines
from tests.support.boards import START, board_a
from tests.support.requests import ANSWER, PROMPT, board_a_census

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]


def activity() -> dict[str, Any]:
    """Board A's session: ten finished steps whose census the gateway kept, the session growing to its last."""
    census = board_a_census()
    slim = {key: value for key, value in census.items() if key != "items"}
    steps = [ended(f"r-{n}", PROMPT * n // 10, ANSWER, census=slim) for n in range(1, 10)]
    last = ended("r-19", PROMPT, ANSWER, cached=PROMPT - 2000, census=census)
    return doing(*steps, last, slots={"main": held("r-19", flowlines.SESSION)})


def estimated(preset: str = "daily-262k", facts: Any = facts_of) -> dict[str, Any]:
    return totals(flowlines.SESSION, activity(), route(preset), facts, OpenCode().compaction, board_a()[0])


def plain(lines: list[Content]) -> list[str]:
    return [line.plain for line in lines]


def test_what_is_in_it_lists_each_part_with_its_tokens_share_items_biggest_and_last_ten_steps() -> None:
    drawn = contents(estimated(), 100)
    shown = plain(drawn)
    assert shown[0].startswith("part         tokens share items  the biggest")
    assert shown[0].endswith("last 10 steps")
    results = next(line for line in shown if line.startswith("█ results"))
    assert results.startswith("█ results    18,624   49%    18  5.6K read src/simulator.py")
    trend = results[-10:]
    assert len(set(trend)) > 1, "the part grew over its last ten steps"
    assert trend == "".join(sorted(trend))
    assert [line.split()[1] for line in shown[1:]] == [
        "system", "tools", "you", "text", "thinking", "calls", "results", "loop",
    ], "every part of the loaded model's, in the bar's order, by the legend's short names"  # fmt: skip
    swatch = next(span for span in drawn[7].spans if span.start == 0)
    assert str(swatch.style) == "$clank-part-results"
    nothing = estimated(facts=lambda name: _without_thinking(facts_of(name)))
    assert not any(line.startswith("█ thinking") for line in plain(contents(nothing, 100))), "no thinking part"
    assert plain(contents(None, 60)) == ["no session yet"]
    bare = totals(flowlines.SESSION, doing(ended("r-1", 9000, 100)), route("daily-262k"), facts_of,
                  OpenCode().compaction)  # fmt: skip
    assert plain(contents(bare, 60)) == ["the parts come with the session's next finished step"]


def _without_thinking(found: dict[str, Any] | None) -> dict[str, Any] | None:
    if found is None:
        return None
    model = {**found["model"], "template": {**found["model"]["template"], "earlier_thinking": "none"}}
    return {**found, "model": model}


def test_what_is_in_it_gives_up_the_biggests_words_first_then_its_trend_then_its_items() -> None:
    found = estimated()
    wide, cut = plain(contents(found, 100)), plain(contents(found, 70))
    assert "5.6K read src/simulator.py" in wide[7]
    assert "5.6K read src/sim" in cut[7], "the biggest's words first"
    assert "simulator.py" not in cut[7]
    assert cut[0].endswith("last 10 steps")
    no_trend = plain(contents(found, 60))
    assert "last 10" not in no_trend[0], "then the last ten steps"
    assert "items" in no_trend[0]
    no_items = plain(contents(found, 45))
    assert "items" not in no_items[0], "then the items"
    assert "the biggest" in no_items[0]
    least = plain(contents(found, 40))
    assert least[0] == "part         tokens share"
    assert least[7] == "█ results    18,624   49%", "never a part's name, tokens or share"
    for width in range(8, 161):
        assert all(line.cell_length <= width for line in contents(found, width)), width


def test_enter_on_a_part_lists_its_items_biggest_first() -> None:
    found = estimated()
    results = items_of(found, "results")
    assert results[0] == "  5,636  step 3   read src/simulator.py"
    assert results[1] == "  4,303  step 16  read studies/notes.md · kept if compacted"
    assert results[-1] == "and 7 more of its 18 items, about 625 tokens in all", "the census keeps the biggest"
    calls = items_of(found, "calls")
    assert calls[-1].startswith("and 10 more of its 18 items, about ")
    assert calls[-1].endswith(" tokens in all")
    assert items_of(found, "text") == ["the model's text holds nothing in this step"]


async def test_enter_on_a_part_of_what_is_in_it_opens_its_items(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway_of(kernel, monkeypatch, activity(), "daily-262k")
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        listed = app.query_one(PartsList)
        await pilot.press("f10")  # the view after the Session view
        await settle(pilot, lambda: bool(listed.shown) and listed.display)
        listed.focus()
        listed.index = [row["part"] for row in listed.shown].index("results")
        await settle(pilot, lambda: app.focused is listed)
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, ItemsScreen))
        assert isinstance(app.screen, ItemsScreen)
        assert app.screen.heading.startswith("tool results, about 18,624 tokens")
        assert app.screen.lines[0] == "  5,636  step 3   read src/simulator.py"


def test_where_the_room_went_names_the_biggest_groups() -> None:
    shown = plain(room(estimated(), 48))
    assert shown[0] == "read: 8 results".ljust(35) + "  15,424" + "  41%"
    assert shown[1].startswith("the system prompt and tool def")
    assert shown[1].endswith("13,510  36%")
    assert len(shown) <= 6
    narrow = plain(room(estimated(), 30))
    assert narrow[1].endswith("13,510  36%"), "the words are cut first"
    for width in range(8, 120):
        assert all(line.cell_length <= width for line in room(estimated(), width)), width


def test_where_these_figures_come_from_names_the_engines_facts_the_template_and_the_calibration() -> None:
    said = plain(sources(estimated()))
    assert said[0] == (
        "the engine: KVMem/llama.cpp v0.16.0-rc1 (“daily 262K”): a window of 262,144 tokens, at most 16,384 an answer; "
        "it attends 36,864 tokens exactly on the GPU, its first block of 128 and blocks of 128 picked by likeness to "
        "the last user message; it does not count tokens"
    )
    assert said[1].startswith(
        "the model: Qwen3.8-27B: thinking before your last message left out; tool calls written as XML; thinking "
        "between <think> and </think> (Qwen's reference chat template"
    )
    assert said[2] == (
        "the estimate: each part's characters, shared out so the parts add up to the engine's own count of 37,729 "
        "tokens; Qwen3.8-27B is not calibrated, so every part counts alike by its characters"
    )
    cpu = totals(flowlines.SESSION, doing(ended("r-1", 6000, 100, preset="cpu-8k", census=board_a_census())),
                 route("cpu-8k"), facts_of, OpenCode().compaction)  # fmt: skip
    small = plain(sources(cpu))
    assert "it attends its whole window, in system memory (it runs on the CPU); it counts tokens" in small[0]
    assert small[1].startswith("the model: Qwen2.5-Coder 0.5B: its chat template is not in the catalog")
    assert plain(sources(None)) == ["no session yet"]


@pytest.mark.parametrize(
    ("size", "f5", "name"),
    [((160, 60), False, "monitor-context-128"), ((160, 50), True, "monitor-context-88"),
     ((82, 80), False, "monitor-context-60")],
)  # fmt: skip
async def test_the_context_view_at_128_88_and_60_columns(
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
    app = make(client, home)
    async with app.run_test(size=size) as pilot:
        await opened(pilot, app)
        if f5:
            await pilot.press("f5")
        await settle(pilot, lambda: any("Draft the parameter gr" in each.plain for each in chart(app).drawn.lines))
        await settle(pilot, lambda: known(app))
        await pilot.press("c", "enter")
        await settle(pilot, lambda: bool(app.query_one(PartsList).shown))
        assert_frame(await steady_frame(pilot, app), name)


def test_on_the_gpu_exactly_says_the_first_block_the_newest_the_picked_and_the_rest_under_kvmem() -> None:
    shown = plain(gpu(estimated(), board_a()[0], UTC))
    assert shown == [
        "The model reads 36,864 tokens exactly:",
        f"█ {'the first':<11}{'128':>8}  the prompt's start",
        f"█ {'the newest':<11}{'~2,000':>8}  after the cached part",
        f"█ {'picked':<11}{'~34,736':>8}  by likeness to the last user message",
        f"░ {'the rest':<11}{'926':>8}  in system memory",
        "steps pick by your message of 12:05",
        "its picks by part: not reported by this engine",
    ]
    mine = {"main": held("r-1", flowlines.SESSION)}
    small = totals(flowlines.SESSION, doing(ended("r-1", 30_000, 100, census=board_a_census()), slots=mine),
                   route("daily-262k"), facts_of, OpenCode().compaction)  # fmt: skip
    assert plain(gpu(small, None, UTC)) == [
        "All 30,100 tokens are on the GPU: it reads up to 36,864 exactly",
        "nothing is picked: the whole conversation fits",
    ]
    lost = totals(flowlines.SESSION, activity(), route(None), facts_of, OpenCode().compaction)
    assert plain(gpu(lost, None, UTC))[0].startswith("On the GPU: nothing of this session's (the main slot is stopped)")
    assert plain(gpu(None, None, UTC)) == ["no session yet"]


def test_on_the_gpu_under_an_engine_without_an_exact_window_says_it_attends_its_whole_window() -> None:
    cpu = totals(flowlines.SESSION, doing(ended("r-1", 6000, 100, preset="cpu-8k", census=board_a_census())),
                 route("cpu-8k"), facts_of, OpenCode().compaction)  # fmt: skip
    assert plain(gpu(cpu, None, UTC)) == [
        "In system memory: all 6,100 tokens; it attends its whole window (it runs on the CPU)",
        "which parts were picked: all of them, every step",
    ]


def charted() -> tuple[dict[str, Any], dict[str, Any]]:
    """A session's totals and flow: a step split by part, one the loop guard stopped, one without a census, a
    compaction, then a step split by part again."""
    looped = "Clank's loop guard stopped the answer: it repeated itself"
    nodes = [
        {"kind": "step", "id": "s1", "n": 1, "ended": "finished", "created": START, "tokens": {"total": 100_000},
         "request": {"id": "r-1"}},
        {"kind": "step", "id": "s2", "n": 2, "ended": "failed", "error": looped, "created": START + 60_000,
         "request": {"id": "r-2", "looped": looped}},
        {"kind": "step", "id": "s3", "n": 3, "ended": "finished", "created": START + 120_000,
         "tokens": {"total": 160_000}},
        {"kind": "band", "id": "compacted:1", "at": [START + 180_000, "", 0], "auto": True, "done": True},
        {"kind": "step", "id": "s4", "n": 4, "ended": "finished", "created": START + 240_000,
         "tokens": {"total": 20_000}, "request": {"id": "r-4"}},
    ]  # fmt: skip
    steps = [{"request": "r-1", "prompt": 99_000, "parts": {"tools": 49_500, "results": 49_500}},
             {"request": "r-4", "prompt": 19_800, "parts": {"system": 19_800}}]  # fmt: skip
    return {"window": 262_144, "line": 229_376, "steps": steps, "parts": {"parts": []}}, {"head": {}, "nodes": nodes}


def cell(line: Content, x: int) -> tuple[str, str]:
    """The glyph at a column of a line and its color."""
    styles = [str(span.style) for span in line.spans if span.start <= x < span.end]
    return line.plain[x], styles[-1] if styles else ""


def test_the_chart_draws_each_steps_size_split_by_part_and_marks_compactions_and_loop_guard_stops() -> None:
    found, view = charted()
    drawn = over_session(found, 60, view, UTC)
    rows = drawn[:CHART_ROWS]
    assert rows[0].plain.startswith(" 262K "), "the window at the top"
    assert rows[-1].plain.startswith("    0 ")
    bottom, second, third = rows[-1], rows[-2], rows[-3]
    assert cell(bottom, AXIS) == ("█", "$clank-part-tools"), "step 1: the tools at the bottom"
    assert cell(second, AXIS) == ("█", "$clank-part-tools")
    assert cell(third, AXIS) == ("█", "$clank-part-results"), "then the results"
    assert cell(bottom, AXIS + 1)[1] == "$clank-failed", "the step the loop guard stopped"
    assert cell(bottom, AXIS + 2) == ("█", "$clank-data-1"), "a step whose parts are not known"
    assert cell(bottom, AXIS + 3)[1] == "$clank-attention", "the compaction"
    assert cell(bottom, AXIS + 4) == ("▅", "$clank-part-system"), "20,000 of a row of 32,768, the system prompt's"
    marks = drawn[CHART_ROWS].plain
    assert (marks[AXIS + 1], marks[AXIS + 3]) == ("✗", "▲")
    assert drawn[CHART_ROWS + 1].plain.startswith(" " * AXIS + "11:58")
    assert over_session(found, 80, view, UTC)[-1].plain == (
        "✗ 11:59 the loop guard stopped step 2 · 12:01 compacted by OpenCode"
    ), "each mark said"
    assert drawn[-1].plain.endswith("…"), "cut where the panel ends"
    assert plain(over_session(None, 60, None, UTC)) == ["no session yet"]
    nothing = {"window": 262_144, "line": 229_376, "steps": [], "parts": None}
    said = plain(over_session(nothing, 60, {"nodes": []}, UTC))
    assert said == ["no step of this session has ended since Clank watched it"]


def test_no_chart_line_is_wider_than_its_panel() -> None:
    found, view = charted()
    for width in range(4, 161):
        assert all(line.cell_length <= width for line in over_session(found, width, view, UTC)), width
        assert all(line.cell_length <= width for line in freed(estimated(), width)), width
        assert all(line.cell_length <= width for line in gpu_drawn(estimated(), width, UTC, board_a()[0])), width


def test_could_be_freed_says_what_each_frees() -> None:
    shown = plain(freed(estimated(), 90))
    assert shown[0].startswith("   the earlier results of calls made again: 1 item")
    assert shown[0].endswith("frees about 1,212")
    assert shown[1].startswith(" k the loop text the model wrote, which only compacting clears: 1 item"), (
        "a thinking that looped: Drop cannot clear it, so it is not offered to Drop"
    )
    assert shown[1].endswith("frees about 2,049")
    assert shown[2].startswith(" k compact now: OpenCode sums the session up")
    assert shown[2].endswith("frees about 22,729")
    assert plain(freed(estimated(), 40))[2].endswith("frees about 22,729"), "the words are cut first"


async def test_enter_on_compact_now_in_could_be_freed_asks_first_as_k_does(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway_of(kernel, monkeypatch, activity(), "daily-262k")
    board(kernel)
    monkeypatch.setattr(kernel.parts["agents"].sessions, "runs", lambda workspace, session: 4096)
    app = make(client, home)
    async with app.run_test(size=(160, 50)) as pilot:
        await opened(pilot, app)
        listed = app.query_one(FreedList)
        await pilot.press("f10")
        await settle(pilot, lambda: bool(listed.shown) and listed.display)
        page = app.query_one(MonitorPage)
        await settle(pilot, lambda: bool(((page.seen.guide if page.seen else None) or {}).get("actions")))
        listed.focus()
        listed.index = [row["what"] for row in listed.shown].index("compact")
        await settle(pilot, lambda: app.focused is listed)
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.pause(0.3)
        assert isinstance(app.screen, ConfirmScreen), "the Enter that opened it did not do it"
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, ConfirmScreen))
        listed.index = [row["what"] for row in listed.shown].index("again")
        await pilot.press("enter")
        await settle(pilot, lambda: isinstance(app.screen, ItemsScreen))
        assert isinstance(app.screen, ItemsScreen)
        assert any("the Guide's Drop" in line for line in app.screen.notes)
        await pilot.press("escape")
        await settle(pilot, lambda: not isinstance(app.screen, ItemsScreen))
        await pilot.press("k")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))


def test_could_be_freed_leaves_out_a_result_already_cleared() -> None:
    found = estimated()
    parts = found["parts"]
    for item in parts["items"]:
        if item.get("again"):
            item.update(cleared=True, cleared_by="you", freed=1_212)
    again = next(row for row in parts["freed"] if row["what"] == "again")
    assert freed_items(found, again) == [], "a result cleared is not offered again"
