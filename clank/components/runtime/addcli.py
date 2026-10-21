"""`clank model add` (design 0016 §14, §16): the console's Add a model, in the terminal, step by step in the service's
order and words (its guide, `GET /runtime/guide`): cloud or local; for the cloud, the provider, the agreement, the key
(read without echo, sent once, never printed), a model from the provider's live list, its settings as the service
fills them (refused in its words, asked again), and the test, a load into an empty main slot or a short request beside
the local model that runs and then "load it now?"; for a local model, the main slot's presets and what each needs here,
each step asked first and followed. The command works out nothing of its own: what it prints and asks is the service's.
"""

from functools import partial
from typing import Any

import click

from clank.cli import common, follow
from clank.client import Client, ClientError
from clank.components.runtime.cloudcli import ended, read_key
from clank.components.runtime.cloudclient import written
from clank.money import dollars

SHOWN_MODELS = 20  # the models listed at once; a search narrows them
TRIES = 3  # a key or settings asked again at most this many times


def steps(client: Client, preset: str = "") -> dict[str, dict[str, Any]]:
    """The guide's steps, by id, and where Cloud starts (under `""`)."""
    found = common.call(lambda: client.get("runtime/guide", preset=preset))
    return {"": {"cloud_from": found["cloud_from"]}, **{step["id"]: step for step in found["steps"]}}


def say(step: dict[str, Any]) -> None:
    """A step's title and words."""
    click.echo(f"\n== {step['title']}")
    for line in step.get("said", []):
        click.echo(line)


@click.command("add")
@click.option("--stdin", "from_stdin", is_flag=True, help="Read the key from one line of standard input (scripts).")
def add_model(from_stdin: bool) -> None:
    """Add a model, step by step, as the console's Add a model does: cloud (OpenRouter, with your key) or local."""
    client = common.call(common.connect)
    guide = steps(client)
    choice = guide["choice"]
    say(choice)
    for option in choice["options"]:
        click.echo(f"  {option['key']}  {option['said']}")
    picked = click.prompt("Cloud or local", type=click.Choice([option["key"] for option in choice["options"]]))
    if picked == "l":
        local(client, guide)
        return
    start = guide[""]["cloud_from"]
    if start == "provider":
        say(guide["provider"])
        agree(client, guide["agreement"])
    if start in ("provider", "key"):
        key(client, guide["key"], from_stdin)
    model = pick(client)
    preset = settings(client, model)
    test(client, preset)


def agree(client: Client, step: dict[str, Any]) -> None:
    """The agreement, asked once; the provider's record written with it."""
    say(step)
    click.echo(step["policy"]["deny"])
    servers = [server["name"] for server in step["servers"]]
    click.echo(f"{step['servers_said']} {', '.join(servers)}".strip())
    if not click.confirm("Agree", default=False):
        click.echo("Nothing was added.")
        raise click.exceptions.Exit(1)
    deny = click.confirm("Ask only for providers that do not keep your data", default=True)
    common.call(lambda: client.post("runtime/endpoints", {"id": "openrouter", "adapter": "openrouter", "agree": True}))
    if not deny:
        body = {"options": {"data_collection": "allow"}}
        common.call(lambda: client.patch("runtime/endpoints/openrouter", body))
    click.echo("OpenRouter is added, with your agreement.")


def key(client: Client, step: dict[str, Any], from_stdin: bool) -> None:
    """The key, read without echo and sent once; refused, said and asked again."""
    say(step)
    for _ in range(TRIES):
        try:
            answer = partial(client.put, "runtime/endpoints/openrouter/key")({"key": read_key(from_stdin)})
        except ClientError as error:
            click.echo(f"{error} {step.get('refused', '')}".strip())
            continue
        click.echo(f"OpenRouter took the key; Clank keeps it (ends …{answer['key']['ends']}).")
        click.echo(answer["account"]["said"])
        return
    raise click.ClickException("the key was refused; nothing more is asked")


