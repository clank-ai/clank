"""The agents component's declaration (design 0002 §1, design 0004 §4).

It owns the programs that work in a workspace: the agent program kind of adapter (OpenCode first, decision 0011),
making one ready in a workspace's container, the console's page for the folder clank was started in (a bare `clank`
opens the console on it) and the Monitor (F10: watching and guiding a session, design 0012), `clank work`: the agent,
in a folder, at once, and Clank's VS Code window (`clank code`: the folder, the agent beside the files; its settings
`config/vscode.json`), what the Monitor's Watch for rules do (`config/monitor.json`, design 0012 §8), and what OpenCode
is told of its model (`config/opencode.json`: the margin kept for a step's tool results, decision 0089), and `clank
setup` with the console's Setup page (design 0028 §4: what Clank needs on this computer, and the fixes). It uses the
workspaces (the container), the gateway (the model's URL and limits) and the tools (the MCP servers the agent gets,
design 0004 §10); the runtime and the machine for Add a model's guide and the setup's checklist.
"""

from typing import Any

from clank.components.agents.adapters import AGENT_PROGRAMS
from clank.components.agents.kinds import MonitorSettings, OpenCodeSettings, VsCodeSettings
from clank.components.agents.service import EVENT_TYPES, Agents
from clank.kernel.components import Component


def pages() -> list[Any]:
    """The page of the folder clank was started in, the Monitor (design 0012), and Setup (design 0028 §4)."""
    from clank.components.agents.console.folder import FolderPage
    from clank.components.agents.console.monitor import MonitorPage
    from clank.components.agents.console.setup import SetupPage

    return [FolderPage, MonitorPage, SetupPage]


def commands() -> list[Any]:
    """`clank work`, `clank code`, `clank latex` (design 0020), `clank jobs` and `clank artifact` (design 0021), `clank
    board` (design 0022), and `clank setup` (design 0028 §4)."""
    from clank.components.agents.artifactcli import artifact
    from clank.components.agents.boardcli import board
    from clank.components.agents.cli import code, work
    from clank.components.agents.jobscli import jobs
    from clank.components.agents.latexcli import latex
    from clank.components.agents.setupcli import setup

    return [work, code, latex, jobs, artifact, board, setup]


COMPONENT = Component(
    name="agents",
    summary="The programs that work in a workspace (OpenCode first), and `clank work`: the agent in a folder.",
    kinds=(VsCodeSettings, MonitorSettings, OpenCodeSettings),
    event_types=tuple(EVENT_TYPES),
    adapter_kinds=(AGENT_PROGRAMS,),
    build=Agents,
    uses=("workspaces", "gateway", "tools", "runtime", "machine"),  # runtime and machine: Add a model's guide
    commands=commands,
    console=pages,
)
