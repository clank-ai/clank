"""The workspaces component's kinds of record: how Clank uses Docker (`config/docker.json`), and from M4 each workspace
(`config/workspaces/<name>.json`): the folder an agent works in, its container's CPUs and memory, and from design 0004
§10 the setup that installs the folder's own software and the MCP servers its agent gets, and from design 0007
whether the agent's changes to files are reviewed.

Every value applies at once: the background check reads its interval each time, and an operation its limits when it
starts.
"""

from typing import Literal

from pydantic import Field

from clank.kernel.records import Settings


class DockerSettings(Settings):
    """How Clank uses Docker."""

    KIND = "docker"
    LABEL = "Docker"
    HELP = "How Clank uses Docker: which container platform, how often it is checked, and how long it may take."
    SINGLE = True

    adapter: str = Field(
        "docker-desktop",
        title="Container platform",
        description="The adapter Clank uses for containers: docker-desktop, or docker-engine (Docker Engine on Linux, "
        "the system's service, which Clank never starts or stops).",
    )
    poll_seconds: float = Field(
        5.0, ge=1, title="Checked every", description="How often, in seconds, Clank reads Docker's state."
    )
    start_timeout_seconds: int = Field(
        300, ge=10, title="Time to start", description="How long a start may take before it is reported as failed."
    )
    stop_timeout_seconds: int = Field(
        120, ge=10, title="Time to stop", description="How long a stop may take before it is reported as failed."
    )
    question_minutes: int = Field(
        30,
        ge=1,
        title="Time to answer",
        description="How long a question about stopping Docker waits before its default (cancel) applies.",
    )


class Workspace(Settings):
    """A folder an agent works in, in a container of its own."""

    KIND = "workspace"
    LABEL = "Workspace"
    HELP = "A folder agents work in, in a container of its own: the folder, and the container's CPUs and memory."

    path: str = Field(
        title="Folder",
        description="The folder on this machine; its container sees it as /workspace, and nothing else of the machine.",
    )
    cpus: float | None = Field(
        None, ge=0.5, title="CPUs", description="The CPUs its container may use; empty: half of what Docker has."
    )
    memory_mib: int | None = Field(
        None,
        ge=512,
        title="Memory",
        description="The memory its container may use, in MiB; empty: a quarter of what Docker has.",
    )
    layers: list[str] = Field(
        default_factory=list,
        title="Image layers",
        description=(
            "What its container has besides Clank's sandbox image, each built on it once: tex (TeX Live, for the LaTeX "
            "the agent writes, design 0020). Its container moves to the new image when it is next made."
        ),
    )
    setup: str | None = Field(
        None,
        title="Setup",
        description="The command that installs the folder's own software into its home (~/.venv), run by Clank in a "
        "container that reaches the internet; empty: proposed from the folder's files (pyproject.toml, "
        "requirements.txt).",
    )
    set_up: str = Field(
        "",
        title="Installed with",
        description="The setup command that last ran to its end; empty: the software is not installed.",
    )
    mcp_allowed: dict[str, str] = Field(
        default_factory=dict,
        title="Folder's MCP servers allowed",
        description="The folder's own MCP servers (its .mcp.json) its agent gets, each with the fingerprint of its "
        "entry as allowed: an entry changed since is not given until it is allowed again.",
    )
    mcp_off: list[str] = Field(
        default_factory=list,
        title="Your MCP servers held back",
        description="Your own MCP servers (clank mcp add) this workspace's agent does not get; the others it gets.",
    )
    hosts: dict[str, str] = Field(
        default_factory=dict,
        title="Hosts its agent may reach",
        description="The internet hosts its agent reaches through Clank's proxy (design 0024): a name (pypi.org) or a "
        "suffix (.arxiv.org: arxiv.org and every name under it), each with when and how it was allowed. Every other "
        "host is refused; private addresses always.",
    )
    changes: Literal["review", "auto"] = Field(
        "review",
        title="The agent's changes",
        description="review: the agent asks before it changes a file, and you accept or reject the change (VS Code "
        "shows it beside your files); auto: it changes files without asking, and VS Code shows each change after.",
    )
    one_window: bool = Field(
        True,
        title="One OpenCode window",
        description="Opening OpenCode in a terminal (VS Code's, or the console's) first closes every OpenCode window "
        "open in the workspace, so there is only ever one and switching between plan, review and auto reaches it; "
        "off: each opening adds another window. OpenCode without a terminal (the phone's) is left alone.",
    )
    models: Literal["this-machine", "cloud"] = Field(
        "this-machine",
        title="Where its requests may go",
        description="this-machine: its agent's requests go only to a model on this machine; cloud: also to a cloud "
        "model, once you allowed it (design 0016 §9). Every workspace starts on this machine.",
    )
    cloud_answered: str = Field(
        "",
        title="Cloud answered",
        description="When you last answered whether it may use the cloud model; empty: never asked, or not answered "
        "in time, so it is asked the next time a cloud model would serve it.",
    )
