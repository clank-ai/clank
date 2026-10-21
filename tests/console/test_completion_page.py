"""Design 0006 §6 (the Completion page, 2026-10-15): F8 says whether completion is served (the fast slot, and while it
does not run, what loading it needs on its host: the engine installed, the model's file downloaded), how fast the
gateway's last completions were answered, and the settings. `l` installs the engine and downloads the model when they
are missing, then loads the preset, each an operation followed to its end, without a second question; `x` turns
completion off or on in VS Code (the `completion` settings, which the service's routes read and change)."""

import json
import threading
from collections.abc import Iterator
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from clank.client import Client, ClientError
from clank.components.gateway.service import Gateway
from clank.components.runtime.state import InstallRecord
from clank.console.app import ClankConsole
from clank.console.rows import Rows
from clank.console.snapshot import render_text
from clank.kernel.core import Kernel
from tests.console.frames import settle
from tests.support.served import free_port

pytestmark = pytest.mark.anyio
NOW = datetime(2026, 10, 15, 13, 0, tzinfo=UTC)
COUNTS = {
    "count": 3, "broken_off": 1, "failed": 0, "refused": 0, "last_minute": 3, "last_hour": 3, "median_ms": 310.0,
    "p95_ms": 880.0, "recent": [
        {"time": "2026-10-15T12:59:58Z", "role": "completion", "outcome": "answered", "total_ms": 280.4,
         "prompt_n": 512, "predicted_n": 9},
        {"time": "2026-10-15T12:59:57Z", "role": "completion", "outcome": "broken off", "total_ms": 90.0},
    ],
}  # fmt: skip


class Counted(BaseHTTPRequestHandler):
    """The gateway's `GET /completion`, answered with fixed counts."""

    def do_GET(self) -> None:
        data = json.dumps(COUNTS).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        """Quiet."""


@pytest.fixture
def gateway(monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    """A gateway that runs, on a port of the test's own (never the real one's), counting its completions."""
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Counted)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    running = {"state": "running", "port": port, "url": f"http://127.0.0.1:{port}/v1", "pid": 7, "since": None,
               "problem": "", "log": ""}  # fmt: skip
    monkeypatch.setattr(Gateway, "status", lambda self: dict(running))
    yield port
    server.shutdown()
    server.server_close()


class Operations:
    """The console's client, but an install, a download or a load is only recorded, and answered as an operation that
    ends done at once (nothing is installed, downloaded or started)."""

    def __init__(self, client: Client) -> None:
        self.client = client
        self.posted: list[tuple[str, Any]] = []

    def post(self, path: str, body: Any = None) -> Any:
        if path in ("runtime/installs", "runtime/downloads", "runtime/slots/fast/load"):
            self.posted.append((path, body))
            return {"id": f"op-made-up{len(self.posted)}", "status": "running"}
        return self.client.post(path, body)

    def get(self, path: str, **params: Any) -> Any:
        if path.startswith("records/operation/op-made-up"):
            return {"values": {"status": "done"}}
        return self.client.get(path, **params)

    def __getattr__(self, name: str) -> Any:
        return getattr(self.client, name)


def text(app: ClankConsole) -> str:
    """The page's rows, a line each, the name padded to its column; then the keys bar."""
    page = app.query_one("#page-completion")
    lines = []
    for rows in page.query(Rows).results(Rows):
        for row in rows.query(".row"):
            labels = [str(label.content) for label in row.query("Label")]  # type: ignore[attr-defined]
            if len(labels) == 2:
                lines.append(f"{labels[0]:<{rows.width}}{labels[1]}")
    return "\n".join([*lines, render_text(app).splitlines()[-1]])


def installed_reader(kernel: Kernel) -> None:
    """KVMem on the local host, so a GGUF model's host is the local one."""
    record = InstallRecord(setup="kvmem-llamacpp", version="v0.16.0-rc1", host="local", program=["kvmem"],
                           folder="/kvmem", how="test")  # fmt: skip
    kernel.parts["runtime"].state.add_install(record, NOW)


