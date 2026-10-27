"""Who the gateway answers (design 0001 §6.6, design 0002 §2.7): Clank's own programs, never a web page.

The gateway listens on 127.0.0.1 only, and its callers are all Clank's. On this machine: the service, VS Code's
completion and Clank's tools, at `127.0.0.1:<port>` (`localhost` and `[::1]` name the same place). In a workspace's
container: OpenCode and Clank's MCP server, at `edge:<port>` (`agents/service.py` writes both addresses), through the
edge, which relays bytes and leaves the Host header its client wrote (`workspaces/image/edge.py`). A request addressed
to any other host name is refused (421, as the service's own API refuses one, `kernel/api.py`): a web page whose name
is made to point at 127.0.0.1 (DNS rebinding) reaches the port, but its requests carry its own name.

A request a browser made is refused too (403), whatever its host: one with an `Origin` header (a web page's script or
form), or with `Sec-Fetch-Site` other than `none` (a page's link, image or frame; `none` is an address the owner typed,
which a browser sends without `Origin` for a GET). None of Clank's own callers sends either: OpenCode (Bun's fetch),
Clank's MCP server (Python's urllib) and the service (httpx) send no such header, and Node's fetch, VS Code's
completion's, adds only `Sec-Fetch-Mode`, which is not read here.

Both checks are made before any route, as plain ASGI (`OnlyClanksCallers`), so a streamed answer passes through it
untouched and a client that leaves is seen by the route as before.
"""

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

NAMES = ("127.0.0.1", "localhost", "[::1]", "edge")  # the gateway's host names, each with its port
WRONG_HOST = (
    "the gateway answers only requests addressed to {hosts} (a defense against a web page that poses as this "
    "machine), not to {given}"
)
FROM_A_BROWSER = "the gateway answers Clank's own programs, never a web page: this request came from a browser ({how})"


def hosts(port: int) -> tuple[str, ...]:
    """The Host values the gateway answers when it listens on `port`."""
    return tuple(f"{name}:{port}" for name in NAMES)


class OnlyClanksCallers:
    """The gateway's door: a request addressed to another host name, or one a browser made, is refused before any
    route; every other passes on as it came."""

    def __init__(self, app: ASGIApp, *, port: int) -> None:
        self.app = app
        self.hosts = hosts(port)
        self.listed = f"{', '.join(self.hosts[:-1])} or {self.hosts[-1]}"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """An HTTP request refused, or passed on as it came; anything else (the application's start and end) passed
        on."""
        if scope["type"] == "http":
            refused = self.refusal(Headers(scope=scope))
            if refused is not None:
                await refused(scope, receive, send)
                return
        await self.app(scope, receive, send)

    def refusal(self, headers: Headers) -> JSONResponse | None:
        """Why a request with these headers is refused, as the answer to give; None when it may pass."""
        host = headers.get("host", "").lower()
        if host not in self.hosts:
            return _refused(421, "wrong_host", WRONG_HOST.format(hosts=self.listed, given=host[:80] or "none"))
        origin = headers.get("origin")
        if origin is not None:
            return _refused(403, "browser_refused", FROM_A_BROWSER.format(how=f"Origin: {origin[:80]}"))
        site = headers.get("sec-fetch-site")
        if site is not None and site.strip().lower() != "none":
            return _refused(403, "browser_refused", FROM_A_BROWSER.format(how=f"Sec-Fetch-Site: {site[:40]}"))
        return None


def _refused(status: int, code: str, message: str) -> JSONResponse:
    """A refusal in OpenAI's shape, which OpenCode shows, with the `code` and `message` the other routes' have."""
    return JSONResponse({"error": {"message": message, "type": code, "code": code}}, status_code=status)
