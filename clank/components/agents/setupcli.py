"""`clank setup` (design 0028 §4): what Clank needs on this computer, in order, and what to do about each item that is
not done.

It is one of the three commands that act without the service (design 0002 §2.15): when the service runs, the checklist
is the service's (`GET /setup`, Docker read now); when it does not, `clank setup` reads Docker itself, through the
platform the settings choose, as `clank doctor` does, and says that the model and the folder are told once the service
runs, rather than guessing. The folder it was started in is checked as a workspace's would be. `--check` prints the
checklist and changes nothing; it exits 0 when everything required is done, else 1 (the installers end with it, design
0028 §3); `--json` prints the checklist as the API gives it, for scripts and models. The fixes come with the setup's
next step (S3, plan s62); until then `clank setup` alone does what `--check` does.

Each item is a line: its state (`done`, `to do`, `doing`, `waits` for an item before it, `unknown` until the service
says, `optional`), its title and what it is now; under an item not done, what to do (`->`), wrapped to the terminal.
"""

import json
import os
import shutil
import textwrap
from pathlib import Path
from typing import Any

import click

from clank.cli import common
from clank.client import ClientError, NotRunning
from clank.components.agents import checklist, setupfacts
from clank.kernel.home import Home

MARK = 9  # the state's column
SAID_AT_LEAST = 40  # columns beside an item's title for what it is now; fewer, and it goes under the title
HEAD = "Clank's setup: what Clank needs on this computer, in order."
UNCHANGED = "Nothing was changed."


def read(home: Home, folder: str) -> tuple[dict[str, Any], str]:
    """The checklist: the service's when it runs (Docker read now), else read here; and a note when the service could
    not give it."""
    try:
        client = common.connect()
    except NotRunning:
        return checklist.view(setupfacts.offline(home, folder)), ""
    try:
        return dict(client.get("setup", folder=folder, refresh=True)), ""
    except NotRunning:
        return checklist.view(setupfacts.offline(home, folder)), ""
    except ClientError as error:
        if error.status != 404:
            raise click.ClickException(str(error)) from error
        older = "Clank's service runs an older Clank, which cannot say all of this: `clank stop`, then `clank`"
        return checklist.view(setupfacts.offline(home, folder)), older


def state_of(item: dict[str, Any]) -> str:
    """An item's state as the checklist's first column writes it: `optional` for one offered, not required."""
    return "optional" if item["state"] == "to do" and not item["required"] else str(item["state"])


def render(found: dict[str, Any], width: int) -> list[str]:
    """The checklist's lines: each item, what to do under one not done, then one line on the whole. What an item is
    now stands beside its title, or under it where the terminal leaves less than `SAID_AT_LEAST` columns beside it."""
    titles = max(len(item["title"]) for item in found["items"])
    column = 2 + MARK + titles + 2
    beside = width - column >= SAID_AT_LEAST
    under = " " * (2 + MARK)
    lines = [HEAD, ""]
    for item in found["items"]:
        head = f"  {state_of(item):<{MARK}}{item['title']:<{titles}}"
        if beside:
            said = wrap(item["said"], width - column) or [""]
            lines.append(f"{head}  {said[0]}")
            lines += [" " * column + more for more in said[1:]]
        else:
            lines.append(head.rstrip())
            lines += [under + "  " + more for more in wrap(item["said"], width - len(under) - 2)]
        fix = item.get("fix")
        if fix and item["state"] != "done":
            lines += [under + line for line in wrap(f"-> {fix['said']}", width - len(under), "   ")]
    lines += ["", *wrap(found["said"], width)]
    lines += [line for each in found.get("ready_said") or [] for line in wrap(f"- {each}", width, "  ")]
    return lines


def wrap(text: str, room: int, more: str = "") -> list[str]:
    """Text wrapped to `room` columns (at least 20), never inside a word, a command or an address; `more` indents the
    lines after the first."""
    return textwrap.wrap(text, max(room, 20), subsequent_indent=more, break_long_words=False, break_on_hyphens=False)


def width() -> int:
    """The terminal's width, for wrapping (80 when it does not say)."""
    return shutil.get_terminal_size((80, 24)).columns


@click.command()
@click.option("--check", is_flag=True, help="Print the checklist and change nothing; exit 0 when everything required "
              "is done, else 1.")  # fmt: skip
@click.option("--json", "as_json", is_flag=True, help="Print the checklist as JSON, for scripts and models.")
def setup(check: bool, as_json: bool) -> None:
    """What Clank needs on this computer, in order, and what to do about each item not done (design 0028 §4)."""
    home = Home.resolve()
    folder = str(Path(os.getcwd()).resolve())
    found, note = read(home, folder)
    if as_json:
        click.echo(json.dumps(found, indent=2))
        raise SystemExit(0 if found["ready"] else 1)
    for line in render(found, width()):
        click.echo(line)
    if note:
        click.echo(note)
    click.echo(UNCHANGED)
    raise SystemExit(0 if found["ready"] else 1)
