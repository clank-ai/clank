"""The edge on every workspace's network (design 0004 §3, design 0024 §2; revised 2026-10-26). Its program is
`image/edge.py`; this is how Clank keeps its container.

The edge is one container all workspaces share (`sandbox.edge_spec`): on the network that reaches the host, and on each
workspace's own internal network as `edge`, where the workspace's agent finds the gateway and the proxy. Docker keeps a
container's place on a network with the container, so an edge made again is on its first network only: on 2026-10-26
the edge was made again when the proxy's port was added, joined only the network of the workspace being opened, and the
four that ran lost their way to the model (`getaddrinfo EAI_AGAIN edge` in OpenCode, which then gave up). So whatever
asks for the edge goes through `Edge.ready`, one at a time:

- It makes the edge when it is not there (only when Clank's sandbox image is built: a `docker run` of a missing image
  would download it), starts it when it is stopped, and makes it again when it forwards other ports than the gateway's
  and the proxy's (a running one only when asked to: an opening and an agent's start do, the background check never,
  since that cuts every request in flight) or when it cannot start because a network it was on is gone (made again
  since: Docker keeps the network's id).
- Then it joins the network of the workspace it is asked for, of the others it is given, and, whenever it made or
  started the edge, of every workspace whose container there is, running or stopped.
- What it repaired for a workspace whose container ran (it could not reach the model, and now can) is said in the
  service's log and as the event `workspaces.edge_repaired`, in Clank's words, with what found it.

`state` says from a reading how a workspace's container reaches the edge: `on`; `cut`, the edge not running on its
network; `stale`, the edge forwarding other ports than the gateway's and the proxy's (made again by an opening or an
agent's start); `proxy`, its container told another proxy port than the one the edge forwards (it reaches the model,
not the internet, until it is stopped and opened again); None while its container does not run. `said` puts it in
words, with what Clank does about it. The service's check of Docker (`check`) repairs the workspaces that are cut from
the reading it takes anyway, so it asks Docker nothing more while none is; an edge it could not put right is said once
and left for `QUIET_SECONDS`.
"""

import logging
import threading
from collections.abc import Callable, Collection, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from clank.components.workspaces.adapters.platform import Container, NetworkGone, PlatformError
from clank.components.workspaces.sandbox import (
    EDGE_ALIAS,
    PORTS_LABEL,
    PROXY_LABEL,
    ContainerSpec,
    Names,
    edge_ports,
    edge_spec,
    image_tag,
    names,
)
from clank.kernel.events import Actor, EventType

if TYPE_CHECKING:
    from clank.components.workspaces.service import Workspaces

logger = logging.getLogger(__name__)
CLANK = Actor(kind="clank", via="workspaces")
STOP_SECONDS = 10
QUIET_SECONDS = 60  # how long the check of Docker leaves an edge it could not put right before it tries again
CHECK = "Clank's check of Docker"  # what found a repair the background check made
EVENT_TYPES = [
    EventType(
        "workspaces.edge_repaired",
        "Clank put the edge right for workspaces whose agents could not reach the model: it joined the edge back to "
        "their networks, started it, or made it again (design 0004 §3).",
        {
            "workspaces": "The workspaces whose container ran and reach the model again.",
            "did": "What Clank did, each in its words.",
            "found_by": "What found it: Clank's check of Docker, opening a workspace, or starting the agent in one.",
        },
    )
]


def listed(items: Sequence[str]) -> str:
    """Names in words: "a", "a and b", "a, b and c"."""
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def ports_said(label: str) -> str:
    """The ports an edge's label names: "port 18210", "ports 18210 and 18211", or "ports of its own" for none."""
    ports = [port for port in label.split(",") if port]
    if not ports:
        return "ports of its own"
    return f"{'port' if len(ports) == 1 else 'ports'} {listed(ports)}"


