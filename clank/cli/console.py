"""`clank console`: open Clank's console (design 0001 §5, design 0002 §2.15).

The console is a client of the service. When the service is not running, `clank console` starts it in the background
first, as `clank serve --background` does, and says so; with `--no-start` it says how to start it instead.
`--snapshot` prints one frame as text and exits (design 0001 §5.8), for scripts, bug reports and a model that cannot
see a screen. `--view` opens a page with views on one of them: `--page monitor --view flow` is the Monitor's Flow view
(design 0013 §15), for a terminal that keeps F10 for itself, such as one reached over SSH; a view it does not have is
refused, never opened as another. With no page named, the console opens on Add a model while no model is usable (design
0016 §14). `--record FOLDER` keeps what the console draws, as the terminal gets it, for a player (decision 0126).

Textual's own log file (`TEXTUAL_LOG`) and its devtools are turned off for the console: they would record each key
pressed and each paste, and the console is where a cloud provider's key is typed (design 0016 §4).
"""

import os
from pathlib import Path

import click

from clank.client import Client, ClientError, NotRunning
from clank.kernel.home import Home
from clank.kernel.service import ServiceError, start_detached


@click.command()
@click.option("--snapshot", is_flag=True, help="Print one frame as text and exit: for scripts, bug reports and models.")
@click.option(
    "--page",
    default=None,
    help="The page to open: home (the default), folder, help, or any page's id. Unnamed, the console opens on Add a "
    "model while no model is usable.",
)
@click.option(
    "--view",
    default="",
    callback=lambda context, parameter, value: _view(value),
    help="The view to open on, for a page with views: the Monitor's flow, session or context (alone, the Monitor's); "
    "`--page monitor --view flow` is the Flow view, for a terminal that keeps F10 for itself.",
)
@click.option("--width", default=120, show_default=True, help="The frame's width in columns, with --snapshot.")
@click.option("--height", default=40, show_default=True, help="The frame's height in rows, with --snapshot.")
@click.option("--no-start", is_flag=True, help="Do not start the service when it is not running; say how instead.")
@click.option(
    "--record",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Record what the console draws, as the terminal gets it, into this folder: asciicast files a player shows "
    "again as it happened, a new part every 20 minutes (decision 0126).",
)
@click.option("--opening", default="home", hidden=True, help="The page to open when none is named (a bare clank's).")
def console(
    snapshot: bool,
    page: str | None,
    view: str,
    width: int,
    height: int,
    no_start: bool,
    record: Path | None,
    opening: str,
) -> None:
    """Open Clank's console: what runs, what waits for you, and every page."""
    from clank.console import app as console_app  # Textual loads only when the console opens

    quiet_textual()
    home = Home.resolve()
    client = connect(home, start=not no_start)
    guide = page is None and not view
    page = "monitor" if view and page in (None, "home") else (page or opening)  # a view is the Monitor's
    app = console_app.ClankConsole(
        client, page=page, view=view, home=home, snapshot=snapshot, guide=guide, record=record
    )
    try:
        if snapshot:
            click.echo(app.run(headless=True, size=(width, height)) or "")
        else:
            app.run()
    finally:
        client.close()


VIEWS = ("flow", "session", "context")


def _view(value: str) -> str:
    """A view the console has, or none: a mistyped one (`flow.`) is refused, never opened as another."""
    if value and value not in VIEWS:
        raise click.BadParameter(f"{value!r} is no view: one of {', '.join(VIEWS)}", param_hint="'--view'")
    return value


def connect(home: Home, start: bool) -> Client:
    """A client of the service that answers for this CLANK_HOME, started in the background first if need be."""
    try:
        return _reach(home)
    except NotRunning as error:
        if not start:
            raise click.ClickException(str(error)) from error
    except ClientError as error:
        raise click.ClickException(str(error)) from error
    click.echo("The Clank service is not running; starting it in the background (as `clank serve --background` does)")
    try:
        start_detached(home)
        return _reach(home)
    except (ServiceError, NotRunning, ClientError) as error:
        raise click.ClickException(str(error)) from error


def _reach(home: Home) -> Client:
    client = Client.connect(home, name="console")
    try:
        client.get("service")
    except (NotRunning, ClientError):
        client.close()
        raise
    return client


def quiet_textual() -> None:
    """Turn Textual's log file and devtools off: the console takes keys that must never be written anywhere."""
    from textual import constants

    os.environ.pop("TEXTUAL_LOG", None)
    constants.LOG_FILE = None  # type: ignore[misc]  # Final, read once when Textual loaded: set again here
    features = [each for each in os.environ.get("TEXTUAL", "").split(",") if each.strip() not in ("devtools", "")]
    if features:
        os.environ["TEXTUAL"] = ",".join(features)
    else:
        os.environ.pop("TEXTUAL", None)
