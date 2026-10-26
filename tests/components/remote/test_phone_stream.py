"""Design 0025 §3 (decision 0143): the phone's one live stream, `/api/stream` of the listener, for a paired device
only. It says `connected`, then `now` (what the phone shows first: the model, the agent's requests, the machine, the
workspaces with their sessions, the questions and the marks; never the files, which the Files tab reads), then each
of the kernel's events as it is recorded, with its summary as title, its type, its time and whether it needs the
owner's attention (as its type declares, decision 0113), and `now` again once when it changed; a device that comes
back with `Last-Event-ID` gets the events it missed and no earlier one. Every exchange is logged, the stream as one
line (its bodies are not read whole). The listener is served for real here, since a stream never ends on its own."""

import json
import threading
import time
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import httpx2
import pytest
import uvicorn

from clank import registry
from clank.components.remote import tailnet
from clank.components.remote.app import COOKIE, create_phone_app
from clank.components.workspaces import service as workspaces_service
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor, Subject
from clank.kernel.home import Home
from clank.kernel.questions import Option, QuestionDraft
from clank.kernel.service import server_config
from tests.fakes.platform import FakePlatform
from tests.support.served import free_port

OWNER = "owner@example.com"
YOU = Actor(kind="user", via="console")
THROUGH_TAILSCALE = {"Tailscale-User-Login": OWNER}
ACT = {**THROUGH_TAILSCALE, "X-Clank-Phone": "1"}


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: FakePlatform(state="running"))
    kernel = open_kernel(home, clock, registry.components())
    monkeypatch.setattr(kernel.parts["remote"], "owner_login", lambda: OWNER)
    monkeypatch.setattr(tailnet, "read", lambda: tailnet.Tailnet("desk.tail0.ts.net", OWNER))
    yield kernel
    kernel.close()


@pytest.fixture
def served(kernel: Kernel) -> Iterator[str]:
    """The phone's listener served for real on a free port; its base URL."""
    remote = kernel.parts["remote"]
    port = free_port()
    server = uvicorn.Server(server_config(create_phone_app(remote), "127.0.0.1", port))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the listener never started"
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        for close in list(remote.closers):
            close()
        server.should_exit = True
        thread.join(15)


def paired(kernel: Kernel, base: str) -> dict[str, str]:
    """A device paired; its cookie."""
    code = kernel.parts["remote"].pair("my phone", actor=YOU)["code"]
    answer = httpx2.post(f"{base}/api/pair", json={"code": code}, headers=ACT, timeout=10)
    assert answer.status_code == 200, answer.text
    return {COOKIE: answer.cookies[COOKIE]}


class Events:
    """The stream's events as they come, read in a thread; `close` ends the response from outside."""

    def __init__(self, base: str, headers: dict[str, str], cookies: dict[str, str], path: str = "/api/stream") -> None:
        self.found: list[tuple[str, int | None, Any]] = []
        self.path = path
        self.status = 0
        self._lock = threading.Lock()
        self._response: httpx2.Response | None = None
        self._thread = threading.Thread(target=self._read, args=(base, headers, cookies), daemon=True)
        self._thread.start()

    def _read(self, base: str, headers: dict[str, str], cookies: dict[str, str]) -> None:
        try:
            with (
                httpx2.Client(timeout=httpx2.Timeout(10, read=None)) as client,
                client.stream("GET", f"{base}{self.path}", headers=headers, cookies=cookies) as response,
            ):
                self._response = response
                self.status = response.status_code
                fields: dict[str, str] = {}
                for line in response.iter_lines():
                    if line == "":
                        if "event" in fields:
                            data = json.loads(fields.get("data") or "null")
                            with self._lock:
                                self.found.append(
                                    (fields["event"], int(fields["id"]) if "id" in fields else None, data)
                                )
                        fields = {}
                    elif ":" in line and not line.startswith(":"):
                        name, _, value = line.partition(":")
                        fields[name] = value.strip()
        except (httpx2.HTTPError, RuntimeError):
            pass  # closed from outside

    def until(self, name: str, seconds: float = 10, count: int = 1) -> list[tuple[str, int | None, Any]]:
        """The events up to the `count`th of this name, that one included."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            with self._lock:
                places = [i for i, each in enumerate(self.found) if each[0] == name]
                if len(places) >= count:
                    return list(self.found[: places[count - 1] + 1])
            time.sleep(0.05)
        raise AssertionError(f"no {count} {name} event(s); got {[each[0] for each in self.found]}")

    def close(self) -> None:
        if self._response is not None:
            self._response.close()
        self._thread.join(5)


def test_the_stream_says_now_first_then_each_event_with_its_title_and_a_changed_now_once(
    kernel: Kernel, served: str
) -> None:
    cookies = paired(kernel, served)
    events = Events(served, THROUGH_TAILSCALE, cookies)
    try:
        heard = events.until("now")
        assert [each[0] for each in heard] == ["connected", "now"]
        now = heard[-1][2]
        assert set(now) >= {"model", "agent", "machine", "workspaces", "questions", "marks"}
        assert "files" not in now, "the Files tab reads them"
        assert now["questions"] == []
        draft = QuestionDraft(
            type="choice", title="Let paper's agent reach api.openalex.org?", detail="",
            options=[Option(id="always", label="Always", key="y"), Option(id="no", label="No", key="n")],
            default="no", expires=kernel.clock.now() + timedelta(minutes=5), urgency="high",
            about=Subject(kind="workspace", id="paper"),
        )  # fmt: skip
        question = kernel.questions.ask(draft, asked_by=YOU)
        heard = events.until("event")
        _, id, data = heard[-1]
        assert id is not None
        assert data["type"] == "question.asked"
        assert question.title in data["title"]
        assert data["attention"] is True, "a question asked needs the owner (decision 0113)"
        assert data["subject"] == {"kind": "question", "id": question.id}, "where a tap opens"
        assert set(data) <= {"id", "type", "time", "title", "attention", "subject", "about"}, "titles and names only"
        changed = events.until("now", count=2)[-1][2]
        assert [each["id"] for each in changed["questions"]] == [question.id], "now again, once it changed"
        time.sleep(1.5)
        assert sum(1 for each in events.found if each[0] == "now") == 2, "nothing changed: no now again"
    finally:
        events.close()


def test_a_device_that_comes_back_gets_the_events_it_missed_and_an_unpaired_one_nothing(
    kernel: Kernel, served: str
) -> None:
    unpaired = httpx2.get(f"{served}/api/stream", headers=THROUGH_TAILSCALE, timeout=10)
    assert unpaired.status_code == 401
    cookies = paired(kernel, served)
    first = kernel.events.record("remote.switched", summary="the first", actor=YOU, data={"on": True})
    second = kernel.events.record("remote.switched", summary="the second", actor=YOU, data={"on": False})
    events = Events(served, {**THROUGH_TAILSCALE, "Last-Event-ID": str(first.id)}, cookies)
    try:
        heard = events.until("now")
        kinds = [each[0] for each in heard]
        assert kinds.count("event") == 1, kinds
        resumed = next(each for each in heard if each[0] == "event")
        assert (resumed[1], resumed[2]["title"]) == (second.id, "the second")
    finally:
        events.close()
    log = kernel.parts["remote"].traffic.recent(limit=10)
    assert [each for each in log if each["path"] == "/api/stream"], "the stream is logged as one exchange"