def state(found: Names, workspace: str, containers: Mapping[str, Container], ports: str, proxy: str) -> str | None:
    """How a workspace's container reaches the edge, from a reading (`containers` by name): None when it does not run;
    `cut` when the edge does not run on its network; `stale` when the edge forwards other ports than `ports` (the
    gateway's and the proxy's); `proxy` when the container was told another proxy port than `proxy`; else `on`."""
    box = containers.get(found.container(workspace))
    if box is None or box.state != "running":
        return None
    edge = containers.get(found.edge)
    if edge is None or edge.state != "running" or found.inner(workspace) not in edge.networks:
        return "cut"
    if edge.clank.get(PORTS_LABEL, "") != ports:
        return "stale"
    told = box.clank.get(PROXY_LABEL, "")
    return "proxy" if told and told != proxy else "on"


def said(
    found: Names, workspace: str, containers: Mapping[str, Container], ports: str, proxy: str, seconds: float
) -> str:
    """A workspace's way to the edge in words, with what Clank does about it; empty while it is as it should be or its
    container does not run."""
    now = state(found, workspace, containers, ports, proxy)
    edge = containers.get(found.edge)
    if now == "cut":
        if edge is None:
            why, does = "the edge is not there", "Clank makes it again"
        elif edge.state != "running":
            why, does = "the edge is stopped", "Clank starts it"
        else:
            why, does = "the edge is not on its network", "Clank joins it back"
        return (
            f"cut off from the model: {why}; {does} within {seconds:g} seconds (opening the workspace or starting its "
            "agent does it now)"
        )
    if now == "stale" and edge is not None:
        return (
            f"the edge forwards {ports_said(edge.clank.get(PORTS_LABEL, ''))}, not {listed(ports.split(','))} (the "
            "gateway's and the proxy's): opening the workspace or starting its agent makes it again"
        )
    if now == "proxy":
        told = containers[found.container(workspace)].clank.get(PROXY_LABEL, "")
        return (
            f"its container was told the proxy on port {told}, but the edge forwards {proxy}: its agent reaches the "
            "model, not the internet, until the workspace is stopped and opened again"
        )
    return ""


@dataclass
class Repair:
    """What putting the edge right did: each change in Clank's words, the workspaces whose container ran and reach the
    model again, and why the edge could not be put right when it could not."""

    did: list[str] = field(default_factory=list)
    reached: list[str] = field(default_factory=list)
    problem: str = ""


def _quiet(line: str) -> None:
    return


