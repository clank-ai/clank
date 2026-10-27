"""Design 0004 §5 (revised 2026-10-26): whether a workspace's agent reaches its model now. `GET /agents/reach` follows
the way OpenCode's requests take and says the first thing wrong, in words, with what fixes it: a folder with no
workspace, or whose container does not run (open it); the gateway that does not run (start it); from inside the
container, the gateway's host `edge` that does not resolve, or a gateway that does not answer through it (open the
workspace again); each of these stops OpenCode at once, so a client does not start it. The model in the main slot comes
last: loading is said, none running is said with loading the last that worked, and neither stops OpenCode from
starting. Every check is kept with its words, a check that cannot be run is said as unknown, and nothing is written."""

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.agents.reach import PROBE
from clank.components.agents.service import Agents
from clank.components.runtime.state import LastGood
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import names
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import Answer
from tests.fakes.platform import FakePlatform, container

YOU = Actor(kind="user", via="console")
PORT = 18210
RUNNING = {"state": "running", "port": PORT, "problem": ""}
NOT_RESOLVED = "[Errno -3] Temporary failure in name resolution"


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    monkeypatch.setattr(kernel.parts["gateway"], "status", lambda: dict(RUNNING))
    yield kernel
    kernel.close()


def opened(kernel: Kernel, platform: FakePlatform, folder: Path) -> str:
    """The folder's workspace `paper`, its container running; the container's name."""
    folder.mkdir(exist_ok=True)
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    name = names(kernel.home.id).container("paper")
    platform.containers.append(container(name, labels={"clank.home": kernel.home.id}))
    return name


def probing(
    said: dict[str, Any] | None, seen: list[list[str]] | None = None
) -> Callable[[list[str], bytes | None], Answer]:
    """The container as the probe finds it: what the probe prints (None: python3 is not there)."""

    def inside(argv: list[str], given: bytes | None) -> Answer:
        if seen is not None:
            seen.append(argv)
        if argv[:3] != ["python3", "-c", PROBE]:
            return Answer(1, "", f"the fake container does not run {argv[0]}")
        if said is None:
            return Answer(127, "", 'exec: "python3": executable file not found in $PATH')
        return Answer(0, json.dumps(said) + "\n", "")

    return inside


def ready(kernel: Kernel) -> None:
    kernel.parts["runtime"].state.set_slot("main", "ready", "a test", actor=YOU, preset="daily-262k")


def checks(found: dict[str, Any]) -> dict[str, bool | None]:
    return {check["name"]: check["ok"] for check in found["checks"]}


