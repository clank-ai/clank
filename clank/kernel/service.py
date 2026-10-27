"""The Clank service: the one process that is Clank's control plane (decision 0013, design 0002 §1).

`Service.run` takes the lock of its CLANK_HOME (`state/service.lock`, held for its whole life, so a second service for
the same home is refused even while the first is still starting), opens the kernel, takes the API's port (refusing
clearly when another program holds it), and serves the API with Uvicorn. Beside it run the kernel's housekeeping
(questions whose time is up take their default, hand-edited settings files are read again, old events are pruned) and
each component's background task. Once the API answers, the service writes `state/connection.json` and records
`service.started`; when it stops (`clank stop`, the API's stop route, or Ctrl+C), it first closes the event streams
(each tells its client that the service is closing), gives any other response still open two seconds, then records
`service.stopped` and removes the file, so a connected console never holds a stop up. Operations a stop cuts short are
interrupted at the next start (the API's start recovers them).
`start_detached` starts a service in the background, its output in `logs/service.log`; when one already answers it
starts none (`AlreadyRunning`), and when its start fails it quotes only what that service wrote.

The service's own declarations (its settings kind, its event types) are in `clank/kernel/service_kinds.py`.
"""

import contextlib
import logging
import os
import socket
import subprocess
import sys
import time
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

import anyio
import anyio.to_thread
import httpx2
import psutil
import uvicorn

from clank import __version__
from clank.kernel.accepting import keep_accepting
from clank.kernel.access import Connection, local_token, read_connection, remove_connection, write_connection
from clank.kernel.clock import Clock, SystemClock
from clank.kernel.components import Component
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import CLANK
from clank.kernel.home import Home
from clank.kernel.locks import LockHeld, hold
from clank.kernel.processes import background_flags
from clank.kernel.service_kinds import ServiceSettings

log = logging.getLogger(__name__)
HOUSEKEEPING_SECONDS = 2.0
PRUNING_SECONDS = 3600.0
CLOSING_SECONDS = 2
LOCK = "service.lock"  # in state/: held by the service for its whole life, so one service runs per home
PID = "service.pid"  # in state/: the lock's holder and its start, so one that holds it silent can be ended
SILENT_SECONDS = 60.0  # a lock held this long with no connection written: its service does not answer


def server_config(app: Any, host: str, port: int) -> uvicorn.Config:
    """How Uvicorn serves the API: on the service's address, quietly, closing what is still open soon after a stop."""
    return uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
        timeout_graceful_shutdown=CLOSING_SECONDS,
    )


class ApiServer(uvicorn.Server):
    """Uvicorn serving the API as the service does (`server_config`). Uvicorn lets the responses still open finish
    before the application hears of a stop, so the server itself closes the event streams first: a follower hears
    `closing` at once, and nothing is left for the grace period to cut."""

    def __init__(self, app: Any, host: str, port: int) -> None:
        super().__init__(server_config(app, host, port))
        self.app = app

    async def shutdown(self, sockets: list[socket.socket] | None = None) -> None:
        """Close the event streams, then stop as Uvicorn does."""
        from clank.kernel.api import end_streams  # as in `Service._serve_api`: the commands do not load the API

        end_streams(self.app)
        await super().shutdown(sockets)


class ServiceError(Exception):
    """Why the service cannot start or be reached."""


class AlreadyRunning(ServiceError):
    """A service already answers for this CLANK_HOME: its connection."""

    def __init__(self, connection: Connection, home: Home) -> None:
        super().__init__(
            f"a Clank service already runs for {home.root} at {connection.url} (process {connection.pid}); "
            "stop it with `clank stop`"
        )
        self.connection = connection


def answering(home: Home) -> Connection | None:
    """The service that answers for this CLANK_HOME, if one does; a connection file no service answers is removed."""
    existing = read_connection(home)
    if existing is None:
        return None
    try:
        answer = httpx2.get(
            f"{existing.url}/api/v1/service", headers={"Authorization": f"Bearer {local_token(home)}"}, timeout=3
        )
    except httpx2.TransportError:
        remove_connection(home)
        return None
    return existing if answer.status_code == 200 else None


async def housekeep(kernel: Kernel) -> None:
    """One round of the kernel's housekeeping: expire questions whose time is up; read edited settings files again."""
    await anyio.to_thread.run_sync(kernel.questions.expire_due)
    await anyio.to_thread.run_sync(kernel.settings.reload_changed)


