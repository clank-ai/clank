"""Design 0024 §1, §2 and §7 (decision 0141): the forward proxy at the gateway, the agent's only way to the internet.
A request names its workspace by the token in the proxy's URL (derived from the service's local token, so it names
the workspace and nothing need be handed); a host the workspace is allowed, exact or by suffix, is reached: a
`CONNECT` tunnel carries bytes both ways and is never opened, plain HTTP is forwarded with its path recorded; any
other host is refused with 403 and the words that say how it is allowed; a private address is refused before
resolving and after, whatever the allowance; a wrong token gets 407; a name that cannot be resolved 502; every
exchange is logged by time, workspace, host, method, status, bytes each way and duration, never a body, one file a
day, the days older than kept removed."""

import asyncio
import base64
import http.client
import json
import socket
import socketserver
import threading
from collections.abc import Awaitable, Callable, Iterator
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.proxy import NetworkLog, Proxy, allowed_host, network_token, private_address
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import create_gateway
from tests.support.served import free_port

HOSTS = {"paper": ["docs.test", ".example.test", "echo.test", "private.test", "10.0.0.9", "localhost"], "other": []}
TOKENS = {"paper": "tok-paper", "other": "tok-other"}
Ask = Callable[[str, str], Awaitable[str]]


class Page(BaseHTTPRequestHandler):
    """A plain HTTP upstream: it says which path was asked."""

    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        body = f"page {self.path}".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


class Shout(socketserver.BaseRequestHandler):
    """A TCP upstream for tunnels: it answers each piece in capitals."""

    def handle(self) -> None:
        while piece := self.request.recv(65536):
            self.request.sendall(piece.upper())


