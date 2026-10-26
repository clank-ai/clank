"""The remote component's commands: `clank remote status|on|off|pair [NAME]|revoke ID` (design 0005 §5), each a client
of the local API."""

import json
from typing import Any

import click

from clank.cli import common
from clank.components.remote.qr import qr_lines


@click.group()
def remote() -> None:
    """The phone page: whether it is on, turning it on or off, pairing a device, revoking one."""


@remote.command()
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def status(as_json: bool) -> None:
    """Whether the phone page is on and where, and the paired devices."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get("remote"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    _show(found)


@remote.command()
def on() -> None:
    """Publish the phone page on your tailnet (it applies within a few seconds)."""
    client = common.call(common.connect)
    _show(common.call(lambda: client.post("remote/switch", {"on": True})))


@remote.command()
def off() -> None:
    """Stop publishing the phone page: nothing listens for the phone."""
    client = common.call(common.connect)
    _show(common.call(lambda: client.post("remote/switch", {"on": False})))


@remote.command()
@click.argument("name", default="phone")
def pair(name: str) -> None:
    """Pair a device (design 0025 §2): a QR to scan with its camera, the link it carries, and the code to type on the
    phone page instead (fifteen minutes, once)."""
    client = common.call(common.connect)
    found = common.call(lambda: client.post("remote/pair", {"name": name}))
    if found.get("link"):
        for line in qr_lines(found["link"]):
            click.echo(line)
        click.echo(f"Scan it with the iPhone's camera, or open {found['link']}")
    else:
        click.echo("Tailscale did not say this machine's address: the phone page's link cannot be made")
    click.echo(f"Code for {name}: {found['code'][:4]} {found['code'][4:]}  (until {found['expires']}), to type instead")
    if not found["on"]:
        click.echo("Remote access is off: `clank remote on` publishes the page first.")


@remote.command()
def cancel() -> None:
    """Cancel the pairing code waiting: it no longer pairs."""
    client = common.call(common.connect)
    found = common.call(lambda: client.post("remote/pair/cancel"))
    click.echo("The pairing code is canceled." if found["canceled"] else "No pairing code was waiting.")


@remote.command()
@click.argument("id")
def revoke(id: str) -> None:
    """Revoke a paired device (its id: `clank remote status`)."""
    client = common.call(common.connect)
    found = common.call(lambda: client.post(f"remote/devices/{id}/revoke"))
    click.echo(f"{found['name']} is revoked.")


def _show(found: dict[str, Any]) -> None:
    state = "on" if found["on"] else "off"
    where = f" at {found['url']}" if found.get("url") and found["on"] else ""
    listening = " (listening, published)" if found.get("listening") and found.get("published") else ""
    click.echo(f"Remote access {state}{where}{listening}")
    if found.get("problem"):
        click.echo(f"  {found['problem']}")
    devices = [device for device in found.get("devices") or [] if isinstance(device, dict) and not device["revoked"]]
    for device in devices:
        click.echo(f"  {device['id']}  {device['name']}  last used {device['last_seen']}")
    if not devices:
        click.echo("  No paired device: `clank remote pair` makes a code.")
