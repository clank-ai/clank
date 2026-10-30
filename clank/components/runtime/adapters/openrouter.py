"""OpenRouter, the first cloud provider (design 0016 §2-§3, §6; decision 0102): one key reaches the major models through
one OpenAI-compatible API at `https://openrouter.ai/api/v1`.

Every fact here was read in OpenRouter's public documentation on 2026-10-20 (design 0016 §3 names each page); what it
does not say is marked to be checked with a real key (§18). Its record may say only its own URL, the reach `cloud` and
the key sent as a bearer token; its options are `data_collection` (`deny` by default: only providers that keep no data,
decision 0109) and `zdr` (only zero-data-retention providers, off by default).

- **The list** (`GET /models`): each model's id exactly as listed, its window (the smaller of `context_length` and
  `top_provider.context_length`), its most output, its string prices per token as numbers per million, whether it
  thinks (`reasoning` among its parameters), reads images, takes tool calls; free models (`:free`) with their limits.
- **The account** (`GET /key`): the key's label, limit and what is left (`null`: none), its use (UTC days), the budget
  that refuses first.
- **A cloud preset's options** (design 0016 §7): its context at most the model's window, its most output at most the
  model's and at most half the context, its thinking effort one the model lists; written, or changed later, so.
- **A request** (decision 0109): as the tool sent it, its `model` the listed id; `provider` (the record's data policy)
  and `reasoning` (the preset's effort) added only where the tool set none; the key as a bearer token, and the
  session's id as `x-session-id` for OpenRouter's prompt cache; no attribution header, no `usage` field.
- **A refusal** (decision 0110): OpenRouter's words, then Clank's of what to do; which OpenCode must not retry. Its
  words for a full context are not declared until a real key shows them (`FULL`, design 0016 §18).
- **Cost** (decision 0108): `usage.cost`, else an estimate from the tokens at the model's prices, labeled as one; a
  stream cut short has its generation's `total_cost` afterward.
"""

import copy
import json
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any, ClassVar

from clank.components.runtime.adapters.endpoint import (
    Account,
    Cost,
    EndpointAdapter,
    ModelLine,
    ProviderOption,
    Refusal,
)
from clank.components.runtime.adapters.engine import ContextFacts
from clank.kernel.adapters import Capability

EFFORTS = ("max", "xhigh", "high", "medium", "low", "minimal", "none")  # its reasoning efforts (design 0016 §3)
MAX_OUTPUT = 16384  # a cloud preset's output unless the model's most is smaller (design 0016 §6)
FREE_LIMITS = "20 a minute, 50 a day; 1,000 a day once 10 credits were bought"
PRESET_OPTIONS = ("context", "max_output", "reasoning", "images")
KEY_ADVICE = (
    "OpenRouter refused the key: it may have been deleted or disabled. Set a new one: Providers and models, k; or "
    "clank endpoint key openrouter"
)
CREDITS_ADVICE = (
    "Your OpenRouter credits are used up, or this key's own limit is reached: add credits or raise the key's limit at "
    "openrouter.ai, then ask again"
)
POLICY_WORDS = ("data policy", "privacy")  # OpenRouter's words when no provider of a model meets a data policy
PRIVACY = "openrouter.ai/settings/privacy"  # the account's own data policy, which Clank cannot change
DENY_ADVICE = (
    "No provider of {named} serves it with data_collection deny: pick another model, or allow it on the Providers page "
    "(o), or test with any provider in dev mode (clank dev on)"
)
ACCOUNT_ADVICE = (
    f"OpenRouter refuses {{named}} under your OpenRouter account's privacy settings ({PRIVACY}): allow its providers "
    "there, or pick another model"
)
DAILY_WORDS = ("per-day", "per day")  # its words for a free model's daily limit (free-models-per-day)
DAILY_ADVICE = (
    "OpenRouter's free models take 50 requests a day until 10 credits were bought, then 1,000; the count starts again "
    "at midnight UTC: wait, add credits at openrouter.ai, or pick a paid model"
)


