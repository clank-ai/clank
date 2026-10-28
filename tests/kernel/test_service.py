"""Design 0002 §1 and §2.7, decision 0013: `clank serve` runs the Clank service: it takes its port (refusing clearly
when another program has it, or when a service already runs for the same CLANK_HOME), writes its connection file,
answers only with the token, keeps house (expiring questions, reloading edited settings), and stops on request,
removing the file; what a stop cut short is interrupted at the next start."""

import socket
import time
from datetime import timedelta
from typing import Any

import anyio
import httpx2
import pytest
from fastapi.testclient import TestClient

from clank.kernel.access import local_token, read_connection
from clank.kernel.api import create_app
from clank.kernel.clock import FakeClock
from clank.kernel.components import Component
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.locks import LockHeld, hold
from clank.kernel.operations import OperationContext, OperationType, StepSpec
from clank.kernel.questions import Option, QuestionDraft
from clank.kernel.service import CLOSING_SECONDS, housekeep
from clank.kernel.store import Store
from tests.support.served import clank, free_port, served

YOU = Actor(kind="user", via="console")
GO_ON = QuestionDraft(
    type="approval", title="Go on?", options=[Option(id="yes", label="Yes"), Option(id="no", label="No")]
)


async def asks(context: OperationContext) -> dict[str, Any]:
    async with context.step("ask"):
        answer = await context.ask(GO_ON)
    return {"answer": answer.option}


class Asker:
    def __init__(self, kernel: Kernel) -> None:
        self.kernel = kernel

    def operation_types(self) -> list[OperationType]:
        return [OperationType("test.asks", "Asks first", (StepSpec("ask"),), asks, owner="asker")]


ASKER = Component(name="asker", summary="A component whose operation waits for the user.", build=Asker)


def test_the_service_answers_only_with_the_token_and_stops_on_request(home: Home) -> None:
    with served(home) as (process, connection, _):
        token = local_token(home)
        with httpx2.Client(base_url=connection.url, timeout=10) as http:
            assert http.get("/api/v1/service").status_code == 401
            service = http.get("/api/v1/service", headers={"Authorization": f"Bearer {token}"}).json()
            assert service["pid"] == connection.pid
            http.post("/api/v1/service/stop", headers={"Authorization": f"Bearer {token}"})
        assert process.wait(20) == 0
    assert read_connection(home) is None
    store = Store(home.database)
    try:
        kinds = [row["type"] for row in store.read("SELECT type FROM events ORDER BY id")]
    finally:
        store.close()
    assert "service.started" in kinds
    assert kinds[-1] == "service.stopped"


def test_a_stop_ends_the_event_stream_at_once_telling_its_followers_and_logs_no_error(home: Home) -> None:
    with served(home) as (process, connection, output):
        headers = {"Authorization": f"Bearer {local_token(home)}"}
        with (
            httpx2.Client(base_url=connection.url, headers=headers, timeout=10) as http,
            http.stream("GET", "/api/v1/events", timeout=httpx2.Timeout(10, read=None)) as following,
        ):
            assert following.status_code == 200
            asked = time.perf_counter()
            http.post("/api/v1/service/stop")
            text = following.read().decode("utf-8")
            ended = time.perf_counter() - asked
            assert "event: closing" in text
            # The stream ends when the service says it closes, not at the graceful shutdown's limit: had the limit cut
            # it, Uvicorn would say so (below). The time is a loose check only: on a busy machine a close the service
            # made at once can end just past the limit (2.2 s was seen in a full run), and the process's own exit after
            # it (the interpreter's teardown) is not what is measured.
            assert ended < CLOSING_SECONDS + 3
            assert process.wait(15) == 0
    log = "".join(output)
    assert "timeout graceful shutdown exceeded" not in log, "the graceful shutdown's limit cut the stream"
    assert "Exception in ASGI application" not in log


def test_a_second_service_for_the_same_clank_home_is_refused(home: Home) -> None:
    with served(home) as (_, connection, _):
        second = clank(home, "serve", "--port", str(free_port()))
    assert second.returncode != 0
    assert f"already runs for {home.root} at {connection.url}" in second.stdout + second.stderr


def test_a_service_still_starting_for_the_same_home_is_refused_before_it_writes_its_connection_file(
    home: Home,
) -> None:
    with hold(home.state / "service.lock"):  # what a starting service holds from its first moment
        second = clank(home, "serve", "--port", str(free_port()))
    assert second.returncode != 0
    assert f"a Clank service is starting for {home.root}" in second.stdout + second.stderr
    with hold(home.state / "service.lock"), pytest.raises(LockHeld), hold(home.state / "service.lock"):
        pass


def test_a_port_taken_by_another_program_is_refused_with_a_clear_message(home: Home) -> None:
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        port = taken.getsockname()[1]
        result = clank(home, "serve", "--port", str(port))
    assert result.returncode != 0
    assert f"port {port} is in use" in result.stdout + result.stderr


@pytest.mark.anyio
async def test_the_housekeeping_expires_questions_and_reloads_an_edited_settings_file(
    home: Home, clock: FakeClock
) -> None:
    kernel = open_kernel(home, clock, [])
    try:
        asked = kernel.questions.ask(
            GO_ON.model_copy(update={"default": "no", "expires": clock.now() + timedelta(minutes=1)}), asked_by=YOU
        )
        clock.advance(120)
        (home.config / "service.json").write_text('{"schema": "service/1", "port": 7730}\n', encoding="utf-8")
        await housekeep(kernel)
        assert kernel.questions.get(asked.id).status == "expired"
        assert kernel.settings.get("service", "service").record.model_dump()["port"] == 7730
    finally:
        kernel.close()


def test_an_operation_cut_short_by_a_stop_is_interrupted_at_the_next_start(home: Home, clock: FakeClock) -> None:
    async def leave_one_waiting(kernel: Kernel) -> str:
        async with kernel.operations.running():
            started = await kernel.operations.start("test.asks", actor=YOU)
            with anyio.fail_after(10):
                while kernel.operations.get(started.id).status != "waiting":
                    await anyio.sleep(0.01)
        return started.id

    before = open_kernel(home, clock, [ASKER])
    try:
        left = anyio.run(leave_one_waiting, before)
    finally:
        before.close()
    after = open_kernel(home, clock, [ASKER])
    try:
        app = create_app(after, token="t", port=7720)
        with TestClient(app, base_url="http://127.0.0.1:7720") as api:
            found = api.get(f"/api/v1/records/operation/{left}", headers={"Authorization": "Bearer t"}).json()
        assert found["values"]["status"] == "interrupted"
    finally:
        after.close()
