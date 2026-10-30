"""Add a model's steps, in order, and every word they say (design 0016 §14, decision 0105), for every client: the
console's page, `clank model add`, and the phone's app to come all walk the same steps in the same order and say what
the service gives them here, so none of them decides what a step says, which step comes next, or whether a value fits.

The steps: `choice` (cloud or local), `provider` (OpenRouter, where to get a key), `agreement` (what goes where and
what never goes, the MCP servers to mark local, the data policy), `key` (the hidden field), `model` (OpenRouter's live
list), `settings` (the preset's settings, filled from the model), `test` (the load into an empty main slot, or the
provider's short test beside a local model, then "load it now?"), `ready` (what runs, and Docker's state), and `local`
(Clank's presets for the main slot and what each needs here). `guide` gives each step's title and words from the state
the service holds; `cloud_from` says where Cloud starts (the provider, its key, or the model once the key is set).
`model_said` and `model_settings` are a model line's words and its settings' fields (`limit_fields` the limits');
`account_said` is the key's account in a line; `local_steps` is what a local preset still needs, in
order, each with the call that does it; `endpoint_said` is the Providers page's lines for a provider.

It is the service's: it reads no client's state and draws nothing. The service's routes put its words in their
answers (plan s34's interface; plan s35 lists what it asks for).
"""

import re
from typing import Any

from clank.money import money, size, tokens

STEPS = ("choice", "provider", "agreement", "key", "model", "settings", "test", "ready", "local")
TITLES = {
    "choice": "Add a model",
    "provider": "Cloud: the provider",
    "agreement": "What goes to OpenRouter",
    "key": "Your OpenRouter key",
    "model": "The model",
    "settings": "Its settings",
    "test": "The test",
    "ready": "Ready",
    "local": "Local: a model on this computer",
}
SORTED = {
    "most-popular": "programming models, most used first",
    "price": "cheapest first",
    "context": "largest window first",
    "newest": "newest first",
}
EFFORTS = ("max", "xhigh", "high", "medium", "low", "minimal", "none")  # OpenRouter's, when a model lists none
OUTPUT = 16384  # the output a preset takes by default, or the model's most when smaller
TEST_IN, TEST_OUT = 40, 16  # one short request's tokens, about: "Reply with OK.", 16 out at most
DOCKER_GET = (
    "Docker is not installed: get Docker Desktop (Windows, macOS: docs.docker.com/desktop) or Docker Engine (Linux: "
    "docs.docker.com/engine/install). The model works without it; the agent works in a workspace's container."
)
MARKS = {"local": "local only: never offered to the cloud model", "cloud": "may go to the cloud"}
POLICY = {
    "deny": "Clank asks only for providers that do not keep your data (data_collection deny).",
    "allow": "Clank asks for any provider, those that may keep your data too (data_collection allow).",
}
DEV_SAID = {  # dev mode, on and off (decision 0149)
    True: "Dev mode is on: Clank asks every cloud provider for any of a model's providers, those that may keep or "
    "train on what they are sent too (data_collection allow), whatever its own record says. clank dev off ends it.",
    False: "Dev mode is off: each cloud provider is asked as its record says (data_collection deny unless you changed "
    "it). clank dev on asks for any provider, for testing.",
}


def policy_said(own: str, dev: bool) -> str:
    """A provider's data policy in words: its record's, or dev mode's while it is on and relaxes it (decision 0149)."""
    if dev and own != "allow":
        return (
            "Dev mode: Clank asks for any provider, those that may keep your data too (data_collection allow); this "
            f"record's own is {own}."
        )
    return POLICY.get(own, "")


def cloud_from(endpoint: dict[str, Any] | None) -> str:
    """Where Cloud starts: the provider, until it is added; its key, until one is set; then the model."""
    if endpoint is None:
        return "provider"
    return "model" if endpoint["key"]["set"] else "key"


def machine_said(reading: dict[str, Any] | None, profile: dict[str, Any] | None) -> str:
    """This computer's GPU and memory, from the machine's last reading (or its profile, before the first reading)."""
    if reading:
        gpus = [f"{gpu['name']}, {size(gpu['memory_total'])}" for gpu in reading["gpus"] if gpu["memory_total"]]
        memory = size(reading["memory_total"])
    elif profile and profile.get("detected"):
        gpus = [f"{gpu['name']}, {size(gpu['memory_mib'] << 20)}" for gpu in profile["gpus"]]
        memory = f"{profile['memory_gb']:.0f} GB"
    else:
        return "This computer is not read yet."
    graphics = "; ".join(gpus) if gpus else "no NVIDIA GPU answered"
    return f"This computer: {graphics}; {memory} of memory."


