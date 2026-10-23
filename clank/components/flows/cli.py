"""The flows component's commands (design 0013 §5-§9): `clank flow`, a flow listed, checked, prepared, run, decided.

`clank flow list|show|check|prepare|run|pause|stop|diff|next` and `clank flow proposals|accept|reject` serve scripts and
back up the Flow view. Each is a client of the API (design 0002 §2.15): readable text, or JSON with `--json`. A flow is
named by its id, `<workspace>/<name>`, or by its name or title in a workspace: the one `--workspace` gives, else the one
whose folder the command runs in. `check` also takes a file's path (a draft, a copy), checked as it is on disk now.
`prepare` lists each box's first message as it would be sent now with its size in tokens against its model's window,
counted or an estimate, and how; with a box, that box's message whole (decision 0087). `run` starts a flow (queued
behind another flow's run when one is active), resumes it when it is paused, or with `--from` runs its latest run again
from a box; `pause` and `stop` steer the run; each says what it did, then each box with its state. `diff` compares two
tries of a box (by default its last two that kept a copy of the file it wrote first): how many lines changed, then the
unified diff. `proposals` lists the boxes a run's boxes proposed, each with its state, and those waiting for you
(`--full`: each whole); `accept` and `reject` decide them by their ids, or all still waiting (`--all`), an acceptance of
one edited first (`--prompt`, `--prompt-file`, `--title`, `--model`, `--mode`). `next` shows the flow made after this
one from its INTEGRATE's brief, or why there is none; `--make` makes it, `--run` runs it (decision 0091). `new [NAME]`
builds a flow with the model (design 0013 §15): a planning session in the workspace's OpenCode, here (OpenCode runs in
this terminal; once it ends, the command says whether the flow was built and how to look at it and run it) or in
Clank's VS Code window (`--vscode`, the default in VS Code's terminal); over SSH always here (`clank.kernel.where`).
`attach` runs OpenCode in this terminal on the workspace's open planning, beside the console (decision 0100), the
one-window rule saying what it closed; `--home` names Clank's home for a terminal that has none set (a Windows Terminal
pane the console split).
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any
from urllib.parse import quote

import click

from clank.cli import common
from clank.kernel.where import where_to_open

WORKSPACE = click.option("-w", "--workspace", default="", help="The flow's workspace; default: this folder's.")
AS_JSON = click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")


@click.group()
def flow() -> None:
    """Flows: the work as a program of boxes, each a fresh session with its own model (design 0013)."""


@flow.command("list")
@WORKSPACE
@AS_JSON
def list_(workspace: str, as_json: bool) -> None:
    """Every flow, by workspace, and the files that do not read."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get("flows", workspace=workspace or None))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    if not found["flows"] and not found["unreadable"]:
        click.echo(
            f"No flows yet. A flow is a file, {found['folder']}{os.sep}<workspace>{os.sep}<name>.json; Clank's "
            f"template, to start one from, is {found['template']}."
        )
        return
    width = max((len(each["id"]) for each in found["flows"]), default=0)
    for each in found["flows"]:
        count = len(each["problems"])
        trouble = f"  {_count(count, 'problem')}: `clank flow check {each['id']}`" if count else ""
        click.echo(f"{each['id'].ljust(width)}  {each['title']}  ({_count(each['boxes'], 'box')}){trouble}")
    for problem in found["unreadable"]:
        click.echo(f"does not read: {_problem(problem)}")


