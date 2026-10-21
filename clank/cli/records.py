"""The commands that read and act on what every client sees: `clank events`, `clank questions` (and answering one),
`clank operations` (and canceling or retrying one), `clank records` (every record of every kind).

Each is a client of the API (design 0002 §2.15): readable text by default, JSON with `--json` for scripts and models.
What a command does is recorded as "you (cli)". Without a running service, a command says how to start it.
"""

import json
from typing import Any

import click

from clank.cli import common
from clank.client import ClientError, NotRunning


def _event_line(event: dict[str, Any]) -> str:
    return f"{common.local_time(event['time'])}  {event['summary']}"


@click.command()
@click.option("--follow", "-f", is_flag=True, help="Keep printing events as they happen (Ctrl+C to stop).")
@click.option("--type", "types", multiple=True, help="Only events of this type, such as question.asked (repeatable).")
@click.option("--limit", default=20, show_default=True, help="How many past events to print first.")
@click.option("--json", "as_json", is_flag=True, help="One JSON object per line, for scripts and models.")
def events(follow: bool, types: tuple[str, ...], limit: int, as_json: bool) -> None:
    """Print the newest events, oldest first; with --follow, every new one as it happens."""
    client = common.call(common.connect)
    recent = list(reversed(common.call(lambda: client.get("history", limit=limit, types=",".join(types) or None))))
    for event in recent:
        click.echo(json.dumps(event) if as_json else _event_line(event))
    if not follow:
        return
    after = recent[-1]["id"] if recent else None
    try:
        for message in client.events(after=after, types=list(types) or None):
            if message.name == "connected":
                continue
            if message.name == "reset":
                click.echo(json.dumps({"reset": message.data}) if as_json else "(older events were pruned)")
                continue
            if message.name == "closing":
                click.echo(json.dumps({"closing": message.data}) if as_json else "(the service stopped)")
                return
            click.echo(json.dumps(message.data) if as_json else _event_line(message.data))
    except (NotRunning, ClientError) as error:
        common.fail(error)
    except KeyboardInterrupt:
        return


@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
@click.pass_context
def questions(context: click.Context, as_json: bool) -> None:
    """The questions waiting for your answer (`clank questions answer ID OPTION` answers one)."""
    if context.invoked_subcommand is not None:
        return
    client = common.call(common.connect)
    waiting = common.call(lambda: client.get("questions"))
    if as_json:
        click.echo(json.dumps(waiting, indent=2))
        return
    if not waiting:
        click.echo("No question waits for you.")
        return
    for question in waiting:
        click.echo(f"{question['id']}  {question['title']}")
        click.echo(f"      asked {common.local_time(question['asked'])} by {common.describe(question['asked_by'])}")
        if question["detail"]:
            click.echo(f"      {question['detail']}")
        for option in question["options"]:
            key = option["key"] or option["id"]
            click.echo(f"      {key}  {option['label']}" + (f": {option['effect']}" if option["effect"] else ""))


@questions.command("answer")
@click.argument("id")
@click.argument("option", required=False)
@click.option("--text", default="", help="An answer in words, or a reason given with the option.")
def answer(id: str, option: str | None, text: str) -> None:
    """Answer a question with one of its options (its id or its key), or in words (--text)."""
    client = common.call(common.connect)
    question = common.call(lambda: client.get(f"records/question/{id}"))["values"]
    chosen = next((o for o in question["options"] if option in (o["id"], o["key"])), None)
    answered = common.call(
        lambda: client.post(f"questions/{id}/answer", {"option": chosen["id"] if chosen else option, "text": text})
    )
    shown = chosen["label"] if chosen else answered["answer"]["text"]
    click.echo(f"Answered {id}: {shown}")


@click.group(invoke_without_command=True)
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
@click.pass_context
def operations(context: click.Context, as_json: bool) -> None:
    """The newest operations (`clank operations cancel ID`, `clank operations retry ID`)."""
    if context.invoked_subcommand is not None:
        return
    client = common.call(common.connect)
    found = common.call(lambda: client.get("operations", limit=20))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    if not found:
        click.echo("No operation yet.")
        return
    for operation in found:
        steps = operation["steps"]
        progress = f"{steps[-1]['number']} of {operation['planned_steps']}: {steps[-1]['name']}" if steps else ""
        click.echo(
            f"{operation['id']}  {operation['title']:<28}  {operation['status']:<11}  {progress:<20}  "
            f"{common.local_time(operation['created'])} by {common.describe(operation['started_by'])}"
        )
        if operation["error"]:
            click.echo(f"      {operation['error']}")


@operations.command("cancel")
@click.argument("id")
def cancel(id: str) -> None:
    """Ask a running operation to stop at its next check."""
    client = common.call(common.connect)
    found = common.call(lambda: client.post(f"operations/{id}/cancel"))
    click.echo(f"Asked {found['title']} ({id}) to stop")


@operations.command("retry")
@click.argument("id")
def retry(id: str) -> None:
    """Start an interrupted or failed operation again, when that is safe."""
    client = common.call(common.connect)
    found = common.call(lambda: client.post(f"operations/{id}/retry"))
    click.echo(f"Started {found['title']} again: {found['id']}")


@click.group()
def records() -> None:
    """Every record of every kind, read through the same routes."""


@records.command("kinds")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def kinds(as_json: bool) -> None:
    """Every kind of record, with what it is."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get("kinds"))
    if as_json:
        click.echo(json.dumps([{k: v for k, v in kind.items() if k != "schema"} for kind in found], indent=2))
        return
    for kind in found:
        click.echo(f"{kind['kind']:<12} {kind['sort']:<9} {kind['help']}")


@records.command("list")
@click.argument("kind")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def list_records(kind: str, as_json: bool) -> None:
    """Every record of a kind (the newest ones, for state)."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get(f"records/{kind}"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    for record in found:
        source = f"  ({record['source']})" if "source" in record else ""
        click.echo(f"{record['id']:<16} {record['title']}{source}")


@records.command("show")
@click.argument("kind")
@click.argument("id")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def show(kind: str, id: str, as_json: bool) -> None:
    """One record, every value with its name."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get(f"records/{kind}/{id}"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    click.echo(
        f"{found['kind']} {found['id']}" + (f"  ({found['source']}, {found['file']})" if "source" in found else "")
    )
    for name, value in found["values"].items():
        click.echo(f"  {name}: {json.dumps(value)}")


COMMANDS = [events, questions, operations, records]
