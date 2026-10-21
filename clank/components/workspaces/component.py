"""The workspaces component's declaration (design 0002 §1, §2.1).

It owns where agents work: in M0, Docker (its settings, `config/docker.json`, and the container platform kind of
adapter, with Docker Desktop first); from M4, the workspaces themselves (`config/workspaces/`), their containers and
the edge, which forwards the gateway's port: so it uses the gateway.
"""

from typing import Any

from clank.components.workspaces.adapters import CONTAINER_PLATFORMS
from clank.components.workspaces.kinds import DockerSettings, Workspace
from clank.components.workspaces.service import EVENT_TYPES, Workspaces
from clank.kernel.components import Component


def commands() -> list[Any]:
    """`clank docker` and `clank workspace`."""
    from clank.components.workspaces.cli import docker, workspace

    return [docker, workspace]


def pages() -> list[Any]:
    """Docker's page and the Workspaces page in the console."""
    from clank.components.workspaces.console.docker import DockerPage
    from clank.components.workspaces.console.workspaces import WorkspacesPage

    return [DockerPage, WorkspacesPage]


COMPONENT = Component(
    name="workspaces",
    summary="Where agents work: Docker, the container platform, in M0; the workspaces themselves from M4.",
    kinds=(DockerSettings, Workspace),
    event_types=tuple(EVENT_TYPES),
    adapter_kinds=(CONTAINER_PLATFORMS,),
    build=Workspaces,
    uses=("gateway",),
    commands=commands,
    console=pages,
)
