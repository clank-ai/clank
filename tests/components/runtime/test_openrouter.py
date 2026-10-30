"""Design 0016 §3, §6 and §8: what the OpenRouter adapter reads of OpenRouter's answers and writes into its requests.

Its model line keeps only models that take tool calls unless asked, takes the smaller of a model's two windows (a zero,
which OpenRouter gives a few models beside their provider's real one, says nothing), turns OpenRouter's string prices
per token into numbers per million, leaves out a router priced per request (-1: what a request costs cannot be said
before it is sent), and marks free models with their limits; the list is asked for most used first with
`sort=most-popular`, never with `category` beside `supported_parameters`, which OpenRouter refuses (its public list,
2026-10-28); the account
reads `GET /key` (no limit read as none); a request goes as the tool sent it with the listed id as its model, the
preset's thinking effort added only where the tool set none, and the record's data policy always (merged into a
provider object the tool sent, the stricter word kept), nothing else changed; the
headers carry the bearer key and the session for OpenRouter's cache; each refusal gets words that say what to do and
whether OpenCode may retry it; and a request's cost is OpenRouter's own figure, else an estimate that says so."""

import json
from typing import Any

import pytest

from clank.components.runtime.adapters.openrouter import OpenRouter

KEY = "made-up-openrouter-key"
CODER: dict[str, Any] = {
    "id": "example-vendor/example-coder",
    "canonical_slug": "example-vendor/example-coder-2026",
    "name": "Example Coder",
    "created": 1790000000,
    "description": "A made-up model for coding. It writes code.",
    "context_length": 262144,
    "architecture": {"modality": "text->text", "input_modalities": ["text"], "output_modalities": ["text"]},
    "pricing": {"prompt": "0.0000003", "completion": "0.0000012", "request": "0", "input_cache_read": "0.00000003"},
    "top_provider": {"context_length": 200000, "max_completion_tokens": 32768, "is_moderated": False},
    "supported_parameters": ["max_tokens", "tools", "tool_choice", "reasoning"],
    "reasoning": {"mandatory": False, "default_effort": "medium", "supported_efforts": ["low", "medium", "high"]},
    "expiration_date": None,
}
FREE = {
    **CODER,
    "id": "example-vendor/example-small:free",
    "name": "Example Small (free)",
    "context_length": 32768,
    "architecture": {"input_modalities": ["text", "image"], "output_modalities": ["text"]},
    "pricing": {"prompt": "0", "completion": "0"},
    "top_provider": {"context_length": None, "max_completion_tokens": None, "is_moderated": False},
    "supported_parameters": ["tools"],
    "reasoning": {"mandatory": False},
    "expiration_date": "2026-12-31",
}
CHATTY = {**CODER, "id": "example-vendor/example-chat", "name": "Example Chat", "supported_parameters": ["max_tokens"]}
LISTED = {"data": [CODER, FREE, CHATTY], "total_count": 3, "links": {"next": None}}


@pytest.fixture
def openrouter() -> OpenRouter:
    return OpenRouter()


def test_the_list_keeps_tool_models_unless_asked_with_the_smaller_window_and_prices_per_million(
    openrouter: OpenRouter,
) -> None:
    lines = openrouter.models(LISTED)
    assert [line.id for line in lines] == ["example-vendor/example-coder", "example-vendor/example-small:free"]
    assert [line.id for line in openrouter.models(LISTED, everything=True)][-1] == "example-vendor/example-chat"
    coder = lines[0].view()
    assert coder == {
        "id": "example-vendor/example-coder",
        "name": "Example Coder",
        "description": "A made-up model for coding. It writes code.",
        "window": 200000,
        "output": 32768,
        "price": {"in": 0.3, "out": 1.2, "cached_in": 0.03, "request": 0.0},
        "thinking": True,
        "efforts": ["low", "medium", "high"],
        "images": False,
        "tools": True,
        "free": False,
        "limits": "",
        "retires": None,
    }
    assert lines[0].prices() == pytest.approx({"in": 3e-7, "out": 1.2e-6, "cached_in": 3e-8})


