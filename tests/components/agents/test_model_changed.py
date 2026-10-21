"""Design 0013 §7 (decision 0062): after a flow's box switched the main slot, the owner's window in the workspace is
told its model changed: in the event `agents.model_changed` (which VS Code shows), and in a notice the review's view
carries for This folder, until OpenCode is next started there. A preset whose context is smaller than what one of the
owner's own sessions holds is named as too small for it; a box's session is not the owner's. The window itself is left
as it is: its configuration changes only when it next starts. Run against the fake bridge, with no container and no
OpenCode."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.client import Client
from clank.components.agents.service import Agents
from clank.components.gateway.service import Gateway
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import names
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from tests.fakes.bridge import FakeBridge
from tests.fakes.platform import FakePlatform, container

OWNER = Actor(kind="user", via="console")
RUNNER = Actor(kind="clank", via="flow runner")
CONFIG = "/home/agent/.config/opencode/opencode.json"
BY = "The flow Study, for its box T1,"
FAST = {"status": "ready", "busy": False, "preset": "fast-4k", "title": "fast 4K", "context": 4096, "output": 1024,
        "images": False}  # fmt: skip


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    routes = {"slots": {"main": FAST}, "roles": {"agent": "main"}, "default_slot": "main", "demand": {}}
    monkeypatch.setattr(Gateway, "routes", lambda self: routes)
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
    platform.inside = made.inside
    kernel.parts["workspaces"].docker(refresh=True)
    return made


def agents(kernel: Kernel) -> Agents:
    found: Agents = kernel.parts["agents"]
    return found


def session(bridge: FakeBridge, port: int, id: str, title: str) -> None:
    """A root session on the server on `port`, idle, as the watch says it."""
    bridge.servers[port].sessions[id] = {"title": title, "status": "idle"}
    bridge.say({"type": "session", "port": port, "session": {"id": id, "title": title}})
    bridge.say({"type": "status", "port": port, "session": id, "status": "idle"})


def holding(found: dict[str, int]) -> Any:
    """The context each session holds, as the Context window's totals say it (its last finished step)."""
    return lambda workspace, id: {"workspace": workspace, "session": id, "used": found.get(id)}


def test_the_owners_window_is_told_in_an_event_and_on_the_reviews_view(kernel: Kernel, bridge: FakeBridge) -> None:
    bridge.window()
    told = agents(kernel).model_changed("paper", by=BY, actor=RUNNER)
    said = (
        "The flow Study, for its box T1, switched the main slot to fast 4K (4,096 tokens of context, 1,024 out): "
        "your OpenCode window in paper talks to it from its next step, with the limits it started with until it next "
        "starts"
    )
    assert told["said"] == said
    assert (told["window"], told["too_small"]) == (True, [])
    [event] = kernel.events.after(0, types=["agents.model_changed"])
    assert (event.summary, event.actor, event.subject.id if event.subject else None) == (said, RUNNER, "paper")
    assert (event.data["title"], event.data["context"], event.data["window"]) == ("fast 4K", 4096, True)
    with TestClient(create_app(kernel, token="t", port=7728), base_url="http://127.0.0.1:7728") as http:
        client = Client("http://127.0.0.1:7728", "t", name="console", http=http)
        view = client.get("agents/review", workspace="paper")
    assert view["model_changed"]["said"] == said


def test_with_no_window_open_the_next_opencode_started_is_said_to_get_it(kernel: Kernel, bridge: FakeBridge) -> None:
    told = agents(kernel).model_changed("paper", by=BY, actor=RUNNER)
    assert told["said"].endswith("1,024 out): the next OpenCode started in paper gets it")
    assert told["window"] is False


def test_a_preset_with_a_smaller_context_than_the_owners_session_holds_is_named(
    kernel: Kernel, bridge: FakeBridge, monkeypatch: pytest.MonkeyPatch
) -> None:
    window = bridge.window()
    session(bridge, window, "ses_mine", "My analysis")
    session(bridge, window, "ses_small", "A short question")
    served = agents(kernel).sessions.serve("paper", {})
    session(bridge, served, "ses_box", "Study · plan · try 1")
    monkeypatch.setattr(agents(kernel), "context", holding({"ses_mine": 6000, "ses_small": 900, "ses_box": 9000}))

    told = agents(kernel).model_changed("paper", by=BY, besides={"ses_box"}, actor=RUNNER)
    assert told["too_small"] == [{"session": "ses_mine", "title": "My analysis", "holds": 6000}]
    assert told["said"].endswith(
        "until it next starts; fast 4K is too small for your session My analysis, which holds 6,000 tokens"
    )


def test_the_windows_configuration_changes_only_when_it_next_starts_which_ends_the_notice(
    kernel: Kernel, bridge: FakeBridge
) -> None:
    window = bridge.window()
    platform: FakePlatform = kernel.parts["workspaces"].platform
    before = dict(platform.files)
    agents(kernel).model_changed("paper", by=BY, actor=RUNNER)
    assert platform.files == before, "its configuration is not written while it runs"
    assert window in bridge.servers, "the window goes on"
    assert all(name == "servers" for name, _ in bridge.actions), "nothing is asked of it"
    assert agents(kernel).model_notice("paper") is not None

    agents(kernel).prepare("paper")  # OpenCode started again there: its configuration written with the new model
    config = platform.files[(names(kernel.home.id).container("paper"), CONFIG)]
    assert '"context": 3072' in config, "the new model's window, 4,096, less its margin (decision 0089)"
    assert agents(kernel).model_notice("paper") is None, "the window has the new model's limits now"
