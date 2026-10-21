"""Design 0004 §9 (the owner's request, 2026-10-14): the console shows the machine's CPU, GPU, memory, disks and network
all the time, on the right, and is more dynamic. The gauges draw a share as a bar in eighths of a cell, green, then
yellow when busy, red when nearly full; the last values as a sparkline; sizes and rates briefly; and a spinner. The
column's parts give each meter's lines from the readings, and what Clank is doing with a spinner while it runs; the
header has a pill for each part that runs, its dot in its state's color. A reading the service sends live is kept with
the last five minutes'. The column shows at 130 columns and more, and F5 shows or hides it at any width.

Design 0011 §7, §9 and §11 (R2): the machine column (`MachineColumn`, `#machine`) is two panels, "Machine" and "Clank
now", without a border of its own; each meter is drawn for the inside of its panel, so its lines fit inside the panels
at 100 columns (with F5), 130 and 170; the Machine panel's room is the column's height less the Clank now panel (its
lines and its two borders), its own two borders and the row between them, counted again on the spinner's turn when
Clank now changes its number of lines; when the column is short the blank lines between meters go first, then whole
meters from the last, and the Machine panel's note says how many are hidden."""

import re
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest
from rich.cells import cell_len
from textual.content import Content
from textual.pilot import Pilot
from textual.widgets import Label

from clank.client import Client
from clank.console.app import ClankConsole
from clank.console.data import ConsoleData, Update, apply
from clank.console.gauges import bar, fit, rate, size, spark, spinner, tall_spark
from clank.console.header import header
from clank.console.machine import (
    MachineColumn,
    Seen,
    busy,
    containers,
    cpu,
    disks,
    gpus,
    memory,
    network,
    operations,
    processes,
    requests,
    stacked,
)
from clank.console.panel import Panel
from clank.console.snapshot import render_text
from clank.kernel.core import Kernel
from clank.kernel.events import CLANK
from clank.kernel.home import Home
from clank.kernel.questions import Option, QuestionDraft
from tests.console.conftest import READING
from tests.console.frames import FOLDER, settle, steady_frame

NOW = datetime(2026, 10, 11, 13, 54, tzinfo=UTC)
COLUMN = {100: 38, 130: 38, 170: 46}  # the machine column's width in a terminal this wide (F5 at 100 columns)
INSIDE = 4  # a panel's two borders and its column of padding on each side


def colors(content: Any) -> list[tuple[str, str]]:
    return [(content.plain[span.start : span.end], str(span.style)) for span in content.spans]


def test_a_bar_fills_in_eighths_of_a_cell_and_is_colored_by_how_full() -> None:
    assert bar(0.5, 10).plain == "█████░░░░░"
    assert bar(0.53, 10).plain == "█████▎░░░░"
    assert colors(bar(0.3, 4))[0] == ("█▎", "$clank-low")
    assert colors(bar(0.7, 4))[0] == ("██▊", "$clank-busy")
    assert colors(bar(0.95, 4))[0] == ("███▊", "$clank-full")
    assert bar(1.4, 3).plain == "███", "a share past full fills the bar"


def test_a_sparkline_shows_the_last_values_padded_on_the_left_and_sizes_and_rates_are_brief() -> None:
    assert spark([0, 50, 100], 5).plain == "  ▁▅█"
    assert spark(range(20), 3, top=19).plain == "▇██"
    upper, lower = tall_spark([0, 25, 50, 75, 100], 6)
    assert (upper.plain, lower.plain) == ("    ▄█", " ▁▄███"), "two cells tall: twice the steps, its floor kept"
    assert [size(812), size(1536), size(15.3 * (1 << 30)), size(812 * (1 << 30))] == [
        "812 B",
        "2 KB",
        "15.3 GB",
        "812 GB",
    ]
    assert rate(1.2 * (1 << 20)) == "1.2 MB/s"
    assert (spinner(0), spinner(11)) == ("⣾", "⢿")
    assert fit("a long line", 6) == "a lon…"


