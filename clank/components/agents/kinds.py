"""The agents component's kinds of record (design 0004 §5): the VS Code window's settings, `config/vscode.json`, what
each of the Monitor's Watch for rules does, `config/monitor.json` (design 0012 §8, decision 0053), and what Clank tells
OpenCode of its model, `config/opencode.json` (design 0012 §4.1, decision 0089). Modes (plan, ask, auto), sessions and
the rest of each program's own settings come with the rest of M5 (design 0002 §1, design 0004 §8).
"""

from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from clank.components.agents.watchfor.rules import RULES as WATCH_RULES
from clank.kernel.records import Settings

EXTENSIONS = (
    "ms-python.python",
    "ms-python.vscode-pylance",
    "ms-python.debugpy",
    "charliermarsh.ruff",
    "ms-toolsai.jupyter",
    "leanprover.lean4",
    "james-yu.latex-workshop",
    "tomoki1207.pdf",
    "mechatroner.rainbow-csv",
    "yzhang.markdown-all-in-one",
    "bierner.markdown-mermaid",
    "tamasfe.even-better-toml",
)


class VsCodeSettings(Settings):
    """Clank's VS Code window: the program, the extensions it has besides Clank's, and this PC's SSH name."""

    KIND = "vscode"
    LABEL = "VS Code window"
    HELP = (
        "Clank's VS Code window, a separate instance of VS Code (its settings and extensions under CLANK_HOME/vscode, "
        "the main one untouched): which program runs it, and the extensions it has besides Clank's own."
    )
    SINGLE = True
    ON_CHANGE = "now"  # read each time a folder is opened

    program: list[str] = Field(
        default_factory=list,
        title="Program",
        description=(
            "VS Code's command line and any arguments before VS Code's own; empty: `code` found on the PATH (on "
            "Windows, the program its code.cmd runs)."
        ),
    )
    extensions: list[str] = Field(
        default_factory=lambda: list(EXTENSIONS),
        title="Extensions",
        description=(
            "The extensions installed in the window when missing, by their marketplace ids (publisher.name), besides "
            "Clank's own: Python, Pylance, the debugger, Ruff, Jupyter, Lean 4, LaTeX Workshop, a PDF viewer, Rainbow "
            "CSV, Markdown All in One, Mermaid and Even Better TOML."
        ),
    )
    ssh_host: str = Field(
        "",
        title="SSH host",
        description=(
            "This PC's name in the SSH configuration of the computer you work from (design 0018 §8): over SSH, outside "
            "VS Code's Remote-SSH, Clank says the command that opens a folder there with it; empty: the address the "
            "SSH session came in on."
        ),
    )


class OpenCodeSettings(Settings):
    """What Clank tells OpenCode of the model it works with (design 0012 §4.1, decision 0089)."""

    KIND = "opencode"
    LABEL = "OpenCode"
    HELP = (
        "What Clank tells OpenCode of its model: how much of the engine's window is kept free for one step's tool "
        "results, so that OpenCode compacts a session before a step's results can make its next request too long for "
        "the engine."
    )
    SINGLE = True
    ON_CHANGE = "next start"
    NEXT_START = "OpenCode's next start in a workspace (its configuration is written then)"

    context_margin: int = Field(
        16384,
        ge=0,
        title="Context margin",
        description=(
            "Tokens of the engine's window OpenCode is not told of, kept free for one step's tool results. OpenCode "
            "compacts a session once a step's total reaches the window it is told less its output limit; the step's "
            "tool results then go with the next request, which the engine refuses when it and the answer's room pass "
            "its window (262,144 less 16,384 less 16,384: OpenCode compacts at 229,376 tokens). The default holds one "
            "tool output as OpenCode cuts it (51,200 bytes or 2,000 lines) of code or prose, about 13,000 tokens; one "
            "of digits or a long listing can take up to 49,000, and several results in a step add up: then the "
            "gateway tells OpenCode the context was full, and OpenCode compacts. At most a quarter of the window is "
            "kept; 0 tells OpenCode the whole window. The Monitor shows the engine's window and the line OpenCode "
            "compacts at."
        ),
    )


Action = Literal["mark", "pause", "tell the phone", "tell the model"]
MARKED = "Clank's Monitor marked this in your session: {why}."
GO_ON = "Take it into account, and go on."


def _marks() -> list[Action]:
    """A rule's actions by default: the mark alone."""
    return ["mark"]


def _no_default(schema: dict[str, Any]) -> None:
    """A field the schema shows with no default of its own (each rule's default shows its own)."""
    schema.pop("default", None)


class RuleSettings(BaseModel):
    """What one Watch for rule does when it fires, and the words of its note (design 0012 §8)."""

    model_config = ConfigDict(extra="forbid")

    do: list[Action] = Field(
        default_factory=_marks,
        title="Does",
        description=(
            "What the rule does when it fires: mark (the mark alone: on its node in the session's flow, in the "
            "Monitor's Watch for panel and beside Monitor in the menu), pause (the session, after its step), tell the "
            "phone (the phone page lists the mark with what waits), tell the model (a note in the rule's words, and "
            "the session goes on). A rule that does anything marks too; an empty list turns the rule off."
        ),
    )
    note: str = Field(
        "",
        title="Note",
        description="What the model is told when the rule tells it, sent as a message of yours; {why} is replaced by "
        "what the mark rests on.",
        json_schema_extra=_no_default,  # each rule's own words are its default
    )

    @field_validator("do")
    @classmethod
    def _each_once(cls, value: list[Action]) -> list[Action]:
        if len(set(value)) != len(value):
            raise ValueError("each action at most once")
        return value


