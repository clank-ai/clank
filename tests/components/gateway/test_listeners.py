"""Design 0014 §3 (decision 0071, option (a)): on Linux the gateway also listens on a socket, `gateway.sock`, and the
proxy on `proxy.sock`, in a folder of their own outside CLANK_HOME (`~/.cache/clank/<home id>`, under `$XDG_CACHE_HOME`
when that names a folder, or where `socket_folder` says): the folder the owner's alone (0700), each socket set to 0600
before it listens, the process's umask never changed. The folder is never the home folder itself, nor inside or holding
CLANK_HOME or the folder Clank runs from, and a socket's path is never longer than Linux holds. The gateway makes its
listeners itself: its TCP socket on 127.0.0.1 only, its address reused so a restart finds the port free, and a port
another program holds ends it as before (logged, exit status 3); a socket a gateway left behind is replaced, any other
file left as it is, saying why; no other address listens, and a request on the socket, which has no client address, is
answered as any other. The gateway removes its sockets when it stops. No test makes a socket folder in the real home
folder. The tests with sockets run on Linux only (CI's ubuntu-24.04)."""

import contextlib
import json
import logging
import os
import socket
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psutil
import pytest
import uvicorn

from clank.components.gateway import sockets
from clank.components.gateway.kinds import GatewaySettings
from clank.components.gateway.records import TrafficLog
from clank.components.gateway.routing import Routes
from clank.components.gateway.server import create_gateway
from clank.components.gateway.sockets import (
    PATH_MOST,
    SocketFolderError,
    checked_socket_folder,
    default_folder,
    prepare_folder,
    remove_sockets,
    socket_folder,
    tcp_listener,
)
from clank.kernel.home import Home
from clank.kernel.service import server_config
from tests.support.served import free_port

LINUX_ONLY = pytest.mark.skipif(sys.platform != "linux", reason="Unix sockets: Linux only (CI's ubuntu-24.04 runs it)")
ASKED = {"model": "agent", "messages": [{"role": "user", "content": "Hi"}], "max_tokens": 3}


def mode(path: Path) -> int:
    return stat.S_IMODE(os.lstat(path).st_mode)


def ask(path: Path, port: int, line: str = "GET /health", body: bytes = b"") -> tuple[int, bytes]:
    """A request sent on a socket as the edge relays one (its Host `edge:<port>`): its status and its body."""
    if sys.platform == "win32":  # the type checker's: Unix sockets exist only off Windows
        raise AssertionError("Unix sockets: Linux only")
    head = f"{line} HTTP/1.1\r\nHost: edge:{port}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(30)
        connection.connect(str(path))
        connection.sendall(f"{head}Connection: close\r\n\r\n".encode() + body)
        received = b""
        while piece := connection.recv(65536):
            received += piece
    status, _, rest = received.partition(b"\r\n\r\n")
    return int(status.split()[1]), rest


def test_the_socket_folder_is_never_the_home_folder_nor_inside_or_holding_clank_home_or_the_folder_clank_runs_from(
    short: Path,
) -> None:
    user = short / "home" / "someone"
    clank_home, runs_from = user / ".clank", short / "opt" / "clank"
    for folder in (clank_home, clank_home / "sockets", runs_from, runs_from / "sockets"):
        folder.mkdir(parents=True, exist_ok=True)
    good = user / ".cache" / "clank" / "0123456789ab"
    assert checked_socket_folder(good, clank_home, runs_from, user) == good.resolve(), "it need not be there yet"
    refused = {
        user: "is your home folder itself",
        clank_home: "holds Clank's own folder, CLANK_HOME",
        clank_home / "sockets": "is inside Clank's own folder, CLANK_HOME",
        short / "home": "holds Clank's own folder, CLANK_HOME",
        runs_from: "holds the folder Clank runs from",
        runs_from / "sockets": "is inside the folder Clank runs from",
        short / "opt": "holds the folder Clank runs from",
    }
    for folder, why in refused.items():
        with pytest.raises(SocketFolderError, match=why) as refusal:
            checked_socket_folder(folder, clank_home, runs_from, user)
        assert "socket_folder in config/gateway.json" in str(refusal.value), "it says what to do"
    with pytest.raises(SocketFolderError, match="not a full path"):
        checked_socket_folder(Path("relative", "sockets"), clank_home, runs_from, user)


def test_a_socket_path_too_long_for_linux_is_refused_saying_so(short: Path) -> None:
    base = short.resolve()
    room = PATH_MOST - len(os.fsencode(str(base / "gateway.sock"))) - 1  # the folder's name, and a separator
    fits = base / ("f" * room)
    assert len(os.fsencode(str(fits / "gateway.sock"))) == PATH_MOST
    assert checked_socket_folder(fits, base / "clank-home", base / "clank", base / "me") == fits
    with pytest.raises(SocketFolderError, match=f"{PATH_MOST + 1} bytes long.*{PATH_MOST} bytes at most"):
        checked_socket_folder(base / ("f" * (room + 1)), base / "clank-home", base / "clank", base / "me")