def test_the_panel_shows_each_meter_from_the_last_reading() -> None:
    seen = Seen([dict(READING)] * 3)
    shown = [line.plain for part in (cpu, memory, gpus, disks, network) for line in part(seen, 36)]
    assert shown[0].startswith("CPU  ")
    assert shown[0].endswith(" 12%")
    assert shown[2].startswith("3s ")
    assert "▂▂▂ " in shown[2], "its last seconds, two cells tall"
    assert shown[2].endswith(" max 12%"), "and their peak"
    assert shown[3].startswith("thr  ")
    assert shown[3].endswith("16 threads")
    assert shown[4].startswith("RAM  ")
    assert shown[4].endswith(" 38%")
    assert shown[5] == "     24.0 GB of 64.0 GB"
    assert shown[6].endswith(" max 38%")
    assert shown[7].startswith("GPU  ")
    assert shown[7].endswith("  3%")
    assert shown[9].endswith(" max 3%")
    assert shown[10] == "     RTX 5080 · 34°C · 18 W"
    assert shown[11].startswith("VRAM ")
    assert shown[11].endswith(" 13%")
    assert shown[12] == "     2.0 GB of 15.9 GB"
    assert shown[13] == "Disk read 12.0 MB/s · write 3.0 MB/s"
    assert shown[14].startswith("3s ")
    assert "███ " in shown[14], "its last seconds, scaled to its largest"
    assert shown[14].endswith("max 15.0 MB/s"), "which is said"
    assert len({len(shown[line]) for line in (2, 6, 9, 14, 17)}) == 1, "every graph as long, their peaks in a column"
    assert shown[15].startswith("     C: ")
    assert shown[15].endswith(" 44%")
    assert shown[16] == "Net  ↓ 1.2 MB/s  ↑ 40 KB/s"
    assert shown[17].endswith(" max 1.2 MB/s")
    assert all(len(line) <= 36 for line in shown)
    full = {
        **READING,
        "gpus": [{**READING["gpus"][0], "memory_used": READING["gpus"][0]["memory_total"] - (600 << 20)}],
    }
    assert gpus(Seen([full]), 36)[-1].plain == "     little room for the desktop", "under 1 GB free is said"


def test_what_clank_does_turns_a_spinner_while_it_runs_and_says_how_the_last_request_went() -> None:
    running = {"id": "op-1", "title": "Open a workspace", "status": "running", "planned_steps": 5,
               "steps": [{"number": 2, "name": "image"}]}  # fmt: skip
    waiting = {"id": "op-2", "title": "Stop Docker", "status": "waiting", "planned_steps": 1, "steps": []}
    request = {"role": "agent", "phase": "answering", "tokens": 340, "per_second": 52.3}
    last = {"time": "2026-10-11T13:50:02.000000Z", "tokens": 812, "per_second": 57.1, "status": 200, "error": ""}
    activity = {"state": "running", "requests": [request], "last": last}
    seen = Seen([], [running, waiting], activity, frame=2, zone=UTC)
    assert [line.plain for line in operations(seen, 36)] == [
        "⣻ Open a workspace · 2/5 image",
        "? Stop Docker · asks you",
    ]
    assert [line.plain for line in requests(seen, 36)] == [
        "⣻ answering · 340 tok · 52/s",
        "✓ last 13:50:02 · 812 out · 57/s",
    ]
    told = Seen([], [], {**activity, "last": {**last, "prompt_tokens": 25920}}, zone=UTC)
    assert requests(told, 48)[-1].plain == "✓ last 13:50:02 · 25,920 in · 812 out · 57/s"
    assert busy(seen)
    assert not busy(Seen([], [waiting], {**activity, "requests": []}))


