"""Design 0023 §6: talking to the agent, measured against the running service and the real model.

`uv run python -m bench.talking FOLDER [--text WORDS]` sends one message to the folder's session (or starts one) and
follows the conversation stream (`GET /agents/conversation/stream`) while the model answers: how long the send itself
takes, how soon after Enter the owner's message is on the stream (the mirror heard OpenCode), how soon the model's
first words are, how the words pace (the gaps between the stream's flushes), what the readout said and when, and how
long a read of `GET /agents/conversation` takes at rest afterwards. Prints timings and counts only: never the text.
"""

import argparse
import contextlib
import itertools
import statistics
import sys
import threading
import time
from typing import Any

from clank.client import Client, ServerEvent

DEFAULT_TEXT = (
    "Write one plain paragraph of about 120 words describing a rainy afternoon in a small town, nothing else:"
    " no title, no list, no code."
)  # long enough that the words stream for a few seconds, so the gaps between flushes can be measured
WAIT_SECONDS = 180.0  # for the model to answer and the session to be idle again
REST_READS = 20


def _ms(seconds: float) -> str:
    return f"{seconds * 1000:.0f} ms"


class Follow:
    """The stream's events as they come, read in a thread, each stamped when it arrived."""

    def __init__(self, client: Client, folder: str) -> None:
        self.events: list[tuple[float, ServerEvent]] = []
        self.ready = threading.Event()
        self.stopped = threading.Event()
        self.snapshot_at = 0.0
        self.closing = False
        self._answer: Any = None  # the stream's response, closed to end it from another thread
        self._stream = client.stream(
            "agents/conversation/stream", folder=folder, limit=30, quiet=60, opened=self._opened
        )
        self._lock = threading.Lock()
        threading.Thread(target=self._run, daemon=True).start()

    def _opened(self, answer: Any) -> None:
        self._answer = answer

    def _run(self) -> None:
        try:
            for event in self._stream:
                now = time.perf_counter()
                if event.name == "snapshot" and not self.ready.is_set():
                    self.snapshot_at = now
                    self.ready.set()
                with self._lock:
                    self.events.append((now, event))
        except Exception as error:  # the bench reports the stream's end, whatever ended it
            if not self.closing:
                print(f"stream ended: {type(error).__name__}: {error}")
        finally:
            self.stopped.set()
            self.ready.set()

    def since(self, index: int) -> list[tuple[float, ServerEvent]]:
        """The events from the `index`th on."""
        with self._lock:
            return self.events[index:]

    def close(self) -> None:
        """End the stream (its response closed under the reading thread, which then ends)."""
        self.closing = True
        if self._answer is not None:
            with contextlib.suppress(Exception):  # closing is the point; what the reader meets, it does not report
                self._answer.close()
        self.stopped.wait(5)


def send(client: Client, conversation: dict[str, Any], text: str) -> float:
    """Send `text` to the conversation's session (or start one); the send's own time."""
    workspace = conversation["workspace"]
    began = time.perf_counter()
    if conversation["session"] is None:
        client.post(f"agents/sessions/{workspace}/start", {"text": text, "title": "Talking bench"})
    else:
        session = conversation["session"]
        client.post(f"agents/sessions/{workspace}/{session['port']}/{session['id']}/message", {"text": text})
    return time.perf_counter() - began


