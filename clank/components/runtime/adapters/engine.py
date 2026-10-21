"""The engine adapter kind (design 0001 §2, design 0003 §4): one module per serving setup, every one with the same
interface, so a setup plugs in with one file, its recordings and a line in `ENGINES` (decision 0010).

An adapter is made for one version of its engine, whose support it declares (`EngineVersion.supports`: how many
requests at once, vision, speculation), since what an engine can do is read for its version, never assumed (design 0002
§2.10). `options()` lists the version's launch options, each with the fields of design 0001 §3.1. An option says, for
each value, exactly what the engine receives (`EngineOption.maps`): flags on its command line, and environment variables
written `env:NAME=VALUE`; `{value}` stands for the value and `{name}` for a fact of the launch (the projector's path,
say). The command line is made from those declarations alone, so what the console shows an option maps to is what runs.
A flag is left out when the value is the engine's own default (`engine_default`), so a plan reads at a glance. An
option with no default of Clank's, left unset, gives the engine nothing; where one value cannot say what the engine
then does (a default per thinking mode, or one a model file may replace), the option says it in words
(`engine_default_words`, design 0003 §4.1), and a value set is given even when one of those defaults has it.

`validate` says what is wrong with a preset's options, one sentence each; `plan` gives the exact launch (argv,
environment, folder, port) and the memory it is expected to take, as a breakdown; `ready` and `memory_report` read the
engine's own words in its log.

`context_facts` declares what the engine does with its context for a preset's options (design 0012 §4, decision
0067), so the Monitor reads every figure of the context window from the loaded slot and never from one engine's
numbers: a new engine brings its facts with its adapter, and the Monitor does not change.
"""

import copy
from abc import abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, ClassVar, Literal, cast

from clank.kernel.adapters import Adapter, Capability

OptionValue = int | float | str | bool
OptionKind = Literal["integer", "number", "choice", "switch", "text"]
ANY = "*"


class EngineError(Exception):
    """A preset the engine cannot run as it is: an unknown version, option or value."""


@dataclass(frozen=True)
class EngineVersion:
    """A version of an engine the adapter was written for, and what it supports."""

    name: str
    supports: Mapping[str, str]
    source: str = ""


@dataclass(frozen=True)
class EngineOption:
    """One launch option (design 0001 §3.1)."""

    key: str
    label: str
    help: str
    kind: OptionKind
    default: OptionValue | None
    maps: Mapping[str, tuple[str, ...]]
    choices: tuple[str, ...] = ()
    minimum: float | None = None
    maximum: float | None = None
    unit: str = ""
    scope: Literal["launch", "request"] = "launch"
    memory: str = ""
    requires: tuple[str, ...] = ()
    tested: tuple[OptionValue, ...] = ()
    engine_default: OptionValue | None = None
    # What the engine does when it is not given the option, in words, where one value cannot say it: a default per
    # mode ("1.0 thinking, 0.7 not thinking"), or one a model file may replace (design 0003 §4.1, decision 0119).
    engine_default_words: str = ""
    more_than: float | None = None  # a bound the value must pass, not reach (a repeat penalty above 0)

    def problem(self, value: object) -> str | None:
        """What is wrong with a value for this option, or None."""
        if self.kind == "switch":
            return None if isinstance(value, bool) else f"{self.key} is on or off (true or false), not {value!r}"
        if self.kind == "choice":
            if value in self.choices:
                return None
            return f"{self.key} is one of {', '.join(self.choices)}, not {value!r}"
        if self.kind == "text":
            return None if isinstance(value, str) else f"{self.key} is text, not {value!r}"
        if isinstance(value, bool) or not isinstance(value, int | float):
            allowed = f" or one of {', '.join(self.choices)}" if self.choices else ""
            if isinstance(value, str) and value in self.choices:
                return None
            return f"{self.key} is a number{allowed}, not {value!r}"
        if self.kind == "integer" and not float(value).is_integer():
            return f"{self.key} is a whole number, not {value}"
        if self.minimum is not None and value < self.minimum:
            return f"{self.key} is at least {_number(self.minimum)}{_unit(self.unit)}, not {_number(value)}"
        if self.maximum is not None and value > self.maximum:
            return f"{self.key} is at most {_number(self.maximum)}{_unit(self.unit)}, not {_number(value)}"
        if self.more_than is not None and value <= self.more_than:
            return f"{self.key} is more than {_number(self.more_than)}{_unit(self.unit)}, not {_number(value)}"
        return None

    def mapped(self, value: OptionValue) -> tuple[str, ...]:
        """What the engine receives for a value: its flags and `env:` entries, `{value}` filled in."""
        text = _text(value)
        found = self.maps.get(text, self.maps.get(ANY, ()))
        return tuple(part.replace("{value}", text) for part in found)

    def maps_to(self) -> str:
        """What the option maps to, as the console shows it: `-c {value}`, or each value's flags."""
        if set(self.maps) == {ANY}:
            return " ".join(self.maps[ANY])
        return "; ".join(f"{value}: {' '.join(parts) or '(nothing)'}" for value, parts in self.maps.items())


