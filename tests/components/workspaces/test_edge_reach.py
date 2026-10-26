"""Design 0004 §3 and design 0024 §2 (revised 2026-10-26): the edge is on the network of every workspace, whatever
made it again. Made again by an opening (the ports it forwards changed), it joins back the networks of the workspaces
that run and of those that are stopped, as it does when it is made or started; the service's check of Docker finds a
running workspace whose network the edge is not on from the reading it takes anyway (no other Docker call while nothing
is missing), joins it back, starts an edge that was stopped and makes one that is gone, and says what it repaired in
its log and as an event; it leaves a running edge that forwards other ports to an opening or an agent's start, which
make it again. An edge or a workspace's container that cannot start because a network it was on is gone (made again
since) is made again. The views say a workspace cut off from the model plainly, with what Clank does about it: the
route of the workspaces, the folder's view and `clank workspace list`. A folder named `edge` never gets the edge's
container's name."""

import logging
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from clank import registry
from clank.cli import common
from clank.cli.main import main
from clank.client import Client
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import image_tag, names
from clank.components.workspaces.service import Workspaces
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.operations import Operation
from tests.fakes.platform import FakePlatform, container

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")
PORTS = "18210,18211"  # the gateway's port and the proxy's, as the settings have them by default


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def workspaces(kernel: Kernel) -> Workspaces:
    part: Workspaces = kernel.parts["workspaces"]
    return part


def folder(tmp_path: Path, name: str) -> Path:
    made = tmp_path / name
    made.mkdir(parents=True)
    return made


def ran(kernel: Kernel, platform: FakePlatform, tmp_path: Path, name: str, *, state: str = "running") -> None:
    """A workspace whose container was made by an opening, on its own network."""
    kernel.settings.write("workspace", name, {"path": str(folder(tmp_path, name))}, base=None, actor=YOU)
    found = names(kernel.home.id)
    labels = {"clank.home": kernel.home.id, "clank.component": "workspaces", "clank.record": name}
    platform.networks[found.inner(name)] = True
    platform.containers.append(container(found.container(name), state=state, labels=labels,
                                         networks=[found.inner(name)]))  # fmt: skip


def edge(kernel: Kernel, *networks: str, state: str = "running", ports: str = PORTS) -> Any:
    """The edge, made from Clank's sandbox image, on the network that reaches the host and on these."""
    found = names(kernel.home.id)
    labels = {"clank.home": kernel.home.id, "clank.component": "workspaces", "clank.record": "edge",
              "clank.ports": ports}  # fmt: skip
    made = container(found.edge, state=state, labels=labels, networks=[found.outer, *networks])
    return made.model_copy(update={"image": image_tag()})


async def run(kernel: Kernel, kind: str, params: dict[str, Any]) -> Operation:
    started = await kernel.operations.start(kind, params, actor=YOU)
    with anyio.fail_after(30):
        return await kernel.operations.wait(started.id)


def repaired(kernel: Kernel) -> list[Any]:
    return list(reversed(kernel.events.latest(10, types=["workspaces.edge_repaired"])))


