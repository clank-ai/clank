"""A server keeps accepting connections when a client drops one while it is being accepted (Windows).

On Windows asyncio runs a proactor event loop, and its accept loop (`BaseProactorEventLoop._start_serving`, CPython up
to 3.14 at least) closes the server's listening socket at the first accept that fails with an `OSError`. A client that
drops its connection while it is being accepted fails one with `WinError 64` ("The specified network name is no longer
available"): on the owner's PC on 2026-10-26 the service then ran on without answering anyone, `clank stop` could not
reach it, and `clank serve` found it holding its lock. `keep_accepting` puts in an accept loop that is CPython's own but
for that: an accept that failed only because its client went away (`DROPPED`, a reset or an aborted connection) is
logged at debug level and the next one is accepted; any other error closes the socket as before. Each server process
calls it once, before it serves: the service (its API and the phone's listener share its event loop) and the gateway.
"""

import logging
import sys
from typing import Any

log = logging.getLogger(__name__)
DROPPED = frozenset({64, 1236, 10053, 10054})  # Windows' codes for a connection its client dropped, aborted or reset
WINDOWS = sys.platform == "win32"


def dropped(error: OSError) -> bool:
    """Whether an accept failed only because its client went away."""
    return (
        isinstance(error, ConnectionResetError | ConnectionAbortedError) or getattr(error, "winerror", None) in DROPPED
    )


def keep_accepting(*, windows: bool = WINDOWS) -> bool:
    """On Windows, the proactor event loop's accept loop made to go on past a dropped client (the module docstring);
    whether it was put in now (False elsewhere, and once it is in)."""
    if not windows:
        return False
    from asyncio import proactor_events

    proactor = proactor_events.BaseProactorEventLoop
    if vars(proactor).get("_start_serving") is start_serving:
        return False
    setattr(proactor, "_start_serving", start_serving)  # noqa: B010 (a private method the type stubs do not know)
    return True


def start_serving(
    self: Any,
    protocol_factory: Any,
    sock: Any,
    sslcontext: Any = None,
    server: Any = None,
    backlog: int = 100,
    ssl_handshake_timeout: Any = None,
    ssl_shutdown_timeout: Any = None,
) -> None:
    """CPython's `BaseProactorEventLoop._start_serving`, an accept whose client went away followed by the next."""
    from asyncio import exceptions, trsock

    def loop(f: Any = None) -> None:
        try:
            if f is not None:
                conn, addr = f.result()
                protocol = protocol_factory()
                if sslcontext is not None:
                    self._make_ssl_transport(
                        conn, protocol, sslcontext, server_side=True, extra={"peername": addr}, server=server,
                        ssl_handshake_timeout=ssl_handshake_timeout, ssl_shutdown_timeout=ssl_shutdown_timeout,
                    )  # fmt: skip
                else:
                    self._make_socket_transport(conn, protocol, extra={"peername": addr}, server=server)
            if self.is_closed():
                return
            f = self._proactor.accept(sock)
        except OSError as error:
            if sock.fileno() != -1 and dropped(error):
                log.debug("a client dropped its connection while it was accepted (%s): the next is accepted", error)
                self.call_soon(loop)
                return
            if sock.fileno() != -1:
                self.call_exception_handler(
                    {"message": "Accept failed on a socket", "exception": error, "socket": trsock.TransportSocket(sock)}
                )
                sock.close()
            elif self._debug:
                log.debug("Accept failed on socket %r", sock, exc_info=True)
        except exceptions.CancelledError:
            sock.close()
        else:
            self._accept_futures[sock.fileno()] = f
            f.add_done_callback(loop)

    self.call_soon(loop)
