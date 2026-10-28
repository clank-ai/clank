"""`clank setup` (design 0028 §4, §5): what Clank needs on this computer, in order, and the fixes, each asked first.

It is one of the three commands that act without the service (design 0002 §2.15): when the service runs, the checklist
is the service's (`GET /setup`, Docker read now); when it does not, `clank setup` reads Docker itself, through the
platform the settings choose, as `clank doctor` does, and says that the model and the folder are told once the service
runs, rather than guessing. The folder it was started in is checked as a workspace's would be.

- `--check` prints the checklist and changes nothing; it exits 0 when everything required is done, else 1 (the
  installers end with it, design 0028 §3). `--json` prints the checklist as the API gives it, for scripts and models.
- Without `--check`, after the checklist it asks about each item that is not done, in order, and does it on a yes,
  reading the checklist again after each: the item and its fix are shown first, with the exact command when it runs
  one. A command that needs administrator rights (`sudo systemctl start docker`, `sudo systemctl enable docker`, `sudo
  usermod -aG docker <account>`, the installer's Docker step) runs attached to this terminal (`attached`), so sudo, or
  Windows, asks for the password itself and nothing it says is captured: Clank never reads, asks for or keeps a
  password. A fix that leaves the person something to do after it (log out and in once after joining the docker group;
  open Docker Desktop once after installing it) says so, and the setup stops there. Docker Desktop is started through
  its own start: by the service's operation when the service runs, else here (`start_platform`). Clank's service is
  started in the background as `clank serve --background` starts it; the model's step asks once whether models run in
  the cloud through OpenRouter, on this computer's GPU, or both (the cloud first), and hands the terminal to Add a
  model's command for each (`clank model add --cloud`, `--local`), which keeps the key in Clank's secrets folder; the
  folder is opened as a workspace (`clank workspace open`'s operation). An item
  whose fix is the person's to do (the log out and in, the kernel's memory setting) is said, and the setup goes on.
  Without a terminal to answer in, every answer is no.
- `--yes` does every fix that needs no administrator rights without asking (Docker Desktop's start, the service, the
  folder) and lists the others with their commands; Add a model needs the person's answers, so it is listed too.

Each item is a line: its state (`done`, `to do`, `doing`, `waits` for an item before it, `unknown` until the service
says, `optional`), its title and what it is now; under an item not done, what to do (`->`), wrapped to the terminal.
"""

import json
import os
import shutil
import signal
import subprocess
import sys
import textwrap
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import click

from clank.cli import common, follow
from clank.client import Client, ClientError, NotRunning
from clank.components.agents import checklist, setupfacts
from clank.components.workspaces.service import DockerError, start_platform
from clank.kernel.home import Home
from clank.kernel.service import AlreadyRunning, ServiceError, start_detached

MARK = 9  # the state's column
SAID_AT_LEAST = 40  # columns beside an item's title for what it is now; fewer, and it goes under the title
HEAD = "Clank's setup: what Clank needs on this computer, in order."
UNCHANGED = "Nothing was changed."
OFFERED = (
    "`clank setup` offers each fix in order and asks before each one; a command that needs administrator rights runs "
    "in this terminal, where sudo asks for your password itself."
)
MODEL_QUESTION = (
    "Run models in the cloud through OpenRouter (c), on this computer's GPU (l), or both (b)? Enter: not now"
)


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


def echo(text: str, indent: str = "", more: str = "") -> None:
    """A paragraph, wrapped to the terminal: its first line indented by `indent`, the others by `more` (`indent`'s
    too unless given)."""
    more = more or indent
    lines = wrap(text, width() - len(more))
    for number, line in enumerate(lines or [""]):
        click.echo((indent if number == 0 else more) + line)


def attached(argv: Sequence[str]) -> int | str:
    """Run a command attached to this terminal and wait for it: its input, output and errors are the terminal's own, so
    sudo (or Windows) asks for the password there itself, and nothing it says is captured. Ctrl+C is the command's
    while it runs. Its exit status, or why it could not start."""
    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        return subprocess.call(list(argv))
    except OSError as error:
        return f"{argv[0] if argv else 'it'} could not start: {error}"
    finally:
        signal.signal(signal.SIGINT, previous)


def ask(question: str) -> bool:
    """A yes or no at the terminal: no unless the answer is yes, and no without a terminal to answer in."""
    try:
        return bool(click.confirm(question, default=False))
    except click.Abort:
        click.echo()
        return False


