"""Design 0004 §1 and §4, and design 0013 §15: the console's page for the folder clank was started in shows each step of
getting ready to work there, done or not, with the key that does it, and what to press next. `o` opens the folder's
workspace: the question its first image build asks shows on the page and is answered there, and the page then shows the
container running. `a` says what is not ready, or, once everything is, starts OpenCode in the folder's container (the
console steps aside; headless, the program runs at once) and says how it ended. `f` builds a flow with the model: it
opens a planning as the Flow view's `n` does and brings the console to the Monitor's Flow view, which shows it (decision
0100); the keys bar says `f`. The page's keys do nothing while a window is over it. A folder whose container would see
more than it is refused, saying why. A bare `clank` opens the console on this page.

Design 0016 §9, §10 and §15, decision 0112: with a cloud model loaded, `a` asks the workspace's question first, in a
window in the service's words (stronger for a workspace that existed before the cloud was agreed); `y` starts the
agent, `n` keeps it local and the page says how to allow it; the model's step says the cloud; once a provider is added,
the workspace's bound shows in the service's words, `u` changes it asked first, the MCP servers the service holds back
say so, and what its sessions cost today shows. Design 0011 §12.1: `u` is then a button of Then work's settings' row,
and a click on it does what the key does."""

import contextlib
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from textual.widgets import Label

