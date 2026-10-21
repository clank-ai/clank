"""`clank cost` (design 0016 §11, §16): what the cloud cost, today and this month against the limits, by session and by
flow, and `clank cost limit` to set the limits. Each is a client of the API (design 0002 §2.15), printing the service's
own words (its cost views' `said`), with `--json`; a limit is sent as typed, and the service refuses it in words.
"""

import json
from functools import partial
from typing import Any

import click

from clank.cli import common
from clank.money import dollars


@click.group(invoke_without_command=True)
@click.option("--today", "shown", flag_value="today", help="Today's spending, against its limit.")
@click.option("--month", "shown", flag_value="month", help="This month's spending, against its limit.")
@click.option("--sessions", "shown", flag_value="sessions", help="Each session's cost, its subagents' with it.")
@click.option("--flows", "shown", flag_value="flows", help="Each flow's cost, and each of its boxes'.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
@click.pass_context
def cost(context: click.Context, shown: str | None, as_json: bool) -> None:
    """What the cloud cost: today and this month against the limits (this computer's days), a pause; by session or
    flow."""
    if context.invoked_subcommand is not None:
        return
    client = common.call(common.connect)
    if shown == "sessions":
        sessions = common.call(lambda: client.get("gateway/cost/sessions"))
        if as_json:
            click.echo(json.dumps(sessions, indent=2))
            return
        for each in sessions:
            click.echo(f"{each['session']}  {each['workspace']}  {each['said']}")
        if not sessions:
            click.echo("No session has used the cloud yet.")
        return
    if shown == "flows":
        found = flows(client)
        if as_json:
            click.echo(json.dumps(found, indent=2))
            return
        for flow, spent in found:
            click.echo(f"{flow}  {spent['said']}")
            for box, each in spent.get("boxes", {}).items():
                click.echo(f"    {box}  {each['said']}")
        if not found:
            click.echo("No flow has used the cloud yet.")
        return
    view = common.call(lambda: client.get("gateway/cost"))
    if as_json:
        click.echo(json.dumps(view, indent=2))
        return
    lines = [view[shown]["said"]] if shown in ("today", "month") else [view["said"], view["limits"]["said"]]
    lines += [found["said"] for found in (view["paused"], view["warned"]) if found]
    click.echo("\n".join(lines))


@cost.command("limit")
@click.option("--day", default=None, metavar="USD|none", help="A day's limit in US dollars, or none.")
@click.option("--month", default=None, metavar="USD|none", help="A month's limit in US dollars, or none.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def limit(day: str | None, month: str | None, as_json: bool) -> None:
    """Set the cloud's cost limits: reached, cloud requests wait until you raise it or the period ends."""
    try:
        body = {key: dollars(value) for key, value in (("day_usd", day), ("month_usd", month)) if value is not None}
    except ValueError as error:
        raise click.UsageError(str(error)) from None
    if not body:
        raise click.UsageError("say --day, --month or both (USD, or none)")
    client = common.call(common.connect)
    view = common.call(lambda: client.put("gateway/cost/limits", body))
    click.echo(json.dumps(view, indent=2) if as_json else view["limits"]["said"])


def flows(client: Any) -> list[tuple[str, dict[str, Any]]]:
    """Each flow that used the cloud, with its cost as the service gives it."""
    found = []
    for flow in common.call(lambda: client.get("flows"))["flows"]:
        view = common.call(partial(client.get, f"flows/{flow['id']}"))
        if view.get("cost"):
            found.append((flow["id"], view["cost"]))
    return found
