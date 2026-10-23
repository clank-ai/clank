"""Design 0005 §2-§3: the session bridge and the agent's outbox, run on this machine against a fake OpenCode server.

The bridge (`/opt/clank/bridge.py` in the image, standard library only) finds the OpenCode servers on its ports and
lists their root sessions with their status, the permissions waiting (with their diff) and the questions; it gives a
session's last messages briefly (text, tools with title, state, input and output cut, reasoning only as its length);
it sends a message without waiting, starts a session, stops one, replies to a permission (once, always or reject, any
other refused) and a question, and finds a free port; an error is said in its JSON, never a traceback. The service's
`Sessions` drives it through `docker exec` and records each action (`agents.acted`) with who did it. The bridge also
gives the MCP servers of each running agent with their status, and starts (connects, or adds with its entry) or stops
one while the agent runs; the service's `live` says each server's state (running, stopped, failed; on or off when no
agent runs) and `switch` keeps the choice for the agent's next start and applies it at once.

`send_to_phone` (`/opt/clank/phone_mcp.py`, Clank's own MCP server) copies a file of the folder into `.clank/outbox/`
with its caption beside it and a `.gitignore` that keeps git out; a file outside the folder is refused.

Design 0013 §15: the bridge starts a planning session on a window still starting, waiting for its server, sends its
first message to the agent asked for (the planner), shows the session there, then again; a window that never answers is
said. It shows a session that runs already on a window still starting (`clank flow attach`), and again, starting
none."""

import importlib.util
import json
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from clank import registry
from clank.components.agents.sessions import SessionError
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import image_folder, names
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import Answer, background_flags
from tests.fakes.platform import FakePlatform, container
from tests.support.served import free_port

BRIDGE = image_folder() / "bridge.py"
PHONE = image_folder() / "phone_mcp.py"
PHONE_USER = Actor(kind="device", via="phone")
MESSAGES = [
    {"info": {"id": "m1", "role": "user", "time": {"created": 1}}, "parts": [{"type": "text", "text": "plot tau"}]},
    {"info": {"id": "m2", "role": "assistant", "time": {"created": 2, "completed": 3}}, "parts": [
        {"type": "reasoning", "text": "thinking it over"},
        {"type": "tool", "tool": "read", "state": {"status": "completed", "title": "Read a.py",
                                                   "input": {"filePath": "a.py"}, "output": "x" * 3000}},
        {"type": "text", "text": "Saved runs/tau.png", "synthetic": False},
        {"type": "step-finish"},
    ]},
]  # fmt: skip


class OpenCode(BaseHTTPRequestHandler):
    """The few routes of OpenCode's server the bridge uses, and what was sent to them."""

    sent: ClassVar[list[tuple[str, Any]]] = []
    mcp: ClassVar[dict[str, dict[str, str]]] = {}
    unshown: ClassVar[bool] = False  # its terminal interface refuses to show a session
    slow: ClassVar[float] = 0.0  # seconds it takes to answer a new session, as a window just started readies itself

    def do_GET(self) -> None:
        answers: dict[str, Any] = {
            "/session": [{"id": "ses_1", "title": "Plot tau", "time": {"created": 1, "updated": 2}},
                         {"id": "ses_9", "title": "a subagent", "parentID": "ses_1"}],
            "/session/status": {"ses_1": {"type": "busy"}},
            "/permission": [{"id": "per_1", "sessionID": "ses_1", "permission": "edit", "patterns": ["src/a.py"],
                             "metadata": {"diff": "--- a.py\n+++ a.py\n-old\n+new"}}],
            "/question": [{"id": "que_1", "sessionID": "ses_1",
                           "questions": [{"question": "Which graph?", "options": [{"label": "cycle"}]}]}],
            "/session/ses_1/message": MESSAGES,
            "/session/ses_2/message": MESSAGES[:1],
            "/mcp": OpenCode.mcp,
            "/agent": [{"name": "build", "mode": "primary"}, {"name": "explore", "mode": "subagent"},
                       {"name": "planner", "mode": "primary"}, {"name": "title", "mode": "primary", "hidden": True}],
        }  # fmt: skip
        path = self.path.split("?")[0]  # a page of messages asked for (`limit`) is all of them here
        self._json(answers.get(path, {"error": "no"}), 200 if path in answers else 404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"null")
        OpenCode.sent.append((self.path, body))
        if self.path == "/session":
            time.sleep(OpenCode.slow)
            self._json({"id": "ses_2"})
        elif self.path == "/mcp":
            OpenCode.mcp[body["name"]] = {"status": "connected"}
            self._json(OpenCode.mcp)
        elif self.path.startswith("/mcp/"):
            _, _, name, verb = self.path.split("/")
            OpenCode.mcp[name] = {"status": "connected" if verb == "connect" else "disabled"}
            self._json(True)
        elif self.path == "/session/ses_1/prompt_async":
            self.send_response(204)
            self.end_headers()
        elif self.path == "/tui/select-session" and OpenCode.unshown:
            self._json({"error": "no terminal interface heard it"}, 500)
        else:
            self._json(True)

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
def opencode() -> Iterator[int]:
    OpenCode.sent = []
    OpenCode.mcp = {"clank": {"status": "connected"}, "broken": {"status": "failed", "error": "it exited"}}
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), OpenCode)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield port
    server.shutdown()
    server.server_close()


