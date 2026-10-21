"""Design 0011 §2, §8, §9 and §11 (R3): Home and This folder as boards E1 and E2. Home's panels are Happening now
beside Waiting for you, then What runs, then the History, declared in that order; the first two stand side by side where
the page gives them room (170 columns, the machine column shown) and stack at 80, Happening now above; a question
waiting asks for more room, so the two stack unless the row gives Waiting for you a question's width, inside the
style's padding and past its room between panels, whatever the style sets them to. Each row of What runs that says a
state is led by its state's mark, in its state's color (● as wanted, or changing; ○ not running; ✗ failed; … not read
yet), its name and its key's hint in `quiet`; the mark is colored where it stands, whatever glyph the style gives it,
and a row that wraps keeps each mark with the words it leads. The models' row has a mark for each slot; the rows that
say no state (the GPU, the machine, the folder) have none. Waiting for you says nothing waits with the style's done
mark, on Home and on This folder. This folder's Then work and What runs from here stand side by side at 170 columns
and stack at 80, between Get ready to work here and Waiting for you."""

import json

import pytest
from textual.content import Content
from textual.widgets import Label

from clank.client import Client
from clank.console.app import ClankConsole
from clank.console.data import ConsoleData
from clank.console.pages import Page
from clank.console.pages.home import (
    docker_line,
    folder_line,
    gateway_line,
    gpu_line,
    machine_line,
    models_line,
    service_line,
    workspaces_line,
)
from clank.console.panel import Panel, PanelGrid
from clank.console.style import LoadedStyle, use
from clank.kernel.console_kinds import StyleSettings
from clank.kernel.core import Kernel
from clank.kernel.events import CLANK
from clank.kernel.home import Home
from clank.kernel.questions import Option, QuestionDraft
from tests.console.frames import FOLDER, frame_when, settle, steady_frame

pytestmark = pytest.mark.anyio

GATEWAY = {"state": "running", "port": 18210, "problem": "", "served": 3, "requests": [], "last": None}
GOOD, CHANGING, OFF, FAILED, QUIET = "$clank-good", "$clank-attention", "$clank-quiet", "$clank-failed", "$clank-quiet"


def colored(content: Content) -> list[tuple[str, str]]:
    """Each colored part of a line, in order: its text and its color."""
    spans = sorted(content.spans, key=lambda span: span.start)
    return [(content.plain[span.start : span.end], str(span.style)) for span in spans]


def colored_at(content: Content) -> list[tuple[int, str, str]]:
    """Each colored part of a line, in order: where it starts, its text and its color."""
    spans = sorted(content.spans, key=lambda span: span.start)
    return [(span.start, content.plain[span.start : span.end], str(span.style)) for span in spans]


def test_each_row_of_what_runs_that_says_a_state_is_led_by_its_mark_in_its_states_color() -> None:
    docker = {"state": "running", "summary": "Docker Desktop · running · 2 containers"}
    running = docker_line(docker)
    assert running.plain == "docker     ● Docker Desktop · running · 2 containers   s stops it"
    assert colored(running) == [("docker", QUIET), ("●", GOOD), ("s stops it", QUIET)]
    starting = docker_line({"state": "starting", "summary": "Docker Desktop · starting"})
    assert colored(starting)[1] == ("●", CHANGING)
    stopped = docker_line({"state": "stopped", "summary": "Docker Desktop · stopped"})
    assert stopped.plain == "docker     ○ Docker Desktop · stopped   s starts it"
    assert colored(stopped)[1] == ("○", OFF)
    assert docker_line(None).plain == "docker     … not read yet"
    assert colored(docker_line(None))[1] == ("…", CHANGING)
    problem = gateway_line({**GATEWAY, "state": "problem", "problem": "port 18210 is taken"})
    assert problem.plain == "gateway    ✗ problem: port 18210 is taken   F4, then g, starts it"
    assert colored(problem)[1] == ("✗", FAILED)
    assert gateway_line(GATEWAY).plain == "gateway    ● running on port 18210 · idle · 3 requests served"
    assert gateway_line({**GATEWAY, "state": "stopped"}).plain == "gateway    ○ stopped   F4, then g, starts it"
    assert service_line(ConsoleData()).plain.startswith("service    ○ not running: `clank serve --background`")
    assert workspaces_line({"state": "running", "containers": []}).plain == "workspace  ○ none running   F6 lists them"


def test_the_models_row_has_a_mark_for_each_slot() -> None:
    data = ConsoleData(
        slots=[
            {"name": "main", "preset": "daily", "status": "ready", "reason": ""},
            {"name": "fast", "preset": None, "status": "stopped", "reason": "unloaded"},
            {"name": "vision", "preset": None, "status": "failed", "reason": "out of memory"},
        ],
        presets=[{"id": "daily", "title": "daily 262K"}],
    )
    shown = models_line(data)
    assert shown.plain == (
        "models     ● main: daily 262K · ready   ○ fast: stopped (unloaded)   ✗ vision: failed (out of memory)   "
        "8 opens Models"
    )
    assert [part for part in colored(shown) if part[0] in "●○✗"] == [("●", GOOD), ("○", OFF), ("✗", FAILED)]