def test_the_panel_shows_each_workspaces_container_and_the_busiest_and_largest_processes() -> None:
    """The owner, 2026-10-15: the panel did not say enough."""
    reading = {
        **READING,
        "containers": [{"name": "myproject", "cpu": 50.0, "memory_used": 3 << 30, "memory_total": 12 << 30}],
        "processes": [
            {"pid": 7, "name": "vmmemWSL", "cpu": 23.4, "memory": 18 << 30},
            {"pid": 9, "name": "Code.exe", "cpu": 1.0, "memory": 900 << 20},
        ],
    }
    seen = Seen([reading])
    [box] = [line.plain for line in containers(seen, 38)]
    assert box.split() == ["Work", "myproject", "50%", "3.0", "GB", "of", "12.0", "GB"]
    assert box.index("50%") == len("Work ") + 12 + 1 + 1, "the name padded, so the columns line up"
    shown = [line.plain for line in processes(seen, 38)]
    assert shown[0].startswith("Top ")
    assert shown[0].endswith("cpu   memory")
    assert shown[1].split() == ["vmmemWSL", "23%", "18.0", "GB"]
    assert shown[2].split() == ["Code", "1%", "900", "MB"], "a program's .exe is left out"
    assert all(len(line) <= 38 for line in shown)
    assert containers(Seen([READING]), 38) == [], "nothing when no workspace runs"


def test_the_meters_are_parted_by_a_blank_line_when_they_fit_so_else_the_blank_lines_go_then_the_last_meters() -> None:
    blocks = [[Content("cpu")] * 4, [Content("ram")] * 3, [Content("gpu")] * 6]

    def shown(room: int) -> tuple[list[str], int]:
        lines, hidden = stacked(blocks, room)
        return [line.plain for line in lines], hidden

    assert shown(15) == (["cpu"] * 4 + [""] + ["ram"] * 3 + [""] + ["gpu"] * 6, 0)
    assert shown(14) == (["cpu"] * 4 + ["ram"] * 3 + ["gpu"] * 6, 0), "the blank lines go first"
    assert shown(12) == (["cpu"] * 4 + ["ram"] * 3, 1), "then the last meter, whole"
    assert shown(2) == (["cpu"] * 4, 2), "the first is always shown"


def test_the_header_has_a_pill_for_each_part_that_runs_and_a_spinner_while_something_runs() -> None:
    data = ConsoleData(service={"started": "2026-10-11T11:40:00.000000Z"}, docker={"state": "stopped"}, connected=True)
    data.slots = [{"name": "main", "status": "ready", "preset": "daily-262k"}]
    data.presets = [{"id": "daily-262k", "title": "daily 262K"}]
    activity: dict[str, Any] = {"state": "running", "requests": [{}], "last": None}
    shown = header(data, activity, NOW, heard=True, frame=3)
    assert (
        shown.plain
        == " ◆ CLANK   ● service up 2h14m  ● docker stopped  ● daily 262K  ● gateway · 1 in flight  ⢿ working"
    )
    pills = [(text, style) for text, style in colors(shown) if text.startswith("●")]
    assert pills == [
        ("● service up 2h14m", "$clank-good"),
        ("● docker stopped", "$clank-failed"),
        ("● daily 262K", "$clank-good"),
        ("● gateway · 1 in flight", "$clank-good"),
    ], "each pill whole in its state's color (design 0011 §7)"
    assert header(ConsoleData(), None, NOW, heard=False, frame=None).plain == " ◆ CLANK   ● connecting"
    narrow = header(data, activity, NOW, heard=True, frame=None, folder="C:/work/paper", width=60)
    assert narrow.plain == " ◆ CLANK  paper   ● service  ● docker  ● daily 262K  ● gateway", "short words when narrow"


def test_a_reading_sent_live_is_kept_with_the_last_five_minutes() -> None:
    data = ConsoleData(meters=[{"cpu": float(n)} for n in range(300)])
    assert apply(data, Update("meter", {"cpu": 300.0})) == {"meters"}
    assert len(data.meters) == 300
    assert (data.meters[0]["cpu"], data.meters[-1]["cpu"]) == (1.0, 300.0)


