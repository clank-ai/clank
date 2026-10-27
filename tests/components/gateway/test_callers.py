"""Design 0001 §6.6, design 0002 §2.7 and design 0004 §3: the gateway answers Clank's own programs only. A request
addressed to a host name other than the gateway's own is refused (421, as the service's API refuses one: a defense
against DNS rebinding), whatever its route: the gateway answers `127.0.0.1`, `localhost` and `[::1]` with the port it
listens on (the service, VS Code's completion) and `edge` with that port (a workspace's container, through the edge,
which relays bytes and leaves the Host its client wrote). A request a browser made is refused (403): one with an
`Origin` header, or with `Sec-Fetch-Site` other than `none`; what Clank's own callers send passes, the `Sec-Fetch-Mode`
that Node's fetch adds included."""

import asyncio
from typing import Any

from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from clank.components.gateway.callers import OnlyClanksCallers
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import create_gateway

PORT = 18311
OWN = [f"127.0.0.1:{PORT}", f"localhost:{PORT}", f"[::1]:{PORT}", f"edge:{PORT}"]
OTHERS = [
    f"attacker.example:{PORT}",  # a web page's own name, pointed at this machine (DNS rebinding)
    f"edge.attacker.example:{PORT}",
    f"localhost.:{PORT}",
    f"127.0.0.1:{PORT + 1}",  # another port
    "127.0.0.1",
    "edge",
    "testserver",
]
ROUTES = [("GET", "/health"), ("GET", "/v1/models"), ("POST", "/v1/chat/completions"), ("POST", "/agents/show"),
          ("GET", "/notion/databases"), ("GET", "/holds")]  # fmt: skip


def gateway(port: int = PORT, listening: int | None = None) -> TestClient:
    app = create_gateway(Routes(), GatewaySettings(port=port), None, port=listening)
    return TestClient(app, base_url=f"http://127.0.0.1:{listening or port}")


def test_the_gateway_answers_its_own_host_names_with_its_port() -> None:
    with gateway() as http:
        for host in OWN:
            for path in ("/health", "/v1/models"):
                assert http.get(path, headers={"Host": host}).status_code == 200, (host, path)


def test_a_request_addressed_to_another_host_is_refused_whatever_its_route() -> None:
    with gateway() as http:
        for host in OTHERS:
            for method, path in ROUTES:
                answer = http.request(method, path, headers={"Host": host}, json={})
                assert answer.status_code == 421, (host, path)
                error = answer.json()["error"]
                assert error["code"] == "wrong_host", (host, path)
                assert f"127.0.0.1:{PORT}, localhost:{PORT}, [::1]:{PORT} or edge:{PORT}" in error["message"]


def test_the_gateway_answers_the_port_it_listens_on() -> None:
    """Its process is given its port (`--port`), which its settings' may not be."""
    with gateway(port=PORT, listening=PORT + 7) as http:
        assert http.get("/health").status_code == 200
        assert http.get("/health", headers={"Host": f"edge:{PORT + 7}"}).status_code == 200
        assert http.get("/health", headers={"Host": f"127.0.0.1:{PORT}"}).status_code == 421


def test_a_request_a_browser_made_is_refused() -> None:
    browsers = [
        {"Origin": "https://attacker.example"},  # a web page's script or form
        {"Origin": "null"},  # a sandboxed frame, a file
        {"Origin": f"http://127.0.0.1:{PORT}"},  # even one that says it is the gateway's own
        {"Sec-Fetch-Site": "cross-site"},  # a web page's link, image or frame
        {"Sec-Fetch-Site": "same-site"},
        {"Sec-Fetch-Site": "same-origin"},
    ]
    with gateway() as http:
        for headers in browsers:
            for method, path in ROUTES:
                answer = http.request(method, path, headers=headers, json={})
                assert answer.status_code == 403, (headers, path)
                error = answer.json()["error"]
                assert error["code"] == "browser_refused", (headers, path)
                assert "never a web page" in error["message"]


def test_what_clanks_own_callers_send_passes() -> None:
    """The headers of each of Clank's callers, as the gateway's records and a local server saw them: OpenCode (Bun's
    fetch), Clank's MCP server (Python's urllib), the service (httpx), VS Code's completion (Node's fetch: no `Origin`,
    no `Sec-Fetch-Site`), and the owner's browser on an address they typed (`Sec-Fetch-Site: none`)."""
    callers = [
        {"User-Agent": "opencode/1.19.4 ai-sdk/provider-utils/4.0.23 runtime/bun/1.4.4", "Accept": "*/*"},
        {"User-Agent": "Python-urllib/3.12", "Content-Type": "application/json"},
        {"User-Agent": "python-httpx2/2.13.1", "Accept": "*/*"},
        {"User-Agent": "node", "Accept-Language": "*", "Sec-Fetch-Mode": "cors"},
        {"Sec-Fetch-Site": "none", "Sec-Fetch-Mode": "navigate", "Sec-Fetch-Dest": "document"},
    ]
    with gateway() as http:
        for headers in callers:
            for host in OWN:
                assert http.get("/health", headers={**headers, "Host": host}).status_code == 200, (headers, host)


def test_a_request_without_a_host_is_refused_before_any_route() -> None:
    reached: list[str] = []

    async def routes(scope: Scope, receive: Receive, send: Send) -> None:
        reached.append(str(scope["path"]))

    sent: list[Message] = []

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        sent.append(message)

    scope: dict[str, Any] = {
        "type": "http", "method": "GET", "path": "/health", "raw_path": b"/health", "query_string": b"",
        "headers": [], "http_version": "1.1", "scheme": "http", "server": ("127.0.0.1", PORT),
        "client": ("127.0.0.1", 50000), "root_path": "",
    }  # fmt: skip
    asyncio.run(OnlyClanksCallers(routes, port=PORT)(scope, receive, send))
    assert reached == []
    assert sent[0]["status"] == 421