async def prune(kernel: Kernel, days: int) -> int:
    """Remove the events older than the history the service keeps."""
    return await anyio.to_thread.run_sync(kernel.events.prune, kernel.clock.now() - timedelta(days=days))


class Service:
    """The Clank service for one CLANK_HOME."""

    def __init__(
        self, home: Home, components: Sequence[Component], *, clock: Clock | None = None, port: int | None = None
    ) -> None:
        self._home = home
        self._components = components
        self._clock = clock or SystemClock()
        self._port = port

    def run(self) -> None:
        """Run until stopped; raises `ServiceError` when it cannot start. On Windows a client that drops its connection
        while it is accepted no longer closes the API's socket (`accepting.py`)."""
        keep_accepting()
        if not logging.getLogger().handlers:  # each line of the service's log with its time (its own run decides)
            logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
        anyio.run(self._serve)

    async def _serve(self) -> None:
        with contextlib.ExitStack() as held:
            try:
                held.enter_context(hold(self._home.state / LOCK))
            except LockHeld:
                raise ServiceError(self.held_by_another()) from None
            write_holder(self._home, os.getpid())
            held.callback(lambda: (self._home.state / PID).unlink(missing_ok=True))
            self._refuse_a_second_service()
            kernel = open_kernel(self._home, self._clock, self._components)
            try:
                settings = ServiceSettings.model_validate(kernel.settings.get("service", "service").record.model_dump())
                port = self._port or settings.port
                self._refuse_a_taken_port(settings.host, port)
                await self._serve_api(kernel, settings, port)
            finally:
                kernel.close()

    def held_by_another(self, now: datetime | None = None) -> str:
        """Why this service cannot take its home's lock: another starts, runs, or holds it without answering (its
        lock held over `SILENT_SECONDS` with no connection written: `clank stop` ends it)."""
        existing = read_connection(self._home)
        found = holder(self._home)
        if existing is None and found is not None:
            pid, started = found
            if ((now or datetime.now(UTC)) - started).total_seconds() > SILENT_SECONDS:
                return (
                    f"a Clank service holds {self._home.root} (process {pid}, since {started.astimezone():%H:%M}) but "
                    "does not answer: `clank stop` ends it, then `clank serve` starts one"
                )
        if existing is None:
            return f"a Clank service is starting for {self._home.root}; wait a moment, then `clank status`"
        return (
            f"a Clank service already runs for {self._home.root} at {existing.url} (process {existing.pid}); "
            "stop it with `clank stop`"
        )

    async def _serve_api(self, kernel: Kernel, settings: ServiceSettings, port: int) -> None:
        from clank.kernel.api import create_app  # the API module needs the kernel built first; imported here once

        servers: list[ApiServer] = []
        url = f"http://{settings.host}:{port}"

        def stop() -> None:
            for server in servers:
                server.should_exit = True

        async def announce() -> None:
            while not servers or not servers[0].started:
                await anyio.sleep(0.05)
            write_connection(self._home, Connection(url, os.getpid(), self._clock.now(), __version__))
            kernel.events.record(
                "service.started",
                summary=f"service started ({__version__}) on {url}",
                actor=CLANK,
                data={"url": url, "version": __version__, "pid": os.getpid()},
            )
            print(f"Clank service {__version__} on {url}; stop it with `clank stop` or Ctrl+C", flush=True)

        async def keep_house() -> None:
            last_pruning = 0.0
            while True:
                try:
                    await housekeep(kernel)
                    if time.monotonic() - last_pruning > PRUNING_SECONDS:
                        await prune(kernel, settings.events_kept_days)
                        last_pruning = time.monotonic()
                except Exception:
                    log.exception("the service's housekeeping failed")
                await anyio.sleep(HOUSEKEEPING_SECONDS)

        background = [announce, keep_house]
        background += [part.run for part in kernel.parts.values() if callable(getattr(part, "run", None))]
        app = create_app(
            kernel,
            token=local_token(self._home),
            port=port,
            stop=stop,
            background=background,
            started=self._clock.now(),
        )
        server = ApiServer(app, settings.host, port)
        servers.append(server)
        try:
            await server.serve()
        finally:
            if not remove_connection(self._home):  # a client holds it open: the next one finds no service there
                log.warning("the connection file is held open by another program: left, naming this stopped service")
            kernel.events.record("service.stopped", summary="service stopped", actor=CLANK)

    def _refuse_a_second_service(self) -> None:
        existing = answering(self._home)
        if existing is not None:
            raise AlreadyRunning(existing, self._home)

    def _refuse_a_taken_port(self, host: str, port: int) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind((host, port))
            except OSError as error:
                raise ServiceError(
                    f'port {port} is in use by {_holder(port)}; choose another "port" in '
                    f"{self._home.config / 'service.json'}, or stop that program"
                ) from error


