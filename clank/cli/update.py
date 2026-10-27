"""`clank update` (design 0026): what is installed and what is newer (`--check`), and the update itself, the way Clank
was installed; `--dry-run` says each step and changes nothing. The logic is `clank/updates.py`."""

import json
import os
import sys
from typing import Any

import click

from clank import updates
from clank.kernel.home import Home


@click.command()
@click.option("--check", is_flag=True, help="Say what is installed and what is newer; change nothing.")
@click.option("--dry-run", is_flag=True, help="Say each step of the update without doing it.")
@click.option("--json", "as_json", is_flag=True, help="With --check: print JSON, for scripts and models.")
def update(check: bool, dry_run: bool, as_json: bool) -> None:
    """Update Clank from GitHub, the way it was installed; --check only says what is newer."""
    install = updates.installed(run=updates.run)
    found = updates.newer(install, run=updates.run, fetch=updates.fetch)
    if check:
        if as_json:
            click.echo(json.dumps({"install": install.view(), "newer": found}, indent=2))
        else:
            for line in _said(install, found):
                click.echo(line)
        return
    for line in _said(install, found):
        click.echo(line)
    if found["newer"] is None:
        raise SystemExit(1)
    if not found["newer"]:
        return
    if install.kind == "clone":
        _clone(install, found, dry_run)
    else:
        _helper(install, found, dry_run)


def _said(install: updates.Install, found: dict[str, Any]) -> list[str]:
    """What is installed and what is newer, in words."""
    if install.kind == "clone":
        branch = f", branch {found['branch']}" if found.get("branch") else ""
        lines = [f"Installed: Clank {install.version}, a clone at {install.where}{branch}"]
    elif install.kind == "release":
        lines = [f"Installed: Clank {install.version}, a release ({install.where})"]
    else:
        lines = [f"Installed: Clank {install.version}, another way ({install.where})"]
    lines.append(f"Asked: {found['contacted']}")
    if found["newer"] is None:
        lines.append(f"Not known: {found['error']}")
    elif install.kind == "release":
        if found["newer"]:
            lines.append(f"Newer: {found['latest']} is out. clank update installs it")
        else:
            lines.append(f"Up to date: {found['latest'] or install.version} is the latest release")
    elif found["newer"]:
        lines.append(f"Newer: {found['behind']} commit{'s' if found['behind'] != 1 else ''} on {found['upstream']}:")
        lines += [f"  {title}" for title in found["titles"]]
        if found["behind"] > len(found["titles"]):
            lines.append(f"  and {found['behind'] - len(found['titles'])} more")
        if found["dirty"]:
            lines.append("Its working tree has changes of its own: commit them or set them aside, then clank update")
    else:
        lines.append(f"Up to date with {found['upstream']}")
    return lines


def _clone(install: updates.Install, found: dict[str, Any], dry_run: bool) -> None:
    if found["dirty"]:
        raise click.ClickException(
            f"{install.where} has changes of its own: commit them or set them aside (git stash), then clank update"
        )
    steps = [f"git pull --ff-only (in {install.where})"]
    if found["dependencies"]:
        steps.append(" ".join(updates.install_command(install, found)) + " (its dependencies changed), by a helper")
    else:
        steps.append("start the service again, so the new code runs")
    if found["extension"]:
        steps.append(
            "the VS Code extension changed: uv run python -m tools.extension, then uv run python -m tools.vsix"
        )
    if dry_run:
        click.echo("Would do:")
        for step in steps:
            click.echo(f"  {step}")
        return
    status, said = updates.run(["git", "pull", "--ff-only"], install.where)
    if status != 0:
        raise click.ClickException(f"git pull did not succeed: {said.strip() or 'it said nothing'}")
    click.echo(f"Pulled {found['behind']} commit{'s' if found['behind'] != 1 else ''}")
    if found["dependencies"]:
        _helper(install, found, dry_run=False)
        return
    if updates.restart_service():
        click.echo("The service started again on the new code")
    if found["extension"]:
        click.echo("The VS Code extension changed: uv run python -m tools.extension, then uv run python -m tools.vsix")


def _helper(install: updates.Install, found: dict[str, Any], dry_run: bool) -> None:
    """The tool installed again by a helper once this command has ended (decision 0145)."""
    home = Home.resolve()
    log = home.logs / "update.log"
    windows = sys.platform == "win32"
    script = home.state / ("update-helper.ps1" if windows else "update-helper.sh")
    command = updates.install_command(install, found)
    text = updates.helper_script(command, log, os.getpid(), windows)
    if dry_run:
        click.echo("Would stop the service and the gateway (their files are the tool's), then run this helper:")
        click.echo(text)
        return
    updates.stop_running()
    home.state.mkdir(parents=True, exist_ok=True)
    home.logs.mkdir(parents=True, exist_ok=True)
    script.write_text(text, encoding="utf-8")
    updates.start_helper(script)
    click.echo(f"Updating in the background with: {' '.join(command)}")
    click.echo(f"Each step goes to {log}; Clank's service starts again when it is done (clank status says)")
