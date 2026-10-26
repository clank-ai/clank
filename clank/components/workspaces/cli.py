"""The workspaces component's commands: `clank docker status|start|stop`, and `clank workspace
list|open|setup|stop|remove` (design 0004 §1, §10): open and setup are this folder unless one is named, stop this
folder's workspace unless one is named.

Each is a client of the API (design 0002 §2.15): readable text by default, JSON with `--json`. Start and stop follow
their operation step by step; when stopping needs an answer (containers Clank did not start are running), the
question is asked at the terminal, unless `--yes` answers it. A command that did not do what it was asked ends with 1.
"""

import json
import os
from functools import partial
from pathlib import Path
from typing import Any

import click

from clank.cli import common, follow
from clank.components.workspaces.service import image_name

OWNERS = {"clank": "Clank's", "other": "other"}


@click.group()
def docker() -> None:
    """Docker, through Clank: its status, and starting and stopping it."""


@docker.command()
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def status(as_json: bool) -> None:
    """Docker's state and versions, and each running container with whose it is."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get("docker", refresh=True))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    head = f"{found['label']} {found['version']}".strip() + f" · {found['state']}"
    click.echo(head + (f" · engine {found['engine']}" if found["engine"] else ""))
    said = found["summary"].split(" · ", 2)[-1] if found["state"] == "running" else found["detail"]
    if said:  # a stopped Docker has no detail: its state says it all
        click.echo(f"  {said}")
    running = [container for container in found["containers"] if container["state"] == "running"]
    width = max((len(container["name"]) for container in running), default=0)
    for container in running:
        click.echo(
            f"  {container['name'].ljust(width)}  {OWNERS[container['owner']]:<9}  {container['status']:<16}  "
            f"{image_name(container['image'])}"
        )


@docker.command()
def start() -> None:
    """Start Docker and wait until its engine answers."""
    client = common.call(common.connect)
    operation = common.call(lambda: client.post("docker/start"))
    _report(follow.follow(client, operation))


@docker.command()
@click.option(
    "--yes", is_flag=True, help="Stop even when containers Clank did not start are running (answers the question)."
)
def stop(yes: bool) -> None:
    """Stop Docker and every container in it; asks first when containers Clank did not start are running."""
    client = common.call(common.connect)
    operation = common.call(lambda: client.post("docker/stop"))
    _report(follow.follow(client, operation, answer="stop" if yes else None))


def _report(operation: dict[str, Any]) -> None:
    if operation["status"] == "done":
        docker = (operation["result"] or {}).get("docker") or {}
        click.echo(docker.get("summary") or f"{operation['title']}: done")
        return
    click.echo(f"{operation['title']}: {operation['error'] or operation['status']}")
    raise click.exceptions.Exit(1)


@click.group()
def workspace() -> None:
    """The folders agents work in, each in a container of its own; removing one never touches its folder."""


@workspace.command("list")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def list_workspaces(as_json: bool) -> None:
    """Each workspace, its container's state and its folder."""
    client = common.call(common.connect)
    rows = common.call(lambda: client.get("workspaces"))
    if as_json:
        click.echo(json.dumps(rows, indent=2))
        return
    if not rows:
        click.echo("No workspace yet: `clank workspace open` in a folder makes one.")
        return
    width = max(len(row["name"]) for row in rows)
    states = max(len(row["state"]) for row in rows)
    for row in rows:
        click.echo(f"{row['name'].ljust(width)}  {row['state'].ljust(states)}  {row['path']}")


@workspace.command("open")
@click.argument("folder", required=False)
@click.option("--yes", is_flag=True, help="Build Clank's sandbox image without asking first, when it is not built.")
def open_workspace(folder: str | None, yes: bool) -> None:
    """Open a folder (this one unless named) as a workspace: its container runs, with the folder at /workspace."""
    client = common.call(common.connect)
    body = {"folder": str(Path(folder or os.getcwd()).resolve()), "yes": yes}
    result = _done(follow.follow(client, common.call(lambda: client.post("workspaces/open", body))))
    click.echo(
        f"{result['workspace']}: its container runs ({result['container']}), with {result['folder']} at /workspace"
    )


@workspace.command("allow")
@click.argument("folder")
@click.option("--cloud", "bound", flag_value="cloud", help="Let its agent use a cloud model.")
@click.option("--local", "bound", flag_value="local", help="Keep it on this machine: never the cloud model.")
@click.option("--host", "hosts", multiple=True, help="A host its agent may reach through Clank's proxy: a name "
              "(pypi.org) or a suffix (.arxiv.org); may be given more than once.")  # fmt: skip
@click.option("--no-host", "no_hosts", multiple=True, help="A host its agent may not reach any more.")
@click.option("--set", "sets", multiple=True, help="A named set of hosts its agent may reach (`clank workspace sets` "
              "lists them: python, papers, code, data, docs); may be given more than once.")  # fmt: skip
