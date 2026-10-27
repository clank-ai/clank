"""`clank work [FOLDER]` (design 0004 §1): the agent, in a folder's container, in this terminal, at once; `clank code
[FOLDER]` (design 0004 §5): the folder in Clank's VS Code window, the agent in a terminal beside the files. A bare
`clank` opens the console on the folder's page instead, where `a` starts the agent once everything is ready, and `c`
opens VS Code.

Each step is done only when it is needed, and followed as it goes: the service (started in the background when it
does not run), Docker (started when it is stopped, if Clank starts it: a Docker the system runs, Docker Engine, is
shown with what to do, design 0014 §2), the folder's workspace (opened: its container runs; the first time
it builds Clank's sandbox image, asked first unless `--yes`), a model in the main slot (when none runs: the slot's last
configuration that worked, else `daily 262K`), the agent's configuration (written into the container), and then the
agent itself, here. Leaving the agent stops nothing but the agent. `clank code` gets the folder ready the same way,
then opens it in the VS Code window (set up the first time: its settings and extensions), where Clank's extension
starts the agent beside the files. Over SSH (design 0018 §8) nothing opens on the PC's own screen: from a terminal of
VS Code's Remote-SSH the folder opens in the other computer's VS Code, connected to this PC; from any other, the
command to run on the other computer is said.

With no model usable (design 0016 §14), both say so and how to add one (`clank`, or `clank model add`). With a cloud
model in the main slot, the workspace is asked once, in the terminal and before OpenCode starts, whether its agent may
use it (design 0016 §9, decision 0112): the service's question, answered through its own route; kept local, the command
stops, saying how to allow it.
"""

import os
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import click

from clank.cli import common, follow
from clank.client import Client, ClientError, NotRunning
from clank.kernel import where
from clank.kernel.home import Home
from clank.kernel.service import ServiceError, start_detached

DEFAULT_PRESET = "daily-262k"
Terminal = Callable[[Sequence[str]], int]


def terminal(argv: Sequence[str]) -> int:
    """Run a command attached to this terminal; its exit status."""
    return subprocess.call(list(argv))


@click.command()
@click.argument("folder", required=False)
@click.option("--yes", is_flag=True, help="Build Clank's sandbox image without asking first, when it is not built.")
def work(folder: str | None, yes: bool) -> None:
    """Work with the agent in a folder (this one unless named), in the folder's own container."""
    path = str(Path(folder or os.getcwd()).resolve())
    client = _client()
    _usable(client)
    opened = _ready(client, path, yes)
    _cloud(client, opened["workspace"])
    prepared = common.call(lambda: client.post("agents/prepare", {"workspace": opened["workspace"]}))
    for note in prepared["notes"]:
        click.echo(f"  {note}")
    click.echo(f"{prepared['program']} in {opened['workspace']} ({path} at /workspace), with {prepared['model']}")
    raise click.exceptions.Exit(terminal(prepared["argv"]))


@click.command()
@click.argument("folder", required=False)
@click.option("--yes", is_flag=True, help="Build Clank's sandbox image without asking first, when it is not built.")
def code(folder: str | None, yes: bool) -> None:
    """Open a folder (this one unless named) in Clank's VS Code window, the agent beside the files."""
    path = str(Path(folder or os.getcwd()).resolve())
    client = _client()
    _usable(client)
    opened = _ready(client, path, yes)
    _cloud(client, opened["workspace"])
    place = where.vscode_place(os.environ)
    if place == where.OVER_SSH:
        host = str(common.call(lambda: client.get("records/vscode/vscode"))["values"].get("ssh_host") or "")
        click.echo(f"The folder is ready; {where.ssh_said(path, os.environ, host)}")
        return
    if place == where.REMOTE:
        click.echo(
            "Opening VS Code on your computer, connected to this PC (the first time, it installs its extensions)"
        )
    else:
        click.echo("Opening Clank's VS Code window (the first time, it installs its extensions)")
    body = where.vscode_request(path, os.environ)
    opened = _done(follow.follow(client, common.call(lambda: client.post("agents/vscode", body))))
    for name in opened["failed"]:
        click.echo(f"  {name} could not be installed: it is tried again the next time")
    on = " on your computer" if place == where.REMOTE else ""
    click.echo(f"VS Code opens {path}{on}: OpenCode opens beside your files")


