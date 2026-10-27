"""The gateway component's commands for the agent's internet (design 0024 §4): `clank network log` (the newest
exchanges, one line each, and today's bytes by host) and `clank network hosts` (the hosts allowed per workspace),
clients of the API."""

import json
from typing import Any

import click

from clank.cli import common


@click.group()
def network() -> None:
    """The agent's internet exchanges through Clank's proxy, and the hosts allowed (design 0024)."""


@network.command()
@click.option("--limit", default=30, show_default=True, help="How many of the newest exchanges to show.")
@click.option("--workspace", default="", help="One workspace's exchanges only.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def log(limit: int, workspace: str, as_json: bool) -> None:
    """The newest exchanges (when, workspace, host, status, bytes, time, why), and today's bytes by host."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get("gateway/network/log", limit=limit, workspace=workspace))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    exchanges = found.get("exchanges") or []
    if not exchanges:
        click.echo("No exchange yet: the agent reached no host through the proxy.")
    for each in exchanges:
        click.echo(exchange_line(each))
    by_host = found.get("by_host") or {}
    if by_host:
        click.echo("Today, by host:")
        for host, summed in by_host.items():
            count = summed.get("exchanges", 0)
            click.echo(
                f"  {host}: {bytes_said(summed.get('received', 0))} received, "
                f"{bytes_said(summed.get('sent', 0))} sent, {count} exchange{'s' if count != 1 else ''}"
            )


@network.command()
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def hosts(as_json: bool) -> None:
    """The hosts each workspace's agent may reach, with when and how each was allowed."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get("gateway/network/hosts"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    if not found:
        click.echo("No workspace yet.")
    for workspace, allowed in found.items():
        if allowed:
            click.echo(f"{workspace}: {', '.join(sorted(allowed))}")
            for host, how in sorted(allowed.items()):
                click.echo(f"    {host}: {how}")
        else:
            click.echo(f"{workspace}: no host (clank workspace allow FOLDER --host NAME, or --set NAME)")


def exchange_line(each: dict[str, Any]) -> str:
    """One exchange on a line: when (this computer's time), workspace, method and target, status (words when there is
    none), bytes each way, time, why."""
    when = common.local_time(str(each["time"])) if each.get("time") else ""
    target = f"{each.get('host')}{each.get('path') or ''}"
    size = f"{bytes_said(each.get('received') or 0)} in, {bytes_said(each.get('sent') or 0)} out"
    why = f"  {each['why']}" if each.get("why") else ""
    status = "no status" if each.get("status") is None else str(each["status"])
    return (
        f"{when}  {each.get('workspace')}  {each.get('method')} {target}  {status}  {size}  "
        f"{each.get('seconds') or 0:g} s{why}"
    )


def bytes_said(count: int) -> str:
    """A count of bytes in B, KB or MB."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f} MB"
    if count >= 1_000:
        return f"{count / 1_000:.0f} KB"
    return f"{count} B"