@click.option("--no-set", "no_sets", multiple=True, help="A named set its agent may not reach any more.")
@click.option("--yes", is_flag=True, help="Change it without asking first.")
def allow(
    folder: str,
    bound: str | None,
    hosts: tuple[str, ...],
    no_hosts: tuple[str, ...],
    sets: tuple[str, ...],
    no_sets: tuple[str, ...],
    yes: bool,
) -> None:
    """Where a workspace's requests may go: the cloud model too, or this machine only (design 0016 §9; asked first,
    in the service's words, unless `--yes`); and which internet hosts its agent may reach through Clank's proxy
    (design 0024 §1), each allowed with `--host` or taken back with `--no-host`, or a named set of them (§5) with
    `--set` and `--no-set`."""
    if bound is None and not hosts and not no_hosts and not sets and not no_sets:
        raise click.UsageError("say --cloud, --local, --host or --no-host (or --set, --no-set)")
    client = common.call(common.connect)
    path = str(Path(folder).resolve())
    view = common.call(lambda: client.get("workspaces/folder", folder=path))
    name = view.get("workspace")
    if not name:
        raise click.ClickException(f"{path} has no workspace yet: `clank workspace open` or This folder opens one")
    if hosts or no_hosts or sets or no_sets:
        changed = view
        for host, allowed in [*((each, True) for each in hosts), *((each, False) for each in no_hosts)]:
            body = {"host": host, "allow": allowed}
            changed = common.call(partial(client.post, f"workspaces/{name}/hosts", body))
        for named, allowed in [*((each, True) for each in sets), *((each, False) for each in no_sets)]:
            body = {"set": named, "allow": allowed}
            changed = common.call(partial(client.post, f"workspaces/{name}/sets", body))
        reached = ", ".join(sorted(changed.get("hosts") or {}))
        click.echo(f"{name}: its agent may reach {reached}" if reached else f"{name}: its agent reaches no host")
        if bound is None:
            return
    if not yes:
        click.echo((view.get("cloud_confirm") or {}).get("allow" if bound == "cloud" else "local", ""))
        if not click.confirm("Change it", default=False):
            click.echo("Nothing was changed.")
            raise click.exceptions.Exit(1)
    changed = common.call(lambda: client.post(f"workspaces/{name}/cloud", {"allow": bound == "cloud"}))
    click.echo(f"{name}: {changed.get('cloud_said') or changed['models']}")


@workspace.command("sets")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def list_sets(as_json: bool) -> None:
    """The named sets of hosts an agent may be allowed (design 0024 §5): each with its hosts and what it opens; the
    file config/network-sets.json in your Clank home holds them, yours to change."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get("workspaces/network-sets"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    for name, each in found.items():
        click.echo(f"{name}: {', '.join(each['hosts'])}")
        if each.get("for"):
            click.echo(f"    {each['for']}")
    click.echo("Allow one with: clank workspace allow FOLDER --set NAME")


@workspace.command("setup")
@click.argument("folder", required=False)
@click.option("--command", default="", help="The command that installs it, kept for next time (default: the kept one, "
              "else proposed from the folder's pyproject.toml or requirements.txt).")  # fmt: skip
@click.option("--yes", is_flag=True, help="Install without asking first.")
def setup_workspace(folder: str | None, command: str, yes: bool) -> None:
    """Install a workspace's own software (this folder's unless one is named) into its home, where its agent finds it;
    it runs in a container of its own that reaches the internet."""
    client = common.call(common.connect)
    body = {"folder": str(Path(folder or os.getcwd()).resolve()), "command": command, "yes": yes}
    operation = common.call(lambda: client.post("workspaces/setup", body))
    result = _done(follow.follow(client, operation, answer="install" if yes else None))
    if result.get("installed"):
        click.echo(f"{result['workspace']}: installed with {result['command']}")
    else:
        click.echo(
            f"{result['workspace']}: nothing to install (no pyproject.toml or requirements.txt; --command gives one)"
        )


@workspace.command("stop")
@click.argument("name", required=False)
def stop_workspace(name: str | None) -> None:
    """Stop a workspace's container (this folder's workspace unless one is named)."""
    client = common.call(common.connect)
    chosen = name or _here(common.call(lambda: client.get("workspaces")))
    result = _done(follow.follow(client, common.call(lambda: client.post(f"workspaces/{chosen}/stop"))))
    click.echo(f"{result['workspace']}: {result['container']} stopped")


@workspace.command("remove")
@click.argument("name")
@click.option("--yes", is_flag=True, help="Remove it without asking first.")
def remove_workspace(name: str, yes: bool) -> None:
    """Remove a workspace's container, its home (its agent's settings and sessions) and its record; never its folder."""
    client = common.call(common.connect)
    operation = common.call(lambda: client.post(f"workspaces/{name}/remove", {"yes": yes}))
    result = _done(follow.follow(client, operation))
    click.echo(f"{result['workspace']} is removed; {result['folder']} is as it was")


def _here(rows: list[dict[str, Any]]) -> str:
    """The workspace of the folder the command runs in."""
    here = os.path.normcase(str(Path.cwd().resolve()))
    for row in rows:
        if os.path.normcase(row["path"]) == here:
            return str(row["name"])
    click.echo(f"{Path.cwd()} is no workspace: name one (`clank workspace list` shows them)")
    raise click.exceptions.Exit(1)


def _done(operation: dict[str, Any]) -> dict[str, Any]:
    """The result of an operation that ended well; else its error said, and exit 1."""
    if operation["status"] != "done":
        click.echo(f"{operation['title']}: {operation['error'] or operation['status']}")
        raise click.exceptions.Exit(1)
    return dict(operation.get("result") or {})
