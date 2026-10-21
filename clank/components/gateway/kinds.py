"""The gateway component's kinds of record (design 0001 §6, design 0004 §2): its settings, from design 0006 how
completion in VS Code works, from design 0008 the model that reads images, and from design 0016 the cloud's spending
limits (`config/cost.json`)."""

from typing import Annotated, Literal

from pydantic import Field

from clank.kernel.records import Settings


class GatewaySettings(Settings):
    """How the gateway runs."""

    KIND = "gateway"
    LABEL = "Gateway"
    HELP = (
        "Where the gateway listens, how long a request waits for a model that is starting or switching, whether it "
        "answers OpenCode's session titles itself, and what it keeps of each request."
    )
    SINGLE = True
    ON_CHANGE = "next start"
    NEXT_START = "the gateway's next start (clank gateway restart)"

    start: bool = Field(
        True,
        title="Start with the service",
        description="Start the gateway when the service starts, and again whenever it is found not running.",
    )
    port: int = Field(
        18210, ge=1024, le=65535, title="Port", description="Where tools reach the gateway, on this machine only."
    )
    hold_seconds: int = Field(
        300,
        ge=0,
        title="Hold",
        description="How long a request waits, in seconds, for a slot that is starting or switching, before refusal.",
    )
    local_titles: bool = Field(
        True,
        title="Answer titles here",
        description=(
            "Answer OpenCode's session-title requests in the gateway, so they never take the place of the conversation "
            "the engine keeps cached (design 0001 §6.4)."
        ),
    )
    loop_guard: bool = Field(
        True,
        title="Loop guard",
        description="Stop an answer that repeats itself: the engine stops writing it, and the stream ends with an "
        "error that says what repeated (design 0004 §2). A change applies when the gateway restarts: clank gateway "
        "restart.",
    )
    loop_windows: list[Annotated[int, Field(ge=256)]] = Field(
        default_factory=lambda: [2000, 8000],
        min_length=1,
        title="Loop stretches",
        description="The stretches of the thinking and the text that the loop guard reads, their newest characters: "
        "a short one finds a short repeat soon, a long one prose said again every 600 to 800 characters.",
    )
    loop_tool_windows: list[Annotated[int, Field(ge=256)]] = Field(
        default_factory=lambda: [2000],
        min_length=1,
        title="Loop stretches, tool calls",
        description="The stretches of a tool call's arguments that the loop guard reads: the short one only, since a "
        "file written from a template (records that differ by an id, rows of a table) compresses over a long stretch "
        "as far as a loop does.",
    )
    loop_ratio: float = Field(
        0.06,
        gt=0,
        lt=1,
        title="Loop share",
        description="A part repeats itself when a stretch compresses to under this share of its size (real answers "
        "stay above 0.18; the measurement of 2026-10-18).",
    )
    records: bool = Field(True, title="Keep requests", description="Keep each request and its answer in logs/traffic.")
    record_limit_kib: int = Field(
        256, ge=1, title="Field limit", description="The longest text kept of one field of a request or answer, in KiB."
    )
    keep_days: int = Field(14, ge=1, title="Days kept", description="How many days of requests are kept.")


class CompletionSettings(Settings):
    """How completion in VS Code works (design 0006 §5-§6)."""

    KIND = "completion"
    LABEL = "Completion"
    HELP = (
        "Gray text after the cursor in VS Code, from the model in the fast slot: whether it is on, how long it waits "
        "after a keystroke, and whether it writes a few lines after a line that opens a block."
    )
    SINGLE = True

    enabled: bool = Field(
        True, title="On", description="Suggest the rest of the line as you type in VS Code; off: nothing is asked."
    )
    delay_ms: int = Field(
        120,
        ge=0,
        le=2000,
        title="Wait",
        description="How long, in milliseconds, VS Code waits after you stop typing before it asks for a suggestion.",
    )
    lines: Literal["one", "few"] = Field(
        "few",
        title="Lines",
        description="one: the rest of the line; few: also a few lines on an empty line after one that opens a block "
        "(ending with :, {, ( or [).",
    )


class CostSettings(Settings):
    """The cloud's spending limits (design 0016 §11, decision 0104)."""

    KIND = "cost"
    LABEL = "Cloud cost limits"
    HELP = (
        "An optional daily and monthly limit of what cloud models may cost, in US dollars: once one is reached, each "
        "new cloud request is held until you raise it (or the day or month ends). Days and months are this computer's."
    )
    SINGLE = True

    day_usd: float | None = Field(
        None, gt=0, title="Daily limit", description="What the cloud may cost in a day, in US dollars; empty: no limit."
    )
    month_usd: float | None = Field(
        None,
        gt=0,
        title="Monthly limit",
        description="What the cloud may cost in a month, in US dollars; empty: no limit.",
    )
    warn_at: float = Field(
        0.8, gt=0, lt=1, title="Warn at", description="The share of a limit at which you are told once, such as 0.8."
    )


class VisionSettings(Settings):
    """The model that reads images on the CPU, in the vision slot (design 0008 §7)."""

    KIND = "vision"
    LABEL = "Vision"
    HELP = (
        "The model that reads images on the CPU: off, loaded only when an image is to be read (and unloaded when "
        "idle), or always loaded; how long it stays idle before it is unloaded; and its preset."
    )
    SINGLE = True

    mode: Literal["off", "on-demand", "always"] = Field(
        "on-demand",
        title="Mode",
        description="off: no image is read (annotations go as words, the agent's model is told it takes text only); "
        "on-demand: loaded when an image is to be read, unloaded when idle; always: loaded and kept.",
    )
    idle_minutes: int = Field(
        10, ge=1, le=1440, title="Idle", description="Minutes without use after which an on-demand model is unloaded."
    )
    preset: str = Field("vision", title="Preset", description="The preset the vision slot loads.")
