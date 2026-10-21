"""Design 0016 §18 (design 0015 §14): every endpoint adapter meets the same contract, run against every HTTP recording
of its provider (`tests/fixtures/<adapter>/<date>/http.json`), the documented shapes first and the owner's recordings
after: it reads the recorded list of models, the key's account, a whole answer's and a stream's cost, and each refusal
into words, without an error; and the fake that stands in for the provider in every other test answers each recorded
request as recorded."""

import json
from pathlib import Path
from typing import Any

import httpx2
import pytest

from clank.components.runtime.adapters import ENDPOINTS
from clank.components.runtime.adapters.endpoint import EndpointAdapter
from tests.fakes import openrouter as fake_openrouter

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FAKES = {"openrouter": fake_openrouter}
CASES = [
    pytest.param(adapter, path, id=f"{adapter.NAME}-{path.parent.name}")
    for adapter in ENDPOINTS.all()
    for path in sorted((FIXTURES / adapter.NAME).glob("*/http.json"))
]


def exchanges(path: Path) -> dict[str, dict[str, Any]]:
    played: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return {each["name"]: each for each in played["exchanges"]}


def events(lines: list[str]) -> list[dict[str, Any]]:
    """A stream's data lines, read."""
    return [json.loads(line[5:]) for line in lines if line.startswith("data:") and line[5:].strip() != "[DONE]"]


def test_every_endpoint_adapter_has_a_recording() -> None:
    missing = [adapter.NAME for adapter in ENDPOINTS.all() if not list((FIXTURES / adapter.NAME).glob("*/http.json"))]
    assert missing == []


@pytest.mark.parametrize(("adapter", "path"), CASES)
def test_it_reads_the_recorded_list_of_models_and_the_keys_account(adapter: type[EndpointAdapter], path: Path) -> None:
    recorded = exchanges(path)
    endpoint = adapter()
    lines = endpoint.models(recorded["models"]["response"]["body"])
    assert lines, "the list holds models that take tool calls"
    assert all(line.tools and line.window > 0 and line.id for line in lines)
    assert len(endpoint.models(recorded["every model"]["response"]["body"], everything=True)) >= len(lines)
    account = endpoint.account(recorded["key"]["response"]["body"])
    assert account.view("2026-10-21T09:14:00.000Z")["days"] == "UTC"


@pytest.mark.parametrize(("adapter", "path"), CASES)
def test_it_reads_a_whole_answers_and_a_streams_cost_from_their_usage(
    adapter: type[EndpointAdapter], path: Path
) -> None:
    recorded = exchanges(path)
    endpoint = adapter()
    whole = recorded["answer"]["response"]["body"]
    assert endpoint.cost(whole.get("usage"), {}, {}).how == "usage"
    streamed = events(recorded["stream"]["response"]["stream"])
    usage = next(event["usage"] for event in reversed(streamed) if event.get("usage"))
    assert endpoint.cost(usage, {}, {}).how == "usage"
    cut = events(recorded["cut"]["response"]["stream"])
    assert not any(event.get("usage") for event in cut), "a stream cut short has no usage"
    if "generation" in recorded:  # a recording made before the generation answered has none
        assert endpoint.generation_cost(recorded["generation"]["response"]["body"]) is not None


@pytest.mark.parametrize(("adapter", "path"), CASES)
def test_it_reads_each_recorded_refusal_into_words(adapter: type[EndpointAdapter], path: Path) -> None:
    endpoint = adapter()
    refused = [each for each in exchanges(path).values() if each["response"]["status"] != 200]
    statuses = {each["response"]["status"] for each in refused}
    # The documented shapes hold every refusal; a recording with a key, those that can be asked for on demand.
    assert statuses >= ({401, 402, 403, 404, 429, 503} if path.parent.name == "documented" else {401})
    for each in refused:
        response = each["response"]
        body = json.dumps(response["body"]).encode()
        refusal = endpoint.refusal(response["status"], body, model="example-vendor/example-coder", denied=True)
        assert refusal.status == response["status"]
        assert refusal.message, each["name"]


@pytest.mark.parametrize(("adapter", "path"), CASES)
def test_the_fake_answers_each_recorded_request_as_recorded(adapter: type[EndpointAdapter], path: Path) -> None:
    fakes = FAKES[adapter.NAME]
    played: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    with fakes.served(fakes.FakeOpenRouter(played=played)) as fake:
        for name, each in exchanges(path).items():
            asked, recorded = each["request"], each["response"]
            key = "a-wrong-made-up-key" if name == "key refused" else played["key"]
            if asked["path"] == "/chat/completions":
                fake.play(name)
            answer = httpx2.request(
                asked["method"], fake.url + asked["path"], params=asked["query"], json=asked["body"],
                headers={"Authorization": f"Bearer {key}"}, timeout=10,
            )  # fmt: skip
            assert answer.status_code == recorded["status"], name
            for header, value in recorded["headers"].items():
                if header != "content-type":
                    assert answer.headers.get(header) == value, f"{name}: {header}"
            if "stream" in recorded:
                assert [line for line in answer.text.split("\n\n") if line] == recorded["stream"], name
            else:
                assert answer.json() == recorded["body"], name
