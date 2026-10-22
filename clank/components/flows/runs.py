"""The runs of a flow (design 0013 §6, §8; decision 0061): each a readable JSON file in its own folder.

A run is `CLANK_HOME/state/flows/<workspace>/<flow>/run-<n>/run.json`, numbered from 1 for each flow: the version of
the flow it started from, where it is (the box it is at), whether it is paused, what it waits for (a question), the
operation working on its box and what that box waits for before it starts, the flow's OpenCode server and the model's
limits it was started with, and each box's state (waiting, running, done, failed, stale, skipped) with its tries, each
naming the preset it ran on and the MCP servers it had. A try's folder, `<box>/try-<k>/`, holds its first message
(`first-message.md`), copies of its deliverables (`deliverables/`) and of its handoff note (`handoff.md`), a VERIFY's
verdict (`verdict.md`) and what its accept command said (`accept-command.txt`); their fingerprints, the verdict and how
the command ended are in the run's file (`Kept`, `Try.handoff`, `Try.verdict`, `Try.command`). It is state, not a
setting: Clank writes it, whole and at once, and reads it again after a restart. `order` says the order the boxes run
in: along their lines (then and pass), a DECOMPOSE's tasks one after another in the order of the boxes (§3); `after`
every box later.
"""

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from clank.components.flows.accepting import Commanded
from clank.components.flows.orchestrating import Orchestration
from clank.components.flows.verdicts import Verdict
from clank.kernel.events import Actor

if TYPE_CHECKING:
    from clank.components.flows.kinds import Flow
    from clank.kernel.home import Home

SCHEMA: Literal["flow-run/1"] = "flow-run/1"
RUN = re.compile(r"^run-([1-9][0-9]*)$")
REPLACE_WAITS = (0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.3, None)  # seconds between tries to replace a read file
BoxState = Literal["waiting", "running", "done", "failed", "stale", "skipped"]
RunStatus = Literal["queued", "running", "done", "stopped"]
Outcome = Literal["done", "failed", "stopped"]
WaitingFor = Literal["you", "gate", "failed", "done", "proposals"]


class Part(BaseModel):
    """A part of a run's file: no field but its own."""

    model_config = ConfigDict(extra="forbid")


class Kept(Part):
    """A file of the folder as Clank saw it: its fingerprint and size, and for a plan its progress apart (§8)."""

    path: str = Field(description="The file, from the folder, with '/'.")
    sha256: str = Field("", description="Its content's fingerprint; empty when the file did not exist.")
    size: int = Field(0, description="Its size in bytes.")
    modified: int = Field(0, description="When it was last written, in nanoseconds.")
    rest: str = Field("", description="A plan's lines but its progress, fingerprinted; empty for another file.")
    progress: str = Field("", description="A plan's progress (its ticks, its Log, its status), fingerprinted.")
    copied: bool = Field(False, description="Whether a copy is kept in the try's folder (else its fingerprint only).")


class Try(Part):
    """One try of a box: its session, when it ran, how it ended."""

    number: int = Field(ge=1, description="Its number, from 1.")
    started: datetime = Field(description="When it started.")
    ended: datetime | None = Field(None, description="When it ended.")
    operation: str = Field("", description="The operation that ran it (flows.box).")
    port: int | None = Field(None, description="The OpenCode server its session runs on, in the container.")
    session: str = Field("", description="Its session.")
    agent: str = Field("", description="The agent its first message was sent to: planner or build.")
    mode: str = Field("", description="The mode its session ran in: plan, review or auto; empty: the workspace's.")
    preset: str = Field(
        "", description="The preset the main slot ran when its session started (design 0013 §7); empty: none ran."
    )
    tools: list[str] = Field(
        default_factory=list,
        description="The MCP servers connected on its server when its session started (design 0013 §4).",
    )
    sent: datetime | None = Field(None, description="When its first message was sent.")
    told: str = Field("", description="What its first message said of the last try, the owner's note included.")
    outcome: Outcome | None = Field(None, description="done, failed or stopped; empty while it runs.")
    reason: str = Field("", description="Why it failed or was stopped.")
    tokens: int = Field(0, description="The tokens its model wrote, thinking included.")
    before: list[Kept] = Field(default_factory=list, description="Its deliverables as they were when it started.")
    earlier: list[Kept] = Field(
        default_factory=list, description="The earlier boxes' deliverables as they were when it started."
    )
    deliverables: list[Kept] = Field(default_factory=list, description="Its deliverables as it left them.")
    handoff_before: Kept | None = Field(
        None, description="A PLAN's, TASK's or INTEGRATE's: its handoff note's file as it was when it started."
    )
    handoff: Kept | None = Field(
        None,
        description="Its handoff note as it left it, when written during the try (a copy beside it, `handoff.md`); "
        "empty: it wrote none.",
    )
    verdict: Verdict | None = Field(None, description="A VERIFY's: the newest verdict it gave during this try.")
    command: Commanded | None = Field(None, description="Its accept command, as it ran after the try.")