class Served:
    """The proxy and its upstreams on this machine, with a resolver that maps the test's names to them."""

    def __init__(self, folder: Path, ask: Ask | None = None) -> None:
        self.pages = ThreadingHTTPServer(("127.0.0.1", 0), Page)
        self.shouts = socketserver.ThreadingTCPServer(("127.0.0.1", 0), Shout)
        self.shouts.daemon_threads = True
        for server in (self.pages, self.shouts):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        self.log = NetworkLog(folder, keep_days=3)
        self.port = free_port()
        self.proxy = Proxy(
            hosts=HOSTS.get, token_of=lambda workspace: TOKENS.get(workspace, ""), log=self.log,
            resolve=self.resolve, private=lambda ip: ip != "127.0.0.1" and private_address(ip), ask=ask,
        )  # fmt: skip
        self.loop = asyncio.new_event_loop()
        self.ready = threading.Event()
        self.stopping: asyncio.Event | None = None
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()
        assert self.ready.wait(10)

    async def resolve(self, host: str, port: int) -> list[tuple[str, int]]:
        if host in ("docs.test", "www.example.test", "example.test"):
            return [("127.0.0.1", self.pages.server_port)]
        if host == "echo.test":
            return [("127.0.0.1", self.shouts.server_address[1])]
        if host == "private.test":
            return [("10.0.0.5", port)]
        raise OSError(f"{host} cannot be resolved")

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self._serve())
        self.loop.close()

    async def _serve(self) -> None:
        server = await self.proxy.serve("127.0.0.1", self.port)
        self.stopping = asyncio.Event()
        self.ready.set()
        async with server:
            await self.stopping.wait()

    def close(self) -> None:
        if self.stopping is not None:
            self.loop.call_soon_threadsafe(self.stopping.set)
        self.thread.join(10)
        for server in (self.pages, self.shouts):
            server.shutdown()
            server.server_close()

    def lines(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        for file in sorted(self.log.folder.glob("*.jsonl")):
            found += [json.loads(line) for line in file.read_text(encoding="utf-8").splitlines() if line.strip()]
        return found


def auth(workspace: str, token: str) -> dict[str, str]:
    return {"Proxy-Authorization": "Basic " + base64.b64encode(f"{workspace}:{token}".encode()).decode()}


@pytest.fixture
def served(tmp_path: Path) -> Iterator[Served]:
    made = Served(tmp_path / "network")
    yield made
    made.close()


def get(served: Served, url: str, headers: dict[str, str]) -> tuple[int, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", served.port, timeout=10)
    try:
        connection.putrequest("GET", url, skip_host=True, skip_accept_encoding=True)
        connection.putheader("Host", url.split("/")[2])
        for name, value in headers.items():
            connection.putheader(name, value)
        connection.endheaders()
        answer = connection.getresponse()
        return answer.status, answer.read()
    finally:
        connection.close()


def connect(served: Served, target: str, headers: dict[str, str]) -> tuple[int, bytes, socket.socket | None]:
    """A CONNECT through the proxy: the status, the answer's body (a refusal's words), and the tunnel when opened."""
    connection = socket.create_connection(("127.0.0.1", served.port), timeout=10)
    lines = [f"CONNECT {target} HTTP/1.1", f"Host: {target}", *(f"{k}: {v}" for k, v in headers.items()), "", ""]
    connection.sendall("\r\n".join(lines).encode())
    head = b""
    while b"\r\n\r\n" not in head:
        piece = connection.recv(65536)
        if not piece:
            break
        head += piece
    status_line, _, rest = head.partition(b"\r\n")
    status = int(status_line.split()[1])
    if status == 200:
        return status, b"", connection
    headers_part, _, body = rest.partition(b"\r\n\r\n")
    length = next(
        (int(h.split(b":")[1]) for h in headers_part.split(b"\r\n") if h.lower().startswith(b"content-length")), 0
    )
    while len(body) < length:
        piece = connection.recv(65536)
        if not piece:
            break
        body += piece
    connection.close()
    return status, body, None


def test_a_connect_to_an_allowed_host_is_a_tunnel_both_ways_logged_without_its_bytes(served: Served) -> None:
    status, _, tunnel = connect(served, "echo.test:443", auth("paper", "tok-paper"))
    assert status == 200
    assert tunnel is not None
    tunnel.sendall(b"hello tunnel")
    assert tunnel.recv(65536) == b"HELLO TUNNEL", "bytes both ways, as they are"
    tunnel.close()
    # the log line comes once both sides are done
    for _ in range(100):
        if served.lines():
            break
        threading.Event().wait(0.05)
    [line] = served.lines()
    assert (line["workspace"], line["host"], line["port"], line["method"], line["status"]) == (
        "paper", "echo.test", 443, "CONNECT", 200,
    )  # fmt: skip
    assert (line["sent"], line["received"]) == (12, 12)
    assert "path" not in line
    assert "hello" not in json.dumps(line).lower(), "never a tunnel's bytes"
    assert line["seconds"] >= 0


def test_plain_http_to_an_allowed_host_is_forwarded_and_its_path_recorded(served: Served) -> None:
    status, body = get(served, "http://docs.test/papers/1?x=1", auth("paper", "tok-paper"))
    assert (status, body) == (200, b"page /papers/1?x=1")
    for _ in range(100):
        if served.lines():
            break
        threading.Event().wait(0.05)
    [line] = served.lines()
    assert (line["host"], line["method"], line["path"], line["status"]) == ("docs.test", "GET", "/papers/1?x=1", 200)
    assert line["received"] > 0


def test_a_host_not_allowed_is_refused_in_plain_words_and_the_refusal_logged(served: Served) -> None:
    status, body = get(served, "http://nope.test/", auth("paper", "tok-paper"))
    assert status == 403
    words = body.decode()
    assert "nope.test is not allowed for the workspace paper" in words
    assert "clank workspace allow" in words
    assert "--host nope.test" in words
    status, body, _ = connect(served, "docs.test:443", auth("other", "tok-other"))
    assert status == 403, "an allowance is the workspace's, not another's"
    assert "docs.test is not allowed for the workspace other" in body.decode()
    for _ in range(100):
        if len(served.lines()) == 2:
            break
        threading.Event().wait(0.05)
    assert [(line["status"], line["why"]) for line in served.lines()] == [(403, "not allowed"), (403, "not allowed")]


def test_a_suffix_allows_the_name_and_every_name_under_it() -> None:
    assert allowed_host("example.test", [".example.test"]) is True
    assert allowed_host("www.example.test", [".example.test"]) is True
    assert allowed_host("a.b.example.test", [".example.test"]) is True
    assert allowed_host("badexample.test", [".example.test"]) is False
    assert allowed_host("docs.test", ["docs.test"]) is True
    assert allowed_host("sub.docs.test", ["docs.test"]) is False, "an exact name is that name alone"
    assert allowed_host("Docs.Test.", ["docs.test"]) is True, "names compare in lower case, the root dot dropped"
    assert allowed_host("docs.test", []) is False


def test_a_private_address_is_refused_before_resolving_and_after_whatever_the_allowance(served: Served) -> None:
    for target in ("10.0.0.9:443", "localhost:443", "edge:443", "host.docker.internal:443", "[::1]:443"):
        status, body, _ = connect(served, target, auth("paper", "tok-paper"))
        assert status == 403, target
        assert "private" in body.decode(), target
    status, body, _ = connect(served, "private.test:443", auth("paper", "tok-paper"))
    assert status == 403
    assert "private" in body.decode(), "a public name that resolves to a private address is refused too"
    for ip in ("127.0.0.1", "10.1.2.3", "192.168.0.1", "172.16.5.5", "172.31.255.1", "169.254.1.1", "100.100.1.1",
               "::1", "fe80::1", "fd00::1", "0.0.0.0"):  # fmt: skip
        assert private_address(ip) is True, ip
    for ip in ("8.8.8.8", "151.101.1.63", "2606:4700::1", "172.32.0.1", "100.128.0.1"):
        assert private_address(ip) is False, ip


def test_a_wrong_or_missing_token_is_refused_with_407(served: Served) -> None:
    connection = http.client.HTTPConnection("127.0.0.1", served.port, timeout=10)
    try:
        connection.putrequest("GET", "http://docs.test/", skip_host=True, skip_accept_encoding=True)
        connection.putheader("Host", "docs.test")
        connection.endheaders()
        answer = connection.getresponse()
        assert answer.status == 407
        assert answer.getheader("Proxy-Authenticate", "").startswith("Basic")
        answer.read()
    finally:
        connection.close()
    assert get(served, "http://docs.test/", auth("paper", "wrong"))[0] == 407
    assert get(served, "http://docs.test/", auth("nobody", "tok-paper"))[0] == 407
    assert served.lines() == [], "a request that names no workspace is nobody's: not logged as one"


def test_a_host_that_cannot_be_resolved_is_answered_502(served: Served) -> None:
    status, body, _ = connect(served, "unknown.example.test:443", auth("paper", "tok-paper"))
    assert status == 502
    assert "could not be resolved" in body.decode()


def test_the_workspace_token_is_derived_from_the_local_token_and_names_the_workspace() -> None:
    assert network_token("local-secret", "paper") == network_token("local-secret", "paper")
    assert network_token("local-secret", "paper") != network_token("local-secret", "other")
    assert network_token("local-secret", "paper") != network_token("another", "paper")
    token = network_token("local-secret", "paper")
    assert len(token) == 32
    assert all(c in "0123456789abcdef" for c in token)


def test_the_network_log_keeps_a_file_a_day_and_removes_the_days_older_than_kept(tmp_path: Path) -> None:
    today = [date(2026, 10, 26)]
    log = NetworkLog(tmp_path / "network", keep_days=3, today=lambda: today[0])
    (tmp_path / "network").mkdir()
    for old in ("2026-10-20", "2026-10-24"):
        (tmp_path / "network" / f"{old}.jsonl").write_text("{}\n", encoding="utf-8")
    log.write({"workspace": "paper", "host": "docs.test", "status": 200})
    names = sorted(file.name for file in (tmp_path / "network").glob("*.jsonl"))
    assert names == ["2026-10-24.jsonl", "2026-10-26.jsonl"], "the days within the three kept stay"
    [line] = (tmp_path / "network" / "2026-10-26.jsonl").read_text(encoding="utf-8").splitlines()
    written = json.loads(line)
    assert written["host"] == "docs.test"
    assert written["time"].startswith("2026-10-26") or "T" in written["time"]


def test_the_gateway_serves_the_proxy_with_its_application_on_the_proxy_port() -> None:
    """Design 0024 §2: the proxy runs in the gateway's process, started and stopped with it, on `proxy_port`."""
    port = free_port()
    proxy = Proxy(hosts=lambda workspace: None, token_of=lambda workspace: "")
    app = create_gateway(Routes(), GatewaySettings(proxy_port=port), None, proxy=proxy)
    with TestClient(app):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        try:
            connection.putrequest("GET", "http://docs.test/", skip_host=True, skip_accept_encoding=True)
            connection.putheader("Host", "docs.test")
            connection.endheaders()
            assert connection.getresponse().status == 407
        finally:
            connection.close()
    with pytest.raises((ConnectionRefusedError, TimeoutError)):  # nothing answers: refused, or (Windows, a loop
        socket.create_connection(("127.0.0.1", port), timeout=2).close()  # stopped mid-accept) never answered


def test_the_routes_carry_each_workspaces_hosts_for_the_proxy() -> None:
    routes = Routes()
    routes.update({"slots": {}, "roles": {}, "network": {"paper": {"hosts": [".arxiv.org", "pypi.org"]}}})
    assert routes.hosts_of("paper") == [".arxiv.org", "pypi.org"]
    assert routes.hosts_of("other") is None, "a workspace the routes do not name is allowed nothing"


def test_a_host_not_allowed_is_asked_for_and_let_out_on_once_or_always_and_refused_on_no(tmp_path: Path) -> None:
    """Design 0024 §3: the connection is held while the owner is asked; the answer decides this request."""
    decisions = {"echo.test": "once", "docs.test": "always", "nope.test": "no"}
    asked: list[tuple[str, str]] = []

    async def ask(workspace: str, host: str) -> str:
        asked.append((workspace, host))
        return decisions.get(host, "no")

    served = Served(tmp_path / "network", ask=ask)
    try:
        status, _, tunnel = connect(served, "echo.test:443", auth("other", "tok-other"))
        assert status == 200, "once: this request goes out"
        assert tunnel is not None
        tunnel.sendall(b"hi")
        assert tunnel.recv(65536) == b"HI"
        tunnel.close()
        assert get(served, "http://docs.test/a", auth("other", "tok-other")) == (200, b"page /a"), "always: out too"
        status, body = get(served, "http://nope.test/", auth("other", "tok-other"))
        assert status == 403
        words = body.decode()
        assert "nope.test is not allowed for the workspace other" in words
        assert "asked" in words
        assert "did not allow" in words
        assert asked == [("other", "echo.test"), ("other", "docs.test"), ("other", "nope.test")]
        for _ in range(100):
            if len(served.lines()) == 3:
                break
            threading.Event().wait(0.05)
        assert [(line["host"], line["status"], line.get("why")) for line in served.lines()] == [
            ("echo.test", 200, "asked: once"), ("docs.test", 200, "asked: always"), ("nope.test", 403, "asked: no"),
        ]  # fmt: skip
        assert get(served, "http://docs.test/b", auth("paper", "tok-paper")) == (200, b"page /b")
        assert asked[-1] == ("other", "nope.test"), "a host allowed is never asked for"
    finally:
        served.close()