from clank.cli import console as console_command
from clank.cli.main import main
from clank.client import Client
from clank.components.agents.console.folder import Step, checklist_rows, missing, next_line, readiness
from clank.components.agents.console.monitor import MonitorPage
from clank.components.gateway.service import Gateway
from clank.components.tools import service as tools_service
from clank.components.tools.mcp import Checked, Server, Tool
from clank.components.workspaces.sandbox import image_tag, names
from clank.console.app import ClankConsole
from clank.console.ask import AskScreen
from clank.console.buttons import Buttons
from clank.console.confirm import ConfirmScreen
from clank.console.data import ConsoleData
from clank.console.form import FormScreen
from clank.console.pick import PickScreen
from clank.console.rows import Rows
from clank.console.snapshot import render_text
from clank.kernel.core import Kernel
from clank.kernel.events import Actor
from tests.console.frames import settle
from tests.fakes.platform import FakePlatform, container
from tests.support.cloud import CloudBench
from tests.support.vscode import asked, fake_vscode

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 11, 11, 45, tzinfo=UTC)
YOU = Actor(kind="user", via="console")
CONFIG = "/home/agent/.config/opencode/opencode.json"
GATEWAY = {"state": "running", "port": 18210, "url": "http://127.0.0.1:18210/v1", "pid": 7, "since": None,
           "problem": "", "log": ""}  # fmt: skip


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    """The gateway runs (nothing starts a real one in a test)."""
    monkeypatch.setattr(Gateway, "status", lambda self: dict(GATEWAY))
    monkeypatch.setattr(Gateway, "ensure", lambda self: dict(GATEWAY))
    idle = {"state": "running", "port": 18210, "problem": "", "requests": [], "served": 0, "last": None}
    # never asks the gateway on 18210
    monkeypatch.setattr(Gateway, "activity", lambda self, session="", subagents=False, ended=False: dict(idle))


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A folder to work in, inside the test's own folder (which holds the test's CLANK_HOME, so it is refused)."""
    folder = tmp_path / "paper"
    folder.mkdir()
    (folder / "notes.md").write_text("mine\n", encoding="utf-8")
    return folder


def recorder(ran: list[list[str]]) -> Callable[[Sequence[str]], int]:
    """A terminal that keeps what it was asked to run, and says it ended well."""

    def run(argv: Sequence[str]) -> int:
        ran.append(list(argv))
        return 0

    return run


def text(app: ClankConsole) -> str:
    """Everything the page shows, its labels joined; a row (`console/rows.py`) as one line, its name padded to its
    column."""
    page = app.query_one("#page-folder")
    lines = [str(label.content) for label in page.query(Label).results(Label) if not label.has_class("name", "value")]
    for rows in page.query(Rows).results(Rows):
        for row in rows.query(".row"):
            labels = [str(label.content) for label in row.query(Label).results(Label)]
            if len(labels) == 2:  # a row being made has no labels yet
                lines.append(f"{labels[0]:<{rows.width}}{labels[1]}")
    for group in page.query(Buttons).results(Buttons):  # its keys, buttons (design 0011 §12.1), each line whole
        if group.display:
            lines += [line.plain.rstrip() for line in group.lines(1000)[0]]
    return "\n".join(lines)


def message(app: ClankConsole) -> str:
    return str(app.query_one("#message", Label).content)


def console(client: Client, kernel: Kernel, folder: Path, **kwargs: Any) -> ClankConsole:
    return ClankConsole(
        client, now=lambda: NOW, zone=UTC, home=kernel.home, page="folder", folder=str(folder), **kwargs
    )


async def test_a_new_folder_shows_what_is_not_ready_each_with_its_key(
    kernel: Kernel, client: Client, gateway: None, project: Path
) -> None:
    app = console(client, kernel, project)
    async with app.run_test(size=(220, 50)) as pilot:
        await settle(pilot, lambda: "not opened yet" in text(app) and "none is loaded" in text(app))
        shown = text(app)
    assert f"Folder: {project}" in shown
    assert " 1  Docker             ✓ running" in shown
    assert " 2  This folder        ✓ ready: it can be a workspace" in shown
    assert " 3  Its workspace      ✗ not opened yet   press o to open the workspace" in shown
    assert " 4  The sandbox image  ✗ not built yet: opening the workspace builds it (once)" in shown
    assert " 5  Its software       ✓ nothing to install (no pyproject.toml or requirements.txt)" in shown
    assert " 6  A model            ✗ none is loaded" in shown
    assert "press l to load a model" in shown
    assert " 7  The gateway        ✓ running on port 18210" in shown
    assert "Next:  o open the workspace  g get everything ready" in shown, "its keys, buttons (design 0011 §12.1)"
    assert " a OpenCode in this terminal; the menu comes back when you leave it" in shown
    assert (
        "OpenCode will use the model Clank runs: 24,576 tokens of context (the engine's 32,768 less 8,192 kept for a "
        "step's tool results), 8,192 out"
    ) in shown, "what OpenCode is told: the window less the margin, at most a quarter of it (decision 0089)"
    assert "MCP servers: open the workspace (o) to choose which its agent gets" in shown


async def test_r_switches_the_agents_changes_between_review_and_auto(
    kernel: Kernel, client: Client, platform: FakePlatform, gateway: None, project: Path
) -> None:
    """Design 0007 §7 and design 0009 §7: the workspace's mode shows beside the keys that start the agent; r switches
    it, and with no OpenCode window reachable the message says why the agent itself was not switched."""
    kernel.settings.write("workspace", "paper", {"path": str(project)}, base=None, actor=YOU)
    platform.containers.append(
        container(names(kernel.home.id).container("paper"), labels={"clank.home": kernel.home.id})
    )
    app = console(client, kernel, project)
    async with app.run_test(size=(220, 50)) as pilot:
        await settle(pilot, lambda: "review: the agent asks before it changes a file" in text(app))
        await pilot.press("r")
        await settle(pilot, lambda: "auto: the agent changes files without asking" in text(app))
        assert "paper's agent now builds, changing files without asking (the bridge" in message(app)
    assert kernel.settings.get("workspace", "paper").record.model_dump()["changes"] == "auto"
    [switched] = kernel.events.after(0, types=["agents.review_switched"])
    assert switched.actor == YOU


async def test_w_turns_one_opencode_window_at_a_time_off_and_on_again(
    kernel: Kernel, client: Client, platform: FakePlatform, gateway: None, project: Path
) -> None:
    """Design 0004 §5: one window is the workspace's way unless turned off; w turns it off and on, in its record."""
    kernel.settings.write("workspace", "paper", {"path": str(project)}, base=None, actor=YOU)
    platform.containers.append(
        container(names(kernel.home.id).container("paper"), labels={"clank.home": kernel.home.id})
    )
    app = console(client, kernel, project)
    async with app.run_test(size=(220, 50)) as pilot:
        await settle(pilot, lambda: "one OpenCode window: opening one closes the one open" in text(app))
        await pilot.press("w")
        await settle(pilot, lambda: "several OpenCode windows: opening one adds another" in text(app))
        assert kernel.settings.get("workspace", "paper").record.model_dump()["one_window"] is False
        await pilot.press("w")
        await settle(pilot, lambda: "one OpenCode window: opening one closes" in text(app))
    assert kernel.settings.get("workspace", "paper").record.model_dump()["one_window"] is True


