"""The watchers (design 0007 §4): one for each running workspace container, the bridge's `watch` kept open with `docker
exec`, its lines handed to the review (`review.py`) as they come.

`keep` starts and ends them from Docker's last reading (the workspaces' background check keeps it current, so watching
costs no extra call to Docker): a container that runs gets a watcher, one that stopped or was made again loses its
own. A watcher that ends while its container runs is started again, a little later each time. A container whose image
has no `watch` (from before design 0007) is said to be so (`state`) and not tried again until it is made again; its
agent asks in its terminal meanwhile. A workspace whose watcher cannot start (its container no longer runs, though
Docker's last reading said it did) is said once in the log and leaves the others watched. A watcher ends when its input
is closed: the service closes them all when it stops, and the bridge ends one a stopped service left behind
(`replace_older`).

The watcher is also the channel for the actions the owner waits on (design 0023 §4, decision 0140): `request` writes
`{"id", "action", "args", "body"}` on its input and waits for the bridge's `answer` line with that id, which the
review never hears. Once the watch synced, the watcher asks it `hello`: a bridge from before the channel (copied into
the image of a container made before Clank's programs were mounted, decision 0142) reads only `shown` and never
answers, so once `PROBE_SECONDS` passed without an answer its requests raise `NoRequests` at once and go through a
process of their own, the watcher left as it is (a request waits for the hello's answer while it may still come), and
the log says once that the workspace is to be opened again. The bridge answers each request within its own deadline,
in words when OpenCode does not answer, so a request still unanswered after `REQUEST_SECONDS` means the watch itself
no longer answers: the watcher is ended, so `keep` starts it again, and `Unanswered` tells the caller to send the
request through a process of its own; so does `NoChannel` when no watcher is alive and synced for the workspace.
"""

import json
import logging
import subprocess
import threading
import time
from collections.abc import Callable
from typing import IO, TYPE_CHECKING, Any

import anyio

from clank.kernel.processes import background_flags

if TYPE_CHECKING:
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel

log = logging.getLogger(__name__)
CHECK_SECONDS = 3.0
RETRY_SECONDS = (2.0, 5.0, 15.0, 30.0, 60.0)  # after a watcher's 1st, 2nd, ... end while its container runs
REQUEST_SECONDS = 10.0  # a request on the channel waits this long for its answer (design 0023 §4); the bridge answers
# within its own deadline, below this (its ANSWER_SECONDS), so a request unanswered here means the watch itself is stuck
PROBE_SECONDS = 5.0  # how long a watch has to answer its hello before its bridge is taken to read no request
OLDER = (
    "its container runs an older sandbox image: reopen the workspace (Workspaces, F6: x, then o) to review changes in "
    "VS Code; until then the agent asks in its terminal"
)
NO_REQUESTS = (
    "{workspace}'s container runs a bridge from before its request channel (the container was made before Clank's "
    "programs were mounted, decision 0142): its requests go through a process of their own, about a second each; stop "
    "the workspace and open it again (Workspaces, F6: x, then o) to have them answered at once"
)
Heard = Callable[[str, dict[str, Any]], None]
Spawn = Callable[[str], "subprocess.Popen[bytes]"]


class NoChannel(Exception):
    """No watcher alive and synced carries the workspace's requests now: a process of its own does."""


class NoRequests(NoChannel):
    """The watcher's bridge reads no request (it never answered its hello): a process of its own does each one."""


class Unanswered(Exception):
    """The watcher did not answer the request in time: it is ended, and a process of its own does the request."""


class _Pending:
    """A request waiting for its answer."""

    def __init__(self) -> None:
        self.done = threading.Event()
        self.answer: dict[str, Any] = {}