def bridge(
    port: int, *argv: str, given: dict[str, Any] | None = None, ports: str = "", again: str = "", answer: str = ""
) -> dict[str, Any]:
    shown_again = {"CLANK_BRIDGE_SHOW_AGAIN": again} if again else {}
    answered = {"CLANK_BRIDGE_TIMEOUT": answer} if answer else {}  # how long a request waits for its answer
    done = subprocess.run(
        [sys.executable, str(BRIDGE), *argv], input=json.dumps(given) if given is not None else "",
        capture_output=True, text=True, timeout=60, creationflags=background_flags(),
        env={**__import__("os").environ, "CLANK_BRIDGE_PORTS": ports or f"{port}-{port}", **shown_again, **answered},
    )  # fmt: skip
    found: dict[str, Any] = json.loads(done.stdout)
    return found


def test_the_bridge_lists_each_servers_root_sessions_their_status_and_what_waits(opencode: int) -> None:
    found = bridge(opencode, "servers")
    assert found["ok"] is True
    [server] = found["servers"]
    assert (server["port"], server["terminal"]) == (opencode, False), "a test server is no window"
    assert server["sessions"] == [
        {"id": "ses_1", "title": "Plot tau", "parent": None, "created": 1, "updated": 2, "status": "busy"}
    ], "a subagent's session is not listed among the root sessions"
    assert server["children"] == [
        {"id": "ses_9", "title": "a subagent", "parent": "ses_1", "created": None, "updated": None, "status": "idle"}
    ], "but beside them (design 0012 §3)"
    assert server["permissions"][0]["metadata"]["diff"].endswith("+new")
    assert server["questions"][0]["questions"][0]["question"] == "Which graph?"


def test_the_bridge_gives_a_sessions_messages_briefly(opencode: int) -> None:
    found = bridge(opencode, "messages", str(opencode), "ses_1", "10")
    user, answer = found["messages"]
    assert user["parts"] == [{"type": "text", "text": "plot tau"}]
    reasoning, tool, text = answer["parts"]
    assert reasoning == {"type": "reasoning", "length": len("thinking it over")}
    assert (tool["tool"], tool["status"], tool["title"]) == ("read", "completed", "Read a.py")
    assert tool["output"].startswith("x" * 1500)
    assert tool["output"].endswith("[3,000 characters]")
    assert text == {"type": "text", "text": "Saved runs/tau.png"}
    assert found["count"] == 2


