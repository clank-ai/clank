"""Design 0016 §9 and §10 (decisions 0075 and 0111): once the cloud is in play, each workspace's OpenCode sends its
workspace's own key to the gateway, never `local`, and so does Clank's MCP server in its container (before, nothing
changes: `local`, and no key made); a workspace allowed the cloud gets no MCP
server marked local only (held back, saying why) and Clank's server lists no Notion tool there; a workspace kept on this
machine gets them all; and the gateway's routes carry the names of the tools kept from the cloud: Clank's Notion tools
always, and each server marked local, as OpenCode names them, once the agents component gave them (until then the
routes say so, and the gateway sends nothing to the cloud)."""

import json
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, ClassVar

import pytest

from clank import registry
from clank.components.agents.service import Agents
from clank.components.gateway.service import Gateway
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import image_folder, names
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import background_flags
from tests.fakes.platform import FakePlatform, container
from tests.support.served import free_port

YOU = Actor(kind="user", via="console")
CONFIG = "/home/agent/.config/opencode/opencode.json"
SERVER = image_folder() / "phone_mcp.py"


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def opened(kernel: Kernel, platform: FakePlatform, tmp_path: Path, models: str = "this-machine") -> str:
    folder = tmp_path / "paper"
    folder.mkdir(exist_ok=True)
    kernel.settings.write("workspace", "paper", {"path": str(folder), "models": models}, base=None, actor=YOU)
    name = names(kernel.home.id).container("paper")
    platform.containers.append(container(name, labels={"clank.home": kernel.home.id}))
    return name


def servers(kernel: Kernel) -> None:
    tools = kernel.parts["tools"]
    tools.add("lit", {"command": "lit-mcp"}, scope="user", folder="", actor=YOU, local_only=True)
    tools.add("plot", {"command": "plot-mcp"}, scope="user", folder="", actor=YOU)


def agreed(kernel: Kernel) -> None:
    """A cloud provider agreed, as Add a model writes it."""
    from clank.components.runtime.adapters.openrouter import OpenRouter

    values = {**OpenRouter.template(), "agreed": "2026-10-21T09:12:04.120Z"}
    kernel.settings.write("endpoint", "openrouter", values, base=None, actor=YOU)


def test_before_any_cloud_provider_is_agreed_opencode_sends_local_and_no_key_is_made(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    container_name = opened(kernel, platform, tmp_path)
    kernel.parts["agents"].prepare("paper")
    config = json.loads(platform.files[(container_name, CONFIG)])
    assert config["provider"]["clank"]["options"]["apiKey"] == "local"
    assert config["mcp"]["clank"]["environment"]["CLANK_GATEWAY_KEY"] == "local"
    assert not (kernel.home.secrets / "workspace").exists()
    assert [event for event in kernel.events.latest(200) if event.type.startswith("secret.")] == []


def test_opencode_and_clanks_server_send_the_workspaces_own_key(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    agreed(kernel)
    container_name = opened(kernel, platform, tmp_path)
    kernel.parts["agents"].prepare("paper")
    config = json.loads(platform.files[(container_name, CONFIG)])
    gateway: Gateway = kernel.parts["gateway"]
    key = gateway.workspace_key("paper", why="a test")
    assert config["provider"]["clank"]["options"]["apiKey"] == key
    assert key != "local"
    environment = config["mcp"]["clank"]["environment"]
    assert environment["CLANK_GATEWAY_KEY"] == key
    assert "CLANK_NOTION" not in environment


def test_a_workspace_allowed_the_cloud_gets_no_server_marked_local_and_no_notion(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    servers(kernel)
    container_name = opened(kernel, platform, tmp_path, models="cloud")
    agents: Agents = kernel.parts["agents"]
    rows = {row["name"]: (row["given"], row["why"]) for row in agents.servers("paper")}
    assert rows["lit"] == (False, "held back: local only, it never goes to the cloud model")
    assert rows["plot"] == (True, "")
    agents.prepare("paper")
    config = json.loads(platform.files[(container_name, CONFIG)])
    assert set(config["mcp"]) == {"clank", "plot"}
    assert config["mcp"]["clank"]["environment"]["CLANK_NOTION"] == "off"


def test_a_workspace_kept_on_this_machine_gets_them_all(kernel: Kernel, platform: FakePlatform, tmp_path: Path) -> None:
    servers(kernel)
    container_name = opened(kernel, platform, tmp_path)
    kernel.parts["agents"].prepare("paper")
    assert set(json.loads(platform.files[(container_name, CONFIG)])["mcp"]) == {"clank", "lit", "plot"}


def test_the_gateways_routes_carry_the_tools_kept_from_the_cloud(kernel: Kernel) -> None:
    gateway: Gateway = kernel.parts["gateway"]
    agents: Agents = kernel.parts["agents"]
    before = gateway.routes()
    assert (before["local_only"], before["local_only_given"]) == (["clank_notion_"], False)
    agents.give_local_only()
    assert (gateway.routes()["local_only"], gateway.routes()["local_only_given"]) == (["clank_notion_"], True)
    servers(kernel)
    assert gateway.routes()["local_only"] == ["clank_notion_", "lit_"], "each change of a server gives them again"
    kernel.parts["tools"].add("my-notes", {"command": "notes-mcp"}, scope="user", folder="", actor=YOU, local_only=True)
    assert gateway.routes()["local_only"] == ["clank_notion_", "lit_", "my-notes_"]


class Edge(BaseHTTPRequestHandler):
    """The gateway's routes as Clank's server reaches them, and the headers it sent."""

    heard: ClassVar[list[dict[str, str]]] = []

    def do_GET(self) -> None:
        Edge.heard.append(dict(self.headers))
        data = json.dumps({"databases": []}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        """Quiet."""


@pytest.fixture
def edge() -> Iterator[str]:
    Edge.heard = []
    port = free_port()
    server = ThreadingHTTPServer(("127.0.0.1", port), Edge)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{port}/v1"
    server.shutdown()
    server.server_close()


def session(tmp_path: Path, edge: str, messages: list[dict[str, Any]], **extra: str) -> list[Any]:
    opening = {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}
    env = {"CLANK_WORKSPACE": str(tmp_path), "CLANK_GATEWAY": edge, "CLANK_WORKSPACE_NAME": "paper",
           "SYSTEMROOT": "C:\\Windows", "PATH": "", **extra}  # fmt: skip
    done = subprocess.run(
        [sys.executable, str(SERVER)], input="".join(json.dumps(each) + "\n" for each in [opening, *messages]),
        capture_output=True, text=True, timeout=120, creationflags=background_flags(), env=env,
    )  # fmt: skip
    return [json.loads(line) for line in done.stdout.splitlines()][1:]


def test_clanks_server_sends_the_key_and_lists_no_notion_tool_when_told_so(tmp_path: Path, edge: str) -> None:
    listing = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    reading = {
        "jsonrpc": "2.0",
        "id": 2,
        "method": "tools/call",
        "params": {"name": "notion_databases", "arguments": {}},
    }
    [listed, read] = session(tmp_path, edge, [listing, reading], CLANK_GATEWAY_KEY="clank-ws-made-up")
    assert "notion_databases" in {tool["name"] for tool in listed["result"]["tools"]}
    assert read["result"]["isError"] is False
    assert Edge.heard[0]["Authorization"] == "Bearer clank-ws-made-up"
    [listed, refused] = session(tmp_path, edge, [listing, reading], CLANK_GATEWAY_KEY="k", CLANK_NOTION="off")
    assert not any(tool["name"].startswith("notion_") for tool in listed["result"]["tools"])
    assert refused["error"]["message"] == "no such tool"
