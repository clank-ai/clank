"""Design 0012 §2, §4.1, §4.4 and §11 step 3, decision 0067: the Monitor's Context window panel shows the followed
session's totals from the loaded slot's facts only: how much of the window its last finished step used, how much is left
before OpenCode compacts, the share read from the cache (or "not reported by this engine"), the bar to the compaction
line and the room kept for the answer, what sits on the GPU (under KVMem its exact window and the rest in system memory;
under llama.cpp its whole window attended), whose conversation the engine holds and when another session took it, what a
compaction keeps, where the figures come from (a model without calibration labeled so), and the slot's preset after a
switch; no line wider than the panel. Design 0012 §4.5 (§11 step 7): under the GPU's line, a spark of the session's size
at each step, as OpenCode counts it, marked where the loop guard stopped an answer (its cell in the failed color) and
where it was compacted (in the attention color), each said after the spark. When the engine stopped, started again or
was switched, the panel says it holds no conversation and that this session's tokens are read again; when the last
step's answer did not report its size, it says so; when the totals cannot be read, it says why. Totals that did not
change are not drawn again (design 0001 §5.7). Frames: the Session view at 128 columns with a session on KVMem.
Design 0012 §4.2 (§11 step 12): with the parts estimated, the bar is drawn by part, each in its color, and a line says
what each part holds, "estimate" first; narrower, it gives up its smallest parts first, saying how many."""

from datetime import UTC
from typing import Any

import pytest
from textual.content import Content

from clank.client import Client, ClientError
from clank.components.agents.adapters.opencode import OpenCode
from clank.components.agents.console.contextpanel import NOT_REPORTED, ContextWindow, growth, lines, spark_line
from clank.components.agents.console.following import Following
from clank.components.agents.context import totals
from clank.components.agents.sessionflow.flow import Flow
from clank.console.app import ClankConsole
from clank.console.style import mark
from clank.kernel.core import Kernel
from clank.kernel.home import Home
from tests.components.agents.test_monitor_context import (
    CHILD,
    OTHER,
    SESSION,
    context,
    doing,
    ended,
    facts_of,
    held,
    route,
)
from tests.console.frames import assert_frame, settle, steady_frame
from tests.console.test_monitor_flow import board, chart, known, make, opened
from tests.support import flowlines
from tests.support.boards import START
from tests.support.requests import ANSWER, PROMPT, board_a_census

pytestmark = [pytest.mark.anyio, pytest.mark.usefixtures("still_spinner")]


def shown(activity: dict[str, Any], routes: dict[str, Any], width: int = 200, facts: Any = facts_of) -> list[str]:
    found = totals(SESSION, activity, routes, facts, OpenCode().compaction)
    return [line.plain for line in lines(found, width, UTC)]


def test_the_panel_says_used_left_and_the_cache_share_from_the_totals() -> None:
    said = shown(doing(ended("r-1", 150000, 2661, cached=147815)), route("daily-262k"))
    assert said[0] == (
        "152,661 of 262,144 tokens (58%) · 93,099 left before OpenCode compacts at 245,760 · 99% read from the cache"
    )
    assert said[1].startswith("█" * 116), "the room used, of 200 cells"
    assert said[1].count("▒") == 12, "the 16,384 kept for the answer: 200 cells less the line's 188"
    before = shown(doing(), route("daily-262k"))
    assert before[0] == (
        "window 262,144 · OpenCode compacts at 245,760 · no step of this session has ended since the gateway started"
    )
    assert shown(doing(), route(None)) == ["no model runs in the main slot"]


def test_the_gpu_line_under_kvmem_and_under_llamacpp() -> None:
    above = shown(doing(ended("r-1", 150000, 2661)), route("daily-262k"))
    assert above[2] == (
        "On the GPU exactly 36,864 · 115,797 in system memory · blocks of 128 picked by likeness to the last user "
        "message"
    )
    within = shown(doing(ended("r-1", 30000, 6000)), route("daily-262k"))
    assert within[2] == "On the GPU exactly: all 36,000 tokens (up to 36,864)"
    cpu = shown(doing(ended("r-1", 6000, 100, preset="cpu-8k")), route("cpu-8k"))
    assert cpu[2] == "In system memory: all 6,100 tokens; it attends its whole window (it runs on the CPU)"


