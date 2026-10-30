"""Design 0024 §1, §3 and §7 (decision 0152): dev mode opens the agent's internet. While the routes say dev mode is
on, the proxy lets every public host out at once, for any workspace, whatever its allowances, and asks the owner
nothing; each exchange it let out is logged with why `dev mode`, by host, bytes and time as always, and one to a host
allowed as before. Private addresses stay refused, before resolving and after: this machine, the local networks, the
tailnet's range, Clank's own service on the edge. Turned on or off, dev mode applies from the next connection with
nothing restarted, and a connection held while the owner is asked goes out at once when it is turned on. The routes
the gateway's process follows carry dev mode as the runtime's settings have it, and the proxy its process makes reads
it there."""

import asyncio
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from clank.components.gateway.proxy import Refused
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import agent_proxy
from clank.components.gateway.service import Gateway
from clank.kernel.events import Actor
from tests.components.gateway.test_proxy import Served, auth, connect, get
from tests.components.runtime.conftest import Rig

YOU = Actor(kind="user", via="console")


def logged(served: Served, count: int) -> list[dict[str, Any]]:
    """The network log's lines once there are `count` (a tunnel's comes once both sides are done), by workspace and
    host."""
    for _ in range(200):
        if len(served.lines()) >= count:
            break
        threading.Event().wait(0.05)
    return sorted(served.lines(), key=lambda line: (line["workspace"], line["host"], line.get("path") or ""))


def test_in_dev_mode_every_public_host_goes_out_at_once_unasked_and_is_logged_why(tmp_path: Path) -> None:
    asked: list[tuple[str, str]] = []

    async def ask(workspace: str, host: str) -> str:
        asked.append((workspace, host))
        return "no"

    served = Served(tmp_path / "network", ask=ask, dev_mode=lambda: True)
    try:
        status, _, tunnel = connect(served, "echo.test:443", auth("other", "tok-other"))
        assert status == 200, "a host the workspace was never allowed: a git clone over HTTPS, say"
        assert tunnel is not None
        tunnel.sendall(b"clone")
        assert tunnel.recv(65536) == b"CLONE"
        tunnel.close()
        assert get(served, "http://docs.test/repo.git/info/refs", auth("other", "tok-other")) == (
            200, b"page /repo.git/info/refs",
        )  # fmt: skip
        assert get(served, "http://docs.test/a", auth("paper", "tok-paper")) == (200, b"page /a")
        assert asked == [], "nobody is asked, and nothing waits"
        lines = logged(served, 3)
        assert [(line["workspace"], line["host"], line["status"], line.get("why")) for line in lines] == [
            ("other", "docs.test", 200, "dev mode"), ("other", "echo.test", 200, "dev mode"),
            ("paper", "docs.test", 200, None),
        ], "what dev mode let out says so; a host allowed goes out as it always did"  # fmt: skip
        assert all(line["received"] > 0 and line["sent"] > 0 and line["seconds"] >= 0 for line in lines), (
            "the log keeps its sizes and times"
        )
    finally:
        served.close()


def test_in_dev_mode_private_addresses_stay_refused_before_resolving_and_after(tmp_path: Path) -> None:
    served = Served(tmp_path / "network", dev_mode=lambda: True)
    try:
        for target in ("10.0.0.9:443", "localhost:443", "edge:443", "host.docker.internal:443", "[::1]:443",
                       "100.100.1.1:443", "192.168.1.10:22", "169.254.169.254:80"):  # fmt: skip
            status, body, _ = connect(served, target, auth("other", "tok-other"))
            assert status == 403, target
            assert "private" in body.decode(), target
        status, body, _ = connect(served, "private.test:443", auth("other", "tok-other"))
        assert status == 403, "a public name that resolves to a private address"
        assert "private" in body.decode()
        status, body = get(served, "http://edge:18210/v1/models", auth("other", "tok-other"))
        assert status == 403, "never Clank's own service through the proxy"
        assert "private" in body.decode()
        assert {(line["status"], line["why"]) for line in logged(served, 10)} == {(403, "private")}
    finally:
        served.close()


