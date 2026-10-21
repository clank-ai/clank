"""Design 0013 §5 and design 0012 §4 (decision 0087): a text is counted for a preset by its engine only when the main
slot runs that preset now and its engine counts tokens (llama.cpp's `/tokenize`); otherwise it is estimated, from the
model's calibration when it has one, else from Clank's plain default, and the count says which; an engine that does not
answer leaves the estimate, saying why. Nothing is loaded to count."""

import json
import math
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, ClassVar

import pytest

from clank.components.runtime.adapters import ENGINES
from clank.components.runtime.catalog import Calibration
from clank.components.runtime.service import PLAIN_TOKENS_PER_CHARACTER
from clank.kernel.events import Actor
from tests.components.runtime.conftest import Rig
from tests.support.served import free_port

YOU = Actor(kind="user", via="a test")
TEXT = "Write the grid of the study's parameters, about sixty points."


class Tokenizer(BaseHTTPRequestHandler):
    """llama.cpp's `/tokenize`, a token for each word."""

    asked: ClassVar[list[dict[str, Any]]] = []

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        if self.path != "/tokenize":
            self.send_response(404)
            self.end_headers()
            return
        Tokenizer.asked.append(body)
        answer = json.dumps({"tokens": list(range(len(str(body["content"]).split())))}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(answer)))
        self.end_headers()
        self.wfile.write(answer)

    def log_message(self, format: str, *args: Any) -> None:
        """Quiet."""


@pytest.fixture
def engine() -> Iterator[int]:
    """An engine's port that answers `/tokenize`."""
    Tokenizer.asked = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), Tokenizer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1]
    server.shutdown()
    server.server_close()


def llama(rig: Rig) -> None:
    rig.preset("fake-llama", {"title": "fake llama", "engine": "llamacpp", "engine_version": "b11588",
                              "model": "tiny", "options": {"context": 16384}})  # fmt: skip


def test_a_text_is_counted_by_the_engine_when_the_main_slot_runs_its_preset_and_its_engine_counts(
    rig: Rig, engine: int
) -> None:
    llama(rig)
    rig.runtime.state.set_slot("main", "ready", "a test", actor=YOU, preset="fake-llama", host="local", port=engine)
    counted = rig.runtime.count_tokens("fake llama", TEXT)
    assert counted == {
        "tokens": len(TEXT.split()),
        "exact": True,
        "counted": "counted by llama.cpp b11588, which runs fake llama now",
    }
    assert Tokenizer.asked == [{"content": TEXT}]
    assert rig.runtime.count_tokens("fake-llama", TEXT)["exact"] is True, "by its id too"


def test_a_preset_not_loaded_or_an_engine_that_cannot_count_is_estimated_at_the_plain_default(
    rig: Rig, engine: int
) -> None:
    llama(rig)
    rig.runtime.state.set_slot("main", "ready", "a test", actor=YOU, preset="fake-kvmem", host="local", port=engine)
    estimate = math.ceil(len(TEXT) * PLAIN_TOKENS_PER_CHARACTER)
    assert PLAIN_TOKENS_PER_CHARACTER == 0.3
    counted = rig.runtime.count_tokens("fake KVMem", TEXT)
    assert counted == {
        "tokens": estimate,
        "exact": False,
        "counted": "an estimate: 0.3 tokens per character, Clank's plain default (Tiny has no calibration; "
        "KVMem/llama.cpp v0.16.0-rc1 does not count tokens)",
    }
    elsewhere = rig.runtime.count_tokens("fake llama", TEXT)
    assert (elsewhere["tokens"], elsewhere["exact"]) == (estimate, False)
    assert "the main slot does not run fake llama now" in elsewhere["counted"]
    assert Tokenizer.asked == [], "nothing loaded, and no engine asked, to count"
    nothing = rig.runtime.count_tokens("", TEXT)
    assert nothing == {
        "tokens": estimate,
        "exact": False,
        "counted": "an estimate: 0.3 tokens per character, Clank's plain default (no preset named)",
    }


def test_a_models_calibration_is_used_when_it_has_one(rig: Rig) -> None:
    assert rig.runtime.models is not None
    tiny = rig.runtime.models["tiny"]
    measured = "2026-10-20, on synthetic requests"
    calibration = Calibration(tokens_per_character={"user": 0.25, "tools": 0.5}, measured=measured)
    rig.runtime.models = {"tiny": tiny.model_copy(update={"calibration": calibration})}
    counted = rig.runtime.count_tokens("fake KVMem", TEXT)
    assert counted == {
        "tokens": math.ceil(len(TEXT) * 0.25),
        "exact": False,
        "counted": f"an estimate: 0.25 tokens per character, Tiny's calibration ({measured}) (the main slot does not "
        "run fake KVMem now)",
    }


def test_an_engine_that_does_not_answer_leaves_the_estimate_saying_why(rig: Rig) -> None:
    llama(rig)
    rig.runtime.state.set_slot("main", "ready", "a test", actor=YOU, preset="fake-llama", host="local",
                               port=free_port())  # fmt: skip
    counted = rig.runtime.count_tokens("fake llama", TEXT)
    assert (counted["tokens"], counted["exact"]) == (math.ceil(len(TEXT) * PLAIN_TOKENS_PER_CHARACTER), False)
    assert "llama.cpp b11588 did not count it" in counted["counted"]


def test_an_engine_names_a_route_to_count_exactly_when_its_context_facts_say_it_counts() -> None:
    for kind in ENGINES.all():
        facts = kind(kind.VERSIONS[-1].name).context_facts({})
        assert bool(kind.TOKENIZE) == facts.counts_tokens, kind.NAME