def test_a_figure_not_reported_by_this_engine_is_said_so_and_a_model_without_calibration_too() -> None:
    def silent(name: str) -> dict[str, Any] | None:
        found = facts_of(name)
        assert found is not None
        fields = {key: path for key, path in found["engine"]["fields"].items() if key != "cached"}
        return {**found, "engine": {**found["engine"], "fields": fields}}

    said = shown(doing(ended("r-1", 40000, 100, cached=39000)), route("daily-262k"), facts=silent)
    assert said[0].endswith(f"read from the cache: {NOT_REPORTED}")
    assert not any("39,000" in line or "98%" in line for line in said), "never a number"
    missing = shown(doing(ended("r-1", 40000, 100)), route("daily-262k"))
    assert missing[0].endswith("read from the cache: not in the last step's answer")
    assert missing[4] == (
        "figures from KVMem/llama.cpp v0.16.0-rc1, “daily 262K” · Qwen3.8-27B, not calibrated · after compacting: a "
        "summary and the last 15,000 tokens"
    )


def test_the_panel_says_whose_conversation_the_engine_holds_and_when_another_took_it() -> None:
    mine = ended("r-1", 40000, 100)
    assert shown(doing(mine), route("daily-262k"))[3] == "● the engine holds this session's conversation"
    other = shown(doing(mine, slots={"main": held("r-2", OTHER)}), route("daily-262k"))
    assert (
        other[2] == "On the GPU: another conversation now; this session's 40,100 tokens are read again at its next step"
    )
    assert other[3] == (
        f"▲ another session took the engine at 12:31: this session's next step reads its whole prompt again ({OTHER})"
    )
    child = shown(doing(mine, slots={"main": held("r-3", CHILD, SESSION, True)}), route("daily-262k"))
    assert child[3].startswith("▲ a subagent of this session has the engine now at 12:31")
    nobody = shown(doing(mine, slots={"main": held("r-4", "")}), route("daily-262k"))
    assert nobody[3].startswith("▲ a request of no session took the engine at 12:31")
    cpu = shown(doing(ended("r-1", 6000, 100, preset="cpu-8k"), slots={"main": held("r-2", OTHER)}), route("cpu-8k"))
    assert cpu[3].startswith("the engine's newest request is another session's (12:31); it may keep this one's too")
    unknown = shown(doing(mine, slots={}), route("daily-262k"))
    assert unknown[3] == "whose conversation the engine holds: not known since the gateway started"


def test_the_panel_says_the_engine_holds_no_conversation_once_it_stopped_started_again_or_was_switched() -> None:
    mine = ended("r-1", 150000, 2661)
    stopped = shown(doing(mine), route(None))
    assert stopped[0].startswith("152,661 of 262,144 tokens"), "the last step's figures stay"
    assert stopped[2] == (
        "On the GPU: nothing of this session's (the main slot is stopped); its 152,661 tokens are read again at its "
        "next step"
    )
    assert stopped[3] == (
        "▲ the main slot is stopped: the engine holds no conversation; this session's next step reads its whole prompt "
        "again"
    )
    switched = shown(doing(mine), route("frontier-96k"))
    assert switched[2].startswith("On the GPU: nothing of this session's (the main slot was switched); its 152,661")
    assert switched[3].startswith("▲ the main slot was switched: the engine holds no conversation")
    assert not any("holds this session's" in line for line in switched)
    restarted = shown(doing(mine, slots={"main": held("r-1", SESSION, gone=True)}), route("daily-262k"))
    assert restarted[3].startswith("▲ its engine started again: the engine holds no conversation")