def test_a_free_model_is_marked_with_its_limits_and_its_retirement(openrouter: OpenRouter) -> None:
    free = openrouter.models(LISTED)[1].view()
    assert (free["free"], free["window"], free["output"], free["images"], free["thinking"]) == (
        True, 32768, None, True, False
    )  # fmt: skip
    assert free["limits"] == "20 a minute, 50 a day; 1,000 a day once 10 credits were bought"
    assert free["retires"] == "2026-12-31"
    assert free["price"]["cached_in"] is None


def test_the_models_are_asked_for_with_tools_most_used_first_and_never_with_a_category_beside_them(
    openrouter: OpenRouter,
) -> None:
    assert openrouter.models_query("most-popular") == {"supported_parameters": "tools", "sort": "most-popular"}
    assert openrouter.models_query("price") == {"supported_parameters": "tools"}
    assert openrouter.models_query("most-popular", everything=True) == {"sort": "most-popular"}
    for sort in ("most-popular", "price", "context", "newest"):
        for everything in (False, True):
            asked = openrouter.models_query(sort, everything=everything)
            assert not ("category" in asked and "supported_parameters" in asked), "OpenRouter refuses both (400)"


def test_the_account_reads_the_keys_own_facts_and_no_limit_as_none(openrouter: OpenRouter) -> None:
    answer = {
        "data": {
            "label": "my laptop key", "limit": 20, "limit_remaining": 18.71, "limit_reset": "monthly", "usage": 1.29,
            "usage_daily": 0.12, "usage_weekly": 0.5, "usage_monthly": 1.29, "is_free_tier": False,
            "budgets": [
                {"scope": "member", "limit_usd": 50, "spend_usd": 32.5, "remaining_usd": 17.5,
                 "resets_at": "2026-10-26T00:00:00Z"},
                {"scope": "api_key", "limit_usd": 5, "spend_usd": 5, "remaining_usd": 0,
                 "resets_at": "2026-10-22T00:00:00Z"},
            ],
            "effective_budget": {"scope": "api_key", "limit_usd": 5, "spend_usd": 5, "remaining_usd": 0,
                                 "resets_at": "2026-10-22T00:00:00Z"},
            "expires_at": None,
        }
    }  # fmt: skip
    view = openrouter.account(answer).view("2026-10-21T09:14:00.000Z")
    assert view == {
        "label": "my laptop key",
        "limit_usd": 20.0,
        "remaining_usd": 18.71,
        "limit_reset": "monthly",
        "used_today_usd": 0.12,
        "used_week_usd": 0.5,
        "used_month_usd": 1.29,
        "free_tier": False,
        "budget": {"scope": "api_key", "remaining_usd": 0.0, "resets_at": "2026-10-22T00:00:00Z"},
        "expires_at": None,
        "read_at": "2026-10-21T09:14:00.000Z",
        "days": "UTC",
    }
    unlimited = openrouter.account({"data": {"label": "", "limit": None, "limit_remaining": None, "usage": 0}})
    assert (unlimited.limit_usd, unlimited.remaining_usd, unlimited.budget, unlimited.used_today_usd) == (
        None, None, None, 0.0
    )  # fmt: skip