@pytest.mark.anyio
async def test_the_machine_column_shows_at_130_columns_and_more_and_f5_shows_or_hides_it(
    client: Client, home: Home
) -> None:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = FOLDER
    async with app.run_test(size=(160, 40)) as pilot:
        column = app.query_one("#machine", MachineColumn)
        await settle(pilot, lambda: "RTX 5080" in str(app.query_one("#machine-meters").render()))
        assert column.display
        await pilot.press("f5")
        await settle(pilot, lambda: not column.display)
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        column = app.query_one("#machine", MachineColumn)
        assert not column.display
        await pilot.press("f5")
        await settle(pilot, lambda: column.display)


async def column_shown(pilot: Pilot[Any], app: ClankConsole) -> MachineColumn:
    """The machine column once its meters are drawn and the frame has stopped changing."""
    column = app.query_one("#machine", MachineColumn)
    await settle(pilot, lambda: column.display and "RTX 5080" in render_text(app))
    await steady_frame(pilot, app)
    return column


def drawn(app: ClankConsole, id: str) -> list[str]:
    """The lines a label of the column was given."""
    return str(app.query_one(f"#{id}", Label).content).splitlines()


@pytest.mark.anyio
@pytest.mark.parametrize("width", [100, 130, 170])
async def test_the_machine_columns_lines_fit_inside_its_two_panels(client: Client, home: Home, width: int) -> None:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = FOLDER
    async with app.run_test(size=(width, 50)) as pilot:
        if width < 130:
            await pilot.press("f5")
        column = await column_shown(pilot, app)
        rows = render_text(app).splitlines()
        panels = list(column.query(Panel))
        assert [panel.title for panel in panels] == ["Machine", "Clank now"]
        assert column.outer_size.width == COLUMN[width], "the column keeps its widths"
        inside = COLUMN[width] - INSIDE
        for panel in panels:
            area, box = column.region, panel.region
            assert (box.x, box.right) == (area.x, area.right), f"{panel.title}: the column's whole width"
            assert box.bottom <= area.bottom, f"{panel.title}: inside the column"
            assert re.fullmatch(rf"┌─ {panel.title} ─+┐", rows[box.y][box.x : box.right]), panel.title
            assert re.fullmatch(r"└─+┘", rows[box.bottom - 1][box.x : box.right]), panel.title
            assert panel.query_one(Label).content_size.width == inside, panel.title
        meters = drawn(app, "machine-meters")
        assert cell_len(meters[0]) == inside, "each meter drawn for the inside of its panel: the CPU's bar fills it"
        assert all(cell_len(line) <= inside for line in meters + drawn(app, "machine-now"))
        for panel, label in zip(panels, ("machine-meters", "machine-now"), strict=True):
            box, lines = panel.region, drawn(app, label)
            shown = [row[box.x + 2 : box.right - 2].rstrip() for row in rows[box.y + 1 : box.bottom - 1]]
            assert shown[: len(lines)] == [line.rstrip() for line in lines], f"{panel.title}: each line whole, as drawn"


@pytest.mark.anyio
@pytest.mark.parametrize(("height", "spaced"), [(31, True), (30, False)])
async def test_the_machine_panel_has_the_column_less_clank_now_and_the_blank_lines_between_meters_go_first(
    client: Client, home: Home, height: int, spaced: bool
) -> None:
    """The column is 28 rows at 31: "Clank now" is 3 (its line and two borders), the row between them 1, and the
    Machine panel's own borders 2, which leaves 22 rows inside it: its 18 lines and the 4 blank lines between its 5
    meters. At 30 the blank lines go, and every meter is still shown."""
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = FOLDER
    async with app.run_test(size=(130, height)) as pilot:
        column = await column_shown(pilot, app)
        meters = drawn(app, "machine-meters")
        assert len(drawn(app, "machine-now")) == 1
        assert ("" in meters) == spaced
        assert len(meters) == (22 if spaced else 18), "every meter shown"
        assert meters[-2].startswith("Net "), "the last meter, whole"
        now = app.query_one("#machine-now-panel", Panel)
        assert now.region.bottom <= column.region.bottom, "Clank now, whole, under the Machine panel"
        if spaced:
            assert now.region.bottom == column.region.bottom, "the two panels fill the column"
        assert app.query_one("#machine-meters-panel", Panel).note == ""


