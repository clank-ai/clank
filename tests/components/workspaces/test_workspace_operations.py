"""Design 0004 §1, §3 and §6: opening a folder makes it a workspace (a record naming it; nothing is written in the
folder), builds Clank's sandbox image if it is not built (asked first: it downloads about a gigabyte), makes the
internal network and the one that reaches the host, starts the edge and the folder's container, and the next time
does nothing it already did (a stopped container is started, not made again). A container's limits are its record's,
else half of what the platform has. A folder whose container would see more than itself (a drive's root, the user's
home, one holding CLANK_HOME or inside it) is refused, as is opening with Docker stopped. Stopping a workspace stops its
container; removing one asks first (saying, when its container runs, that what runs in it ends), then removes its
container and its home, and leaves its folder as it was. Design 0014 §2: on Docker Engine, which Clank never starts,
opening while it is stopped is refused in the status's words, with the command that starts it. Design 0014 §4: Docker's
memory limits are read as a workspace opens (never in the regular check, the last reading kept): where Docker cannot
limit a container's memory no workspace opens, saying so in Docker's words with the fix (`cgroup_enable=memory` on a
Raspberry Pi), unless `allow_unlimited_memory` is set, and then its log and Docker's summary say its memory is not
limited. A folder the agent's user (1000 in its container) may not write, as the platform mounts it, is refused before
its record is made, in the platform's words: whose folder it is, and how to let user 1000 write it. A workspace's own
network is made with the platform's options that give this computer no address on it (Docker Engine's bridge would),
the outer network keeping its address; one made before them is made again once the workspace's container does not
run, and said until then."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank import registry
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.adapters.docker_engine import DockerEngine, refusal
from clank.components.workspaces.sandbox import image_tag, names
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.operations import Operation
from tests.fakes.platform import FakePlatform, container
from tests.fakes.recorded import FIXTURES, RecordedProgram

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="console")


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    found = tmp_path / "work" / "My Project"
    found.mkdir(parents=True)
    (found / "notes.md").write_text("mine\n", encoding="utf-8")
    return found


async def run(kernel: Kernel, kind: str, params: dict[str, Any]) -> Operation:
    """Start an operation; it as it is once it waits on a question or has ended."""
    started = await kernel.operations.start(kind, params, actor=YOU)
    with anyio.fail_after(30):
        while True:
            current = kernel.operations.get(started.id)
            if (current.status == "waiting" and current.waiting_on) or current.status in ("done", "failed", "canceled"):
                return current
            await anyio.sleep(0.01)


async def finish(kernel: Kernel, operation: Operation) -> Operation:
    with anyio.fail_after(30):
        return await kernel.operations.wait(operation.id)


def record(kernel: Kernel, name: str) -> dict[str, Any]:
    return dict(kernel.settings.get("workspace", name).record.model_dump())


async def test_opening_a_folder_makes_its_workspace_and_its_container_and_the_next_time_does_nothing_again(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
        assert done.status == "done", done.error
        before = list(platform.calls)
        again = await run(kernel, "workspaces.open", {"folder": str(folder)})
    assert again.status == "done", again.error
    home = names(kernel.home.id)
    assert (done.result or {})["workspace"] == "my-project"
    assert record(kernel, "my-project")["path"] == str(folder)
    inner = home.inner("my-project")
    assert before == [
        f"build {image_tag()}", f"network {home.outer}", f"network {inner}", f"run {home.edge}",
        f"join {home.edge} {inner}", f"run {home.container('my-project')}",
    ]  # fmt: skip
    assert platform.calls == before, "nothing is done twice"
    spec = platform.specs[home.container("my-project")]
    assert spec.binds == ((str(folder), "/workspace"),)
    assert (spec.cpus, spec.memory_mib) == (8.0, 8192), "half the platform's CPUs and a quarter of its memory"
    assert platform.networks == {home.outer: False, inner: True}, "its own internal network, and the edge's"
    assert platform.specs[home.container("my-project")].networks == ((inner, ""),)
    assert sorted(path.name for path in folder.iterdir()) == ["notes.md"], "nothing is written in the folder"


async def test_the_edge_is_made_again_when_the_ports_it_forwards_change(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    """Design 0024 §2: an edge from before the proxy forwards one port; it is stopped and made again with both."""
    home = names(kernel.home.id)
    platform.containers.append(container(home.edge, labels={"clank.ports": "18210"}))
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
    assert done.status == "done", done.error
    assert [call for call in platform.calls if home.edge in call] == [
        f"stop {home.edge}", f"remove {home.edge}", f"run {home.edge}", f"join {home.edge} {home.inner('my-project')}",
    ]  # fmt: skip
    assert platform.specs[home.edge].labels[-1] == ("clank.ports", "18210,18211")
    assert "18211" in platform.specs[home.edge].command


async def test_a_stopped_container_from_before_the_proxy_is_made_again_when_opened(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    """Design 0024 §2: the proxy is in the container's environment, so one made without it is made again (stopped
    first by the owner, as an image change is); its label `clank.proxy` says which it was told."""
    home = names(kernel.home.id)
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
        assert done.status == "done", done.error
        name = home.container("my-project")
        assert platform.container(name) is not None
        assert platform.container(name).clank.get("clank.proxy") == "18211"  # type: ignore[union-attr]
        platform.containers = [each for each in platform.containers if each.name != name]
        platform.containers.append(container(name, state="exited", labels={"clank.record": "my-project"}))
        platform.calls.clear()
        again = await run(kernel, "workspaces.open", {"folder": str(folder)})
    assert again.status == "done", again.error
    assert [call for call in platform.calls if name in call] == [f"remove {name}", f"run {name}"]
    assert dict(platform.specs[name].env)["HTTPS_PROXY"].endswith("@edge:18211")


async def test_the_image_build_is_asked_first_and_no_builds_nothing(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    async with kernel.operations.running():
        waiting = await run(kernel, "workspaces.open", {"folder": str(folder)})
        question = kernel.questions.get(waiting.waiting_on or "")
        assert question.title == "Build Clank's sandbox image?"
        assert "about a gigabyte" in question.detail
        kernel.questions.answer(question.id, by=YOU, option="cancel")
        done = await finish(kernel, waiting)
    assert done.status == "canceled"
    assert not [call for call in platform.calls if call.startswith(("build", "run"))]


async def test_a_stopped_container_is_started_not_made_again(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    name = names(kernel.home.id).container("my-project")
    async with kernel.operations.running():
        await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
        stopped = await run(kernel, "workspaces.stop", {"name": "my-project"})
        assert stopped.status == "done", stopped.error
        assert platform.container(name).state == "exited"  # type: ignore[union-attr]
        again = await run(kernel, "workspaces.open", {"folder": str(folder)})
    assert again.status == "done", again.error
    assert platform.calls[-1] == f"start {name}"
    assert platform.container(name).state == "running"  # type: ignore[union-attr]


async def test_a_second_folder_of_the_same_name_gets_a_name_of_its_own_and_its_record_sets_its_limits(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    first, second = tmp_path / "a" / "proj", tmp_path / "b" / "proj"
    first.mkdir(parents=True)
    second.mkdir(parents=True)
    async with kernel.operations.running():
        await run(kernel, "workspaces.open", {"folder": str(first), "yes": True})
        kernel.settings.write(
            "workspace", "proj-2", {"path": str(second), "cpus": 2, "memory_mib": 4096}, base=None, actor=YOU
        )
        done = await run(kernel, "workspaces.open", {"folder": str(second)})
    assert (done.result or {})["workspace"] == "proj-2"
    spec = platform.specs[names(kernel.home.id).container("proj-2")]
    assert (spec.cpus, spec.memory_mib) == (2.0, 4096)


async def test_a_folder_whose_container_would_see_more_than_itself_is_refused(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    inside = kernel.home.root / "logs"
    refused = {
        str(Path(tmp_path.anchor)): "a drive's root",
        str(Path.home()): "your home folder",
        str(kernel.home.root.parent): "holds Clank's own folder",
        str(inside): "inside Clank's own folder",
        str(tmp_path / "missing"): "is not a folder",
    }
    async with kernel.operations.running():
        for given, why in refused.items():
            done = await run(kernel, "workspaces.open", {"folder": given, "yes": True})
            assert done.status == "failed", given
            assert why in (done.error or ""), (given, done.error)
    assert not [call for call in platform.calls if call.startswith("run")]


async def test_opening_with_docker_stopped_says_how_to_start_it(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    platform.state = "stopped"
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
    assert done.status == "failed"
    assert "`clank docker start`" in (done.error or "")


async def test_opening_a_workspace_while_docker_engine_is_stopped_names_the_command_to_start_it(
    home: Home, clock: FakeClock, folder: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    program = RecordedProgram.load(FIXTURES / "docker-engine" / "28.0.4", state="stopped")
    engine = DockerEngine(program, program.command, platform="linux", answer=program.answer)
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: engine)
    kernel = open_kernel(home, clock, registry.components())
    try:
        async with kernel.operations.running():
            done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
    finally:
        kernel.close()
    assert done.status == "failed"
    assert done.error == (
        "Docker Engine is stopped: start it with `sudo systemctl start docker`; Clank never starts or stops Docker "
        "Engine"
    )
    assert "clank docker start" not in (done.error or ""), "Clank does not start the system's Docker"


async def test_removing_a_workspace_asks_then_removes_its_container_and_home_and_leaves_its_folder(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    home = names(kernel.home.id)
    async with kernel.operations.running():
        await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
        waiting = await run(kernel, "workspaces.remove", {"name": "my-project"})
        question = kernel.questions.get(waiting.waiting_on or "")
        assert question.title == "Remove the workspace my-project?"
        assert f"{folder} stays as it is" in question.detail
        kernel.questions.answer(question.id, by=YOU, option="remove")
        done = await finish(kernel, waiting)
    assert done.status == "done", done.error
    assert platform.container(home.container("my-project")) is None
    assert home.volume("my-project") not in platform.volumes
    assert home.inner("my-project") not in platform.networks
    assert (home.inner("my-project"), home.edge) not in platform.joined
    assert [loaded.id for loaded in kernel.settings.records("workspace")] == []
    assert (folder / "notes.md").read_text(encoding="utf-8") == "mine\n"


async def test_removing_a_workspace_whose_container_runs_says_that_what_runs_in_it_ends(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    async with kernel.operations.running():
        await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
        waiting = await run(kernel, "workspaces.remove", {"name": "my-project"})
        question = kernel.questions.get(waiting.waiting_on or "")
        assert "runs now" in question.detail, question.detail
        assert "OpenCode" in question.detail, "what ends: the agent in a window too"
        kernel.questions.answer(question.id, by=YOU, option="cancel")
        assert (await finish(kernel, waiting)).status == "canceled"
        await run(kernel, "workspaces.stop", {"name": "my-project"})
        waiting = await run(kernel, "workspaces.remove", {"name": "my-project"})
        question = kernel.questions.get(waiting.waiting_on or "")
        assert "runs now" not in question.detail, "a stopped container ends nothing"
        kernel.questions.answer(question.id, by=YOU, option="cancel")
        await finish(kernel, waiting)


NO_MEMORY_LIMITS = (False, ["WARNING: No memory limit support"])  # Docker's words on a Pi's default kernel


async def test_a_workspace_does_not_open_where_docker_cannot_limit_memory_saying_how_to_fix_it(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    platform.memory = NO_MEMORY_LIMITS
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
    assert done.status == "failed"
    error = done.error or ""
    assert "WARNING: No memory limit support" in error, "in Docker's words"
    assert "`cgroup_enable=memory`" in error
    assert "/boot/firmware/cmdline.txt" in error
    assert "allow_unlimited_memory" in error
    assert kernel.settings.records("workspace") == [], "refused before its record is made"
    assert not [call for call in platform.calls if call.startswith(("run", "build"))]


async def test_allowing_unlimited_memory_opens_it_and_every_client_is_told(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    platform.memory = NO_MEMORY_LIMITS
    platform.images.add(image_tag())
    loaded = kernel.settings.get("docker", "docker")
    allowed = {**loaded.record.model_dump(), "allow_unlimited_memory": True}
    kernel.settings.write("docker", "docker", allowed, base=loaded.revision, actor=YOU)
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
    assert done.status == "done", done.error
    said = " ".join(line.text for line in kernel.operations.log_lines(done.id))
    assert "its memory is not limited" in said
    assert "WARNING: No memory limit support" in said
    view = kernel.parts["workspaces"].docker(refresh=True)
    assert view["memory_limits"] is False
    assert view["summary"].endswith(" · memory not limited"), "the summary every client shows says so"


async def test_dockers_memory_limits_are_read_when_a_workspace_opens_never_in_the_regular_check(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    platform.images.add(image_tag())
    for _ in range(3):
        await kernel.parts["workspaces"].check()
    assert platform.memory_asked == 0, "never in the 5-second check"
    assert kernel.parts["workspaces"].docker()["memory_limits"] is None, "not read yet"
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
    assert done.status == "done", done.error
    assert platform.memory_asked == 1
    assert kernel.parts["workspaces"].docker(refresh=True)["memory_limits"] is True, "the last reading is kept"


async def test_on_linux_a_folder_the_agent_cannot_write_is_refused_saying_why(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    platform.access = refusal(str(folder), 0o40755, 1001, 1001, None, "owner")  # Docker Engine's words
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
    assert done.status == "failed"
    error = done.error or ""
    assert error.startswith("the agent works as user 1000 in its container"), error
    assert "is owner's (user 1001" in error, "whose folder it is"
    assert "may not write it" in error
    assert "setfacl -R -m u:1000:rwX,d:u:1000:rwX" in error, "how to let it write"
    assert platform.access_asked == [str(folder)]
    assert kernel.settings.records("workspace") == [], "refused before its record is made"
    platform.access = ""
    async with kernel.operations.running():
        opened = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
    assert opened.status == "done", opened.error


HOST_OFF = {"com.docker.network.bridge.inhibit_ipv4": "true"}  # Docker Engine's: no address of this computer's


async def test_a_workspaces_own_network_gives_this_computer_no_address_where_the_platform_would(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    platform.inner_options = dict(HOST_OFF)
    platform.images.add(image_tag())
    async with kernel.operations.running():
        done = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
    assert done.status == "done", done.error
    found = names(kernel.home.id)
    assert platform.network_options(found.inner(str((done.result or {})["workspace"]))) == HOST_OFF
    assert platform.network_options(found.outer) == {}, "the edge's way out keeps this computer's address"


async def test_a_network_made_before_is_made_again_without_this_computers_address_once_its_container_does_not_run(
    kernel: Kernel, platform: FakePlatform, folder: Path
) -> None:
    platform.images.add(image_tag())
    async with kernel.operations.running():
        first = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
        assert first.status == "done", first.error
        name = str((first.result or {})["workspace"])
        found = names(kernel.home.id)
        inner = found.inner(name)
        assert platform.network_options(inner) == {}, "made before the platform kept this computer off it"
        platform.inner_options = dict(HOST_OFF)
        running = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
        assert running.status == "done", running.error
        said = " ".join(line.text for line in kernel.operations.log_lines(running.id))
        assert f"{inner} gives this computer an address on it" in said
        assert "once the workspace is stopped and opened again" in said
        assert platform.network_options(inner) == {}, "what runs is left as it is"
        stopped = await run(kernel, "workspaces.stop", {"name": name})
        assert stopped.status == "done", stopped.error
        again = await run(kernel, "workspaces.open", {"folder": str(folder), "yes": True})
    assert again.status == "done", again.error
    assert platform.network_options(inner) == HOST_OFF, "made again, the host given no address on it"
    told = " ".join(line.text for line in kernel.operations.log_lines(again.id))
    assert f"{inner} gave this computer an address on it: made again without one" in told
    container = platform.container(found.container(name))
    assert container is not None
    assert container.state == "running", "made again on it, its home kept"
    assert f"remove {found.container(name)}" in platform.calls
    edge = platform.container(found.edge)
    assert edge is not None
    assert inner in edge.networks, "the edge back on it"