def pick(client: Client) -> dict[str, Any]:
    """A model from the provider's live list: by its number, or a search that narrows the list."""
    search = ""
    while True:
        found = common.call(partial(client.get, "runtime/endpoints/openrouter/models", search=search))
        click.echo(f"\n{found['said']}")
        shown = found["models"][:SHOWN_MODELS]
        for number, model in enumerate(shown, 1):
            click.echo(f"{number:>3}  {model['said']['name']}  ({model['id']})\n     {model['said']['facts']}")
        answer = str(click.prompt("A model's number, or words to search for", default="1")).strip()
        if answer.isdigit() and 1 <= int(answer) <= len(shown):
            return dict(shown[int(answer) - 1])
        search = "" if answer.isdigit() else answer


def settings(client: Client, model: dict[str, Any]) -> dict[str, Any]:
    """The preset's settings as the service fills them, each kept or typed again; refused, said and asked again."""
    click.echo(f"\n{model['said']['about']}\nOne short request costs {model['said']['test']} at its prices.")
    fields = [*model["settings"], *steps(client, "")["settings"].get("limits", [])]  # the model's, then the limits
    for _ in range(TRIES):
        typed = {field["id"]: str(click.prompt(field["said"], default=field["value"], show_default=True))
                 for field in fields}  # fmt: skip
        filled = {field["id"]: field["value"] for field in fields}
        limits = {key: typed.pop(key) for key in ("day_usd", "month_usd")}
        body = {"model": model["id"], **typed}
        try:
            changed = {key: dollars(value) for key, value in limits.items() if value != filled.get(key)}
            preset, before = written(client, body)
            if changed:
                client.put("gateway/cost/limits", changed)
        except (ClientError, ValueError) as error:
            click.echo(str(error))
            continue
        said = "Took" if before else "Wrote"
        click.echo(f"{said} {preset['title']} ({preset['id']})" + (", written before." if before else "."))
        return preset
    raise click.ClickException("the settings were refused; nothing more is asked")


def test(client: Client, preset: dict[str, Any]) -> None:
    """The test, as the guide says: a load into an empty main slot, or a short request, then "load it now?"."""
    guide = steps(client, preset["id"])
    step = guide["test"]
    say(step)
    if step["mode"] == "ask":
        operation = common.call(lambda: client.post("runtime/endpoints/openrouter/test", {"preset": preset["id"]}))
        result = ended(follow.follow(client, operation))
        click.echo(f"It answered: {result['said']}" if result.get("ok") else f"It failed: {result['said']}")
        if not result.get("ok"):
            raise click.exceptions.Exit(1)
        if not click.confirm(step["ask"], default=False):
            click.echo(guide["ready"]["kept"])
            return
        path = "runtime/slots/main/switch"
    else:
        path = "runtime/slots/main/load"
    loaded = ended(follow.follow(client, common.call(lambda: client.post(path, {"preset": preset["id"]}))))
    ready = steps(client, preset["id"])["ready"]
    say(ready)
    click.echo(f"{ready['runs']} Its test: {loaded.get('said', '')}".strip())


def local(client: Client, guide: dict[str, dict[str, Any]]) -> None:
    """A local preset, picked from the main slot's, and what it needs here, each step asked first and followed."""
    say(guide["local"])
    presets = common.call(lambda: client.get("runtime/guide/local"))["presets"]
    for number, preset in enumerate(presets, 1):
        click.echo(f"{number:>3}  " + "\n     ".join(preset["said"]))
    number = click.prompt("A preset's number", type=click.IntRange(1, len(presets)), default=1)
    for step in presets[number - 1]["steps"]:
        if step["call"] is None:
            raise click.ClickException(step["asks"])
        if not click.confirm(f"{step['title']} {step['asks']}", default=False):
            click.echo("Nothing more was done.")
            raise click.exceptions.Exit(1)
        started = common.call(partial(client.post, step["call"]["path"], step["call"]["body"]))
        ended(follow.follow(client, started))
    click.echo(steps(client)["ready"]["runs"])
