"""`clank artifact` (design 0021 §5): the artifacts the agent made in a folder's workspace, from the command line.
`clank artifact list [FOLDER]` lists them, the newest made first; `clank artifact export NAME [--version N] [FOLDER]`
writes one version as one self-contained page (its libraries and files inside it) and says where. Each asks the service
(`/agents/artifacts`), which reads the folder's `.clank/artifacts/`.
"""

import os
from pathlib import Path
from typing import Any

import click

from clank.cli import common


@click.group()
def artifact() -> None:
    """The artifacts the agent made: pages of results, reports, diagrams."""


def _workspace(client: Any, folder: str | None) -> str:
    """The workspace of a folder (this one unless named)."""
    path = str(Path(folder or os.getcwd()).resolve())
    found = common.call(lambda: client.get("workspaces/folder", folder=path))
    if not found.get("workspace"):
        raise click.ClickException(f"{path} has no Clank workspace: run `clank` in it first")
    return str(found["workspace"])


@artifact.command(name="list")
@click.argument("folder", required=False)
def listed(folder: str | None) -> None:
    """The folder's artifacts, the newest made first."""
    client = common.call(common.connect)
    workspace = _workspace(client, folder)
    found = common.call(lambda: client.get("agents/artifacts", workspace=workspace))["artifacts"]
    if not found:
        click.echo(f"{workspace} has no artifact yet.")
    for each in found:
        versions = f"{each['versions']} version{'' if each['versions'] == 1 else 's'}"
        click.echo(f"{each['name']}  {each['title']}  ({each['kind']}, {versions}, the newest {each['made']})")


@artifact.command()
@click.argument("name")
@click.argument("folder", required=False)
@click.option("--version", "number", type=int, default=0, help="The version; default: the newest.")
def export(name: str, folder: str | None, number: int) -> None:
    """One version as one self-contained page, to open in any browser or send."""
    client = common.call(common.connect)
    workspace = _workspace(client, folder)
    if not number:
        number = len(common.call(lambda: client.get(f"agents/artifacts/{workspace}/{name}"))["versions"])
    done = common.call(lambda: client.post(f"agents/artifacts/{workspace}/{name}/export", {"version": number}))
    click.echo(done["said"])
