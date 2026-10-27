"""Whether a workspace's agent reaches its model now (design 0004 §5, revised after approval 2026-10-26).

OpenCode in a workspace's container asks Clank's gateway for the model through the edge (`http://edge:PORT/v1`). When
a part of that way is missing, OpenCode fails at once and its terminal closes with it (seen 2026-10-26: `getaddrinfo
EAI_AGAIN edge`, then `AbortError`), or its first message fails. `check` follows the way in the order a request takes
it and says the first thing wrong, in words, with what fixes it, so a client says it instead: the folder's workspace,
Docker and its container running; the gateway; from inside the container, the gateway's host `edge` resolved and the
gateway answering through it (one `docker exec` of a few lines of Python, `PROBE`, within `EXEC_SECONDS`); then the
model in the agent's slot. `blocked` says OpenCode would fail at once, so a client does not start it then; a model
loading, or none running, is said without blocking: OpenCode starts, and waits for it or fails at its first message. A
fix is a route of the service and its body, which a client posts when the owner asks for it; none when no one step
fixes it. A check that cannot be run (a container without Python, Docker slow to answer) is said as unknown and stops
nothing. Nothing is written.
"""

import json
import ntpath
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from clank.components.gateway.service import Gateway
    from clank.components.runtime.service import Runtime
    from clank.components.workspaces.service import Workspaces
    from clank.kernel.core import Kernel

ROLE = "agent"  # the role OpenCode's requests name (design 0004 §2)
EDGE = "edge"  # the gateway's host as a workspace's container calls it: the edge, on the workspace's network
EXEC_SECONDS = 8.0  # the look from inside the container, `docker exec` and all
PROBE_SECONDS = 3  # the probe's own wait for the gateway's answer
# Run in the container as `python3 -c PROBE HOST PORT`: resolves the host, asks the gateway's /health through it (never
# through the agent's proxy), and prints one JSON line: the step it reached and the error or the status.
PROBE = (
    "import json, socket, sys, urllib.request\n"
    "host, port = sys.argv[1], int(sys.argv[2])\n"
    "try:\n"
    "    socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)\n"
    "except OSError as error:\n"
    "    print(json.dumps({'step': 'resolve', 'error': str(error)}))\n"
    "    raise SystemExit(0)\n"
    "opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))\n"
    "try:\n"
    f"    with opener.open(f'http://{{host}}:{{port}}/health', timeout={PROBE_SECONDS}) as answer:\n"
    "        print(json.dumps({'step': 'answered', 'status': answer.status}))\n"
    "except Exception as error:\n"
    "    print(json.dumps({'step': 'connect', 'error': str(error) or type(error).__name__}))\n"
)


@dataclass
class Found:
    """The checks so far, and the first thing wrong with whether it blocks OpenCode and what fixes it."""

    workspace: str | None
    checks: list[dict[str, Any]] = field(default_factory=list)
    problem: str = ""
    blocked: bool = False
    fix: dict[str, Any] | None = None

    def fine(self, name: str, said: str) -> None:
        self.checks.append({"name": name, "ok": True, "said": said})

    def unknown(self, name: str, said: str) -> None:
        self.checks.append({"name": name, "ok": None, "said": said})

    def wrong(self, name: str, said: str, *, blocked: bool, fix: dict[str, Any] | None = None) -> None:
        self.checks.append({"name": name, "ok": False, "said": said})
        if not self.problem:
            self.problem, self.blocked, self.fix = said, blocked, fix


