"""Record what OpenRouter answers Clank's fixed made-up requests (design 0016 §18, design 0015 §14), with the owner's
key, into `tests/fixtures/openrouter/<date>/http.json`, which the endpoint contract then runs over beside the documented
shapes. Never in CI: the owner runs it once a key is at hand.

    CLANK_TEST_OPENROUTER_KEY=... uv run python -m tools.capture_endpoint [--model ID] [--thinking-model ID]

The key is read from the environment variable, typed for the run (never an argument, never stored), sent only to
OpenRouter, and never written: the recording holds no request's headers. What the account says of the owner is replaced
by made-up values (the key's label, its limit and use, the ids of its creator, organization and workspace), and the
fields Clank does not read whose British spelling the repository refuses (`LEFT_OUT`) are left out; the recording's
`how` says so. The requests are Clank's own made-up words only, to the cheapest model that takes tool calls unless one
is named. What cannot be asked for on demand (no credits, a budget, a limit of requests, no provider under the data
policy, a stream broken mid-way) stays the documented shapes' alone."""

import json
import os
import sys
import time
from datetime import date
from pathlib import Path
from typing import Any

import httpx2

URL = "https://openrouter.ai/api/v1"
VARIABLE = "CLANK_TEST_OPENROUTER_KEY"
MADE_UP_KEY = "made-up-openrouter-key"
FOLDER = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "openrouter"
TINY = [{"role": "user", "content": "Reply with OK."}]
TOOL = {
    "type": "function",
    "function": {
        "name": "made_up_lookup",
        "description": "Look up a made-up word.",
        "parameters": {"type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"]},
    },
}
POLICY = {"data_collection": "deny"}
ACCOUNT_MADE_UP = {
    "label": "made-up key label", "limit": 20, "limit_remaining": 18.71, "usage": 1.29, "usage_daily": 0.12,
    "usage_weekly": 0.5, "usage_monthly": 1.29, "byok_usage": 0, "byok_usage_daily": 0, "byok_usage_weekly": 0,
    "byok_usage_monthly": 0, "creator_user_id": None, "organization_id": None, "workspace_id": None,
}  # fmt: skip
LEFT_OUT = ("cancelled",)  # spelling: keep (OpenRouter's own field, which Clank does not read, left out of recordings)


def main(argv: list[str] | None = None) -> int:
    """Ask, record, write; returns the exit status."""
    args = list(sys.argv[1:] if argv is None else argv)
    key = os.environ.get(VARIABLE, "").strip()
    if not key:
        print(f"set {VARIABLE} for this run (typed, never stored) to the key to record with", file=sys.stderr)
        return 2
    named = _option(args, "--model")
    thinking = _option(args, "--thinking-model")
    with httpx2.Client(base_url=URL, headers={"Authorization": f"Bearer {key}"}, timeout=120) as client:
        recording = capture(client, named, thinking)
    folder = FOLDER / date.today().isoformat()
    folder.mkdir(parents=True, exist_ok=True)
    text = json.dumps(recording, indent=2, ensure_ascii=False) + "\n"
    if key in text:
        print("the key appears in what was answered: nothing written", file=sys.stderr)
        return 1
    (folder / "http.json").write_bytes(text.encode("utf-8"))
    print(f"wrote {folder / 'http.json'}: {len(recording['exchanges'])} exchanges")
    return 0


def capture(client: httpx2.Client, named: str, thinking: str) -> dict[str, Any]:
    """Each of Clank's fixed made-up requests, and what OpenRouter answered."""
    exchanges: list[dict[str, Any]] = []

    def ask(name: str, method: str, path: str, query: dict[str, str] | None = None, body: Any = None) -> Any:
        answer = client.request(method, path, params=query, json=body)
        exchanges.append(_exchange(name, method, path, query, body, answer))
        return answer

    ask("key", "GET", "/key")
    ask("models", "GET", "/models", {"supported_parameters": "tools", "category": "programming",
                                     "sort": "most-popular"})  # fmt: skip
    every = ask("every model", "GET", "/models").json().get("data") or []
    model = named or _cheapest(every)
    ask("answer", "POST", "/chat/completions", body={"model": model, "messages": TINY, "max_tokens": 16,
                                                     "provider": POLICY})  # fmt: skip
    streamed = ask("stream", "POST", "/chat/completions", body={"model": model, "messages": TINY, "max_tokens": 16,
                                                                 "provider": POLICY, "stream": True})  # fmt: skip
    if thinking or _thinks(every, model):
        ask("thinking", "POST", "/chat/completions", body={
            "model": thinking or model, "messages": TINY, "max_tokens": 64, "provider": POLICY, "stream": True,
            "reasoning": {"effort": "low"}})  # fmt: skip
    ask("tool call", "POST", "/chat/completions", body={
        "model": model, "stream": True, "max_tokens": 64, "tools": [TOOL], "tool_choice": "required",
        "messages": [{"role": "user", "content": "Look up the made-up word blue."}], "provider": POLICY})  # fmt: skip
    generation = _first_id(streamed.text)
    if generation:
        for _ in range(10):  # how soon a generation answers is one of the checks owed (design 0016 §18)
            if client.get("/generation", params={"id": generation}).status_code == 200:
                break
            time.sleep(3)
        ask("generation", "GET", "/generation", {"id": generation})
    exchanges.append(_cut(client, model))
    wrong = client.get("/key", headers={"Authorization": "Bearer made-up-wrong-key"})
    exchanges.append(_exchange("key refused", "GET", "/key", None, None, wrong))
    ask("no model", "POST", "/chat/completions", body={"model": "example-vendor/no-such-made-up-model",
                                                       "messages": TINY, "max_tokens": 16})  # fmt: skip
    return {
        "adapter": "openrouter",
        "source": f"Recorded from OpenRouter's API ({URL}) with the owner's key, by tools/capture_endpoint.py.",
        "recorded": date.today().isoformat(),
        "how": (
            f"Clank's fixed made-up requests to {model}; the key never written (no request's headers are kept), the "
            "account's label, limit, use and ids replaced by made-up values, the fields "
            f"{', '.join(LEFT_OUT)} left out. No credits, a budget, a limit of requests, no provider under the data "
            "policy and a stream broken mid-way cannot be asked for: the documented shapes keep them."
        ),
        "key": MADE_UP_KEY,
        "exchanges": exchanges,
    }


