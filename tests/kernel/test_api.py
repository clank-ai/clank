"""Design 0002 §2.7 and §2.14: every route of the Clank API needs the local token and answers only to the service's own
host names; errors have one shape; every kind of record is read and written through the same routes; questions are
answered as the client that sent the answer; the event stream sends what a client missed, then what happens, without
gaps or repeats, and tells a client behind the pruned history to reload."""

import json
import re
import threading
import time
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import anyio
import pytest
from fastapi.testclient import TestClient

from clank import registry
from clank.components.workspaces import service as workspaces_service
from clank.kernel.api import access_of, create_app, event_stream
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import CLANK, Actor
from clank.kernel.home import Home
from clank.kernel.questions import Option, QuestionDraft
from tests.fakes.platform import FakePlatform

TOKEN = "test-token-0123456789abcdefghijklmnopqrstuvwxyz"
BASE = "http://127.0.0.1:7720"
AUTH = {"Authorization": f"Bearer {TOKEN}", "X-Clank-Client": "console"}
STOP = QuestionDraft(
    type="approval",
    title="Stop Docker Desktop?",
    options=[Option(id="stop", label="Stop it", key="y"), Option(id="cancel", label="Cancel", key="n")],
    default="cancel",
)


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="stopped"))
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


@pytest.fixture
def api(kernel: Kernel) -> Iterator[TestClient]:
    with TestClient(create_app(kernel, token=TOKEN, port=7720), base_url=BASE) as client:
        yield client


def events_in(text: str) -> list[tuple[str, dict[str, Any]]]:
    found = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines() if ": " in line and not line.startswith(":"))
        if "event" in fields:
            found.append((fields["event"], json.loads(fields["data"])))
    return found


def operations(api: TestClient) -> list[tuple[str, str, dict[str, Any]]]:
    paths: dict[str, dict[str, Any]] = api.app.openapi()["paths"]  # type: ignore[attr-defined]
    return [
        (path, method.upper(), operation) for path, methods in paths.items() for method, operation in methods.items()
    ]


def test_the_api_describes_every_route(api: TestClient) -> None:
    described = {(path, method) for path, method, _ in operations(api)}
    assert ("/api/v1/events", "GET") in described
    assert ("/api/v1/questions/{id}/answer", "POST") in described
    assert len(described) >= 15


def test_every_route_refuses_a_call_without_the_token(api: TestClient) -> None:
    for path, method, _ in operations(api):
        concrete = re.sub(r"\{[^}]+\}", "x", path)
        for headers in ({}, {"Authorization": "Bearer wrong"}):
            answer = api.request(method, concrete, headers=headers)
            assert answer.status_code == 401, f"{method} {path} answered {answer.status_code}"
            assert answer.json()["error"]["code"] == "unauthorized"


def test_every_route_declares_its_access_level(api: TestClient) -> None:
    assert [f"{method} {path}" for path, method, operation in operations(api) if not access_of(operation)] == []


def test_a_request_addressed_to_another_host_is_refused(api: TestClient) -> None:
    answer = api.get("/api/v1/service", headers={**AUTH, "Host": "attacker.example:7720"})
    assert answer.status_code == 421
    assert answer.json()["error"]["code"] == "wrong_host"
    assert "access-control-allow-origin" not in answer.headers


def test_errors_have_one_shape(api: TestClient) -> None:
    unknown = api.get("/api/v1/records/nothing", headers=AUTH)
    assert unknown.status_code == 404
    assert set(unknown.json()["error"]) == {"code", "message", "where"}
    invalid = api.put("/api/v1/records/service/service", headers=AUTH, json={"values": {"port": "high"}, "base": None})
    assert invalid.status_code in (409, 422)
    assert set(invalid.json()["error"]) >= {"code", "message", "where"}


def test_the_service_says_what_it_is(api: TestClient) -> None:
    service = api.get("/api/v1/service", headers=AUTH).json()
    assert service["version"]
    assert service["url"] == BASE


def test_kinds_are_listed_with_their_labels_help_and_schemas(api: TestClient) -> None:
    kinds = {kind["kind"]: kind for kind in api.get("/api/v1/kinds", headers=AUTH).json()}
    assert {"service", "event", "operation", "question"} <= set(kinds)
    assert kinds["service"]["sort"] == "settings"
    assert kinds["service"]["schema"]["properties"]["port"]["title"] == "Port"
    assert kinds["question"]["sort"] == "state"


