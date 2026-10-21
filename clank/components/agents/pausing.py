"""The Guide's pause in the service (design 0012 §9.4, §11 step 11, decision 0055): **pause after this step** (`p`).

The Guide acts on the root session (design 0012 §3), so `pause` and `resume` find the root of the session they are
given, up the parents the workspace's watcher heard, and set its pause in the gateway (the gateway's `holds`, through
the gateway component's `pause` and `resume`, with the service's token: decision 0084). From then on the request in
flight finishes, OpenCode runs that step's calls, and the session's next model request, and its subagents', is held
until it is resumed. Each pause and resume is an `agents.acted` event with who did it: the owner from the console or the
phone, or a Watch for rule (through `guide.Ruled`, as the rule). A pause the gateway cannot set (it does not run, or
refused) is refused here with its reason (`PauseError`), and nothing is sent.

`state` reads the pause from the gateway each time it is asked, never guessed: **pausing after this step** (paused,
nothing held yet), **held** (a request waits, with its timer: the longest held), or **resumed** (the last resume Clank
made, kept in memory as the flows are, decision 0049); None when never paused. `action` is the pause as the Guide offers
it, in the shape of its other actions (design 0012 §9.1): its key, whether it can run and why not, what it does in
words and as the exact call to the gateway, its cost (nothing while held: nothing is read again), that it asks first,
and its state. A message sent to a held session closes the request it held before the message was sent
(`Sessions.send`), so the note is read; the request that carries it is held until the owner resumes. A gateway from
before pausing, still running, refuses each of these with words that say to restart it, never a pause that holds
nothing.
"""

import json
import threading
from typing import TYPE_CHECKING, Any

from clank.kernel.clock import to_text
from clank.kernel.events import Actor

if TYPE_CHECKING:
    from clank.components.agents.sessions import Sessions
    from clank.components.gateway.service import Gateway
    from clank.kernel.core import Kernel

KEY = "p"
TITLES = {False: "Pause", True: "Resume"}  # the Guide panel's; §9.1 names it "Pause after this step"
BRIEFS = {False: "after this step: its next request waits in the gateway", True: "the held request goes to the model"}
DEPTH = 32  # parents walked up at most
COST = {"tokens": 0, "seconds": 0.0, "words": "nothing while held: nothing is read again"}
PAUSING = "pausing after this step"
HELD = "held"
RESUMED = "resumed"
Key = tuple[str, str]


class PauseError(Exception):
    """A pause or a resume that cannot run now, and why."""


class Pausing:
    """The pauses Clank sets in the gateway, on root sessions, and the last resume of each."""

    def __init__(self, kernel: "Kernel", sessions: "Sessions") -> None:
        self.kernel, self.sessions = kernel, sessions
        self._lock = threading.Lock()
        self._resumed: dict[Key, dict[str, Any]] = {}

    def root(self, workspace: str, session: str) -> str:
        """The root of a session: up its parents, as the workspace's watcher heard them."""
        parents = {str(each["session"]): str(each.get("parent") or "") for each in self.sessions.seen(workspace)}
        found = session
        for _ in range(DEPTH):
            parent = parents.get(found, "")
            if not parent:
                return found
            found = parent
        return found

    def pause(self, workspace: str, session: str, *, actor: Actor) -> dict[str, Any]:
        """Pause the session's root after its step: its next model requests, and its subagents', are held."""
        root = self.root(workspace, session)
        from clank.components.gateway.service import HoldError

        try:
            found = self._gateway().pause(root, actor.describe())
        except HoldError as error:
            raise PauseError(f"Pause cannot run now: {error}") from error
        with self._lock:
            self._resumed.pop((workspace, root), None)
        if not found.get("already"):
            detail = "its next requests held after this step"
            self.sessions.acted(workspace, self.sessions.runs(workspace, root), root, "pause", detail, actor)
        return {"session": root, "already": bool(found.get("already")), "state": self.state(workspace, root)["state"]}

    def resume(self, workspace: str, session: str, *, actor: Actor) -> dict[str, Any]:
        """Resume the session's root: the requests it holds go to the model."""
        root = self.root(workspace, session)
        from clank.components.gateway.service import HoldError

        try:
            found = self._gateway().resume(root)
        except HoldError as error:
            raise PauseError(f"Resume cannot run now: {error}") from error
        if found is None:
            raise PauseError(f"{root} is not paused")
        went = int(found.get("held") or 0)
        with self._lock:
            self._resumed[(workspace, root)] = {"state": RESUMED, "time": to_text(self.kernel.clock.now()),
                                                "by": actor.describe(), "went": went}  # fmt: skip
        detail = f"{went} request{'' if went == 1 else 's'} held went on" if went else ""
        self.sessions.acted(workspace, self.sessions.runs(workspace, root), root, "resume", detail, actor)
        return {"session": root, "went": went, "state": self.state(workspace, root)["state"]}

    def state(self, workspace: str, session: str) -> dict[str, Any]:
        """The pause of the session's root, as the gateway says it now: its state (None when never paused), and why the
        gateway cannot say (`problem`)."""
        root = self.root(workspace, session)
        holds = self._gateway().holds()
        pause = next((each for each in holds.get("pauses") or [] if each.get("session") == root), None)
        state: dict[str, Any] | None = None
        if pause is not None:
            held = list(pause.get("held") or [])
            seconds = max((float(each.get("seconds") or 0) for each in held), default=None)
            state = {"state": HELD if held else PAUSING, "time": pause.get("since") or "", "by": pause.get("by") or "",
                     "why": "", "step": None, "seconds": seconds, "held": held}  # fmt: skip
        else:
            with self._lock:
                resumed = self._resumed.get((workspace, root))
            if resumed is not None:
                state = {"state": RESUMED, "time": resumed["time"], "by": resumed["by"], "why": "", "step": None,
                         "seconds": None, "held": []}  # fmt: skip
        problem = str(holds.get("problem") or "")
        return {"session": root, "paused": pause is not None, "state": state, "problem": problem}

    def action(self, workspace: str, session: str) -> dict[str, Any]:
        """The pause as the Guide offers it (design 0012 §9.1): `p`, pause or resume as the session stands."""
        found = self.state(workspace, session)
        root, paused = found["session"], found["paused"]
        if paused:
            does = ("resumes the session: the request it holds goes to the model, and its next requests are no longer "
                    "held")  # fmt: skip
            calls = [f"DELETE /holds/{root} (the gateway's)"]
        else:
            does = (
                "the request in flight finishes and OpenCode runs that step's calls; then the next model "
                "request of the session, and of its subagents, waits in the gateway until you resume (p again)"
            )
            calls = [f"PUT /holds/{root} {json.dumps({'by': '<you>'})} (the gateway's)"]
        return {"action": "pause", "key": KEY, "title": TITLES[paused], "can": not found["problem"],
                "why": found["problem"], "brief": BRIEFS[paused], "does": does, "calls": calls, "cost": dict(COST),
                "confirm": True, "state": found["state"], "session": root, "paused": paused}  # fmt: skip

    def _gateway(self) -> "Gateway":
        found: Gateway = self.kernel.parts["gateway"]
        return found
