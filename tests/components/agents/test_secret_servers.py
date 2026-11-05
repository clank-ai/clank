"""Design 0002 §2.8 and design 0004 §10: the secret values of your own MCP servers reach the agent in OpenCode's
environment alone. Its configuration names a variable of OpenCode's own environment for each (`{env:NAME}`, which
OpenCode reads as it loads the file), the variables go to `docker exec` by name and to the client in `env`, and no value
is in any file Clank writes into the container, nor on a command line. A value is put in the variable as OpenCode
needs it to read back the same (it puts the variable's text into the file's JSON as it is). A server with secrets that
a running OpenCode does not know is not added to it live: its values reach OpenCode only when it starts."""

import json
import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from clank import registry
from clank.components.agents.adapters.opencode import OpenCode
from clank.components.agents.service import Agents
from clank.components.tools.mcp import Server
from clank.components.workspaces import service as workspaces_service
from clank.components.workspaces.sandbox import names
from clank.kernel.clock import FakeClock
from clank.kernel.core import Kernel, open_kernel
from clank.kernel.events import Actor
from clank.kernel.home import Home
from clank.kernel.processes import Answer
from tests.fakes.platform import FakePlatform, container

YOU = Actor(kind="user", via="console")
CONFIG = "/home/agent/.config/opencode/opencode.json"
VALUE = "k1-the-value"


@pytest.fixture
def platform() -> FakePlatform:
    return FakePlatform(state="running")


@pytest.fixture
def kernel(home: Home, clock: FakeClock, platform: FakePlatform, monkeypatch: pytest.MonkeyPatch) -> Iterator[Kernel]:
    monkeypatch.setattr(workspaces_service, "make_platform", lambda name: platform)
    kernel = open_kernel(home, clock, registry.components())
    yield kernel
    kernel.close()


def opened(kernel: Kernel, platform: FakePlatform, folder: Path, **values: object) -> str:
    """The folder's workspace, its container running."""
    folder.mkdir(exist_ok=True)
    kernel.settings.write("workspace", "paper", {"path": str(folder), **values}, base=None, actor=YOU)
    name = names(kernel.home.id).container("paper")
    platform.containers.append(container(name, labels={"clank.home": kernel.home.id}))
    return name


def substituted(text: str, env: dict[str, str]) -> Any:
    """The configuration as OpenCode reads it: each `{env:NAME}` replaced by the variable's text, then parsed."""
    return json.loads(re.sub(r"\{env:([^}]+)\}", lambda found: env.get(found.group(1), ""), text))


def test_a_servers_secret_values_reach_opencode_in_its_environment_and_its_configuration_names_them(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    kernel.parts["tools"].add("notes", {"command": "notes-mcp", "env": {"KEY": VALUE}}, scope="user", folder="",
                              actor=YOU)  # fmt: skip
    box = opened(kernel, platform, tmp_path / "paper")
    agents: Agents = kernel.parts["agents"]
    prepared = agents.prepare("paper")
    written = platform.files[(box, CONFIG)]
    assert json.loads(written)["mcp"]["notes"]["environment"] == {"KEY": "{env:CLANK_MCP_NOTES__KEY}"}
    assert prepared["env"]["CLANK_MCP_NOTES__KEY"] == VALUE, "OpenCode's own environment holds it"
    assert prepared["argv"][prepared["argv"].index("CLANK_MCP_NOTES__KEY") - 1] == "--env", "named alone"
    assert not any(VALUE in part for part in prepared["argv"]), "no value on the command line"
    assert not any(VALUE in text for text in platform.files.values()), "no value in any file in the container"
    assert substituted(written, prepared["env"])["mcp"]["notes"]["environment"] == {"KEY": VALUE}

    env = agents.configure("paper")  # OpenCode started without a terminal: its environment goes on the bridge's input
    assert env["CLANK_MCP_NOTES__KEY"] == VALUE
    assert not any(VALUE in text for text in platform.files.values())


def test_a_value_opencode_puts_into_its_json_as_it_is_reads_back_the_same() -> None:
    """OpenCode puts the variable's text into the file's JSON before it reads it: Clank writes the variable as that JSON
    needs it (a quote, a backslash, a line break, and a brace that could start another of OpenCode's references)."""
    odd = 'a"b\\c\nd{file:/etc/hostname}é'
    servers = {"notes": Server("stdio", command="notes-mcp", env={"KEY": odd, "MODE": "fast"})}
    named, env = OpenCode().by_reference(servers, {"notes"})
    _, text = OpenCode().configuration(fake_model(), named)
    assert odd not in text
    found = substituted(text, env)["mcp"]["notes"]["environment"]
    assert found == {"KEY": odd, "MODE": "fast"}
    assert "{file:" not in re.sub(r"\{env:([^}]+)\}", lambda each: env[each.group(1)], text), "no reference made"


def test_each_servers_variables_are_its_own_and_another_servers_environment_is_written_as_it_is() -> None:
    servers = {
        "notes": Server("stdio", command="notes-mcp", env={"KEY": "one"}),
        "notes-2": Server("stdio", command="notes-mcp", env={"KEY": "two"}),
        "myproject": Server("stdio", command="myproject-mcp", env={"MODE": "fast"}),
    }
    named, env = OpenCode().by_reference(servers, {"notes", "notes-2"})
    assert named["notes"].env == {"KEY": "{env:CLANK_MCP_NOTES__KEY}"}
    assert named["notes-2"].env == {"KEY": "{env:CLANK_MCP_NOTES_2__KEY}"}
    assert env == {"CLANK_MCP_NOTES__KEY": "one", "CLANK_MCP_NOTES_2__KEY": "two"}
    assert named["myproject"] == servers["myproject"], "a folder's own server keeps its file's entry"


def test_a_server_with_secrets_is_not_added_live_to_an_opencode_that_does_not_know_it(
    kernel: Kernel, platform: FakePlatform, tmp_path: Path
) -> None:
    kernel.parts["tools"].add("notes", {"command": "notes-mcp", "env": {"KEY": VALUE}}, scope="user", folder="",
                              actor=YOU)  # fmt: skip
    opened(kernel, platform, tmp_path / "paper")
    agents: Agents = kernel.parts["agents"]
    agents.allow("paper", "notes", False, actor=YOU)
    sent: list[tuple[list[str], Any]] = []

    def inside(argv: list[str], given: bytes | None) -> Answer:
        sent.append((argv[2:], json.loads(given) if given else None))
        if argv[2] == "mcp":
            return Answer(0, json.dumps({"ok": True, "servers": [{"port": 4096, "mcp": {}}]}), "")
        return Answer(0, json.dumps({"ok": False, "error": "notes is not one of this agent's MCP servers"}), "")

    platform.inside = inside
    found = agents.switch("paper", "notes", True, actor=YOU)
    [(_, start)] = [each for each in sent if each[0][0] == "mcp-start"]
    assert start == {"config": {}}, "no entry, so no value, goes to a running OpenCode"
    assert found["given"] is True
    assert found["applied"] == "at the agent's next start"
    assert "its secret values reach OpenCode only in its environment, as it starts" in found["problem"]
    assert not any(VALUE in json.dumps(each) for each in sent)


def fake_model() -> Any:
    from clank.components.agents.adapters.program import AgentModel

    return AgentModel(url="http://edge:18210/v1", name="agent", title="a model", context=32768, output=8192)