def counting(platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every call that would ask Docker something besides its status, kept by name."""
    asked: list[str] = []
    for name in ("container", "join_network", "start_container", "run_container", "image_exists", "ensure_network"):
        found: Callable[..., Any] = getattr(platform, name)

        def kept(*args: Any, _name: str = name, _found: Callable[..., Any] = found, **kwargs: Any) -> Any:
            asked.append(_name)
            return _found(*args, **kwargs)

        monkeypatch.setattr(platform, name, kept)
    return asked


async def test_an_edge_made_again_by_an_opening_joins_back_the_networks_of_the_other_workspaces(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    """As on 2026-10-26: the edge from before the proxy forwarded one port; opening another workspace made it again,
    and the four that ran lost their way to the model (`getaddrinfo EAI_AGAIN edge` in OpenCode)."""
    found = names(kernel.home.id)
    ran(kernel, platform, tmp_path, "running")
    ran(kernel, platform, tmp_path, "resting", state="exited")
    platform.images.add(image_tag())
    platform.networks[found.outer] = False
    platform.containers.append(edge(kernel, found.inner("running"), found.inner("resting"), ports="18210"))
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder(tmp_path, "third")), "yes": True})
    assert done.status == "done", done.error
    made = platform.container(found.edge)
    assert made is not None
    assert made.clank["clank.ports"] == PORTS
    assert set(made.networks) == {found.outer, found.inner("running"), found.inner("resting"), found.inner("third")}
    log = [line.text for line in kernel.operations.log_lines(done.id)]
    assert "the edge joined the networks of resting and running" in log, log
    [event] = repaired(kernel)
    assert event.data["workspaces"] == ["running"], "the one that ran was cut off; the stopped one was only made ready"
    assert event.summary == (
        "the edge forwarded port 18210, not 18210 and 18211 (the gateway's and the proxy's): Clank made it again; the "
        "edge joined the networks of resting and running, so running reaches the model again (found by opening third)"
    )


async def test_the_check_of_docker_joins_the_edge_back_to_each_running_workspaces_network_and_says_so(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    found = names(kernel.home.id)
    for name in ("paper", "notes", "survey"):
        ran(kernel, platform, tmp_path, name)
    ran(kernel, platform, tmp_path, "resting", state="exited")
    platform.containers.append(edge(kernel, found.inner("paper")))
    with caplog.at_level(logging.WARNING):
        await workspaces(kernel).check()
    assert platform.calls == [f"join {found.edge} {found.inner('notes')}", f"join {found.edge} {found.inner('survey')}"]
    [event] = repaired(kernel)
    assert event.data["workspaces"] == ["notes", "survey"]
    assert event.data["found_by"] == "Clank's check of Docker"
    said = (
        "the edge was not on the networks of notes and survey: Clank joined it back, so notes and survey reach the "
        "model again (found by Clank's check of Docker)"
    )
    assert event.summary == said
    assert said in caplog.text, "the service's log says it too"


async def test_the_check_asks_docker_nothing_more_while_every_running_workspace_reaches_the_edge(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    found = names(kernel.home.id)
    ran(kernel, platform, tmp_path, "paper")
    ran(kernel, platform, tmp_path, "resting", state="exited")
    platform.containers.append(edge(kernel, found.inner("paper")))
    asked = counting(platform, monkeypatch)
    await workspaces(kernel).check()
    await workspaces(kernel).check()
    assert asked == [], "the reading the check takes anyway says it all"
    assert (platform.calls, repaired(kernel)) == ([], [])


async def test_the_check_starts_a_stopped_edge_and_makes_a_missing_one_while_a_workspace_runs(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    found = names(kernel.home.id)
    ran(kernel, platform, tmp_path, "paper")
    platform.containers.append(edge(kernel, found.inner("paper"), state="exited"))
    await workspaces(kernel).check()
    assert platform.calls == [f"start {found.edge}"]
    assert repaired(kernel)[-1].summary == (
        "the edge was stopped: Clank started it, so paper reaches the model again (found by Clank's check of Docker)"
    )
    platform.containers = [each for each in platform.containers if each.name != found.edge]
    platform.images.add(image_tag())
    platform.calls.clear()
    await workspaces(kernel).check()
    made = [f"network {found.outer}", f"run {found.edge}", f"join {found.edge} {found.inner('paper')}"]
    assert platform.calls == made
    assert platform.specs[found.edge].labels[-1] == ("clank.ports", PORTS)
    assert repaired(kernel)[-1].summary == (
        "the edge was not there: Clank made it; the edge joined paper's network, so paper reaches the model again "
        "(found by Clank's check of Docker)"
    )


async def test_the_check_says_once_when_the_edge_cannot_be_made_and_does_not_try_again_at_once(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Its image is not built: a `docker run` would download it from the internet every few seconds."""
    ran(kernel, platform, tmp_path, "paper")
    with caplog.at_level(logging.WARNING):
        await workspaces(kernel).check()
        await workspaces(kernel).check()
    assert platform.calls == []
    assert caplog.text.count("the edge is not there and cannot be made") == 1, caplog.text
    assert repaired(kernel) == []


async def test_the_check_leaves_a_running_edge_that_forwards_other_ports_for_an_opening_to_make_again(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    """Making it again cuts every request in flight: the owner's opening or agent's start does it, not the check."""
    found = names(kernel.home.id)
    ran(kernel, platform, tmp_path, "paper")
    platform.containers.append(edge(kernel, ports="18210"))
    await workspaces(kernel).check()
    assert platform.calls == [f"join {found.edge} {found.inner('paper')}"]
    [row] = workspaces(kernel).workspaces()
    assert row["edge"] == "stale"
    assert row["edge_said"] == (
        "the edge forwards port 18210, not 18210 and 18211 (the gateway's and the proxy's): opening the workspace or "
        "starting its agent makes it again"
    )


async def test_starting_the_agent_puts_the_edge_right_first_and_says_what_it_did(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    found = names(kernel.home.id)
    ran(kernel, platform, tmp_path, "paper")
    ran(kernel, platform, tmp_path, "notes")
    platform.containers.append(edge(kernel, found.inner("notes"), ports="18210"))
    platform.images.add(image_tag())
    said = workspaces(kernel).reach("paper")
    made = platform.container(found.edge)
    assert made is not None
    assert made.clank["clank.ports"] == PORTS
    assert set(made.networks) == {found.outer, found.inner("paper"), found.inner("notes")}
    assert said == [
        "the edge forwarded port 18210, not 18210 and 18211 (the gateway's and the proxy's): Clank made it again",
        "the edge joined the networks of notes and paper",
    ]
    assert repaired(kernel)[-1].data["found_by"] == "starting the agent in paper"
    platform.calls.clear()
    assert workspaces(kernel).reach("paper") == []
    assert platform.calls == [], "nothing to do the next time"


async def test_an_edge_and_a_container_whose_network_was_made_again_are_made_again_when_opened(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    """`docker network prune` removes the network of a stopped workspace; opening it makes the network again, with
    another id, and neither the edge nor its container can start on the old one."""
    found = names(kernel.home.id)
    place = folder(tmp_path, "paper")
    async with kernel.operations.running():
        first = await run(kernel, "workspaces.open", {"folder": str(place), "yes": True})
        assert first.status == "done", first.error
        platform.stop_container(found.container("paper"), 10)
        platform.stop_container(found.edge, 10)
        platform.remove_network(found.inner("paper"))
        platform.calls.clear()
        again = await run(kernel, "workspaces.open", {"folder": str(place)})
    assert again.status == "done", again.error
    assert platform.calls == [
        f"network {found.inner('paper')}", f"start {found.edge}", f"remove {found.edge}", f"run {found.edge}",
        f"join {found.edge} {found.inner('paper')}", f"start {found.container('paper')}",
        f"remove {found.container('paper')}", f"run {found.container('paper')}",
    ]  # fmt: skip
    assert {each.name: each.state for each in platform.containers} == {
        found.edge: "running",
        found.container("paper"): "running",
    }
    log = " ".join(line.text for line in kernel.operations.log_lines(again.id))
    assert f"{found.edge} could not start (a network it was on is gone): it is made again" in log
    assert f"{found.container('paper')} could not start (a network it was on is gone): it is made again" in log


async def test_a_folder_named_edge_never_gets_the_edges_containers_name(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    """Its container would have been the edge itself, on the network that reaches the host."""
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder(tmp_path, "Edge")), "yes": True})
    assert done.status == "done", done.error
    assert (done.result or {})["workspace"] == "edge-2"
    assert (done.result or {})["container"] != names(kernel.home.id).edge


@pytest.fixture
def http(kernel: Kernel, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    with TestClient(create_app(kernel, token="t", port=7731), base_url="http://127.0.0.1:7731") as client:
        monkeypatch.setattr(common, "connect", lambda: Client("http://127.0.0.1:7731", "t", name="cli", http=client))
        yield client


def test_a_workspace_cut_off_from_the_model_is_said_plainly_with_what_clank_does(
    kernel: Kernel, platform: FakePlatform, http: TestClient, tmp_path: Path
) -> None:
    found = names(kernel.home.id)
    ran(kernel, platform, tmp_path, "paper")
    ran(kernel, platform, tmp_path, "notes")
    ran(kernel, platform, tmp_path, "resting", state="exited")
    platform.containers.append(edge(kernel, found.inner("notes")))
    rows = {row["name"]: row for row in http.get("/api/v1/workspaces", headers={"Authorization": "Bearer t"}).json()}
    cut = (
        "cut off from the model: the edge is not on its network; Clank joins it back within 5 seconds (opening the "
        "workspace or starting its agent does it now)"
    )
    assert (rows["paper"]["edge"], rows["paper"]["edge_said"]) == ("cut", cut)
    assert (rows["notes"]["edge"], rows["notes"]["edge_said"]) == ("on", "")
    assert (rows["resting"]["edge"], rows["resting"]["edge_said"]) == (None, "")
    view = workspaces(kernel).folder_view(str(tmp_path / "paper"))
    assert (view["edge"], view["edge_said"]) == ("cut", cut)
    listed = CliRunner().invoke(main, ["workspace", "list"])
    assert listed.exit_code == 0, listed.output
    lines = listed.output.splitlines()
    paper = next(index for index, line in enumerate(lines) if line.startswith("paper "))
    assert lines[paper + 1].strip() == cut
    assert sum("cut off" in line for line in lines) == 1, "said under paper alone"
    platform.containers = [each for each in platform.containers if each.name != found.edge]
    stopped = workspaces(kernel).folder_view(str(tmp_path / "notes"))
    assert stopped["edge_said"].startswith("cut off from the model: the edge is not there; Clank makes it again")
