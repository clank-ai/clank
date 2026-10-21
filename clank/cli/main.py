"""The `clank` command's entry point: the top-level group that every component's commands join.

It is built with click (decision 0023): the generic commands for every kind of record are made from the kinds'
definitions when the program starts, which click supports directly. `clank --version` prints the version of the code
that is running. Everything it prints is UTF-8 on every platform, as Python 3.15 makes the default (PEP 686): on
Windows a pipe would otherwise get the system's code page, and a reader expecting UTF-8 would see "·" garbled.
Arguments reach the commands as typed: on Windows, click would expand `~` and wildcards as a shell does, but a path
may be one on a WSL host, where `~` is not this user's home.
"""

import io
import sys
from typing import Any

import click

from clank import __version__, registry
from clank.cli import records
from clank.cli.console import console
from clank.cli.service import serve, status, stop


class Clank(click.Group):
    """The top-level group, which passes the command line as typed on every platform."""

    def main(self, *args: Any, **kwargs: Any) -> Any:
        """Run as click does, without expanding `~` and wildcards on Windows."""
        kwargs.setdefault("windows_expand_args", False)
        return super().main(*args, **kwargs)


@click.group(cls=Clank, invoke_without_command=True, context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "--version", "-V", prog_name="clank", message="%(prog)s %(version)s")
@click.pass_context
def main(context: click.Context) -> None:
    """Clank: a local LLM suite that runs on your own hardware. Alone, `clank` opens the console on this folder's page:
    what working here needs, and the agent; `clank work` starts the agent here at once."""
    for stream in (sys.stdout, sys.stderr):
        if isinstance(stream, io.TextIOWrapper) and stream.encoding.lower().replace("-", "") != "utf8":
            stream.reconfigure(encoding="utf-8")
    if context.invoked_subcommand is None:
        context.invoke(console, opening="folder")


for command in (serve, stop, status, console, *records.COMMANDS):
    main.add_command(command)
for component in registry.components():
    if component.commands is not None:
        for command in component.commands():
            main.add_command(command)
