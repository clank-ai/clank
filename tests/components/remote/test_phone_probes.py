"""Design 0025 §2 (when the page does not load): the two questions the checkup asks beyond Tailscale. This PC opens its
own published address as a phone's browser would, naming itself, and says what answered and in how long, or why
nothing did; while Funnel is on, one public DNS server is asked over UDP what the internet is told for the PC's name
(its IPv4 addresses, none for a name it does not know), within a short time, and a server that does not answer is
said, never raised."""

import json
import socket
import struct
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from clank.components.remote.probes import AGENT, Public, public_addresses, reach
from tests.support.served import free_port

KNOWN = {"desk.tail0.ts.net": ["203.0.113.5", "203.0.113.6"]}


def answer(query: bytes, known: dict[str, list[str]]) -> bytes:
    """A DNS server's answer to a query, as public resolvers write it: the question again, then for a known name a
    CNAME-free list of A records whose names point back at the question (compression), else NXDOMAIN."""
    ident = query[:2]
    labels, at = [], 12
    while query[at]:
        labels.append(query[at + 1 : at + 1 + query[at]].decode())
        at += query[at] + 1
    question = query[12 : at + 5]
    addresses = known.get(".".join(labels), [])
    flags = 0x8180 if addresses else 0x8183  # an answer, recursion asked and offered; NXDOMAIN when unknown
    header = ident + struct.pack(">HHHHH", flags, 1, len(addresses), 0, 0)
    records = b"".join(struct.pack(">HHHIH", 0xC00C, 1, 1, 60, 4) + socket.inet_aton(address) for address in addresses)
    return header + question + records


@contextmanager
def fake_dns(known: dict[str, list[str]], silent: bool = False) -> Iterator[int]:
    """A DNS server on this machine's loopback answering `known` (or never, when `silent`); its port."""
    server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server.bind(("127.0.0.1", 0))
    server.settimeout(0.1)
    port: int = server.getsockname()[1]
    done = threading.Event()

    def serve() -> None:
        while not done.is_set():
            try:
                query, sender = server.recvfrom(512)
            except (TimeoutError, OSError):
                continue
            if not silent:
                server.sendto(answer(query, known), sender)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    try:
        yield port
    finally:
        done.set()
        thread.join(5)
        server.close()


@contextmanager
def fake_page(status: int, body: dict[str, Any]) -> Iterator[tuple[str, list[str]]]:
    """A page answering every GET with this status and JSON body; its address, and the user agents it was asked by."""
    agents: list[str] = []

    class Page(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            agents.append(self.headers.get("User-Agent", ""))
            sent = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(sent)))
            self.end_headers()
            self.wfile.write(sent)

        def log_message(self, format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Page)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/", agents
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_public_dns_is_asked_for_the_names_addresses_and_a_name_it_does_not_know_has_none() -> None:
    with fake_dns(KNOWN) as port:
        found = public_addresses("desk.tail0.ts.net", server="127.0.0.1", port=port)
        assert found == Public(("203.0.113.5", "203.0.113.6"), server="127.0.0.1")
        assert public_addresses("other.tail0.ts.net", server="127.0.0.1", port=port) == Public((), server="127.0.0.1")


def test_a_dns_server_that_does_not_answer_is_said_within_the_time_given() -> None:
    with fake_dns(KNOWN, silent=True) as port:
        found = public_addresses("desk.tail0.ts.net", server="127.0.0.1", port=port, timeout=0.3)
    assert (found.addresses, found.problem) == ((), "no answer within 0.3 s")
    nobody = public_addresses("desk.tail0.ts.net", server="127.0.0.1", port=free_port(), timeout=0.3)
    assert nobody.addresses == ()
    assert nobody.problem, "a port nobody listens on is said too (Windows refuses it at once, others time out)"


def test_this_pc_opens_its_address_as_a_browser_would_and_says_what_answered() -> None:
    with fake_page(200, {"ok": True}) as (url, agents):
        found = reach(url)
    assert (found.status, found.said) == (200, "")
    assert found.ms > 0
    assert agents == [AGENT], "it names itself, so the listener's log tells it from a phone"
    refusal = "this page answers only to this computer's own Tailscale user"
    with fake_page(403, {"error": refusal}) as (url, _):
        refused = reach(url)
    assert (refused.status, refused.said) == (403, refusal), "a refusal in the listener's words"
    closed = reach(f"http://127.0.0.1:{free_port()}/", timeout=1)
    assert closed.status is None
    assert closed.said.startswith(("could not connect: ", "no answer within 1 s")), (
        "refused, or (Windows tries a refused connection again for about two seconds) not answered in time"
    )