def test_a_settings_record_is_written_over_its_revision_and_refused_over_a_stale_one(api: TestClient) -> None:
    service = api.get("/api/v1/records/service/service", headers=AUTH).json()
    assert (service["source"], service["values"]["port"]) == ("built-in", 7720)
    changed = api.put(
        "/api/v1/records/service/service",
        headers=AUTH,
        json={"values": {**service["values"], "port": 7721}, "base": service["revision"]},
    )
    assert changed.status_code == 200
    assert (changed.json()["source"], changed.json()["values"]["port"]) == ("user", 7721)
    stale = api.put(
        "/api/v1/records/service/service",
        headers=AUTH,
        json={"values": {**service["values"], "port": 7722}, "base": service["revision"]},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["current"]["values"]["port"] == 7721


def test_state_records_are_read_through_the_same_routes_and_never_written_through_them(
    api: TestClient, kernel: Kernel
) -> None:
    asked = kernel.questions.ask(STOP, asked_by=CLANK)
    listed = api.get("/api/v1/records/question", headers=AUTH).json()
    assert [record["id"] for record in listed] == [asked.id]
    one = api.get(f"/api/v1/records/question/{asked.id}", headers=AUTH).json()
    assert one["values"]["title"] == "Stop Docker Desktop?"
    refused = api.put(f"/api/v1/records/question/{asked.id}", headers=AUTH, json={"values": {}, "base": None})
    assert refused.status_code == 405


def test_kinds_say_when_a_change_to_their_records_applies_and_whose_start_applies_it(api: TestClient) -> None:
    kinds = {kind["kind"]: kind for kind in api.get("/api/v1/kinds", headers=AUTH).json()}
    assert kinds["service"]["applies"] == "at the service's next start"
    assert kinds["gateway"]["applies"] == "at the gateway's next start (clank gateway restart)"
    assert kinds["preset"]["applies"] == "at the next start of the slot that runs it"
    assert kinds["notion"]["applies"] == "at once"
    assert kinds["question"]["applies"] is None, "state is not changed by hand"


def test_kinds_say_where_they_are_defined_and_a_settings_record_where_the_users_file_is(api: TestClient) -> None:
    kinds = {kind["kind"]: kind for kind in api.get("/api/v1/kinds", headers=AUTH).json()}
    assert kinds["service"]["defined_in"] == "clank.kernel.service_kinds.ServiceSettings"
    assert kinds["question"]["defined_in"] == "clank.kernel.questions.Question"
    service = api.get("/api/v1/records/service/service", headers=AUTH).json()
    assert (service["source"], service["file"]) == ("built-in", None)
    assert service["user_file"].replace("\\", "/").endswith("config/service.json")


def test_answering_a_question_records_the_client_that_answered(api: TestClient, kernel: Kernel) -> None:
    asked = kernel.questions.ask(STOP, asked_by=CLANK)
    answer = api.post(
        f"/api/v1/questions/{asked.id}/answer", headers={**AUTH, "X-Clank-Client": "vscode"}, json={"option": "stop"}
    )
    assert answer.status_code == 200
    assert answer.json()["answer"]["by"] == {"kind": "user", "via": "vscode"}
    again = api.post(f"/api/v1/questions/{asked.id}/answer", headers=AUTH, json={"option": "cancel"})
    assert again.status_code == 409
    assert "already answered by you (vscode)" in again.json()["error"]["message"]


def test_an_operations_log_is_read_through_the_api_from_any_line_on(api: TestClient) -> None:
    started = api.post("/api/v1/docker/start", headers=AUTH).json()
    for _ in range(500):
        if api.get(f"/api/v1/records/operation/{started['id']}", headers=AUTH).json()["values"]["status"] == "done":
            break
        time.sleep(0.01)
    lines = api.get(f"/api/v1/operations/{started['id']}/log", headers=AUTH).json()
    assert lines[0]["text"] == "asked Fake Docker to start"
    after = {"after": lines[-1]["number"]}
    assert api.get(f"/api/v1/operations/{started['id']}/log", headers=AUTH, params=after).json() == []


def test_the_stream_sends_what_a_client_missed_in_order(api: TestClient, kernel: Kernel) -> None:
    first = kernel.questions.ask(STOP, asked_by=CLANK)
    kernel.questions.answer(first.id, by=Actor(kind="user", via="console"), option="cancel")
    with api.stream("GET", "/api/v1/events?after=0&follow=false", headers=AUTH) as answer:
        text = answer.read().decode("utf-8")
    assert [kind for kind, _ in events_in(text)] == ["connected", "question.asked", "question.answered"]
    ids = [int(line[4:]) for line in text.splitlines() if line.startswith("id: ")]
    assert ids == sorted(ids)


def test_the_stream_tells_a_client_behind_the_pruned_history_to_reload(
    api: TestClient, kernel: Kernel, clock: FakeClock
) -> None:
    kernel.questions.ask(STOP, asked_by=CLANK)
    clock.advance(timedelta(days=40).total_seconds())
    kernel.events.prune(clock.now() - timedelta(days=30))
    with api.stream("GET", "/api/v1/events?after=0&follow=false", headers=AUTH) as answer:
        text = answer.read().decode("utf-8")
    assert [kind for kind, _ in events_in(text)][:2] == ["connected", "reset"]


@pytest.mark.anyio
async def test_the_stream_sends_live_events_from_other_threads_without_gaps_or_repeats(kernel: Kernel) -> None:
    received: list[int] = []

    def ask_many() -> None:
        for _ in range(20):
            kernel.questions.ask(STOP, asked_by=CLANK)

    with anyio.fail_after(10):
        stream = event_stream(kernel, after=kernel.events.last_id(), types=["question.asked"])
        writers = [threading.Thread(target=ask_many) for _ in range(3)]
        for writer in writers:
            writer.start()
        async for chunk in stream:
            received += [int(line[4:]) for line in chunk.splitlines() if line.startswith("id: ")]
            if len(received) >= 60:
                break
        await stream.aclose()
        for writer in writers:
            await anyio.to_thread.run_sync(writer.join)
    assert received == sorted(set(received))
    assert len(received) == 60


@pytest.mark.parametrize("route", ["/api/v1/history", "/api/v1/operations"])
@pytest.mark.parametrize("limit", [0, -1, 1001])
def test_a_page_size_outside_one_to_a_thousand_is_refused_in_the_one_error_shape(
    api: TestClient, route: str, limit: int
) -> None:
    answer = api.get(route, params={"limit": limit}, headers=AUTH)
    assert answer.status_code == 422
    assert answer.json()["error"]["code"] == "invalid"
    assert answer.json()["error"]["where"] == {"fields": ["query.limit"]}
    said = answer.json()["error"]["message"]
    assert said.startswith("the request is not what this route takes: limit: "), "the field named, and why (2026-10-26)"
    assert api.get(route, params={"limit": 1000}, headers=AUTH).status_code == 200
