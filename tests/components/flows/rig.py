"""What the runner's tests share: a kernel with the workspace `myproject` on a synthetic folder, its container running
on the fake platform, the fake bridge answering in it with a scripted agent, a flow's file, and the service's runner
running (`running`), with nothing in a container and no OpenCode. The fake bridge reads the container's OpenCode
configuration as Clank last wrote it when it starts a server (its model's limits, its MCP servers)."""

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import anyio

from clank import registry
from clank.components.flows import runner as runner_module
from clank.components.flows.runs import Run
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import image_tag, names
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor, Event
from clank.kernel.home import Home
from clank.kernel.questions import Question
from tests.fakes.bridge import FakeBridge
from tests.fakes.platform import FakePlatform, container

OWNER = Actor(kind="user", via="console")
WORKSPACE = "myproject"
FLOW = f"{WORKSPACE}/study"
CONFIG = "/home/agent/.config/opencode/opencode.json"  # OpenCode's configuration in the container's home


def study(**changes: Any) -> dict[str, Any]:
    """A flow of YOU, PLAN, GATE and TASK, as the owner writes it."""
    flow: dict[str, Any] = {
        "schema": "flow/1",
        "title": "Study",
        "boxes": [
            {"id": "brief", "type": "you", "title": "Brief", "writes": ["BRIEF.md"]},
            {"id": "plan", "type": "plan", "title": "Write the plan", "sees": ["BRIEF.md"], "writes": ["PLAN.md"],
             "prompt": "Write the study plan for the brief."},
            {"id": "approve", "type": "gate", "title": "You approve the plan", "shows": ["PLAN.md"]},
            {"id": "T1", "type": "task", "title": "The grid", "sees": ["PLAN.md"], "writes": ["grid.json"],
             "prompt": "Write the grid."},
        ],
        "lines": [{"from": "brief", "to": "plan"}, {"from": "plan", "to": "approve"}, {"from": "approve", "to": "T1"}],
    }  # fmt: skip
    flow.update(changes)
    return flow


def checked_study(tries: int | None = None) -> dict[str, Any]:
    """The study with its plan checked by a VERIFY before the owner approves it: its pass line on to the gate, its
    fail line back to the plan; the plan's tries `tries`, else the flow's."""
    flow = study()
    plan = flow["boxes"][1]
    plan["accept_when"] = ["about 60 grid points", "at most 48 CPU-hours"]
    if tries is not None:
        plan["tries"] = tries
    flow["boxes"].insert(
        2,
        {"id": "check", "type": "verify", "title": "Check the plan", "checks": "plan", "sees": ["BRIEF.md", "PLAN.md"]},
    )
    flow["lines"] = [
        {"from": "brief", "to": "plan"}, {"from": "plan", "to": "check"},
        {"from": "check", "to": "approve", "when": "pass"}, {"from": "check", "to": "plan", "when": "fail"},
        {"from": "approve", "to": "T1"},
    ]  # fmt: skip
    return flow


def decomposing(**changes: Any) -> dict[str, Any]:
    """A flow whose plan is broken into tasks by a DECOMPOSE, put together by an INTEGRATE, and reviewed by the owner:
    board D1's shape, its tasks not proposed yet."""
    flow: dict[str, Any] = {
        "schema": "flow/1",
        "title": "Study",
        "boxes": [
            {"id": "brief", "type": "you", "title": "Brief", "writes": ["BRIEF.md"]},
            {"id": "plan", "type": "plan", "title": "Write the plan", "sees": ["BRIEF.md"], "writes": ["PLAN.md"],
             "prompt": "Write the study plan for the brief."},
            {"id": "split", "type": "decompose", "title": "Break it into tasks", "sees": ["BRIEF.md", "PLAN.md"]},
            {"id": "join", "type": "integrate", "title": "Put it together", "writes": ["STUDY-PLAN.md"]},
            {"id": "review", "type": "gate", "title": "You review the whole", "shows": ["STUDY-PLAN.md"]},
        ],
        "lines": [
            {"from": "brief", "to": "plan"}, {"from": "plan", "to": "split"}, {"from": "split", "to": "join"},
            {"from": "join", "to": "review"},
        ],
    }  # fmt: skip
    flow.update(changes)
    return flow


def task(number: int, **more: Any) -> dict[str, Any]:
    """A TASK as a DECOMPOSE proposes it with `flow_propose_box`: after `split`, writing `out/t<number>.md`."""
    return {
        "after": "split", "type": "TASK", "title": f"Task {number}", "prompt": f"Write out/t{number}.md.",
        "deliverable": f"out/t{number}.md", "why": f"The plan's step {number}.", **more,
    }  # fmt: skip