class BoxRun(Part):
    """A box in a run: its state, its tries, its deliverables as they stand, and what its next try is told."""

    state: BoxState = Field("waiting", description="waiting, running, done, failed, stale or skipped.")
    tries: list[Try] = Field(default_factory=list, description="Its tries, oldest first.")
    settings: str = Field("", description="Its settings' fingerprint when it last ran.")
    kept: list[Kept] = Field(default_factory=list, description="Its deliverables as they stand, done and approved.")
    why: str = Field("", description="Why it failed, or why it is stale.")
    changed: str = Field("", description="Why a finished box is changed: its settings, or its deliverable.")
    note: str = Field("", description="What its next try's first message is told: the owner's note.")
    steer: str = Field(
        "", description="What its next try's first message is told by the orchestrator (design 0013 §16)."
    )
    again: str = Field(
        "",
        description="Why it runs again after a try that was done: sent back at a gate, run again from a box, or found "
        "wrong by a VERIFY.",
    )
    findings: list[str] = Field(
        default_factory=list,
        description="What its next try is handed of a VERIFY's fail: the findings on its last try (the checked box's, "
        "or the VERIFY's own).",
    )


class ServerLimits(Part):
    """The model's limits a flow's OpenCode server was started with: those of the model the main slot ran for its box
    (design 0013 §5), and whether it reads images, which its configuration says too. Its title alone, only shown, does
    not start the server again: every request reaches the slot by its role."""

    context: int = Field(description="The context OpenCode is told: the window less its margin (decision 0089).")
    output: int = Field(description="Its output limit, in tokens.")
    images: bool = Field(False, description="Whether the model reads images (its configuration takes them).")


class Waiting(Part):
    """A question the run waits for: a YOU box, a gate, a failed box, a box whose *when done* waits, or the proposals
    of a box's try (design 0013 §9)."""

    question: str = Field(description="The question's id.")
    kind: WaitingFor = Field(description="you, gate, failed, done, or proposals (a batch of a box's).")
    box: str = Field(description="The box it is about.")


class Run(BaseModel):
    """A run of a flow."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, serialize_by_alias=True)

    schema_: Literal["flow-run/1"] = Field(SCHEMA, alias="schema")
    flow: str = Field(description="The flow's id: <workspace>/<name>.")
    number: int = Field(ge=1, description="Its number among the flow's runs, from 1.")
    title: str = Field("", description="The flow's title.")
    workspace: str = Field(description="The workspace whose folder its boxes work in.")
    version: str = Field(description="The flow's revision when the run started.")
    status: RunStatus = Field(description="queued (behind another flow's run), running, done or stopped.")
    behind: str = Field("", description="A queued run: the run it waits behind.")
    paused: bool = Field(False, description="No box starts while it is paused; the running one goes on.")
    at: str = Field("", description="The box it is at.")
    waiting: Waiting | None = Field(None, description="The question it waits for.")
    operation: str = Field("", description="The operation working on its box now.")
    waits_for: str = Field(
        "",
        description="What its box waits for before the main slot is switched to its preset (an operation changing the "
        "slot, your own session at work, a request in flight on the slot), or before the flow's OpenCode server is "
        "started again with its limits (a session at work on it): design 0013 §5, §7; empty: nothing.",
    )
    server: int | None = Field(None, description="The flow's OpenCode server, in the workspace's container.")
    server_limits: ServerLimits | None = Field(
        None, description="The model's limits its OpenCode server was started with; empty: not kept (started again)."
    )
    started_by: Actor = Field(description="Who started it.")
    created: datetime = Field(description="When it was started.")
    ended: datetime | None = Field(None, description="When it ended.")
    boxes: dict[str, BoxRun] = Field(default_factory=dict, description="Each box's state, by its id.")
    orchestration: Orchestration = Field(
        default_factory=Orchestration,
        description="What its orchestrator did (design 0013 §16): the ledger, the limits used, the checkpoint at work.",
    )

    @property
    def name(self) -> str:
        """How the run is named: `<workspace>/<flow>#<n>`."""
        return f"{self.flow}#{self.number}"

    def box(self, id: str) -> BoxRun:
        """A box's state in the run (a box the run has not met yet is waiting)."""
        return self.boxes.setdefault(id, BoxRun())