def measure(folder: str, text: str) -> int:
    """Send `text` to the folder's session and follow the stream while the model answers; print what was measured."""
    client = Client.connect(name="bench")
    began = time.perf_counter()
    conversation = client.get("agents/conversation", folder=folder, limit=1)
    print(f"GET /agents/conversation (first, the history once if new): {_ms(time.perf_counter() - began)}")
    if conversation["workspace"] is None:
        print("this folder has no workspace: open it with `clank code` first")
        return 1
    follow = Follow(client, folder)
    follow.ready.wait(30)
    if follow.stopped.is_set():
        return 1
    print(f"stream opened, snapshot after {_ms(follow.snapshot_at - began)}")
    seen = len(follow.events)
    pressed = time.perf_counter()
    took = send(client, conversation, text)
    print(f"the send (POST): {_ms(took)}")
    owner_at = thinking_at = words_at = idle_at = None
    users: set[str] = set()
    assistants: set[str] = set()
    types: dict[str, str] = {}  # each part's type, so a delta is known as thinking or as words
    flushes: list[float] = []
    deltas = 0
    phases: list[tuple[float, str]] = []
    while time.perf_counter() - pressed < WAIT_SECONDS and not follow.stopped.is_set():
        for at, event in follow.since(seen):
            seen += 1
            data = event.data
            if event.name == "snapshot":
                for message in data.get("messages") or []:
                    (users if message["info"].get("role") == "user" else assistants).add(message["info"]["id"])
                    for part in message.get("parts") or []:
                        types[part["id"]] = str(part.get("type") or "")
                if owner_at is None and any(m["info"].get("role") == "user" for m in data.get("messages") or []):
                    owner_at = at
                    print(f"owner's message on the stream (in a snapshot) after {_ms(at - pressed)}")
            elif event.name == "message":
                info = data.get("message") or {}
                (users if info.get("role") == "user" else assistants).add(str(info.get("id")))
            elif event.name == "part":
                part = data.get("part") or {}
                types[str(part.get("id"))] = str(part.get("type") or "")
                if owner_at is None and data.get("message") in users and part.get("type") == "text":
                    owner_at = at
                    print(f"owner's message on the stream after {_ms(at - pressed)}")
                if (
                    words_at is None
                    and data.get("message") in assistants
                    and part.get("type") == "text"
                    and part.get("text")
                ):
                    words_at = at
                    print(f"model's first words on the stream (a whole part) after {at - pressed:.2f} s")
            elif event.name == "delta":
                if data.get("message") in assistants:
                    deltas += 1
                    if not flushes or at - flushes[-1] > 0.001:
                        flushes.append(at)
                    if types.get(str(data.get("part")), "text") == "reasoning":
                        if thinking_at is None:
                            thinking_at = at
                            print(f"model's first thinking on the stream after {at - pressed:.2f} s")
                    elif words_at is None:
                        words_at = at
                        print(f"model's first words on the stream after {at - pressed:.2f} s")
            elif event.name == "readout":
                now = (data.get("readout") or {}).get("now") or {}
                phase = str(now.get("phase") or now.get("state") or "")
                if phase and (not phases or phases[-1][1] != phase):
                    phases.append((at, phase))
            elif event.name == "status" and words_at is not None and not data.get("busy"):
                idle_at = at
        if idle_at is not None:
            break
        time.sleep(0.02)
    follow.close()
    if idle_at is not None:
        print(f"session idle again after {idle_at - pressed:.2f} s")
    else:
        print("the session did not go idle within the wait")
    if phases:
        print("readout phases: " + ", ".join(f"{phase} at {at - pressed:.1f} s" for at, phase in phases))
    if len(flushes) > 1:
        gaps = [b - a for a, b in itertools.pairwise(flushes)]
        print(
            f"text: {deltas} deltas in {len(flushes)} flushes;"
            f" gap between flushes median {_ms(statistics.median(gaps))}, max {_ms(max(gaps))}"
        )
    reads: list[float] = []
    for _ in range(REST_READS):
        began = time.perf_counter()
        client.get("agents/conversation", folder=folder, limit=30)
        reads.append(time.perf_counter() - began)
    print(f"{REST_READS} reads of the route at rest: median {_ms(statistics.median(reads))}, max {_ms(max(reads))}")
    return 0


def main() -> int:
    """The command: `python -m bench.talking FOLDER [--text WORDS]`."""
    parser = argparse.ArgumentParser(
        description="Talking to the agent, measured on the running service (design 0023 §6)."
    )
    parser.add_argument("folder", help="a folder with a Clank workspace")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="the message to send")
    arguments = parser.parse_args()
    return measure(arguments.folder, arguments.text)


if __name__ == "__main__":
    sys.exit(main())
