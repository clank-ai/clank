"""Design 0018 §7.5: each time Clank starts an agent in a workspace (`prepare`, and `configure` for one started without
a terminal), it writes its current MCP server (`phone_mcp.py` and `find_figures.py`) and its instructions into the
agent's home in the container (`/home/agent/.clank/`), and OpenCode's configuration runs that server and reads those
instructions: the agent's tools are this Clank's, whatever image its container was made from. The instructions say how
a file is opened for the user (`show_files`; there is no `code` command in the container).

Design 0021 §9: and that the agent's model reads no images, `look_at_figure` asking Clank's vision model, which is
always there.

Design 0025 §12: and that, asked in a few words for a figure or a number that could mean different things, the agent
pins it down first in one question whose options a tap answers."""

import json
from pathlib import Path

from clank.components.workspaces.sandbox import (
    AGENT_CLANK,
    CURRENT_INSTRUCTIONS,
    CURRENT_PHONE,
    agent_files,
    image_folder,
)
from clank.kernel.core import Kernel
from tests.components.agents.test_agent_servers import CONFIG, kernel, opened, platform  # noqa: F401 (fixtures)
from tests.fakes.platform import FakePlatform

IMAGE = image_folder()


def test_clanks_files_for_the_agent_are_its_mcp_server_and_its_instructions_as_this_clank_has_them() -> None:
    found = dict(agent_files())
    assert CURRENT_PHONE == f"{AGENT_CLANK}/mcp/phone_mcp.py" == "/home/agent/.clank/mcp/phone_mcp.py"
    assert CURRENT_INSTRUCTIONS == "/home/agent/.clank/instructions/*.md"
    assert found[CURRENT_PHONE] == (IMAGE / "phone_mcp.py").read_text(encoding="utf-8")
    assert found[f"{AGENT_CLANK}/mcp/find_figures.py"] == (IMAGE / "find_figures.py").read_text(encoding="utf-8")
    for rules in sorted((IMAGE / "instructions").glob("*.md")):
        assert found[f"{AGENT_CLANK}/instructions/{rules.name}"] == rules.read_text(encoding="utf-8")
    files = found[f"{AGENT_CLANK}/instructions/files.md"]
    for needed in ("show_files", "no `code` command", "find_figures", "Do not read, describe or check"):
        assert needed in files, needed
    images = found[f"{AGENT_CLANK}/instructions/images.md"]
    for needed in ("reads no images", "look_at_figure", "never tell the user that no vision model is loaded"):
        assert needed in images, needed  # design 0021 §9


def test_the_agent_asks_one_question_with_options_from_the_folder_when_a_request_could_mean_different_things() -> None:
    asking = dict(agent_files())[f"{AGENT_CLANK}/instructions/asking.md"]
    for needed in ("`question` tool", "two to four", "Look in the folder first", "Do not ask when the request is clear",
                   "`show_files`"):  # fmt: skip
        assert needed in asking, needed


def test_starting_an_agent_writes_them_and_its_configuration_runs_and_reads_them(
    kernel: Kernel,  # noqa: F811
    platform: FakePlatform,  # noqa: F811
    tmp_path: Path,
) -> None:
    folder = tmp_path / "paper"
    folder.mkdir()
    container_name = opened(kernel, platform, folder)
    kernel.parts["agents"].prepare("paper")
    for path, text in agent_files():
        assert platform.files[(container_name, path)] == text, path
    config = json.loads(platform.files[(container_name, CONFIG)])
    assert config["mcp"]["clank"]["command"] == ["python3", CURRENT_PHONE]
    assert config["instructions"] == [CURRENT_INSTRUCTIONS]
    platform.files.clear()
    kernel.parts["agents"].configure("paper")
    assert platform.files[(container_name, CURRENT_PHONE)], "a flow's OpenCode, started without a terminal, too"
