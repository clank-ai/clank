"""`clank autostart on|off|status` (design 0021 §11): Clank's service, and Docker Desktop through it, started when the
owner signs in to Windows, so the PC is ready for remote work after a restart (over SSH the service cannot be started:
Docker's sign-in needs the owner's session).

`on` writes the entry Windows runs at sign-in, the value `Clank` of the current user's Run key
(`HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run`), which Task Manager's Startup apps lists like any other:
Python's windowless program (`pythonw.exe`, beside the Python Clank runs on) running `clank autostart run`, with
`--home` when CLANK_HOME is set; `off` removes it; `status` says whether it is there and what it runs. `run` starts the
service in the background when it does not run, then asks it to start Docker (an operation, followed until it ends);
with no console to write to, it writes what it did to `logs/autostart.log`. The service keeps the gateway running
itself. On another system, `on` says it is not supported there yet (Linux: design 0014).
"""

import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import click

from clank.cli import common, follow
from clank.client import ClientError, NotRunning
from clank.kernel.home import Home
from clank.kernel.service import AlreadyRunning, ServiceError, start_detached

WINDOWS = sys.platform == "win32"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
ENTRY = "Clank"


def windowless() -> str:
    """Python's program without a console window, beside the one Clank runs on (else that one)."""
    found = Path(sys.executable).with_name("pythonw.exe")
    return str(found) if found.is_file() else sys.executable


def read_entry() -> str | None:
    """The sign-in entry's command, or None when there is none."""
    if sys.platform != "win32":  # an `if` on sys.platform, so the type checker knows winreg's names exist only there
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return str(winreg.QueryValueEx(key, ENTRY)[0])
    except FileNotFoundError:
        return None


def write_entry(command: str) -> None:
    """Write the sign-in entry."""
    if sys.platform != "win32":
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        winreg.SetValueEx(key, ENTRY, 0, winreg.REG_SZ, command)


def delete_entry() -> None:
    """Remove the sign-in entry, when there is one."""
    if sys.platform != "win32":
        return
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, ENTRY)
    except FileNotFoundError:
        pass


@click.group()
def autostart() -> None:
    """Start Clank's service and Docker when you sign in to Windows (ready for remote work after a restart)."""


@autostart.command()
def on() -> None:
    """Start Clank's service, and Docker through it, when you sign in."""
    if not WINDOWS:
        raise click.ClickException("starting at sign-in is Windows only for now")
    home = os.environ.get("CLANK_HOME", "")
    command = f'"{windowless()}" -m clank autostart run' + (f' --home "{home}"' if home else "")
    write_entry(command)
    click.echo(
        "Clank now starts Clank's service and Docker when you sign in to Windows. Task Manager's Startup apps lists it "
        "as Clank; `clank autostart off` removes it."
    )


@autostart.command()
def off() -> None:
    """Stop starting Clank at sign-in."""
    if WINDOWS:
        delete_entry()
    click.echo("Clank no longer starts when you sign in.")


@autostart.command()
def status() -> None:
    """Whether Clank starts at sign-in, and what it runs then."""
    found = read_entry() if WINDOWS else None
    click.echo(f"Starting at sign-in is on: {found}" if found else "Starting at sign-in is off.")


@autostart.command()
@click.option("--home", default="", help="Clank's home (CLANK_HOME), as `on` wrote it.")
def run(home: str) -> None:
    """What runs at sign-in: the service in the background when it does not run, then Docker through it."""
    if home:
        os.environ["CLANK_HOME"] = home
    found = Home.resolve()
    found.ensure()
    with (found.logs / "autostart.log").open("a", encoding="utf-8") as log:

        def say(text: str) -> None:
            log.write(f"{datetime.now(UTC).isoformat(timespec='seconds')} {text}\n")
            log.flush()

        try:
            client = common.connect()
            say("Clank's service runs already")
        except NotRunning:
            try:
                start_detached(found)
                say("started Clank's service")
            except AlreadyRunning:
                say("Clank's service runs already")
            except ServiceError as error:
                say(f"Clank's service did not start: {error}")
                return
            client = common.connect()
        try:
            ended = follow.follow(client, client.post("docker/start"))
            say(f"Docker: {ended.get('status') if isinstance(ended, dict) else ended}")
        except (NotRunning, ClientError) as error:
            say(f"Docker was not started: {error}")