def test_the_socket_folder_is_the_cache_folders_own_for_its_home_unless_the_settings_name_one(tmp_path: Path) -> None:
    me = tmp_path / "me"
    cache = tmp_path / "cache"
    assert default_folder("0123456789ab", {}, me) == me / ".cache" / "clank" / "0123456789ab"
    assert default_folder("0123456789ab", {"XDG_CACHE_HOME": str(cache)}, me) == cache / "clank" / "0123456789ab"
    relative = {"XDG_CACHE_HOME": "cache"}  # not a folder from the root: ignored, as the XDG rules say
    assert default_folder("0123456789ab", relative, me) == me / ".cache" / "clank" / "0123456789ab"
    named = tmp_path / "sockets"
    assert socket_folder(f"  {named}  ", "0123456789ab", {"XDG_CACHE_HOME": str(cache)}, me) == named
    assert socket_folder("~/sockets", "0123456789ab", {}, me) == Path.home() / "sockets"
    assert socket_folder("", "0123456789ab", {}, me) == me / ".cache" / "clank" / "0123456789ab"


def test_no_test_makes_a_socket_folder_in_the_real_home_folder() -> None:
    """The session's XDG_CACHE_HOME (tests/conftest.py): every socket folder a test makes by default is under it."""
    cache = Path(os.environ["XDG_CACHE_HOME"])
    assert cache.name.startswith("clank-tests-cache-"), "the session's own"
    assert not cache.resolve().is_relative_to((Path.home() / ".cache").resolve())
    assert default_folder(Home.resolve().id).is_relative_to(cache)
    assert len(os.fsencode(str(default_folder("0123456789ab") / "gateway.sock"))) <= PATH_MOST


@LINUX_ONLY
def test_on_linux_the_gateway_also_listens_where_only_the_edge_reaches_it(home: Home, short: Path) -> None:
    port, proxy_port = free_port(), free_port()
    settings = {"schema": "gateway/1", "port": port, "proxy_port": proxy_port}
    (home.config / "gateway.json").write_text(json.dumps(settings) + "\n", encoding="utf-8")
    folder = short / "clank" / home.id
    log = home.logs / "gateway.log"
    with log.open("wb") as output:
        gateway = subprocess.Popen(
            [sys.executable, "-m", "clank.components.gateway.server", "--port", str(port), "--socket-folder",
             str(folder)],
            stdout=output, stderr=subprocess.STDOUT, env={**os.environ, "CLANK_HOME": str(home.root)},
        )  # fmt: skip
    try:
        deadline = time.monotonic() + 30
        while not (folder / "proxy.sock").exists() or not (folder / "gateway.sock").exists():
            assert gateway.poll() is None, log.read_text(encoding="utf-8", errors="replace")
            assert time.monotonic() < deadline, "the gateway never made its sockets"
            time.sleep(0.05)
        while True:
            with contextlib.suppress(OSError):
                status, body = ask(folder / "gateway.sock", port)
                break
            assert time.monotonic() < deadline, "the gateway never answered on its socket"
            time.sleep(0.05)
        assert (status, json.loads(body)) == (200, {"status": "ok"})
        assert (mode(folder), mode(folder / "gateway.sock"), mode(folder / "proxy.sock")) == (0o700, 0o600, 0o600)
        assert not folder.resolve().is_relative_to(home.root.resolve()), "outside CLANK_HOME"
        listening = {
            (each.laddr.ip, each.laddr.port)
            for each in psutil.Process(gateway.pid).net_connections(kind="inet")
            if each.status == psutil.CONN_LISTEN
        }
        assert listening == {("127.0.0.1", port), ("127.0.0.1", proxy_port)}, "no other address listens"
    finally:
        gateway.terminate()
        gateway.wait(30)
    assert not (folder / "gateway.sock").exists(), "it removes its sockets when it stops"
    assert not (folder / "proxy.sock").exists()
    assert folder.is_dir(), "the folder stays"


@LINUX_ONLY
def test_the_socket_is_set_to_0600_before_it_listens_and_the_umask_is_never_changed(
    short: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if sys.platform == "win32":  # the type checker's: Unix sockets exist only off Windows
        return
    seen: list[tuple[str, int]] = []

    class Watched(socket.socket):
        """A socket that notes the mode of its path when it starts listening."""

        def listen(self, backlog: int = 5, /) -> None:
            if self.family == socket.AF_UNIX:
                path = Path(self.getsockname())
                seen.append((path.name, mode(path)))
            super().listen(backlog)

    def refused(mask: int) -> int:
        raise AssertionError("the umask is the whole process's: never changed")

    before = os.umask(0o022)
    os.umask(before)
    monkeypatch.setattr(socket, "socket", Watched)
    monkeypatch.setattr(os, "umask", refused)
    made = sockets.listeners(free_port(), short / "sockets")
    try:
        assert seen == [("gateway.sock", 0o600), ("proxy.sock", 0o600)]
        assert mode(short / "sockets") == 0o700
    finally:
        for each in (made.tcp, made.gateway, made.proxy):
            if each is not None:
                each.close()
        remove_sockets(made.made)
    monkeypatch.undo()
    after = os.umask(before)
    os.umask(after)
    assert after == before


@LINUX_ONLY
def test_on_linux_the_gateways_port_is_bound_for_reuse_so_a_restart_finds_it_free() -> None:
    port = free_port()
    listener = tcp_listener(port)
    assert listener.getsockname() == ("127.0.0.1", port), "127.0.0.1 only"
    assert listener.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) != 0
    client = socket.create_connection(("127.0.0.1", port), timeout=10)
    accepted, _ = listener.accept()
    accepted.close()  # the gateway's side closes first, and its connection waits out TIME_WAIT
    client.close()
    listener.close()
    again = tcp_listener(port)  # a gateway started again at once
    again.close()


