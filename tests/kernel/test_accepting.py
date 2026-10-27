"""Design 0002 §1: the service keeps answering. On Windows a client that drops its connection while it is being accepted
fails that accept with `WinError 64`, and asyncio's proactor accept loop then closed the server's listening socket for
good: the service ran on without answering anyone (the owner's PC, 2026-10-26). Clank's accept loop logs such an accept
and accepts the next; any other accept error still closes the socket as before; it is put in once, on Windows only."""

import asyncio.proactor_events
from collections.abc import Callable
from typing import Any

import pytest

from clank.kernel import accepting


class Dropped(OSError):
    """An accept its client dropped, as Windows says it (`WinError 64`)."""

    winerror = 64


class Future:
    """An accept's outcome: a connection and its address, or an error."""

    def __init__(self, outcome: object) -> None:
        self.outcome = outcome
        self.callbacks: list[Callable[[Any], None]] = []

    def result(self) -> object:
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome

    def add_done_callback(self, callback: Callable[[Any], None]) -> None:
        self.callbacks.append(callback)


class Socket:
    def __init__(self) -> None:
        self.closed = False

    def fileno(self) -> int:
        return -1 if self.closed else 7

    def close(self) -> None:
        self.closed = True


class Loop:
    """What the accept loop uses of a proactor event loop: each accept's outcome in turn."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes = outcomes
        self.futures: list[Future] = []
        self.soon: list[Callable[[], None]] = []
        self.handled: list[dict[str, Any]] = []
        self.connected: list[object] = []
        self._accept_futures: dict[int, Future] = {}
        self._debug = False
        self._proactor = self

    def is_closed(self) -> bool:
        return False

    def accept(self, sock: Socket) -> Future:
        self.futures.append(Future(self.outcomes.pop(0) if self.outcomes else ("idle", None)))
        return self.futures[-1]

    def call_soon(self, callback: Callable[[], None]) -> None:
        self.soon.append(callback)

    def call_exception_handler(self, context: dict[str, Any]) -> None:
        self.handled.append(context)

    def _make_socket_transport(self, conn: object, protocol: object, extra: dict[str, Any], server: object) -> None:
        self.connected.append(extra["peername"])

    def run(self) -> None:
        """Run what is due, then complete each accept in turn until none is left to complete."""
        for _ in range(20):
            while self.soon:
                self.soon.pop(0)()
            done = next((each for each in self.futures if each.callbacks and each.outcome != ("idle", None)), None)
            if done is None:
                return
            callback = done.callbacks.pop()
            callback(done)


def test_an_accept_whose_client_dropped_its_connection_is_followed_by_the_next_accept() -> None:
    loop, sock = (
        Loop([Dropped(22, "The specified network name is no longer available"), ("conn", "127.0.0.1:50001")]),
        Socket(),
    )
    accepting.start_serving(loop, lambda: "protocol", sock)
    loop.run()
    assert not sock.closed, "the listening socket stays open"
    assert loop.connected == ["127.0.0.1:50001"], "the next client is served"
    assert loop.handled == []
    loop, sock = Loop([ConnectionResetError(), ("conn", "127.0.0.1:50002")]), Socket()
    accepting.start_serving(loop, lambda: "protocol", sock)
    loop.run()
    assert (sock.closed, loop.connected) == (False, ["127.0.0.1:50002"]), "a reset connection too"


def test_any_other_accept_error_still_closes_the_socket_as_asyncio_does() -> None:
    loop, sock = Loop([OSError(22, "Invalid argument"), ("conn", "127.0.0.1:50003")]), Socket()
    accepting.start_serving(loop, lambda: "protocol", sock)
    loop.run()
    assert sock.closed
    assert [each["message"] for each in loop.handled] == ["Accept failed on a socket"]
    assert loop.connected == []


def test_it_is_put_in_once_and_only_on_windows(monkeypatch: pytest.MonkeyPatch) -> None:
    proactor = asyncio.proactor_events.BaseProactorEventLoop
    monkeypatch.setattr(proactor, "_start_serving", vars(proactor)["_start_serving"])
    assert accepting.keep_accepting(windows=False) is False
    assert vars(proactor)["_start_serving"] is not accepting.start_serving
    assert accepting.keep_accepting(windows=True) is True
    assert vars(proactor)["_start_serving"] is accepting.start_serving
    assert accepting.keep_accepting(windows=True) is False, "once"