class Watcher:
    """The bridge's `watch` in one workspace's container, read in a thread of its own."""

    def __init__(self, workspace: str, container: str, process: "subprocess.Popen[bytes]", heard: Heard) -> None:
        self.workspace, self.container, self.process = workspace, container, process
        self.heard = heard
        self.synced = False
        self.problem = ""
        self.ended: float | None = None
        self._telling = threading.Lock()
        self._pending: dict[str, _Pending] = {}  # each request waiting, by its id
        self._requests = 0
        self._hello = ""  # the id of the hello asked once the watch synced
        self._hello_at = 0.0  # when it was asked
        self._answered = threading.Event()  # set once the bridge answered it: it reads requests
        self.thread = threading.Thread(target=self._read, name=f"clank-watch-{workspace}", daemon=True)
        self.thread.start()

    def alive(self) -> bool:
        """Whether its process still runs."""
        return self.ended is None

    def stop(self) -> None:
        """Close its input, which ends the watch in the container; end the process if it lingers. It is ended from
        here on, whatever its reader still reads."""
        try:
            with self._telling:
                if self.process.stdin is not None:
                    self.process.stdin.close()
            self.process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            self.process.kill()
        if self.ended is None:
            self.ended = time.monotonic()
        self.synced = False

    def tell(self, line: dict[str, Any]) -> bool:
        """A line on the watch's input (the sessions shown, a request); whether it was written (not once the watch
        has ended)."""
        try:
            with self._telling:
                if self.process.stdin is None:
                    return False
                self.process.stdin.write((json.dumps(line) + "\n").encode())
                self.process.stdin.flush()
                return True
        except (OSError, ValueError):
            return False

    def carries(self) -> bool:
        """Whether its bridge reads requests: it answered the hello asked once the watch synced (a refusal is an
        answer too); while that answer may still come (`PROBE_SECONDS`), it is waited for."""
        if not self._answered.is_set() and self._hello_at:
            self._answered.wait(max(0.0, self._hello_at + PROBE_SECONDS - time.monotonic()))
        return self._answered.is_set()

    def request(self, action: str, args: list[str], body: dict[str, Any] | None, timeout: float) -> dict[str, Any]:
        """Do a bridge action through the watch (design 0023 §4): its answer as a one-off run would print it (`ok`
        false with the bridge's words when it refused). `NoChannel` when the watch is not alive and synced, when its
        input cannot be written, or when asked from its own reader thread (which reads the answers: a line heard
        that asks goes through a process of its own); `NoRequests` when its bridge reads no request; `Unanswered`
        after `timeout` seconds."""
        if not self.alive() or not self.synced:
            raise NoChannel(f"{self.workspace}'s watcher is not ready to carry requests")
        if threading.current_thread() is self.thread:  # a line heard (the review, a listener) asks: the answer
            raise NoChannel(f"{self.workspace}'s watcher cannot wait for itself")  # would be read by this very thread
        if not self.carries():
            raise NoRequests(f"{self.workspace}'s bridge reads no request: it never answered its hello")
        waiting = _Pending()
        with self._telling:
            self._requests += 1
            id = f"{self._requests}"
            self._pending[id] = waiting
        if not self.tell({"id": id, "action": action, "args": args, "body": body or {}}):
            self._pending.pop(id, None)
            raise NoChannel(f"{self.workspace}'s watcher takes no request: its input is closed")
        if not waiting.done.wait(timeout):
            self._pending.pop(id, None)
            raise Unanswered(f"{self.workspace}'s watcher did not answer {action} within {timeout:g} seconds")
        return waiting.answer

    def _ask_hello(self) -> None:
        """Ask the bridge `hello` (its answer says it reads requests), before the watch is taken to be synced."""
        with self._telling:
            self._requests += 1
            self._hello = f"{self._requests}"
        self._hello_at = time.monotonic()
        self.tell({"id": self._hello, "action": "hello", "args": [], "body": {}})

    def _read(self) -> None:
        self.heard(self.workspace, {"type": "started"})
        stdout: IO[bytes] | None = self.process.stdout
        try:
            for raw in stdout or []:
                self._line(raw)
        except (OSError, ValueError):
            pass
        finally:
            self.process.wait()
            if stdout is not None:
                stdout.close()
            self.ended = time.monotonic()
            self.synced = False

    def _line(self, raw: bytes) -> None:
        try:
            line = json.loads(raw)
        except ValueError:
            if b"bridge.py" in raw:  # an image without the bridge at all
                self.problem = OLDER
            return
        if not isinstance(line, dict):
            return
        if line.get("type") == "answer":  # a request's answer: for the one waiting, never for the review
            id = str(line.get("id"))
            if self._hello and id == self._hello:
                self._answered.set()  # whatever it says (an older bridge has no hello: its refusal is an answer)
                return
            waiting = self._pending.pop(id, None)
            if waiting is not None:
                waiting.answer = line
                waiting.done.set()
            return
        if line.get("ok") is False:  # a bridge without `watch`
            self.problem = OLDER if "no action" in str(line.get("error")) else str(line.get("error"))
            return
        if line.get("type") == "synced":
            self._ask_hello()
            self.synced = True
        try:
            self.heard(self.workspace, line)
        except Exception:
            log.exception("the review failed on a line from %s's watcher", self.workspace)


