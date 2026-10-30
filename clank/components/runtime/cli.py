"""The runtime component's commands (design 0003 §8.4): `clank model status|load|unload|switch|download|adopt|remove`
(and `add`, design 0016 §16, in `addcli.py`), `clank preset list|show|check|change`, `clank host list|add`, `clank
engine list|install|adopt|uninstall`.

Each is a client of the API (design 0002 §2.15): readable text by default, JSON with `--json`. A preset is named by its
id or its title; `clank preset show` prints its settings and the sampling it gives its engine, each value it sets or
else the engine's own default in words (design 0003 §4.1); `clank preset change` changes a cloud preset's most output,
context or thinking effort and prints what the service says it did (design 0016 §7, §16).
"""

import json
from typing import Any, get_args
from urllib.parse import quote

import click

from clank.cli import common, follow
from clank.components.runtime.addcli import add_model
from clank.components.runtime.catalog import ModelFileEntry, size_text
from clank.console.text import count

FORMATS = list(get_args(ModelFileEntry.model_fields["format"].annotation))
ROLES = list(get_args(ModelFileEntry.model_fields["role"].annotation))


@click.group()
def model() -> None:
    """What runs in each slot, loading, unloading and switching presets, and the models' files on each host."""


@model.command()
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def status(as_json: bool) -> None:
    """Each slot: its state since when and why, and what it runs."""
    client = common.call(common.connect)
    slots = common.call(lambda: client.get("runtime/slots"))
    if as_json:
        click.echo(json.dumps(slots, indent=2))
        return
    titles = {entry["id"]: entry for entry in common.call(lambda: client.get("runtime/presets"))}
    for slot in slots:
        preset = titles.get(slot["preset"] or "")
        if slot["status"] in ("stopped", "failed") and preset is None:
            click.echo(f"{slot['name']}  {slot['status']}  since {common.local_time(slot['since'])}: {slot['reason']}")
            continue
        title = preset["title"] if preset else slot["preset"]
        where = (
            f"({preset['engine']} {preset['engine_version']} on {slot['host']}, port {slot['port']})"
            if preset and slot["host"]
            else ""
        )
        since = common.local_time(slot["since"])
        click.echo(f"{slot['name']}  {slot['status']}  {title}  {where}  since {since}: {slot['reason']}".strip())


@model.command()
@click.argument("preset")
@click.option("--slot", default="main", show_default=True, help="The slot to load it in.")
@click.option("--anyway", is_flag=True, help="Start it even when the fit check says it does not fit.")
def load(preset: str, slot: str, anyway: bool) -> None:
    """Start a preset in an empty slot, and follow it until it answers."""
    client = common.call(common.connect)
    body = {"preset": preset, "anyway": anyway}
    _report(follow.follow(client, common.call(lambda: client.post(f"runtime/slots/{slot}/load", body))), preset)


@model.command()
@click.argument("preset")
@click.option("--slot", default="main", show_default=True, help="The slot to switch.")
@click.option("--anyway", is_flag=True, help="Start it even when the fit check says it does not fit.")
def switch(preset: str, slot: str, anyway: bool) -> None:
    """Stop what a slot runs and start a preset; back to the last that worked if it fails."""
    client = common.call(common.connect)
    body = {"preset": preset, "anyway": anyway}
    _report(follow.follow(client, common.call(lambda: client.post(f"runtime/slots/{slot}/switch", body))), preset)


@model.command()
@click.option("--slot", default="main", show_default=True, help="The slot to unload.")
def unload(slot: str) -> None:
    """Stop what a slot runs."""
    client = common.call(common.connect)
    _report(follow.follow(client, common.call(lambda: client.post(f"runtime/slots/{slot}/unload"))), "")


@model.command("download")
@click.argument("name")
@click.option("--format", "form", required=True, type=click.Choice(FORMATS), help="The file's format.")
@click.option("--role", default="weights", show_default=True, type=click.Choice(ROLES))
@click.option("--host", "host_name", required=True, help="Where, as `clank host list` names it.")
@click.option("--yes", is_flag=True, help="Download it without asking first.")
@click.option("--limit", type=float, default=0, help="At most this many MB/s, so the network stays usable.")
def download(name: str, form: str, role: str, host_name: str, yes: bool, limit: float) -> None:
    """Download one of a catalog model's files to a host; it goes on from what an earlier download fetched, and is
    used only once its SHA-256 is the catalog's."""
    client = common.call(common.connect)
    body = {"model": name, "format": form, "role": role, "host": host_name, "yes": yes, "limit": limit}
    result = _ended(follow.follow(client, common.call(lambda: client.post("runtime/downloads", body))))
    already = "" if result["fetched"] else ", already there"
    click.echo(f"{result['file']} is on {result['host']} at {result['path']}{already}")


