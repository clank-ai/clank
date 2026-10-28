"""Design 0001 §5.1 and §5.7, design 0002 §2.15: the console loads what it shows once, then follows the one event
stream: each event brings the fresh data of the topics it touches, read from the API off the screen's thread; a live
log line arrives as it is written; a lost service is said, tried again, and reloaded whole when it is back; stopping
the follower ends it at once. Design 0013 §7: a window told its model changed brings the slots again, so This folder
says it at once. Design 0016 §11 and §14: whether a model is usable, the cloud providers and the cloud's cost are read
at the start (unknown from a service without their routes), and again on the events that change each, and only those.
Design 0028 §4: so is `clank setup`'s checklist, again whenever Docker, a slot, an operation's end or a workspace's
record changes."""

import queue
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest

from clank.client import Client
from clank.console import data as console_data
from clank.console.data import HISTORY, ConsoleData, Follower, Update, apply, load
from clank.kernel.core import Kernel
from clank.kernel.events import CLANK
from clank.kernel.questions import Option, QuestionDraft
from tests.fakes.platform import FakePlatform, container
from tests.support.cloud import CloudBench
from tests.support.live import live_service
from tests.support.served import free_port

STOP = QuestionDraft(
    type="approval",
    title="Stop Docker Desktop?",
    options=[Option(id="stop", label="Stop them and Docker", key="y"), Option(id="cancel", label="Cancel", key="n")],
    default="cancel",
)


@contextmanager
def following(client: Client, after: int) -> Iterator["queue.Queue[Update]"]:
    updates: queue.Queue[Update] = queue.Queue()
    follower = Follower(client, after, updates)
    thread = threading.Thread(target=follower.run, daemon=True)
    thread.start()
    try:
        yield updates
    finally:
        follower.stop()
        thread.join(5)
        assert not thread.is_alive(), "the follower did not stop"


def take(updates: "queue.Queue[Update]", until: Callable[[Update], bool], seconds: float = 10) -> list[Update]:
    taken: list[Update] = []
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            update = updates.get(timeout=0.05)
        except queue.Empty:
            continue
        taken.append(update)
        if until(update):
            return taken
    raise AssertionError(f"never came; got {[update.topic for update in taken]}")


def test_loading_reads_every_topic(client: Client, kernel: Kernel) -> None:
    asked = kernel.questions.ask(STOP, asked_by=CLANK)
    data = load(client)
    assert data.connected
    assert data.service["version"]
    assert data.docker is not None
    assert data.docker["state"] == "running"
    assert data.machine is not None
    assert (data.machine["profile"]["detected"], data.machine["doctor"]) == (None, None)
    assert [question["id"] for question in data.questions] == [asked.id]
    assert data.history[-1]["type"] == "question.asked"
    assert data.last_event == data.history[-1]["id"]
    assert "docker" in {kind["kind"] for kind in data.kinds}


def test_a_question_asked_reaches_the_console_as_an_event_then_as_the_fresh_questions(
    client: Client, kernel: Kernel
) -> None:
    with following(client, kernel.events.last_id()) as updates:
        take(updates, lambda update: update.topic == "connection" and update.data is True)
        asked = kernel.questions.ask(STOP, asked_by=CLANK)
        taken = take(updates, lambda update: update.topic == "questions")
    events = [update.data["type"] for update in taken if update.topic == "event"]
    assert events == ["question.asked"]
    assert [question["id"] for question in taken[-1].data] == [asked.id]


def test_docker_changing_brings_the_fresh_view_of_docker(
    client: Client, kernel: Kernel, platform: FakePlatform
) -> None:
    kernel.parts["workspaces"].docker(refresh=True)
    with following(client, kernel.events.last_id()) as updates:
        take(updates, lambda update: update.topic == "connection")
        platform.containers.append(container("postgres-dev"))
        kernel.parts["workspaces"].docker(refresh=True)
        taken = take(updates, lambda update: update.topic == "docker")
    assert "postgres-dev" in {each["name"] for each in taken[-1].data["containers"]}


def test_a_doctor_run_brings_the_machine_profile_then_its_checks(client: Client, kernel: Kernel) -> None:
    with following(client, kernel.events.last_id()) as updates:
        take(updates, lambda update: update.topic == "connection")
        client.post("machine/doctor")
        taken = take(updates, lambda update: update.topic == "machine" and update.data["doctor"] is not None)
    assert taken[-1].data["doctor"]["of"] == 11
    assert taken[-1].data["profile"]["cores"] == 16
    assert "operations" in {update.topic for update in taken}


