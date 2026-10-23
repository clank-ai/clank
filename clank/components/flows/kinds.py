"""The flows component's kinds of record (design 0013 §2-§4, §11): a flow, `config/flows/<workspace>/<name>.json`.

A flow is a settings record kept by workspace (decision 0066), its id `<workspace>/<name>`: its boxes, each a big task
with a deliverable done by a model in a session of its own, or a decision the owner makes; and the lines that say what
comes next. `Box` and `Line` are the parts of its file, defined once here as kinds are, but no records of their own.
The rules of §3 that need nothing but the file are the kind's own validation (`clank.components.flows.rules`), so a
file that breaks one is reported like any settings file that does not read, with its file, line and field, and the
last good flow stays in force.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import InitErrorDetails, PydanticCustomError

from clank.components.flows.rules import in_the_folder, rule_problems
from clank.kernel.records import Settings

BoxType = Literal["you", "plan", "verify", "decompose", "task", "integrate", "gate"]
Mode = Literal["plan", "review", "auto"]

FolderFile = Annotated[str, AfterValidator(in_the_folder)]


class Part(BaseModel):
    """A part of a flow's file: no field but its own."""

    model_config = ConfigDict(extra="forbid")


class FlowLimits(Part):
    """What one try of a box may use, unless the box says otherwise."""

    minutes: int = Field(30, ge=1, title="Minutes", description="How long one try of a box may run.")
    tokens: int = Field(
        200_000,
        ge=1,
        title="Tokens written",
        description="How many tokens the model may write in one try, its thinking included (a prompt read again "
        "from the engine's cache is not counted).",
    )


class Limits(Part):
    """What one try of this box may use; each empty takes the flow's."""

    minutes: int | None = Field(None, ge=1, title="Minutes", description="How long one try may run; empty: the flow's.")
    tokens: int | None = Field(
        None,
        ge=1,
        title="Tokens written",
        description="How many tokens the model may write in one try, its thinking included; empty: the flow's.",
    )


class FlowDefaults(Part):
    """What every box takes unless it names its own."""

    model: str = Field(
        "",
        title="Model",
        description='The preset each box runs on, by its id or title ("daily 262K"); empty: whatever the main slot '
        "runs when the box starts.",
    )
    tries: int = Field(
        3, ge=1, title="Tries", description="How many times a box may run before a gate decides (a VERIFY's loop)."
    )
    limits: FlowLimits = Field(default_factory=FlowLimits, title="Limits", description="What one try of a box may use.")
    whole_up_to: int = Field(
        40_000,
        ge=0,
        title="Handed whole up to",
        description="The bytes of a text file a box's first message hands whole; a larger one is named by its path "
        "and size, for the box to read with its tools.",
    )
    note_up_to: int = Field(
        2_000,
        ge=0,
        title="Notes handed up to",
        description="The characters of each earlier box's handoff note a box's first message hands; a longer note is "
        "cut there, saying where the whole is.",
    )
    copied_up_to: int = Field(
        5_000_000,
        ge=0,
        title="Copied up to",
        description="The bytes of a deliverable copied into the run's folder when its box ends; a larger one is kept "
        "by its fingerprint only.",
    )


class Proposed(Part):
    """Where a box accepted from a proposal came from (design 0013 §9)."""

    run: int = Field(ge=1, title="Run", description="The run in which it was proposed.")
    by: str = Field(title="Proposed by", description="The box that proposed it, a DECOMPOSE above all.")
    accepted: Literal["owner", "auto-accept"] = Field(
        "owner",
        title="Accepted by",
        description="owner: you accepted it; auto-accept: the flow's setting did, within its cap.",
    )


