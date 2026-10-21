"""A fake engine for the runtime's tests (design 0003 §9): it is started with a real engine's flags (from the real
adapters' plans), prints the startup lines its engine printed (from the adapters' recordings), says it is ready in that
engine's own words, answers `/health`, `/v1/models`, a short `/v1/chat/completions` and (as llama.cpp) `/infill`, and
ends on SIGTERM (on Windows, when it is ended). A chat request asking to stream is answered one token at a time
(`max_tokens` tokens, `--fake-token-seconds` apart, after reading the prompt for `--fake-prompt-seconds`), with its
usage when `stream_options` asks for it. Each request it takes is logged (`received {...}`), and a client that leaves
mid-answer too (`client left after N tokens`). Its own flags make it slow to start (`--fake-start-seconds`), fail at its
start as a GPU out of memory (`--fake-fail-start oom`), crash a while after it is ready (`--fake-crash-after`), or stop
answering while it still runs (`--fake-deaf-after`); with `--fake-only-context N` these apply only when it is started
with that context (`-c N`), so one install serves a preset that fails beside one that starts. With `--fake-end-after N`
a streamed answer stops after N tokens with an ordinary close, no end event and no error: what a crashed engine's
stream looks like on Linux, where the system closes its connection cleanly (on Windows it is reset). With
`--fake-loop-after N` a streamed answer loses its way after N tokens, as a model did on 2026-10-18: the same closing
tags again and again, in its text, its thinking or a `bash` call's arguments (`--fake-loop-in`). With
`--fake-prompt-tokens N` its usage says the prompt had N tokens (5 otherwise), and with `--fake-cached-tokens M` that M
of them came from its cache, where its engine reports it: KVMem in its usage (`prompt_cache_hit_tokens`), llama.cpp in
its `timings` (`cache_n`, beside `prompt_n`, the tokens it read), with the answer's last event. With `--fake-refuse
STATUS` it refuses every chat request with that status and an error in llama.cpp's shape (`REFUSAL`), as an engine does
a prompt longer than its context. With `--fake-full` it refuses every chat request as its engine refuses one its
context cannot hold (`FULL`): KVMem with a 400 and its words as a plain string, llama.cpp with a 400 and an error of
type `exceed_context_size_error`.

It uses the standard library only, and `program(style, ...)` is the command that runs it, ready for a `Launch`.
"""

import argparse
import json
import os
import signal
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
RECORDINGS = {"kvmem": "kvmem-llamacpp/v0.16.0-rc1", "llamacpp": "llamacpp/b11588"}
READY = {
    "llamacpp": "0.03.534.448 I srv  llama_server: listening on http://{host}:{port}",
    "kvmem": "llama-kvmem-server listening on http://{host}:{port}  model={model} kvmem=1 method=retrieval",
}
OUT_OF_MEMORY = {
    "llamacpp": "0.00.744.541 E llama_model_load: error loading model: unable to allocate CPU buffer",
    "kvmem": "ggml_backend_cuda_buffer_type_alloc_buffer: allocating 2176.00 MiB on device 0: cudaMalloc failed: "
    "out of memory",
}
CRASH = {
    "llamacpp": "0.10.098.194 E ggml_abort: GGML_ASSERT(n_tokens > 0) failed",
    "kvmem": "ggml-cuda.cu:2657: GGML_ASSERT(stat == cudaSuccess) failed",
}
LOOP = ("</f>", "\n", "</invoke>", "\n", "</functions>", "\n")  # the loop of 2026-10-18, a token at a time


def program(style: str, *fake: str) -> tuple[str, ...]:
    """The command that runs the fake engine in a style, before the engine's own arguments."""
    return (sys.executable, str(Path(__file__).resolve()), "--fake-style", style, *fake)


def startup(style: str) -> list[str]:
    """The lines its engine printed before it was ready, as its recording holds them (the loader's few kept)."""
    recorded = json.loads((FIXTURES / RECORDINGS[style] / "program.json").read_text(encoding="utf-8"))
    lines = [str(line) for line in recorded["startup"][:-1]]
    if style == "kvmem":
        lines = [line for line in lines if "buffer size" in line or line.startswith(("ggml_cuda_init", "KVMEM_KV"))]
    if style == "llamacpp":
        lines = [line for line in lines if "buffer size" in line or "llama_server" in line]
    return lines


REFUSAL = "the request exceeds the available context size, try increasing it (15000 tokens, 8192 in the context)"
FULL = {  # each engine's words when a request's prompt (and, for KVMem, its max_tokens) pass its window
    "kvmem": "prompt + max_tokens exceeds n_ctx",
    "llamacpp": "request (300000 tokens) exceeds the available context size (262144 tokens), try increasing it",
}