class OpenRouter(EndpointAdapter):
    """OpenRouter's API."""

    NAME = "openrouter"
    LABEL = "OpenRouter"
    URL: ClassVar[str] = "https://openrouter.ai/api/v1"
    REACH = "cloud"
    AUTH = "bearer"
    FULL: ClassVar[tuple[str, ...]] = ()  # its words for a full context: to be checked with a real key (§18)

    @classmethod
    def provider_options(cls) -> list[ProviderOption]:
        """`data_collection` and `zdr`, OpenRouter's provider routing (design 0016 §3)."""
        return [
            ProviderOption(
                "data_collection",
                "Data collection",
                "deny: only the model's providers that keep no data (fewer models answer); allow: any provider.",
                "deny",
                ("deny", "allow"),
            ),
            ProviderOption("zdr", "Zero data retention", "Only providers that retain no data at all.", False),
        ]

    def capabilities(self) -> list[Capability]:
        """What OpenRouter's API gives Clank, as its documentation says (design 0016 §3)."""
        return [
            Capability("tool calls", True, "tools, tool_choice, streamed delta.tool_calls"),
            Capability("thinking", True, "streamed as delta.reasoning"),
            Capability("usage", True, "in the stream's last message"),
            Capability("cost", True, "usage.cost, in US dollars"),
            Capability("infill", False, "completion stays on this machine (design 0006)"),
        ]

    def models_query(self, sort: str, *, everything: bool = False) -> dict[str, str]:
        """Tool models (`supported_parameters=tools`) unless `everything`; most used first (`sort=most-popular`, over
        every model: OpenRouter refuses `category` beside `supported_parameters`, and `category=programming` alone
        gives its first twenty, as its public list answered on 2026-10-28); other sorts are Clank's own, over the whole
        list."""
        query = {} if everything else {"supported_parameters": "tools"}
        if sort == "most-popular":
            query["sort"] = "most-popular"
        return query

    def models(self, answer: Mapping[str, Any], *, everything: bool = False) -> list[ModelLine]:
        """`GET /models`' `data`, read into Clank's lines; a router priced per request (OpenRouter writes -1) is left
        out, since what one of its requests costs cannot be said before it is sent (design 0016 §11)."""
        lines = [_line(model) for model in answer.get("data") or [] if isinstance(model, dict) and model.get("id")]
        priced = [line for line in lines if line.price_in >= 0 and line.price_out >= 0]
        return [line for line in priced if line.tools or everything]

    def account(self, answer: Mapping[str, Any]) -> Account:
        """`GET /key`'s `data`."""
        data = answer.get("data") if isinstance(answer.get("data"), dict) else answer
        assert isinstance(data, Mapping)
        return Account(
            label=str(data.get("label") or ""),
            limit_usd=_money(data.get("limit")),
            remaining_usd=_money(data.get("limit_remaining")),
            limit_reset=data.get("limit_reset") or None,
            used_today_usd=_money(data.get("usage_daily")) or 0.0,
            used_week_usd=_money(data.get("usage_weekly")) or 0.0,
            used_month_usd=_money(data.get("usage_monthly")) or 0.0,
            free_tier=bool(data.get("is_free_tier")),
            budget=_budget(data),
            expires_at=data.get("expires_at") or None,
        )

    def preset_options(self, model: ModelLine, wanted: Mapping[str, Any]) -> dict[str, Any]:
        """Its context (at most the model's window), its output (16,384 or the model's most when smaller, and at most
        half the context: the agent keeps room for a whole answer in every request, design 0016 §7), its thinking
        effort (`default`, or one the model lists, else one of OpenRouter's seven) and whether it reads images (the
        model's)."""
        problems = self.option_problems(wanted)
        if problems:
            raise ValueError("; ".join(problems))
        most = model.output or MAX_OUTPUT
        context = int(wanted.get("context") or model.window)
        if context > model.window:
            raise ValueError(f"context is at most {model.window:,} for {model.id}, not {context:,}")
        half = context // 2 or most
        output = int(wanted.get("max_output") or max(1, min(MAX_OUTPUT, most, half)))
        if output > most:
            raise ValueError(f"max_output is at most {most:,} for {model.id}, not {output:,}")
        if output > half:
            raise ValueError(
                f"max_output is at most half the context ({half:,} of {context:,}), not {output:,}: the agent keeps "
                "room for a whole answer in every request, and the conversation needs the rest"
            )
        reasoning = str(wanted.get("reasoning") or "default")
        if reasoning != "default" and model.efforts and reasoning not in model.efforts:
            raise ValueError(f"reasoning is default or one of {', '.join(model.efforts)} for {model.id}")
        return {"context": context, "max_output": output, "reasoning": reasoning, "images": model.images}

    def option_problems(self, options: Mapping[str, Any]) -> list[str]:
        """Each option known and its value of the right sort."""
        problems = []
        for key, value in options.items():
            if key not in PRESET_OPTIONS:
                problems.append(f"{self.NAME} has no preset option {key}")
            elif key in ("context", "max_output") and (isinstance(value, bool) or not isinstance(value, int)):
                problems.append(f"{key} is a whole number of tokens, not {value!r}")
            elif key in ("context", "max_output") and value < 1:
                problems.append(f"{key} is at least 1, not {value}")
            elif key == "reasoning" and value not in ("default", *EFFORTS):
                problems.append(f"reasoning is one of {', '.join(('default', *EFFORTS))}, not {value!r}")
            elif key == "images" and not isinstance(value, bool):
                problems.append(f"images is true or false, not {value!r}")
        return problems

    def adds(self, options: Mapping[str, Any], reasoning: str) -> dict[str, Any]:
        """`provider.data_collection` (and `zdr` when on) from the record; `reasoning.effort` when the preset sets
        one."""
        provider: dict[str, Any] = {"data_collection": str(options.get("data_collection") or "deny")}
        if options.get("zdr") is True:
            provider["zdr"] = True
        found: dict[str, Any] = {"provider": provider}
        if reasoning and reasoning != "default":
            found["reasoning"] = {"effort": reasoning}
        return found

    def translate(
        self, body: Mapping[str, Any], model: str, adds: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        """The request as the tool sent it, its model the listed id; `reasoning` added where it set none (decision
        0109); the record's data policy (`provider`) always: added, or merged into a provider object the tool sent, the
        stricter word kept (`deny` over `allow`, `zdr` on over off), so no request loosens it."""
        sent = copy.deepcopy(dict(body))
        sent["model"] = model
        notes = []
        source = str(adds.get("provider_from") or "the provider's record")  # dev mode's, while it is on (decision 0149)
        provider = adds.get("provider")
        own = body.get("provider")
        if isinstance(provider, Mapping) and isinstance(own, Mapping):
            merged = {**own, **_stricter(own, provider)}
            sent["provider"] = merged
            changed = {key: value for key, value in merged.items() if own.get(key, _ABSENT) != value}
            if changed:
                said = ", ".join(f"provider.{key} {_word(value)}" for key, value in changed.items())
                notes.append(f"{said} merged ({source})")
        elif isinstance(provider, Mapping):
            sent["provider"] = dict(provider)
            said = ", ".join(f"provider.{key} {_word(value)}" for key, value in provider.items())
            notes.append(f"{said} added ({source})")
        reasoning = adds.get("reasoning")
        if isinstance(reasoning, Mapping) and "reasoning" not in body:
            sent["reasoning"] = dict(reasoning)
            notes.append(f"reasoning.effort {reasoning.get('effort')} added (the preset's thinking effort)")
        return sent, notes

    def headers(self, key: str, session: str) -> dict[str, str]:
        """The bearer key, and `x-session-id` when the tool named its session (OpenRouter's cache keeps a session on
        one provider, which lowers its cost); never an attribution header (decision 0109)."""
        found = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if session:
            found["x-session-id"] = session
        return found

    def refusal(self, status: int, body: bytes, *, model: str = "", denied: bool = False) -> Refusal:
        """Design 0016 §8's table: OpenRouter's words, then what to do; OpenCode retries only a timeout, a limit of
        requests but a free model's daily one, a model down, and no provider when the record allows any. No provider
        under a data policy, by its words or a 503 under `deny`, is the record's to change (`denied`) or the account's
        (OpenRouter names its privacy settings, or the request allowed any provider)."""
        said = _said(body)
        named = model or "the model"
        lowered = said.lower()
        if status in (404, 503) and (any(words in lowered for words in POLICY_WORDS) or (status == 503 and denied)):
            account = ACCOUNT_ADVICE.format(named=named)
            advice = DENY_ADVICE.format(named=named) if denied else account
            if denied and "privacy" in lowered:
                advice = f"{advice}; and allow its providers in your OpenRouter account's privacy settings ({PRIVACY})"
            return Refusal(status, "data_policy", said, advice, False)
        if status == 401:
            return Refusal(status, "key_refused", said, KEY_ADVICE, False)
        if status == 402:
            return Refusal(status, "no_credits", said, CREDITS_ADVICE, False)
        if status == 403:
            return Refusal(status, "refused", "", f"OpenRouter refused this request: {said}", False)
        if status == 404:
            advice = (
                f"OpenRouter lists no model {named}; it may have been retired (its expiration_date). Pick another: "
                "Add a model, or clank endpoint models openrouter"
            )
            return Refusal(status, "no_model", said, advice, False)
        if status == 413:
            return Refusal(status, "too_large", said, "The request is larger than OpenRouter takes", False)
        if status in (408, 524):
            return Refusal(status, "timed_out", said, "", True)
        if status == 429 and any(words in lowered for words in DAILY_WORDS):
            return Refusal(status, "free_limit", said, DAILY_ADVICE, False)
        if status == 429:
            return Refusal(status, "rate_limited", said, "", True)
        if status in (502, 529):
            return Refusal(status, "model_down", said, "", True)
        if status == 503:
            return Refusal(status, "no_provider", said, "", True)
        if status >= 500:
            return Refusal(status, "refused", said, "", True)
        return Refusal(status, "bad_request" if status == 400 else "refused", said, "", False)

    def says_full(self, status: int, body: bytes) -> bool:
        """None of its words are known yet (design 0016 §18): such a refusal passes on as OpenRouter said it."""
        text = body.decode("utf-8", errors="replace")
        return status == 400 and any(words in text for words in self.FULL)

    def cost(self, usage: Mapping[str, Any] | None, tokens: Mapping[str, int], prices: Mapping[str, Any]) -> Cost:
        """`usage.cost` (OpenRouter's own figure, its cache discounts and thinking included), else the tokens counted
        at the model's prices: input not cached, input cached (at its cache price, else the input price), and output
        with thinking (thinking is billed as output)."""
        found = usage.get("cost") if usage else None
        if isinstance(found, int | float) and not isinstance(found, bool):
            return Cost(float(found), "usage", dict(tokens))
        price_in = float(prices.get("in") or 0.0)
        price_out = float(prices.get("out") or 0.0)
        cached_price = prices.get("cached_in")
        cached_in = float(cached_price) if cached_price is not None else price_in
        taken, cached = int(tokens.get("in") or 0), int(tokens.get("cached") or 0)
        out = int(tokens.get("out") or 0) + int(tokens.get("thinking") or 0)
        usd = max(taken - cached, 0) * price_in + cached * cached_in + out * price_out
        return Cost(usd, "estimate", dict(tokens))

    def context_facts(self, model: ModelLine, options: Mapping[str, Any], read: str) -> ContextFacts:
        """What the Monitor reads of a cloud model's context (design 0016 §13): its window (the smaller of the
        preset's and the model's), its most output; no thinking budget (an effort is not one), no exact window (the
        provider attends the whole, as far as anyone outside it knows), nothing on this machine's GPU, no count of
        tokens, no one conversation; its figures read from OpenRouter's usage; its words for a full context once a
        real key showed them (none yet); where it was read."""
        window = min(int(options.get("context") or model.window), model.window)
        output = int(options.get("max_output") or min(MAX_OUTPUT, model.output or MAX_OUTPUT))
        return ContextFacts(
            window=window, output=output, thinking_budget=None, exact=None, on_gpu=False, counts_tokens=False,
            one_conversation=False,
            fields={"prompt": "usage.prompt_tokens", "output": "usage.completion_tokens",
                    "cached": "usage.prompt_tokens_details.cached_tokens"},
            full="; ".join(self.FULL), source=f"{self.LABEL}'s list, read {read}",
        )  # fmt: skip

    def generation_cost(self, answer: Mapping[str, Any]) -> float | None:
        """`GET /generation`'s `data.total_cost`."""
        data = answer.get("data")
        found = data.get("total_cost") if isinstance(data, Mapping) else None
        return float(found) if isinstance(found, int | float) and not isinstance(found, bool) else None


def _line(model: Mapping[str, Any]) -> ModelLine:
    """One model of the list, as Clank's line: its window the smaller of the two it gives, a zero saying nothing (a few
    models give 0 beside their provider's real window)."""
    top = model.get("top_provider") if isinstance(model.get("top_provider"), dict) else {}
    assert isinstance(top, dict)
    given = (model.get("context_length"), top.get("context_length"))
    windows = [value for value in given if isinstance(value, int) and not isinstance(value, bool) and value > 0]
    pricing = model.get("pricing") if isinstance(model.get("pricing"), dict) else {}
    assert isinstance(pricing, dict)
    parameters = [str(name) for name in model.get("supported_parameters") or []]
    reasoning = model.get("reasoning") if isinstance(model.get("reasoning"), dict) else {}
    assert isinstance(reasoning, dict)
    architecture = model.get("architecture") if isinstance(model.get("architecture"), dict) else {}
    assert isinstance(architecture, dict)
    free = str(model["id"]).endswith(":free")
    most = top.get("max_completion_tokens")
    return ModelLine(
        id=str(model["id"]),
        name=str(model.get("name") or model["id"]),
        description=str(model.get("description") or ""),
        window=min(windows) if windows else 0,
        output=most if isinstance(most, int) else None,
        price_in=_per_million(pricing.get("prompt")) or 0.0,
        price_out=_per_million(pricing.get("completion")) or 0.0,
        price_cached_in=_per_million(pricing.get("input_cache_read")),
        price_request=_money(pricing.get("request")) or 0.0,
        thinking="reasoning" in parameters,
        efforts=tuple(str(each) for each in reasoning.get("supported_efforts") or []),
        images="image" in (architecture.get("input_modalities") or []),
        tools="tools" in parameters,
        free=free,
        limits=FREE_LIMITS if free else "",
        retires=model.get("expiration_date") or None,
        created=int(model.get("created") or 0),
    )


def _per_million(value: object) -> float | None:
    """A price per token, as OpenRouter writes it (a string of US dollars), per million tokens; None when not given."""
    if value is None or value == "":
        return None
    try:
        return float(Decimal(str(value)) * 1_000_000)
    except InvalidOperation:
        return None


def _money(value: object) -> float | None:
    """US dollars as a number; None when not given."""
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        return float(Decimal(str(value)))
    except InvalidOperation:
        return None


def _budget(data: Mapping[str, Any]) -> dict[str, Any] | None:
    """The budget that refuses first: `effective_budget`, else the one of `budgets` with the least left."""
    found = data.get("effective_budget")
    if not isinstance(found, dict):
        budgets = [each for each in data.get("budgets") or [] if isinstance(each, dict)]
        found = min(budgets, key=lambda each: _money(each.get("remaining_usd")) or 0.0) if budgets else None
    if not isinstance(found, dict):
        return None
    return {
        "scope": str(found.get("scope") or ""),
        "remaining_usd": _money(found.get("remaining_usd")) or 0.0,
        "resets_at": found.get("resets_at") or None,
    }


def _said(body: bytes) -> str:
    """OpenRouter's own words in a refusal: its error's message, else its text."""
    try:
        found = json.loads(body)
    except ValueError:
        return body.decode("utf-8", errors="replace").strip()
    error = found.get("error") if isinstance(found, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    return str(error or found or "")


_ABSENT = object()


def _stricter(own: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, Any]:
    """The record's data policy against a provider object the tool sent: for each of its fields, the stricter word."""
    found: dict[str, Any] = {}
    if "data_collection" in record:
        denied = "deny" in (record.get("data_collection"), own.get("data_collection"))
        found["data_collection"] = "deny" if denied else record["data_collection"]
    if "zdr" in record:
        found["zdr"] = bool(record.get("zdr")) or own.get("zdr") is True
    return found


def _word(value: object) -> str:
    return ("true" if value else "false") if isinstance(value, bool) else str(value)