def test_the_bridge_sends_starts_stops_and_replies_and_says_why_it_cannot(opencode: int) -> None:
    port = str(opencode)
    assert bridge(opencode, "prompt", port, "ses_1", given={"text": "and for n=16"})["ok"]
    assert bridge(opencode, "new", port, given={"title": "From the phone"})["session"] == "ses_2"
    assert bridge(opencode, "abort", port, "ses_1")["stopped"] is True
    assert bridge(opencode, "permission", port, "per_1", "once")["replied"] is True
    assert bridge(opencode, "question", port, "que_1", given={"answers": [["cycle"]]})["replied"] is True
    assert OpenCode.sent == [
        ("/session/ses_1/prompt_async", {"parts": [{"type": "text", "text": "and for n=16"}]}),
        ("/session", {"title": "From the phone"}),
        ("/session/ses_1/abort", None),
        ("/permission/per_1/reply", {"reply": "once"}),
        ("/question/que_1/reply", {"answers": [["cycle"]]}),
    ]
    refused = bridge(opencode, "permission", port, "per_1", "maybe")
    assert refused == {"ok": False, "error": "a permission's reply is once, always or reject, not 'maybe'"}
    assert not bridge(opencode, "prompt", port, "ses_1", given={"text": "  "})["ok"]
    free = bridge(opencode, "free-port", ports=f"{opencode}-{opencode + 20}")  # another program may hold a neighbor
    assert opencode < free["port"] <= opencode + 20, f"the first port no server listens on, not the fake's: {free}"


def test_the_bridge_names_the_windows_agents_presses_tab_and_hands_a_plan_to_a_new_session(opencode: int) -> None:
    """Design 0009 §7-§8: Tab's agents in its order; Tab pressed by the command's old name (OpenCode 1.19 maps it);
    a new session whose first message build is sent, shown once that message is there."""
    port = str(opencode)
    assert bridge(opencode, "agents", port)["agents"] == ["build", "planner"]
    assert bridge(opencode, "cycle", port, "2")["cycled"] == 2
    asked = {"text": "Implement the plan in: p.md", "title": "Implement p.md"}
    found = bridge(opencode, "implement", port, given=asked)
    assert found == {"ok": True, "session": "ses_2", "shown": True}
    assert OpenCode.sent == [
        ("/tui/execute-command", {"command": "agent_cycle"}),
        ("/tui/execute-command", {"command": "agent_cycle"}),
        ("/session", {"title": "Implement p.md"}),
        ("/session/ses_2/prompt_async", {"agent": "build", "parts": [{"type": "text",
                                                                      "text": "Implement the plan in: p.md"}]}),
        ("/tui/select-session", {"sessionID": "ses_2"}),
    ]  # fmt: skip
    assert not bridge(opencode, "cycle", port, "9")["ok"]
    assert not bridge(opencode, "implement", port, given={"text": " "})["ok"]


def test_the_bridge_knows_a_terminal_interface_by_its_command_line(tmp_path: Path) -> None:
    """Design 0009 §7: `opencode --port N` (itself, or node running it) runs a window; `opencode serve` does not."""
    spec = importlib.util.spec_from_file_location("clank_image_bridge", BRIDGE)  # the image's bridge, as a module
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lines = {
        "101": ["opencode", "--port", "4096", "--hostname", "127.0.0.1"],
        "102": ["/usr/bin/node", "/usr/lib/node_modules/opencode-ai/bin/opencode", "--port", "4098"],
        "103": ["opencode", "serve", "--port", "4097"],
        "104": ["python3", "server.py", "--port", "5000"],
        "105": ["opencode"],
    }
    for pid, argv in lines.items():
        (tmp_path / pid).mkdir()
        (tmp_path / pid / "cmdline").write_bytes(b"\0".join(part.encode() for part in argv) + b"\0")
    (tmp_path / "self").mkdir()
    assert module.terminal_ports(str(tmp_path)) == {4096, 4098}
    assert module.terminal_ports(str(tmp_path / "missing")) == set()


