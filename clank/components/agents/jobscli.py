"""`clank jobs` (design 0021 §6): the long computations the agents started as jobs, from the command line. With no
command, every workspace's jobs (or one's, `--workspace`), newest first, a line each; `clank jobs show WORKSPACE N`
one whole, its log's last lines and the files it wrote; `clank jobs stop WORKSPACE N` ends one and everything it
started. Each asks the service (`/agents/jobs`), which reads the jobs' files in their folders.
"""

from typing import Any

import click

from clank.cli import common
from clank.components.workspaces.service import jobs as runner


@click.group(invoke_without_command=True)
@click.option("--workspace", default="", help="One workspace's jobs only.")
@click.pass_context
def jobs(context: click.Context, workspace: str) -> None:
    """The jobs the agents started (long computations), newest first."""
    if context.invoked_subcommand is not None:
        return
    client = common.call(common.connect)
    found = common.call(lambda: client.get("agents/jobs", workspace=workspace))["jobs"]
    if not found:
        click.echo("No job yet." if not workspace else f"{workspace} has no job yet.")
    for job in found:
        click.echo(line(job))


@jobs.command()
@click.argument("workspace")
@click.argument("number", type=int)
def show(workspace: str, number: int) -> None:
    """One job whole: its state, its log's last lines and the files it wrote."""
    client = common.call(common.connect)
    job = common.call(lambda: client.post("agents/jobs/status", {"workspace": workspace, "job": number}))
    click.echo(line(job))
    click.echo(f"  command: {job['command']}")
    if job.get("tail"):
        click.echo("  the last lines of its log:")
        for each in str(job["tail"]).splitlines():
            click.echo(f"    {each}")
    if job.get("written"):
        click.echo("  files written since it started: " + ", ".join(job["written"]))


@jobs.command()
@click.argument("workspace")
@click.argument("number", type=int)
def stop(workspace: str, number: int) -> None:
    """End a job and everything it started."""
    client = common.call(common.connect)
    click.echo(common.call(lambda: client.post("agents/jobs/stop", {"workspace": workspace, "job": number}))["said"])


def line(job: dict[str, Any]) -> str:
    """A job in a line: its workspace, number, title, state and how long, and where its log is."""
    ran = runner.span(float(job.get("seconds") or 0))
    state = f"ended, {job['said']}, after {ran}" if job["state"] == "ended" else f"{job['state']} for {ran}"
    return f"{job['workspace']}  job {job['job']}  {job['title']}: {state}  ({job['folder']}/log)"