OPENCODE_ASKS: dict[str, Any] = {
    "model": "agent",
    "stream": True,
    "stream_options": {"include_usage": True},
    "max_tokens": 16384,
    "tools": [{"type": "function", "function": {"name": "bash", "parameters": {"type": "object"}}}],
    "messages": [
        {"role": "system", "content": "You are an agent."},
        {"role": "user", "content": "Read the file."},
        {"role": "assistant", "content": "", "reasoning_content": "I should read it.",
         "tool_calls": [{"id": "call_1", "type": "function", "function": {"name": "bash", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "call_1", "content": "made-up output"},
    ],
}  # fmt: skip


def test_a_request_goes_as_the_tool_sent_it_with_the_listed_id_and_the_records_policy(openrouter: OpenRouter) -> None:
    adds = openrouter.adds({"data_collection": "deny", "zdr": False}, "default")
    assert adds == {"provider": {"data_collection": "deny"}}
    sent, notes = openrouter.translate(OPENCODE_ASKS, "example-vendor/example-coder", adds)
    assert sent == {**OPENCODE_ASKS, "model": "example-vendor/example-coder", "provider": {"data_collection": "deny"}}
    assert notes == ["provider.data_collection deny added (the provider's record)"]
    assert OPENCODE_ASKS["model"] == "agent", "the request given is not changed"
    assert "usage" not in sent


def test_the_presets_effort_and_zdr_are_added_only_where_the_tool_set_none(openrouter: OpenRouter) -> None:
    adds = openrouter.adds({"data_collection": "allow", "zdr": True}, "high")
    assert adds == {"provider": {"data_collection": "allow", "zdr": True}, "reasoning": {"effort": "high"}}
    sent, notes = openrouter.translate(OPENCODE_ASKS, "example-vendor/example-coder", adds)
    assert (sent["provider"], sent["reasoning"]) == ({"data_collection": "allow", "zdr": True}, {"effort": "high"})
    assert len(notes) == 2
    own = {**OPENCODE_ASKS, "provider": {"order": ["a-provider"]}, "reasoning": {"effort": "low"}}
    sent, notes = openrouter.translate(own, "example-vendor/example-coder", adds)
    assert (sent["provider"], sent["reasoning"]) == (
        {"order": ["a-provider"], "data_collection": "allow", "zdr": True}, {"effort": "low"})  # fmt: skip
    assert notes == ["provider.data_collection allow, provider.zdr true merged (the provider's record)"]


def test_a_provider_object_the_tool_sent_never_loosens_the_records_data_policy(openrouter: OpenRouter) -> None:
    adds = openrouter.adds({"data_collection": "deny", "zdr": False}, "default")
    loose = {**OPENCODE_ASKS, "provider": {"order": ["a-provider"], "data_collection": "allow", "zdr": False}}
    sent, _ = openrouter.translate(loose, "example-vendor/example-coder", adds)
    assert sent["provider"] == {"order": ["a-provider"], "data_collection": "deny", "zdr": False}
    strict = {**OPENCODE_ASKS, "provider": {"data_collection": "deny", "zdr": True}}
    allowing = openrouter.adds({"data_collection": "allow", "zdr": False}, "default")
    sent, _ = openrouter.translate(strict, "example-vendor/example-coder", allowing)
    assert sent["provider"] == {"data_collection": "deny", "zdr": True}, "the stricter word kept"
    odd = {**OPENCODE_ASKS, "provider": "not an object"}
    sent, _ = openrouter.translate(odd, "example-vendor/example-coder", adds)
    assert sent["provider"] == {"data_collection": "deny"}


def test_the_headers_carry_the_bearer_key_and_the_session_for_openrouters_cache(openrouter: OpenRouter) -> None:
    assert openrouter.headers(KEY, "ses_made_up") == {
        "Authorization": f"Bearer {KEY}", "Content-Type": "application/json", "x-session-id": "ses_made_up"
    }  # fmt: skip
    assert "x-session-id" not in openrouter.headers(KEY, "")


def said(code: int, message: str) -> bytes:
    return json.dumps({"error": {"code": code, "message": message}}).encode()


@pytest.mark.parametrize(
    ("status", "code", "words", "retried"),
    [
        (401, "key_refused", "OpenRouter refused the key: it may have been deleted or disabled. Set a new one", False),
        (402, "no_credits", "Your OpenRouter credits are used up, or this key's own limit is reached", False),
        (403, "refused", "OpenRouter refused this request: Flagged by moderation", False),
        (404, "no_model", "OpenRouter lists no model example-vendor/example-coder; it may have been retired", False),
        (413, "too_large", "The request is larger than OpenRouter takes", False),
        (429, "rate_limited", "Rate limited upstream", True),
        (502, "model_down", "Model is down", True),
        (408, "timed_out", "Timed out", True),
    ],
)
def test_each_refusal_says_what_to_do_and_whether_opencode_may_retry_it(
    openrouter: OpenRouter, status: int, code: str, words: str, retried: bool
) -> None:
    upstream = {401: "No auth credentials found", 402: "Insufficient credits", 403: "Flagged by moderation",
                404: "No endpoints found", 413: "Payload too large", 429: "Rate limited upstream",
                502: "Model is down", 408: "Timed out"}  # fmt: skip
    refusal = openrouter.refusal(status, said(status, upstream[status]), model="example-vendor/example-coder")
    assert (refusal.status, refusal.code, refusal.retried) == (status, code, retried)
    assert words in refusal.message
    assert upstream[status] in refusal.message, "OpenRouter's own words are kept"


def test_no_provider_under_deny_says_how_to_allow_it_and_is_not_retried(openrouter: OpenRouter) -> None:
    for status in (503, 404):
        body = said(status, "No endpoints found matching your data policy")
        denied = openrouter.refusal(status, body, model="example-vendor/example-coder", denied=True)
        assert (denied.code, denied.retried) == ("data_policy", False), status
        assert "No provider of example-vendor/example-coder serves it with data_collection deny" in denied.message
        assert "Providers page (o)" in denied.message
        assert "dev mode (clank dev on)" in denied.message
    unsaid = openrouter.refusal(
        503, said(503, "No provider available"), model="example-vendor/example-coder", denied=True
    )
    assert (unsaid.code, unsaid.retried) == ("data_policy", False), "a 503 under deny, whatever its words"
    allowed = openrouter.refusal(503, said(503, "No provider available"), model="example-vendor/example-coder")
    assert (allowed.code, allowed.retried) == ("no_provider", True)


def test_a_data_policy_refusal_under_allow_points_to_the_accounts_privacy_settings(openrouter: OpenRouter) -> None:
    words = "No endpoints found matching your data policy (Free model training). Configure: https://openrouter.ai/settings/privacy"
    for status in (404, 503):
        refusal = openrouter.refusal(status, said(status, words), model="example-vendor/example-small:free")
        assert (refusal.code, refusal.retried) == ("data_policy", False), status
        assert refusal.message.startswith(words), "OpenRouter's own words first"
        assert "your OpenRouter account's privacy settings (openrouter.ai/settings/privacy)" in refusal.message
    denied = openrouter.refusal(404, said(404, words), model="example-vendor/example-small:free", denied=True)
    assert "openrouter.ai/settings/privacy" in denied.message, "named by OpenRouter: Clank's own policy is not all"
    assert "dev mode (clank dev on)" in denied.message


def test_a_free_models_daily_limit_is_not_retried_and_says_when_it_starts_again(openrouter: OpenRouter) -> None:
    words = "Rate limit exceeded: free-models-per-day. Add 10 credits to unlock 1000 free model requests per day"
    daily = openrouter.refusal(429, said(429, words), model="example-vendor/example-small:free")
    assert (daily.code, daily.retried) == ("free_limit", False)
    assert daily.message.startswith(words)
    assert "50 requests a day until 10 credits were bought, then 1,000" in daily.message
    assert "midnight UTC" in daily.message
    minute = openrouter.refusal(429, said(429, "Rate limit exceeded: free-models-per-min."), model="x:free")
    assert (minute.code, minute.retried) == ("rate_limited", True), "a minute's limit passes: OpenCode waits"


def test_no_full_context_words_are_declared_until_a_real_key_shows_them(openrouter: OpenRouter) -> None:
    assert not openrouter.says_full(400, said(400, "This endpoint's maximum context length is 1 tokens"))


def test_a_requests_cost_is_openrouters_figure_else_an_estimate_that_says_so(openrouter: OpenRouter) -> None:
    usage = {"prompt_tokens": 194, "completion_tokens": 2, "total_tokens": 196, "cost": 0.000095}
    prices = {"in": 3e-7, "out": 1.2e-6, "cached_in": 3e-8}
    found = openrouter.cost(usage, {}, prices)
    assert (found.usd, found.how) == (0.000095, "usage")
    tokens = {"in": 1000, "cached": 800, "out": 100, "thinking": 50}
    estimate = openrouter.cost(None, tokens, prices)
    assert estimate.how == "estimate"
    assert estimate.usd == pytest.approx(200 * 3e-7 + 800 * 3e-8 + 150 * 1.2e-6)
    no_cache_price = openrouter.cost({"prompt_tokens": 10}, {"in": 10, "out": 0}, {"in": 1e-6, "out": 0.0})
    assert no_cache_price.usd == pytest.approx(1e-5)
    assert no_cache_price.how == "estimate"


def test_a_generations_record_gives_its_total_cost(openrouter: OpenRouter) -> None:
    assert openrouter.generation_cost({"data": {"id": "gen-made-up", "total_cost": 0.0123}}) == 0.0123
    assert openrouter.generation_cost({"data": {"id": "gen-made-up"}}) is None


def test_a_presets_options_follow_the_model(openrouter: OpenRouter) -> None:
    [coder, free] = openrouter.models(LISTED)
    assert openrouter.preset_options(coder, {}) == {
        "context": 200000, "max_output": 16384, "reasoning": "default", "images": False
    }  # fmt: skip
    assert openrouter.preset_options(free, {"context": 16384}) == {
        "context": 16384, "max_output": 16384, "reasoning": "default", "images": True
    }  # fmt: skip
    small = openrouter.models({"data": [{**CODER, "top_provider": {"max_completion_tokens": 8192}}]})[0]
    assert openrouter.preset_options(small, {})["max_output"] == 8192
    assert openrouter.preset_options(coder, {"reasoning": "high"})["reasoning"] == "high"
    with pytest.raises(ValueError, match="at most 200,000"):
        openrouter.preset_options(coder, {"context": 300000})
    with pytest.raises(ValueError, match="low, medium, high"):
        openrouter.preset_options(coder, {"reasoning": "xhigh"})
    assert openrouter.option_problems({"context": 8192, "max_output": 4096, "reasoning": "none"}) == []
    assert openrouter.option_problems({"reasoning": "loud", "speed": 3}) == [
        "reasoning is one of default, max, xhigh, high, medium, low, minimal, none, not 'loud'",
        "openrouter has no preset option speed",
    ]


# Two lines of OpenRouter's public list (2026-10-28), cut to what the line reads.
ZERO_WINDOW: dict[str, Any] = {
    "id": "openai/gpt-oss-safeguard-20b", "name": "OpenAI: gpt-oss-safeguard-20b", "context_length": 0,
    "top_provider": {"context_length": 131072, "max_completion_tokens": 65536, "is_moderated": False},
    "pricing": {"prompt": "0.000000075", "completion": "0.0000003", "input_cache_read": "0.0000000375"},
    "supported_parameters": ["tools", "tool_choice", "reasoning"],
}  # fmt: skip
ROUTER: dict[str, Any] = {
    "id": "openrouter/auto", "name": "Auto Router", "context_length": 2000000,
    "top_provider": {"context_length": None, "max_completion_tokens": None, "is_moderated": False},
    "pricing": {"prompt": "-1", "completion": "-1"}, "supported_parameters": ["tools", "tool_choice"],
}  # fmt: skip


def test_a_window_of_zero_beside_the_providers_real_one_says_nothing(openrouter: OpenRouter) -> None:
    line = openrouter.models({"data": [ZERO_WINDOW]})[0]
    assert line.window == 131072
    assert openrouter.option_problems(openrouter.preset_options(line, {})) == [], "its preset can be written"


def test_a_router_priced_per_request_is_left_out_since_its_cost_cannot_be_said_before(openrouter: OpenRouter) -> None:
    assert openrouter.models({"data": [ROUTER, CODER]}) == openrouter.models({"data": [CODER]})
    assert [line.id for line in openrouter.models({"data": [ROUTER]}, everything=True)] == []
