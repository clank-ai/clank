"""What the console shows, and how it stays current (design 0001 §5.1, §5.7; design 0002 §2.15).  The console holds
nothing of its own. `load` reads every topic it shows from the API once (the history first, so the stream can resume
right after it), and a `Follower`, in a thread of its own, follows the one event stream: each kept event becomes an
`event` update, and the topics it touches (`questions`, `operations`, `docker`, `machine`, `service`, the runtime's
`slots`, `presets`, `engines`, `launches` and `hosts`, the MCP servers, `mcp`, those of the folder the console was
started in included, the Monitor's Watch for `marks`, and the cloud's: whether a model is `usable`, the providers,
`endpoints`, and the `cost`, design 0016 §11 and §14; `clank setup`'s checklist, `setup`, design 0028 §4) are read
again from the API by a second thread, each once however many events touched it meanwhile, so a burst of events costs a
few reads and the screen's thread never calls the API. A live log line becomes `log`, who is connected `clients`, and
each reading of the machine's meters (`machine.meters`, once a second) `meter`, kept with the last `METERS` (`meters`,
read whole at load). The gateway's activity (`activity`) is loaded with the rest; the shell reads it again every few
seconds. The stream's first word (`connected`) becomes `connection` True; a lost connection, or a stream ended by the
service stopping (`closing`), becomes `connection` False, and the service is tried again every `RETRY_SECONDS`; when it
answers again, or when the stream says the console fell behind (`reset`), everything is read again (`all`). The app
takes the updates off the queue at most four times a second and `apply`s them, which caps its redraws. A service
without the cloud's routes (one older than the console) leaves those three unknown (None) rather than failing the load,
and one without the setup's route its checklist.
"""

import contextlib
import logging
import os
import queue
import socket
import threading
from dataclasses import dataclass, field, fields
from typing import Any

import httpx2

from clank.client import Client, ClientError, NotRunning, ServerEvent

log = logging.getLogger(__name__)
HISTORY = 500
OPERATIONS = 20
RETRY_SECONDS = 2.0
LAUNCHES = 20
METERS = 300  # the readings kept: five minutes, as the service keeps them
TOPICS = (
    "service", "docker", "machine", "questions", "operations", "slots", "presets", "engines", "launches", "hosts",
    "mcp", "meters", "activity", "marks", "usable", "endpoints", "cost", "setup",
)  # fmt: skip
OPTIONAL = {"usable", "endpoints", "cost", "setup"}  # unknown (None) from a service without their routes
PATHS = {
    "activity": "gateway/activity",
    "slots": "runtime/slots",
    "presets": "runtime/presets",
    "engines": "runtime/engines",
    "hosts": "runtime/hosts",
    "marks": "agents/marks",
    "usable": "runtime/usable",
    "endpoints": "runtime/endpoints",
    "cost": "gateway/cost",
    "setup": "setup",
}
GATEWAY_COST = ("gateway.cost", "gateway.limit_warned", "gateway.limit_reached", "gateway.limit_raised")
# What ends with an engine or a model file put on a host, or taken off: the engines' installs change.
INSTALLS = (
    "runtime.install",
    "runtime.adopt",
    "runtime.uninstall",
    "runtime.download",
    "runtime.verify",
    "runtime.remove",
)


@dataclass
class ConsoleData:
    """Everything the console shows, as last read."""

    service: dict[str, Any] = field(default_factory=dict)
    docker: dict[str, Any] | None = None
    machine: dict[str, Any] | None = None
    questions: list[dict[str, Any]] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)
    operations: list[dict[str, Any]] = field(default_factory=list)
    slots: list[dict[str, Any]] = field(default_factory=list)
    presets: list[dict[str, Any]] = field(default_factory=list)
    engines: list[dict[str, Any]] = field(default_factory=list)
    launches: list[dict[str, Any]] = field(default_factory=list)
    hosts: list[dict[str, Any]] = field(default_factory=list)
    mcp: list[dict[str, Any]] = field(default_factory=list)
    meters: list[dict[str, Any]] = field(default_factory=list)
    activity: dict[str, Any] | None = None  # the gateway's: its requests in flight (read again every few seconds)
    marks: dict[str, Any] | None = None  # the Monitor's Watch for: the newest marks, and how many are not seen
    usable: dict[str, Any] | None = None  # whether a model is usable, and why (design 0016 §14); None: not known
    endpoints: list[dict[str, Any]] | None = None  # the cloud providers (design 0016 §4); None: not known
    cost: dict[str, Any] | None = None  # the cloud's spending today and this month, the limits, a pause (§11)
    setup: dict[str, Any] | None = None  # `clank setup`'s checklist (design 0028 §4); None: not known
    kinds: list[dict[str, Any]] = field(default_factory=list)
    connected: bool = False
    last_event: int = 0
    last_log: dict[str, Any] | None = None

    def shown_slots(self) -> list[dict[str, Any]]:
        """The slots the pages list: the main one always, another once it has run (the `fast` slot of completion stays
        out of sight until completion is set up, design 0006)."""
        return [slot for slot in self.slots if slot["name"] == "main" or slot["reason"] != "never started"]