def _holder(port: int) -> str:
    try:
        for connection in psutil.net_connections(kind="tcp"):
            listening = connection.laddr and connection.laddr.port == port and connection.status == psutil.CONN_LISTEN
            if listening and connection.pid:
                return f"{psutil.Process(connection.pid).name()} (process {connection.pid})"
    except (psutil.Error, OSError):
        pass
    return "another program"


def started_at(pid: int) -> datetime:
    """When a running process started, as the system says."""
    return datetime.fromtimestamp(psutil.Process(pid).create_time(), UTC)


def write_holder(home: Home, pid: int) -> None:
    """Say which process holds the service's lock, with its start (a number the system may give another later)."""
    (home.state / PID).write_text(f"{pid} {psutil.Process(pid).create_time()}", encoding="utf-8")


def holder(home: Home) -> tuple[int, datetime] | None:
    """The process that holds the service's lock as it said, with its start; None when it said none, when that process
    no longer runs, or when another took its number since (its start differs)."""
    try:
        pid_text, created_text = (home.state / PID).read_text(encoding="utf-8").split()
        pid, created = int(pid_text), float(created_text)
        if abs(psutil.Process(pid).create_time() - created) > 1.0:
            return None
    except (OSError, ValueError, psutil.Error):
        return None
    return pid, datetime.fromtimestamp(created, UTC)


def end_silent(home: Home) -> int | None:
    """End a service that holds its home's lock but does not answer (`clank stop`, after the API did not answer): the
    process it named, and the files it left behind; that process, or None when none holds the lock. Only that process
    is ended: the gateway it may have started runs on, and the bridges it ran end with their input."""
    found = holder(home)
    if found is None:
        return None
    pid, _ = found
    try:
        process = psutil.Process(pid)
        process.terminate()
        process.wait(timeout=10)
    except psutil.TimeoutExpired:
        process.kill()
    except psutil.Error:
        pass
    existing = read_connection(home)
    if existing is not None and existing.pid == pid:
        remove_connection(home)
    (home.state / PID).unlink(missing_ok=True)
    return pid


def start_detached(home: Home, port: int | None = None, timeout: float = 30) -> Connection:
    """Start the service in the background and wait until it answers; its output goes to `logs/service.log`. A service
    that already answers is refused at once (`AlreadyRunning`), and a start that fails says only what its own service
    wrote, never the lines another service left in the shared log."""
    home.ensure()
    existing = answering(home)
    if existing is not None:
        raise AlreadyRunning(existing, home)
    arguments = [sys.executable, "-m", "clank", "serve", *(["--port", str(port)] if port else [])]
    environment = {**os.environ, "CLANK_HOME": str(home.root)}
    log_file = home.logs / "service.log"
    offset = log_file.stat().st_size if log_file.exists() else 0
    output = log_file.open("a", encoding="utf-8")
    process = subprocess.Popen(
        arguments,
        env=environment,
        cwd=str(home.root),  # never the current folder: `python -m clank` would read a checkout of Clank found there
        stdin=subprocess.DEVNULL,
        stdout=output,
        stderr=subprocess.STDOUT,
        creationflags=background_flags(),
        start_new_session=sys.platform != "win32",
        close_fds=True,
    )
    output.close()
    launched = datetime.now(UTC) - timedelta(seconds=2)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        connection = read_connection(home)
        if connection is not None and connection.started >= launched:
            return connection
        if process.poll() is not None:
            with log_file.open("rb") as written:
                written.seek(offset)
                tail = written.read().decode("utf-8", errors="replace").strip().splitlines()[-5:]
            raise ServiceError("the service did not start: " + " / ".join(tail))
        time.sleep(0.1)
    raise ServiceError(f"the service did not answer within {timeout:.0f} seconds; see {home.logs / 'service.log'}")