def docker_said(state: str) -> str:
    """What Ready says of Docker: it runs; how to start it; or where to get it."""
    if state == "running":
        return "Docker runs: a workspace's container can start."
    if state == "not installed":
        return DOCKER_GET
    if state:
        return f"Docker is {state}: it can be started from here. The agent works in a workspace's container."
    return "Docker is not read yet."


def guide(
    usable: dict[str, Any],
    endpoint: dict[str, Any] | None,
    servers: list[dict[str, Any]],
    machine: str,
    docker: str,
    main: dict[str, Any],
    preset: dict[str, Any] | None = None,
    limits: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Every step of Add a model, in order, each with its title and words; `preset`, once written, gives the test's
    and Ready's words for it. `main` is the main slot as the service has it, with its preset's title."""
    why = [f"No model is usable yet: {usable['why']}."] if not usable.get("usable") else []
    title = (preset or {}).get("title", "")
    local = main.get("title") or main.get("preset") or "the local model"
    runs_local = main.get("status") in ("ready", "starting") and main.get("preset") != (preset or {}).get("id")
    steps: list[dict[str, Any]] = [
        {
            "id": "choice",
            "said": [*why, "How should Clank run its model?"],
            "options": [
                {
                    "key": "c",
                    "id": "cloud",
                    "said": "Cloud: a model at OpenRouter, with your key. No GPU needed. "
                    "Each request costs money, from your OpenRouter credits, and Clank shows what each one cost.",
                },
                {
                    "key": "l",
                    "id": "local",
                    "said": "Local: a model on this computer's GPU. Nothing to pay per "
                    f"request; it needs an engine and the model's files (many GB) here. {machine}",
                },
            ],
        },
        {
            "id": "provider",
            "said": [
                "OpenRouter: one account and one key reach the major models (OpenAI's, Anthropic's, Google's, "
                "open-weight ones), each at its own price. It is the one cloud provider for now; others come later.",
                "You need an OpenRouter account with credits, and a key: openrouter.ai, Keys, Create Key. OpenRouter "
                "recommends a credit limit on every key; set one there.",
                "Next: what goes to OpenRouter, then your key.",
            ],
        },
        {
            "id": "agreement",
            "said": [
                "Read this once, for OpenRouter.",
                "What goes: each request of an agent's session: your messages, what the agent reads of the folder, "
                "command output, and its instructions.",
                "Where: to OpenRouter, then the model's provider. OpenRouter does not log prompts by default.",
                "What never goes: Notion pages; the MCP servers marked local (below); a workspace you have not "
                "allowed. Each workspace asks once, the first time its agent would use the cloud model; those you "
                "have now stay local until you say.",
                "What it costs: each request is paid from your OpenRouter credits. Clank shows what each request, "
                "session and flow cost, and you may set a daily and a monthly limit.",
            ],
            "policy": dict(POLICY),
            "servers": [{"name": server["name"], "local_only": True} for server in servers],
            "marks": dict(MARKS),
            "servers_said": "MCP servers (each one you have is marked local only; unmark one to offer it):"
            if servers
            else "No MCP server is added: nothing to mark.",
        },
        {
            "id": "key",
            "said": ["Paste your OpenRouter key (openrouter.ai, Keys). It is never shown: dots, then its last four."],
            "placeholder": "paste your OpenRouter key",
            "hint": "Clank asks OpenRouter whether it takes the key (which costs nothing) and keeps it only then, in "
            "CLANK_HOME/secrets, readable by you alone. It is never shown, logged or copied.",
            "refused": "The field is cleared: paste the key again.",
        },
        {"id": "model", "said": ["OpenRouter's live list of the models that take tool calls (the agent needs them)."]},
        {
            "id": "settings",
            "said": ["Each setting is filled from the model; change what you want."],
            "hint": "OpenRouter can limit the key too (openrouter.ai, Keys). Taking these writes the preset, then "
            "tests it with one short request.",
            "limits": limit_fields(limits or {}),
        },
        {
            "id": "test",
            "said": [
                f"{local} runs in the main slot: testing with one short request"
                if runs_local
                else f"Loading {title or 'the preset'} into the main slot; its health is one short request"
            ],
            "mode": "ask" if runs_local else "load",
            "ask": f"Load it now? This stops {local} in the main slot; or keep {local} running, and "
            f"{title or 'the new preset'} waits on the Presets page.",
            "failed": "Go back to the model (another, or other settings), or to the key (a new one).",
        },
        {
            "id": "ready",
            "said": [
                docker_said(docker),
                "This folder's agent works with it; it asks once whether this workspace may use the cloud model.",
                "Each request costs money: Home, Requests and the Monitor show what each cost; the Providers and "
                "models page sets the limits.",
            ],
            "runs": f"{title} runs in the main slot." if title else f"{local} runs in the main slot.",
            "kept": f"{title} is written and tested; {local} keeps the main slot. Load {title} from Presets.",
            "docker": docker,
        },
        {
            "id": "local",
            "said": [
                "Clank's presets for the main slot, each with its fit on this GPU and what it needs here. Each missing "
                "step is done in order: the engine by Clank's recipe, the model's files, the load; each is asked "
                "first. A local model costs nothing per request."
            ],
        },
    ]
    for step in steps:
        step["title"] = TITLES[step["id"]]
    return {"usable": usable, "cloud_from": cloud_from(endpoint), "steps": steps}


def account_said(account: dict[str, Any], ends: str = "") -> str:
    """The key as OpenRouter tells it: its label, its own limit and what is left (or the advice to set one)."""
    key = f'key "{account["label"]}"' + (f" (ends …{ends})" if ends else "")
    if account["limit_usd"] is None:
        limit = "it has no limit of its own; OpenRouter advises one (openrouter.ai, Keys)"
    else:
        limit = f"its own limit {money(account['limit_usd'])}, {money(account['remaining_usd'])} left"
    used = f"OpenRouter counts {money(account['used_today_usd'])} today, {money(account['used_month_usd'])} this month"
    budget = account.get("budget")
    refused = f"; its budget is spent until {budget['resets_at']}" if budget and budget["remaining_usd"] <= 0 else ""
    free = "; a free-tier key" if account.get("free_tier") else ""
    return f"{key}: {limit}; {used} (UTC days){free}{refused}"


def per_million(price: dict[str, Any]) -> str:
    """A model's prices per million tokens, in and out."""
    return f"{money(price['in'])} in, {money(price['out'])} out"


def model_said(model: dict[str, Any]) -> dict[str, str]:
    """A model in words: its line in the list, itself under the list, and what one short request costs."""
    cost = f"free ({model['limits']})" if model["free"] else per_million(model["price"])
    facts = [f"{tokens(model['window'])} window", cost]
    facts += [word for word, has in (("thinks", model["thinking"]), ("reads images", model["images"])) if has]
    sentence = re.split(r"(?<=[.!?])\s", model["description"].strip(), maxsplit=1)[0] if model["description"] else ""
    output = f"{model['output']:,}" if model["output"] else "not said"
    about = [f"{model['id']}: {sentence}".rstrip(": "), f"Window {model['window']:,} tokens, most output {output}."]
    if model["retires"]:
        about.append(f"OpenRouter retires it on {model['retires']}.")
    price = model["price"]
    usd = (TEST_IN * price["in"] + TEST_OUT * price["out"]) / 1_000_000 + (price.get("request") or 0.0)
    test = "nothing (a free model)" if usd <= 0 else f"about {money(usd)}"
    return {"name": model["name"], "facts": " · ".join(facts), "about": " ".join(about), "test": test}


def listed_said(count: int, sort: str, free: bool, search: str) -> str:
    """What a list of models shows: how many, in which order, and how it is narrowed."""
    narrowed = (["free ones only"] if free else []) + ([f"names with {search}"] if search else [])
    said = "; ".join([SORTED.get(sort, sort), *narrowed])
    return f"{count} that take tool calls, {said}. Prices per million tokens."


def efforts(model: dict[str, Any]) -> tuple[str, ...]:
    """The thinking efforts a model takes, `default` first."""
    return ("default", *(model["efforts"] or (EFFORTS if model["thinking"] else ())))


def model_settings(model: dict[str, Any]) -> list[dict[str, str]]:
    """A cloud preset's settings for a model, each field's words and its value as filled."""
    thinks = f"one of {', '.join(efforts(model))}" if model["thinking"] else "default: it does not think"
    output = model["output"] or OUTPUT
    return [
        {"id": "title", "said": "Its title, as the pickers show it", "value": f"cloud: {model['name']}"},
        {"id": "context", "said": f"Its context, in tokens (the model's window, {model['window']:,}; a smaller one "
         "makes OpenCode compact sooner and each request cost less)", "value": str(model["window"])},
        {"id": "max_output", "said": f"Its most output, in tokens (at most {output:,})",
         "value": str(min(OUTPUT, output))},
        {"id": "reasoning", "said": f"Its thinking effort ({thinks})", "value": "default"},
    ]  # fmt: skip


def limit_fields(limits: dict[str, Any]) -> list[dict[str, str]]:
    """The cloud's limits as Add a model's settings show them, filled as they are now."""

    def shown(value: float | None) -> str:
        return "" if value is None else f"{value:g}"

    return [
        {"id": "day_usd", "said": "A day's cost limit, US dollars (empty: none)",
         "value": shown(limits.get("day_usd"))},
        {"id": "month_usd", "said": "A month's cost limit, US dollars (empty: none)",
         "value": shown(limits.get("month_usd"))},
    ]  # fmt: skip


def local_steps(needs: dict[str, Any], preset: str) -> list[dict[str, Any]]:
    """What a local preset still needs here, in order, each with its words, its question, and the call that does it:
    its engine installed by Clank's recipe, its model's weights downloaded, then the load; an engine with no recipe
    here is a step that cannot be done from Add a model, saying what to do instead (its `call` is None)."""
    host = needs["host"]
    steps = []
    engine = needs["engine"]
    if not engine["installed"] and not engine["recipe"]:
        words = f"{engine['label']} {engine['version']} is not installed here, and Clank has no recipe for it"
        return [{
            "kind": "cannot", "said": words, "title": "Not installed",
            "asks": f"{words}: build it, then adopt it where it is (clank engine adopt); or choose Cloud.",
            "call": None,
        }]  # fmt: skip
    if not engine["installed"] and engine["recipe"]:
        words = f"install {engine['label']} {engine['version']}"
        steps.append({
            "kind": "install", "said": words, "title": "Install the engine?",
            "asks": f"Clank will {words} on {host} by its recipe: it builds there, which takes a while.",
            "call": {"method": "POST", "path": "runtime/installs",
                     "body": {"setup": engine["setup"], "version": engine["version"], "host": host, "yes": True}},
        })  # fmt: skip
    model = needs["model"]
    for file in model.get("files", []):
        if file["role"] == "weights" and not file["downloaded"]:
            words = f"download {model['name']}'s weights"
            steps.append({
                "kind": "download", "said": f"{words} ({size(file['size'])})", "title": "Download the model?",
                "asks": f"Clank will {words} to {host}: {size(file['size'])}, from Hugging Face.",
                "call": {"method": "POST", "path": "runtime/downloads",
                         "body": {"model": model["id"], "format": model["format"], "role": "weights", "host": host,
                                  "yes": True}},
            })  # fmt: skip
    steps.append({
        "kind": "load", "said": "load it into the main slot", "title": "Load it?",
        "asks": "Clank will load it into the main slot: it takes this computer's GPU while it runs.",
        "call": {"method": "POST", "path": "runtime/slots/main/load", "body": {"preset": preset}},
    })  # fmt: skip
    return steps


def local_said(preset: dict[str, Any], plan: dict[str, Any] | None, steps: list[dict[str, Any]]) -> list[str]:
    """A local preset on the Local step: its title, what it runs and its fit, and what it still needs."""
    if plan is None:
        fit = "fit: not read"
    elif plan.get("fit"):
        fit = f"fit: {plan['fit']['verdict']}"
    else:
        fit = "fit: known once its engine is installed"
    needs = [step["said"] for step in steps if step["kind"] != "load"]
    return [
        preset["title"],
        f"{preset['engine']} {preset['engine_version']} · {preset['model']} · {fit}",
        "; ".join(needs) if needs else "nothing missing: it loads now",
    ]
