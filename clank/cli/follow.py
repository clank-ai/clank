"""Following an operation from the command line (design 0002 §2.4, §2.15): its steps and the log lines each step
writes, as they come, then its end. When it waits for the user's answer, the question is shown with its options and
asked at the terminal, or answered as the command was told (`clank docker stop --yes`); an answer given in another
client meanwhile is reported with who gave it, and the command goes on. Ctrl+C stops following, not the operation.

A command reads the operation and its log a few times a second rather than following the event stream: log lines are
live-only events, so the lines written between starting an operation and a stream connecting would be lost. The
console and VS Code, which follow everything at once, use the stream.
"""

import time
from typing import Any

import click

from clank.cli import common
from clank.client import Client, ClientError

POLL_SECONDS = 0.25
FINISHED = ("done", "failed", "canceled", "interrupted")


def ask(text: str, default: str) -> str:
    """Ask at the terminal (tests replace it)."""
    return str(click.prompt(text, default=default, show_default=True))


def follow(client: Client, operation: dict[str, Any], *, answer: str | None = None) -> dict[str, Any]:
    """Print an operation's steps and log as they come, settle the questions it asks, and return it once it ends."""
    id = operation["id"]
    click.echo(f"{operation['title']} ({id})")
    shown = {"steps": 0, "lines": 0}
    settled: set[str] = set()
    try:
        while True:
            lines = common.call(lambda: client.get(f"operations/{id}/log", after=shown["lines"]))
            current = common.call(lambda: client.get(f"records/operation/{id}"))["values"]
            _show(current, lines, shown)
            waiting_on = current["waiting_on"]
            if current["status"] == "waiting" and waiting_on and waiting_on not in settled:
                settled.add(waiting_on)
                _settle(client, waiting_on, answer)
                continue
            if current["status"] in FINISHED:
                _show(current, common.call(lambda: client.get(f"operations/{id}/log", after=shown["lines"])), shown)
                return dict(current)
            time.sleep(POLL_SECONDS)
    except KeyboardInterrupt:
        click.echo(f"Stopped following; {operation['title']} goes on in the service (`clank operations` shows it).")
        raise click.exceptions.Exit(130) from None


def _show(current: dict[str, Any], lines: list[dict[str, Any]], shown: dict[str, int]) -> None:
    steps = current["steps"]
    for line in lines:
        while shown["steps"] < min(line["step"] or 0, len(steps)):
            _step(steps[shown["steps"]], current["planned_steps"])
            shown["steps"] += 1
        click.echo(f"      {line['text']}")
        shown["lines"] = line["number"]
    while shown["steps"] < len(steps):
        _step(steps[shown["steps"]], current["planned_steps"])
        shown["steps"] += 1


def _step(step: dict[str, Any], planned: int) -> None:
    click.echo(f"  {step['number']} of {planned}: {step['name']}")


def _settle(client: Client, question_id: str, answer: str | None) -> None:
    question = common.call(lambda: client.get(f"records/question/{question_id}"))["values"]
    click.echo(f"  {question['title']}")
    if question["detail"]:
        click.echo(f"  {question['detail']}")
    options: dict[str, str] = {}
    for option in question["options"]:
        key = option["key"] or option["id"]
        options[key] = options[option["id"]] = option["id"]
        click.echo(f"    {key}  {option['label']}" + (f": {option['effect']}" if option["effect"] else ""))
    chosen = answer
    if chosen is None:
        default = next((o["key"] or o["id"] for o in question["options"] if o["id"] == question["default"]), "")
        try:
            chosen = ask("  Your answer", default)
        except click.Abort:
            click.echo(f"  Waiting for an answer from another client, or `clank questions answer {question_id} <key>`")
            return
    try:
        client.post(f"questions/{question_id}/answer", {"option": options.get(chosen.strip(), chosen.strip())})
    except ClientError as error:
        click.echo(f"  {error}")
