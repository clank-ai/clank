"""The tools component's declaration (design 0002 §1, §2.1; the M8.0 plan).

It owns the MCP servers: those added for the user (`config/mcp-servers/`, their values kept as secrets) and a project's
`.mcp.json`; checking one. M8 adds the catalog, installs, each server in its own container, and the tool hub. It uses
the workspaces, to check a server in a workspace's container, where its agent will start it (design 0004 §10).
"""

from typing import Any

from clank.components.tools.kinds import McpServer
from clank.components.tools.service import EVENT_TYPES, Tools
from clank.kernel.components import Component


def commands() -> list[Any]:
    """`clank mcp`."""
    from clank.components.tools.cli import mcp

    return [mcp]


def pages() -> list[Any]:
    """The MCP servers page in the console."""
    from clank.components.tools.console.servers import McpServersPage

    return [McpServersPage]


COMPONENT = Component(
    name="tools",
    summary="MCP servers: added the way other harnesses add them, listed, checked and removed; M8 runs them.",
    kinds=(McpServer,),
    event_types=tuple(EVENT_TYPES),
    build=Tools,
    uses=("workspaces",),
    commands=commands,
    console=pages,
)
