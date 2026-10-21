"""The cloud provider's commands (design 0016 §16): `clank endpoint add|key|list|show|models|preset|check|remove`.

Each is a client of the API (design 0002 §2.15): readable text by default, JSON with `--json`. What each prints is the
service's own words (its views' `said`, the guide's agreement, a refusal's message), so the commands, the console and
the phone's app to come say the same things; no command works out a cost, a consent or a fit itself.

A key is never an argument (design 0016 §4): `clank endpoint key` asks for it without echo, or reads one line of
standard input with `--stdin` for a script, so the shell's history never holds it; it is sent once, in the body of one
call, and printed only by its last four characters. `--stdin` is refused at a terminal, which would echo the key.
"""

import json
import sys
import time
from functools import partial
from typing import Any

import click

from clank.cli import common, follow
from clank.client import Client

ADAPTERS = ("openrouter",)  # the cloud providers Clank has an adapter for (design 0016 §2)


def provider_path(provider: str) -> str:
    """The provider's route."""
    return f"runtime/endpoints/{provider}"


def ended(operation: dict[str, Any]) -> dict[str, Any]:
    """The result of an operation that ended well; else its error said, and exit 1."""
    if operation["status"] != "done":
        click.echo(f"{operation['title']}: {operation.get('error') or operation['status']}")
        raise click.exceptions.Exit(1)
    return dict(operation.get("result") or {})


def agreement(client: Client) -> dict[str, Any]:
    """The guide's agreement step: what goes to the provider, where, and what never goes."""
    guide = common.call(lambda: client.get("runtime/guide"))
    return next(step for step in guide["steps"] if step["id"] == "agreement")


def at_terminal() -> bool:
    """Whether standard input is a terminal (which echoes what is typed into it)."""
    return sys.stdin.isatty()


def read_key(stdin: bool) -> str:
    """The key: one line of standard input piped in (never typed at a terminal, which would echo it), or asked
    without echo."""
    if stdin:
        if at_terminal():
            raise click.UsageError(
                "--stdin reads a key piped in (`clank endpoint key openrouter --stdin < keyfile`); at a terminal it "
                "would show as you type it: leave --stdin out, and the key is asked without echo"
            )
        return sys.stdin.readline().strip()
    return str(click.prompt("Paste your OpenRouter key (it is not shown)", hide_input=True)).strip()


@click.group()
def endpoint() -> None:
    """The cloud provider: its record and agreement, its key (never shown), its models, its presets and its check."""


@endpoint.command("add")
@click.argument("provider", type=click.Choice(ADAPTERS))
@click.option("--agree", is_flag=True, help="Agree to what goes to the provider without being asked (for a script).")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def add(provider: str, agree: bool, as_json: bool) -> None:
    """Add the provider, once you agree to what goes to it; every MCP server you have is marked local only."""
    client = common.call(common.connect)
    if not agree:
        step = agreement(client)
        click.echo("\n\n".join([*step["said"], step["policy"]["deny"]]))
        servers = [server["name"] for server in step["servers"]]
        click.echo(f"\n{step['servers_said']} {', '.join(servers)}" if servers else f"\n{step['servers_said']}")
        if not click.confirm("Agree", default=False):
            click.echo("Nothing was added.")
            raise click.exceptions.Exit(1)
    body = {"id": provider, "adapter": provider, "agree": True}
    added = common.call(lambda: client.post("runtime/endpoints", body))
    if as_json:
        click.echo(json.dumps(added, indent=2))
        return
    click.echo(f"Added {added['title']} ({added['id']}), agreed. Next: clank endpoint key {added['id']}")


@endpoint.command("key")
@click.argument("provider", type=click.Choice(ADAPTERS))
@click.option("--stdin", "from_stdin", is_flag=True, help="Read the key from one line of standard input (scripts).")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models (never the key).")
def key(provider: str, from_stdin: bool, as_json: bool) -> None:
    """Set the provider's key: asked without echo (or one line of standard input); kept only once the provider takes
    it, and shown only by its last four characters."""
    client = common.call(common.connect)
    given = read_key(from_stdin)
    if not given:
        raise click.ClickException("no key was given")
    answer = common.call(partial(client.put, f"{provider_path(provider)}/key", {"key": given}))
    del given  # sent once; nothing here holds it now
    if as_json:
        click.echo(json.dumps(answer, indent=2))
        return
    click.echo(f"OpenRouter took the key; Clank keeps it (ends …{answer['key']['ends']}).")
    click.echo(answer["account"]["said"])