@dataclass(frozen=True)
class Update:
    """One change for the console: a topic and its new data."""

    topic: str
    data: Any


def fetch(client: Client, topic: str) -> Any:
    """One topic, read from the API; one of the cloud's, None from a service without its route."""
    if topic in OPTIONAL:
        try:
            return client.get(PATHS[topic])
        except ClientError as error:
            if error.status == 404:
                return None
            raise
    if topic == "operations":
        return client.get("operations", limit=OPERATIONS)
    if topic == "launches":
        return client.get("runtime/launches", limit=LAUNCHES)
    if topic == "mcp":
        return client.get("mcp/servers", folder=os.getcwd())["servers"]
    if topic == "meters":
        return client.get("machine/meters")["samples"]
    return client.get(PATHS.get(topic, topic))


def load(client: Client) -> ConsoleData:
    """Everything the console shows, read once."""
    history = list(reversed(client.get("history", limit=HISTORY)))
    data = ConsoleData(
        history=history,
        last_event=history[-1]["id"] if history else 0,
        kinds=client.get("kinds"),
        connected=True,
    )
    for topic in TOPICS:
        setattr(data, topic, fetch(client, topic))
    return data


def touched(event: dict[str, Any]) -> list[str]:
    """The topics a kept event changes."""
    kind = event["type"]
    if kind.startswith("question."):
        return ["questions"]
    if kind.startswith("operation."):
        ended = kind == "operation.finished"
        if ended and event["actor"]["via"] == "machine.doctor":
            return ["operations", "machine", "setup"]
        if ended:
            return ["operations", "engines", "setup"] if event["actor"]["via"] in INSTALLS else ["operations", "setup"]
        return ["operations"]
    if kind == "docker.changed":
        return ["docker", "setup"]
    if kind in ("agents.marked", "agents.marks_seen"):
        return ["marks"]
    if kind == "agents.model_changed":  # a window told its model changed (design 0013 §7): the slots' pages read again
        return ["slots"]
    if kind.startswith("service."):
        return ["service"]
    if kind == "runtime.slot":
        return ["slots", "launches", "usable", "setup"]
    if kind == "runtime.preset_changed":  # a cloud preset's settings (design 0016 §7): its page, This folder's limits
        return ["presets", "slots"]
    if kind == "runtime.endpoint_checked":
        return ["endpoints"]
    if kind.startswith("runtime.endpoint_"):
        return ["endpoints", "usable"]
    if kind in GATEWAY_COST:
        return ["cost"]
    secret_of = (event.get("subject") or {}).get("kind") if kind in ("secret.set", "secret.removed") else None
    if secret_of == "endpoint":
        return ["endpoints", "usable"]
    secret_of_a_server = kind.startswith("secret.") and (event.get("subject") or {}).get("kind") == "mcp-server"
    if kind == "mcp.changed" or secret_of_a_server:
        return ["mcp"]
    if kind.startswith("settings."):
        subject = (event.get("subject") or {}).get("kind")
        if subject == "machine":
            return ["machine"]
        if subject == "preset":
            return ["presets", "usable"]
        if subject == "host":
            return ["engines", "hosts"]
        if subject == "model-file":
            return ["engines"]
        if subject == "mcp-server":
            return ["mcp"]
        if subject == "workspace":
            return ["setup"]
        if subject == "runtime":  # dev mode, which each provider's view says (decision 0149)
            return ["endpoints"]
    return []


def apply(data: ConsoleData, update: Update) -> set[str]:
    """Apply an update to what the console shows; returns the topics that changed."""
    topic, value = update.topic, update.data
    if topic == "all":
        for each in fields(ConsoleData):
            setattr(data, each.name, getattr(value, each.name))
        return {"all"}
    if topic == "event":
        data.history.append(value)
        del data.history[:-HISTORY]
        data.last_event = value["id"]
        return {"history"}
    if topic == "connection":
        data.connected = bool(value)
        return {"connection"}
    if topic == "clients":
        data.service = {**data.service, "clients": value}
        return {"service"}
    if topic == "log":
        data.last_log = value
        return {"log"}
    if topic == "meter":
        data.meters.append(value)
        del data.meters[:-METERS]
        return {"meters"}
    if topic in TOPICS:
        setattr(data, topic, value)
        return {topic}
    return set()


