"""Design 0002 §2.4-2.5 and §3.2: starting and stopping Docker are operations the service runs under one lock. A start
asks the platform, waits for its engine within its time limit (and can be canceled while it waits), then puts right
what the start disturbed; a stop asks first when containers Clank did not start are running, naming them, and "cancel"
leaves Docker running; a press sent twice starts one operation, and a second start while one runs is refused; the
background check records `docker.changed` once per change (the first reading is what clients load, not a change);
after a restart an interrupted operation is reconciled
from Docker's state."""

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import anyio
import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.workspaces import service as workspaces_service
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


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="stopped")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    monkeypatch.setattr(workspaces_service, "WAIT_SECONDS", 0.001)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def workspaces(kernel: Kernel) -> Workspaces:
    part: Workspaces = kernel.parts["workspaces"]
    return part


async def finished(kernel: Kernel, id: str) -> Operation:
    with anyio.fail_after(10):
        return await kernel.operations.wait(id)


async def until(kernel: Kernel, id: str, reached: Callable[[Operation], bool]) -> Operation:
    for _ in range(5000):
        operation = kernel.operations.get(id)
        if reached(operation):
            return operation
        await anyio.sleep(0.001)
    raise AssertionError(f"{id} never got there; it is {kernel.operations.get(id).status}")


async def test_the_check_records_docker_changed_once_per_change_and_not_for_the_first_reading(
    kernel: Kernel, platform: FakePlatform
) -> None:
    await workspaces(kernel).check()
    await workspaces(kernel).check()
    platform.state = "running"
    platform.containers = [container("postgres-dev")]
    await workspaces(kernel).check()
    await workspaces(kernel).check()
    changes = [event.summary for event in reversed(kernel.events.latest(10, types=["docker.changed"]))]
    assert changes == ["Fake Docker · running · 1 container running, not Clank's"]


async def test_a_start_asks_the_platform_waits_for_its_engine_then_puts_right_what_it_disturbed(
    kernel: Kernel, platform: FakePlatform
) -> None:
    platform.starts_after = 3
    async with kernel.operations.running():
        started = await kernel.operations.start("docker.start", actor=YOU)
        done = await finished(kernel, started.id)
    assert done.status == "done", done.error
    assert platform.calls == ["start", "after start"]
    assert [step.name for step in done.steps] == ["start", "wait"]
    assert done.result is not None
    assert done.result["docker"]["state"] == "running"


async def test_a_start_when_docker_runs_is_done_at_once(kernel: Kernel, platform: FakePlatform) -> None:
    platform.state = "running"
    async with kernel.operations.running():
        started = await kernel.operations.start("docker.start", actor=YOU)
        done = await finished(kernel, started.id)
    assert (done.status, done.result is not None and done.result["already"]) == ("done", True)
    assert platform.calls == []


async def test_a_start_that_does_not_answer_in_time_fails_naming_the_time_and_frees_docker(
    kernel: Kernel, platform: FakePlatform, clock: FakeClock
) -> None:
    platform.starts_after = None
    platform.on_check = lambda: clock.advance(120)
    async with kernel.operations.running():
        started = await kernel.operations.start("docker.start", actor=YOU)
        done = await finished(kernel, started.id)
        assert done.status == "failed"
        assert "300 seconds" in done.error
        again = await kernel.operations.start("docker.start", actor=YOU)
        await finished(kernel, again.id)


async def test_canceling_while_it_waits_ends_the_start_canceled_and_frees_docker(
    kernel: Kernel, platform: FakePlatform
) -> None:
    platform.starts_after = None
    async with kernel.operations.running():
        started = await kernel.operations.start("docker.start", actor=YOU)
        await until(kernel, started.id, lambda operation: bool(operation.steps) and operation.steps[-1].name == "wait")
        await kernel.operations.cancel(started.id, actor=YOU)
        done = await finished(kernel, started.id)
        assert (done.status, done.error) == ("canceled", "canceled by you (console)")
        again = await kernel.operations.start("docker.start", actor=YOU)
        await kernel.operations.cancel(again.id, actor=YOU)
        await finished(kernel, again.id)


async def test_a_stop_with_only_clanks_containers_or_none_does_not_ask(
    kernel: Kernel, platform: FakePlatform, home: Home
) -> None:
    platform.state = "running"
    platform.containers = [container("workspace-demo", labels={"clank.home": home.id}), container("x", state="exited")]
    async with kernel.operations.running():
        started = await kernel.operations.start("docker.stop", actor=YOU)
        done = await finished(kernel, started.id)
    assert done.status == "done", done.error
    assert (platform.calls, platform.state) == (["stop"], "stopped")
    assert kernel.questions.find() == []