def test_the_panel_says_when_the_last_steps_answer_did_not_report_its_size() -> None:
    said = shown(doing({**ended("r-1", 0, 0), "usage": None}), route("daily-262k"))
    assert said[0] == "window 262,144 · OpenCode compacts at 245,760 · the last step's answer did not report its size"


def test_the_panel_says_why_the_totals_could_not_be_read() -> None:
    unavailable = {"session": SESSION, "unavailable": "the gateway did not answer"}
    assert [line.plain for line in lines(unavailable, 200)] == [
        "context totals not available: the gateway did not answer"
    ]

    class Refusing:
        def get(self, path: str, **params: Any) -> Any:
            if path == "workspaces/folder":
                return {"workspace": "myproject"}
            if path == "agents/flow/myproject":
                return {"flows": [{"session": SESSION, "version": 1, "status": "busy"}]}
            if path == f"agents/flow/myproject/{SESSION}":
                return {"version": 1, "base": 0, "head": {"session": SESSION}, "nodes": [], "items": [], "whole": True}
            raise ClientError("the gateway did not answer", "unavailable", 503)

    seen = Following(Refusing(), "/work/myproject").read()  # type: ignore[arg-type]
    assert seen is not None
    assert seen.context == unavailable, "the followed session's, with why"


def test_the_panel_says_when_the_slot_switched_to_another_preset() -> None:
    said = shown(doing(ended("r-1", 90000, 1000)), route("frontier-96k"))
    assert said[0].startswith("91,000 of 262,144 tokens"), "the step's window until the next step"
    assert said[-1] == "▲ the main slot now runs “frontier 96K” (98,304 tokens): its window applies from the next step"


def test_no_line_is_wider_than_the_panel() -> None:
    cases: list[tuple[dict[str, Any], dict[str, Any] | None]] = [
        (doing(ended("r-1", 150000, 2661, cached=147815), slots={"main": held("r-2", OTHER)}), route("frontier-96k")),
        (doing(ended("r-1", 6000, 100, preset="cpu-8k")), route("cpu-8k")),
        (doing(), route(None)),
        (doing(ended("r-1", 150000, 2661)), route(None)),
        ({"session": SESSION, "unavailable": "the gateway did not answer in 2 seconds"}, None),
    ]
    for width in range(12, 161):
        for activity, routes in cases:
            found = activity if routes is None else totals(SESSION, activity, routes, facts_of, OpenCode().compaction)
            drawn = lines(found, width, UTC)
            assert all(isinstance(line, Content) and line.cell_length <= width for line in drawn), width
    assert lines(None, 40) == [Content.styled("no session yet", "$clank-quiet")]


def gateway_of(kernel: Kernel, monkeypatch: pytest.MonkeyPatch, activity: dict[str, Any], preset: str) -> None:
    """The service's gateway, as if the followed session's steps had gone to KVMem on the main slot."""
    gateway = kernel.parts["gateway"]
    monkeypatch.setattr(gateway, "activity", lambda session="", subagents=False, ended=False: activity)
    monkeypatch.setattr(gateway, "routes", lambda: route(preset))
    monkeypatch.setattr(gateway, "facts", facts_of)


def panel(app: ClankConsole) -> ContextWindow:
    return app.query_one("#monitor-context-window", ContextWindow)


async def test_the_monitor_shows_the_followed_sessions_totals_in_the_context_window_panel(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    activity = doing(ended("r-1", 150000, 2661, cached=147815), slots={"main": held("r-1", flowlines.SESSION)})
    gateway_of(kernel, monkeypatch, activity, "daily-262k")
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 44)) as pilot:
        await opened(pilot, app)
        await settle(pilot, lambda: any("Draft the parameter gr" in line.plain for line in chart(app).drawn.lines))
        await settle(pilot, lambda: "152,661" in str(panel(app).content))
        await settle(pilot, lambda: known(app))
        assert_frame(await steady_frame(pilot, app), "monitor-session-context-160")


