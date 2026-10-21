"""The service's commands: `clank serve` (in this terminal, or in the background), `clank stop`, `clank status`.

`clank serve` is one of the three commands that act without a running service (design 0002 §2.15); `stop` and
`status` are clients of the API like any other.
"""

import json
import time
from datetime import UTC, datetime

import click

from clank import registry
from clank.client import Client, ClientError, NotRunning
from clank.kernel.access import read_connection
from clank.kernel.home import Home
from clank.kernel.service import AlreadyRunning, Service, ServiceError, start_detached


@click.command()
@click.option(
    "--background", is_flag=True, help="Start it detached, and return once it answers (output: logs/service.log)."
)
@click.option("--port", type=click.IntRange(1024, 65535), help="Listen on this port instead of config/service.json's.")
def serve(background: bool, port: int | None) -> None:
    """Run the Clank service (in this terminal until Ctrl+C or `clank stop`)."""
    home = Home.resolve()
    try:
        if background:
            try:
                connection = start_detached(home, port)
            except AlreadyRunning as running:
                found = running.connection
                click.echo(f"Clank service already runs on {found.url} (process {found.pid}); nothing was started")
                return
            click.echo(
                f"Clank service started on {connection.url} (process {connection.pid}); stop it with `clank stop`"
            )
            return
        Service(home, registry.components(), port=port).run()
    except ServiceError as error:
        raise click.ClickException(str(error)) from error


@click.command()
def stop() -> None:
    """Stop the Clank service."""
    home = Home.resolve()
    try:
        with Client.connect(home) as client:
            client.post("service/stop")
    except (NotRunning, ClientError) as error:
        raise click.ClickException(str(error)) from error
    deadline = time.monotonic() + 15
    while read_connection(home) is not None and time.monotonic() < deadline:
        time.sleep(0.1)
    click.echo("Clank service stopped" if read_connection(home) is None else "Clank service is still stopping")


@click.command()
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def status(as_json: bool) -> None:
    """Show whether the Clank service runs, since when, and what waits for you."""
    try:
        with Client.connect(Home.resolve()) as client:
            service = client.get("service")
            waiting = client.get("questions", status="waiting")
    except NotRunning as error:
        if as_json:
            click.echo(json.dumps({"running": False, "message": str(error)}))
        else:
            click.echo(f"Clank service: not running. {str(error).split('; ', 1)[-1].capitalize()}.")
        raise SystemExit(1) from error
    if as_json:
        click.echo(json.dumps({"running": True, **service, "questions_waiting": len(waiting)}, indent=2))
        return
    started = datetime.fromisoformat(service["started"])
    click.echo(
        f"Clank service: running ({service['version']}) at {service['url']}, process {service['pid']}, "
        f"up {_duration((datetime.now(UTC) - started).total_seconds())}"
    )
    clients = ", ".join(service["clients"]) or "none"
    click.echo(f"  clients following it: {clients}")
    click.echo(f"  questions waiting for you: {len(waiting)}")


def _duration(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 1:
        return f"{int(seconds)}s"
    if minutes < 60:
        return f"{minutes}m"
    return f"{minutes // 60}h {minutes % 60:02d}m"