class Follower:
    """Follows the event stream in a thread of its own, turning what happens into updates on a queue.

    Each of its threads reads through a connection of its own (cloned from the client it is given) and closes it
    itself. `stop` ends the stream at once by shutting its socket down and closing its response: the first wakes a
    read waiting on it on Linux and macOS, the second on Windows. The other threads finish the request they are
    making, if any, and end.
    """

    def __init__(self, client: Client, after: int | None, updates: "queue.Queue[Update]") -> None:
        self._client = client
        self._after = after
        self._updates = updates
        self._stopped = threading.Event()
        self._lock = threading.Lock()
        self._response: httpx2.Response | None = None
        self._dirty: set[str] = set()
        self._wanted = threading.Event()

    def run(self) -> None:
        """Load everything first (unless told where to resume), then follow until stopped, through lost connections."""
        fetcher = threading.Thread(target=self._fetch, name="console-fetcher", daemon=True)
        fetcher.start()
        reader = self._client.clone()
        try:
            if self._after is None and not self._reload(reader):
                self._updates.put(Update("connection", False))
                self._reconnect(reader)
            while not self._stopped.is_set():
                self._follow(reader)
                if self._stopped.is_set():
                    return
                self._updates.put(Update("connection", False))
                self._reconnect(reader)
        finally:
            self._wanted.set()
            reader.close()

    def stop(self) -> None:
        """Stop following: end the stream now, and the other threads after the request they are making."""
        self._stopped.set()
        self._wanted.set()
        with self._lock:
            response, self._response = self._response, None
        if response is not None:
            _interrupt(response)

    def _opened(self, response: httpx2.Response) -> None:
        with self._lock:
            self._response = response
        if self._stopped.is_set():
            self.stop()

    def _follow(self, reader: Client) -> None:
        stream = self._client.clone()
        try:
            for message in stream.events(after=self._after, opened=self._opened):
                if self._stopped.is_set():
                    return
                self._receive(message, reader)
        except (NotRunning, ClientError):
            return
        except Exception:
            if not self._stopped.is_set():
                log.exception("following the event stream failed")
        finally:
            with self._lock:
                self._response = None
            stream.close()

    def _receive(self, message: ServerEvent, reader: Client) -> None:
        if message.name == "connected":
            self._updates.put(Update("connection", True))
        elif message.name == "reset":
            if not self._reload(reader):
                raise NotRunning("the service did not answer after telling this client to reload")
        elif message.id is None:
            if message.name == "operation.log":
                self._updates.put(Update("log", message.data))
            elif message.name == "service.clients":
                self._updates.put(Update("clients", message.data["data"]["clients"]))
            elif message.name == "machine.meters":
                self._updates.put(Update("meter", message.data["data"]))
        elif message.id > (self._after or 0):
            self._after = message.id
            self._updates.put(Update("event", message.data))
            topics = touched(message.data)
            if topics:
                with self._lock:
                    self._dirty.update(topics)
                    self._wanted.set()

    def _fetch(self) -> None:
        client = self._client.clone()
        try:
            while True:
                self._wanted.wait()
                if self._stopped.is_set():
                    return
                with self._lock:
                    topics, self._dirty = self._dirty, set()
                    self._wanted.clear()
                for topic in sorted(topics):
                    try:
                        self._updates.put(Update(topic, fetch(client, topic)))
                    except Exception:
                        break  # the stream notices a lost service, and everything is read again once it is back
        finally:
            client.close()

    def _reload(self, reader: Client) -> bool:
        """Read everything again; False when the service does not answer (or the follower was stopped)."""
        try:
            data = load(reader)
        except (NotRunning, ClientError):
            return False
        except Exception:
            if not self._stopped.is_set():
                log.exception("reading what the console shows failed")
            return False
        self._after = data.last_event
        self._updates.put(Update("all", data))
        return True

    def _reconnect(self, reader: Client) -> None:
        while not self._stopped.wait(RETRY_SECONDS):
            if self._reload(reader):
                return


def _interrupt(response: httpx2.Response) -> None:
    stream = response.extensions.get("network_stream")
    connection = stream.get_extra_info("socket") if stream is not None else None
    if connection is not None:
        with contextlib.suppress(OSError):
            connection.shutdown(socket.SHUT_RDWR)
    with contextlib.suppress(Exception):
        response.close()