async def test_totals_that_did_not_change_are_not_drawn_again(
    kernel: Kernel, client: Client, home: Home, monkeypatch: pytest.MonkeyPatch
) -> None:
    activity = doing(ended("r-1", 150000, 2661), slots={"main": held("r-1", flowlines.SESSION)})
    gateway_of(kernel, monkeypatch, activity, "daily-262k")
    board(kernel)
    app = make(client, home)
    async with app.run_test(size=(160, 44)) as pilot:
        await opened(pilot, app)
        await settle(pilot, lambda: "152,661" in str(panel(app).content) and known(app))
        await steady_frame(pilot, app)  # every panel drawn, so none changes the page's width meanwhile
        draws = panel(app).draws
        await pilot.pause(2.5)
        assert panel(app).draws == draws, "the same totals: not drawn again"
        activity["slots"] = {"main": held("r-2", OTHER, flying=True)}
        await settle(pilot, lambda: "took the engine" in str(panel(app).content) or "has the engine" in str(
            panel(app).content))  # fmt: skip
        assert panel(app).draws == draws + 1


def sized(message: dict[str, Any], prompt: int, cached: int = 0, answer: int = 200) -> dict[str, Any]:
    """A step whose tokens OpenCode counted: its prompt (and the part read from the cache) and its answer."""
    message["info"]["tokens"] = {"total": prompt + answer, "input": prompt - cached, "output": answer, "reasoning": 0,
                                 "cache": {"read": cached, "write": 0}}  # fmt: skip
    return message


def grown() -> dict[str, Any]:
    """A session's flow: steps growing, a step the loop guard stopped, a compaction by OpenCode, two steps after."""
    looped = {"name": "APIError", "data": {"message": "Clank's loop guard stopped the answer: it repeated itself"}}
    flow = Flow(flowlines.SESSION)
    t = START
    flow.history(flowlines.page([
        flowlines.user("msg_01", t, "Plan the study."),
        sized(flowlines.step("msg_02", "msg_01", t + 10_000, [], completed=t + 12_000), 20_000),
        sized(flowlines.step("msg_03", "msg_01", t + 20_000, [], completed=t + 22_000), 60_000),
        sized(flowlines.step("msg_04", "msg_01", t + 30_000, [], completed=t + 32_000), 120_000),
        flowlines.step("msg_05", "msg_01", t + 40_000, [], completed=t + 55_000, error=looped),
        sized(flowlines.step("msg_06", "msg_01", t + 60_000, [], completed=t + 62_000), 230_000),
        flowlines.compacting("msg_07", "msg_06", t + 70_000),
        sized(flowlines.step("msg_08", "msg_07", t + 71_000, [], completed=t + 80_000, summary=True), 230_000),
        sized(flowlines.step("msg_09", "msg_07", t + 90_000, [], completed=t + 92_000), 18_000),
        sized(flowlines.step("msg_10", "msg_07", t + 100_000, [], completed=t + 102_000), 25_000),
        flowlines.step("msg_11", "msg_07", t + 110_000, []),
    ]))  # fmt: skip
    for each in flowlines.lines([{"type": "session.compacted", "properties": {"sessionID": flowlines.SESSION}}]):
        flow.heard(each)
    return flow.view()