def _rule(name: str, do: list[Action], note: str) -> Any:
    """A rule's field: its title, when it fires (`watchfor/rules.py`, design 0012 §8's table), and what it does by
    default, which the schema shows too (pydantic copies the default for each settings read)."""
    rule = WATCH_RULES[name]
    return Field(
        RuleSettings(do=list(do), note=note),
        title=rule.title,
        description=f"When: {rule.fires}. By default: {', '.join(do) or 'off'}; a key left out keeps its default.",
    )


class MonitorSettings(Settings):
    """What each of the Monitor's Watch for rules does when it fires (design 0012 §8, decision 0053)."""

    KIND = "monitor"
    LABEL = "Monitor: Watch for"
    HELP = (
        "The Monitor's Watch for rules, run in the service over each session's flow whether or not a console is open: "
        "for each rule, what it does when it fires (mark it, pause the session, tell the phone, tell the model and go "
        "on) and the words it tells the model; and how many notes in a row one rule may send before it calls you."
    )
    SINGLE = True
    ON_CHANGE = "now"  # read each time the rules run
    RULES: ClassVar[tuple[str, ...]] = tuple(WATCH_RULES)  # in design 0012 §8's order

    waiting_for_you: RuleSettings = _rule(
        "waiting_for_you", ["mark", "tell the phone"],
        f"{MARKED} The owner will answer it.",
    )  # fmt: skip
    engine_broke_off: RuleSettings = _rule(
        "engine_broke_off", ["mark"],
        f"{MARKED} That answer is not in your context; go on from where you were.",
    )  # fmt: skip
    loop_guard_stopped: RuleSettings = _rule(
        "loop_guard_stopped", ["mark", "tell the model"],
        "Clank's loop guard stopped your last answer because it repeated itself, and that answer is not in your "
        "context. Go on from where you were, without writing it the same way again.",
    )  # fmt: skip
    answer_cut: RuleSettings = _rule(
        "answer_cut", ["mark", "tell the model"],
        f"{MARKED} Go on from where you were: think more briefly, and take the work in smaller steps (a long file in "
        "parts).",
    )  # fmt: skip
    asks_about_a_repeat: RuleSettings = _rule(
        "asks_about_a_repeat", ["mark", "tell the phone"],
        f"{MARKED} Try another way instead of making the same call again.",
    )  # fmt: skip
    same_call_again: RuleSettings = _rule(
        "same_call_again", ["mark"],
        f"{MARKED} Its result will not change; try another way.",
    )  # fmt: skip
    failing_again: RuleSettings = _rule(
        "failing_again", ["mark"],
        f"{MARKED} Step back and find why before trying again.",
    )  # fmt: skip
    one_file_again: RuleSettings = _rule(
        "one_file_again", ["mark"],
        f"{MARKED} Read the file whole before editing it again.",
    )  # fmt: skip
    call_then_step_failed: RuleSettings = _rule(
        "call_then_step_failed", ["mark"],
        f"{MARKED} A file may have changed without your knowing; check it before going on.",
    )  # fmt: skip
    stopped_with_an_ask_waiting: RuleSettings = _rule(
        "stopped_with_an_ask_waiting", ["mark"],
        f"{MARKED} {GO_ON}",
    )  # fmt: skip
    note_not_read: RuleSettings = _rule(
        "note_not_read", ["mark"],
        f"{MARKED} {GO_ON}",
    )  # fmt: skip
    retrying: RuleSettings = _rule(
        "retrying", ["mark"],
        f"{MARKED} {GO_ON}",
    )  # fmt: skip
    compaction_near: RuleSettings = _rule(
        "compaction_near", ["mark"],
        f"{MARKED} Finish what you are doing in as few steps as you can.",
    )  # fmt: skip
    budget_near: RuleSettings = _rule(
        "budget_near", ["mark"],
        f"{MARKED} Keep your thinking and your answers shorter.",
    )  # fmt: skip
    engine_taken: RuleSettings = _rule(
        "engine_taken", ["mark"],
        f"{MARKED} {GO_ON}",
    )  # fmt: skip
    notes_in_a_row: int = Field(
        2,
        ge=0,
        le=10,
        title="Notes in a row",
        description=(
            "The most notes one rule sends the model in a row in a session, counted again from your own next "
            "message; after that the rule marks, pauses and tells the phone (decision 0053)."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def _rules_in_part(cls, data: Any) -> Any:
        """A rule given in part keeps its own defaults for the rest: only `do` keeps its note's words, only `note`
        keeps what it does."""
        if not isinstance(data, dict):
            return data
        filled = dict(data)
        for name in cls.RULES:
            given = filled.get(name)
            if isinstance(given, dict):
                default = cls.model_fields[name].get_default(call_default_factory=True)
                filled[name] = {**default.model_dump(), **given}
        return filled

    def rule(self, name: str) -> RuleSettings:
        """The settings of the rule of that name."""
        if name not in self.RULES:
            raise KeyError(f"there is no Watch for rule named {name!r}")
        found: RuleSettings = getattr(self, name)
        return found
