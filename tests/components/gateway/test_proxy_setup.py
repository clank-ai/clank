"""Design 0004 §10 and design 0024 §2 (decision 0169): a workspace's setup goes out through the proxy under an
identity of its own, `<workspace>.setup`, with a token of its own: it reaches the hosts the routes carry for it (the set
`setup`, the package indexes, while it runs) and nothing else. A host not among them is refused in words that name the
set, never asked for, and dev mode does not lift that; a private address stays refused; the workspace's own token is
not the setup's. Each exchange is logged under the setup's identity, and the log of a workspace shows its setup's
exchanges with its agent's."""

import threading
from pathlib import Path
from typing import Any

import pytest

from clank.components.gateway.proxy import NetworkLog, setup_identity, setup_of
from tests.components.gateway import test_proxy
from tests.components.gateway.test_proxy import Served, auth, connect, get


def logged(served: Served, count: int) -> list[dict[str, Any]]:
    """The network log's lines once there are `count`."""
    for _ in range(200):
        if len(served.lines()) >= count:
            break
        threading.Event().wait(0.05)
    return served.lines()


def test_a_setups_identity_is_its_workspaces_name_with_setup_after_it() -> None:
    assert setup_identity("paper") == "paper.setup"
    assert setup_of("paper.setup") == "paper"
    assert setup_of("paper") is None, "a workspace's own agent"
    assert setup_of(".setup") is None


def test_a_setup_reaches_its_hosts_and_nothing_else_never_asked_and_not_in_dev_mode_either(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setitem(test_proxy.HOSTS, "paper.setup", ["docs.test", "localhost"])
    monkeypatch.setitem(test_proxy.TOKENS, "paper.setup", "tok-setup")
    asked: list[tuple[str, str]] = []

    async def ask(workspace: str, host: str) -> str:
        asked.append((workspace, host))
        return "always"

    served = Served(tmp_path / "network", ask=ask, dev_mode=lambda: True)
    try:
        setup = auth("paper.setup", "tok-setup")
        assert get(served, "http://docs.test/simple/numpy/", setup) == (200, b"page /simple/numpy/")
        status, body = get(served, "http://www.example.test/", setup)
        assert status == 403, "dev mode lets the agent out, not a setup"
        words = body.decode()
        assert "www.example.test is not among the hosts paper's setup reaches" in words
        assert "the set setup in config/network-sets.json" in words
        status, body, _ = connect(served, "echo.test:443", setup)
        assert status == 403
        assert "echo.test is not among the hosts paper's setup reaches" in body.decode()
        status, body = get(served, "http://localhost/", setup)
        assert status == 403, "a private address, whatever the set says"
        assert "private address" in body.decode()
        status, _, _ = connect(served, "docs.test:443", auth("paper.setup", "tok-paper"))
        assert status == 407, "the workspace's own token is not its setup's"
        assert asked == [], "a setup's host is never asked for: nobody waits at a setup"
        lines = logged(served, 4)
        assert [(line["workspace"], line["host"], line["status"], line.get("why")) for line in lines] == [
            ("paper.setup", "docs.test", 200, None), ("paper.setup", "www.example.test", 403, "not allowed"),
            ("paper.setup", "echo.test", 403, "not allowed"), ("paper.setup", "localhost", 403, "private"),
        ]  # fmt: skip
    finally:
        served.close()


def test_a_setup_the_routes_do_not_carry_reaches_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Its identity is carried only while it runs: before and after, nothing is allowed it."""
    monkeypatch.setitem(test_proxy.TOKENS, "paper.setup", "tok-setup")
    served = Served(tmp_path / "network")
    try:
        status, body = get(served, "http://docs.test/", auth("paper.setup", "tok-setup"))
        assert status == 403
        assert "docs.test is not among the hosts paper's setup reaches" in body.decode()
    finally:
        served.close()


def test_a_workspaces_log_shows_its_setups_exchanges_with_its_agents(tmp_path: Path) -> None:
    log = NetworkLog(tmp_path / "network")
    for workspace, host in (("paper", "docs.test"), ("paper.setup", "pypi.org"), ("other", "nope.test")):
        log.write({"workspace": workspace, "host": host, "port": 443, "method": "CONNECT", "status": 200})
    assert [line["host"] for line in log.recent(10, workspace="paper")] == ["pypi.org", "docs.test"]
    assert [line["host"] for line in log.recent(10, workspace="other")] == ["nope.test"]