async def test_f8_says_what_serving_completion_needs_how_fast_it_answers_and_l_gets_it_all_done(
    kernel: Kernel, client: Client, gateway: int
) -> None:
    installed_reader(kernel)
    operations = Operations(client)
    app = ClankConsole(operations, now=lambda: NOW, zone=UTC, home=kernel.home, page="completion")  # type: ignore[arg-type]
    async with app.run_test(size=(200, 50)) as pilot:
        await settle(pilot, lambda: "not downloaded" in text(app))
        shown = text(app)
        assert "Fast slot    ✗ stopped (never started): l loads it" in shown
        assert "Engine       ✗ llama.cpp b11588 not installed on local: l installs it (on the CPU)" in shown
        assert "Model        ✗ Qwen2.5-Coder 0.5B (506 MB) not downloaded to local: l downloads it" in shown
        assert "In VS Code   ✓ on: gray text after the cursor as you type; Tab takes it (x: off)" in shown
        assert "Answered in  median 310 ms · 95% under 880 ms" in shown
        assert "Not answered 1 broken off by a newer keystroke · 0 failed · 0 refused" in shown
        assert "answered 280 ms · read 512 tokens · wrote 9" in shown
        assert "Wait         120 ms after you stop typing, before it asks" in shown
        assert " l loads  u unloads  x turns it off or on in VS Code  v vision's mode" in shown
        await pilot.press("l")
        await settle(pilot, lambda: "completion is served" in str(app.query_one("#message").content))  # type: ignore[attr-defined]
    assert operations.posted == [
        ("runtime/installs", {"setup": "llamacpp", "version": "b11588", "host": "local", "yes": True}),
        (
            "runtime/downloads",
            {"model": "qwen2.5-coder-0.5b", "format": "gguf", "role": "weights", "host": "local", "yes": True},
        ),
        ("runtime/slots/fast/load", {"preset": "completion-0.5b"}),
    ]


async def test_x_turns_completion_off_and_on_for_vs_code(kernel: Kernel, client: Client, gateway: int) -> None:
    app = ClankConsole(client, now=lambda: NOW, zone=UTC, home=kernel.home, page="completion")
    async with app.run_test(size=(200, 50)) as pilot:
        await settle(pilot, lambda: "(x: off)" in text(app))
        await pilot.press("x")
        await settle(pilot, lambda: "In VS Code   ✗ off: nothing is asked (x: on)" in text(app))
    assert kernel.parts["gateway"].completion_settings().enabled is False
    settings = client.post("gateway/completion", {"enabled": True, "delay_ms": 200})["settings"]
    assert (settings["enabled"], settings["delay_ms"], settings["lines"]) == (True, 200, "few")
    with pytest.raises(ClientError, match="not what this route takes"):
        client.post("gateway/completion", {"delay_ms": 5000})


async def test_the_vision_section_says_its_mode_v_switches_it_and_g_gets_its_files(
    kernel: Kernel, client: Client, gateway: int
) -> None:
    """Design 0008 §7: off, on demand (the default) or always; on demand, g gets the files and loads nothing."""
    installed_reader(kernel)
    operations = Operations(client)
    app = ClankConsole(operations, now=lambda: NOW, zone=UTC, home=kernel.home, page="completion")  # type: ignore[arg-type]
    async with app.run_test(size=(200, 60)) as pilot:
        await settle(pilot, lambda: "g downloads them" in text(app))
        shown = text(app)
        assert "Mode         on demand: loaded when an image is to be read, unloaded after 10 minutes" in shown
        assert "Files        ✗ Qwen3-VL 4B (2.7 GB) not downloaded to local: g downloads them" in shown
        await pilot.press("g")
        await settle(pilot, lambda: "ready to load when an image is read" in str(app.query_one("#message").content))  # type: ignore[attr-defined]
        await pilot.press("v")
        await settle(pilot, lambda: "Mode         always: loaded and kept" in text(app))
    assert [path for path, _ in operations.posted] == ["runtime/installs", "runtime/downloads", "runtime/downloads"]
    assert [body["role"] for path, body in operations.posted[1:]] == ["weights", "projector"]
    assert kernel.parts["gateway"].vision_settings().mode == "always"
