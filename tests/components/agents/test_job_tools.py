"""Design 0021 §6: Clank's own MCP server gives the agent `run_job(command, title, minutes)`, `job_status(job)` and
`job_stop(job)`: requests to the gateway's `/agents/jobs`, `/agents/jobs/status` and `/agents/jobs/stop` naming the
workspace the server serves. `run_job`'s description tells the model to start as a job any command expected to run
more than two minutes, and that it is told when the job ends; its answer is the service's words. `job_status` reads
only (the planner may use it): one job with its log's last lines and the files it wrote, or every job of the workspace
in a line each. A refusal is the tool's error in the service's words."""

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from tests.components.agents.test_flow_tools import called, session
from tests.support.served import free_port

STARTED = "job 3 (sweep) started in the container, at the lowest CPU priority; you are told when it ends"
ONE = {
    "workspace": "myproject", "job": 3, "title": "sweep", "command": "python sweep.py", "minutes": 120,
    "state": "ended", "status": 0, "said": "exited 0", "seconds": 754, "folder": ".clank/jobs/agent/3",
    "tail": "seed 9: 0.412\nseed 10: 0.398", "written": ["results/sweep.csv"],
}  # fmt: skip
RUNNING = {**ONE, "job": 4, "title": "anneal", "state": "running", "status": None, "said": "", "seconds": 65}


class Gateway(BaseHTTPRequestHandler):
    """The gateway's job routes as the service answers them, and what was asked."""

    asked: ClassVar[list[tuple[str, Any]]] = []

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        Gateway.asked.append((self.path, body))
        if self.path == "/agents/jobs" and not body.get("command"):
            self._json({"error": {"code": "refused", "message": "a job needs a command"}}, 409)
        elif self.path == "/agents/jobs":
            self._json({"job": 3, "folder": ".clank/jobs/agent/3", "said": STARTED})
        elif self.path == "/agents/jobs/status":
            self._json(ONE if body.get("job") == 3 else {"jobs": [RUNNING, ONE]})
        else:
            self._json({**RUNNING, "said": "job 4 (anneal) is being stopped, with everything it started"})

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
    Gateway.asked = []
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Gateway)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/v1"
    server.shutdown()
    server.server_close()


def text(reply: dict[str, Any]) -> str:
    return str(reply["result"]["content"][0]["text"])


def test_the_job_tools_are_listed_and_run_job_says_when_to_use_it(tmp_path: Path, gateway: str) -> None:
    [listed] = session(tmp_path, gateway, [{"jsonrpc": "2.0", "id": 1, "method": "tools/list"}])
    tools = {tool["name"]: tool for tool in listed["result"]["tools"]}
    run = tools["run_job"]
    assert run["inputSchema"]["required"] == ["command", "title"]
    assert "more than two minutes" in run["description"]
    assert "told when it ends" in run["description"]
    assert tools["job_status"]["annotations"]["readOnlyHint"] is True, "the planner may follow jobs"
    assert tools["job_stop"]["annotations"]["readOnlyHint"] is False


def test_run_job_asks_the_gateway_naming_its_workspace_and_answers_the_services_words(
    tmp_path: Path, gateway: str
) -> None:
    arguments = {"command": "python sweep.py --seeds 10", "title": "sweep", "minutes": 120}
    [reply] = session(tmp_path, gateway, [called("run_job", arguments)])
    assert Gateway.asked == [("/agents/jobs", {"workspace": "myproject", **arguments})]
    assert text(reply) == STARTED
    [refused] = session(tmp_path, gateway, [called("run_job", {"command": "", "title": "nothing"})])
    assert refused["result"]["isError"] is True
    assert text(refused) == "a job needs a command"


def test_job_status_gives_one_job_whole_or_every_job_in_a_line(tmp_path: Path, gateway: str) -> None:
    [one, every] = session(tmp_path, gateway, [called("job_status", {"job": 3}), called("job_status", {}, id=2)])
    said = text(one)
    assert said.startswith("Job 3 (sweep): ended, exited 0, after 12 minutes.")
    assert "seed 10: 0.398" in said
    assert "results/sweep.csv" in said
    lines = text(every).splitlines()
    assert lines[0].startswith("Job 4 (anneal): running for 1 minute")
    assert lines[1].startswith("Job 3 (sweep): ended, exited 0")
    [stopped] = session(tmp_path, gateway, [called("job_stop", {"job": 4})])
    assert text(stopped) == "job 4 (anneal) is being stopped, with everything it started"
    assert Gateway.asked[-1] == ("/agents/jobs/stop", {"workspace": "myproject", "job": 4})