class Fixes:
    """The fixes of one run of `clank setup`, item after item, the checklist read again after each."""

    def __init__(self, home: Home, folder: str, yes: bool) -> None:
        self.home = home
        self.folder = folder
        self.yes = yes
        self.offered: set[str] = set()
        self.later: list[dict[str, Any]] = []  # fixes not done: declined, or needing what --yes does not give
        self.stopped = False

    def run(self, found: dict[str, Any]) -> dict[str, Any]:
        """Offer each item's fix in order until none is left to offer, or one leaves the person something to do; the
        checklist as it ends."""
        while not self.stopped:
            item = next((each for each in found["items"] if self._pending(each)), None)
            if item is None:
                break
            self.offered.add(item["id"])
            self._offer(item)
            found, _ = read(self.home, self.folder)
        return found

    def _pending(self, item: dict[str, Any]) -> bool:
        return item["state"] in ("to do", "unknown") and bool(item.get("fix")) and item["id"] not in self.offered

    def _offer(self, item: dict[str, Any]) -> None:
        fix = item["fix"]
        click.echo()
        echo(f"{item['title']}: {item['said']}")
        if not fix["does"]:
            echo(f"{'Yours' if item['required'] else 'Optional, yours'} to do: {fix['said']}", "  ")
            return
        if fix["admin"] and self.yes:
            echo(f"Not done with --yes, since it needs administrator rights: run `{fix['shown']}` yourself, or `clank "
                 "setup` without --yes, which asks first.", "  ")  # fmt: skip
            self.later.append(item)
            return
        if fix["does"] == "model":
            self._model(item)
            return
        echo(fix["said"], "  ")
        if not self.yes and not ask("  Do it now?"):
            self.later.append(item)
            return
        actions: dict[str, Callable[[dict[str, Any]], None]] = {
            "terminal": self._terminal,
            "docker": self._docker,
            "service": self._service,
            "folder": self._folder,
        }
        actions[fix["does"]](item)

    def _terminal(self, item: dict[str, Any]) -> None:
        """The command, attached to this terminal; what the person does after it, said, and the setup stops there."""
        fix = item["fix"]
        click.echo(f"  > {fix['shown'] or ' '.join(fix['command'])}")
        outcome = attached(fix["command"])
        if outcome != 0:
            ended = outcome if isinstance(outcome, str) else f"exit {outcome}"
            echo(f"That did not work ({ended}): its words are above.", "  ")
            return
        click.echo("  Done.")
        if fix["after"]:
            echo(f"Next: {fix['after']}.", "  ")
            self.stopped = True

    def _docker(self, item: dict[str, Any]) -> None:
        """Docker Desktop, started through its own start: the service's operation when it runs, else here."""
        client = self._client()
        if client is not None:
            done = follow.follow(client, common.call(lambda: client.post("docker/start")))
            if done["status"] != "done":
                echo(f"{done['title']}: {done['error'] or done['status']}", "  ")
            return
        try:
            status = start_platform(self.home, lambda text: echo(text, "  "))
        except DockerError as error:
            echo(f"Docker did not start: {error}", "  ")
            return
        echo(f"{status.label} runs.", "  ")

    def _service(self, item: dict[str, Any]) -> None:
        """Clank's service, started in the background as `clank serve --background` starts it."""
        try:
            start_detached(self.home)
        except AlreadyRunning:
            pass
        except ServiceError as error:
            echo(f"Clank's service did not start: {error}", "  ")
            return
        echo("Clank's service runs in the background; `clank stop` ends it.", "  ")

    def _model(self, item: dict[str, Any]) -> None:
        """Add a model, asked once: in the cloud, on this computer's GPU, or both (the cloud first), each walked as
        `clank model add` walks it."""
        client = self._client()
        if client is None:
            echo("Clank's service adds it: start it first (above).", "  ")
            return
        if self.yes:
            echo("Not done with --yes, since it needs your answers: `clank model add`, or `clank`, whose console opens "
                 "on Setup, then Add a model.", "  ")  # fmt: skip
            self.later.append(item)
            return
        echo(item["fix"]["said"], "  ")
        try:
            picked = str(click.prompt(f"  {MODEL_QUESTION}", default="", show_default=False)).strip().lower()
        except click.Abort:
            picked = ""
        paths = {"c": ["cloud"], "l": ["local"], "b": ["cloud", "local"]}.get(picked, [])
        if not paths:
            self.later.append(item)
            return
        for path in paths:
            outcome = attached([sys.executable, "-m", "clank", "model", "add", f"--{path}"])
            if outcome != 0:
                echo(f"Add a model ended without a {path} model; `clank model add` tries again.", "  ")
                return

    def _folder(self, item: dict[str, Any]) -> None:
        """The folder `clank setup` was started in, opened as a workspace by the service's operation."""
        client = self._client()
        if client is None:
            echo("Clank's service opens it: start it first (above).", "  ")
            return
        body = {"folder": self.folder, "yes": True}
        done = follow.follow(client, common.call(lambda: client.post("workspaces/open", body)))
        if done["status"] != "done":
            echo(f"{done['title']}: {done['error'] or done['status']}", "  ")

    def _client(self) -> Client | None:
        """A client of the service, or None when it does not run."""
        try:
            client = common.connect()
            client.get("service")
        except (NotRunning, ClientError):
            return None
        return client

    def report(self, found: dict[str, Any]) -> None:
        """How the setup ends: the checklist's line, what was set up once ready, and the fixes left with their
        commands."""
        click.echo()
        echo(found["said"])
        for line in found.get("ready_said") or []:
            echo(f"- {line}", "  ", "    ")
        if self.later:
            click.echo("Left to do:")
            for item in self.later:
                fix = item["fix"]
                said = f"`{fix['shown']}`" if fix.get("shown") else fix["said"]
                echo(f"- {item['title']}: {said}", "  ", "    ")


@click.command()
@click.option("--check", is_flag=True, help="Print the checklist and change nothing; exit 0 when everything required "
              "is done, else 1.")  # fmt: skip
@click.option("--yes", is_flag=True, help="Do every fix that needs no administrator rights without asking; the others "
              "are listed with their commands.")  # fmt: skip
@click.option("--json", "as_json", is_flag=True, help="Print the checklist as JSON, for scripts and models.")
def setup(check: bool, yes: bool, as_json: bool) -> None:
    """What Clank needs on this computer, in order, and the fixes, each asked first (design 0028 §4)."""
    home = Home.resolve()
    folder = str(Path(os.getcwd()).resolve())
    found, note = read(home, folder)
    if as_json:
        click.echo(json.dumps(found, indent=2))
        raise SystemExit(0 if found["ready"] else 1)
    for line in render(found, width()):
        click.echo(line)
    if note:
        echo(note)
    if check:
        if not found["ready"]:
            echo(OFFERED)
        click.echo(UNCHANGED)
        raise SystemExit(0 if found["ready"] else 1)
    if found["ready"]:
        return
    fixes = Fixes(home, folder, yes)
    found = fixes.run(found)
    fixes.report(found)
    raise SystemExit(0 if found["ready"] else 1)