@dataclass(frozen=True)
class MemoryEstimate:
    """The GPU memory a launch is expected to take, as a breakdown the user can read (design 0001 §3.6). An engine that
    sizes its KV cache itself says so (`kv_auto`), with what one token of KV takes, the headroom it keeps free beside
    it, and how many tokens its KV cache can grow by into what is left (`kv_more_tokens`); its `kv_mib` is then the
    least it takes. `learned_mib` is what the last launch of the engine on its host took beyond (or below) the
    adapter's own estimate (design 0001 §3.6, learning). An engine that runs on the CPU (`on_gpu` false: llama.cpp's
    CPU build for completion) estimates the system memory it takes in the same fields, and takes none of the GPU."""

    weights_mib: int
    kv_mib: int
    buffers_mib: int
    overhead_mib: int
    notes: tuple[str, ...] = ()
    kv_auto: bool = False
    kv_bytes_per_token: float = 0.0
    kv_headroom_mib: int = 0
    kv_more_tokens: int = 0
    learned_mib: int = 0
    on_gpu: bool = True

    @property
    def total_mib(self) -> int:
        """Everything together."""
        return self.weights_mib + self.kv_mib + self.buffers_mib + self.overhead_mib + self.learned_mib


@dataclass(frozen=True)
class Launch:
    """What a plan needs besides the preset: the command that runs the engine (its program's path, after anything
    that runs it, such as `nice`, or a test's fake engine), its model's file on the host, its port, the facts its
    options' mappings name (`facts`: the projector's path, the install's folder), the model's sizes the memory
    estimate needs (`sizes`, from the catalog: its weights on the GPU, its attention layers, its KV width)."""

    program: tuple[str, ...]
    model_path: str
    port: int
    address: str = "127.0.0.1"
    facts: Mapping[str, str] = field(default_factory=dict)
    sizes: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class Plan:
    """Exactly what would run, and the memory it is expected to take."""

    argv: tuple[str, ...]
    env: Mapping[str, str]
    cwd: str
    port: int
    memory: MemoryEstimate

    def command_line(self) -> str:
        """The command as one line, its environment first, as the console shows it."""
        variables = [f"{name}={value}" for name, value in sorted(self.env.items())]
        return " ".join([*variables, *(_quoted(part) for part in self.argv)])


@dataclass(frozen=True)
class ExactWindow:
    """The part of its window an engine attends to exactly on the GPU, when that is less than the whole (design 0012
    §4.4, KVMem's retrieval): how many tokens, in blocks of how many, the first block always kept, and how it picks the
    other blocks."""

    tokens: int
    block: int
    first: int
    picks: str