class Edge:
    """The edge as every workspace needs it, put right one caller at a time."""

    def __init__(self, workspaces: "Workspaces") -> None:
        self.workspaces = workspaces
        self._lock = threading.Lock()
        self._quiet_until: datetime | None = None
        self._last_problem = ""

    @property
    def names(self) -> Names:
        """This CLANK_HOME's names."""
        return names(self.workspaces.kernel.home.id)

    def spec(self) -> ContainerSpec:
        """The edge as Clank wants it now: forwarding the gateway's port and the proxy's."""
        return edge_spec(
            self.workspaces.kernel.home.id,
            image_tag(),
            gateway_port=self.workspaces.gateway_port(),
            proxy_port=self.workspaces.proxy_port(),
        )

    def ports(self) -> str:
        """The ports the edge forwards when it is as Clank wants it, as its label says them."""
        return edge_ports(self.workspaces.gateway_port(), self.workspaces.proxy_port())

    def view(self, workspace: str, containers: Mapping[str, Container]) -> dict[str, str | None]:
        """A workspace's way to the edge, for the views: `edge` (its state) and `edge_said` (its words)."""
        ports, proxy = self.ports(), str(self.workspaces.proxy_port())
        seconds = self.workspaces.settings().poll_seconds
        return {
            "edge": state(self.names, workspace, containers, ports, proxy),
            "edge_said": said(self.names, workspace, containers, ports, proxy, seconds),
        }

    def cut_off(self, containers: Sequence[Container]) -> list[str]:
        """The workspaces whose container runs while the edge does not run on its network, from a reading."""
        by_name = {each.name: each for each in containers}
        ports, proxy = self.ports(), str(self.workspaces.proxy_port())
        return [
            loaded.id
            for loaded in self.workspaces.kernel.settings.records("workspace")
            if state(self.names, loaded.id, by_name, ports, proxy) == "cut"
        ]

    def check(self, containers: Sequence[Container]) -> Repair | None:
        """For the service's check of Docker, given its reading: the running workspaces cut off from the edge are
        joined back to it, the edge started or made when it must be (never made again while it runs); None when
        nothing was missing, or while an edge that could not be put right is left alone."""
        cut = self.cut_off(containers)
        now = self.workspaces.kernel.clock.now()
        if not cut or (self._quiet_until is not None and now < self._quiet_until):
            return None
        try:
            repair = self.ready("", containers, others=cut, remake=False, found_by=CHECK)
        except PlatformError as error:
            repair = Repair(problem=f"the edge could not be put right: {error}")
        if repair.problem:
            self._quiet_until = now + timedelta(seconds=QUIET_SECONDS)
            if repair.problem != self._last_problem:
                logger.warning("%s (found by %s; tried again in %d seconds)", repair.problem, CHECK, QUIET_SECONDS)
            self._last_problem = repair.problem
        else:
            self._quiet_until, self._last_problem = None, ""
        return repair

    def ready(
        self,
        target: str,
        containers: Sequence[Container],
        *,
        others: Collection[str] = (),
        everyone: bool = False,
        remake: bool,
        found_by: str,
        log: Callable[[str], None] = _quiet,
    ) -> Repair:
        """The edge made, started or made again as it must be, then on the network of `target` (a refusal to join it is
        raised), of `others`, and, with `everyone` or once it made or started the edge, of every workspace whose
        container is in the reading `containers`. `log` gets each line of what it does; what it repaired is recorded."""
        with self._lock:
            platform = self.workspaces.platform
            spec, found = self.spec(), self.names
            repair = Repair()
            current = platform.container(spec.name)
            was_running = current is not None and current.state == "running"
            current, fresh = self._put_right(spec, current, remake, repair, log)
            if repair.problem or current is None:
                return repair
            boxes = {each.name: each for each in containers}
            records = [loaded.id for loaded in self.workspaces.kernel.settings.records("workspace")]
            existing = {name for name in records if found.container(name) in boxes}
            running = {name for name in existing if boxes[found.container(name)].state == "running"}
            wanted = set(others) | (existing if everyone or fresh else set())
            joined = self._join(spec.name, current, [target] if target else [], sorted(wanted - {target}), log)
            told = sorted(name for name in joined if name != target or name in running)
            if told:
                repair.did.append(_joined_said(told, fresh == "made"))
                log(repair.did[-1])
            on = set(current.networks) | {found.inner(name) for name in joined}
            back = {name for name in joined if name in running}
            if not was_running:
                back |= {name for name in running if found.inner(name) in on}
            repair.reached = sorted(back)
            if repair.reached:
                self._record(repair, found_by)
            return repair

    def _put_right(
        self, spec: ContainerSpec, current: Container | None, remake: bool, repair: Repair, log: Callable[[str], None]
    ) -> tuple[Container | None, str]:
        """The edge as the spec says, as far as `remake` allows; it as it is after, and whether it was `made` or
        `started` now (empty: neither). The changes are said in `repair`."""
        platform = self.workspaces.platform
        wanted = dict(spec.labels)[PORTS_LABEL]
        if current is None:
            repair.did.append("the edge was not there: Clank made it")
            return self._make(spec, repair, log), "made"
        had = current.clank.get(PORTS_LABEL, "")
        stale = had != wanted and (remake or current.state != "running")
        older = current.state != "running" and current.image != spec.image
        if (stale or older) and platform.image_exists(spec.image):  # never removed before the new one can be made
            if current.state == "running":
                platform.stop_container(spec.name, STOP_SECONDS)
            platform.remove_container(spec.name)
            if stale:
                log(f"{spec.name} forwarded {ports_said(had)}; it is made again for {wanted}")
                repair.did.append(
                    f"the edge forwarded {ports_said(had)}, not {listed(wanted.split(','))} (the gateway's and the "
                    "proxy's): Clank made it again"
                )
            else:
                log(f"{spec.name} was made from {current.image}; it is made again from {spec.image}")
                repair.did.append("the edge was stopped, made from an older image: Clank made it again")
            return self._make(spec, repair, log), "made"
        if current.state != "running":
            try:
                platform.start_container(spec.name)
            except NetworkGone:
                platform.remove_container(spec.name)
                log(f"{spec.name} could not start (a network it was on is gone): it is made again")
                repair.did.append("the edge could not start (a network it was on is gone): Clank made it again")
                return self._make(spec, repair, log), "made"
            log(f"{spec.name} started")
            repair.did.append("the edge was stopped: Clank started it")
            return platform.container(spec.name), "started"
        if current.image != spec.image:
            log(f"{spec.name} runs {current.image}: it is made again from {spec.image} once it is stopped")
        elif current.clank.get(PORTS_LABEL, "") != wanted:
            log(f"{spec.name} forwards {ports_said(current.clank.get(PORTS_LABEL, ''))}: opening a workspace makes it "
                f"again for {wanted}")  # fmt: skip
        else:
            log(f"{spec.name} runs")
        return current, ""

    def _make(self, spec: ContainerSpec, repair: Repair, log: Callable[[str], None]) -> Container | None:
        """The edge made from its spec, on the network that reaches the host; None, with the problem said, when Clank's
        sandbox image is not built (a `docker run` would download it)."""
        platform = self.workspaces.platform
        if not platform.image_exists(spec.image):
            repair.did.clear()
            repair.problem = (
                f"the edge is not there and cannot be made: Clank's sandbox image ({spec.image}) is not built; opening "
                "a workspace builds it"
            )
            return None
        labels = {"clank.home": self.workspaces.kernel.home.id, "clank.component": "workspaces"}
        platform.ensure_network(self.names.outer, internal=False, labels=labels)
        platform.run_container(spec)
        log(f"{spec.name} made and started")
        return platform.container(spec.name)

    def _join(
        self, edge: str, current: Container, first: list[str], rest: list[str], log: Callable[[str], None]
    ) -> list[str]:
        """The edge joined to each workspace's network it is not on: `first`'s refusal is raised, the others' said and
        passed; the workspaces whose network it joined now."""
        platform, found = self.workspaces.platform, self.names
        joined = []
        for name in [*first, *rest]:
            network = found.inner(name)
            if network in current.networks:
                continue
            try:
                if platform.join_network(network, edge, EDGE_ALIAS):
                    joined.append(name)
            except PlatformError as error:
                if name in first:
                    raise
                log(f"{edge} could not join {name}'s network: {error}")
        return joined

    def _record(self, repair: Repair, found_by: str) -> None:
        """What was repaired, in the service's log and as an event."""
        whose = listed(repair.reached)
        reaches = "reaches" if len(repair.reached) == 1 else "reach"
        summary = f"{'; '.join(repair.did)}, so {whose} {reaches} the model again (found by {found_by})"
        logger.warning("%s", summary)
        self.workspaces.kernel.events.record(
            "workspaces.edge_repaired",
            summary=summary,
            actor=CLANK,
            data={"workspaces": repair.reached, "did": list(repair.did), "found_by": found_by},
        )


def _joined_said(workspaces: list[str], made: bool) -> str:
    """The networks the edge joined, in words: as part of making it, or put back."""
    whose = f"{workspaces[0]}'s network" if len(workspaces) == 1 else f"the networks of {listed(workspaces)}"
    return f"the edge joined {whose}" if made else f"the edge was not on {whose}: Clank joined it back"