class Watchers:
    """A watcher for each running workspace container."""

    def __init__(self, kernel: "Kernel", heard: Heard, spawn: Spawn | None = None) -> None:
        self.kernel = kernel
        self.heard = heard
        self.spawn = spawn or self._spawn
        self._lock = threading.Lock()
        self._watching: dict[str, Watcher] = {}
        self._ends: dict[str, int] = {}  # how often each workspace's watcher ended while its container ran
        self._older: dict[str, str] = {}  # a workspace whose container cannot be watched, by that container's id
        self._shown: dict[str, list[str]] = {}  # the sessions whose text each workspace's watch says as it is written
        self._followed: dict[str, list[str]] = {}  # the sessions whose parts each watch says whole (design 0023 §2)
        self._unstarted: dict[str, str] = {}  # a workspace whose watcher could not start, said once: its container
        self._told: set[str] = set()  # the containers whose bridge was said to read no request

    async def run(self) -> None:
        """Keep the watchers while the service runs; close them all when it stops."""
        try:
            while True:
                try:
                    await anyio.to_thread.run_sync(self.keep)
                except Exception:
                    log.exception("keeping the watchers failed")
                await anyio.sleep(CHECK_SECONDS)
        finally:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(self.stop)

    def keep(self) -> None:
        """A watcher for each running workspace container (Docker's last reading), none for any other."""
        workspaces: Workspaces = self.kernel.parts["workspaces"]
        running = workspaces.running()
        with self._lock:
            for workspace, watcher in list(self._watching.items()):
                if running.get(workspace) != watcher.container:
                    watcher.stop()
                    del self._watching[workspace]
                    self._ends.pop(workspace, None)
            for workspace, container in running.items():
                if self._older.get(workspace) == container:
                    continue
                kept = self._watching.get(workspace)
                if kept is not None and not self._due(kept):
                    continue
                if kept is not None:
                    if kept.problem == OLDER:
                        self._older[workspace] = container
                        continue
                    self._ends[workspace] = self._ends.get(workspace, 0) + 1
                self._older.pop(workspace, None)
                try:
                    self._watching[workspace] = Watcher(workspace, container, self.spawn(workspace), self.heard)
                except Exception as error:  # its container ended since Docker's last reading, Docker refused: the
                    if self._unstarted.get(workspace) != container:  # others are watched all the same
                        log.warning("the watcher of %s did not start: %s", workspace, error)
                        self._unstarted[workspace] = container
                    continue
                self._unstarted.pop(workspace, None)
                if workspace in self._shown:
                    self._watching[workspace].tell({"shown": self._shown[workspace]})
                if workspace in self._followed:
                    self._watching[workspace].tell({"followed": self._followed[workspace]})

    def show(self, workspace: str, sessions: list[str]) -> None:
        """Name the sessions whose text the workspace's watch says as it is written (design 0012 §6.1); told again
        to a watch started again."""
        with self._lock:
            self._shown[workspace] = sorted(set(sessions))
            watcher = self._watching.get(workspace)
        if watcher is not None:
            watcher.tell({"shown": self._shown[workspace]})

    def follow(self, workspace: str, sessions: list[str]) -> None:
        """Name the sessions whose parts the workspace's watch says whole, with their text as it is written (design
        0023 §2: the mirror keeps them); told again to a watch started again."""
        with self._lock:
            self._followed[workspace] = sorted(set(sessions))
            watcher = self._watching.get(workspace)
        if watcher is not None:
            watcher.tell({"followed": self._followed[workspace]})

    def request(
        self, workspace: str, action: str, args: list[str], body: dict[str, Any] | None, timeout: float | None = None
    ) -> dict[str, Any]:
        """Do a bridge action through the workspace's watcher (design 0023 §4), waiting `REQUEST_SECONDS` unless
        another wait is given; the answer as the bridge prints it. `NoChannel` without a watcher alive and synced, or
        whose bridge reads no request (`NoRequests`, said once in the log for its container); `Unanswered` when it did
        not answer in time, the watcher ended so that `keep` starts it again: the caller sends the request through a
        process of its own either way."""
        with self._lock:
            watcher = self._watching.get(workspace)
        if watcher is None:
            raise NoChannel(f"{workspace} has no watcher")
        try:
            return watcher.request(action, args, body, REQUEST_SECONDS if timeout is None else timeout)
        except NoRequests:
            with self._lock:
                told = watcher.container in self._told
                self._told.add(watcher.container)
            if not told:
                log.warning(NO_REQUESTS.format(workspace=workspace))
            raise
        except Unanswered as error:
            log.warning(
                "%s: the watcher is ended and started again; the request goes through a process of its own", error
            )
            watcher.stop()
            raise

    def state(self, workspace: str) -> dict[str, Any]:
        """Whether the workspace's agents are watched now, and why not when they cannot be."""
        with self._lock:
            watcher = self._watching.get(workspace)
            if workspace in self._older:
                return {"watching": False, "problem": OLDER}
            if watcher is None:
                return {"watching": False, "problem": ""}
            return {"watching": watcher.alive() and watcher.synced, "problem": watcher.problem}

    def stop(self) -> None:
        """End every watcher."""
        with self._lock:
            watching, self._watching = list(self._watching.values()), {}
        for watcher in watching:
            watcher.stop()

    def _due(self, watcher: Watcher) -> bool:
        """Whether a watcher that ended is due to be started again."""
        if watcher.ended is None:
            return False
        if watcher.problem == OLDER:
            return True
        wait = RETRY_SECONDS[min(self._ends.get(watcher.workspace, 0), len(RETRY_SECONDS) - 1)]
        return time.monotonic() - watcher.ended >= wait

    def _spawn(self, workspace: str) -> "subprocess.Popen[bytes]":
        from clank.components.workspaces.service import BRIDGE_PROGRAM

        workspaces: Workspaces = self.kernel.parts["workspaces"]
        argv = workspaces.exec_argv(workspace, ["python3", BRIDGE_PROGRAM, "watch"], {}, terminal=False)
        return subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            creationflags=background_flags(),
        )  # fmt: skip
