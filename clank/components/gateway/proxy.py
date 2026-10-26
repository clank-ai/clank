"""The forward proxy at the gateway (design 0024 §1, §2 and §7, decision 0141): the agent's only way to the internet,
open only to the hosts the owner allowed for its workspace.

A workspace's container is told `HTTP_PROXY=http://<workspace>:<token>@edge:<port>` (and the same for HTTPS and ALL);
the edge forwards the port here. The token is `network_token`: the SHA-256 HMAC of the service's local token over the
workspace's name, so the gateway process (which holds the local token) checks it without being handed anything, it
survives every restart, and it names the workspace; a request without the right one is answered 407.

`Proxy` serves HTTP/1.1 on the loopback: a `CONNECT host:port` (TLS, or any stream) to a host the workspace is
allowed (`allowed_host`: an exact name, or a suffix `.example.org` for the name and every name under it) is resolved
here (the container has no way to the internet's names), refused when the name or any address it resolves to is
private (`private_address`: the machine, the local networks, the carrier range the tailnet uses, link-local), else
joined to the first address found, bytes both ways, counted and never read; a plain request (`GET http://host/path`)
is forwarded to its host with the proxy's own headers dropped and `Connection: close`, one request a connection, its
path recorded. A host not allowed is asked for when the proxy has an `ask` (design 0024 §3: the connection held up to
`ASK_SECONDS` while the service asks the owner; `always` or `once` let the request out, logged as asked), else, or
when the owner did not allow it, refused 403 with the words that say the host, the workspace and how it is
allowed (`clank workspace allow FOLDER --host NAME`); a name that cannot be resolved 502. Every exchange is one line of
`NetworkLog` (`logs/network/<day>.jsonl`: time, workspace, host, port, method, the path of a plain request, status,
bytes sent and received, seconds, why refused), never a body, never a tunnel's bytes; the days older than kept are
removed when a day's first line is written; `recent` and `by_host` read it back for the owner (design 0024 §4). The
resolver and the private check can be given (the tests reach upstreams on this machine).
"""

import asyncio
import base64
import contextlib
import hashlib
import hmac
import ipaddress
import json
import logging
import threading
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
CHUNK = 65536
HEAD_MOST = 64 * 1024  # bytes of a request's head read before it is refused as too long
KEEP_DAYS = 30
ASK_SECONDS = 60  # how long a connection is held while the owner is asked about its host (design 0024 §3)
PRIVATE_NAMES = ("localhost", "edge", "host.docker.internal", "gateway.docker.internal")
PRIVATE_SUFFIXES = (".localhost", ".local", ".internal", ".home.arpa")
# The private ranges (RFC 1918, the loopback, link-local, the carrier range 100.64/10 the tailnet uses, this host,
# unique local and link-local IPv6) besides what `ipaddress` calls private.
PRIVATE_NETWORKS = [ipaddress.ip_network(each) for each in ("100.64.0.0/10", "0.0.0.0/8", "fc00::/7", "fe80::/10")]
HOP_BY_HOP = ("proxy-authorization", "proxy-connection", "connection", "keep-alive", "te", "trailer", "upgrade")
Resolve = Callable[[str, int], Awaitable[list[tuple[str, int]]]]
Ask = Callable[[str, str], Awaitable[str]]  # workspace, host: always, once or no


def network_token(local: str, workspace: str) -> str:
    """A workspace's token at the proxy: the local token's HMAC over its name, 32 hex characters."""
    return hmac.new(local.encode(), f"network:{workspace}".encode(), hashlib.sha256).hexdigest()[:32]


def allowed_host(host: str, patterns: list[str]) -> bool:
    """Whether a host is among the patterns: its own name exactly, or under a suffix (`.example.org` allows
    `example.org` and every name under it); names compare in lower case, a root dot dropped."""
    name = host.lower().rstrip(".")
    for pattern in patterns:
        wanted = pattern.lower().strip().rstrip(".")
        if not wanted:
            continue
        if wanted.startswith("."):
            if name == wanted[1:] or name.endswith(wanted):
                return True
        elif name == wanted:
            return True
    return False


def private_address(ip: str) -> bool:
    """Whether an address is one the agent must never reach: the machine, a local network, the tailnet's range."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return True  # not an address at all: nothing to reach
    if address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified:
        return True
    if address.is_multicast or address.is_reserved:
        return True
    return any(address in network for network in PRIVATE_NETWORKS)


def private_name(host: str) -> bool:
    """Whether a name is the machine's or a local one, before it is resolved."""
    name = host.lower().rstrip(".")
    return name in PRIVATE_NAMES or any(name.endswith(suffix) for suffix in PRIVATE_SUFFIXES)