class Handler(BaseHTTPRequestHandler):
    """The API a check and a switch use."""

    model = ""
    style = ""
    token_seconds = 0.0
    prompt_seconds = 0.0
    loop_after: int | None = None
    loop_in = "answer"
    end_after: int | None = None
    prompt_tokens = 5
    cached_tokens: int | None = None
    refuse: int | None = None
    full = False

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            self._answer({"status": "ok"})
        elif self.path.startswith("/v1/models"):
            self._answer({"object": "list", "data": [{"id": self.model, "object": "model"}]})
        else:
            self._answer({"error": "not found"}, 404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path.startswith("/infill") and self.style == "llamacpp":
            self._infill(body)
            return
        if not self.path.startswith("/v1/chat/completions"):
            self._answer({"error": "not found"}, 404)
            return
        print("received " + json.dumps(body, sort_keys=True), flush=True)
        if self.full:
            if self.style == "kvmem":
                self._answer({"error": FULL["kvmem"]}, 400)
            else:
                self._answer({"error": {"code": 400, "message": FULL["llamacpp"], "type": "exceed_context_size_error",
                                        "n_prompt_tokens": 300000, "n_ctx": 262144}}, 400)  # fmt: skip
            return
        if self.refuse is not None:
            self._answer({"error": {"code": self.refuse, "message": REFUSAL, "type": "exceed_context_size_error",
                                    "n_prompt_tokens": 15000, "n_ctx": 8192}}, self.refuse)  # fmt: skip
            return
        if body.get("stream"):
            self._stream(
                int(body.get("max_tokens") or 2), bool((body.get("stream_options") or {}).get("include_usage"))
            )
            return
        time.sleep(self.prompt_seconds)
        self._answer(
            {
                "id": "fake-1",
                "object": "chat.completion",
                "model": self.model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}],
                "usage": self._usage(1),
                **self._timings(1),
            }
        )

    def log_message(self, format: str, *args: Any) -> None:
        """Quiet, as the engines are about each request."""

    def _stream(self, tokens: int, usage: bool) -> None:
        """Server-sent events, one token each, then the end (and the usage when asked)."""
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        sent = 0
        try:
            self.wfile.flush()
            time.sleep(self.prompt_seconds)
            for index in range(tokens):
                if index == self.end_after:
                    print(f"stream ended after {sent} tokens, without its end", flush=True)
                    return  # the server closes the connection, as a system closes a crashed engine's
                delta = {"role": "assistant", **self._delta(index)} if index == 0 else self._delta(index)
                self._event({"id": "fake-1", "object": "chat.completion.chunk", "model": self.model,
                             "choices": [{"index": 0, "delta": delta, "finish_reason": None}]})  # fmt: skip
                sent += 1
                time.sleep(self.token_seconds)
            self._event({"id": "fake-1", "object": "chat.completion.chunk", "model": self.model,
                         "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                         **self._timings(tokens)})  # fmt: skip
            if usage:
                self._event({"id": "fake-1", "object": "chat.completion.chunk", "choices": [],
                             "usage": self._usage(tokens)})  # fmt: skip
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            print(f"client left after {sent} tokens", flush=True)

    def _usage(self, tokens: int) -> dict[str, int]:
        """The answer's usage: the prompt's tokens and the answer's; for KVMem, the cache's hits too when given."""
        usage = {"prompt_tokens": self.prompt_tokens, "completion_tokens": tokens,
                 "total_tokens": self.prompt_tokens + tokens}  # fmt: skip
        if self.cached_tokens is not None and self.style == "kvmem":
            usage["prompt_cache_hit_tokens"] = self.cached_tokens
        return usage

    def _timings(self, tokens: int) -> dict[str, Any]:
        """llama.cpp's `timings`, when the cache's hits are given: the tokens it read, those from its cache, and the
        answer's."""
        if self.cached_tokens is None or self.style != "llamacpp":
            return {}
        read = self.prompt_tokens - self.cached_tokens
        return {"timings": {"prompt_n": read, "cache_n": self.cached_tokens, "predicted_n": tokens}}

    def _delta(self, index: int) -> dict[str, Any]:
        """The token at `index`: `w<index> ` in the answer's text, or, from `--fake-loop-after` on, the closing tags of
        the loop again and again, in the part `--fake-loop-in` names (a `bash` call's arguments, JSON-escaped)."""
        if self.loop_after is None or index < self.loop_after:
            return {"content": f"w{index} "}
        token = LOOP[(index - self.loop_after) % len(LOOP)]
        if self.loop_in == "thinking":
            return {"reasoning_content": token}
        if self.loop_in == "tool":
            escaped = json.dumps(token)[1:-1]
            if index == self.loop_after:
                begun = {"name": "bash", "arguments": '{"command": "ls ' + escaped}
                return {"tool_calls": [{"index": 0, "id": "call-1", "type": "function", "function": begun}]}
            return {"tool_calls": [{"index": 0, "function": {"arguments": escaped}}]}
        return {"content": token}

    def _infill(self, body: dict[str, Any]) -> None:
        """llama.cpp's fill in the middle: the middle is the line so far's length, after reading for
        `--fake-prompt-seconds`; a client that left by then is said."""
        print("received " + json.dumps(body, sort_keys=True), flush=True)
        time.sleep(self.prompt_seconds)
        middle = f"middle{len(str(body.get('prompt', '')))}"
        timings = {"prompt_n": 12, "prompt_ms": 8.5, "predicted_n": 3, "predicted_ms": 4.5}
        try:
            self._answer({"content": middle, "stop": True, "model": self.model, "timings": timings,
                          "tokens_evaluated": 12, "tokens_predicted": 3})  # fmt: skip
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            print("client left before the middle", flush=True)

    def _event(self, data: dict[str, Any]) -> None:
        self.wfile.write(b"data: " + json.dumps(data).encode() + b"\n\n")
        self.wfile.flush()

    def _answer(self, body: dict[str, Any], status: int = 200) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main(argv: list[str]) -> int:
    """Start, answer, and end as told; with `--help`, print its engine's recorded help."""
    if "--help" in argv:
        style = argv[argv.index("--fake-style") + 1]
        recorded = json.loads((FIXTURES / RECORDINGS[style] / "program.json").read_text(encoding="utf-8"))
        print(next(iter(recorded["states"]["installed"].values()))[1], end="")
        return 0
    parser = argparse.ArgumentParser()
    parser.add_argument("--fake-style", choices=sorted(RECORDINGS), required=True)
    parser.add_argument("--fake-start-seconds", type=float, default=0.0)
    parser.add_argument("--fake-fail-start", choices=["oom"])
    parser.add_argument("--fake-crash-after", type=float)
    parser.add_argument("--fake-deaf-after", type=float)
    parser.add_argument("--fake-token-seconds", type=float, default=0.0)
    parser.add_argument("--fake-prompt-seconds", type=float, default=0.0)
    parser.add_argument("--fake-only-context", type=int)
    parser.add_argument("--fake-loop-after", type=int)
    parser.add_argument("--fake-loop-in", choices=["answer", "thinking", "tool"], default="answer")
    parser.add_argument("--fake-end-after", type=int)
    parser.add_argument("--fake-prompt-tokens", type=int, default=5)
    parser.add_argument("--fake-cached-tokens", type=int)
    parser.add_argument("--fake-refuse", type=int)
    parser.add_argument("--fake-full", action="store_true")
    parser.add_argument("-c", "--ctx-size", type=int)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("-m", "--model", default="")
    known, rest = parser.parse_known_args(argv)
    if known.fake_only_context is not None and known.ctx_size != known.fake_only_context:
        known.fake_start_seconds, known.fake_fail_start = 0.0, None  # another context: it behaves
        known.fake_crash_after = known.fake_deaf_after = None
    style = known.fake_style
    positional = next((part for part in rest if not part.startswith("-")), "")
    Handler.model = Path(known.model or positional).name
    Handler.style = style
    Handler.token_seconds = known.fake_token_seconds
    Handler.prompt_seconds = known.fake_prompt_seconds
    Handler.loop_after = known.fake_loop_after
    Handler.loop_in = known.fake_loop_in
    Handler.end_after = known.fake_end_after
    Handler.prompt_tokens = known.fake_prompt_tokens
    Handler.cached_tokens = known.fake_cached_tokens
    Handler.refuse = known.fake_refuse
    Handler.full = known.fake_full
    print(f"fake {style} engine, started as: {' '.join(argv)}", flush=True)
    for line in startup(style):
        print(line, flush=True)
    if known.fake_fail_start == "oom":
        print(OUT_OF_MEMORY[style], flush=True)
        return 1
    time.sleep(known.fake_start_seconds)
    server = ThreadingHTTPServer((known.host, known.port), Handler)
    print(READY[style].format(host=known.host, port=known.port, model=Handler.model), flush=True)
    if known.fake_crash_after is not None:

        def crash() -> None:
            print(CRASH[style], flush=True)
            os._exit(134)

        threading.Timer(known.fake_crash_after, crash).start()

    asked_to_end = threading.Event()
    if known.fake_deaf_after is not None:
        threading.Timer(known.fake_deaf_after, server.shutdown).start()

    def stop(*_: object) -> None:
        print("stopping: asked to end", flush=True)
        asked_to_end.set()
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    server.serve_forever()
    while known.fake_deaf_after is not None and not asked_to_end.wait(0.2):
        pass  # deaf: it no longer answers, but it runs until it is asked to end
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
