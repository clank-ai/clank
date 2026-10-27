"""Design 0004 §3, §10 (the Workspaces page, 2026-10-15): F6 lists every workspace with its container's state, its
software and its folder; the highlighted one shows its container and limits, its use now (from the meters), its
software and the MCP servers its agent gets; `x` stops its container. Design 0011 §4 and §8 (board E15): how many
workspaces there are and run is the note in the top border of the list's panel, drawn again when it changes, and the
highlighted workspace's name the note of its; "No workspace yet" shows in the list's panel only while there is none.
Design 0004 §3 (revised 2026-10-26): a workspace whose running container is cut off from the model (the edge not
running on its network) says `cut off` in place of its state, in the failed color, and the highlighted one says what is
wrong and what Clank does about it, in the service's words."""

import re
from datetime import UTC, datetime
from pathlib import Path

import pytest
from textual.widgets import Label

from clank.client import Client
from clank.components.workspaces.console.workspaces import shown_state, workspace_detail, workspace_line
from clank.components.workspaces.sandbox import names
from clank.console.app import ClankConsole
from clank.console.snapshot import render_text
from clank.console.text import painted, tone
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from tests.console.frames import settle, steady_frame
from tests.fakes.platform import FakePlatform, container

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 15, 2, 0, tzinfo=UTC)
YOU = Actor(kind="user", via="console")


def text(app: ClankConsole) -> str:
    return "\n".join(str(label.content) for label in app.query("#page-workspaces Label").results(Label))


async def test_f6_lists_the_workspaces_and_shows_the_highlighted_one_whole(
    kernel: Kernel, client: Client, platform: FakePlatform, tmp_path: Path
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    (folder / "requirements.txt").write_text("numpy\n", encoding="utf-8")
    kernel.settings.write("workspace", "paper", {"path": str(folder), "cpus": 8}, base=None, actor=YOU)
    found = names(kernel.home.id)
    name = found.container("paper")
    platform.containers.append(container(name, labels={"clank.home": kernel.home.id}))
    edge = {"clank.home": kernel.home.id, "clank.ports": "18210,18211"}  # as an opening leaves it: on paper's network
    platform.containers.append(container(found.edge, labels=edge, networks=[found.outer, found.inner("paper")]))
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=kernel.home, page="workspaces")
    async with app.run_test(size=(200, 50)) as pilot:
        line = f"paper              running      software not installed {folder}"
        await settle(pilot, lambda: line in text(app) and "MCP servers its agent gets" in text(app), seconds=20)
        shown, frame = text(app), render_text(app)
        assert "─ 1 workspace, 1 running ─┐" in frame, "the list's note, in its panel's top border"
        assert "─ paper ─┐" in frame, "the highlighted workspace's name"
        assert not app.query_one("#workspaces-none", Label).display
        assert f"container {name}: running · limits 8 CPUs, a quarter of Docker's memory" in shown
        assert "software: not installed (e installs it with python3 -m venv" in shown
        await pilot.press("x")
        await settle(pilot, lambda: "exited" in text(app), seconds=20)
        await settle(pilot, lambda: "paper is stopped" in str(app.query_one("#message", Label).content), seconds=20)
        await settle(pilot, lambda: "─ 1 workspace, 0 running ─┐" in render_text(app))
    assert f"stop {name}" in platform.calls


async def test_with_no_workspace_the_lists_panel_says_so_and_has_no_note(kernel: Kernel, client: Client) -> None:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=kernel.home, page="workspaces")
    async with app.run_test(size=(200, 50)) as pilot:
        # The label shows on the first read; the frame is taken once the screen has caught up with it.
        await settle(pilot, lambda: app.query_one("#workspaces-none", Label).display, seconds=20)
        await settle(pilot, lambda: "No workspace yet" in render_text(app))
        frame = await steady_frame(pilot, app)
    assert "No workspace yet: clank in a folder (F4, o)." in frame
    assert re.search(r"┌─ Workspaces ─+┐", frame), "no note"


def test_a_workspaces_detail_says_its_use_and_which_servers_its_agent_gets() -> None:
    row = {"name": "paper", "path": "/w/paper", "container": "clank-x-paper", "state": "running", "cpus": None,
           "memory_mib": 4096, "setup": {"command": "make", "installed": True}}  # fmt: skip
    usage = {"name": "paper", "cpu": 49.6, "memory_used": 3 << 30, "memory_total": 12 << 30}
    servers = [{"name": "myproject", "given": True, "why": ""}, {"name": "web", "given": False, "why": "reached by"}]
    lines = workspace_detail(row, usage, servers)
    assert lines[1] == "container clank-x-paper: running · limits half of Docker's CPUs, 4,096 MiB"
    assert lines[2] == "using now: 50% of the machine's CPU, 3.0 GB of 12.0 GB memory"
    assert lines[3] == "software: installed with make"
    assert lines[4:] == ["MCP servers its agent gets: myproject", "not given: web (reached by)"]
    assert workspace_line({**row, "setup": {"command": None}}).split()[2:5] == ["nothing", "to", "install"]


def test_a_workspace_cut_off_from_the_model_says_so_in_its_line_and_its_detail() -> None:
    said = (
        "cut off from the model: the edge is not on its network; Clank joins it back within 5 seconds (opening the "
        "workspace or starting its agent does it now)"
    )
    row = {"name": "paper", "path": "/w/paper", "container": "clank-x-paper", "state": "running", "cpus": 2,
           "memory_mib": 4096, "setup": {"command": None}, "edge": "cut", "edge_said": said}  # fmt: skip
    line = workspace_line(row)
    assert line.split()[1:3] == ["cut", "off"]
    assert tone(shown_state(row)) == "$clank-failed"
    content = painted(line, shown_state(row))
    assert [content.plain[span.start : span.end] for span in content.spans] == ["cut off"]
    assert workspace_detail(row, None, [])[2] == said
    reached = {**row, "edge": "on", "edge_said": ""}
    assert workspace_line(reached).split()[1] == "running"
    assert said not in workspace_detail(reached, None, [])