def test_the_bridge_gives_starts_and_stops_the_mcp_servers_of_a_running_agent(opencode: int) -> None:
    port = str(opencode)
    [server] = bridge(opencode, "mcp")["servers"]
    assert server["mcp"] == {"clank": {"status": "connected", "error": ""},
                             "broken": {"status": "failed", "error": "it exited"}}  # fmt: skip
    assert bridge(opencode, "mcp-stop", port, "clank")["stopped"] is True
    assert bridge(opencode, "mcp-start", port, "clank")["status"] == {"status": "connected"}
    entry = {"type": "local", "command": ["myproject-mcp"], "environment": {}, "enabled": True}
    assert bridge(opencode, "mcp-start", port, "myproject", given={"config": entry})["status"]["status"] == "connected"
    refused = bridge(opencode, "mcp-start", port, "other")
    assert not refused["ok"]
    assert "not one of this agent's MCP servers" in refused["error"]
    assert OpenCode.sent == [
        ("/mcp/clank/disconnect", None), ("/mcp/clank/connect", None),
        ("/mcp", {"name": "myproject", "config": entry}),
    ]  # fmt: skip


@pytest.fixture
def kernel(home: Home, clock: FakeClock, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    platform = FakePlatform(state="running")
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def test_the_service_drives_a_session_through_the_bridge_and_records_who_did_what(
    kernel: Kernel, opencode: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kernel.settings.write("workspace", "paper", {"path": str(tmp_path)}, base=None, actor=PHONE_USER)
    platform: FakePlatform = kernel.parts["workspaces"].platform
    platform.containers.append(container(names(kernel.home.id).container("paper")))
    monkeypatch.setenv("CLANK_BRIDGE_PORTS", f"{opencode}-{opencode}")

    def inside(argv: list[str], given: bytes | None) -> Answer:
        assert argv[:2] == ["python3", "/opt/clank/bridge.py"]
        done = subprocess.run([sys.executable, str(BRIDGE), *argv[2:]], input=given or b"", capture_output=True,
                              timeout=60, creationflags=background_flags())  # fmt: skip
        return Answer(done.returncode, done.stdout.decode(), done.stderr.decode())

    platform.inside = inside
    sessions = kernel.parts["agents"].sessions
    [server] = sessions.servers("paper")
    assert server["sessions"][0]["status"] == "busy"
    sessions.send("paper", opencode, "ses_1", "send me the figure", actor=PHONE_USER)
    sessions.permission("paper", opencode, "per_1", "reject", actor=PHONE_USER)
    acted = kernel.events.after(0, types=["agents.acted"])
    assert [event.data["action"] for event in acted] == ["message", "permission"]
    assert acted[0].summary == "device phone sent a message to paper's agent (message: send me the figure)"
    with pytest.raises(SessionError, match="once, always or reject"):
        sessions.permission("paper", opencode, "per_1", "later", actor=PHONE_USER)
    platform.inside = None
    with pytest.raises(SessionError, match="did not answer"):
        sessions.servers("paper")
    platform.inside = lambda argv, given: Answer(
        2, "", f"python3: can't open file '{argv[1]}': [Errno 2] No such file or directory"
    )
    with pytest.raises(SessionError, match=r"older sandbox image.*x, then o"):
        sessions.servers("paper")


def test_an_mcp_server_is_stopped_and_started_while_the_agent_runs_and_kept_for_its_next_start(
    kernel: Kernel, opencode: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kernel.settings.write("workspace", "paper", {"path": str(tmp_path)}, base=None, actor=PHONE_USER)
    platform: FakePlatform = kernel.parts["workspaces"].platform
    platform.containers.append(container(names(kernel.home.id).container("paper")))
    monkeypatch.setenv("CLANK_BRIDGE_PORTS", f"{opencode}-{opencode}")

    def inside(argv: list[str], given: bytes | None) -> Answer:
        done = subprocess.run([sys.executable, str(BRIDGE), *argv[2:]], input=given or b"", capture_output=True,
                              timeout=60, creationflags=background_flags())  # fmt: skip
        return Answer(done.returncode, done.stdout.decode(), done.stderr.decode())

    platform.inside = inside
    agents = kernel.parts["agents"]
    [clank] = agents.live("paper")
    assert (clank["name"], clank["state"], clank["agents"], clank["checked"]) == ("clank", "running", True, None)
    stopped = agents.switch("paper", "clank", False, actor=PHONE_USER)
    assert (stopped["given"], stopped["applied"]) == (False, "now")
    assert kernel.settings.get("workspace", "paper").record.model_dump()["mcp_off"] == ["clank"]
    assert agents.live("paper")[0]["state"] == "stopped"
    started = agents.switch("paper", "clank", True, actor=PHONE_USER)
    assert (started["given"], started["applied"], agents.live("paper")[0]["state"]) == (True, "now", "running")
    acted = [event.summary for event in kernel.events.after(0, types=["agents.acted"])]
    assert acted[-2:] == [
        "device phone changed the MCP servers of paper's agent (mcp: clank stopped)",
        "device phone changed the MCP servers of paper's agent (mcp: clank started)",
    ]
    platform.inside = None  # the container does not answer: the choice is kept for the agent's next start
    held = agents.switch("paper", "clank", False, actor=PHONE_USER)
    assert held["applied"] == "at the agent's next start"
    [clank] = agents.live("paper")
    assert (clank["state"], clank["agents"]) == ("off", False)


def mcp(workspace: Path, *messages: dict[str, Any]) -> list[dict[str, Any]]:
    lines = "".join(json.dumps(message) + "\n" for message in messages)
    done = subprocess.run(
        [sys.executable, str(PHONE)], input=lines, capture_output=True, text=True, timeout=60,
        creationflags=background_flags(), env={**__import__("os").environ, "CLANK_WORKSPACE": str(workspace)},
    )  # fmt: skip
    return [json.loads(line) for line in done.stdout.splitlines()]


def test_send_to_phone_puts_a_file_of_the_folder_in_its_outbox_with_its_caption(tmp_path: Path) -> None:
    (tmp_path / "runs").mkdir()
    (tmp_path / "runs" / "tau.png").write_bytes(b"\x89PNG fake")
    call = {"jsonrpc": "2.0", "method": "tools/call"}
    hello, listed, sent, outside = mcp(
        tmp_path,
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {**call, "id": 3, "params": {"name": "send_to_phone",
                                     "arguments": {"path": "runs/tau.png", "caption": "tau vs p, n=8"}}},
        {**call, "id": 4, "params": {"name": "send_to_phone", "arguments": {"path": "../secret.txt"}}},
    )  # fmt: skip
    assert hello["result"]["serverInfo"]["name"] == "clank"
    assert [tool["name"] for tool in listed["result"]["tools"]] == [
        "send_to_phone", "look_at_figure", "notion_databases", "notion_query", "notion_page", "notion_search",
        "notion_propose_entry", "notion_propose_change", "notion_propose_removal", "notion_submit", "notion_reply",
        "flow_read", "flow_propose_box", "flow_submit", "flow_verdict", "flow_decide", "flow_job", "flow_draft",
    ], "the Notion tools (design 0010 §4-§7), a flow's (design 0013 §9, §16, §17) and its draft (§15)"  # fmt: skip
    assert sent["result"]["isError"] is False
    outbox = tmp_path / ".clank" / "outbox"
    [image] = [path for path in outbox.iterdir() if path.suffix == ".png"]
    assert image.read_bytes() == b"\x89PNG fake"
    note = json.loads((outbox / (image.name + ".json")).read_text(encoding="utf-8"))
    assert (note["caption"], note["from"]) == ("tau vs p, n=8", "runs/tau.png")
    assert (tmp_path / ".clank" / ".gitignore").read_text(encoding="utf-8").splitlines()[-1] == "*"
    assert outside["result"]["isError"] is True
    assert "not in the folder" in outside["result"]["content"][0]["text"]


def test_the_bridge_waits_for_a_window_that_answers_late_sends_to_the_planner_and_shows_the_session_again() -> None:
    """Design 0013 §15 (decision 0099): a planning session started on a window that is still starting: the bridge waits
    for its server, sends the first message to the agent asked for, and shows the session, then shows it again."""
    OpenCode.sent = []
    port = free_port()
    servers: list[ThreadingHTTPServer] = []

    def later() -> None:
        time.sleep(0.6)
        server = ThreadingHTTPServer(("127.0.0.1", port), OpenCode)
        servers.append(server)
        server.serve_forever()

    threading.Thread(target=later, daemon=True).start()
    asked = {"text": "Build a flow.", "title": "flow · building the flow", "agent": "planner", "wait": 20}
    try:
        found = bridge(port, "implement", str(port), given=asked, again="0.1,0.1")
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
    assert found == {"ok": True, "session": "ses_2", "shown": True}
    shown = ("/tui/select-session", {"sessionID": "ses_2"})
    assert OpenCode.sent == [
        ("/session", {"title": "flow · building the flow"}),
        ("/session/ses_2/prompt_async", {"agent": "planner", "parts": [{"type": "text", "text": "Build a flow."}]}),
        shown, shown, shown,
    ]  # fmt: skip
    silent = free_port()
    refused = bridge(silent, "implement", str(silent), given={**asked, "wait": 0.5})
    assert not refused["ok"]
    assert f"no OpenCode window answered on port {silent}" in refused["error"]


def test_a_planning_session_waits_for_a_new_windows_slow_first_answers_and_starts(opencode: int) -> None:
    """Design 0013 §15: OpenCode readies itself on a new window's first requests, which took longer than a request's
    usual wait for its answer on the owner's machine (2026-10-20 and 2026-10-22: the planning failed, "timed out", and
    no session was started). A planning's session gives each of its requests the whole wait the planning has."""
    OpenCode.slow = 1.0
    try:
        asked = {"text": "Build a flow.", "title": "flow · building the flow", "agent": "planner", "wait": 20}
        found = bridge(opencode, "implement", str(opencode), given=asked, answer="0.3")
    finally:
        OpenCode.slow = 0.0
    assert found == {"ok": True, "session": "ses_2", "shown": True}
    assert OpenCode.sent[:2] == [
        ("/session", {"title": "flow · building the flow"}),
        ("/session/ses_2/prompt_async", {"agent": "planner", "parts": [{"type": "text", "text": "Build a flow."}]}),
    ]  # fmt: skip


def test_the_bridge_shows_a_session_on_a_window_that_answers_late_and_again() -> None:
    """Design 0013 §15 (decision 0100): `clank flow attach` to a planning already talking: its session shown on the new
    window once it answers, then again; no session started."""
    OpenCode.sent = []
    port = free_port()
    servers: list[ThreadingHTTPServer] = []

    def later() -> None:
        time.sleep(0.6)
        server = ThreadingHTTPServer(("127.0.0.1", port), OpenCode)
        servers.append(server)
        server.serve_forever()

    threading.Thread(target=later, daemon=True).start()
    try:
        found = bridge(port, "show", str(port), "ses_plan", given={"wait": 20}, again="0.1,0.1")
    finally:
        for server in servers:
            server.shutdown()
            server.server_close()
    assert found == {"ok": True, "session": "ses_plan", "shown": True}
    assert OpenCode.sent == [("/tui/select-session", {"sessionID": "ses_plan"})] * 3, "shown, then again; none started"
    silent = free_port()
    refused = bridge(silent, "show", str(silent), "ses_plan", given={"wait": 0.5})
    assert not refused["ok"]
    assert f"no OpenCode window answered on port {silent}" in refused["error"]


def test_a_session_the_window_does_not_show_stands_and_says_so(opencode: int) -> None:
    """Design 0013 §15: OpenCode refusing to show the session leaves it started, its id given back, shown false."""
    OpenCode.unshown = True
    try:
        asked = {"text": "Build a flow.", "title": "flow · building the flow", "agent": "planner"}
        found = bridge(opencode, "implement", str(opencode), given=asked)
    finally:
        OpenCode.unshown = False
    assert found == {"ok": True, "session": "ses_2", "shown": False}
