"""The notion component's commands (design 0010 §9): `clank notion connect` (asks for the integration's secret without
showing it), `clank notion status`, `clank notion databases` (what the integration can see) and `clank notion
disconnect`; and the agent's batches: `clank notion batches`,
`show` (with the comments and the agent's answers), `approve` (all, or `--only` some), `reject` (with a reason),
`comment` and `send-back`: the backup of VS Code's review.
Each is a client of the API (design 0002 §2.15): readable text, or JSON with `--json`."""

import json
from typing import Any

import click

from clank.cli import common


@click.group()
def notion() -> None:
    """Notion: connect Clank with your integration's secret, see what it reaches, disconnect."""


@notion.command()
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def connect(as_json: bool) -> None:
    """Connect Clank to Notion: paste your integration's secret when asked (it is not shown)."""
    secret = click.prompt("Your Notion integration's secret", hide_input=True)
    client = common.connect()
    found = common.call(lambda: client.post("notion/connect", {"secret": secret}))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    click.echo(f"Connected to Notion: the integration {found['integration']}, in {found['workspace']}.")


@notion.command()
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def status(as_json: bool) -> None:
    """Whether Clank is connected to Notion, and as what."""
    client = common.connect()
    found = common.call(lambda: client.get("notion/status"))
    click.echo(json.dumps(found, indent=2) if as_json else _said(found))


@notion.command()
def disconnect() -> None:
    """Remove Clank's Notion secret (the integration itself stays in Notion until you delete it there)."""
    client = common.connect()
    common.call(lambda: client.delete("notion/connect"))
    click.echo("Disconnected from Notion: the secret is removed.")


@notion.command()
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def databases(as_json: bool) -> None:
    """The databases shared with Clank's integration, with their properties: what the agent can read."""
    client = common.connect()
    found = common.call(lambda: client.get("notion/databases"))["databases"]
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    for database in found:
        properties = ", ".join(_property(each) for each in database["properties"])
        click.echo(f"{database['name']}: {properties}")
    if not found:
        click.echo("No database is shared with Clank's integration yet (docs/notion-setup.md, part 2).")


def _property(described: dict[str, Any]) -> str:
    if described["type"] == "relation":
        return f"{described['name']} (relation → {described['points_to']})"
    return f"{described['name']} ({described['type']})"


