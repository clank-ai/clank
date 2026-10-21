"""The tools component's commands: `clank mcp add|add-json|list|get|remove|check`, the way other harnesses add MCP
servers (`claude mcp add`, `codex mcp add`; the M8.0 plan), and `clank mcp allow|hold NAME`, which give a server to
this folder's agent or hold it back (`check --workspace` starts it where that agent will; design 0004 §10).

`clank mcp add [options] NAME -- COMMAND [ARGS...]` adds a server Clank starts (stdio): everything after `--` is the
server's own, so its options are never taken for Clank's; without `--`, the first word after the name is its command,
and the words after it that are no option of Clank's go with it. `clank mcp add --transport http NAME URL` adds a
remote one (a URL alone says http). `-e KEY=VALUE` gives it an environment variable and `-H "Name: value"` a header,
kept as secrets for your servers (`--scope user`, the default) and written into the current folder's `.mcp.json` for a
project's (`--scope project`), as that file holds them. `add-json NAME JSON` takes an entry as `.mcp.json` holds one.
Each command is a client of the API (design 0002 §2.15): readable text, or JSON with `--json`; the current folder is
the project whose `.mcp.json` is read.
"""

import json
import os
from typing import Any

import click

from clank.cli import common, follow
from clank.client import ClientError, NotRunning

SCOPES = click.Choice(["user", "project"])


@click.group()
def mcp() -> None:
    """MCP servers: add, list, show, check and remove them, as other harnesses do; allow or hold one for this folder."""


@mcp.command(context_settings={"ignore_unknown_options": True})
@click.option(
    "-t", "--transport", type=click.Choice(["stdio", "http", "sse"]), default=None,
    help="stdio: a program Clank starts (the default); http or sse: a server listening at a URL.",
)  # fmt: skip
@click.option("-e", "--env", "env", multiple=True, metavar="KEY=VALUE", help="An environment variable (repeatable).")
@click.option("-H", "--header", "headers", multiple=True, metavar="'NAME: VALUE'", help="A header (repeatable).")
@click.option("-s", "--scope", type=SCOPES, default="user", help="user: yours, everywhere; project: ./.mcp.json.")
@click.option("--local", "local", flag_value="local", default=None,
              help="Local only: never offered to a cloud model (design 0016 §10).")  # fmt: skip
@click.option("--cloud-ok", "local", flag_value="cloud", help="It may be offered to a cloud model.")
@click.argument("name")
@click.argument("command", nargs=-1, required=True, type=click.UNPROCESSED)
def add(transport: str | None, env: tuple[str, ...], headers: tuple[str, ...], scope: str, local: str | None,
        name: str, command: tuple[str, ...]) -> None:  # fmt: skip
    """Add an MCP server: `clank mcp add NAME -- COMMAND [ARGS...]`, or `clank mcp add -t http NAME URL`."""
    first = command[0]
    if first.startswith("-"):
        raise click.UsageError(
            f"the server's command cannot start with '-' ({first}): put the command after --, as in "
            f"`clank mcp add {name} -- {first.lstrip('-')}`"
        )
    if transport is None:
        transport = "http" if first.startswith(("http://", "https://")) else "stdio"
    if transport == "stdio":
        if headers:
            raise click.UsageError("-H gives a header to a server at a URL (--transport http or sse)")
        entry: dict[str, Any] = {"type": "stdio", "command": first, "args": list(command[1:]), "env": _pairs(env, "=")}
    else:
        if env:
            raise click.UsageError("-e gives an environment variable to a server Clank starts (stdio)")
        if len(command) != 1:
            raise click.UsageError(f"an {transport} server is given by its URL alone")
        entry = {"type": transport, "url": first, "headers": _pairs(headers, ":")}
    _added(_post(name, scope, entry, _local_only(name, local)))


@mcp.command("add-json")
@click.option("-s", "--scope", type=SCOPES, default="user", help="user: yours, everywhere; project: ./.mcp.json.")
@click.argument("name")
@click.argument("entry")
def add_json(scope: str, name: str, entry: str) -> None:
    """Add an MCP server from its entry as .mcp.json holds one: '{"command": "...", "args": [...], "env": {...}}'."""
    try:
        parsed = json.loads(entry)
    except ValueError as error:
        raise click.UsageError(f"the entry is not JSON: {error}") from error
    _added(_post(name, scope, parsed))