def test_a_mark_is_colored_where_it_stands_even_when_its_glyph_is_a_letter_of_the_words_before_it() -> None:
    use(LoadedStyle("plain", StyleSettings.model_validate({"marks": {"on": "*", "off": "o", "failed": "x"}})))
    data = ConsoleData(
        slots=[
            {"name": "main", "preset": "frontier", "status": "ready", "reason": ""},
            {"name": "fast", "preset": None, "status": "stopped", "reason": "unloaded"},
            {"name": "vision", "preset": None, "status": "failed", "reason": "too big for the GPU"},
        ],
        presets=[{"id": "frontier", "title": "frontier 96K"}],
    )
    for width in (None, 60, 90, 200):
        shown = models_line(data, width)
        marks = [part for part in colored_at(shown) if part[2] in (GOOD, OFF, FAILED) and len(part[1]) == 1]
        plain = shown.plain
        assert marks == [
            (plain.index("* main"), "*", GOOD),
            (plain.index("o fast"), "o", OFF),
            (plain.index("x vision"), "x", FAILED),
        ], width
        assert colored_at(shown)[-1] == (len(plain) - len("8 opens Models"), "8 opens Models", QUIET)


THREE_SLOTS = ConsoleData(
    slots=[
        {"name": "main", "preset": "daily", "status": "ready", "reason": ""},
        {"name": "fast", "preset": None, "status": "stopped", "reason": "unloaded"},
        {"name": "vision", "preset": None, "status": "stopped", "reason": ""},
    ],
    presets=[{"id": "daily", "title": "daily 262K"}],
)


def test_a_row_that_wraps_keeps_each_mark_with_the_words_it_leads() -> None:
    said = "models ● main: daily 262K · ready ○ fast: stopped (unloaded) ○ vision: stopped 8 opens Models"
    for width in range(30, 141):
        lines = models_line(THREE_SLOTS, width).plain.splitlines()
        assert not [line for line in lines if line.rstrip().endswith(("●", "○", "✗"))], (width, lines)
        assert " ".join(" ".join(lines).split()) == said, (width, lines)
        assert not [line for line in lines if "\u00a0" in line], "no space of the wrapping's own is left"


def test_the_rows_that_say_no_state_have_no_mark() -> None:
    gpu = {"name": "NVIDIA GeForce RTX 5080", "use": 3.0, "memory_used": 2041 << 20, "memory_total": 16303 << 20,
           "temperature": 34}  # fmt: skip
    assert gpu_line([{"gpus": [gpu]}]).plain == "gpu        RTX 5080 · 3% busy · 2.0 GB of 15.9 GB in use · 34°C"
    assert machine_line(None).plain == "machine    not detected yet   d runs the doctor, which detects it"
    assert folder_line("C:/work/paper").plain == "folder     C:/work/paper   F4: get ready and work here"
    assert colored(folder_line("C:/work/paper")) == [("folder", QUIET), ("F4: get ready and work here", QUIET)]


def test_a_row_wraps_under_its_value_after_its_mark_and_keeps_its_hint_whole() -> None:
    docker = {"state": "running", "summary": "Docker Desktop · running · 2 containers running, none of them Clank's"}
    assert docker_line(docker, width=86).plain.splitlines() == [
        "docker     ● Docker Desktop · running · 2 containers running, none of them Clank's",
        "             s stops it",
    ]
    assert docker_line(docker, width=120).plain == (
        "docker     ● Docker Desktop · running · 2 containers running, none of them Clank's   s stops it"
    )
    narrow = docker_line(docker, width=40).plain.splitlines()
    assert all(line.startswith(" " * 13) for line in narrow[1:])
    assert narrow[-1].endswith("s stops it")
    assert all(len(line) <= 40 for line in narrow)


def make(client: Client, home: Home, page: str = "home") -> ClankConsole:
    app = ClankConsole(client, home=home, page=page)
    app.folder = FOLDER
    return app


def panels(page: Page) -> dict[str, Panel]:
    return {panel.id or "": panel for panel in page.query(Panel)}


def beside(left: Panel, right: Panel) -> bool:
    """Side by side: the same top row, the left one ending before the right one starts."""
    return left.region.y == right.region.y and left.region.right <= right.region.x


def above(top: Panel, below: Panel) -> bool:
    """Stacked: the same left edge, the top one ending before the one below starts."""
    return top.region.x == below.region.x and top.region.bottom <= below.region.y