@model.command("adopt")
@click.argument("name")
@click.option("--format", "form", required=True, type=click.Choice(FORMATS), help="The file's format.")
@click.option("--role", default="weights", show_default=True, type=click.Choice(ROLES))
@click.option("--host", "host_name", required=True, help="Where it is, as `clank host list` names it.")
@click.option("--path", required=True, help="Where it is on that host.")
def adopt_file(name: str, form: str, role: str, host_name: str, path: str) -> None:
    """Adopt a model's file you already have, where it is, once its size and SHA-256 are the catalog's."""
    client = common.call(common.connect)
    body = {"model": name, "format": form, "role": role, "host": host_name, "path": path}
    result = _ended(follow.follow(client, common.call(lambda: client.post("runtime/model-files", body))))
    click.echo(f"{result['file']} is adopted on {result['host']} at {result['path']}")


@model.command("remove")
@click.argument("name")
@click.option("--host", "host_name", required=True, help="Where, as `clank host list` names it.")
@click.option("--format", "form", type=click.Choice(FORMATS), help="Only its files in this format.")
@click.option("--role", type=click.Choice(ROLES), help="Only its files of this role.")
@click.option("--yes", is_flag=True, help="Remove them without asking first.")
def remove(name: str, host_name: str, form: str | None, role: str | None, yes: bool) -> None:
    """Remove a catalog model's files from a host, freeing its disk; the catalog keeps the model and every preset stays,
    so `clank model download` brings them back. A file you keep elsewhere is only forgotten, never deleted."""
    client = common.call(common.connect)
    body = {"model": name, "host": host_name, "format": form, "role": role, "yes": yes}
    result = _ended(follow.follow(client, common.call(lambda: client.post("runtime/model-files/remove", body))))
    removed, forgotten = result["removed"], result["forgotten"]
    if removed:
        freed = size_text(result["freed"])
        click.echo(f"Removed {count(len(removed), 'file')} of {result['name']} from {result['host']}, {freed} freed.")
        click.echo("To bring it back: " + "; ".join(result["restore"]))
    if forgotten:
        stay = "it stays where it is" if len(forgotten) == 1 else "they stay where they are"
        files = count(len(forgotten), "file")
        click.echo(f"Clank forgot {files} of {result['name']} on {result['host']}; {stay}: {', '.join(forgotten)}")
    if not removed and not forgotten:
        click.echo(f"Nothing of {result['name']} is on {result['host']}.")


def _ended(operation: dict[str, Any]) -> dict[str, Any]:
    """The result of an operation that ended well; else its error said, and exit 1."""
    if operation["status"] != "done":
        click.echo(f"{operation['title']}: {operation['error'] or operation['status']}")
        raise click.exceptions.Exit(1)
    return dict(operation.get("result") or {})


def _report(operation: dict[str, Any], preset: str) -> None:
    result = operation.get("result") or {}
    if operation["status"] != "done":
        click.echo(f"{operation['title']}: {operation['error'] or operation['status']}")
        raise click.exceptions.Exit(1)
    if "stopped" in result:
        click.echo(f"{result['slot']}: stopped ({result['stopped']})")
        return
    measured = result.get("measured_mib")
    memory = f"; GPU memory {measured:,} MiB (estimated {result['estimate_mib']:,})" if measured is not None else ""
    click.echo(f"{result['slot']}: {preset} is ready in {result['seconds']:.0f} s{memory}")


@click.group()
def preset() -> None:
    """The presets: saved launch configurations of a serving setup and a model."""


