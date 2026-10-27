"""What the commands that are clients of the API share (design 0002 §2.15): connecting to the service as `cli`,
turning the client's errors into the command's own message, and showing times and actors the same way everywhere.

Commands call `common.connect()` through the module, so tests can replace it with a client of a test service.
"""

from collections.abc import Callable
from datetime import datetime
from typing import Any, NoReturn

import click

from clank.client import Client, ClientError, NotRunning
from clank.kernel.home import Home


def connect() -> Client:
    """A client of the service of this CLANK_HOME, naming itself `cli`."""
    return Client.connect(Home.resolve(), name="cli")


def fail(error: Exception) -> NoReturn:
    """End the command with the error's message."""
    raise click.ClickException(str(error)) from error


def call[T](action: Callable[[], T]) -> T:
    """Run a call to the service; a service that does not run, or refuses, ends the command with its message."""
    try:
        return action()
    except (NotRunning, ClientError) as error:
        fail(error)


def local_time(time: str) -> str:
    """A time from the API, in this computer's time zone: 11:42:05."""
    return datetime.fromisoformat(time.replace("Z", "+00:00")).astimezone().strftime("%H:%M:%S")


def local_moment(time: str) -> str:
    """A time from the API, in this computer's time zone, to the minute, with its day when it is not today: "today
    17:54", "2026-10-15 00:47"."""
    moment = datetime.fromisoformat(time.replace("Z", "+00:00")).astimezone()
    if moment.date() == datetime.now().astimezone().date():
        return f"today {moment:%H:%M}"
    return f"{moment:%Y-%m-%d %H:%M}"


def describe(actor: dict[str, Any]) -> str:
    """Who did something, as people say it: "you (console)", "Clank (machine.doctor)"."""
    if actor["kind"] == "user":
        return f"you ({actor['via']})" if actor["via"] else "you"
    if actor["kind"] == "clank":
        return f"Clank ({actor['via']})" if actor["via"] else "Clank"
    return f"{actor['kind']} {actor['via']}".strip()