async def resolve_name(host: str, port: int) -> list[tuple[str, int]]:
    """The addresses a name resolves to, with the port, as the system resolves them."""
    found = await asyncio.get_running_loop().getaddrinfo(host, port, type=2)  # SOCK_STREAM
    seen: list[tuple[str, int]] = []
    for _, _, _, _, address in found:
        pair = (str(address[0]), int(address[1]))
        if pair not in seen:
            seen.append(pair)
    return seen


class NetworkLog:
    """One JSON line an exchange, in one file a day."""

    def __init__(self, folder: Path, keep_days: int = KEEP_DAYS, today: Callable[[], date] | None = None) -> None:
        self.folder = folder
        self.keep_days = keep_days
        self.today = today or date.today
        self._lock = threading.Lock()
        self._day = ""

    def write(self, record: dict[str, Any]) -> None:
        """Append a record to today's file, with its time; when a new day's file begins, remove the days older than
        kept."""
        day = self.today().isoformat()
        line = json.dumps({"time": datetime.now(UTC).isoformat(timespec="milliseconds"), **record},
                          ensure_ascii=False)  # fmt: skip
        with self._lock:
            try:
                self.folder.mkdir(parents=True, exist_ok=True)
                if day != self._day:
                    self._day = day
                    self._prune(day)
                with (self.folder / f"{day}.jsonl").open("a", encoding="utf-8") as file:
                    file.write(line + "\n")
            except OSError as error:
                log.warning("the network log could not be written: %s", error)

    def recent(self, limit: int, workspace: str = "") -> list[dict[str, Any]]:
        """The newest exchanges first, of one workspace when named, read from the files' ends (design 0024 §4)."""
        from clank.components.gateway.records import _newest_first, _parsed

        found: list[dict[str, Any]] = []
        if not self.folder.is_dir():
            return found
        for line in _newest_first(self.folder):
            record = _parsed(line)
            if record is None or (workspace and record.get("workspace") != workspace):
                continue
            found.append(record)
            if len(found) >= limit:
                break
        return found

    def by_host(self) -> dict[str, dict[str, int]]:
        """Today's exchanges summed by host: the bytes received and sent, and how many; the most received first."""
        from clank.components.gateway.records import _parsed

        file = self.folder / f"{self.today().isoformat()}.jsonl"
        summed: dict[str, dict[str, int]] = {}
        if not file.is_file():
            return summed
        for line in file.read_text(encoding="utf-8", errors="replace").splitlines():
            record = _parsed(line)
            if record is None or not record.get("host"):
                continue
            row = summed.setdefault(str(record["host"]), {"sent": 0, "received": 0, "exchanges": 0})
            row["sent"] += int(record.get("sent") or 0)
            row["received"] += int(record.get("received") or 0)
            row["exchanges"] += 1
        return dict(sorted(summed.items(), key=lambda item: -item[1]["received"]))

    def _prune(self, day: str) -> None:
        for file in self.folder.glob("*.jsonl"):
            try:
                written = date.fromisoformat(file.stem)
            except ValueError:
                continue
            if (date.fromisoformat(day) - written).days >= self.keep_days:
                file.unlink(missing_ok=True)


class Refused(Exception):
    """A request the proxy answers itself, with a status and the words."""

    def __init__(self, status: int, why: str, words: str) -> None:
        super().__init__(words)
        self.status, self.why, self.words = status, why, words