class Runs:
    """The runs of every flow, in `state/flows/`."""

    def __init__(self, home: "Home") -> None:
        self.folder = home.state / "flows"

    def flow_folder(self, flow: str) -> Path:
        """Where a flow's runs are kept."""
        workspace, name = flow.split("/", 1)
        return self.folder / workspace / name

    def run_folder(self, run: Run) -> Path:
        """A run's folder."""
        return self.flow_folder(run.flow) / f"run-{run.number}"

    def try_folder(self, run: Run, box: str, number: int) -> Path:
        """A try's folder: its first message and its deliverables' copies."""
        return self.run_folder(run) / box / f"try-{number}"

    def next_number(self, flow: str) -> int:
        """The number the flow's next run takes."""
        return max(self._numbers(flow), default=0) + 1

    def save(self, run: Run) -> Path:
        """Write the run's file whole, at once (`write_whole`); its path."""
        path = self.run_folder(run) / "run.json"
        write_whole(path, json.dumps(run.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n")
        return path

    def load(self, flow: str, number: int) -> Run:
        """One run, from its file."""
        path = self.flow_folder(flow) / f"run-{number}" / "run.json"
        return Run.model_validate_json(read_whole(path))

    def latest(self, flow: str) -> Run | None:
        """The flow's newest run, if it has one that reads."""
        for number in sorted(self._numbers(flow), reverse=True):
            try:
                return self.load(flow, number)
            except (OSError, ValueError):
                continue
        return None

    def all(self) -> list[Run]:
        """Every run that reads, by flow and number."""
        found = []
        for path in self._files():
            try:
                found.append(Run.model_validate_json(read_whole(path)))
            except (OSError, ValueError):
                continue
        return sorted(found, key=lambda run: (run.flow, run.number))

    def problems(self) -> list[tuple[Path, str]]:
        """Each run's file that does not read, with why."""
        found = []
        for path in self._files():
            try:
                Run.model_validate_json(read_whole(path))
            except ValidationError as error:
                found.append((path, str(error.errors()[0]["msg"]) if error.errors() else str(error)))
            except (OSError, ValueError) as error:
                found.append((path, str(error)))
        return found

    def _files(self) -> list[Path]:
        if not self.folder.is_dir():
            return []
        return sorted(
            path for path in self.folder.glob("*/*/run-*/run.json") if RUN.match(path.parent.name) is not None
        )

    def _numbers(self, flow: str) -> list[int]:
        folder = self.flow_folder(flow)
        if not folder.is_dir():
            return []
        return [int(found.group(1)) for path in folder.iterdir() if (found := RUN.match(path.name)) is not None]


def order(flow: "Flow") -> list[str]:
    """The boxes in the order they run: from the first, along the lines that lead on (then and pass); the boxes a
    DECOMPOSE fans out to, one after another in the order of `boxes`, then the box they join at."""
    rank = {box.id: index for index, box in enumerate(flow.boxes)}
    leading: dict[str, list[str]] = {}
    for line in flow.lines:
        if line.when != "fail":
            leading.setdefault(line.from_, []).append(line.to)
    found: list[str] = []
    current = [flow.boxes[0].id]
    while current:
        found += current
        seen = set(found)
        current = sorted(
            {to for name in current for to in leading.get(name, []) if to not in seen},
            key=lambda name: rank.get(name, len(rank)),
        )
    return found


def after(flow: "Flow", box: str) -> list[str]:
    """Every box that runs after `box`, in order."""
    found = order(flow)
    return found[found.index(box) + 1 :] if box in found else []


def read_whole(path: Path) -> bytes:
    """A file of the runs, read whole. Windows refuses for a moment to open a file that another thread is replacing,
    so the read is tried again, a second at most, rather than taking the run for one that does not read (a second run
    of a flow could then start beside it)."""
    for wait in REPLACE_WAITS[:-1]:
        try:
            return path.read_bytes()
        except PermissionError:
            time.sleep(wait or 0)
    return path.read_bytes()


def write_whole(path: Path, text: str) -> None:
    """Write a file of the runs whole, at once. Windows refuses to replace a file that another thread is reading at
    that moment (the phone's page, VS Code, `clank flow`), so the write waits for that read to end, a second at most,
    rather than failing."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.writing")
    temporary.write_bytes(text.encode("utf-8"))
    for wait in REPLACE_WAITS:
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            if wait is None:
                raise
            time.sleep(wait)