@dataclass(frozen=True)
class ContextFacts:
    """What an engine does with its context, for a preset's options (design 0012 §4, decision 0067): its window and
    the most tokens one answer may have; the most tokens of thinking, when it limits them (`None`: thinking off, no
    limit, or no such option); the part it attends to exactly (`None`: the whole window); whether it runs on the GPU;
    whether it can count tokens (a route such as llama.cpp's `/tokenize`); whether it keeps one conversation, so that
    another's request makes it read the next one again; where its answer reports each figure (`fields`: `prompt`,
    `output`, `cached`, `timings`, each a dotted path into the answer, such as `usage.prompt_tokens`; a figure it does
    not report has none); how it says the context is full ("" while not known); and where these facts were read."""

    window: int
    output: int
    thinking_budget: int | None
    exact: ExactWindow | None
    on_gpu: bool
    counts_tokens: bool
    one_conversation: bool
    fields: Mapping[str, str]
    full: str
    source: str

    def view(self) -> dict[str, Any]:
        """The facts as JSON."""
        return {**asdict(self), "fields": dict(self.fields)}


class EngineAdapter(Adapter):
    """A serving setup's engine, at one of the versions its adapter was written for."""

    PLATFORMS: ClassVar[tuple[str, ...]] = ("linux",)
    PROGRAM: ClassVar[str] = ""
    FORMAT: ClassVar[str] = ""
    VERSIONS: ClassVar[tuple[EngineVersion, ...]] = ()
    FULL: ClassVar[tuple[str, ...]] = ()  # words of its refusal (HTTP 400) of a request its context cannot hold
    # The route that counts a text's tokens, as llama.cpp's `/tokenize` takes it (`{"content": ...}`, answering its
    # `tokens`); "" for an engine that cannot count (its context facts' `counts_tokens`, decision 0087).
    TOKENIZE: ClassVar[str] = ""

    def __init__(self, version: str) -> None:
        self.version = self.known(version)

    @classmethod
    def known(cls, version: str) -> EngineVersion:
        """The version of that name, or `EngineError` naming the versions known."""
        for known in cls.VERSIONS:
            if known.name == version:
                return known
        names = ", ".join(known.name for known in cls.VERSIONS)
        raise EngineError(f"{cls.LABEL} has no adapter for version {version}; the known ones: {names}")

    def capabilities(self) -> list[Capability]:
        """What this version supports, as its adapter declares it."""
        return [Capability(name, value != "no", value) for name, value in self.version.supports.items()]

    @abstractmethod
    def options(self) -> list[EngineOption]:
        """Every launch option of this version, in the order the command line takes them."""

    @abstractmethod
    def plan(self, options: Mapping[str, OptionValue], launch: Launch) -> Plan:
        """The exact launch of a preset's options, and its memory estimate."""

    @abstractmethod
    def ready(self, line: str) -> bool:
        """Whether a line of the engine's log says it is ready for requests."""

    @abstractmethod
    def memory_report(self, lines: Sequence[str]) -> dict[str, float]:
        """What the engine says it allocated, in MiB, by name, read from its log."""

    @abstractmethod
    def context_facts(self, options: Mapping[str, OptionValue]) -> ContextFacts:
        """What the engine does with its context for a preset's options (its own, else Clank's defaults)."""

    def says_full(self, status: int, body: bytes) -> bool:
        """Whether an answer of this status and body is the engine's refusal of a request its context cannot hold
        (design 0012 §4.1, decision 0090): a 400 that holds its words (`FULL`); never, for an engine whose words are
        not known."""
        text = body.decode("utf-8", errors="replace")
        return status == 400 and any(words in text for words in self.FULL)

    def translate(self, body: Mapping[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """A request as this engine takes it (design 0001 §6.3): fields it names its own way renamed, fields it refuses
        left out, a note for each change; the request given is not changed. Most engines take it as it is."""
        return copy.deepcopy(dict(body)), []

    def needed_mib(self, lines: Sequence[str], free_before_mib: int) -> int | None:
        """The GPU memory the engine needed free to start, from what its log says, when it says (an engine that
        reserves more than it touches); None for one that does not."""
        return None

    def option(self, key: str) -> EngineOption:
        """The option of that key, or `EngineError`."""
        for found in self.options():
            if found.key == key:
                return found
        raise EngineError(f"{self.LABEL} {self.version.name} has no option {key}")

    def validate(self, options: Mapping[str, object]) -> list[str]:
        """What is wrong with a preset's options, one sentence each; an empty list when nothing is."""
        known = {option.key: option for option in self.options()}
        problems = [f"{self.LABEL} {self.version.name} has no option {key}" for key in options if key not in known]
        good: dict[str, OptionValue] = {}
        for key, value in options.items():
            if key not in known:
                continue
            if (problem := known[key].problem(value)) is not None:
                problems.append(problem)
            else:
                good[key] = cast(OptionValue, value)
        resolved = self.resolved(good)
        for key in good:
            problems += [f"{key} needs {needed}" for needed in _unmet(known[key], resolved)]
        return problems

    def resolved(self, options: Mapping[str, OptionValue]) -> dict[str, OptionValue]:
        """Every option's value: the preset's, else Clank's default for this engine."""
        values: dict[str, OptionValue] = {}
        for option in self.options():
            value = options.get(option.key, option.default)
            if value is not None:
                values[option.key] = value
        return values

    def receives(self, option: EngineOption, values: Mapping[str, OptionValue]) -> tuple[tuple[str, ...], str]:
        """What the engine receives for an option among resolved values (its flags and `env:` entries, facts not yet
        filled in), or nothing and why: no value, the engine's own default, or a requirement the values do not meet."""
        if option.key not in values:
            return (), "no value"
        value = values[option.key]
        if option.engine_default is not None and _text(value) == _text(option.engine_default):
            return (), "the engine's own default"
        unmet = _unmet(option, values)
        if unmet:
            return (), f"needs {', '.join(unmet)}"
        return option.mapped(value), ""

    def arguments(
        self, options: Mapping[str, OptionValue], facts: Mapping[str, str]
    ) -> tuple[list[str], dict[str, str]]:
        """The flags and environment of a preset's options: each option's mapping of its value, in the order of
        `options()`, left out when the value is the engine's own default, or when it is a default whose requirement
        the preset does not meet (the image tokens of an engine whose preset turns vision off)."""
        problems = self.validate(options)
        if problems:
            raise EngineError("; ".join(problems))
        argv: list[str] = []
        env: dict[str, str] = {}
        resolved = self.resolved(options)
        for option in self.options():
            parts, _ = self.receives(option, resolved)
            for part in parts:
                for name, fact in facts.items():
                    part = part.replace("{" + name + "}", fact)
                if part.startswith("env:"):
                    name, _, setting = part.removeprefix("env:").partition("=")
                    env[name] = setting
                else:
                    argv.append(part)
        return argv, env


UNSET = (None, False, "off", "none", 0)


def _unmet(option: EngineOption, values: Mapping[str, OptionValue]) -> list[str]:
    """The requirements of an option set to something that the other values do not meet."""
    if values.get(option.key) in UNSET:
        return []
    unmet = []
    for needed in option.requires:
        key, _, wanted = needed.partition("=")
        have = values.get(key)
        if (wanted and _text(have) != wanted) or (not wanted and have in UNSET):
            unmet.append(needed)
    return unmet


def flags(option: EngineOption) -> list[str]:
    """The command-line flags an option can give the engine (what its `--help` must show)."""
    return sorted({part for parts in option.maps.values() for part in parts if part.startswith("-")})


def _text(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _number(value: float) -> str:
    return f"{value:,.0f}" if float(value).is_integer() else f"{value:g}"


def _unit(unit: str) -> str:
    return f" {unit}" if unit else ""


def _quoted(part: str) -> str:
    return f"'{part}'" if any(char in part for char in " \"'$") else part
