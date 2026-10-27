"""The gateway component's commands: `clank gateway status|restart|stop` (design 0004 §2), clients of the API."""

import json
from typing import Any

import click

from clank.cli import common


@click.group()
def gateway() -> None:
    """The gateway: every model request, to the engine of its role's slot."""


@gateway.command()
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def status(as_json: bool) -> None:
    """Whether the gateway runs, where tools reach it (on Linux, its socket too), and which process it is."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get("gateway"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    _say(found)


@gateway.command()
def restart() -> None:
    """Stop the gateway and start it again, with its settings as they are now."""
    client = common.call(common.connect)
    _say(common.call(lambda: client.post("gateway/restart")))


@gateway.command()
def stop() -> None:
    """Stop the gateway (the service starts it again unless its settings say not to)."""
    client = common.call(common.connect)
    click.echo(f"gateway: {common.call(lambda: client.post('gateway/stop'))['stopped']}")


def _say(found: dict[str, Any]) -> None:
    if found["state"] == "running":
        since = f", since {common.local_time(found['since'])}" if found.get("since") else ""
        click.echo(f"gateway: running at {found['url']} (process {found['pid']}{since}); its log: {found['log']}")
        if found.get("socket"):  # on Linux: the edge's way in on Docker Engine (design 0014 §3)
            click.echo(f"gateway: its socket, the edge's way in on Docker Engine: {found['socket']}")
        elif found.get("socket_problem"):
            click.echo(f"gateway: no socket for the edge: {found['socket_problem']}")
        if found.get("problem"):  # a restart whose stop failed: the gateway runs on as it was
            click.echo(f"gateway: {found['problem']}")
    elif found["state"] == "problem":
        click.echo(f"gateway: not running: {found['problem']}")
        raise click.exceptions.Exit(1)
    else:
        click.echo(f"gateway: stopped; it listens at {found['url']} once it runs (`clank gateway restart`)")