class Box(Part):
    """A step of a flow: a big task with a deliverable, done by a model in a session of its own, or the owner's."""

    id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
        title="Id",
        description="Its name in the flow's lines: letters, digits, '-' and '_'.",
    )
    type: BoxType = Field(
        title="Type",
        description="you: your brief or work; plan: a plan (PLAN.md); verify: a verdict on an earlier box's "
        "deliverable; decompose: proposed tasks; task: its deliverable; integrate: a summary of every deliverable "
        "and the next flow's brief; gate: your decision.",
    )
    title: str = Field(min_length=1, title="Title", description="What it does, in a few words.")
    checks: str = Field("", title="Checks", description="A VERIFY only: the earlier box whose deliverable it checks.")
    model: str = Field(
        "",
        title="Model",
        description="The preset it runs on, by its id or title, loaded before it starts; empty: the flow's (a "
        "VERIFY's: the preset of the box it checks).",
    )
    mode: Mode | None = Field(
        None,
        title="Mode",
        description="plan, review or auto, for its own session; empty: plan for PLAN, VERIFY, DECOMPOSE and "
        "INTEGRATE, the workspace's for a TASK.",
    )
    sees: list[FolderFile] = Field(
        default_factory=list,
        title="Sees",
        description="The files of the folder its first message hands it; it may still read any other.",
    )
    shows: list[FolderFile] = Field(
        default_factory=list, title="Shows", description="A GATE's: the files it shows you, to approve or edit."
    )
    prompt: str = Field("", title="Prompt", description="Its own words: yours, or drafted by a DECOMPOSE.")
    writes: list[FolderFile] = Field(
        default_factory=list,
        title="Deliverable",
        description="The files it must write in the folder; it is done when each was written during its try.",
    )
    holds: str = Field("", title="What they hold", description="What its deliverable's files hold, in words.")
    accept_when: list[str] = Field(
        default_factory=list,
        title="Accept when",
        description="What makes its deliverable right, one thing per line, checked by a VERIFY or by you at a gate.",
    )
    accept_command: str = Field(
        "",
        title="Accept command",
        description="A command run in the workspace's container after it, which passes when it exits 0; empty: none.",
    )
    when_done: Literal["go on", "wait"] = Field(
        "go on",
        title="When done",
        description="go on: the box after it starts; wait: the flow waits for you first.",
    )
    tries: int | None = Field(
        None, ge=1, title="Tries", description="How many times it may run before a gate decides; empty: the flow's."
    )
    limits: Limits = Field(
        default_factory=Limits, title="Limits", description="What one try may use; empty values: the flow's."
    )
    mcp_servers: list[str] | None = Field(
        None,
        title="MCP servers",
        description="The workspace's MCP servers it gets; empty: those the workspace's agent gets.",
    )
    proposed: Proposed | None = Field(
        None, title="Proposed", description="Where it came from, when it was accepted from a proposal."
    )


class Line(Part):
    """What comes after a box: a then line, or a VERIFY's pass or fail line."""

    model_config = ConfigDict(extra="forbid", validate_by_name=True, validate_by_alias=True, serialize_by_alias=True)

    from_: str = Field(alias="from", title="From", description="The box it leaves.")
    to: str = Field(title="To", description="The box it leads to.")
    when: Literal["pass", "fail"] | None = Field(
        None,
        title="When",
        description="A VERIFY's lines only: pass, to the box after it; fail, back to the box it checks, with the "
        "findings.",
    )


class Follows(Part):
    """Where a next flow came from (design 0013 §3, decision 0091): the flow whose last gate was approved, its run, the
    INTEGRATE that wrote its brief, and the brief's file."""

    flow: str = Field(title="Flow", description="The flow it follows: <workspace>/<name>.")
    run: int = Field(ge=1, title="Run", description="That flow's run whose last gate was approved.")
    by: str = Field(title="By", description="The INTEGRATE that wrote its brief.")
    brief: FolderFile = Field(
        title="Brief", description="The brief's file, copied into its own first box's file when it first runs."
    )
    replaces: str = Field(
        "",
        title="Replaces",
        description="The fingerprint of its first box's file when it was made (empty: not in the folder): the brief "
        "is copied over it only while it is unchanged.",
    )


class Built(Part):
    """How a flow built with the model came to be (design 0013 §15, decision 0097): the planning session its draft came
    from, when Clank wrote it, and the brief the owner wrote with the model, which its first box takes (decision
    0098)."""

    session: str = Field(
        "", title="Session", description="The planning session the draft came from; empty when not known yet."
    )
    at: datetime = Field(title="Written", description="When Clank wrote the flow from the model's last draft.")
    brief: FolderFile = Field(
        title="Brief", description="The brief written with the model: its first box is done by it when it is there."
    )
    before: str = Field(
        "",
        title="Brief before",
        description="The brief's fingerprint when the planning began (empty: not there): a brief still so is not the "
        "one written with the model, and its first box asks for it.",
    )


class CheckpointLimits(Part):
    """What one checkpoint of the orchestrator may use."""

    minutes: int = Field(20, ge=1, title="Minutes", description="How long one checkpoint may run.")
    tokens: int = Field(
        60_000,
        ge=1,
        title="Tokens written",
        description="How many tokens one checkpoint may write, its thinking included.",
    )


class SideLimits(Part):
    """What side work may use while a box waits on its job (design 0013 §17, decision 0132)."""

    minutes: int = Field(20, ge=1, title="Minutes", description="How long one side task may run.")
    tokens: int = Field(
        60_000,
        ge=1,
        title="Tokens written",
        description="How many tokens one side task may write, its thinking included.",
    )
    per_job: int = Field(
        3, ge=1, title="Per job", description="How many side tasks one job's checkpoint may set going."
    )
    budget: int = Field(
        180,
        ge=0,
        title="Budget",
        description="Minutes of side work in one run; past them a job's checkpoint may only wait or change.",
    )
    corpus: str = Field(
        "corpus", title="Corpus", description="The folder, in the workspace's, where side tasks write their notes."
    )