@preset.command("list")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def list_presets(as_json: bool) -> None:
    """Every preset, Clank's own and yours."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get("runtime/presets"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    if not found:
        click.echo("No preset yet.")
        return
    width = max(len(entry["title"]) for entry in found)
    for entry in found:
        setup = entry.get("provider") if entry.get("endpoint") else f"{entry['engine']} {entry['engine_version']}"
        count = len(entry["problems"])
        trouble = f"  cannot run: {count} problem{'s' if count > 1 else ''}" if count else ""
        click.echo(f"{entry['title'].ljust(width)}  {setup:<28}  {entry['model']:<16}  ({entry['source']}){trouble}")


@preset.command()
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def show(name: str, as_json: bool) -> None:
    """One preset: its serving setup, model and options."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get(f"runtime/presets/{quote(name, safe='')}"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    click.echo(f"{found['title']}  ({found['source']}, {found['file']})")
    if found.get("endpoint"):  # a cloud preset: its provider, and its price as the service says it (design 0016 §7)
        price = f": {found['price_said']}" if found.get("price_said") else ""
        click.echo(f"  provider       {found.get('provider') or 'cloud ' + found['endpoint']}{price}")
    else:
        click.echo(f"  serving setup  {found['engine']} {found['engine_version']}")
    click.echo(f"  model          {found['model']}")
    click.echo(f"  slot           {found['slot']}")
    for key, value in found["options"].items():
        click.echo(f"  {key}: {json.dumps(value) if not isinstance(value, str) else value}")
    if found["notes"]:
        click.echo(f"  notes: {found['notes']}")
    for problem in found["problems"]:
        click.echo(f"  cannot run: {problem}")
    if found.get("sampling"):
        click.echo("  sampling (a request's own values win over these):")
        for each in found["sampling"]:
            click.echo(f"    {each['key'].removeprefix('sampling.'):<18} {sampling_text(each)}")


@preset.command("change")
@click.argument("name")
@click.option("--output", "max_output", type=click.IntRange(min=1), help="Its most output, in tokens: its thinking "
              "and its answer together.")  # fmt: skip
@click.option("--context", type=click.IntRange(min=1), help="Its context, in tokens.")
@click.option("--reasoning", help="Its thinking effort: default, or one its model takes.")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def change_preset(name: str, max_output: int | None, context: int | None, reasoning: str | None, as_json: bool) -> None:
    """Change a cloud preset's most output, context or thinking effort, within its model's limits; the main slot
    follows at once when it runs it, and OpenCode windows open now keep their limits until they start again."""
    body = {"max_output": max_output, "context": context, "reasoning": reasoning}
    wanted = {key: value for key, value in body.items() if value is not None}
    if not wanted:
        raise click.UsageError("give --output, --context or --reasoning: what to change")
    client = common.call(common.connect)
    found = common.call(lambda: client.patch(f"runtime/presets/{quote(name, safe='')}", wanted))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    for line in found["said"]:
        click.echo(line)


def sampling_text(option: dict[str, Any]) -> str:
    """A sampling option in effect, as people read it: its value and that the preset sets it, else the engine's own
    default in words (design 0003 §4.1)."""
    if option["value"] is not None:
        return f"{option['value']} (the preset)" if option["source"] == "preset" else f"{option['value']}"
    words = option["engine_default_words"]
    return f"the engine's own: {words}" if words else "(not set)"


@click.group()
def host() -> None:
    """Where engines run: this machine, and its WSL distributions."""


@host.command("list")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def list_hosts(as_json: bool) -> None:
    """Every host, with its kind and its Clank folder."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get("runtime/hosts"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    kinds = [f"WSL: {entry['distro']}" if entry["adapter"] == "wsl" else "this machine" for entry in found]
    width = max(len(entry["name"]) for entry in found)
    kind_width = max(len(kind) for kind in kinds)
    for entry, kind in zip(found, kinds, strict=True):
        click.echo(f"{entry['name'].ljust(width)}  {kind.ljust(kind_width)}  {entry['clank_folder']}")


@host.command("add")
@click.argument("name")
@click.option("--wsl", "distro", required=True, help="The WSL distribution, as `wsl --list` names it.")
@click.option("--folder", default="~/.clank", show_default=True, help="Its Clank folder, for engines and models.")
def add_host(name: str, distro: str, folder: str) -> None:
    """Add a WSL distribution as a host."""
    client = common.call(common.connect)
    body = {"id": name, "adapter": "wsl", "distro": distro, "clank_folder": folder}
    added = common.call(lambda: client.post("runtime/hosts", body))
    click.echo(f"Added the host {added['name']}: WSL's {added['distro']}, its Clank folder {added['clank_folder']}")


@preset.command("check")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def check_preset(name: str, as_json: bool) -> None:
    """Check a preset without starting it: valid, installed, its files there, its flags known, its fit."""
    client = common.call(common.connect)
    found = common.call(lambda: client.post(f"runtime/presets/{quote(name, safe='')}/check"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
    else:
        marks = {"passed": "ok  ", "failed": "FAIL", "unknown": "?   "}
        for item in found:
            click.echo(f"{marks[item['status']]}  {item['name']:<9}  {item['detail']}")
    if any(item["status"] == "failed" for item in found):
        raise SystemExit(1)


@click.group()
def engine() -> None:
    """The serving setups' engines: where each version is installed, and installing one by Clank's recipe."""


@engine.command("list")
@click.option("--json", "as_json", is_flag=True, help="Print JSON, for scripts and models.")
def list_engines(as_json: bool) -> None:
    """Each serving setup's versions: where each is installed and how, and which Clank has a recipe for."""
    client = common.call(common.connect)
    found = common.call(lambda: client.get("runtime/engines"))
    if as_json:
        click.echo(json.dumps(found, indent=2))
        return
    for entry in found:
        for version in entry["versions"]:
            where = sorted(f"{one['host']} ({one['how']})" for one in entry["installs"] if one["version"] == version)
            installed = f"on {', '.join(where)}" if where else "not installed"
            recipe = "; Clank has its recipe" if version in entry["recipes"] else ""
            click.echo(f"{entry['name']}  {version}  {installed}{recipe}")


