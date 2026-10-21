"""Design 0008 §7: the agent's tool `look_at_figure` (Clank's own MCP server in the container) asks the vision model,
through the gateway's role `vision`, about a figure of the folder, and gives the figure's geometry beside the answer
(its plots, their axes and lines, as Matplotlib's save left them); when the vision model does not answer (vision is
off), the answer says why and the geometry is still given; a file that is not a PNG or a JPEG is refused."""

import json
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from clank.components.workspaces.sandbox import image_folder
from clank.kernel.processes import background_flags
from tests.components.workspaces.test_figure_geometry import run
from tests.support.served import free_port

SERVER = image_folder() / "phone_mcp.py"


class Gateway(BaseHTTPRequestHandler):
    """The gateway's chat completions as the vision model answers them (or refuses), and what was asked."""

    asked: ClassVar[list[dict[str, Any]]] = []
    refusal: ClassVar[str] = ""

    def do_POST(self) -> None:
        Gateway.asked.append(json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0))))
        if Gateway.refusal:
            self._json({"error": {"message": Gateway.refusal, "type": "no_engine"}}, 503)
        else:
            self._json({"choices": [{"message": {"role": "assistant", "content": "The red dot sits at (2.5, 3)."}}]})

    def log_message(self, format: str, *args: Any) -> None:
        """Quiet."""

    def _json(self, value: Any, status: int = 200) -> None:
        data = json.dumps(value).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture
def gateway() -> Iterator[str]:
    Gateway.asked, Gateway.refusal = [], ""
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Gateway)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/v1"
    server.shutdown()
    server.server_close()


def call(folder: Path, gateway: str, arguments: dict[str, str]) -> dict[str, Any]:
    """`look_at_figure` called once through the server's standard input; the call's result."""
    messages = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "look_at_figure", "arguments": arguments},
        },
    ]
    done = subprocess.run(
        [sys.executable, str(SERVER)], input="".join(json.dumps(message) + "\n" for message in messages),
        capture_output=True, text=True, timeout=120, creationflags=background_flags(),
        env={"CLANK_WORKSPACE": str(folder), "CLANK_GATEWAY": gateway, "SYSTEMROOT": "C:\\Windows", "PATH": ""},
    )  # fmt: skip
    replies = [json.loads(line) for line in done.stdout.splitlines()]
    result: dict[str, Any] = replies[-1]["result"]
    return result


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    folder = tmp_path / "paper"
    (folder / "figs").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    done = run(folder, str(tmp_path / "elsewhere"))
    assert done.returncode == 0, done.stderr
    return folder


def test_the_vision_model_answers_about_a_figure_with_its_geometry_beside(folder: Path, gateway: str) -> None:
    result = call(folder, gateway, {"path": "figs/plot.png", "question": "Where is the red dot?"})
    text = result["content"][0]["text"]
    assert result["isError"] is False
    assert text.startswith("The vision model on figs/plot.png: The red dot sits at (2.5, 3).")
    assert "Its geometry (from Matplotlib's save):" in text
    assert "- plot 1 'MSD vs time': x 'time'" in text
    assert "lines: n = 16, (unlabeled)" in text
    [asked] = Gateway.asked
    image, question = asked["messages"][0]["content"]
    assert (asked["model"], image["image_url"]["url"][:22]) == ("vision", "data:image/png;base64,")
    assert question["text"].startswith("Where is the red dot?")


def test_without_the_vision_model_the_geometry_is_still_given_and_a_non_image_is_refused(
    folder: Path, gateway: str
) -> None:
    Gateway.refusal = "the vision model is off: the console's F8 page turns it on (v)"
    text = call(folder, gateway, {"path": "figs/plot.png"})["content"][0]["text"]
    assert "(the vision model did not answer: the vision model is off" in text
    assert "- plot 2 'growth'" in text
    (folder / "notes.txt").write_text("not a figure\n", encoding="utf-8")
    refused = call(folder, gateway, {"path": "notes.txt"})
    assert refused["isError"] is True
    assert "is not a PNG or a JPEG" in refused["content"][0]["text"]
