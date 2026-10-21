"""The endpoint adapter kind (design 0016 §6, design 0015 §3): one module per provider someone else runs, reached at
its URL with the owner's key, every one with the same interface, so the next provider meets it too (decision 0102).

An endpoint adapter fixes what its record may say (`URL`, `REACH`, `AUTH`: a cloud provider's own address, so the key
never goes elsewhere) and the provider options it takes (`provider_options`); `template` is the record Add a model and
`clank endpoint add` write. What it reads of the provider's answers and writes into its requests comes with it (design
0016 §6), so nothing in the gateway, the slots or the console names a provider but through its adapter.
"""

from abc import abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, ClassVar, Literal

from clank.components.runtime.adapters.engine import ContextFacts
from clank.kernel.adapters import Adapter

Place = tuple[str | int, ...]
TIMEOUT_SECONDS = 600
How = Literal["usage", "generation", "estimate"]


@dataclass(frozen=True)
class ProviderOption:
    """One of a provider's own options, kept in its record's `options` (design 0016 §4): a choice among words, or a
    switch (no choices: true or false)."""

    key: str
    label: str
    help: str
    default: str | bool
    choices: tuple[str, ...] = ()

    def problem(self, value: object) -> str | None:
        """What is wrong with a value for this option, or None."""
        if self.choices:
            return None if value in self.choices else f"is one of {', '.join(self.choices)}, not {value!r}"
        return None if isinstance(value, bool) else f"is true or false, not {value!r}"


@dataclass(frozen=True)
class ModelLine:
    """A model a provider lists, as Clank shows it (design 0016 §6): its id exactly as listed, its window and most
    output, its prices per million tokens (in, out, cached in; `request` per request), whether it thinks (and the
    efforts it takes), reads images and takes tool calls, whether it is free and its limits then, when it retires."""

    id: str
    name: str
    description: str
    window: int
    output: int | None
    price_in: float
    price_out: float
    price_cached_in: float | None
    price_request: float
    thinking: bool
    efforts: tuple[str, ...]
    images: bool
    tools: bool
    free: bool
    limits: str
    retires: str | None
    created: int = 0

    def view(self) -> dict[str, Any]:
        """The line as clients read it (plan s34's interface)."""
        return {
            "id": self.id, "name": self.name, "description": self.description, "window": self.window,
            "output": self.output,
            "price": {"in": self.price_in, "out": self.price_out, "cached_in": self.price_cached_in,
                      "request": self.price_request},
            "thinking": self.thinking, "efforts": list(self.efforts), "images": self.images, "tools": self.tools,
            "free": self.free, "limits": self.limits, "retires": self.retires,
        }  # fmt: skip

    def prices(self) -> dict[str, float | None]:
        """Its prices per token, as a route carries them for estimates (design 0016 §12)."""
        cached = self.price_cached_in / 1e6 if self.price_cached_in is not None else None
        return {"in": self.price_in / 1e6, "out": self.price_out / 1e6, "cached_in": cached}


@dataclass(frozen=True)
class Account:
    """A key's own facts, as its provider counts them (design 0016 §6): its label, its limit and what is left (None:
    no limit), its use today, this week and this month (the provider's days), whether it is a free-tier key, the
    budget that refuses first (its scope, what is left, when it resets) and when the key expires."""

    label: str
    limit_usd: float | None
    remaining_usd: float | None
    limit_reset: str | None
    used_today_usd: float
    used_week_usd: float
    used_month_usd: float
    free_tier: bool
    budget: dict[str, Any] | None
    expires_at: str | None
    days: str = "UTC"

    def view(self, read_at: str) -> dict[str, Any]:
        """The account as clients read it (plan s34's interface), with when it was read."""
        return {
            "label": self.label, "limit_usd": self.limit_usd, "remaining_usd": self.remaining_usd,
            "limit_reset": self.limit_reset, "used_today_usd": self.used_today_usd,
            "used_week_usd": self.used_week_usd, "used_month_usd": self.used_month_usd, "free_tier": self.free_tier,
            "budget": self.budget, "expires_at": self.expires_at, "read_at": read_at, "days": self.days,
        }  # fmt: skip


@dataclass(frozen=True)
class Refusal:
    """What a provider's refusal means (design 0016 §8): its status, Clank's code for it, the provider's own words
    (`said`), Clank's words of what to do (`advice`), whether OpenCode may retry it, and the wait the provider asked."""

    status: int
    code: str
    said: str
    advice: str
    retried: bool
    retry_after: str | None = None

    @property
    def message(self) -> str:
        """The provider's words, then Clank's."""
        return f"{self.said}: {self.advice}" if self.advice and self.said else self.advice or self.said


@dataclass(frozen=True)
class Cost:
    """What a request cost, in US dollars, and how it is known: the provider's own figure in its usage, its record of
    the request afterward, or an estimate from the tokens counted at the model's prices."""

    usd: float
    how: How
    tokens: dict[str, int] = field(default_factory=dict)