@engine.command("install")
@click.argument("setup")
@click.option("--version", "version", required=True, help="The version, as `clank engine list` shows it.")
@click.option("--host", "host_name", required=True, help="Where, as `clank host list` names it.")
@click.option("--yes", is_flag=True, help="Install it without asking first.")
def install(setup: str, version: str, host_name: str, yes: bool) -> None:
    """Install an engine on a host by Clank's recipe for it, following each step; it asks first unless told --yes."""
    client = common.call(common.connect)
    body = {"setup": setup, "version": version, "host": host_name, "yes": yes}
    done = follow.follow(client, common.call(lambda: client.post("runtime/installs", body)))
    if done["status"] != "done":
        click.echo(f"{done['title']}: {done['error'] or done['status']}")
        raise click.exceptions.Exit(1)
    result = done["result"]
    click.echo(f"{result['title']} is installed on {result['host']}, in {result['folder']}")


@engine.command("adopt")
@click.argument("setup")
@click.option("--version", "version", required=True, help="The version it is, as `clank engine list` shows it.")
@click.option("--host", "host_name", required=True, help="Where it is, as `clank host list` names it.")
@click.option("--program", required=True, help="Its program, a path on the host.")
@click.option("--folder", required=True, help="The folder it runs in.")
@click.option("--source", default="", help="The git checkout it was built from, when it is not its folder.")
@click.option("--library-path", default="", help="Its libraries' folders (for LD_LIBRARY_PATH), separated by `:`.")
def adopt(setup: str, version: str, host_name: str, program: str, folder: str, source: str, library_path: str) -> None:
    """Adopt an engine already built, where it is, once its flags and the commit it was built from are checked."""
    client = common.call(common.connect)
    body = {"setup": setup, "version": version, "host": host_name, "program": [program], "folder": folder,
            "source": source, "library_path": library_path}  # fmt: skip
    done = follow.follow(client, common.call(lambda: client.post("runtime/installs/adopt", body)))
    if done["status"] != "done":
        click.echo(f"{done['title']}: {done['error'] or done['status']}")
        raise click.exceptions.Exit(1)
    result = done["result"]
    click.echo(f"{result['title']} is adopted on {result['host']}, where it is: {result['folder']}")


@engine.command("uninstall")
@click.argument("setup")
@click.option("--version", "version", required=True, help="The version, as `clank engine list` shows it.")
@click.option("--host", "host_name", required=True, help="Where, as `clank host list` names it.")
@click.option("--yes", is_flag=True, help="Remove the one Clank built without asking first.")
def uninstall(setup: str, version: str, host_name: str, yes: bool) -> None:
    """Remove an engine from a host: one Clank built by its recipe is deleted with its folder (`clank engine install`
    builds it again); one adopted where it was is only forgotten, its folder kept."""
    client = common.call(common.connect)
    body = {"setup": setup, "version": version, "host": host_name, "yes": yes}
    result = _ended(follow.follow(client, common.call(lambda: client.post("runtime/installs/remove", body))))
    if result["kept"]:
        click.echo(
            f"Clank forgot {result['title']} on {result['host']}; its folder stays where it is: {result['folder']}"
        )
    else:
        freed = size_text(result["freed"])
        click.echo(f"{result['title']} is removed from {result['host']}: {result['folder']} deleted, {freed} freed.")


model.add_command(add_model)  # the console's Add a model in the terminal (design 0016 §16)
COMMANDS = [model, preset, host, engine]
