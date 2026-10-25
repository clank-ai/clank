"""Design 0018 §7.5, on this machine's Docker when asked (`-m docker`): starting an agent in a real workspace's
container writes Clank's current MCP server and instructions into the agent's home there, and that server, run as
OpenCode runs it, lists `show_files` and `find_figures`, whatever image the container was made from."""

import json
import subprocess
from pathlib import Path
from typing import Any

import anyio
import pytest

from clank.components.workspaces.sandbox import CURRENT_PHONE, names
from clank.kernel.core import Kernel
from clank.kernel.events import Actor

pytestmark = [pytest.mark.docker, pytest.mark.anyio]
YOU = Actor(kind="user", via="console")


async def test_starting_an_agent_gives_it_this_clanks_tools(machine: Kernel, tmp_path: Path) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    async with machine.operations.running():
        started = await machine.operations.start("workspaces.open", {"folder": str(folder), "yes": True}, actor=YOU)
        with anyio.fail_after(2400):
            done = await machine.operations.wait(started.id)
    assert done.status == "done", done.error
    await anyio.to_thread.run_sync(lambda: machine.parts["agents"].configure("paper"))
    container = names(machine.home.id).container("paper")
    asked: list[Any] = [
        {"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
    ]
    listed = subprocess.run(
        ["docker", "exec", "-i", container, "python3", CURRENT_PHONE],
        input="".join(json.dumps(each) + "\n" for each in asked), capture_output=True, text=True, timeout=60,
        check=False,
    )  # fmt: skip
    tools = {tool["name"] for tool in json.loads(listed.stdout.splitlines()[1])["result"]["tools"]}
    assert {"show_files", "find_figures", "send_to_phone"} <= tools
    rules = subprocess.run(["docker", "exec", container, "sh", "-c", "ls /home/agent/.clank/instructions"],
                           capture_output=True, text=True, timeout=60, check=False)  # fmt: skip
    assert rules.stdout.split() == ["artifacts.md", "files.md", "images.md", "jobs.md", "latex.md"]