@LINUX_ONLY
def test_a_port_another_program_holds_ends_the_gateway_as_before_saying_so(home: Home, short: Path) -> None:
    with socket.socket() as holder:
        holder.bind(("127.0.0.1", 0))
        holder.listen()
        port = holder.getsockname()[1]
        ended = subprocess.run(
            [sys.executable, "-m", "clank.components.gateway.server", "--port", str(port), "--socket-folder",
             str(short / "sockets")],
            capture_output=True, text=True, timeout=60, env={**os.environ, "CLANK_HOME": str(home.root)},
        )  # fmt: skip
    assert ended.returncode == 3, "Uvicorn's exit status when it cannot bind"
    assert f"error while attempting to bind on address ('127.0.0.1', {port})" in ended.stderr, ended.stderr
    assert not (short / "sockets").exists(), "nothing more is made"


@LINUX_ONLY
def test_a_stale_socket_is_replaced_and_any_other_file_is_left_saying_why(
    short: Path, caplog: pytest.LogCaptureFixture
) -> None:
    if sys.platform == "win32":  # the type checker's: Unix sockets exist only off Windows
        return
    left = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    left.bind(str(short / "gateway.sock"))  # a gateway that ended without removing it: nothing answers there
    left.close()
    (short / "proxy.sock").write_text("the owner's\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="clank.components.gateway.sockets"):
        made = sockets.listeners(free_port(), short)
    try:
        assert made.gateway is not None, "the socket left behind is replaced"
        assert made.proxy is None
        assert (short / "proxy.sock").read_text(encoding="utf-8") == "the owner's\n", "any other file is left"
        assert "proxy.sock is there and is not a socket" in caplog.text
    finally:
        for each in (made.tcp, made.gateway):
            if each is not None:
                each.close()
        remove_sockets(made.made)
    assert not (short / "gateway.sock").exists(), "its own socket removed"
    assert (short / "proxy.sock").exists(), "the other file left"


@contextlib.contextmanager
def serving_on(path: Path, settings: GatewaySettings, tmp_path: Path) -> Iterator[None]:
    """The gateway's application served on a socket at `path` only, as the gateway's process serves it on Linux."""
    if sys.platform == "win32":  # the type checker's: Unix sockets exist only off Windows
        raise AssertionError("Unix sockets: Linux only")
    app = create_gateway(Routes(), settings, TrafficLog(tmp_path / "traffic", 256, 14), token="t", port=settings.port)
    listener = sockets.unix_listener(path)
    server = uvicorn.Server(server_config(app, "127.0.0.1", settings.port))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "the gateway never started"
        time.sleep(0.01)
    try:
        yield
    finally:
        server.should_exit = True
        thread.join(15)
        path.unlink(missing_ok=True)


@LINUX_ONLY
def test_a_request_on_the_socket_has_no_client_address_and_is_answered_as_any_other(
    short: Path, tmp_path: Path
) -> None:
    settings = GatewaySettings(port=free_port(), hold_seconds=0)
    path = short / "gateway.sock"
    with serving_on(path, settings, tmp_path):
        status, body = ask(path, settings.port, "POST /v1/chat/completions", json.dumps(ASKED).encode())
        refused, _ = ask(path, settings.port, "GET /activity")
    assert status == 503, body
    assert json.loads(body)["error"]["code"] == "no_engine", "refused for want of an engine, as on 127.0.0.1"
    assert refused == 401, "the owner's routes still want the service's token: a caller on the socket is the edge's"
    records: list[dict[str, Any]] = [
        json.loads(line)
        for file in sorted((tmp_path / "traffic").glob("*.jsonl"))
        for line in file.read_text(encoding="utf-8").splitlines()
    ]
    assert [(each["client"], each["status"]) for each in records] == [("", 503)], "no client address, and recorded"


def test_a_socket_folder_that_cannot_be_made_the_owners_alone_is_refused_saying_why(
    short: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Said as such, never taken for a port another program holds: the gateway then listens on no socket."""
    folder = short / "sockets"
    folder.mkdir()
    os.chmod(folder, 0o755)

    def refused(path: object, mode: int) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "chmod", refused)
    with pytest.raises(SocketFolderError, match=r"could not be made the owner's alone: .*Operation not permitted"):
        prepare_folder(folder)
