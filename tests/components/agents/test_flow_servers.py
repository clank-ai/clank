"""Design 0013 §4, §5 and §7 (decision 0062): what the flows' runner needs of a workspace's agents. A session at work in
the workspace that is no session of a flow's box, nor a subagent of one, is the owner's own, which a switch of the main
slot waits for. The flow's own OpenCode server, without a terminal, can be ended (to start it again with a box's
limits), and a window never is. A box's MCP servers are connected on the flow's server alone, those it does not name
disconnected there, Clank's own always kept (it carries the flow's tools), the window's left as they are, a box naming
none (or an empty list) getting every one the workspace's agent gets; a server the workspace's agent does not get is
refused, saying why, while one the bridge fails to connect or disconnect is said and the others still change. Run
against the fake bridge (`tests/fakes/bridge.py`), with no container and no OpenCode."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from clank import registry
from clank.components.agents.service import AgentError, Agents, SessionError
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import names
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.bridge import FakeBridge
from tests.fakes.platform import FakePlatform, container

OWNER = Actor(kind="user", via="console")
CONFIG = "/home/agent/.config/opencode/opencode.json"


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def bridge(kernel: Kernel, tmp_path: Path) -> FakeBridge:
    folder = tmp_path / "paper"
    folder.mkdir()
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=OWNER)
    platform: FakePlatform = kernel.parts["workspaces"].platform
    name = names(kernel.home.id).container("paper")
    platform.containers.append(container(name))
    made = FakeBridge("paper", folder, hear=kernel.parts["agents"].review.heard)
    made.configuration = lambda: platform.files.get((name, CONFIG))
    platform.inside = made.inside
    kernel.parts["workspaces"].docker(refresh=True)
    return made


def agents(kernel: Kernel) -> Agents:
    found: Agents = kernel.parts["agents"]
    return found


def at_work(bridge: FakeBridge, port: int, session: str, parent: str | None = None) -> None:
    """A session on the server on `port` works, as the watch says it."""
    bridge.servers[port].sessions[session] = {"title": session, "status": "busy"}
    if parent is not None:
        bridge.say({"type": "session", "port": port, "session": {"id": session, "parent": parent}})
    bridge.say({"type": "status", "port": port, "session": session, "status": "busy"})


def test_a_session_at_work_that_is_no_boxs_is_the_owners_and_its_subagents_too(
    kernel: Kernel, bridge: FakeBridge
) -> None:
    sessions = agents(kernel).sessions
    window = bridge.window()
    served = sessions.serve("paper", {})
    at_work(bridge, window, "ses_mine")
    at_work(bridge, window, "ses_mine_helper", parent="ses_mine")
    at_work(bridge, served, "ses_box")
    at_work(bridge, served, "ses_box_helper", parent="ses_box")
    at_work(bridge, served, "ses_box_helpers_helper", parent="ses_box_helper")
    bridge.servers[window].sessions["ses_resting"] = {"title": "resting", "status": "idle"}
    bridge.say({"type": "status", "port": window, "session": "ses_resting", "status": "idle"})

    found = sessions.working("paper", besides={"ses_box"})
    assert sorted(each["session"] for each in found) == ["ses_mine", "ses_mine_helper"]
    assert {each["port"] for each in found} == {window}

    bridge.status("ses_mine", "idle")
    bridge.status("ses_mine_helper", "idle")
    assert sessions.working("paper", besides={"ses_box"}) == []
    assert [each["session"] for each in sessions.working("paper")][:1] == ["ses_box"], "a box's, when not set apart"
    bridge.gone(served)
    assert sessions.working("paper") == [], "a session whose server stopped works no more"


def test_a_server_without_a_terminal_is_ended_and_a_window_never(kernel: Kernel, bridge: FakeBridge) -> None:
    sessions = agents(kernel).sessions
    window = bridge.window()
    served = sessions.serve("paper", {})

    with pytest.raises(SessionError, match="runs an OpenCode window"):
        sessions.end_server("paper", window)
    assert window in bridge.servers, "a window is never ended this way"

    assert sessions.end_server("paper", served) == "ended"
    assert served not in bridge.servers
    assert sessions.end_server("paper", served) == "gone", "nothing runs there any more"
    assert [argv[:3] for argv in bridge.commanded if argv[0] == "pkill"] == [["pkill", "-TERM", "-f"]]


def test_a_boxs_mcp_servers_are_connected_on_its_server_alone_and_clanks_own_kept(
    kernel: Kernel, bridge: FakeBridge
) -> None:
    tools = kernel.parts["tools"]
    tools.add("notes", {"command": "notes-mcp", "args": []}, scope="user", folder="", actor=OWNER)
    tools.add("sim", {"command": "sim-mcp", "args": []}, scope="user", folder="", actor=OWNER)
    window = bridge.window()
    bridge.servers[window].mcp = dict.fromkeys(("clank", "notes", "sim"), "connected")
    served = agents(kernel).sessions.serve("paper", agents(kernel).configure("paper"))
    assert bridge.servers[served].mcp == dict.fromkeys(("clank", "notes", "sim"), "connected"), "as configured"

    only = agents(kernel).box_tools("paper", served, ["sim"])
    assert only == {"connected": ["clank", "sim"], "started": [], "stopped": ["notes"], "failed": {}, "kept": {}}
    assert bridge.servers[served].mcp == {"clank": "connected", "notes": "disabled", "sim": "connected"}
    assert bridge.servers[window].mcp == dict.fromkeys(("clank", "notes", "sim"), "connected"), "the window's as is"

    every = agents(kernel).box_tools("paper", served, None)
    assert every == {
        "connected": ["clank", "notes", "sim"], "started": ["notes"], "stopped": [], "failed": {}, "kept": {},
    }  # fmt: skip
    again = agents(kernel).box_tools("paper", served, None)
    assert (again["started"], again["stopped"]) == ([], []), "only what differs is changed"
    assert bridge.done("mcp-start") == [[str(served), "notes"]], "on the flow's server alone"


def test_a_box_that_names_its_mcp_servers_as_an_empty_list_gets_every_one_the_workspaces_agent_gets(
    kernel: Kernel, bridge: FakeBridge
) -> None:
    """Design 0013 §4: a box's tools left empty are those the workspace's agent gets, whether absent or an empty
    list."""
    tools = kernel.parts["tools"]
    tools.add("notes", {"command": "notes-mcp", "args": []}, scope="user", folder="", actor=OWNER)
    served = agents(kernel).sessions.serve("paper", agents(kernel).configure("paper"))
    agents(kernel).box_tools("paper", served, ["clank"])
    assert bridge.servers[served].mcp == {"clank": "connected", "notes": "disabled"}

    empty = agents(kernel).box_tools("paper", served, [])
    assert empty == {"connected": ["clank", "notes"], "started": ["notes"], "stopped": [], "failed": {}, "kept": {}}


def test_an_mcp_server_the_bridge_cannot_start_or_stop_is_said_and_the_others_still_change(
    kernel: Kernel, bridge: FakeBridge
) -> None:
    """One MCP server that fails to connect (or to disconnect) on the flow's server is said, in the bridge's words, and
    left out of what is connected (or kept in it); the box is not failed for it, and the others still change."""
    tools = kernel.parts["tools"]
    for name in ("notes", "sim"):
        tools.add(name, {"command": f"{name}-mcp", "args": []}, scope="user", folder="", actor=OWNER)
    served = agents(kernel).sessions.serve("paper", agents(kernel).configure("paper"))

    bridge.refuse["mcp-stop"] = "notes did not disconnect: OpenCode answered 500"
    held = agents(kernel).box_tools("paper", served, ["sim"])
    assert held == {
        "connected": ["clank", "notes", "sim"], "started": [], "stopped": [], "failed": {},
        "kept": {"notes": "notes did not disconnect: OpenCode answered 500"},
    }  # fmt: skip
    bridge.refuse.clear()
    assert agents(kernel).box_tools("paper", served, ["sim"])["stopped"] == ["notes"]

    bridge.refuse["mcp-start"] = "notes did not connect within 90 seconds"
    failed = agents(kernel).box_tools("paper", served, None)
    assert failed == {
        "connected": ["clank", "sim"], "started": [], "stopped": [], "kept": {},
        "failed": {"notes": "notes did not connect within 90 seconds"},
    }  # fmt: skip


def test_an_mcp_server_the_workspaces_agent_does_not_get_is_refused_saying_why(
    kernel: Kernel, bridge: FakeBridge
) -> None:
    tools = kernel.parts["tools"]
    tools.add("notes", {"command": "notes-mcp", "args": []}, scope="user", folder="", actor=OWNER)
    agents(kernel).allow("paper", "notes", False, actor=OWNER)
    served = agents(kernel).sessions.serve("paper", agents(kernel).configure("paper"))
    config = json.loads(bridge.servers[served].config or "{}")
    assert sorted(config.get("mcp", {})) == ["clank"], "held back: not in its configuration"

    with pytest.raises(AgentError, match="notes, which paper's agent does not get: held back from this workspace"):
        agents(kernel).box_tools("paper", served, ["notes"])
    with pytest.raises(AgentError, match="nowhere, which paper's agent does not get: it is no MCP server"):
        agents(kernel).box_tools("paper", served, ["nowhere"])
    assert (bridge.done("mcp-start"), bridge.done("mcp-stop")) == ([], []), "nothing changed"