@flow.command()
@WORKSPACE
@AS_JSON
@click.argument("name")
def show(workspace: str, as_json: bool, name: str) -> None:
    """A flow's boxes, each with its type, title, files and what comes after it."""
    client = common.call(common.connect)
    group, own = _named(client, name, workspace)
    found = common.call(lambda: client.get(f"flows/{quote(group, safe='')}/{quote(own, safe='')}"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    values = found["values"]
    place = "yours" if found["source"] == "user" else "Clank's"
    click.echo(f"{found['title']} ({found['id']}, {place}: {found['file']})")
    defaults = values["defaults"]
    limits = defaults["limits"]
    model = defaults["model"] or "what the main slot runs"
    accept = f"auto-accept on, up to {values['auto_accept_cap']}" if values["auto_accept"] else "auto-accept off"
    click.echo(
        f"Each box: {model}, up to {_count(defaults['tries'], 'try')}, {limits['minutes']} minutes and "
        f"{limits['tokens']:,} tokens a try; {accept}."
    )
    click.echo("")
    boxes = values["boxes"]
    width = max(len(box["id"]) for box in boxes)
    title = max(len(box["title"]) for box in boxes)
    for box in boxes:
        row = f"  {box['id'].ljust(width)}  {box['type'].upper():<9}  {box['title'].ljust(title)}"
        click.echo(f"{row}  {'; '.join(_details(box, boxes, values['lines']))}".rstrip())
    click.echo("")
    click.echo(_switches(found))
    for problem in found["problems"]:
        click.echo(f"problem: {_problem(problem)}")


@flow.command()
@WORKSPACE
@AS_JSON
@click.argument("name")
def check(workspace: str, as_json: bool, name: str) -> None:
    """Check a flow's file as it is on disk now, by the flow's name or the file's path: §3's rules, its presets and its
    workspace; then warn, never failing, of a box's first message past a quarter of its window and of a file a box
    sees that nothing gives it."""
    client = common.call(common.connect)
    if os.path.isfile(name):
        body = {"file": os.path.abspath(name)}
    else:
        group, own = _named(client, name, workspace)
        body = {"flow": f"{group}/{own}"}
    found = common.call(lambda: client.post("flows/check", body))
    if as_json:
        click.echo(json.dumps(found, indent=2))
    elif not found["problems"]:
        count = len(found.get("switches") or [])
        switched = (
            f"switches the main slot {_count(count, 'time')} (clank flow show says where)"
            if count
            else ("makes no switch of the main slot")
        )
        click.echo(f"{found['file']}: the flow keeps every rule; a run {switched}.")
    for problem in found["problems"] if not as_json else []:
        click.echo(_problem(problem))
    for warning in found.get("warnings", []) if not as_json else []:
        click.echo(f"warning: {_problem(warning)}")
    if found["problems"]:
        raise click.exceptions.Exit(1)


@flow.command("run")
@WORKSPACE
@AS_JSON
@click.option(
    "--from", "start_from", default="", help="Run the latest run again from this box, and every box after it."
)
@click.argument("name")
def run_(workspace: str, as_json: bool, start_from: str, name: str) -> None:
    """Run a flow: a new run, its paused run resumed, or (--from) its latest run again from a box."""
    client = common.call(common.connect)
    group, own = _named(client, name, workspace)
    path = f"flows/{quote(group, safe='')}/{quote(own, safe='')}/run"
    found = common.call(lambda: client.post(path, {"from": start_from} if start_from else {}))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    run = found["run"]
    named = f"{run['title']} ({run['flow']}#{run['number']})"
    said = {
        "started": f"Started {named}.",
        "queued": f"Started {named}: it waits behind {run['behind']}, since one flow runs at a time.",
        "resumed": f"Resumed {named}.",
        "from": f"{named} runs again from {start_from}.",
    }[found["did"]]
    click.echo(said)
    _boxes(found)


@flow.command()
@WORKSPACE
@AS_JSON
@click.argument("name")
def pause(workspace: str, as_json: bool, name: str) -> None:
    """Pause a flow's run: no box starts; the running one goes on (`clank flow run` resumes it)."""
    found = _steer(name, workspace, "pause")
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    run = found["run"]
    click.echo(
        f"Paused {run['title']} ({run['flow']}#{run['number']}): no box starts, the running one goes on; "
        "`clank flow run` resumes it."
    )
    _boxes(found)


@flow.command()
@WORKSPACE
@AS_JSON
@click.option("--final", "final_review", type=click.Choice(["orchestrator", "owner"]), default=None,
              help="Who decides the last gate: the orchestrator, or you.")  # fmt: skip
@click.option("--model", default=None, help="The preset its checkpoints run on; empty: the flow's.")
@click.option("--role", type=click.Choice(["steer", "watch"]), default=None,
              help="steer: it decides the questions too; watch: it checks each box only (turns it on).")  # fmt: skip
@click.argument("name")
@click.argument("state", required=False, type=click.Choice(["on", "off"]))
def orchestrator(
    workspace: str,
    as_json: bool,
    final_review: str | None,
    model: str | None,
    role: str | None,
    name: str,
    state: str | None,
) -> None:
    """A flow's orchestrator (design 0013 §16): a model that checks the run after each box and tells you what you
    should know at once; steering, it decides each question too. Alone, its settings and the latest run's ledger; `on`
    or `off` turns it on or off, `--role` sets how far it goes, the run going on."""
    client = common.call(common.connect)
    group, own = _named(client, name, workspace)
    path = f"flows/{quote(group, safe='')}/{quote(own, safe='')}/orchestrator"
    if state is None and final_review is None and model is None and role is None:
        found = common.call(lambda: client.get(path))
    else:
        body: dict[str, Any] = {}
        if role is not None:
            body["role"] = role
        if state is not None:
            body["on"] = state == "on"
        if final_review is not None:
            body["final_review"] = final_review
        if model is not None:
            body["model"] = model
        found = common.call(lambda: client.post(path, body))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    settings = found["orchestrator"]
    model_said = f"the preset {settings['model']}" if settings["model"] else "the flow's model"
    if not settings["on"]:
        state_said = "off"
    elif settings.get("role") == "watch":
        state_said = (
            "on, watching: it checks each box is on track, pauses the run or tells you, and decides no question"
        )
    else:
        final = (
            "it decides the last gate too" if settings["final_review"] == "orchestrator" else "the last gate is yours"
        )
        state_said = (
            f"on, steering: {final}; {settings['changes']} changes a run, {settings['extra_tries']} extra tries a box, "
            f"stall at {settings['stall']}"
        )
    click.echo(
        f"The orchestrator of {found['title']} ({found['flow']}) is {state_said}; it runs on {model_said} "
        "(the main slot's, unless the flow names another), and tells you at once what you should know."
    )
    if found["ledger"]:
        click.echo(f"\nThe ledger of run {found['run']}:\n\n{found['ledger']}")


@flow.command()
@WORKSPACE
@AS_JSON
@click.argument("name")
def stop(workspace: str, as_json: bool, name: str) -> None:
    """Stop a flow's run: its running box's session is stopped, and the run ends."""
    found = _steer(name, workspace, "stop")
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    run = found["run"]
    click.echo(f"Stopped {run['title']} ({run['flow']}#{run['number']}).")
    _boxes(found)


@flow.command()
@WORKSPACE
@AS_JSON
@click.option("--path", default="", help="The file to compare; default: the one the box wrote first.")
@click.option("--tries", nargs=2, type=int, default=None, help="The two tries to compare; default: its last two.")
@click.option("--run", "number", type=int, default=0, help="The run; default: the flow's latest.")
@click.argument("name")
@click.argument("box")
def diff(
    workspace: str, as_json: bool, path: str, tries: tuple[int, int] | None, number: int, name: str, box: str
) -> None:
    """Compare two tries of a box: how many lines of its file changed, then the diff (design 0013 §8)."""
    client = common.call(common.connect)
    group, own = _named(client, name, workspace)
    asked: dict[str, Any] = {"box": box, "file": path or None, "run": number or None}
    if tries:
        asked |= {"a": tries[0], "b": tries[1]}
    found = common.call(lambda: client.get(f"flows/{quote(group, safe='')}/{quote(own, safe='')}/diff", **asked))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    said = found["said"].removeprefix(f"{found['path']} of {found['box']}: ")
    click.echo(
        f"{found['path']} of {found['box']}, try {found['b']} against try {found['a']} "
        f"({found['flow']}#{found['run']}): {said}."
    )
    if found["diff"]:
        click.echo("")
        click.echo(found["diff"].rstrip("\n"))


@flow.command()
@WORKSPACE
@AS_JSON
@click.argument("name")
@click.argument("box", required=False, default="")
def prepare(workspace: str, as_json: bool, name: str, box: str) -> None:
    """Each box's first message as it would be sent now, with its size against its model's window (design 0013 §5):
    every box listed, or one box's message whole. It changes nothing."""
    client = common.call(common.connect)
    group, own = _named(client, name, workspace)
    path = f"flows/{quote(group, safe='')}/{quote(own, safe='')}/prepare"
    found = common.call(lambda: client.get(path, box=box or None))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    if box:
        shown = found["boxes"][0]
        click.echo(shown["text"].rstrip("\n"))
        click.echo("")
        click.echo(f"{shown['box']} ({shown['type'].upper()}), try {shown['try']}: {_size(shown)}.")
    else:
        run = f", in run {found['run']}" if found["run"] else ""
        click.echo(
            f"{found['title']} ({found['flow']}): each box's first message as it would be sent now, from the files as "
            f"they are now{run}."
        )
        click.echo("")
        width = max((len(each["box"]) for each in found["boxes"]), default=0)
        for each in found["boxes"]:
            said = "counted" if each["exact"] else "an estimate"
            row = f"  {each['box'].ljust(width)}  {each['type'].upper():<9}  try {each['try']}  "
            click.echo(f"{row}{each['tokens']:>8,} tokens, {said}  {_window(each)}")
        click.echo("")
        click.echo("How each was counted:")
        ways: dict[str, list[str]] = {}
        for each in found["boxes"]:
            ways.setdefault(each["counted"], []).append(each["box"])
        for way, boxes in ways.items():
            click.echo(f"- {', '.join(boxes)}: {way}")
    click.echo("")
    for line in found["said"]:
        click.echo(line)
    if not box:
        click.echo(f"`clank flow prepare {name} <box>` shows a box's first message whole.")


def _size(shown: dict[str, Any]) -> str:
    """A first message's size, how it was counted, and its window."""
    return f"{shown['tokens']:,} tokens ({shown['counted']}); {_window(shown)}"


def _window(shown: dict[str, Any]) -> str:
    """A first message's share of its window, or why its window is not known; past a quarter, said so."""
    if shown["window"] is None:
        return str(shown["window_said"])
    over = ": over a quarter of its window" if shown["over"] else ""
    return f"{shown['share']:.1%} of {shown['window']:,} ({shown['preset_title']}){over}"


@flow.command("next")
@WORKSPACE
@AS_JSON
@click.option("--make", is_flag=True, help="Make it now, when it has none, from the latest run's INTEGRATE's brief.")
@click.option("--run", "run_it", is_flag=True, help="Run it now, making it first when it has none.")
@click.argument("name")
def next_(workspace: str, as_json: bool, make: bool, run_it: bool, name: str) -> None:
    """The flow made after this one from its INTEGRATE's brief (design 0013 §3): shown, made, or run."""
    client = common.call(common.connect)
    group, own = _named(client, name, workspace)
    path = f"flows/{quote(group, safe='')}/{quote(own, safe='')}/next"
    if make or run_it:
        found = common.call(lambda: client.post(path, {"run": run_it}))
    else:
        found = common.call(lambda: client.get(path))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    named = f"{found['title'] or own} ({found['flow']})"
    following = found["next"]
    if following is None:
        click.echo(f"{named} has no next flow: {found['why']}.")
        return
    came = ""
    if following["brief"]:
        came = f", from {following['brief']}, which {following['by']} wrote in run {following['run']}"
    if run_it:
        click.echo(f"Started {following['title']} ({following['id']}): its brief waits for you at its first box.")
    click.echo(f"{named} is followed by {following['title']} ({following['id']}){came}.")
    if following["runs"] and not run_it:
        click.echo(f"It has run {_count(following['runs'], 'time')}: `clank flow show {following['id']}`.")
    elif found["waiting"]:
        click.echo(f"It has not run yet; a question asks whether to run it now, or `clank flow next {name} --run`.")
    else:
        click.echo(f"It has not run yet: `clank flow run {following['id']}` runs it.")


@flow.command()
@WORKSPACE
@click.option("--here", "where", flag_value="here", help="OpenCode in this terminal, on the planning session.")
@click.option("--vscode", "where", flag_value="vscode", help="In Clank's VS Code window, OpenCode in its terminal.")
@click.option("--set-aside", "aside", is_flag=True, help="Set the planning open in the workspace aside, to start this.")
@click.argument("name", required=False, default="")
def new(workspace: str, where: str | None, aside: bool, name: str) -> None:
    """Build a flow with the model, by talking it through (design 0013 §15): a planning session in the workspace's
    OpenCode, here (the default, and always over SSH) or in Clank's VS Code window (the default in VS Code's terminal).
    The model reads the folder, asks you, writes BRIEF.md with you and drafts the flow; Clank checks and writes it."""
    client = common.call(common.connect)
    chosen, said = where_to_open(where or "", os.environ)
    if said:
        click.echo(said)
    body = {"folder": os.getcwd(), "workspace": workspace, "name": name, "where": chosen, "aside": aside}
    found = common.call(lambda: client.post("flows/new", body))
    flow = found["flow"]
    click.echo(f"Building {flow} with the model; its session's first message is {found['first_message']}.")
    if chosen == "vscode":
        open_vscode(client, found["folder"])
        if found["window"] == "running":
            click.echo("Clank's VS Code window comes forward: its OpenCode shows the planning session.")
        else:
            click.echo("Clank's VS Code window opens: OpenCode starts in its terminal and shows the planning session.")
        click.echo(f"Once the model wrote the flow: look, then r to run ({LOOK}), or `clank flow run {flow}`.")
        return
    for note in found.get("notes") or []:
        click.echo(f"  {note}")
    title = found.get("title") or f"{found['name']} · building the flow"
    click.echo(
        f"OpenCode opens here on the planning session ({found.get('model') or 'the model Clank runs'}), "
        f"“{title}”: if it opens on another, pick it from OpenCode's session list (/sessions). Talk it through, "
        "then leave OpenCode (/exit) to come back."
    )
    terminal(found["argv"])
    _after(client, flow, title)


@flow.command()
@WORKSPACE
@click.option("--home", default="", help="Clank's home (CLANK_HOME), for a terminal that does not have it set.")
def attach(workspace: str, home: str) -> None:
    """Talk with the model on the open planning, beside the console (design 0013 §15): OpenCode in this terminal on
    the planning session of this folder's workspace (or --workspace's), back here when OpenCode ends. One OpenCode
    window at a time in a workspace: another open there is closed first, and said."""
    if home:
        os.environ["CLANK_HOME"] = home  # a Windows Terminal pane does not inherit the console's environment
    client = common.call(common.connect)
    found = common.call(lambda: client.post("flows/attach", {"folder": os.getcwd(), "workspace": workspace}))
    flow, title = str(found["flow"]), str(found.get("title") or f"{found['name']} · building the flow")
    for note in found.get("notes") or []:
        click.echo(f"  {note}")
    state = {"waiting": "its session starts there", "opening": "its session is being started"}.get(
        str(found.get("status")), "its session is shown there"
    )
    click.echo(
        f"OpenCode opens here on the planning of {flow} ({found.get('model') or 'the model Clank runs'}), “{title}”: "
        f"{state}; if it opens on another, pick it from OpenCode's session list (/sessions). Leave OpenCode (/exit) to "
        "come back."
    )
    terminal(found["argv"])
    _after(client, flow, title)


def _after(client: Any, flow: str, title: str) -> None:
    """Once OpenCode ended: whether the flow was built, and how to look and run it; else why not."""
    planning = common.call(lambda: client.get("flows/building", flow=flow)).get("planning") or {}
    if planning.get("status") in ("built", "ran"):
        click.echo(f"{flow}: flow built: look, then r to run ({LOOK}), or `clank flow run {flow}`.")
    elif planning.get("status") == "failed":
        click.echo(
            f"{flow} is not built: its planning session did not start: {planning.get('why') or 'no reason given'}. "
            "`clank flow new` opens another planning."
        )
    else:
        state = planning.get("status") or "gone"
        why = f": {planning['why']}" if planning.get("why") else ""
        click.echo(
            f"{flow} is not built yet ({state}{why}). Its session, “{title}”, stays in OpenCode's list of "
            "sessions; `clank flow attach` opens it again, `clank flow new` opens another planning."
        )


LOOK = "in the console's Flow view: F10, or `clank console --page monitor --view flow`"


def terminal(argv: list[str]) -> int:
    """Run a command attached to this terminal (OpenCode, on the planning session); its exit status."""
    return subprocess.call(list(argv))


def open_vscode(client: Any, folder: str) -> None:
    """Open the folder in Clank's VS Code window, where Clank's extension starts OpenCode beside the files."""
    common.call(lambda: client.post("agents/vscode", {"folder": folder}))


RUN = click.option("--run", "number", type=int, default=0, help="The run; default: the flow's latest.")
EVERY = click.option("--all", "every", is_flag=True, help="Every proposal still waiting for you.")


@flow.command()
@WORKSPACE
@AS_JSON
@RUN
@click.option("--full", is_flag=True, help="Each proposal whole: its prompt, what it sees, what to accept, why.")
@click.argument("name")
def proposals(workspace: str, as_json: bool, number: int, full: bool, name: str) -> None:
    """The boxes a flow's run proposed (design 0013 §9): each with its state, and those waiting for you."""
    client = common.call(common.connect)
    group, own = _named(client, name, workspace)
    path = f"flows/{quote(group, safe='')}/{quote(own, safe='')}/proposals"
    found = common.call(lambda: client.get(path, run=number or None))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    title = found.get("title") or own
    if found["run"] is None:
        click.echo(f"{title} has not run yet: it has no proposals.")
        return
    named = f"{title} ({found['flow']}#{found['run']})"
    batches = [batch for batch in found["batches"] if batch["proposals"]]
    if not batches:
        click.echo(f"{named} has no proposals.")
        return
    click.echo(f"Proposals of {named}:")
    for batch in batches:
        click.echo("")
        summary = f": {batch['summary']}" if batch["summary"] else "."
        state = f"submitted{summary}" if batch["submitted"] else "not submitted yet."
        click.echo(f"From {batch['box']}, try {batch['try']}, {state}")
        _proposals(batch["proposals"], full)
    click.echo("")
    waiting = found["waiting"]
    if waiting:
        click.echo(
            f"Waiting for you: {', '.join(waiting)}. `clank flow accept {name} <id>` or `clank flow reject {name} "
            "<id>`, or --all for each."
        )
    else:
        click.echo("None waits for you.")


@flow.command()
@WORKSPACE
@AS_JSON
@RUN
@EVERY
@click.option("--prompt", default=None, help="Edit the one proposal accepted first: its prompt.")
@click.option(
    "--prompt-file", type=click.Path(exists=True, dir_okay=False), default=None, help="Its prompt, from a file."
)
@click.option("--title", default=None, help="Edit it first: its title.")
@click.option("--model", default=None, help="Edit it first: the preset it runs on.")
@click.option("--mode", default=None, help="Edit it first: plan, review or auto (empty: the box's own).")
@click.argument("name")
@click.argument("ids", nargs=-1)
def accept(
    workspace: str, as_json: bool, number: int, every: bool, prompt: str | None, prompt_file: str | None,
    title: str | None, model: str | None, mode: str | None, name: str, ids: tuple[str, ...],
) -> None:  # fmt: skip
    """Accept proposals by their ids (T1 T2), or --all: they join the flow's file; one may be edited first."""
    changes: dict[str, Any] = {
        key: value for key, value in (("prompt", prompt), ("title", title), ("model", model), ("mode", mode))
        if value is not None
    }  # fmt: skip
    if prompt_file:
        changes["prompt"] = Path(prompt_file).read_text(encoding="utf-8")
    found = _decide(name, workspace, "accept", ids, every, number, changes)
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    decided = found["decided"]
    joins = "they join" if len(decided) > 1 else "it joins"
    click.echo(f"Accepted {', '.join(decided)}{', edited' if changes else ''}: {joins} {found['title']}'s flow.")


@flow.command()
@WORKSPACE
@AS_JSON
@RUN
@EVERY
@click.argument("name")
@click.argument("ids", nargs=-1)
def reject(workspace: str, as_json: bool, number: int, every: bool, name: str, ids: tuple[str, ...]) -> None:
    """Reject proposals by their ids (T1 T2), or --all: none of them ever runs."""
    found = _decide(name, workspace, "reject", ids, every, number)
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    click.echo(f"Rejected {', '.join(found['decided'])}.")


def _decide(
    name: str,
    workspace: str,
    decision: str,
    ids: tuple[str, ...],
    every: bool,
    number: int,
    changes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not ids and not every:
        click.echo(f"Name the proposals to {decision} (T1 T2), or --all.")
        raise click.exceptions.Exit(1)
    client = common.call(common.connect)
    group, own = _named(client, name, workspace)
    path = f"flows/{quote(group, safe='')}/{quote(own, safe='')}/proposals/{decision}"
    body = {"proposals": list(ids), "all": every, "run": number, "changes": changes or {}}
    found: dict[str, Any] = common.call(lambda: client.post(path, body))
    return found


def _proposals(proposals: list[dict[str, Any]], full: bool) -> None:
    """A batch's proposals, a row each: its place, id, type, title, the box it follows, its state, its deliverable."""
    width = max(len(each["id"]) for each in proposals)
    titles = max(len(each["box"]["title"]) for each in proposals)
    afters = max(len(each["after"]) for each in proposals)
    for each in proposals:
        box = each["box"]
        row = (
            f"  {each['number']}  {each['id'].ljust(width)}  {box['type'].upper():<9}  {box['title'].ljust(titles)}  "
            f"after {each['after'].ljust(afters)}  {each['state']:<8}"
        )
        row += f"  writes {', '.join(box['writes'])}" if box["writes"] else ""
        click.echo(row.rstrip())
        if each.get("said"):
            click.echo(f"     {each['said']}")
        if full:
            _whole(each)


def _whole(proposal: dict[str, Any]) -> None:
    """A proposal whole: its prompt, what it sees, what to accept, its model and mode, why, and what you changed."""
    box = proposal["box"]
    click.echo("")
    for line in box["prompt"].splitlines():
        click.echo(f"     {line}")
    click.echo("")
    for key, words in (("sees", "sees"), ("accept_when", "accepted when")):
        if box.get(key):
            click.echo(f"     {words}: {'; '.join(box[key])}")
    for key in ("model", "mode"):
        if box.get(key):
            click.echo(f"     {key}: {box[key]}")
    if proposal.get("why"):
        click.echo(f"     why: {proposal['why']}")
    original = proposal.get("original")
    if original and original.get("prompt") != box["prompt"]:
        click.echo("     you changed its prompt; the model proposed:")
        for line in original["prompt"].splitlines():
            click.echo(f"       {line}")
    click.echo("")


def _steer(name: str, workspace: str, action: str) -> dict[str, Any]:
    client = common.call(common.connect)
    group, own = _named(client, name, workspace)
    found: dict[str, Any] = common.call(
        lambda: client.post(f"flows/{quote(group, safe='')}/{quote(own, safe='')}/{action}")
    )
    return found


def _boxes(found: dict[str, Any]) -> None:
    """Each box of the run, in the order they run: its state, its last try, and where the run is."""
    run = found["run"]
    width = max((len(name) for name in found["order"]), default=0)
    click.echo("")
    for name in found["order"]:
        state = run["boxes"].get(name) or {"state": "waiting", "tries": [], "why": ""}
        kind = found.get("types", {}).get(name, "").upper()
        row = f"  {name.ljust(width)}  {kind:<9}  {state['state']:<8}"
        if state["tries"]:
            last = state["tries"][-1]
            row += f"  try {last['number']}" + (f": {last['outcome']}" if last.get("outcome") else "")
        if state.get("why"):
            row += f" ({state['why']})"
        if name == run["at"] and run["status"] in ("queued", "running"):
            row += "  <- here"
        click.echo(row.rstrip())


def _named(client: Any, name: str, workspace: str) -> tuple[str, str]:
    """A flow's workspace and name: from its id, else from `--workspace` or the folder the command runs in."""
    group, slash, own = name.partition("/")
    if slash:
        return group, own
    if not workspace:
        workspace = common.call(lambda: client.get("flows", folder=os.getcwd()))["workspace"] or ""
    if not workspace:
        click.echo(f"{os.getcwd()} is in no workspace: name the flow's with --workspace, or as <workspace>/{name}")
        raise click.exceptions.Exit(1)
    return workspace, name


def _switches(found: dict[str, Any]) -> str:
    """The switches of the main slot a run makes, from what it runs now (design 0013 §7): before which box, to which
    preset, and how long that preset's last whole switch here took (else its engine's last start to ready)."""
    now = found.get("running_title") or "nothing"
    planned = found.get("switches") or []
    if not planned:
        return f"A run makes no switch of the main slot: each box runs on what it runs now ({now})."
    each = [f"before {switch['box']}, to {switch['title']} ({_took(switch)})" for switch in planned]
    times = _count(len(planned), "time")
    return f"A run switches the main slot {times}, from what it runs now ({now}): {'; '.join(each)}."


def _took(switch: dict[str, Any]) -> str:
    """How long a switch's preset last took to come in here, as the flow's view says it."""
    if switch.get("seconds") is None:
        return "not loaded here yet"
    if switch.get("whole"):
        return f"its last switch here took {switch['seconds']:.0f} s"
    return f"its engine last started here in {switch['seconds']:.0f} s"


def _details(box: dict[str, Any], boxes: list[dict[str, Any]], lines: list[dict[str, Any]]) -> list[str]:
    """What a box's row says after its title: its model and mode, the files it checks, sees, shows and writes, and the
    boxes after it (a DECOMPOSE's task: the next of its tasks, in the order of the boxes)."""
    found = []
    for key, words in (("model", "on"), ("mode", "mode"), ("checks", "checks")):
        if box.get(key):
            found.append(f"{words} {box[key]}")
    for key in ("sees", "shows", "writes"):
        if box.get(key):
            found.append(f"{key} {', '.join(box[key])}")
    leaving = [line for line in lines if line["from"] == box["id"]]
    on = [line["to"] for line in leaving if line.get("when") != "fail"]
    fan = _fan_of(box["id"], boxes, lines)
    if fan and fan.index(box["id"]) + 1 < len(fan):
        on = [fan[fan.index(box["id"]) + 1]]
    back = [line["to"] for line in leaving if line.get("when") == "fail"]
    if box["type"] == "verify":
        found += [f"pass: {', '.join(on)}"] if on else []
        found += [f"fail: back to {', '.join(back)}"] if back else []
    elif len(on) > 1:
        found.append(f"then {', '.join(on)}, one after another")
    elif on:
        found.append(f"then {on[0]}")
    return found


def _fan_of(name: str, boxes: list[dict[str, Any]], lines: list[dict[str, Any]]) -> list[str]:
    """The tasks a box is one of, when a DECOMPOSE fans out to it, in the order they run; else none."""
    into = [line["from"] for line in lines if line["to"] == name and line.get("when") != "fail"]
    if len(into) != 1:
        return []
    tasks = {line["to"] for line in lines if line["from"] == into[0] and line.get("when") != "fail"}
    return [box["id"] for box in boxes if box["id"] in tasks] if len(tasks) > 1 else []


def _problem(problem: dict[str, Any]) -> str:
    where = [problem["file"]]
    where += [f"line {problem['line']}"] if problem["line"] else []
    where += [problem["field"]] if problem["field"] else []
    return f"{', '.join(where)}: {problem['message']}"


def _count(number: int, word: str) -> str:
    plural = {"box": "boxes", "try": "tries"}.get(word, f"{word}s")
    return f"{number:,} {word if number == 1 else plural}"
