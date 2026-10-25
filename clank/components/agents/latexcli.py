"""`clank latex` (design 0020): LaTeX with the agent. `clank latex setup [FOLDER]` gives the folder's workspace the TeX
layer (§3): the workspace is opened with it (made the first time), which adds it to its record and builds its image on
Clank's sandbox image (asked first unless `--yes`). A container already running keeps
its image until it is made again; `--restart` stops it and opens it again on the new image at once, which ends the
agent's sessions running there.
"""

import os
from pathlib import Path
from typing import Any

import click

from clank.cli import common, follow
from clank.client import Client


@click.group()
def latex() -> None:
    """LaTeX with the agent: TeX in the folder's container (design 0020)."""


@latex.command()
@click.argument("folder", required=False)
@click.option("--yes", is_flag=True, help="Build the images without asking first, when they are not built.")
@click.option("--restart", is_flag=True, help="Stop the workspace's container and open it again on the new image now.")
def setup(folder: str | None, yes: bool, restart: bool) -> None:
    """Give a folder's workspace (this one unless named) TeX Live in its container."""
    path = str(Path(folder or os.getcwd()).resolve())
    client = common.call(common.connect)
    docker = common.call(lambda: client.get("docker", refresh=True))
    if docker["state"] != "running":
        click.echo(f"Docker is {docker['state']}: starting it")
        _done(follow.follow(client, common.call(lambda: client.post("docker/start"))))
    opened = _open(client, path, yes)
    name = opened["workspace"]
    if restart:
        _done(follow.follow(client, common.call(lambda: client.post(f"workspaces/{name}/stop"))))
        opened = _open(client, path, yes)
    view = common.call(lambda: client.get("workspaces/folder", folder=path))
    click.echo(f"TeX is in {name}'s image ({opened['image']})")
    if view["image"]["current"] is False:
        click.echo(
            "Its container still runs the image it was made from: `clank latex setup --restart` moves it now (the "
            "agent's sessions running there end), or it moves when the workspace is next stopped and opened"
        )
    else:
        click.echo("its container runs it: TeX is ready")


def _open(client: Client, path: str, yes: bool) -> dict[str, Any]:
    started = common.call(lambda: client.post("workspaces/open", {"folder": path, "yes": yes, "layers": ["tex"]}))
    return _done(follow.follow(client, started))


def _done(operation: dict[str, Any]) -> dict[str, Any]:
    """The result of an operation that ended well; else its error said, and exit 1."""
    if operation["status"] != "done":
        click.echo(f"{operation['title']}: {operation['error'] or operation['status']}")
        raise click.exceptions.Exit(1)
    return dict(operation.get("result") or {})
