"""The tools component's kinds of record (design 0002 §1, §2.11; the M8.0 plan): the MCP servers added for the user.

A project's own servers are not records: they are its `.mcp.json`, the file other harnesses read (the service's
`Tools` reads and writes it). A server of the owner's may be marked local only (design 0016 §10): what it gives the
agent never goes to a cloud model.
"""

from typing import Literal

from pydantic import Field, model_validator

from clank.kernel.records import Settings


class McpServer(Settings):
    """An MCP server added for the user."""

    KIND = "mcp-server"
    LABEL = "MCP server"
    HELP = (
        "An MCP server, added as other harnesses add one (`claude mcp add`, `codex mcp add`): the command that starts "
        "it (stdio), or the address it listens at (http, sse). The values of its environment variables and headers "
        "are kept with the secrets, never in this file."
    )

    transport: Literal["stdio", "http", "sse"] = Field(
        "stdio",
        title="Transport",
        description=(
            "How Clank talks to it: stdio, a program started and spoken to over its input and output; http, the "
            "streamable HTTP transport; sse, the older server-sent events one."
        ),
    )
    command: str = Field("", title="Command", description="The program that starts it (stdio).")
    args: list[str] = Field(
        default_factory=list, title="Arguments", description="What the program is given after its name (stdio)."
    )
    env: list[str] = Field(
        default_factory=list,
        title="Environment",
        description="The names of the environment variables it is started with; their values are secrets.",
    )
    url: str = Field("", title="Address", description="Where it listens (http, sse).")
    headers: list[str] = Field(
        default_factory=list,
        title="Headers",
        description="The names of the HTTP headers sent to it; their values are secrets.",
    )
    local_only: bool = Field(
        False,
        title="Local only",
        description="What it gives the agent never goes to a cloud model (design 0016 §10): a workspace allowed the "
        "cloud does not get it, and the gateway keeps its tools and a session that used it from the cloud.",
    )

    @model_validator(mode="after")
    def _complete(self) -> "McpServer":
        if self.transport == "stdio" and not self.command:
            raise ValueError("a stdio server needs the command that starts it")
        if self.transport != "stdio" and not self.url:
            raise ValueError(f"an {self.transport} server needs the address it listens at")
        return self