@endpoint.command("list")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def list_endpoints(as_json: bool) -> None:
    """Every cloud provider: its agreement, its key's last four, its presets."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get("runtime/endpoints"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    if not found:
        click.echo("No cloud provider yet: clank endpoint add openrouter, or Add a model in the console")
    for each in found:
        agreed = f"agreed {common.local_time(each['agreed'])}" if each["agreed"] else "not agreed"
        key = f"key ends …{each['key']['ends']}" if each["key"]["set"] else "no key"
        click.echo(f"{each['id']}  {each['title']}  {agreed}  {key}  presets: {', '.join(each['presets']) or 'none'}")


@endpoint.command("show")
@click.argument("provider", type=click.Choice(ADAPTERS))
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def show(provider: str, as_json: bool) -> None:
    """One provider: its record, its key's last four, the key's account as the provider tells it, its last check."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get(provider_path(provider)))
    account = None
    if found["key"]["set"]:
        account = common.call(lambda: client.get(f"{provider_path(provider)}/account"))
    if as_json:
        click.echo(json.dumps({**found, "account": account}, indent=2))
        return
    click.echo(f"{found['title']} ({found['id']}), {found['url']}, {found['file']}")
    click.echo(f"  agreed   {common.local_time(found['agreed']) if found['agreed'] else 'no: nothing loads from it'}")
    click.echo(f"  key      {'ends …' + found['key']['ends'] if found['key']['set'] else 'not set'}")
    click.echo(f"  policy   {(found.get('said') or {}).get('policy') or found['options']}")
    if account is not None:
        click.echo(f"  account  {account['said']}")
    click.echo(f"  presets  {', '.join(found['presets']) or 'none'}")
    check = found["check"]
    if check:
        click.echo(f"  check    {common.local_time(check['time'])}: {'ok' if check['ok'] else 'failed'}")
        for item in check["items"]:
            click.echo(f"    {item['status']:<6}{item['name']:<10}{item['said']}")


@endpoint.command("models")
@click.argument("provider", type=click.Choice(ADAPTERS))
@click.option("--search", default="", help="Only models whose name or id holds this.")
@click.option("--sort", type=click.Choice(("most-popular", "price", "context", "newest")), default="most-popular",
              show_default=True, help="The order.")  # fmt: skip
@click.option("--free", is_flag=True, help="Only the free models (their limits said).")
@click.option("--all", "every", is_flag=True, help="Every model, those without tool calls too (the agent needs them).")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def models(provider: str, search: str, sort: str, free: bool, every: bool, as_json: bool) -> None:
    """The provider's live list of models, read with its key."""
    client = common.call(common.connect)
    found = common.call(
        lambda: client.get(f"{provider_path(provider)}/models", search=search, sort=sort, free=free, all=every)
    )
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    click.echo(found["said"])
    for model in found["models"]:
        click.echo(f"{model['said']['name']}  {model['id']}\n    {model['said']['facts']}")


@endpoint.command("preset")
@click.argument("provider", type=click.Choice(ADAPTERS))
@click.argument("model")
@click.option("--title", default=None, help="Its title (the service's, from the model, unless given).")
@click.option("--context", default=None, help="Its context, in tokens (the model's window unless given).")
@click.option("--output", default=None, help="Its most output, in tokens.")
@click.option("--reasoning", default=None, help="Its thinking effort: default, or one the model takes.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def preset(
    provider: str,
    model: str,
    title: str | None,
    context: str | None,
    output: str | None,
    reasoning: str | None,
    as_json: bool,
) -> None:
    """Write a cloud preset for one of the provider's models, then test it with one short request."""
    client = common.call(common.connect)
    given = {"title": title, "context": context, "max_output": output, "reasoning": reasoning}
    body = {"model": model, **{key: value for key, value in given.items() if value is not None}}
    written = common.call(lambda: client.post(f"{provider_path(provider)}/presets", body))
    if not as_json:
        click.echo(f"Wrote {written['title']} ({written['id']}): {written['provider']} · {written['model']}")
    operation = common.call(lambda: client.post(f"{provider_path(provider)}/test", {"preset": written["id"]}))
    result = ended(follow.follow(client, operation) if not as_json else wait(client, operation))
    if as_json:
        click.echo(json.dumps({"preset": written, "test": result}, indent=2))
    else:
        click.echo(f"Its test: {result['said']}")
    if not result.get("ok"):
        raise click.exceptions.Exit(1)


@endpoint.command("check")
@click.argument("provider", type=click.Choice(ADAPTERS))
@click.option("--model", default=None, help="The model the short request and the tool call go to.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def check(provider: str, model: str | None, as_json: bool) -> None:
    """Check the provider: its key, its account, its models, one short request, a tool call; each item with why."""
    client = common.call(common.connect)
    body = {"model": model} if model else {}
    operation = common.call(lambda: client.post(f"{provider_path(provider)}/check", body))
    result = ended(follow.follow(client, operation) if not as_json else wait(client, operation))
    if as_json:
        click.echo(json.dumps(result, indent=2))
        return
    for item in result["items"]:
        click.echo(f"  {item['status']:<6}{item['name']:<10}{item['said']}")
    if not result["ok"]:
        raise click.exceptions.Exit(1)


@endpoint.command("remove")
@click.argument("provider", type=click.Choice(ADAPTERS))
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def remove(provider: str, as_json: bool) -> None:
    """Remove the provider with its key; refused while a preset names it or the main slot runs one."""
    client = common.call(common.connect)
    found = common.call(lambda: client.delete(provider_path(provider)))
    click.echo(json.dumps(found, indent=2) if as_json else f"Removed {found['removed']}, with its key")


def wait(client: Client, operation: dict[str, Any]) -> dict[str, Any]:
    """An operation once it ended, followed without printing (for `--json`)."""
    while True:
        values: dict[str, Any] = common.call(lambda: client.get(f"records/operation/{operation['id']}"))["values"]
        if values["status"] in follow.FINISHED:
            return values
        time.sleep(follow.POLL_SECONDS)