def fix(label: str, post: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """A fix: what its button says, the route a client posts and its body."""
    return {"label": label, "post": post, "body": body or {}}


def check(kernel: "Kernel", folder: str = "", workspace: str = "") -> dict[str, Any]:
    """The way from a folder's (or a named) workspace's agent to its model, checked now: `ready` when nothing is wrong,
    `blocked` when OpenCode would fail at once, the first `problem` and its `fix`, each check, and how long it took."""
    began = time.monotonic()
    workspaces: Workspaces = kernel.parts["workspaces"]
    records = {record["name"]: str(record["path"]) for record in workspaces.records()}
    wanted = ntpath.normcase(str(Path(folder))) if folder else ""
    name = workspace or next((each for each, path in records.items() if ntpath.normcase(path) == wanted), None)
    found = Found(name if name in records else None)
    path = records.get(name or "", folder)
    opening = fix("Open the workspace", "workspaces/open", {"folder": path}) if path else None
    if found.workspace is None:
        where = folder or workspace
        found.wrong("workspace", f"{where} has no Clank workspace: `clank code` in it gets everything ready",
                    blocked=True, fix=opening)  # fmt: skip
        return _done(found, began)
    _container(found, workspaces, found.workspace, opening)
    gateway: Gateway = kernel.parts["gateway"]
    status = gateway.status()
    if status.get("state") != "running":
        why = f": {status['problem']}" if status.get("problem") else ""
        found.wrong("gateway", f"the gateway does not run{why}", blocked=True, fix=fix("Start the gateway", "gateway/restart"))  # fmt: skip
    else:
        found.fine("gateway", f"the gateway runs on port {status['port']}")
        if not found.blocked:  # a running container to look from
            _edge(found, workspaces, found.workspace, int(status["port"]), path)
    _model(found, kernel)
    return _done(found, began)


def _container(found: Found, workspaces: "Workspaces", name: str, opening: dict[str, Any] | None) -> None:
    """Docker running, and the workspace's container in it."""
    from clank.components.workspaces.service import WorkspaceUnavailable

    docker = workspaces.docker()
    if docker.get("state") != "running":
        found.wrong("workspace", f"Docker is {docker.get('state')}: {name}'s container cannot run", blocked=True,
                    fix=fix("Start Docker", "docker/start"))  # fmt: skip
        return
    try:
        workspaces.container_of(name)
    except WorkspaceUnavailable:
        found.wrong("workspace", f"{name}'s container does not run", blocked=True, fix=opening)
        return
    found.fine("workspace", f"{name}'s container runs")


def _edge(found: Found, workspaces: "Workspaces", name: str, port: int, path: str) -> None:
    """From inside the container: the gateway's host resolved, and the gateway answering through it."""
    from clank.components.workspaces.service import WorkspaceUnavailable

    again = fix("Open the workspace again", "workspaces/open", {"folder": path})
    try:
        answer = workspaces.run_in(name, ["python3", "-c", PROBE, EDGE, str(port)], timeout=EXEC_SECONDS)
    except WorkspaceUnavailable as error:
        found.unknown("edge", f"the way to the gateway from {name}'s container could not be checked: {error}")
        return
    said = _said(answer.output) if answer.ok else None
    if said is None:
        words = (answer.errors or answer.output).strip().splitlines()
        why = words[-1] if words else f"exit {answer.status}"
        found.unknown("edge", f"the way to the gateway from {name}'s container could not be checked: {why}")
        return
    step, error = said.get("step"), str(said.get("error") or "")
    if step == "resolve":
        found.wrong(
            "edge",
            f"{name}'s container cannot find the gateway's host `{EDGE}` ({error}): its network lost the edge, so "
            "OpenCode cannot reach the model",
            blocked=True,
            fix=again,
        )
    elif step == "connect":
        found.wrong("edge", f"the gateway does not answer {name}'s container through the edge ({error})", blocked=True,
                    fix=again)  # fmt: skip
    elif said.get("status") != 200:
        found.wrong("edge", f"the gateway answered {said.get('status')} through the edge", blocked=True, fix=again)
    else:
        found.fine("edge", f"the gateway answers {name}'s container through the edge ({EDGE}:{port})")


def _model(found: Found, kernel: "Kernel") -> None:
    """The model in the slot the agent's requests go to: ready, loading, or none (with the last that worked)."""
    gateway: Gateway = kernel.parts["gateway"]
    runtime: Runtime = kernel.parts["runtime"]
    routes = gateway.routes()
    name = str(routes["roles"].get(ROLE, routes["default_slot"]))
    slot = runtime.state.slot(name)
    title = runtime.title(slot.preset)
    if slot.status == "ready":
        found.fine("model", f"{title} is ready in the {name} slot")
    elif slot.status == "starting":
        found.wrong("model", f"the model is loading: {title} ({slot.reason}); OpenCode's first answer waits for it",
                    blocked=False)  # fmt: skip
    elif slot.status == "stopping":
        found.wrong("model", f"the model is stopping ({slot.reason})", blocked=False)
    elif slot.last_good is not None:
        good = slot.last_good.preset
        loading = fix(f"Load {runtime.title(good)}", f"runtime/slots/{name}/load", {"preset": good})
        found.wrong("model", f"no model runs in the {name} slot ({slot.reason})", blocked=False, fix=loading)
    else:
        found.wrong(
            "model",
            f"no model runs in the {name} slot ({slot.reason}): load one (Clank: Switch the model, or the console's "
            "Models page)",
            blocked=False,
        )


def _said(output: str) -> dict[str, Any] | None:
    """The probe's line, or None when it printed none."""
    lines = output.strip().splitlines()
    try:
        found = json.loads(lines[-1]) if lines else None
    except ValueError:
        return None
    return found if isinstance(found, dict) else None


def _done(found: Found, began: float) -> dict[str, Any]:
    return {
        "workspace": found.workspace,
        "ready": not found.problem,
        "blocked": found.blocked,
        "problem": found.problem,
        "fix": found.fix,
        "checks": found.checks,
        "seconds": round(time.monotonic() - began, 3),
    }