@pytest.mark.anyio
async def test_a_turn_of_the_spinner_draws_the_machine_panel_again_when_clank_now_changes_its_number_of_lines(
    client: Client, home: Home
) -> None:
    """At 31 rows the Machine panel just holds its meters with a blank line between each (the test above). A model
    request in flight and how the last one went make Clank now two lines, so the Machine panel one row shorter: on the
    spinner's turn, with no new reading, its blank lines go; when Clank now is one line again, they come back."""
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = FOLDER
    async with app.run_test(size=(130, 31)) as pilot:
        column = await column_shown(pilot, app)
        seen = app.seen()
        assert "" in drawn(app, "machine-meters")
        request = {"role": "agent", "phase": "answering", "tokens": 340, "per_second": 52.3}
        last = {"time": "2026-10-11T13:50:02.000000Z", "tokens": 812, "per_second": 57.1, "status": 200, "error": ""}
        column.draw(replace(seen, activity={"state": "running", "requests": [request], "last": last}), machine=False)
        assert len(drawn(app, "machine-now")) == 2
        meters = drawn(app, "machine-meters")
        assert "" not in meters, "the blank lines go at once, not at the next reading"
        assert len(meters) == 18, "every meter still shown"
        column.draw(replace(seen, activity=None), machine=False)
        assert drawn(app, "machine-now") == ["idle"]
        assert len(drawn(app, "machine-meters")) == 22, "the blank lines back"


@pytest.mark.anyio
async def test_a_machine_column_too_short_for_every_meter_hides_the_last_ones_whole_and_says_how_many(
    client: Client, home: Home
) -> None:
    """At 20 rows the Machine panel has 11 inside: the CPU's 4 lines and the memory's 3, but not the GPU's 6."""
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    app.folder = FOLDER
    async with app.run_test(size=(130, 20)) as pilot:
        column = app.query_one("#machine", MachineColumn)
        await settle(pilot, lambda: column.display and "RAM" in render_text(app))
        await steady_frame(pilot, app)
        meters = drawn(app, "machine-meters")
        assert meters[0].startswith("CPU ")
        assert meters[-3].startswith("RAM ")
        assert not any(line.startswith(("GPU", "Disk", "Net")) for line in meters), "no meter cut halfway"
        machine = app.query_one("#machine-meters-panel", Panel)
        assert machine.note == "3 meters hidden"
        assert "─ 3 meters hidden ─┐" in render_text(app)
        assert app.query_one("#machine-now-panel", Panel).region.bottom <= column.region.bottom


@pytest.mark.anyio
async def test_the_menu_shows_each_pages_badge_the_questions_waiting_and_dockers_state(
    client: Client, home: Home, kernel: Kernel
) -> None:
    kernel.questions.ask(
        QuestionDraft(
            type="approval",
            title="Go on?",
            detail="",
            options=[Option(id="yes", label="Yes", key="y"), Option(id="no", label="No", key="n")],
            default="no",
        ),
        asked_by=CLANK,
    )
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=home)
    async with app.run_test(size=(120, 40)) as pilot:

        def label(id: str) -> str:
            return str(app.query_one(f"#menu-{id} Label", Label).render())

        await settle(pilot, lambda: label("questions").endswith("● 1"))
        await settle(pilot, lambda: label("docker").endswith("●"))
        assert label("records") == "7 Records", "a page with nothing to say has no badge"
