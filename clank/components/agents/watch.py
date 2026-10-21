"""The watchers (design 0007 §4): one for each running workspace container, the bridge's `watch` kept open with `docker
exec`, its lines handed to the review (`review.py`) as they come.

`keep` starts and ends them from Docker's last reading (the workspaces' background check keeps it current, so watching
costs no extra call to Docker): a container that runs gets a watcher, one that stopped or was made again loses its
own. A watcher that ends while its container runs is started again, a little later each time. A container whose image
has no `watch` (from before design 0007) is said to be so (`state`) and not tried again until it is made again; its
agent asks in its terminal meanwhile. A watcher ends when its input is closed: the service closes them all when it
stops, and the bridge ends one a stopped service left behind (`replace_older`).
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
OLDER = (
    "its container runs an older sandbox image: reopen the workspace (Workspaces, F6: x, then o) to review changes in "
    "VS Code; until then the agent asks in its terminal"
)
Heard = Callable[[str, dict[str, Any]], None]
Spawn = Callable[[str], "subprocess.Popen[bytes]"]


class Watcher:
    """The bridge's `watch` in one workspace's container, read in a thread of its own."""

    def __init__(self, workspace: str, container: str, process: "subprocess.Popen[bytes]", heard: Heard) -> None:
        self.workspace, self.container, self.process = workspace, container, process
        self.heard = heard
        self.synced = False
        self.problem = ""
        self.ended: float | None = None
        self._telling = threading.Lock()
        self.thread = threading.Thread(target=self._read, name=f"clank-watch-{workspace}", daemon=True)
        self.thread.start()

    def alive(self) -> bool:
        """Whether its process still runs."""
        return self.ended is None

    def stop(self) -> None:
        """Close its input, which ends the watch in the container; end the process if it lingers."""
        try:
            with self._telling:
                if self.process.stdin is not None:
                    self.process.stdin.close()
            self.process.wait(timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            self.process.kill()

    def tell(self, line: dict[str, Any]) -> None:
        """A line on the watch's input (the sessions shown); nothing when the watch has ended."""
        try:
            with self._telling:
                if self.process.stdin is not None:
                    self.process.stdin.write((json.dumps(line) + "\n").encode())
                    self.process.stdin.flush()
        except (OSError, ValueError):
            pass

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
        if line.get("ok") is False:  # a bridge without `watch`
            self.problem = OLDER if "no action" in str(line.get("error")) else str(line.get("error"))
            return
        if line.get("type") == "synced":
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
                except OSError as error:
                    log.warning("the watcher of %s did not start: %s", workspace, error)
                    continue
                if workspace in self._shown:
                    self._watching[workspace].tell({"shown": self._shown[workspace]})

    def show(self, workspace: str, sessions: list[str]) -> None:
        """Name the sessions whose text the workspace's watch says as it is written (design 0012 §6.1); told again
        to a watch started again."""
        with self._lock:
            self._shown[workspace] = sorted(set(sessions))
            watcher = self._watching.get(workspace)
        if watcher is not None:
            watcher.tell({"shown": self._shown[workspace]})

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