class EndpointAdapter(Adapter):
    """A provider someone else runs, reached at its URL."""

    PLATFORMS: ClassVar[tuple[str, ...]] = ("win32", "linux", "darwin")
    URL: ClassVar[str] = ""  # its API's base URL; a test points it at its fake
    REACH: ClassVar[str] = "cloud"
    AUTH: ClassVar[str] = "bearer"

    @classmethod
    def provider_options(cls) -> list[ProviderOption]:
        """The options its record may hold, with their defaults."""
        return []

    @classmethod
    def template(cls) -> dict[str, Any]:
        """Its record as Clank writes it first: its own URL, reach and auth, its options' defaults, not agreed."""
        return {
            "title": cls.LABEL,
            "adapter": cls.NAME,
            "url": cls.URL,
            "auth": cls.AUTH,
            "reach": cls.REACH,
            "options": {option.key: option.default for option in cls.provider_options()},
            "timeout_seconds": TIMEOUT_SECONDS,
        }

    @classmethod
    def record_problems(cls, values: Mapping[str, Any]) -> list[tuple[Place, str]]:
        """What its record says that it does not take: a URL other than its own, another reach or auth, options it
        does not have or values they do not take; each with the place of the field."""
        found: list[tuple[Place, str]] = []
        for name, own in (("url", cls.URL), ("reach", cls.REACH), ("auth", cls.AUTH)):
            if values.get(name) != own:
                found.append(((name,), f"{cls.NAME} takes {own} only, not {values.get(name)!r}"))
        known = {option.key: option for option in cls.provider_options()}
        for key, value in dict(values.get("options") or {}).items():
            option = known.get(key)
            if option is None:
                found.append((("options", key), f"{cls.NAME} takes no option {key}; it takes {', '.join(known)}"))
            elif (problem := option.problem(value)) is not None:
                found.append((("options", key), f"{key} {problem}"))
        return found

    @abstractmethod
    def models_query(self, sort: str, *, everything: bool = False) -> dict[str, str]:
        """What the list of models is asked with (its query): the models that take tool calls unless `everything`,
        in the provider's own order when `sort` is one it sorts by."""

    @abstractmethod
    def models(self, answer: Mapping[str, Any], *, everything: bool = False) -> list[ModelLine]:
        """The provider's list of models read into Clank's lines; only those that take tool calls unless `everything`
        (the agent cannot work without tool calls)."""

    @abstractmethod
    def account(self, answer: Mapping[str, Any]) -> Account:
        """The key's own facts, from the provider's answer about it."""

    @abstractmethod
    def preset_options(self, model: ModelLine, wanted: Mapping[str, Any]) -> dict[str, Any]:
        """A cloud preset's options for a model (design 0016 §7): those wanted, else the model's; `ValueError`, in
        words, for one the model does not take."""

    @abstractmethod
    def option_problems(self, options: Mapping[str, Any]) -> list[str]:
        """What is wrong with a cloud preset's options, without its model, one sentence each."""

    @abstractmethod
    def adds(self, options: Mapping[str, Any], reasoning: str) -> dict[str, Any]:
        """What the gateway adds to each request where the tool set none (design 0016 §8): from the record's
        provider options and the preset's thinking effort."""

    @abstractmethod
    def translate(
        self, body: Mapping[str, Any], model: str, adds: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        """A request as the provider takes it: as the tool sent it, its `model` the listed id, `adds` added where the
        tool set none; a note for each addition; the request given is not changed."""

    @abstractmethod
    def headers(self, key: str, session: str) -> dict[str, str]:
        """The headers of a request to it: the key, and the session for its cache when there is one."""

    @abstractmethod
    def refusal(self, status: int, body: bytes, *, model: str = "", denied: bool = False) -> Refusal:
        """What a refusal of this status and body means, in words that say what to do (`denied`: the record allows
        only providers that keep no data)."""

    @abstractmethod
    def says_full(self, status: int, body: bytes) -> bool:
        """Whether a refusal is the model's context being full (decision 0090)."""

    @abstractmethod
    def cost(self, usage: Mapping[str, Any] | None, tokens: Mapping[str, int], prices: Mapping[str, Any]) -> Cost:
        """A request's cost: the provider's own figure in its usage, else an estimate from `tokens` (`in`, `cached`,
        `out`, `thinking`) at the model's `prices` per token."""

    @abstractmethod
    def context_facts(self, model: ModelLine, options: Mapping[str, Any], read: str) -> "ContextFacts":
        """What the Monitor reads of a cloud model's context for a preset's options (design 0016 §13), read from the
        model's line (`read`: when the list was read)."""

    @abstractmethod
    def generation_cost(self, answer: Mapping[str, Any]) -> float | None:
        """A request's cost from the provider's record of it afterward; None while it has none."""