def _exchange(
    name: str, method: str, path: str, query: dict[str, str] | None, body: Any, answer: httpx2.Response
) -> dict[str, Any]:
    kind = answer.headers.get("content-type", "")
    response: dict[str, Any] = {"status": answer.status_code, "headers": {"content-type": kind.split(";")[0]}}
    if "retry-after" in answer.headers:
        response["headers"]["retry-after"] = answer.headers["retry-after"]
    if "event-stream" in kind:
        response["stream"] = [line for line in answer.text.split("\n\n") if line.strip()]
    else:
        try:
            response["body"] = _scrubbed(answer.json(), name)
        except ValueError:
            response["body"] = answer.text
    return {"name": name, "request": {"method": method, "path": path, "query": query or {}, "body": body},
            "response": response}  # fmt: skip


def _cut(client: httpx2.Client, model: str) -> dict[str, Any]:
    """A stream left after its first data line, as a client that left: what came before it."""
    body = {"model": model, "messages": [{"role": "user", "content": "Count from one to fifty in words."}],
            "max_tokens": 200, "provider": POLICY, "stream": True}  # fmt: skip
    lines: list[str] = []
    with client.stream("POST", "/chat/completions", json=body) as answer:
        for line in answer.iter_lines():
            if line.strip():
                lines.append(line)
            if line.startswith("data:"):
                break
    return {"name": "cut", "request": {"method": "POST", "path": "/chat/completions", "query": {}, "body": body},
            "response": {"status": 200, "headers": {"content-type": "text/event-stream"}, "stream": lines}}  # fmt: skip


def _scrubbed(found: Any, name: str) -> Any:
    """An answer with what it says of the owner made up, and the fields left out."""
    if isinstance(found, dict):
        found = {key: _scrubbed(value, name) for key, value in found.items() if key not in LEFT_OUT}
        if name in ("key", "key refused") and isinstance(found.get("data"), dict):
            data = found["data"]
            found["data"] = {key: ACCOUNT_MADE_UP.get(key, value) if key in ACCOUNT_MADE_UP else value
                             for key, value in data.items()}  # fmt: skip
        return found
    if isinstance(found, list):
        return [_scrubbed(item, name) for item in found]
    return found


def _cheapest(models: list[dict[str, Any]]) -> str:
    """The cheapest model that takes tool calls and is not free (a free one has limits of its own)."""
    priced = []
    for model in models:
        if "tools" not in (model.get("supported_parameters") or []) or str(model.get("id", "")).endswith(":free"):
            continue
        pricing = model.get("pricing") or {}
        try:
            priced.append((float(pricing.get("prompt") or 0) + float(pricing.get("completion") or 0), model["id"]))
        except (TypeError, ValueError):
            continue
    if not priced:
        raise SystemExit("OpenRouter lists no model that takes tool calls")
    return str(min(priced)[1])


def _thinks(models: list[dict[str, Any]], model: str) -> bool:
    found = next((each for each in models if each.get("id") == model), {})
    return "reasoning" in (found.get("supported_parameters") or [])


def _first_id(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("data:") and line[5:].strip() != "[DONE]":
            try:
                return str(json.loads(line[5:]).get("id") or "")
            except ValueError:
                continue
    return ""


def _option(args: list[str], name: str) -> str:
    return args[args.index(name) + 1] if name in args and args.index(name) + 1 < len(args) else ""


if __name__ == "__main__":
    sys.exit(main())
