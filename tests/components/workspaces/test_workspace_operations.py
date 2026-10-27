"""Design 0004 §1, §3 and §6: opening a folder makes it a workspace (a record naming it; nothing is written in the
folder), builds Clank's sandbox image if it is not built (asked first: it downloads about a gigabyte), makes the
internal network and the one that reaches the host, starts the edge and the folder's container, and the next time
does nothing it already did (a stopped container is started, not made again). A container's limits are its record's,
else half of what the platform has. A folder whose container would see more than itself (a drive's root, the user's
home, one holding CLANK_HOME or inside it) is refused, as is opening with Docker stopped. Stopping a workspace stops its
container; removing one asks first (saying, when its container runs, that what runs in it ends), then removes its
container and its home, and leaves its folder as it was."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank import registry
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import image_tag, names
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.operations import Operation
from tests.fakes.platform import FakePlatform, container

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