@pytest.mark.parametrize("width", [170, 80])
async def test_happening_now_stands_beside_waiting_for_you_at_170_columns_and_above_it_at_80(
    client: Client, home: Home, width: int
) -> None:
    app = make(client, home)
    async with app.run_test(size=(width, 60)) as pilot:
        await frame_when(pilot, app, "Fake Docker", "Nothing waits for you")
        page = app.query_one("#page-home", Page)
        assert page.PANELS == ("now", "waiting", "runs", "history")
        now, waiting, runs, history = (panels(page)[id] for id in page.PANELS)
        assert all(panel.region.area for panel in (now, waiting, runs, history)), "every panel on screen"
        assert beside(now, waiting) if width == 170 else above(now, waiting)
        assert now.region.height == waiting.region.height or width == 80, "side by side, they share their height"
        assert above(now, runs)
        assert runs.region.bottom <= history.region.y
        assert runs.region.y >= waiting.region.bottom


@pytest.mark.parametrize("width", [170, 80])
async def test_this_folders_what_runs_from_here_stands_beside_then_work_at_170_columns_and_below_it_at_80(
    client: Client, home: Home, width: int
) -> None:
    app = make(client, home, "folder")
    async with app.run_test(size=(width, 60)) as pilot:
        await frame_when(pilot, app, "Then work", "No question waits")
        page = app.query_one("#page-folder", Page)
        items, work, runs, waiting = (panels(page)[id] for id in page.PANELS)
        assert (work.id, runs.id) == ("folder-work-panel", "folder-runs")
        assert all(panel.region.area for panel in (items, work, runs, waiting)), "every panel on screen"
        assert beside(work, runs) if width == 170 else above(work, runs)
        assert items.region.bottom <= work.region.y
        assert items.region.bottom <= runs.region.y
        assert max(work.region.bottom, runs.region.bottom) <= waiting.region.y


async def test_nothing_waiting_is_said_with_the_styles_done_mark_on_home_and_on_this_folder(
    client: Client, home: Home
) -> None:
    app = make(client, home)
    async with app.run_test(size=(170, 60)) as pilot:
        frame = await frame_when(pilot, app, "Fake Docker", "Nothing waits for you")
        assert "✓ Nothing waits for you." in frame
        app.show_page("folder")
        frame = await frame_when(pilot, app, "No question waits")
        assert "✓ No question waits." in frame


STOP = QuestionDraft(
    type="approval",
    title="Stop Docker Desktop?",
    detail="2 containers that Clank did not start are running: another-model-relay, toolbox-sandbox-017.",
    options=[Option(id="stop", label="Stop them and Docker", key="y"), Option(id="cancel", label="Cancel", key="n")],
    default="cancel",
)


@pytest.mark.parametrize("width", [170, 260])
async def test_a_question_waiting_stacks_waiting_for_you_under_happening_now_unless_the_row_gives_it_a_questions_width(
    client: Client, kernel: Kernel, home: Home, width: int
) -> None:
    app = make(client, home)
    async with app.run_test(size=(width, 60)) as pilot:
        await frame_when(pilot, app, "Fake Docker", "Nothing waits for you")
        page = app.query_one("#page-home", Page)
        now, waiting = panels(page)["now"], panels(page)["waiting"]
        assert beside(now, waiting)
        kernel.questions.ask(STOP, asked_by=CLANK)
        asked = app.query_one("#waiting-text", Label)
        await settle(pilot, lambda: "Stop Docker Desktop?" in str(asked.content))  # not the history's line
        await steady_frame(pilot, app)
        assert above(now, waiting) if width == 170 else beside(now, waiting)
        assert waiting.region.width >= 44 or above(now, waiting), "a question's width, or the page's"


SPACED = {"schema": "style/1", "title": "Spaced", "spacing": {"panel_padding": 3, "columns_between": 8}}


async def test_a_question_waiting_gets_its_width_inside_the_styles_padding_and_past_its_room_between_panels(
    client: Client, kernel: Kernel, home: Home
) -> None:
    (home.config / "styles").mkdir(parents=True, exist_ok=True)
    (home.config / "styles" / "spaced.json").write_text(json.dumps(SPACED), encoding="utf-8")
    (home.config / "console.json").write_text(json.dumps({"schema": "console/1", "style": "spaced"}), encoding="utf-8")
    app = make(client, home)
    async with app.run_test(size=(220, 60)) as pilot:
        await frame_when(pilot, app, "Fake Docker", "Nothing waits for you")
        page = app.query_one("#page-home", Page)
        row, now, waiting = page.query_one("#home-top", PanelGrid), panels(page)["now"], panels(page)["waiting"]
        beyond = 220 - row.size.width  # the page's padding and the machine column
        kernel.questions.ask(STOP, asked_by=CLANK)
        asked = app.query_one("#waiting-text", Label)
        await settle(pilot, lambda: "Stop Docker Desktop?" in str(asked.content))
        for width in (134, 140, 151, 152, 160, 200):  # 134: Clank's own padding and room between, the old least row
            await pilot.resize_terminal(width + beyond, 60)
            await settle(pilot, lambda: row.size.width == app.size.width - beyond)
            await steady_frame(pilot, app)
            assert above(now, waiting) or waiting.content_size.width >= 40, (width, waiting.content_size.width)
        assert beside(now, waiting), "the row gives a question its width at 200 columns: side by side"