class Orchestrator(Part):
    """The model that steers a run at checkpoints while it is on (design 0013 §16, decisions 0123-0124): after each box
    a model ran, and at each question the run would ask you."""

    on: bool = Field(
        False,
        title="On",
        description="Steer the run: a checkpoint after each box, and at each question; it decides as you would, "
        "within its limits, and you may answer first.",
    )
    model: str = Field(
        "", title="Model", description="The preset its checkpoints run on, by its id or title; empty: the flow's."
    )
    role: Literal["steer", "watch"] = Field(
        "steer",
        title="Role",
        description="steer: it decides the run's questions and may change the boxes ahead; watch: it checks each box "
        "is on track, goes on or pauses the run, and leaves every question to you. In both it tells you at once what "
        "you should know.",
    )
    final_review: Literal["orchestrator", "owner"] = Field(
        "orchestrator",
        title="Final review",
        description="Who decides the last gate: orchestrator, or owner (it waits for you).",
    )
    changes: int = Field(
        12,
        ge=0,
        title="Changes",
        description="How many changes it may make in one run: each box changed or added, send back, skip and extra "
        "try.",
    )
    extra_tries: int = Field(2, ge=0, title="Extra tries", description="How many tries past its cap it may give a box.")
    stall: int = Field(
        3,
        ge=1,
        title="Stall",
        description="Checkpoints in a row without progress after which it may not go on: it changes the plan or stops.",
    )
    limits: CheckpointLimits = Field(
        default_factory=CheckpointLimits, title="Limits", description="What one checkpoint may use."
    )
    side: SideLimits = Field(
        default_factory=SideLimits,
        title="Side work",
        description="What side tasks may use while a box waits on its job, and where their notes go.",
    )


class Flow(Settings):
    """A flow: boxes joined by lines, kept by workspace."""

    KIND = "flow"
    LABEL = "Flow"
    HELP = (
        "The work as a program of boxes (design 0013): each a big task with a deliverable, done by a model in a "
        "session of its own, or a decision you make; the lines say what comes next."
    )
    FOLDER = "flows"
    GROUPED_BY = "workspace"

    workspace: str = Field(
        "",
        title="Workspace",
        description="The workspace whose folder its boxes work in; the folder it is kept in names it, and this, when "
        "given, must be the same.",
    )
    defaults: FlowDefaults = Field(
        default_factory=FlowDefaults, title="Defaults", description="What every box takes unless it names its own."
    )
    auto_accept: bool = Field(
        False,
        title="Auto-accept",
        description="Boxes the model proposes join the flow at once, when they pass the checks, up to the cap; off: "
        "each waits for you.",
    )
    auto_accept_cap: int = Field(
        10, ge=0, title="Auto-accept cap", description="How many proposals auto-accept may accept in one run."
    )
    wait_after_every_box: bool = Field(
        False, title="Wait after every box", description="Every box waits for you when it is done, to step through."
    )
    next_flow: Literal["ask", "run", "off"] = Field(
        "ask",
        title="Next flow",
        description="Once its last gate is approved, the next flow is made from its INTEGRATE's brief: ask, you are "
        "asked whether to run it now; run, it starts at once; off, none is made.",
    )
    follows: Follows | None = Field(
        None, title="Follows", description="The flow it was made after, from that flow's INTEGRATE's brief."
    )
    next: str = Field(
        "", title="Next", description="The flow made after it, from its INTEGRATE's brief: <workspace>/<name>."
    )
    orchestrator: Orchestrator = Field(
        default_factory=Orchestrator,
        title="Orchestrator",
        description="A model that steers the run at checkpoints while it is on (design 0013 §16).",
    )
    built: Built | None = Field(
        None,
        title="Built",
        description="Set when the model drafted it in a planning session and Clank wrote it: that session, when, and "
        "the brief written with the model.",
    )
    boxes: list[Box] = Field(min_length=1, title="Boxes", description="Its boxes; DECOMPOSE's tasks run in this order.")
    lines: list[Line] = Field(default_factory=list, title="Lines", description="What comes after each box.")

    @model_validator(mode="after")
    def _keeps_the_rules(self) -> "Flow":
        problems = rule_problems(self)
        if problems:
            raise ValidationError.from_exception_data(
                "Flow",
                [
                    InitErrorDetails(
                        type=PydanticCustomError("flow_rule", "{rule}", {"rule": message}), loc=place, input=None
                    )
                    for place, message in problems
                ],
            )
        return self