@dataclass
class Rig:
    """The kernel, the folder, the fake platform and the fake bridge."""

    kernel: Kernel
    folder: Path
    platform: FakePlatform
    bridge: FakeBridge
    clock: FakeClock

    @property
    def runner(self) -> runner_module.Runner:
        found: runner_module.Runner = self.kernel.parts["flows"].runner
        return found

    def write_flow(self, flow: dict[str, Any], name: str = "study") -> None:
        """The flow's file, read by the service as if edited by hand."""
        path = self.kernel.home.config / "flows" / WORKSPACE / f"{name}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((json.dumps(flow, indent=2) + "\n").encode("utf-8"))
        self.kernel.settings.reload_changed()

    def run(self, number: int = 1, flow: str = FLOW) -> Run:
        return self.runner.runs.load(flow, number)

    def waiting(self) -> list[Question]:
        return self.kernel.questions.waiting()

    def events(self, *types: str) -> list[Event]:
        return list(reversed(self.kernel.events.latest(500, types=list(types) or None)))

    def write(self, path: str, text: str) -> None:
        target = self.folder.joinpath(*path.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(text.encode("utf-8"))


def make_rig(home: Home, clock: FakeClock, tmp_path: Path, monkeypatch: Any, flow: dict[str, Any] | None) -> Rig:
    """The rig, with `flow` as the flow `study` (none: no flow yet)."""
    platform = FakePlatform(state="running")
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    monkeypatch.setattr(runner_module, "TICK", 0.02)
    monkeypatch.setattr(runner_module, "WAIT", 0.02)
    folder = tmp_path / WORKSPACE
    folder.mkdir()
    record = home.config / "workspaces" / f"{WORKSPACE}.json"
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"schema": "workspace/1", "path": str(folder)}), encoding="utf-8")
    kernel = open_kernel(home, clock, registry.components())
    name = names(kernel.home.id).container(WORKSPACE)
    platform.containers.append(container(name).model_copy(update={"image": image_tag()}))  # the image as built now
    bridge = FakeBridge(WORKSPACE, folder, hear=kernel.parts["agents"].review.heard)
    platform.inside = bridge.inside
    bridge.configuration = lambda: platform.files.get((name, CONFIG))
    kernel.parts["workspaces"].docker(refresh=True)
    rig = Rig(kernel, folder, platform, bridge, clock)
    if flow is not None:
        rig.write_flow(flow)
    return rig


def restart(rig: Rig) -> Rig:
    """The service started again on the same home: the rig's kernel a new one, its platform, folder and bridge the
    same (the container and its OpenCode servers went on meanwhile)."""
    rig.kernel.close()
    rig.clock.advance(5)  # a restart takes a moment, so what it starts comes after what it interrupted
    rig.kernel = open_kernel(rig.kernel.home, rig.clock, registry.components())
    rig.bridge.hear = rig.kernel.parts["agents"].review.heard
    rig.kernel.parts["workspaces"].docker(refresh=True)
    return rig


@asynccontextmanager
async def running(kernel: Kernel) -> AsyncIterator[None]:
    """The service's operations and the flows' runner, running while the block lasts."""
    await kernel.operations.recover()
    async with kernel.operations.running(), anyio.create_task_group() as group:
        group.start_soon(kernel.parts["flows"].run)
        try:
            yield
        finally:
            group.cancel_scope.cancel()


async def until(found: Callable[[], Any], seconds: float = 10) -> Any:
    """What `found` gives once it gives something truthy; fails after `seconds`."""
    with anyio.fail_after(seconds):
        while True:
            value = found()
            if value:
                return value
            await anyio.sleep(0.01)


def question(rig: Rig, words: str) -> Question | None:
    """The question waiting whose title holds `words`."""
    return next((each for each in rig.waiting() if words in each.title), None)


def is_sent(rig: Rig, box: str, number: int = 1) -> bool:
    """Whether the run's file says the box's try `number` sent its first message (its model may then give what its
    flow takes from it: proposals, a verdict); the bridge hears the message a moment before the file says so."""
    tries = rig.run().box(box).tries
    return len(tries) >= number and tries[number - 1].sent is not None


async def at_work(rig: Rig, box: str, number: int = 1) -> Any:
    """The flow Study's box at work in its try `number`: its first message as the bridge got it, once the run's file
    says it was sent."""
    prompt = await until(lambda: rig.bridge.prompted(f"Study · {box} · try {number}"))
    await until(lambda: is_sent(rig, box, number))
    return prompt