@mcp.command("list")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def list_(as_json: bool) -> None:
    """Every MCP server: yours, then this folder's project's (.mcp.json)."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get("mcp/servers", folder=os.getcwd()))["servers"]
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    if not found:
        click.echo("No MCP servers yet: `clank mcp add NAME -- COMMAND [ARGS...]` adds one.")
        return
    width = max(len(server["name"]) for server in found)
    for server in found:
        click.echo(f"{server['name'].ljust(width)}  {server['scope']:<7}  {server['transport']:<5}  {_how(server)}")


@mcp.command()
@click.option("-s", "--scope", type=SCOPES, default=None, help="Which one, when the name is in both places.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
@click.argument("name")
def get(scope: str | None, as_json: bool, name: str) -> None:
    """One MCP server: how it is started or reached, and its secrets (by name and last four characters)."""
    client = common.call(common.connect)
    server = common.call(lambda: client.get(f"mcp/servers/{name}", folder=os.getcwd(), scope=scope))
    if as_json:
        click.echo(json.dumps(server, indent=2))
        return
    click.echo(f"{server['name']}  ({_place(server['scope'])}: {server['file']})")
    click.echo(f"  {server['transport']}: {_how(server)}")
    for secret in server["secrets"]:
        click.echo(f"  {secret['name']}: set {common.local_time(secret['set'])}, ends in {secret['ends']}")
    for name_ in server["env"] if server["scope"] == "project" else []:
        click.echo(f"  env {name_}: in {server['file']}")


@mcp.command()
@click.option("-s", "--scope", type=SCOPES, default=None, help="Which one, when the name is in both places.")
@click.argument("name")
def remove(scope: str | None, name: str) -> None:
    """Remove an MCP server, with its secrets."""
    client = common.call(common.connect)
    gone = common.call(lambda: client.delete(f"mcp/servers/{name}", folder=os.getcwd(), scope=scope))
    click.echo(f"Removed {gone['name']} from {_place(gone['scope'])}.")


@mcp.command()
@click.option("-s", "--scope", type=SCOPES, default=None, help="Which one, when the name is in both places.")
@click.option("--seconds", type=float, default=30.0, show_default=True, help="How long it may take to answer.")
@click.option(
    "--workspace", "in_workspace", is_flag=True, help="Start it in this folder's workspace, as its agent would."
)
@click.argument("name")
def check(scope: str | None, seconds: float, in_workspace: bool, name: str) -> None:
    """Start (or reach) an MCP server, ask it what it is and what tools it offers, and end it."""
    client = common.call(common.connect)
    body = {"folder": os.getcwd(), "scope": scope, "seconds": seconds}
    if in_workspace:
        body["workspace"] = _workspace_here(client)
    operation = follow.follow(client, common.call(lambda: client.post(f"mcp/servers/{name}/check", body)))
    if operation["status"] != "done":
        click.echo(f"{operation['title']}: {operation['error'] or operation['status']}")
        raise click.exceptions.Exit(1)
    found = operation["result"]
    click.echo(f"{name}: {found['name']} {found['version']}, protocol {found['protocol']}, {len(found['tools'])} tools")
    for tool in found["tools"]:
        click.echo(f"  {tool['name']}: {tool['description'].splitlines()[0] if tool['description'] else ''}")


@mcp.command()
@click.argument("name")
def allow(name: str) -> None:
    """Give an MCP server to this folder's agent: one of yours held back from it, or one of the folder's own
    (.mcp.json), allowed as its entry is now."""
    _give(name, True)


@mcp.command()
@click.argument("name")
def hold(name: str) -> None:
    """Hold an MCP server back from this folder's agent (yours stay yours; the folder's .mcp.json is not changed)."""
    _give(name, False)


def _give(name: str, given: bool) -> None:
    client = common.call(common.connect)
    workspace = _workspace_here(client)
    row = common.call(lambda: client.post("agents/servers", {"workspace": workspace, "name": name, "given": given}))
    if row["given"]:
        click.echo(f"{workspace}'s agent gets {name} ({row['shown']}) when it next starts.")
    else:
        click.echo(f"{workspace}'s agent does not get {name}: {row['why']}.")


def _workspace_here(client: Any) -> str:
    """The workspace of the folder the command runs in."""
    view = common.call(lambda: client.get("workspaces/folder", folder=os.getcwd()))
    if not view["workspace"]:
        click.echo(f"{os.getcwd()} is no workspace yet: `clank workspace open` makes it one")
        raise click.exceptions.Exit(1)
    return str(view["workspace"])


def _local_only(name: str, local: str | None) -> bool | None:
    """Whether a server added is local only: as told, else asked when a cloud provider is agreed (in the service's
    words), else not said."""
    if local is not None:
        return local == "local"
    client = common.call(common.connect)
    try:
        agreed = any(each["agreed"] for each in client.get("runtime/endpoints"))
    except (ClientError, NotRunning):
        return None  # a service without the cloud's routes
    if not agreed:
        return None
    step = next(step for step in common.call(lambda: client.get("runtime/guide"))["steps"] if step["id"] == "agreement")
    return bool(click.confirm(f"Mark {name} {step['marks']['local']}", default=True))


@mcp.command("local")
@click.argument("name")
@click.option("--off", is_flag=True, help="It may be offered to a cloud model again.")
def local_only(name: str, off: bool) -> None:
    """Mark an MCP server local only, never offered to a cloud model (design 0016 §10), or not (`--off`)."""
    client = common.call(common.connect)
    found = common.call(lambda: client.put(f"mcp/servers/{name}/local", {"local_only": not off}))
    click.echo(f"{name}: {found.get('local_said') or ('local only' if found['local_only'] else 'may go to the cloud')}")


def _post(name: str, scope: str, entry: dict[str, Any], local_only: bool | None = None) -> dict[str, Any]:
    client = common.call(common.connect)
    body: dict[str, Any] = {"name": name, "scope": scope, "folder": os.getcwd(), "entry": entry}
    if local_only is not None:
        body["local_only"] = local_only
    added: dict[str, Any] = common.call(lambda: client.post("mcp/servers", body))
    return added


def _added(server: dict[str, Any]) -> None:
    click.echo(f"Added {server['name']} to {_place(server['scope'])} ({server['transport']}: {_how(server)}).")
    click.echo(f"Check it with `clank mcp check {server['name']}`.")


def _pairs(given: tuple[str, ...], sign: str) -> dict[str, str]:
    found = {}
    for pair in given:
        key, said, value = pair.partition(sign)
        if not said or not key.strip():
            raise click.UsageError(f"{pair!r} is not {'KEY=VALUE' if sign == '=' else 'NAME: VALUE'}")
        found[key.strip()] = value.strip() if sign == ":" else value
    return found


def _how(server: dict[str, Any]) -> str:
    if server["transport"] == "stdio":
        return " ".join([server["command"], *server["args"]])
    return str(server["url"])


def _place(scope: str) -> str:
    return "your servers" if scope == "user" else "this project's .mcp.json"