def test_a_workspace_whose_gateway_answers_through_the_edge_with_a_model_ready_reaches_it(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    opened(kernel, platform, tmp_path / "paper")
    seen: list[list[str]] = []
    platform.inside = probing({"step": "answered", "status": 200}, seen)
    ready(kernel)
    agents: Agents = kernel.parts["agents"]
    found = agents.reach(folder=str(tmp_path / "paper"))
    assert found["workspace"] == "paper"
    assert (found["ready"], found["blocked"], found["problem"], found["fix"]) == (True, False, "", None)
    assert checks(found) == {"workspace": True, "gateway": True, "edge": True, "model": True}
    assert seen == [["python3", "-c", PROBE, "edge", str(PORT)]], "one look from inside the container, at the edge"
    assert agents.reach(workspace="paper")["ready"] is True, "named by its workspace too"


def test_a_container_that_cannot_resolve_the_edge_is_blocked_with_opening_the_workspace_again(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    folder = tmp_path / "paper"
    opened(kernel, platform, folder)
    platform.inside = probing({"step": "resolve", "error": NOT_RESOLVED})
    ready(kernel)
    found = kernel.parts["agents"].reach(folder=str(folder))
    assert (found["ready"], found["blocked"]) == (False, True), "OpenCode would end at once: it is not started"
    assert "cannot find the gateway's host `edge`" in found["problem"]
    assert NOT_RESOLVED in found["problem"]
    assert found["fix"] == {
        "label": "Open the workspace again", "post": "workspaces/open", "body": {"folder": str(folder)},
    }  # fmt: skip
    assert checks(found) == {"workspace": True, "gateway": True, "edge": False, "model": True}


def test_a_gateway_that_does_not_answer_through_the_edge_is_blocked_too(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    opened(kernel, platform, tmp_path / "paper")
    platform.inside = probing({"step": "connect", "error": "Remote end closed connection without response"})
    ready(kernel)
    found = kernel.parts["agents"].reach(folder=str(tmp_path / "paper"))
    assert found["blocked"] is True
    assert "does not answer" in found["problem"]
    assert "Remote end closed" in found["problem"]
    assert found["fix"]["post"] == "workspaces/open"


def test_a_gateway_that_does_not_run_is_said_first_with_its_start_and_the_container_is_not_asked(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened(kernel, platform, tmp_path / "paper")
    seen: list[list[str]] = []
    platform.inside = probing({"step": "answered", "status": 200}, seen)
    gateway = kernel.parts["gateway"]
    monkeypatch.setattr(gateway, "status", lambda: {"state": "stopped", "port": PORT, "problem": "port 18210 is held"})
    found = kernel.parts["agents"].reach(folder=str(tmp_path / "paper"))
    assert found["blocked"] is True
    assert found["problem"] == "the gateway does not run: port 18210 is held"
    assert found["fix"] == {"label": "Start the gateway", "post": "gateway/restart", "body": {}}
    assert seen == [], "nothing to reach through the edge"
    assert "edge" not in checks(found)
    assert checks(found)["model"] is False, "the model is still looked at, after the first problem"


def test_a_folder_with_no_workspace_or_a_container_that_does_not_run_is_blocked_with_opening_it(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    agents: Agents = kernel.parts["agents"]
    none = agents.reach(folder=str(folder))
    assert (none["workspace"], none["blocked"]) == (None, True)
    assert "has no Clank workspace" in none["problem"]
    assert none["fix"] == {"label": "Open the workspace", "post": "workspaces/open", "body": {"folder": str(folder)}}
    kernel.settings.write("workspace", "paper", {"path": str(folder)}, base=None, actor=YOU)
    stopped = agents.reach(folder=str(folder))
    assert stopped["problem"] == "paper's container does not run"
    assert stopped["fix"]["post"] == "workspaces/open"
    assert stopped["blocked"] is True


def test_no_model_in_the_main_slot_is_said_with_loading_the_last_that_worked_and_does_not_block(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    opened(kernel, platform, tmp_path / "paper")
    platform.inside = probing({"step": "answered", "status": 200})
    state = kernel.parts["runtime"].state
    agents: Agents = kernel.parts["agents"]
    state.set_slot("main", "stopped", "unloaded", actor=YOU)
    found = agents.reach(folder=str(tmp_path / "paper"))
    assert (found["ready"], found["blocked"]) == (False, False), "OpenCode starts; its first message would fail"
    assert found["problem"].startswith("no model runs in the main slot (unloaded)")
    assert found["fix"] is None, "no configuration has worked yet: the words say how to load one"
    state.remember_good("main", LastGood(preset="daily-262k", options={}, time=kernel.clock.now()))
    state.set_slot("main", "failed", "it crashed", actor=YOU)
    again = agents.reach(folder=str(tmp_path / "paper"))
    assert again["problem"] == "no model runs in the main slot (it crashed)"
    assert again["fix"] == {
        "label": f"Load {kernel.parts['runtime'].title('daily-262k')}", "post": "runtime/slots/main/load",
        "body": {"preset": "daily-262k"},
    }  # fmt: skip


def test_a_model_loading_is_said_and_does_not_block(kernel: Kernel, platform: FakePlatform, tmp_path: Path) -> None:
    opened(kernel, platform, tmp_path / "paper")
    platform.inside = probing({"step": "answered", "status": 200})
    kernel.parts["runtime"].state.set_slot("main", "starting", "loading its weights", actor=YOU, preset="daily-262k")
    found = kernel.parts["agents"].reach(folder=str(tmp_path / "paper"))
    assert (found["ready"], found["blocked"], found["fix"]) == (False, False, None)
    assert found["problem"].startswith("the model is loading")


def test_a_look_from_inside_that_cannot_run_is_unknown_and_stops_nothing(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    opened(kernel, platform, tmp_path / "paper")
    platform.inside = probing(None)  # a container without python3
    ready(kernel)
    found = kernel.parts["agents"].reach(folder=str(tmp_path / "paper"))
    assert (found["ready"], found["blocked"], found["problem"]) == (True, False, "")
    assert checks(found)["edge"] is None
    edge = next(check for check in found["checks"] if check["name"] == "edge")
    assert "could not be checked" in edge["said"]


def test_the_route_answers_by_folder_or_by_workspace(kernel: Kernel, platform: FakePlatform, tmp_path: Path) -> None:
    opened(kernel, platform, tmp_path / "paper")
    platform.inside = probing({"step": "resolve", "error": NOT_RESOLVED})
    ready(kernel)
    with TestClient(create_app(kernel, token="t", port=7727), base_url="http://127.0.0.1:7727") as http:
        headers = {"Authorization": "Bearer t"}
        by_folder = http.get("/api/v1/agents/reach", params={"folder": str(tmp_path / "paper")}, headers=headers)
        by_name = http.get("/api/v1/agents/reach", params={"workspace": "paper"}, headers=headers)
        neither = http.get("/api/v1/agents/reach", headers=headers)
    assert by_folder.status_code == 200
    assert by_folder.json()["blocked"] is True
    assert by_name.json()["problem"] == by_folder.json()["problem"]
    assert neither.status_code == 400
