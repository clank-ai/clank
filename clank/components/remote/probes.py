"""The two questions the phone's checkup asks beyond Tailscale (design 0025 §2, when the page does not load).

`reach`: this PC opens its own published address (`https://<machine>.<tailnet>.ts.net:<port>/`) as a phone's browser
would, through Tailscale, naming itself (`AGENT`) so the listener's log tells it from a phone; what answered and in how
long, or why nothing did. One opening is one exchange in that log.

`public_addresses`: what the internet is told for this PC's name, asked of one public DNS server (Cloudflare's 1.1.1.1)
in one UDP question, within a short time. Only the checkup asks it, and only while Tailscale Funnel is on for this
machine: Funnel gives the PC's name public addresses (Tailscale's relays), so a phone that does not ask Tailscale's DNS
for the name (iCloud Private Relay, an answer kept from before Tailscale was on) is sent to a relay that does not carry
the phone page's port. The name is all that is sent. The question is written and read here with the standard
library, so no dependency is added for it. Neither question changes anything, and neither raises.
"""

import secrets
import socket
import struct
import time
from dataclasses import dataclass

import httpx2

AGENT = "Clank checkup (this PC)"
REACH_TIMEOUT = 5.0
PUBLIC_DNS = "1.1.1.1"  # Cloudflare's public resolver: what a phone outside Tailscale's DNS is told
DNS_TIMEOUT = 2.0


@dataclass(frozen=True)
class Reached:
    """What this PC got when it opened its own address: the status (None: no answer), in how many milliseconds, and the
    words that came with it (a refusal's) or why nothing answered."""

    status: int | None
    ms: float
    said: str = ""


@dataclass(frozen=True)
class Public:
    """What a public DNS server said for a name: its IPv4 addresses (none: it knows none), or why it could not be
    asked; and which server it was."""

    addresses: tuple[str, ...]
    problem: str = ""
    server: str = PUBLIC_DNS


def reach(url: str, timeout: float = REACH_TIMEOUT) -> Reached:
    """Open `url` as a browser would (GET, following nothing), within `timeout` seconds."""
    began = time.perf_counter()
    try:
        answer = httpx2.get(url, timeout=timeout, headers={"User-Agent": AGENT})
    except httpx2.TimeoutException:
        return Reached(None, (time.perf_counter() - began) * 1000, f"no answer within {timeout:g} s")
    except httpx2.HTTPError as error:
        return Reached(None, (time.perf_counter() - began) * 1000, _why(error))
    ms = (time.perf_counter() - began) * 1000
    said = ""
    if answer.status_code >= 400:
        try:
            found = answer.json()
        except ValueError:
            found = None
        said = str(found.get("error", "")) if isinstance(found, dict) else answer.text.strip()[:200]
    return Reached(answer.status_code, ms, said)


def public_addresses(name: str, server: str = PUBLIC_DNS, port: int = 53, timeout: float = DNS_TIMEOUT) -> Public:
    """The IPv4 addresses `server` gives for `name` (one A question over UDP), or why it could not be asked."""
    ident = secrets.randbits(16)
    question = b"".join(bytes([len(label)]) + label.encode("ascii") for label in name.strip(".").split("."))
    query = struct.pack(">HHHHHH", ident, 0x0100, 1, 0, 0, 0) + question + b"\x00" + struct.pack(">HH", 1, 1)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as asking:
        asking.settimeout(timeout)
        try:
            asking.sendto(query, (server, port))
            deadline = time.monotonic() + timeout
            while True:
                answer, _ = asking.recvfrom(4096)
                if answer[:2] == query[:2]:
                    break
                asking.settimeout(max(0.01, deadline - time.monotonic()))
        except TimeoutError:
            return Public((), f"no answer within {timeout:g} s", server)
        except OSError as error:
            return Public((), f"it could not be reached: {error}", server)
    try:
        return Public(_addresses(answer), "", server)
    except (IndexError, struct.error):
        return Public((), "its answer could not be read", server)


def _addresses(answer: bytes) -> tuple[str, ...]:
    """The A records of a DNS answer, in order (none for NXDOMAIN or an empty answer)."""
    flags, questions, answers = struct.unpack(">HHH", answer[2:8])
    if flags & 0x000F:  # NXDOMAIN, a refusal: no address
        return ()
    at = 12
    for _ in range(questions):
        at = _past_name(answer, at) + 4
    found = []
    for _ in range(answers):
        at = _past_name(answer, at)
        kind, _class, _ttl, length = struct.unpack(">HHIH", answer[at : at + 10])
        at += 10
        if kind == 1 and length == 4:
            found.append(socket.inet_ntoa(answer[at : at + 4]))
        at += length
    return tuple(found)


def _past_name(message: bytes, at: int) -> int:
    """Where the name starting at `at` ends: its labels, up to the empty one or a pointer elsewhere (compression)."""
    while True:
        length = message[at]
        if length & 0xC0 == 0xC0:
            return at + 2
        if length == 0:
            return at + 1
        at += length + 1


def _why(error: httpx2.HTTPError) -> str:
    """Why an address did not answer, in words: a name not found, a certificate refused, no connection."""
    said = str(error) or type(error).__name__
    lowered = said.lower()
    if "getaddrinfo" in lowered or "name or service not known" in lowered or "nodename nor servname" in lowered:
        return f"this PC cannot find the name: {said}"
    if "certificate" in lowered or "ssl" in lowered:
        return f"its certificate was refused: {said}"
    return f"could not connect: {said}"
