"""`clank board` (design 0022 §1): a folder's boards from the command line. `clank board new NAME [--in FOLDER]
[--title TITLE] [FOLDER]` makes an empty board (`NAME.board`, in the subfolder `--in` names) and says where;
`clank board list [FOLDER]` lists the folder's boards, the newest changed first; `clank board show BOARD [FOLDER]`
prints a board in words, as the agent reads it. Each asks the service (`/agents/boards`).
"""

import os
from pathlib import Path
from typing import Any

import click

from clank.cli import common


@click.group()
def board() -> None:
    """Boards: canvases you and the agent share, with figures, LaTeX, notes and frames."""


def _workspace(client: Any, folder: str | None) -> str:
    """The workspace of a folder (this one unless named)."""
    path = str(Path(folder or os.getcwd()).resolve())
    found = common.call(lambda: client.get("workspaces/folder", folder=path))
    if not found.get("workspace"):
        raise click.ClickException(f"{path} has no Clank workspace: run `clank` in it first")
    return str(found["workspace"])


@board.command()
@click.argument("name")
@click.argument("folder", required=False)
@click.option("--in", "under", default="", help="The subfolder to make it in (figures, notes ...).")
@click.option("--title", default="", help="Its title; default: its name.")
def new(name: str, folder: str | None, under: str, title: str) -> None:
    """Make an empty board, NAME.board; open it in VS Code to work on it."""
    client = common.call(common.connect)
    workspace = _workspace(client, folder)
    made = common.call(lambda: client.post("agents/boards", {"workspace": workspace, "name": name, "folder": under,
                                                             "title": title}))  # fmt: skip
    click.echo(f"Made {made['board']}: open it in VS Code (`clank code`) to work on it with the agent.")


@board.command(name="list")
@click.argument("folder", required=False)
def listed(folder: str | None) -> None:
    """The folder's boards, the newest changed first."""
    client = common.call(common.connect)
    workspace = _workspace(client, folder)
    found = common.call(lambda: client.get("agents/boards", workspace=workspace))["boards"]
    if not found:
        click.echo(f"{workspace} has no board yet: `clank board new NAME` makes one.")
    for each in found:
        click.echo(f"{each['board']}  {each['title']}  ({each['items']} item{'' if each['items'] == 1 else 's'})")


@board.command()
@click.argument("name")
@click.argument("folder", required=False)
def show(name: str, folder: str | None) -> None:
    """A board in words, as the agent reads it."""
    client = common.call(common.connect)
    workspace = _workspace(client, folder)
    click.echo(common.call(lambda: client.get("agents/boards/read", workspace=workspace, board=name))["said"])
