"""Design 0004 §2 (found by the model battery, 2026-10-15): an engine that fails mid-answer (KVMem after a 68K-token
prompt: "multimodal query replay failed") sends an error event whose `error` is a plain string, which OpenAI's clients
(OpenCode's AI SDK) refuse to read ("expected object, received string"), so the user saw a parse error, not the reason.
The gateway passes an error event on as OpenAI writes one (an object with its message, type and code) and records the
error, so the Requests page shows the request failed and why."""

import json
from typing import Any

from clank.components.gateway.server import _engine_error


def event(data: dict[str, Any]) -> bytes:
    return b"data: " + json.dumps(data).encode()


def test_an_engines_error_given_as_a_string_is_passed_on_as_openai_writes_one_and_recorded() -> None:
    record: dict[str, Any] = {}
    line = _engine_error(event({"error": "multimodal query replay failed"}), record)
    assert json.loads(line[5:]) == {
        "error": {"message": "multimodal query replay failed", "type": "engine_error", "code": "engine_error"}
    }
    assert record["error"] == "multimodal query replay failed"


def test_an_error_already_as_an_object_is_kept_and_recorded_and_other_lines_pass_untouched() -> None:
    record: dict[str, Any] = {}
    given = event({"error": {"message": "context full", "type": "server_error", "code": 500}})
    assert _engine_error(given, record) == given
    assert record["error"] == "context full"
    chunk = event({"choices": [{"delta": {"content": "hi"}}]})
    assert _engine_error(chunk, {}) == chunk
    assert _engine_error(b"data: [DONE]", {}) == b"data: [DONE]"
    assert _engine_error(b": keep-alive", {}) == b": keep-alive"
