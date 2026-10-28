"""Design 0028 §4 (S4): Clank's sandbox image is built during the setup, as an operation of its own that runs in the
background (`workspaces.image`): it builds the image when no image of this Clank's tag is there, each line of the build
in its log, and does nothing when it is built; it asks first unless `yes` (it downloads about a gigabyte), and nothing
is built on a no; it is refused, in Docker's words, while Docker does not run. Opening a workspace holds the same lock,
so an opening while the image is built is refused, naming the build (and a build while a workspace opens, likewise).
The setup's checklist says the build while it runs, with its operation."""

import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank import registry
from clank.components.agents import checklist, setupfacts, vscode
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import image_tag
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.operations import Busy, Operation
from tests.fakes.platform import FakePlatform

pytestmark = pytest.mark.anyio
YOU = Actor(kind="user", via="cli")


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    monkeypatch.setattr(vscode, "which", lambda name: None)
    monkeypatch.setattr(checklist, "found_tools", lambda: frozenset())
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


async def run(kernel: Kernel, params: dict[str, Any]) -> Operation:
    """Build the image; the operation as it is once it waits on a question or has ended."""
    started = await kernel.operations.start("workspaces.image", params, actor=YOU)
    with anyio.fail_after(30):
        while True:
            current = kernel.operations.get(started.id)
            if (current.status == "waiting" and current.waiting_on) or current.status in ("done", "failed", "canceled"):
                return current
            await anyio.sleep(0.01)


async def test_it_builds_the_image_of_this_clanks_tag_when_it_is_not_built_each_line_in_its_log(
    kernel: Kernel, platform: FakePlatform
) -> None:
    async with kernel.operations.running():
        done = await run(kernel, {"yes": True})
    assert done.status == "done", done.error
    assert platform.calls == [f"build {image_tag()}"]
    assert image_tag() in platform.images
    lines = [line.text for line in kernel.operations.log_lines(done.id)]
    assert "#12 naming to clank-sandbox done" in lines
    assert (done.result or {})["built"] is True


async def test_it_does_nothing_when_the_image_is_built(kernel: Kernel, platform: FakePlatform) -> None:
    platform.images.add(image_tag())
    async with kernel.operations.running():
        done = await run(kernel, {"yes": True})
    assert done.status == "done", done.error
    assert platform.calls == []
    assert (done.result or {})["built"] is False


async def test_it_asks_first_unless_yes_and_a_no_builds_nothing(kernel: Kernel, platform: FakePlatform) -> None:
    async with kernel.operations.running():
        waiting = await run(kernel, {})
        assert waiting.status == "waiting"
        question = kernel.questions.get(str(waiting.waiting_on))
        assert "about a gigabyte" in question.detail
        kernel.questions.answer(question.id, by=YOU, option="cancel")
        with anyio.fail_after(30):
            ended = await kernel.operations.wait(waiting.id)
    assert ended.status == "canceled"
    assert platform.calls == []


async def test_it_is_refused_while_docker_does_not_run(kernel: Kernel, platform: FakePlatform) -> None:
    platform.state = "stopped"
    async with kernel.operations.running():
        failed = await run(kernel, {"yes": True})
    assert failed.status == "failed"
    assert "Docker is stopped" in failed.error
    assert platform.calls == []


async def test_an_opening_while_the_image_is_built_is_refused_naming_the_build(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    platform.build_lines = ["#5 [3/9] RUN apt-get install"]
    held = threading.Event()
    building = platform.build_image

    def slow(*args: Any, **kwargs: Any) -> int | None:
        held.set()
        time.sleep(0.5)
        return building(*args, **kwargs)

    platform.build_image = slow  # type: ignore[method-assign]
    async with kernel.operations.running():
        started = await kernel.operations.start("workspaces.image", {"yes": True}, actor=YOU)
        with anyio.fail_after(10):
            while not held.is_set():
                await anyio.sleep(0.01)
        with pytest.raises(Busy, match="Build Clank's sandbox image"):
            await kernel.operations.start("workspaces.open", {"folder": str(folder), "yes": True}, actor=YOU)
        facts = await anyio.to_thread.run_sync(setupfacts.from_service, kernel)
        assert facts.building is not None
        assert facts.building.operation == started.id
        with anyio.fail_after(30):
            await kernel.operations.wait(started.id)