class Proxy:
    """The forward proxy: `hosts(workspace)` is the workspace's allowances (None for an unknown workspace),
    `token_of(workspace)` its token; `ask(workspace, host)`, when given, is awaited for a host not allowed while the
    connection is held (design 0024 §3: `always`, `once` or `no`); `resolve` and `private` as the module's unless
    given."""

    def __init__(
        self,
        hosts: Callable[[str], list[str] | None],
        token_of: Callable[[str], str],
        log: NetworkLog | None = None,
        resolve: Resolve | None = None,
        private: Callable[[str], bool] | None = None,
        ask: Ask | None = None,
    ) -> None:
        self.hosts = hosts
        self.token_of = token_of
        self.log = log
        self.resolve = resolve or resolve_name
        self.private = private or private_address
        self.ask = ask

    async def serve(self, host: str, port: int) -> asyncio.AbstractServer:
        """Listen on `host:port`; the server returned is the caller's to run and to close."""
        return await asyncio.start_server(self.handle, host=host, port=port)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        """One connection: a request read, answered or carried; then closed."""
        began = time.monotonic()
        record: dict[str, Any] = {}
        try:
            try:
                head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=30)
            except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, TimeoutError, ConnectionError):
                return
            method, target, headers = _parse_head(head)
            workspace = self._workspace(headers)
            if workspace is None:
                words = "Proxy authentication: the workspace's token in the proxy's URL is missing or wrong."
                await _answer(writer, 407, words, extra='Proxy-Authenticate: Basic realm="Clank"\r\n')
                return
            host, port, path = _target(method, target, headers)
            record = {"workspace": workspace, "host": host, "port": port, "method": method}
            if method != "CONNECT":
                record["path"] = path
            try:
                address, why = await self._admitted(workspace, host, port)
                if why:
                    record["why"] = why
                if method == "CONNECT":
                    sent, received = await self._tunnel(reader, writer, address)
                    record.update(status=200, sent=sent, received=received)
                else:
                    status, sent, received = await self._forward(reader, writer, address, head, headers, method, path)
                    record.update(status=status, sent=sent, received=received)
            except Refused as refused:
                record.update(status=refused.status, why=refused.why)
                await _answer(writer, refused.status, refused.words)
        except Exception as error:
            log.warning("the proxy could not serve a request: %s", error)
            record.setdefault("status", 500)
            record["why"] = "failed"
        finally:
            if record and self.log is not None:
                if "status" not in record:  # ended before an answer (the handler canceled, the client gone)
                    record.update(status=0, why="ended")
                record["seconds"] = round(time.monotonic() - began, 3)
                self.log.write(record)
            writer.close()

    def _workspace(self, headers: dict[str, str]) -> str | None:
        """The workspace the request's credentials name, when they are its own."""
        given = headers.get("proxy-authorization", "")
        if not given.lower().startswith("basic "):
            return None
        try:
            decoded = base64.b64decode(given[6:].strip(), validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
        workspace, _, token = decoded.partition(":")
        if not workspace or not token:
            return None
        wanted = self.token_of(workspace)
        if not wanted or not hmac.compare_digest(wanted.encode(), token.encode()):
            return None
        return workspace

    async def _admitted(self, workspace: str, host: str, port: int) -> tuple[tuple[str, int], str]:
        """The address to connect to for an allowed, public host, and why it was let out when it was asked for
        (`asked: once`, `asked: always`; "" for a host allowed); `Refused` otherwise."""
        patterns = self.hosts(workspace)
        literal: str | None = None
        with contextlib.suppress(ValueError):  # a name, not an address
            literal = str(ipaddress.ip_address(host.strip("[]")))
        if (literal is not None and self.private(literal)) or private_name(host):
            raise Refused(403, "private", _private(host))
        why = ""
        if not allowed_host(host, patterns or []):
            if self.ask is None:
                raise Refused(403, "not allowed", _not_allowed(host, workspace))
            decision = await self.ask(workspace, host)  # the connection held meanwhile (design 0024 §3)
            if decision not in ("always", "once"):
                raise Refused(403, "asked: no", _not_allowed(host, workspace, asked=True))
            why = f"asked: {decision}"
        if literal is not None:
            return (literal, port), why
        try:
            found = await self.resolve(host, port)
        except OSError as error:
            raise Refused(502, "unresolved", f"{host} could not be resolved: {error}") from error
        if not found:
            raise Refused(502, "unresolved", f"{host} could not be resolved: no address")
        if any(self.private(address) for address, _ in found):
            raise Refused(403, "private", _private(host))
        return found[0], why

    async def _tunnel(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, address: tuple[str, int]
    ) -> tuple[int, int]:
        """A CONNECT: the upstream connected, 200 said, then bytes both ways until both sides are done."""
        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(asyncio.open_connection(*address), timeout=30)
        except (OSError, TimeoutError) as error:
            raise Refused(502, "unreachable", f"{address[0]}:{address[1]} could not be reached: {error}") from error
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
        try:
            sent, received = await asyncio.gather(_pipe(reader, upstream_writer), _pipe(upstream_reader, writer))
        finally:
            upstream_writer.close()
        return sent, received

    async def _forward(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        address: tuple[str, int],
        head: bytes,
        headers: dict[str, str],
        method: str,
        path: str,
    ) -> tuple[int, int, int]:
        """A plain request: forwarded to its host as an origin request with `Connection: close`, its body after,
        the answer back as it comes; the status answered, the bytes each way."""
        try:
            upstream_reader, upstream_writer = await asyncio.wait_for(asyncio.open_connection(*address), timeout=30)
        except (OSError, TimeoutError) as error:
            raise Refused(502, "unreachable", f"{address[0]}:{address[1]} could not be reached: {error}") from error
        try:
            lines = [f"{method} {path} HTTP/1.1"]
            raw_lines = head.decode("latin-1").split("\r\n")[1:]
            for line in raw_lines:
                name = line.partition(":")[0].strip().lower()
                if line and name not in HOP_BY_HOP:
                    lines.append(line)
            if "host" not in headers:
                lines.append(f"Host: {address[0]}")
            lines.append("Connection: close")
            rewritten = ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")
            upstream_writer.write(rewritten)
            await upstream_writer.drain()
            length = int(headers.get("content-length") or 0)
            sent = len(rewritten)
            while length > 0:
                piece = await reader.read(min(CHUNK, length))
                if not piece:
                    break
                upstream_writer.write(piece)
                await upstream_writer.drain()
                sent += len(piece)
                length -= len(piece)
            if "chunked" in headers.get("transfer-encoding", "").lower():
                sent += await _pipe(reader, upstream_writer)
            status_line = await upstream_reader.readline()
            status = int(status_line.split()[1]) if len(status_line.split()) > 1 else 502
            writer.write(status_line)
            await writer.drain()
            received = len(status_line) + await _pipe(upstream_reader, writer)
            return status, sent, received
        finally:
            upstream_writer.close()


def _parse_head(head: bytes) -> tuple[str, str, dict[str, str]]:
    """The request line's method and target, and the headers by lower-case name."""
    text = head.decode("latin-1")
    first, *rest = text.split("\r\n")
    parts = first.split()
    if len(parts) < 2:
        raise Refused(400, "malformed", "the request line could not be read")
    headers: dict[str, str] = {}
    for line in rest:
        if ":" in line:
            name, _, value = line.partition(":")
            headers[name.strip().lower()] = value.strip()
    return parts[0].upper(), parts[1], headers


def _target(method: str, target: str, headers: dict[str, str]) -> tuple[str, int, str]:
    """The host, the port and the path a request names: `CONNECT host:port`, or an absolute URL."""
    if method == "CONNECT":
        host, port = _host_port(target, 443)
        return host, port, ""
    if "://" in target:
        scheme, _, rest = target.partition("://")
        authority, slash, path = rest.partition("/")
        host, port = _host_port(authority, 443 if scheme.lower() == "https" else 80)
        return host, port, "/" + path if slash else "/"
    host, port = _host_port(headers.get("host", ""), 80)
    if not host:
        raise Refused(400, "malformed", "a plain request names its host in its URL or its Host header")
    return host, port, target or "/"


def _host_port(authority: str, default: int) -> tuple[str, int]:
    authority = authority.strip()
    if authority.startswith("["):  # an IPv6 literal
        host, _, rest = authority[1:].partition("]")
        port = int(rest[1:]) if rest.startswith(":") and rest[1:].isdigit() else default
        return host, port
    host, _, port_text = authority.rpartition(":")
    if not host or not port_text.isdigit():
        return authority, default
    return host, int(port_text)


def _not_allowed(host: str, workspace: str, asked: bool = False) -> str:
    if asked:
        return (
            f"{host} is not allowed for the workspace {workspace}: the owner was asked and did not allow it (the host "
            f"is not asked for again for a while). The owner allows it with `clank workspace allow FOLDER --host "
            f"{host}`; otherwise work without it."
        )
    return (
        f"{host} is not allowed for the workspace {workspace}: the owner allows it with "
        f"`clank workspace allow FOLDER --host {host}` (or you may ask once, in words, and otherwise work without it)."
    )


def _private(host: str) -> str:
    return f"{host} is a private address (this machine, a local network, the tailnet): the agent never reaches those."


async def _answer(writer: asyncio.StreamWriter, status: int, words: str, extra: str = "") -> None:
    """An answer of the proxy's own: the status, plain words, the connection closed."""
    reasons = {400: "Bad Request", 403: "Forbidden", 407: "Proxy Authentication Required", 500: "Internal Server Error",
               502: "Bad Gateway"}  # fmt: skip
    body = words.encode()
    head = (
        f"HTTP/1.1 {status} {reasons.get(status, 'Error')}\r\nContent-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body)}\r\n{extra}Connection: close\r\n\r\n"
    )
    try:
        writer.write(head.encode() + body)
        await writer.drain()
    except (ConnectionError, OSError):
        pass


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> int:
    """Bytes from one side to the other until the first is done (the second told); how many."""
    count = 0
    try:
        while data := await reader.read(CHUNK):
            writer.write(data)
            await writer.drain()
            count += len(data)
        if writer.can_write_eof():
            writer.write_eof()
    except (ConnectionError, OSError):
        pass
    return count