@notion.command()
@click.option("--workspace", default=None, help="Only this workspace's batches.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def batches(workspace: str | None, as_json: bool) -> None:
    """The agent's batches of proposals, newest first."""
    client = common.connect()
    found = common.call(lambda: client.get("notion/batches", workspace=workspace))["batches"]
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    for batch in found:
        click.echo(
            f"{batch['id']}  {batch['state']}  {batch['workspace']}: {_counts(batch['counts'])}: {batch['summary']}"
        )
    if not found:
        click.echo("No batch yet: the agent stages its proposals for Notion in one.")


@notion.command()
@click.argument("batch")
@click.option("--json", "as_json", is_flag=True, help="Print JSON.")
def show(batch: str, as_json: bool) -> None:
    """A batch's proposals: what each would write."""
    client = common.connect()
    found = common.call(lambda: client.get(f"notion/batches/{batch}"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    click.echo(f"{found['id']}  {found['state']}  {found['workspace']}: {found['summary']}")
    for proposal in found["proposals"]:
        label = {"entry": "new", "change": "change", "removal": "remove"}[proposal["kind"]]
        line = f"{proposal['id']}  {label:<7}  {proposal['database_name']}: {proposal['title']}"
        what = [f"{field['name']} {field['was']} → {field['now']}" for field in proposal["fields"]]
        if proposal["kind"] == "change":
            line += f" ({'; '.join(what + (['its page'] if proposal['changes'] else []))})"
        click.echo(line)
        for note in proposal["notes"]:
            click.echo(f"    {note}")
        result = proposal.get("result")
        if result and result.get("error"):
            click.echo(f"    not written: {result['error']}")
        elif result:
            done = "" if result["written"] else f" in part ({', '.join(proposal['done']['parts'])})"
            click.echo(f"    written{done}: {result.get('url', '')}")
    for comment in found.get("comments") or []:
        on = ", ".join(str(each) for each in (comment["proposal"], comment["field"]) if each) or "the batch"
        if comment["block"] is not None:
            on += f", block {comment['block']}"
        state = "answered" if comment["state"] == "answered" else "sent" if comment["sent"] else "not sent yet"
        click.echo(f'    {comment["id"]} on {on} ({state}): "{comment["text"]}"')
        for reply in comment["replies"]:
            click.echo(f'        {reply["by"]}: "{reply["text"]}"')


@notion.command()
@click.argument("batch")
@click.option("--only", default="", help="Only these proposals, as p1,p2.")
def approve(batch: str, only: str) -> None:
    """Write a batch's proposals to Notion (all of them, or --only some)."""
    client = common.connect()
    chosen = [each.strip() for each in only.split(",") if each.strip()] or None
    found = common.call(lambda: client.post(f"notion/batches/{batch}/approve", {"proposals": chosen}))
    click.echo(f"{found['written']} written, {found['left']} left staged" + (
        f", {found['failed']} could not be (`clank notion show {batch}` says why)" if found["failed"] else ""
    ))  # fmt: skip


@notion.command()
@click.argument("batch")
@click.argument("text")
@click.option("--on", "on", default="", help="What it is on: p2, p2:Year (a property), p2:block:3; none: the batch.")
def comment(batch: str, text: str, on: str) -> None:
    """Comment on a batch for its agent (`send-back` sends the comments)."""
    proposal, field, block = _place(on)
    client = common.connect()
    found = common.call(lambda: client.post(
        f"notion/batches/{batch}/comments", {"text": text, "proposal": proposal, "field": field, "block": block}
    ))  # fmt: skip
    click.echo(f"{found['id']} is kept with {batch}: `clank notion send-back {batch}` sends it to the agent.")


def _place(on: str) -> tuple[str | None, str | None, int | None]:
    parts = [each.strip() for each in on.split(":")] if on.strip() else []
    if len(parts) == 3 and parts[1] == "block" and parts[2].isdigit():
        return parts[0], None, int(parts[2])
    if len(parts) == 2:
        return parts[0], parts[1], None
    if len(parts) == 1:
        return parts[0], None, None
    if not parts:
        return None, None, None
    raise click.BadParameter("give p2, p2:Year or p2:block:3", param_hint="--on")


@notion.command(name="send-back")
@click.argument("batch")
def send_back(batch: str) -> None:
    """Send a batch back to its agent with your comments, to revise it."""
    client = common.connect()
    found = common.call(lambda: client.post(f"notion/batches/{batch}/return"))
    where = "a new session" if found["sent_to"]["new"] else f"session {found['sent_to']['session']}"
    click.echo(f"{batch} is sent back to the agent ({where}); its next revision comes back for review.")


@notion.command()
@click.argument("batch")
@click.option("--reason", prompt="Why", help="Why, for the agent.")
def reject(batch: str, reason: str) -> None:
    """Reject a batch: nothing of it is written."""
    client = common.connect()
    common.call(lambda: client.post(f"notion/batches/{batch}/reject", {"reason": reason}))
    click.echo(f"{batch} is rejected: nothing of it is written.")


def _counts(counts: dict[str, int]) -> str:
    named = [f"{counts['new']} new", f"{counts['changed']} changed", f"{counts['removed']} removed"]
    return ", ".join(each for each, count in zip(named, counts.values(), strict=True) if count) or "nothing"


def _said(found: dict[str, Any]) -> str:
    if not found["connected"]:
        return f"Notion: {found['problem']}"
    ends = found["secret"]["ends"]
    line = f"Notion: connected as {found['integration']}, in {found['workspace']} (secret ending {ends})"
    return line + (f"\n  but asking it now failed: {found['problem']}" if found["problem"] else "")