def test_the_growth_spark_marks_compactions_and_loop_guard_stops() -> None:
    points = growth(grown())
    assert [(point.size, point.mark) for point in points] == [
        (20_200, ""),
        (60_200, ""),
        (120_200, ""),
        (120_200, "looped"),
        (230_200, ""),
        (230_200, "compacted"),
        (18_200, ""),
        (25_200, ""),
    ], "each finished step's size; a stopped step leaves the size as it was; the summary is the compaction"
    drawn = spark_line(points, 120, 262_144, UTC)
    cells = drawn.plain.removeprefix("this session ")[: len(points)]
    assert len(cells) == len(points)
    styles = {span.style for span in drawn.spans if span.start == len("this session ") + 3}
    assert "$clank-failed" in styles, "the loop guard's stop in the failed color"
    styles = {span.style for span in drawn.spans if span.start == len("this session ") + 5}
    assert "$clank-attention" in styles, "the compaction in the attention color"
    assert drawn.plain.endswith(f"{mark('failed')} 11:58 the loop guard stopped step 4 · 11:59 compacted by OpenCode")
    assert cells[2] > cells[1] > cells[0], "it grew"
    assert cells[6] < cells[4], "the compaction freed room"
    said = [
        {"kind": "step", "id": "s1", "n": 1, "ended": "finished", "created": START, "tokens": {"total": 9_000}},
        {"kind": "band", "id": "compacted:1", "at": [START + 1, "", 0], "auto": True, "done": True},
        {"kind": "step", "id": "s2", "n": 2, "ended": "finished", "created": START + 2, "tokens": {"total": 4_000}},
    ]
    assert [(point.size, point.mark, point.by) for point in growth({"head": {}, "nodes": said})] == [
        (9_000, "", ""),
        (9_000, "compacted", "OpenCode"),
        (4_000, "", ""),
    ], "a compaction OpenCode said with no summary: a cell of its own, where it was"


def test_the_growth_spark_fits_the_panel_and_says_nothing_before_a_step_ended() -> None:
    points = growth(grown())
    for width in range(12, 161):
        assert spark_line(points, width, 262_144, UTC).cell_length <= width, width
    assert growth(None) == []
    assert growth({"head": {}, "nodes": [{"kind": "step", "id": "s", "n": 1, "ended": "working"}]}) == []
    totals = context(doing(ended("r-1", 150000, 2661)), route("daily-262k"))
    assert not any(line.plain.startswith("this session") for line in lines(totals, 120, UTC, view=None))
    shown = [line.plain for line in lines(totals, 120, UTC, view=grown())]
    assert any(line.startswith("this session ") for line in shown), "drawn under the GPU's line"


def parted(width: int) -> list[Content]:
    """The panel's lines for board A's request, its parts estimated."""
    activity = doing(ended("r-19", PROMPT, ANSWER, cached=PROMPT - 2000, census=board_a_census()))
    return lines(context(activity, route("daily-262k")), width, UTC)


def test_the_bar_is_drawn_by_part_and_the_legend_says_what_each_part_holds() -> None:
    drawn = parted(200)
    cells: dict[str, int] = {}
    for span in drawn[1].spans:
        cells[str(span.style)] = cells.get(str(span.style), 0) + span.end - span.start
    assert {name: cells.get(f"$clank-part-{name}", 0) for name in ("system", "tools", "yours", "text", "thinking",
                                                                    "calls", "results", "loop")} == {
        "system": 3, "tools": 8, "yours": 0, "text": 0, "thinking": 2, "calls": 0, "results": 14, "loop": 2,
    }, "the 29 cells used, shared by the parts' tokens (the largest remainders: tools, loop, system)"  # fmt: skip
    assert drawn[1].cell_length == 200
    assert drawn[2].plain == (
        "estimate: █ system 3.3K · █ tools 10.2K · █ you 25 · █ thinking 2.9K · █ calls 606 · █ results 18.6K · "
        "█ loop 2.0K"
    )
    assert next(str(span.style) for span in drawn[2].spans if drawn[2].plain[span.start] == "█") == (
        "$clank-part-system"
    ), "each swatch in its part's color"
    plain = context(doing(ended("r-1", 150000, 2661)), route("daily-262k"))
    assert not any(line.plain.startswith("estimate") for line in lines(plain, 200, UTC)), "no census: no parts said"


def test_the_legend_gives_up_its_smallest_parts_first_and_no_line_is_wider_than_the_panel() -> None:
    narrow = parted(60)[2].plain
    assert "results 18.6K" in narrow
    assert narrow.index("results 18.6K") < narrow.index("loop 2.0K"), "loop text last; the rest in the bar's order"
    assert "you 25" not in narrow, "the smallest part goes first"
    assert narrow.endswith(" more"), "how many it left out"
    for width in range(12, 161):
        assert all(line.cell_length <= width for line in parted(width)), width