def test_a_live_log_line_arrives_as_it_is_written(client: Client, kernel: Kernel, platform: FakePlatform) -> None:
    platform.state = "stopped"
    with following(client, kernel.events.last_id()) as updates:
        take(updates, lambda update: update.topic == "connection")
        client.post("docker/start")
        taken = take(updates, lambda update: update.topic == "log")
    assert taken[-1].data["data"]["text"] == "asked Fake Docker to start"


def test_who_is_connected_reaches_the_service_topic(client: Client, kernel: Kernel) -> None:
    with following(client, kernel.events.last_id()) as updates:
        taken = take(updates, lambda update: update.topic == "clients")
    assert taken[-1].data == ["console"]


def test_a_lost_service_is_said_and_one_back_on_the_same_address_is_reloaded_whole(
    kernel: Kernel, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(console_data, "RETRY_SECONDS", 0.05)
    port = free_port()
    updates: queue.Queue[Update] = queue.Queue()
    with live_service(kernel, port=port) as client:
        console = Client(client.url, "t", name="console")
        follower = Follower(console, kernel.events.last_id(), updates)
        thread = threading.Thread(target=follower.run, daemon=True)
        thread.start()
        take(updates, lambda update: update.topic == "connection" and update.data is True)
    try:
        take(updates, lambda update: update.topic == "connection" and update.data is False)
        asked = kernel.questions.ask(STOP, asked_by=CLANK)
        with live_service(kernel, port=port):
            reloaded = take(updates, lambda update: update.topic == "all")
            assert [question["id"] for question in reloaded[-1].data.questions] == [asked.id]
            take(updates, lambda update: update.topic == "connection" and update.data is True)
    finally:
        follower.stop()
        thread.join(5)
        console.close()


def test_applying_keeps_at_most_the_newest_events_and_says_what_changed() -> None:
    data = ConsoleData()
    for number in range(1, HISTORY + 11):
        changed = apply(data, Update("event", {"id": number, "type": "question.asked"}))
    assert changed == {"history"}
    assert len(data.history) == HISTORY
    assert (data.history[0]["id"], data.last_event) == (11, HISTORY + 10)
    assert apply(data, Update("connection", False)) == {"connection"}
    assert not data.connected
    assert apply(data, Update("questions", [{"id": "q-1"}])) == {"questions"}
    assert apply(data, Update("clients", ["console", "vscode"])) == {"service"}
    assert data.service["clients"] == ["console", "vscode"]


def test_loading_reads_the_runtimes_slots_presets_engines_and_launches(client: Client) -> None:
    data = load(client)
    assert [(slot["name"], slot["status"]) for slot in data.slots] == [
        ("main", "stopped"), ("fast", "stopped"), ("vision", "stopped"),
    ]  # fmt: skip
    assert {preset["id"] for preset in data.presets} >= {"daily-262k"}
    assert {engine["name"] for engine in data.engines} == {"kvmem-llamacpp", "llamacpp"}
    assert data.launches == []


def test_a_slot_changing_brings_the_fresh_slots_and_launches(client: Client, kernel: Kernel) -> None:
    runtime = kernel.parts["runtime"]
    with following(client, kernel.events.last_id()) as updates:
        take(updates, lambda update: update.topic == "connection")
        runtime.state.set_slot("main", "failed", "a test failed it", actor=CLANK)
        taken = take(updates, lambda update: update.topic == "slots")
    slots = taken[-1].data
    assert [(slot["name"], slot["status"], slot["reason"]) for slot in slots] == [
        ("main", "failed", "a test failed it"),
        ("fast", "stopped", "never started"),
        ("vision", "stopped", "never started"),
    ]


def test_a_preset_written_brings_the_fresh_presets(client: Client, kernel: Kernel) -> None:
    values = {"title": "mine", "engine": "kvmem-llamacpp", "engine_version": "v0.16.0-rc1", "model": "qwen3.8-27b"}
    with following(client, kernel.events.last_id()) as updates:
        take(updates, lambda update: update.topic == "connection")
        kernel.settings.write("preset", "mine", values, base=None, actor=CLANK)
        taken = take(updates, lambda update: update.topic == "presets")
    assert "mine" in {preset["id"] for preset in taken[-1].data}


def test_what_ends_an_install_a_download_or_a_removal_touches_the_engines() -> None:
    def ended(via: str) -> dict[str, object]:
        return {"type": "operation.finished", "actor": {"kind": "clank", "via": via}, "subject": None}

    for via in ("runtime.install", "runtime.adopt", "runtime.uninstall", "runtime.download", "runtime.verify",
                "runtime.remove"):  # fmt: skip
        assert console_data.touched(ended(via)) == ["operations", "engines", "setup"], via
    assert console_data.touched(ended("runtime.load")) == ["operations", "setup"]
    host = {"type": "settings.changed", "actor": {"kind": "user", "via": "cli"}, "subject": {"kind": "host", "id": "x"}}
    assert console_data.touched(host) == ["engines", "hosts"]


def test_the_setup_checklist_is_read_at_the_start_and_again_on_what_changes_it(client: Client) -> None:
    data = load(client)
    assert data.setup is not None
    assert [item["id"] for item in data.setup["items"]][:2] == ["docker_installed", "docker_running"]

    def event(type: str, subject: dict[str, str] | None = None) -> dict[str, object]:
        return {"type": type, "actor": {"kind": "clank", "via": "workspaces"}, "subject": subject}

    assert console_data.touched(event("docker.changed")) == ["docker", "setup"]
    assert console_data.touched(event("settings.changed", {"kind": "workspace", "id": "paper"})) == ["setup"]
    assert "setup" not in console_data.touched(event("operation.step")), "an operation's end, not each of its steps"


def test_a_window_told_its_model_changed_touches_the_slots() -> None:
    told = {"type": "agents.model_changed", "actor": {"kind": "clank", "via": "flow runner"},
            "subject": {"kind": "workspace", "id": "paper"}}  # fmt: skip
    assert console_data.touched(told) == ["slots"]


def test_loading_reads_whether_a_model_is_usable_the_providers_and_the_cost(
    client: Client, cloud_api: CloudBench
) -> None:
    data = load(client)
    assert data.usable is not None
    assert (data.usable["usable"], data.usable["candidates"]) == (False, [])
    assert data.endpoints == []
    assert data.cost is not None
    assert data.cost["limits"] == {"day_usd": None, "month_usd": None, "warn_at": 0.8,
                                   "said": "no daily or monthly limit"}  # fmt: skip


def test_each_cloud_event_touches_its_part_and_only_its_part() -> None:
    def event(type: str, subject: dict[str, str] | None = None) -> dict[str, object]:
        return {"type": type, "actor": {"kind": "user", "via": "console"}, "subject": subject}

    endpoint = {"kind": "endpoint", "id": "openrouter"}
    for type in ("runtime.endpoint_added", "runtime.endpoint_changed", "runtime.endpoint_removed"):
        assert console_data.touched(event(type, endpoint)) == ["endpoints", "usable"], type
    assert console_data.touched(event("runtime.endpoint_checked", endpoint)) == ["endpoints"]
    for type in ("secret.set", "secret.removed"):
        assert console_data.touched(event(type, endpoint)) == ["endpoints", "usable"], type
    assert console_data.touched(event("secret.set", {"kind": "mcp-server", "id": "lit"})) == ["mcp"]
    for type in ("gateway.cost", "gateway.limit_warned", "gateway.limit_reached", "gateway.limit_raised"):
        assert console_data.touched(event(type)) == ["cost"], type
    assert console_data.touched(event("runtime.slot", {"kind": "slot", "id": "main"})) == [
        "slots", "launches", "usable", "setup",
    ]  # fmt: skip
    assert console_data.touched(event("settings.changed", {"kind": "preset", "id": "x"})) == ["presets", "usable"]
    assert console_data.touched(event("workspaces.cloud_answered", {"kind": "workspace", "id": "paper"})) == [], (
        "a workspace's answer is the folder page's to read"
    )


def test_a_key_set_brings_the_fresh_providers_and_whether_a_model_is_usable(
    client: Client, kernel: Kernel, cloud_api: CloudBench
) -> None:
    cloud_api.add()
    cloud_api.write_preset()
    client.delete("runtime/endpoints/openrouter/key")
    with following(client, kernel.events.last_id()) as updates:
        take(updates, lambda update: update.topic == "connection")
        client.put("runtime/endpoints/openrouter/key", {"key": "made-up-openrouter-key"})
        taken = take(updates, lambda update: update.topic == "usable" and update.data["usable"])
    endpoints = next(update.data for update in reversed(taken) if update.topic == "endpoints")
    assert endpoints[0]["key"]["set"]


def test_a_limit_reached_brings_the_fresh_cost(client: Client, kernel: Kernel, cloud_api: CloudBench) -> None:
    with following(client, kernel.events.last_id()) as updates:
        take(updates, lambda update: update.topic == "connection")
        cloud_api.reach("day", 5.02)
        taken = take(updates, lambda update: update.topic == "cost")
    assert taken[-1].data["paused"]["by"] == "day"
