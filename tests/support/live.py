"""Test support: the API of a kernel built in the test, served by Uvicorn on a free port in a thread of the test, so a
client (the console, the follower) uses real HTTP and the real event stream while the test reaches into the kernel
(a fake clock, a fake container platform). The server is the service's own (`ApiServer`)."""

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

from clank.client import Client
from clank.kernel.api import create_app
from clank.kernel.core import Kernel
from clank.kernel.service import ApiServer
from tests.support.served import free_port


@contextmanager
def live_service(kernel: Kernel, port: int | None = None, token: str = "t", name: str = "console") -> Iterator[Client]:
    """The kernel's API, answering on 127.0.0.1 until the block ends; a client of it, naming itself `name`."""
    port = port or free_port()
    server = ApiServer(create_app(kernel, token=token, port=port), "127.0.0.1", port)
    thread = threading.Thread(target=server.run, name="live-service", daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            raise RuntimeError("the live service did not start")
        time.sleep(0.01)
    client = Client(f"http://127.0.0.1:{port}", token, name=name)
    try:
        yield client
    finally:
        client.close()
        server.should_exit = True
        thread.join(15)