def test_dev_mode_turned_on_or_off_applies_from_the_next_connection_with_nothing_restarted(tmp_path: Path) -> None:
    dev = [False]

    async def ask(workspace: str, host: str) -> str:
        return "no"

    served = Served(tmp_path / "network", ask=ask, dev_mode=lambda: dev[0])
    try:
        assert get(served, "http://docs.test/1", auth("other", "tok-other"))[0] == 403, "off: asked, and refused"
        dev[0] = True
        assert get(served, "http://docs.test/2", auth("other", "tok-other")) == (200, b"page /2")
        dev[0] = False
        assert get(served, "http://docs.test/3", auth("other", "tok-other"))[0] == 403, "off again: the allowances"
        assert get(served, "http://docs.test/4", auth("paper", "tok-paper")) == (200, b"page /4"), "allowed, as always"
        whys = [(line["path"], line.get("why")) for line in logged(served, 4)]
        assert whys == [("/1", "asked: no"), ("/2", "dev mode"), ("/3", "asked: no"), ("/4", None)]
    finally:
        served.close()


def test_a_connection_held_while_the_owner_is_asked_goes_out_at_once_when_dev_mode_is_turned_on(tmp_path: Path) -> None:
    dev = [False]
    asked = threading.Event()

    async def ask(workspace: str, host: str) -> str:
        asked.set()
        await asyncio.sleep(60)  # nobody answers: the owner is in OpenCode's window
        return "no"

    served = Served(tmp_path / "network", ask=ask, dev_mode=lambda: dev[0])
    try:
        answered: dict[str, tuple[int, bytes]] = {}
        held = threading.Thread(
            target=lambda: answered.update(got=get(served, "http://docs.test/held", auth("other", "tok-other")))
        )
        held.start()
        assert asked.wait(10), "the host was asked for, the connection held"
        began = time.monotonic()
        dev[0] = True
        held.join(10)
        assert answered["got"] == (200, b"page /held")
        assert time.monotonic() - began < 5, "at once, not after the minute's hold"
        [line] = logged(served, 1)
        assert line["why"] == "dev mode"
    finally:
        served.close()


def test_the_routes_carry_dev_mode_for_the_proxy() -> None:
    routes = Routes()
    assert routes.dev_mode() is False, "until the service says otherwise"
    routes.update({"slots": {}, "roles": {}, "dev_mode": True})
    assert routes.dev_mode() is True
    routes.update({"slots": {}, "roles": {}})
    assert routes.dev_mode() is False, "routes that do not say it (a service from before it) keep it off"


@pytest.mark.anyio
async def test_the_proxy_the_gateways_process_makes_follows_dev_mode_as_the_routes_carry_it() -> None:
    routes = Routes()
    proxy = agent_proxy(routes, "local-secret", None, None)
    with pytest.raises(Refused) as refused:
        await proxy._admitted("paper", "93.184.215.14", 443)
    assert refused.value.status == 403
    routes.update({"slots": {}, "roles": {}, "dev_mode": True})
    assert await proxy._admitted("paper", "93.184.215.14", 443) == (("93.184.215.14", 443), "dev mode")
    with pytest.raises(Refused) as refused:
        await proxy._admitted("paper", "10.1.2.3", 443)
    assert refused.value.why == "private"


def test_the_services_routes_say_dev_mode_as_the_runtime_has_it(rig: Rig) -> None:
    gateway: Gateway = rig.kernel.parts["gateway"]
    assert gateway.routes()["dev_mode"] is False
    rig.runtime.endpoints.set_dev(True, actor=YOU)
    assert gateway.routes()["dev_mode"] is True, "the gateway reads it with the next routes, every second"
    rig.runtime.endpoints.set_dev(False, actor=YOU)
    assert gateway.routes()["dev_mode"] is False