def _ready(client: Client, path: str, yes: bool) -> dict[str, Any]:
    """What the agent needs, each step only when needed: Docker, the folder's workspace, a model; the workspace."""
    docker = common.call(lambda: client.get("docker", refresh=True))
    if docker["state"] != "running":
        if not docker.get("starts", True):  # the system's Docker Engine: Clank never starts it (design 0014 §2)
            click.echo(docker.get("said") or f"Docker is {docker['state']}: {docker['detail']}")
            raise click.exceptions.Exit(1)
        click.echo(f"Docker is {docker['state']}: starting it")
        _done(follow.follow(client, common.call(lambda: client.post("docker/start"))))
    opened = _done(
        follow.follow(client, common.call(lambda: client.post("workspaces/open", {"folder": path, "yes": yes})))
    )
    _model(client)
    return opened


def _client() -> Client:
    """A client of the service, which is started in the background when it does not run."""
    try:
        return common.connect()
    except NotRunning:
        click.echo("The Clank service does not run: starting it")
        try:
            start_detached(Home.resolve())
        except ServiceError as error:
            raise click.ClickException(str(error)) from error
        return common.call(common.connect)


def _model(client: Client) -> None:
    """A model in the main slot: the one that runs, else its last configuration that worked, else the runtime's
    fallback preset (design 0016 §7) when it can load now or none can, else the first that can."""
    slots = {slot["name"]: slot for slot in common.call(lambda: client.get("runtime/slots"))}
    main = slots["main"]
    if main["status"] in ("ready", "starting"):
        return
    usable = _optional(client, "runtime/usable") or {}
    candidates = [each["preset"] for each in usable.get("candidates", [])]
    fallback = str(usable.get("fallback") or DEFAULT_PRESET)
    first = fallback if fallback in candidates or not candidates else candidates[0]
    preset = (main.get("last_good") or {}).get("preset") or first
    click.echo(f"No model runs: loading {preset}")
    _done(follow.follow(client, common.call(lambda: client.post("runtime/slots/main/load", {"preset": preset}))))


def _optional(client: Client, path: str) -> Any:
    """A route of the cloud's, or None from a service without it."""
    try:
        return client.get(path)
    except ClientError as error:
        if error.status == 404:
            return None
        common.fail(error)
    except NotRunning as error:
        common.fail(error)


def _usable(client: Client) -> None:
    """With no model usable and none that worked before (whose load says why it cannot now), say so and how to add
    one, and stop."""
    usable = _optional(client, "runtime/usable")
    if usable is None or usable["usable"]:
        return
    slots = common.call(lambda: client.get("runtime/slots"))
    if not any((slot.get("last_good") or {}).get("preset") for slot in slots if slot["name"] == "main"):
        raise click.ClickException("No model is set up yet: run clank, or clank model add")


def _cloud(client: Client, workspace: str) -> None:
    """With a cloud model loaded, the workspace's question, once, before OpenCode starts; kept local, stop."""
    try:
        asked = client.post(f"workspaces/{workspace}/cloud/ask")
    except ClientError as error:
        if error.status == 404:
            return  # a service without the cloud's routes
        common.fail(error)
    if asked["needed"]:
        question = common.call(lambda: client.get(f"records/question/{asked['question']}"))["values"]
        click.echo(question["title"])
        if question["detail"]:
            click.echo(question["detail"])
        options = {option["key"]: option for option in question["options"] if option["key"]}
        for key, option in options.items():
            click.echo(f"  {key}  {option['label']}" + (f": {option['effect']}" if option["effect"] else ""))
        default = next((key for key, option in options.items() if option["id"] == question["default"]), None)
        chosen = options[click.prompt("Your answer", type=click.Choice(list(options)), default=default)]
        common.call(lambda: client.post(f"questions/{question['id']}/answer", {"option": chosen["id"]}))
        asked = common.call(lambda: client.post(f"workspaces/{workspace}/cloud/ask"))
    if not asked.get("start", True):
        raise click.ClickException(f"{asked['why']} (clank workspace allow FOLDER --cloud allows it)")


def _done(operation: dict[str, Any]) -> dict[str, Any]:
    """The result of an operation that ended well; else its error said, and exit 1."""
    if operation["status"] != "done":
        click.echo(f"{operation['title']}: {operation['error'] or operation['status']}")
        raise click.exceptions.Exit(1)
    return dict(operation.get("result") or {})
