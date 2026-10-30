"""`clank dev` (decision 0149): dev mode, for testing, said, or turned on or off.

On, every cloud provider is asked for any of a model's providers (`data_collection allow`), those that may keep or train
on what they are sent too, whatever its record says, from the next request; off, each provider's record says again. A
client of the API (`GET` and `PUT /runtime/dev`), it prints the service's own words, or JSON with `--json`.
"""

import json

import click

from clank.cli import common


@click.command("dev")
@click.argument("turn", required=False, type=click.Choice(("on", "off")))
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def dev(turn: str | None, as_json: bool) -> None:
    """Dev mode, for testing: on, every cloud provider is asked for any of a model's providers, those that may keep or
    train on what they are sent too (data_collection allow). With no argument, whether it is on."""
    client = common.call(common.connect)
    if turn is None:
        found = common.call(lambda: client.get("runtime/dev"))
    else:
        found = common.call(lambda: client.put("runtime/dev", {"on": turn == "on"}))
    click.echo(json.dumps(found, indent=2) if as_json else found["said"])
