"""Design 0004 §3: the edge's program forwards one port to one target and nothing else: a request sent whole through it
gets its answer back (the target still writes after the request side is done), a streamed answer comes piece by
piece, and a connection the target refuses is closed at once. Design 0024 §2: several ports, each to its own target
(the gateway's and the proxy's). Design 0014 §3: a target is a host and its port, or a Unix socket (on Docker Engine,
the gateway's and the proxy's, on Linux only here). It runs as the program it is in the image (the same file), here on
this machine."""

import importlib.util
import socket
import socketserver
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from clank.components.workspaces.sandbox import image_folder
from tests.support.served import free_port


class Answer(BaseHTTPRequestHandler):
    """A target that answers with what it was asked, in three pieces."""

    protocol_version = "HTTP/1.0"

    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200)
        self.end_headers()
        for piece in (b"got:", body, b":done"):
            self.wfile.write(piece)
            self.wfile.flush()
            time.sleep(0.05)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture
def target() -> Iterator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Answer)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_port
    server.shutdown()
    server.server_close()


def edge(listen: int, target: int) -> subprocess.Popen[bytes]:
    program = str(image_folder() / "edge.py")
    process = subprocess.Popen(
        [sys.executable, "-B", program, str(listen), "127.0.0.1", str(target)], stdout=subprocess.PIPE
    )
    assert process.stdout is not None
    assert process.stdout.readline().startswith(b"edge: port"), "it says what it forwards once it listens"
    return process


def ask(port: int, body: bytes) -> bytes:
    with socket.create_connection(("127.0.0.1", port), timeout=10) as connection:
        connection.sendall(b"POST / HTTP/1.0\r\nContent-Length: %d\r\n\r\n%s" % (len(body), body))
        connection.shutdown(socket.SHUT_WR)
        received = b""
        while piece := connection.recv(65536):
            received += piece
    return received


def test_a_request_through_the_edge_gets_its_whole_answer(target: int) -> None:
    listen = free_port()
    process = edge(listen, target)
    try:
        answer = ask(listen, b"hello")
        assert answer.startswith(b"HTTP/1.0 200")
        assert answer.endswith(b"got:hello:done")
        large = bytes(range(256)) * 4096
        assert ask(listen, large).endswith(b"got:" + large + b":done")
    finally:
        process.kill()
        process.wait(30)
        assert process.stdout is not None
        process.stdout.close()


def test_a_connection_the_target_refuses_is_closed_at_once() -> None:
    listen, nobody = free_port(), free_port()
    process = edge(listen, nobody)
    try:
        started = time.monotonic()
        assert ask(listen, b"hello") == b""
        assert time.monotonic() - started < 5
    finally:
        process.kill()
        process.wait(30)
        assert process.stdout is not None
        process.stdout.close()


def test_the_edge_forwards_several_ports_each_to_its_own_target(target: int) -> None:
    second = ThreadingHTTPServer(("127.0.0.1", 0), Answer)
    threading.Thread(target=second.serve_forever, daemon=True).start()
    first_listen, second_listen = free_port(), free_port()
    program = str(image_folder() / "edge.py")
    process = subprocess.Popen(
        [sys.executable, "-B", program, str(first_listen), "127.0.0.1", str(target), str(second_listen), "127.0.0.1",
         str(second.server_port)], stdout=subprocess.PIPE,
    )  # fmt: skip
    try:
        assert process.stdout is not None
        said = {process.stdout.readline().strip() for _ in range(2)}
        assert said == {
            f"edge: port {first_listen} goes to 127.0.0.1:{target}".encode(),
            f"edge: port {second_listen} goes to 127.0.0.1:{second.server_port}".encode(),
        }, "it says each pair once it listens"
        assert ask(first_listen, b"one").endswith(b"got:one:done")
        assert ask(second_listen, b"two").endswith(b"got:two:done")
    finally:
        process.kill()
        process.wait(30)
        assert process.stdout is not None
        process.stdout.close()
        second.shutdown()
        second.server_close()


def test_the_edge_reads_each_target_as_a_host_and_its_port_or_a_unix_socket() -> None:
    """Design 0014 §3: `LISTEN_PORT HOST PORT` (Docker Desktop's, as before) and `LISTEN_PORT unix:PATH` (Docker
    Engine's: the gateway's socket and the proxy's), in any order; anything else is refused with how it is called."""
    spec = importlib.util.spec_from_file_location("clank_edge_under_test", image_folder() / "edge.py")
    assert spec is not None
    assert spec.loader is not None
    program = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(program)
    given = ["18210", "unix:/run/clank/gateway.sock", "18211", "host.docker.internal", "18211"]
    expected = [(18210, "unix:/run/clank/gateway.sock", 0), (18211, "host.docker.internal", 18211)]
    assert program.forwards(given) == expected
    for wrong in ([], ["18210"], ["18210", "unix:"], ["18210", "host"], ["port", "host", "1"], ["1", "host", "port"]):
        assert program.forwards(wrong) is None, wrong
    refused = subprocess.run(
        [sys.executable, "-B", str(image_folder() / "edge.py"), "18210", "unix:"], capture_output=True, text=True
    )
    assert refused.returncode == 2
    assert "LISTEN_PORT unix:SOCKET" in refused.stderr


@pytest.mark.skipif(sys.platform != "linux", reason="Unix sockets: Linux only (CI's ubuntu-24.04 runs it)")
def test_the_edge_forwards_to_a_unix_socket(short: Path) -> None:
    """Design 0014 §3: on Docker Engine the edge joins each connection to the gateway's socket, bytes both ways, as it
    joins one to a host's port."""
    if sys.platform == "win32":  # the type checker's: Unix sockets exist only off Windows
        return
    path = short / "gateway.sock"
    server = socketserver.ThreadingUnixStreamServer(str(path), Answer)  # the gateway's socket, as the edge finds it
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    listen = free_port()
    process = subprocess.Popen(
        [sys.executable, "-B", str(image_folder() / "edge.py"), str(listen), f"unix:{path}"], stdout=subprocess.PIPE
    )
    try:
        assert process.stdout is not None
        assert process.stdout.readline().strip() == f"edge: port {listen} goes to unix:{path}".encode()
        assert ask(listen, b"hello").endswith(b"got:hello:done")
        large = bytes(range(256)) * 4096
        assert ask(listen, large).endswith(b"got:" + large + b":done")
        server.shutdown()
        server.server_close()
        path.unlink()
        started = time.monotonic()
        assert ask(listen, b"hello") == b"", "the socket gone: the connection is closed at once"
        assert time.monotonic() - started < 5
    finally:
        process.kill()
        process.wait(30)
        assert process.stdout is not None
        process.stdout.close()
        server.server_close()