async def test_stopping_docker_with_containers_clank_did_not_start_asks_first_and_cancel_leaves_it_running(
    kernel: Kernel, platform: FakePlatform
) -> None:
    platform.state = "running"
    platform.containers = [
        container("toolbox-sandbox-017", labels={"toolbox.sandbox": "1"}),
        container("postgres-dev"),
        container("old-build", state="exited"),
    ]
    async with kernel.operations.running():
        started = await kernel.operations.start("docker.stop", actor=YOU)
        waiting = await until(kernel, started.id, lambda operation: operation.status == "waiting")
        assert waiting.waiting_on is not None
        question = kernel.questions.get(waiting.waiting_on)
        assert question.title == "Stop Fake Docker?"
        assert "2 containers that Clank did not start are running" in question.detail
        assert "toolbox-sandbox-017, postgres-dev" in question.detail
        assert "old-build" not in question.detail
        assert question.default == "cancel"
        kernel.questions.answer(question.id, by=YOU, option="cancel")
        done = await finished(kernel, started.id)
    assert (done.status, done.error) == ("canceled", "canceled: you (console) answered Cancel")
    assert (platform.calls, platform.state) == ([], "running")


async def test_a_stop_question_nobody_answers_takes_its_default_and_leaves_docker_running(
    kernel: Kernel, platform: FakePlatform, clock: FakeClock
) -> None:
    platform.state = "running"
    platform.containers = [container("postgres-dev")]
    async with kernel.operations.running():
        started = await kernel.operations.start("docker.stop", actor=YOU)
        await until(kernel, started.id, lambda operation: operation.status == "waiting")
        clock.advance(30 * 60 + 1)
        [expired] = kernel.questions.expire_due()
        done = await finished(kernel, started.id)
    assert (expired.status, expired.answer is not None and expired.answer.option) == ("expired", "cancel")
    assert (done.status, done.error) == ("canceled", "canceled: nobody answered within 30 minutes")
    assert (platform.calls, platform.state) == ([], "running")


async def test_answering_stop_stops_docker(kernel: Kernel, platform: FakePlatform) -> None:
    platform.state = "running"
    platform.containers = [container("postgres-dev")]
    async with kernel.operations.running():
        started = await kernel.operations.start("docker.stop", actor=YOU)
        waiting = await until(kernel, started.id, lambda operation: operation.status == "waiting")
        assert waiting.waiting_on is not None
        kernel.questions.answer(waiting.waiting_on, by=YOU, option="stop")
        done = await finished(kernel, started.id)
    assert done.status == "done", done.error
    assert (platform.calls, platform.state) == (["stop"], "stopped")


async def test_without_docker_installed_start_and_stop_fail_with_what_to_do(
    kernel: Kernel, platform: FakePlatform
) -> None:
    platform.state = "not installed"
    async with kernel.operations.running():
        for kind in ("docker.start", "docker.stop"):
            started = await kernel.operations.start(kind, actor=YOU)
            done = await finished(kernel, started.id)
            assert (done.status, done.error) == ("failed", "Fake Docker is not installed: install it")
    assert platform.calls == []


async def test_after_a_restart_an_interrupted_start_is_reconciled_from_dockers_state(
    kernel: Kernel, platform: FakePlatform
) -> None:
    platform.starts_after = None
    async with kernel.operations.running():
        started = await kernel.operations.start("docker.start", actor=YOU)
        await until(kernel, started.id, lambda operation: bool(operation.steps) and operation.steps[-1].name == "wait")
    platform.state = "running"
    [interrupted] = await kernel.operations.recover()
    assert (interrupted.id, interrupted.status) == (started.id, "interrupted")
    [note] = kernel.events.after(0, types=["operation.reconciled"])
    assert note.data["note"] == "after the restart, Fake Docker is running"


def test_a_press_sent_twice_starts_one_operation_and_another_start_is_refused_as_busy(
    kernel: Kernel, platform: FakePlatform
) -> None:
    platform.starts_after = None
    headers = {"Authorization": "Bearer t", "X-Clank-Client": "vscode"}
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as http:
        first = http.post("/api/v1/docker/start", headers={**headers, "X-Clank-Request-Key": "press-1"}).json()
        again = http.post("/api/v1/docker/start", headers={**headers, "X-Clank-Request-Key": "press-1"}).json()
        assert again["id"] == first["id"]
        refused = http.post("/api/v1/docker/start", headers=headers)
        assert (refused.status_code, refused.json()["error"]["code"]) == (409, "busy")
        assert first["id"] in refused.json()["error"]["message"]
        http.post(f"/api/v1/operations/{first['id']}/cancel", headers=headers)


def test_the_routes_start_operations_that_record_the_client(kernel: Kernel, platform: FakePlatform) -> None:
    platform.state = "running"
    headers = {"Authorization": "Bearer t", "X-Clank-Client": "vscode"}
    with TestClient(create_app(kernel, token="t", port=7720), base_url="http://127.0.0.1:7720") as http:
        started = http.post("/api/v1/docker/start", headers=headers).json()
        assert (started["type"], started["started_by"]) == ("docker.start", {"kind": "user", "via": "vscode"})
        assert datetime.fromisoformat(started["created"]) == datetime(2026, 10, 11, 12, 0, tzinfo=UTC)