async def test_this_folder_says_when_a_flows_box_changed_the_model_its_window_talks_to(
    kernel: Kernel, client: Client, platform: FakePlatform, gateway: None, project: Path
) -> None:
    """Design 0013 §7 (decision 0062): after a flow's box switched the main slot, the window is told on This folder,
    under the keys that start the agent, until OpenCode is next started there."""
    kernel.settings.write("workspace", "paper", {"path": str(project)}, base=None, actor=YOU)
    platform.containers.append(
        container(names(kernel.home.id).container("paper"), labels={"clank.home": kernel.home.id})
    )
    told = kernel.parts["agents"].model_changed(
        "paper", by="The flow Study, for its box T1,", actor=Actor(kind="clank", via="flow runner")
    )
    app = console(client, kernel, project)
    async with app.run_test(size=(220, 50)) as pilot:
        await settle(pilot, lambda: "model changed:" in text(app))
        shown = text(app)
    assert "model changed: The flow Study, for its box T1, switched the main slot to the model Clank runs" in shown
    assert told["said"].endswith("the next OpenCode started in paper gets it")


async def test_e_installs_the_folders_software_and_m_gives_the_agent_the_folders_mcp_server_checked_in_its_container(
    kernel: Kernel,
    client: Client,
    platform: FakePlatform,
    gateway: None,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Design 0004 §10."""
    (project / "pyproject.toml").write_text('[project]\nname = "paper"\nversion = "1"\n', encoding="utf-8")
    (project / ".mcp.json").write_text('{"mcpServers": {"myproject": {"command": "myproject-mcp"}}}', encoding="utf-8")
    kernel.settings.write("workspace", "paper", {"path": str(project)}, base=None, actor=YOU)
    name = names(kernel.home.id).container("paper")
    platform.containers.append(container(name, labels={"clank.home": kernel.home.id}))
    platform.images.add(image_tag())
    kernel.parts["runtime"].state.set_slot("main", "ready", "a test", actor=YOU, preset="daily-262k")
    tools = [Tool(f"tool{number}", "") for number in range(10)]
    checked: list[Server] = []

    def answers(server: Server, seconds: float) -> Checked:
        checked.append(server)
        return Checked("MyProject", "3.0", "2025-06-18", tools)

    monkeypatch.setattr(tools_service, "check", answers)
    app = console(client, kernel, project)
    async with app.run_test(size=(220, 50)) as pilot:
        await settle(pilot, lambda: "not installed: python3 -m venv" in text(app) and "Ready:" in text(app), seconds=20)
        shown = text(app)
        assert "press e to install the folder's software" in shown
        assert "Ready:  a start OpenCode here" in shown
        assert "e installs the folder's software first" in shown
        assert "✗ myproject" in shown
        assert "not allowed yet (m allows it)" in shown
        await pilot.press("e")
        await settle(pilot, lambda: isinstance(app.screen, FormScreen))
        await pilot.press("enter")
        await settle(pilot, lambda: "installed: python3 -m venv ~/.venv" in text(app), seconds=20)
        await settle(pilot, lambda: "Install a workspace's software: done" in message(app), seconds=20)
        assert "✓ clank" in text(app), "Clank's own server (send_to_phone) is given to every agent"
        await pilot.press("m")
        await settle(pilot, lambda: isinstance(app.screen, PickScreen))
        await pilot.press("down")  # Clank's own first, then the folder's
        await pilot.press("enter")
        await settle(pilot, lambda: "✓ myproject" in text(app) and "10 tools" in text(app), seconds=20)
    assert kernel.settings.get("workspace", "paper").record.model_dump()["set_up"].endswith("pip install -e .")
    [server] = checked
    assert server.command == "docker"
    assert server.args[-2:] == [name, "myproject-mcp"]
    assert "--tty" not in server.args


async def test_o_opens_the_workspace_after_its_image_question_is_answered_on_the_page(
    kernel: Kernel, client: Client, platform: FakePlatform, gateway: None, project: Path
) -> None:
    app = console(client, kernel, project)
    async with app.run_test(size=(220, 50)) as pilot:
        await settle(pilot, lambda: "not opened yet" in text(app))
        await pilot.press("o")
        await settle(pilot, lambda: "Build Clank's sandbox image?" in text(app), seconds=20)
        await settle(pilot, lambda: "it waits for your answer below" in text(app))
        await pilot.press("y")
        await settle(pilot, lambda: "running: paper, its container up" in text(app), seconds=30)
        await settle(pilot, lambda: "Open a workspace: done" in message(app))
    assert any(call.startswith("build clank-sandbox:") for call in platform.calls)
    assert f"run {names(kernel.home.id).container('paper')}" in platform.calls
    assert kernel.settings.get("workspace", "paper").record.model_dump()["path"] == str(project)
    assert sorted(path.name for path in project.iterdir()) == ["notes.md"], "nothing is written in the folder"


async def test_o_builds_a_newer_image_while_the_workspace_runs_on_the_one_it_has(
    kernel: Kernel, client: Client, platform: FakePlatform, gateway: None, project: Path
) -> None:
    kernel.settings.write("workspace", "paper", {"path": str(project)}, base=None, actor=YOU)
    name = names(kernel.home.id).container("paper")
    platform.containers.append(container(name, labels={"clank.home": kernel.home.id}))  # made from an older image
    app = console(client, kernel, project)
    async with app.run_test(size=(220, 50)) as pilot:
        await settle(pilot, lambda: "a newer one: o builds it (the workspace keeps running)" in text(app), seconds=20)
        await pilot.press("o")
        await settle(pilot, lambda: "Build Clank's sandbox image?" in text(app), seconds=20)
        await pilot.press("y")
        await settle(pilot, lambda: "built; the workspace moves to it when next opened" in text(app), seconds=30)
    assert any(call.startswith("build clank-sandbox:") for call in platform.calls)
    assert f"run {name}" not in platform.calls, "the running workspace was left as it was"


async def test_a_says_what_is_not_ready_and_starts_nothing(
    kernel: Kernel, client: Client, gateway: None, project: Path
) -> None:
    ran: list[list[str]] = []
    app = console(client, kernel, project, terminal=recorder(ran))
    async with app.run_test(size=(220, 50)) as pilot:
        await settle(pilot, lambda: "not opened yet" in text(app) and "none is loaded" in text(app))
        await pilot.press("a")
        await settle(pilot, lambda: "Not ready yet:" in message(app))
        assert "its workspace (o) · a model (l)" in message(app)
    assert ran == []


async def test_a_starts_opencode_in_the_folders_container_and_the_console_comes_back(
    kernel: Kernel,
    client: Client,
    platform: FakePlatform,
    gateway: None,
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel.settings.write("workspace", "paper", {"path": str(project)}, base=None, actor=YOU)
    name = names(kernel.home.id).container("paper")
    platform.containers.append(container(name, labels={"clank.home": kernel.home.id}))
    kernel.parts["runtime"].state.set_slot("main", "ready", "a test", actor=YOU, preset="daily-262k")
    stepped_aside: list[bool] = []

    def stepped(self: ClankConsole) -> contextlib.AbstractContextManager[None]:
        stepped_aside.append(True)
        return contextlib.nullcontext()

    monkeypatch.setattr(ClankConsole, "suspend", stepped)
    ran: list[list[str]] = []
    app = console(client, kernel, project, terminal=recorder(ran))
    async with app.run_test(size=(220, 50)) as pilot:
        await settle(pilot, lambda: "Ready:  a start OpenCode here" in text(app), seconds=20)
        await pilot.press("a")
        await settle(pilot, lambda: "OpenCode ended" in message(app), seconds=20)
        assert app.is_running
    [argv] = ran
    assert argv[-3:] == ["/workspace", name, "opencode"]
    assert "OPENCODE_DISABLE_MODELS_FETCH=1" in argv
    assert (name, CONFIG) in platform.files, "its configuration is written before it starts"
    assert stepped_aside == [], "headless, the program runs without the console stepping aside"


async def test_c_opens_the_folder_in_clanks_vs_code_window_with_opencode_beside_the_files(
    kernel: Kernel,
    client: Client,
    platform: FakePlatform,
    gateway: None,
    project: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    kernel.settings.write("workspace", "paper", {"path": str(project)}, base=None, actor=YOU)
    name = names(kernel.home.id).container("paper")
    platform.containers.append(container(name, labels={"clank.home": kernel.home.id}))
    kernel.parts["runtime"].state.set_slot("main", "ready", "a test", actor=YOU, preset="daily-262k")
    state = fake_vscode(kernel, tmp_path, monkeypatch)
    app = console(client, kernel, project)
    async with app.run_test(size=(220, 50)) as pilot:
        await settle(pilot, lambda: "Ready:  a start OpenCode here" in text(app), seconds=20)
        assert " c VS Code on this folder, OpenCode beside your files" in text(app)
        await pilot.press("c")
        await settle(pilot, lambda: "VS Code opens this folder" in message(app), seconds=30)
    assert asked(state)["opened"] == [str(project)]


async def test_f_opens_a_planning_and_brings_the_console_to_the_monitors_flow_view(
    kernel: Kernel, client: Client, gateway: None, project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in ("SSH_CLIENT", "SSH_TTY", "TERM_PROGRAM", "WT_SESSION"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SSH_CONNECTION", "10.0.0.2 51022 10.0.0.9 22")  # nothing opens on the PC's own screen
    kernel.settings.write("workspace", "paper", {"path": str(project)}, base=None, actor=YOU)

    def never(argv: Sequence[str]) -> int:
        raise AssertionError(f"the console handed its terminal to {list(argv)[:3]}")

    app = console(client, kernel, project, terminal=never)
    async with app.run_test(size=(120, 50)) as pilot:
        await settle(pilot, lambda: "Get ready to work here" in render_text(app))
        keys = render_text(app).splitlines()[-1]
        await pilot.press("f")
        monitor = app.query_one("#page-monitor", MonitorPage)
        await settle(pilot, lambda: monitor.display and monitor.view == "flow")
        await settle(pilot, lambda: "clank flow attach" in message(app))
        await settle(pilot, lambda: "building with the model" in str(app.query_one("#monitor-heading", Label).content))
    planning = kernel.parts["flows"].building.planning("paper/flow")
    assert planning is not None
    assert planning.where == "attach"
    assert "f build a flow" in keys


async def test_the_pages_keys_do_nothing_while_a_window_is_over_it(
    kernel: Kernel, client: Client, gateway: None, project: Path
) -> None:
    kernel.settings.write("workspace", "paper", {"path": str(project)}, base=None, actor=YOU)

    def never(argv: Sequence[str]) -> int:
        raise AssertionError(f"the console handed its terminal to {list(argv)[:3]}")

    app = console(client, kernel, project, terminal=never)
    async with app.run_test(size=(120, 50)) as pilot:
        await settle(pilot, lambda: "Get ready to work here" in render_text(app))
        app.push_screen(ConfirmScreen("A window over the page", ["Nothing under it acts."]))
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("f", "g", "s", "a")
        await pilot.pause(0.3)
        assert isinstance(app.screen, ConfirmScreen)
        assert not app.query_one("#page-monitor", MonitorPage).display, "f did not go to the Flow view"
    assert kernel.parts["flows"].building.plannings.all() == [], "no planning started"
    assert kernel.operations.find(None, 10) == [], "no step started"


async def test_a_folder_whose_container_would_see_more_than_it_is_refused_saying_why(
    kernel: Kernel, client: Client, gateway: None, tmp_path: Path
) -> None:
    app = console(client, kernel, tmp_path)
    async with app.run_test(size=(220, 50)) as pilot:
        await settle(pilot, lambda: "refused:" in text(app))
        assert "holds Clank's own folder" in text(app)
        await pilot.press("o")
        await settle(pilot, lambda: "holds Clank's own folder" in message(app))
    assert [loaded.id for loaded in kernel.settings.records("workspace")] == []


def test_readiness_names_each_missing_item_with_its_key() -> None:
    data = ConsoleData(connected=True, docker={"state": "stopped"}, slots=[])
    found = missing(data, None, None)
    assert found == [
        ("docker", "s"), ("this folder", ""), ("its workspace", "o"), ("its software", "e"), ("a model", "l"),
        ("the gateway", "g"),
    ]  # fmt: skip
    assert readiness(found).startswith("Not ready yet: docker (s) · this folder · its workspace (o) · a model (l)")
    assert next_line([("its software", "e")]).plain == (
        "Ready: press a to start OpenCode here, or c to open VS Code with OpenCode beside your files"
        " · e installs the folder's software first."
    )
    assert next_line(found).plain == "Next: press s to start Docker · or g to do every step that is not done."
    assert next_line([]).plain == (
        "Ready: press a to start OpenCode here, or c to open VS Code with OpenCode beside your files."
    )
    assert readiness([]) == "Ready: a starts OpenCode here; leaving it brings you back to this page."
    assert missing(ConsoleData(connected=False), None, None) == [("the Clank service", "")]


def test_clank_alone_opens_the_console_on_this_folders_page(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    monkeypatch.chdir(folder)

    class Closed:
        def close(self) -> None:
            return

    monkeypatch.setattr(console_command, "connect", lambda home, start: Closed())
    opened: list[tuple[str, str]] = []
    monkeypatch.setattr(ClankConsole, "run", lambda self, *args, **kwargs: opened.append((self._page, self.folder)))
    result = CliRunner().invoke(main, [])
    assert result.exit_code == 0, result.output
    assert opened == [("folder", str(folder.resolve()))]


def test_the_step_being_worked_on_turns_a_spinner_in_place_of_its_mark() -> None:
    steps: list[Step] = [("Docker", "running", True, "s"), ("Its workspace", "stopped: not opened yet", False, "o")]
    assert [(name, value.plain) for name, value in checklist_rows(steps, "Its workspace", 1)] == [
        (" 1  Docker", "✓ running"),
        (" 2  Its workspace", "⣽ working on it…"),
    ]


def window(app: ClankConsole) -> str:
    """What the window over the page says, its lines joined."""
    return " ".join(" ".join(str(label.content).split()) for label in app.screen.query(Label).results(Label))


def cloud_ready(kernel: Kernel, platform: FakePlatform, project: Path, cloud: CloudBench, older: bool = False) -> str:
    """A workspace whose container runs (made before the provider was agreed, when `older`), and a cloud model in the
    main slot."""
    if not older:
        cloud.add()
        kernel.clock.advance(60)  # type: ignore[attr-defined]
    kernel.settings.write("workspace", "paper", {"path": str(project)}, base=None, actor=YOU)
    name = names(kernel.home.id).container("paper")
    platform.containers.append(container(name, labels={"clank.home": kernel.home.id}))
    if older:
        kernel.clock.advance(60)  # type: ignore[attr-defined]
        cloud.add()
    cloud.write_preset()
    cloud.run("cloud-example-coder")
    return name


async def test_with_a_cloud_model_a_asks_the_workspace_first_and_y_starts_the_agent(
    kernel: Kernel, client: Client, platform: FakePlatform, gateway: None, project: Path, cloud_api: CloudBench
) -> None:
    name = cloud_ready(kernel, platform, project, cloud_api)
    ran: list[list[str]] = []
    app = console(client, kernel, project, terminal=recorder(ran))
    async with app.run_test(size=(160, 50)) as pilot:
        await settle(pilot, lambda: "Ready:  a start OpenCode here" in text(app), seconds=20)
        assert "cloud, at OpenRouter" in text(app)
        assert "not asked yet: paper is asked once before its agent uses the cloud model (u allows it)" in text(app)
        await pilot.press("a")
        await settle(pilot, lambda: isinstance(app.screen, AskScreen))
        assert "Let paper's agent use the cloud model cloud: Example Coder?" in window(app)
        assert "What never goes: Notion pages" in window(app)
        await pilot.press("y")
        await settle(pilot, lambda: "OpenCode ended" in message(app), seconds=20)
    assert cloud_api.bound("paper")["models"] == "cloud"
    [argv] = ran
    assert argv[-3:] == ["/workspace", name, "opencode"]


async def test_n_keeps_the_workspace_local_and_says_how_to_allow_it(
    kernel: Kernel, client: Client, platform: FakePlatform, gateway: None, project: Path, cloud_api: CloudBench
) -> None:
    cloud_ready(kernel, platform, project, cloud_api)
    ran: list[list[str]] = []
    app = console(client, kernel, project, terminal=recorder(ran))
    async with app.run_test(size=(160, 50)) as pilot:
        await settle(pilot, lambda: "Ready:  a start OpenCode here" in text(app), seconds=20)
        await pilot.press("a")
        await settle(pilot, lambda: isinstance(app.screen, AskScreen))
        await pilot.press("n")
        await settle(pilot, lambda: "u allows the cloud for it" in message(app))
        await settle(pilot, lambda: "kept on this machine: paper never uses the cloud model (u allows it)" in text(app))
        await pilot.press("a")
        await settle(pilot, lambda: "the agent was not started" in message(app))
    assert ran == []
    assert cloud_api.bound("paper")["cloud_answered"]


async def test_with_a_provider_added_u_is_a_button_of_then_works_settings_that_asks_first(
    kernel: Kernel, client: Client, platform: FakePlatform, gateway: None, project: Path, cloud_api: CloudBench
) -> None:
    cloud_ready(kernel, platform, project, cloud_api)
    app = console(client, kernel, project)
    async with app.run_test(size=(160, 60)) as pilot:  # the page whole, so no scrollbar comes as the row grows
        await settle(pilot, lambda: bool(app.query("#page-folder")))
        await settle(pilot, lambda: "(u allows it)" in text(app), seconds=20)
        settings = app.query_one("#folder-settings", Buttons)
        await settle(pilot, lambda: [each.key.key for each in settings.buttons] == ["m", "p", "r", "w", "i", "u"])
        assert settings.buttons[-1].said == "cloud or local"
        await settle(pilot, lambda: settings.size.height == len(settings.lines(settings.size.width)[0]))
        _, line, start, _ = settings.lines(settings.size.width)[1][-1]
        await pilot.click("#folder-settings", offset=(start + 1, line))
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        asked = app.screen
        assert isinstance(asked, ConfirmScreen)
        assert asked.heading == "Let paper use the cloud model?"


async def test_a_workspace_that_existed_before_the_agreement_is_asked_in_stronger_words(
    kernel: Kernel, client: Client, platform: FakePlatform, gateway: None, project: Path, cloud_api: CloudBench
) -> None:
    cloud_ready(kernel, platform, project, cloud_api, older=True)
    app = console(client, kernel, project, terminal=recorder([]))
    async with app.run_test(size=(160, 50)) as pilot:
        await settle(pilot, lambda: "Ready:  a start OpenCode here" in text(app), seconds=20)
        await pilot.press("a")
        await settle(pilot, lambda: isinstance(app.screen, AskScreen))
        assert (
            "existed before the cloud provider was agreed: its earlier sessions and its folder may hold research"
            in (window(app))
        )


async def test_u_changes_the_bound_asked_first_and_the_held_back_servers_and_the_cost_show(
    kernel: Kernel, client: Client, platform: FakePlatform, gateway: None, project: Path, cloud_api: CloudBench
) -> None:
    cloud_ready(kernel, platform, project, cloud_api)
    kernel.parts["tools"].add("lit", {"command": "lit-mcp"}, scope="user", folder="", actor=YOU)
    cloud_api.mark("lit", True)
    cloud_api.spend(0.84, requests=142, session="ses_1", workspace="paper")
    app = console(client, kernel, project, terminal=recorder([]))
    async with app.run_test(size=(160, 50)) as pilot:
        await settle(pilot, lambda: "not asked yet" in text(app), seconds=20)
        await pilot.press("u")
        await settle(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        assert "Let paper use the cloud model?" in render_text(app)
        await pilot.press("enter")
        await settle(
            pilot, lambda: "may use the cloud model: paper's requests may go to OpenRouter (u keeps" in text(app)
        )
        await settle(pilot, lambda: "held back: local only" in text(app))
        assert "its sessions: $0.84 today (Requests, F7, shows each)" in text(app)
    assert ("POST", "workspaces/paper/cloud", {"allow": True}) in cloud_api.calls
