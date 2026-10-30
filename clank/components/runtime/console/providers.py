"""The Providers and models page (design 0003 §8.2): the serving setups, and the models' files.

Each serving setup with the format it reads and each version: where it is installed and how (adopted where it was,
built by Clank's recipe, a test's), and whether Clank has a recipe for it. Each model of the catalog with its files
(format, role, size, where it comes from), and, on each host whose installed engine reads the file's format, where it
is (adopted where the user keeps it, or in the host's models folder) and whether it is there at its size; read off the
screen's thread when the page comes on screen and whenever an install, a download or a host changes. `i` installs an
engine by its recipe on a host, `d` downloads a model's file to a host, each picked from lists; `x` removes a model's
files from a host (the catalog keeps it, and every preset stays) and `u` removes an engine (Clank's build is deleted,
one adopted only forgotten). Each asks first when it fetches or deletes, as the operations always do, and the
operations page follows them. Its panels, "Serving setups" and "Models", are board E11's (design 0011 §8).

Its first panel, **Cloud** (design 0016 §15), shows each cloud provider: its agreement, its key (set, its last four and
its label; never the rest), its data policy, OpenRouter's own count for the key (its limit and what is left, read at
most once a minute by the service), Clank's spending today and this month against the limits, its last check, and its
presets; or, without one, how to add one. `a` opens Add a model at Cloud; `k` sets the key again in a hidden field (`PUT
/runtime/endpoints/openrouter/key`); `c` checks the provider (an operation; its items in a window); `o` changes the data
policy, asked first (`PATCH`); `L` sets the cost limits in a form (`PUT /gateway/cost/limits`); `D` turns dev mode on or
off, asked first in words that say both its halves and when each applies (`PUT /runtime/dev`, decisions 0149 and 0152:
any provider, and every public host for the agent), with or without a provider, since dev mode opens the agent's
internet with a local model too; `r` removes the provider with its key, asked first, and says why not while a preset or
the main slot uses it.
"""

import json
from collections.abc import Callable
from typing import Any

from textual.app import ComposeResult
from textual.widgets import Label

from clank.components.runtime.catalog import size_text
from clank.components.runtime.console.addmodel import AddModelPage
from clank.console import actions
from clank.console.confirm import ConfirmScreen
from clank.console.data import ConsoleData
from clank.console.details import DetailsScreen
from clank.console.form import Field, FormScreen
from clank.console.keys import PageKey
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.console.pick import Choice, PickScreen
from clank.console.text import count, moment
from clank.money import dollars

OPENROUTER = "runtime/endpoints/openrouter"

HOW = {
    "recipe": "built by Clank's recipe: its folder is deleted",
    "adopted": "adopted where it was: only forgotten",
    "test": "a test's: only forgotten",
}


def engines_text(engines: list[dict[str, Any]]) -> str:
    """Each serving setup: the format it reads; each version, where it is installed and how, and its recipe."""
    lines = []
    for engine in engines:
        lines.append(f"{engine['label']} ({engine['name']}), reads {engine['format']}")
        for version in engine["versions"]:
            where = sorted(f"{one['host']} ({one['how']})" for one in engine["installs"] if one["version"] == version)
            parts = [f"on {', '.join(where)}" if where else "not installed"]
            if version in engine["recipes"]:
                parts.append("Clank has its recipe")
            lines.append(f"  {version}  {' · '.join(parts)}")
    return "\n".join(lines) or "No serving setup."


def cloud_text(
    endpoints: list[dict[str, Any]] | None,
    account: dict[str, Any] | None,
    cost: dict[str, Any] | None,
    presets: list[dict[str, Any]],
    zone: Any,
) -> str:
    """Each cloud provider: its agreement, key, policy, OpenRouter's count, Clank's spending, check and presets, in the
    service's words (its views' `said`); the console adds only the times, in its own zone."""
    if endpoints is None:
        return "Not read: this service answers nothing of the cloud."
    if not endpoints:
        return "No cloud provider. a adds one: Add a model, OpenRouter with your key (no GPU needed)."
    lines = []
    for each in endpoints:
        agreed = f"agreed {moment(each['agreed'], zone)}" if each["agreed"] else "not agreed: nothing loads from it"
        lines.append(f"{each['title']} ({each['id']}) · {agreed}")
        key = each["key"]
        set_at = f" {moment(key['set_at'], zone)}" if key["set_at"] else ""
        lines.append("  key       " + (f"set{set_at}, ends …{key['ends']}" if key["set"] else "no key: k sets it"))
        policy = each["options"].get("data_collection", "deny")
        lines.append(f"  policy    {(each.get('said') or {}).get('policy') or f'data_collection {policy}'}")
        if key["set"]:
            lines.append(f"  account   {(account or {}).get('said') or 'being read'}")
        spent = cost or {}
        if spent.get("said"):
            lines.append(f"  Clank     {spent['said']} (this computer's days); {spent['limits']['said']}")
        check = each["check"]
        if check:
            failed = [item["name"] for item in check["items"] if item["status"] == "fail"]
            verdict = "ok" if check["ok"] else f"failed: {', '.join(failed)}"
            lines.append(f"  check     {moment(check['time'], zone)}, {verdict} (c checks again)")
        else:
            lines.append("  check     not checked yet: c checks it")
        running = (each.get("running") or {}).get("preset")
        mine = [
            preset["title"] + (" (runs in the main slot)" if preset["id"] == running else "")
            for preset in presets
            if preset.get("endpoint") == each["id"]
        ]
        lines.append(f"  presets   {', '.join(mine) if mine else 'none yet: a adds one'}")
    return "\n".join(lines)


def models_text(models: list[dict[str, Any]] | None) -> str:
    """Each model's files, and where each is on the hosts whose engine reads it."""
    if models is None:
        return "Being read."
    lines = []
    for model in models:
        lines.append(f"{model['name']} ({model['id']})")
        for file in model["files"]:
            source = file["repository"] + (f"@{file['revision'][:12]}" if file["revision"] else "")
            role = f"{file['format']} {file['role']}"
            lines.append(f"  {role:<16} {file['path']}, {size_text(file['size'])}, from {source}")
            for where in file["hosts"]:
                there = "there" if where["present"] else "not there"
                how = "adopted at" if where["how"] == "adopted" else "in its models folder at"
                lines.append(f"    {where['host']}: {there}, {how} {where['path']}")
            if not file["hosts"]:
                lines.append("    no host has an engine that reads it")
    return "\n".join(lines) or "No model in the catalog."


class ProvidersPage(Page):
    """The serving setups and their installs; the models' files and where they are."""

    ENTRY = MenuEntry(
        "providers",
        "Providers and models",
        "The cloud provider (a adds a cloud model, k sets its key, c checks it, o its data policy, L the cost "
        "limits, r removes it); each serving setup's versions, where each is installed and how; each model's files "
        "and where they are; i installs an engine by its recipe, d downloads a model's file, x removes a model's "
        "files, u removes an engine.",
        "design 0003 §8.2",
        key="0",
    )
    PANELS = ("providers-cloud", "providers-setups", "providers-models-panel")
    KEYS = (
        PageKey("a", "add", "add a cloud model", "Add a model, at Cloud"),
        PageKey("k", "key", "set the key", "set the cloud provider's key again, in a hidden field"),
        PageKey(
            "c", "check", "check it", "check the cloud provider: its key, its account, a short request, a tool call"
        ),
        PageKey("o", "policy", "data policy", "only providers that keep no data, or any"),
        PageKey("D", "dev", "dev mode", "for testing: any provider for every request, every public host for the agent"),
        PageKey("L", "limits", "cost limits", "the cloud's daily and monthly cost limits"),
        PageKey("r", "remove", "remove it", "remove the cloud provider, with its key"),
        PageKey("i", "install", "install an engine"),
        PageKey("d", "download", "download a model's file"),
        PageKey("x", "remove_model", "remove a model's files"),
        PageKey("u", "remove_engine", "remove an engine"),
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.models: list[dict[str, Any]] | None = None
        self.account: dict[str, Any] | None = None  # the cloud key's account, as OpenRouter told it

    def compose(self) -> ComposeResult:
        """The cloud; the serving setups; the models; the keys."""
        with Panel(title="Cloud", id="providers-cloud"):
            yield Label(id="providers-cloud-text")
        with Panel(title="Serving setups", id="providers-setups"):
            yield Label(id="providers-engines")
        with Panel(title="Models", id="providers-models-panel"):
            yield Label(id="providers-models")

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Draw the setups again when the engines changed, and read the models' files again."""
        if changed & {"all", "engines", "hosts"}:
            self.query_one("#providers-engines", Label).update(engines_text(data.engines))
            self._read_models()
        if changed & {"all", "models"}:
            self.query_one("#providers-models", Label).update(models_text(self.models))
        if changed & {"all", "endpoints"}:
            self._read_account()
        if changed & {"all", "endpoints", "cost", "presets", "account"}:
            text = cloud_text(data.endpoints, self.account, data.cost, data.presets, self.console.zone)
            self.query_one("#providers-cloud-text", Label).update(text)

    def press(self, key: str) -> bool:
        """`i` installs an engine by its recipe; `d` downloads a model's file; `x` removes a model's files from a host;
        `u` removes an engine from its host."""
        cloud: dict[str, Callable[[], None]] = {
            "a": self._add,
            "k": self._key,
            "c": self._check,
            "o": self._policy,
            "D": self._dev,
            "L": self._limits,
            "r": self._remove_provider,
        }
        if key in cloud:
            if key not in ("a", "D") and not self._provider():  # dev mode opens the agent's internet too (0152)
                self.console.say("there is no cloud provider: a adds one", True)
            else:
                cloud[key]()
            return True
        if key == "i":
            choices = [
                Choice(f"{engine['name']}|{version}", f"{engine['label']} {version}", "by Clank's recipe")
                for engine in self.console.data.engines
                for version in engine["recipes"]
            ]
            self._pick("Install an engine by its recipe", choices, self._install)
            return True
        if key == "d":
            choices = [
                Choice(
                    f"{model['id']}|{file['format']}|{file['role']}",
                    f"{model['name']}: {file['path']}",
                    f"{file['format']} {file['role']}, {size_text(file['size'])}",
                )
                for model in self.models or []
                for file in model["files"]
            ]
            self._pick("Download a model's file", choices, self._download)
            return True
        if key == "x":
            choices = [
                Choice(model["id"], f"{model['name']} ({model['id']})", count(len(model["files"]), "file"))
                for model in self.models or []
            ]
            self._pick("Remove a model's files", choices, self._remove)
            return True
        if key == "u":
            installed = [
                Choice(
                    f"{engine['name']}|{one['version']}|{one['host']}",
                    f"{engine['label']} {one['version']} on {one['host']}",
                    HOW.get(one["how"], one["how"]),
                )
                for engine in self.console.data.engines
                for one in engine["installs"]
            ]
            if not installed:
                self.console.say("there is nothing to choose: no engine is installed", True)
                return True
            self.console.push_screen(PickScreen("Remove an engine", installed), self._uninstall)
            return True
        return False

    def explain(self) -> tuple[str, list[str]]:
        """What the page shows, and what the keys do."""
        return "Providers and models", [
            "A serving setup is an engine Clank has an adapter for (KVMem), at the versions the adapter knows. "
            "An install is adopted (found where it was, its commit checked), built by Clank's recipe (in an "
            "environment of its own, nothing installed with root), or a test's.",
            "A model's file is used only once its SHA-256 is the catalog's: adopted where you keep it (checked once), "
            "or downloaded into the host's models folder (resumed after an interruption, kept aside when it differs).",
            "i installs an engine by its recipe and d downloads a model's file, each on a host picked from a list; "
            "both ask first, and the operations page follows them.",
            "x removes a model's files from a host: what Clank put in its models folder is deleted after a question, "
            "a file you keep elsewhere only forgotten; the catalog keeps the model and every preset stays, so d brings "
            "it back. u removes an engine: one Clank built is deleted with its folder after a question (i builds it "
            "again), one adopted is only forgotten. What a running slot uses is refused: unload it first.",
        ]

    def _pick(self, title: str, choices: list[Choice], then: Callable[[str, str], None]) -> None:
        """A choice, then a host to put it on."""
        if not choices:
            self.console.say("there is nothing to choose: " + ("no recipe" if "engine" in title else "no model"), True)
            return
        hosts = [Choice(host["name"], host["name"], _host_line(host)) for host in self.console.data.hosts]

        def chosen(value: str | None) -> None:
            if value is None:
                return

            def placed(host: str | None) -> None:
                if host is not None:
                    then(value, host)

            self.console.push_screen(PickScreen("On which host?", hosts), placed)

        self.console.push_screen(PickScreen(title, choices), chosen)

    def _install(self, value: str, host: str) -> None:
        setup, version = value.split("|")
        client, body = self.console.client, {"setup": setup, "version": version, "host": host}
        actions.call(self.console, lambda: client.post("runtime/installs", body), done=f"asked to install it on {host}")

    def _download(self, value: str, host: str) -> None:
        model, form, role = value.split("|")
        client, body = self.console.client, {"model": model, "format": form, "role": role, "host": host}
        actions.call(
            self.console, lambda: client.post("runtime/downloads", body), done=f"asked to download it to {host}"
        )

    def _remove(self, model: str, host: str) -> None:
        client, body = self.console.client, {"model": model, "host": host}
        actions.call(
            self.console,
            lambda: client.post("runtime/model-files/remove", body),
            done=f"asked to remove its files from {host}",
        )

    def _uninstall(self, value: str | None) -> None:
        if value is None:
            return
        setup, version, host = value.split("|")
        client, body = self.console.client, {"setup": setup, "version": version, "host": host}
        actions.call(
            self.console, lambda: client.post("runtime/installs/remove", body), done=f"asked to remove it from {host}"
        )

    # The cloud.

    def _provider(self) -> dict[str, Any] | None:
        return next((each for each in self.console.data.endpoints or [] if each["id"] == "openrouter"), None)

    def _read_account(self) -> None:
        provider = self._provider()
        if provider is None or not provider["key"]["set"]:
            self.account = None
            return
        client = self.console.client

        def work() -> None:
            try:
                found = client.get(f"{OPENROUTER}/account")
            except Exception:
                return
            self.console.call_from_thread(self._account_read, found)

        self.run_worker(work, thread=True, group="providers-account", exclusive=True, exit_on_error=False)

    def _account_read(self, found: dict[str, Any]) -> None:
        self.account = found
        self.draw(self.console.data, {"account"})

    def _add(self) -> None:
        self.console.show_page("addmodel")
        self.console.query_one("#page-addmodel", AddModelPage).start("cloud")

    def _key(self) -> None:
        """The key again, in a hidden field: sent once, and held no longer."""
        field = Field("key", "Paste your OpenRouter key (openrouter.ai, Keys): dots, then its last four", "the key",
                      secret=True)  # fmt: skip
        note = ("Enter: Clank asks OpenRouter whether it takes the key and keeps it only then, replacing the one kept; "
                "a cloud model loaded gets the new one at once. Esc leaves the key kept as it is.")  # fmt: skip

        def given(values: dict[str, str] | None) -> None:
            if not values or not values["key"]:
                return
            client = self.console.client

            def send(key: str) -> None:
                try:
                    answer = client.put(f"{OPENROUTER}/key", {"key": key})
                except Exception as error:
                    self.console.call_from_thread(self.console.say, str(error), True)
                    return
                said = f"OpenRouter took the key; Clank keeps it (ends …{answer['key']['ends']})"
                self.console.call_from_thread(self.console.say, said)

            key = values.pop("key")
            self.run_worker(
                lambda: send(key),
                thread=True,
                group="providers-key",
                description="send the key to the service",  # never the call's repr in Textual's log
                exit_on_error=False,
            )

        self.console.push_screen(FormScreen("OpenRouter's key", [field], note), given)

    def _check(self) -> None:
        """The check: an operation of a few seconds; its items in a window once it ends."""
        client = self.console.client

        def work() -> None:
            try:
                operation = client.post(f"{OPENROUTER}/check", {})
            except Exception as error:
                self.console.call_from_thread(self.console.say, str(error), True)
                return
            self.console.call_from_thread(self.console.say, "checking OpenRouter: a few seconds")
            ended = actions.follow(client, operation["id"], lambda: not self.console.is_running)
            if ended is None:
                return
            items = (ended.get("result") or {}).get("items") or []
            lines = [f"{item['status']:<7} {item['name']:<9} {item['said']}" for item in items]
            lines = lines or [str(ended.get("error") or ended["status"])]
            self.console.call_from_thread(self.console.push_screen, DetailsScreen("Check of OpenRouter", lines))

        self.run_worker(work, thread=True, group="providers-check", exclusive=True, exit_on_error=False)

    def _policy(self) -> None:
        provider = self._provider() or {}
        policy = "allow" if provider.get("options", {}).get("data_collection", "deny") == "deny" else "deny"
        body = {"options": {"data_collection": policy}}
        said = (
            "OpenRouter may then send your requests to providers that keep data, as their own policies say."
            if policy == "allow"
            else "OpenRouter then sends your requests only to providers that keep no data; a model none of them serves "
            "is refused."
        )
        lines = [said, "It applies from the next load of a cloud model.", f"The call: PATCH /api/v1/{OPENROUTER} "
                 f"{json.dumps(body)}"]  # fmt: skip

        def answered(yes: bool | None) -> None:
            if yes:
                client = self.console.client
                actions.call(self.console, lambda: client.patch(OPENROUTER, body), done=f"data_collection {policy}")

        self.console.push_screen(ConfirmScreen(f"Ask OpenRouter for data_collection {policy}?", lines), answered)

    def _dev(self) -> None:
        known = self.console.data.dev
        on = not (known.get("on") if known is not None else (self._provider() or {}).get("dev_mode"))
        body = {"on": on}
        if on:
            said = (
                "For testing: every cloud request then goes to any of the model's providers, those that may keep or "
                "train on what they are sent too (data_collection allow), whatever the provider's record says; and "
                "every workspace's agent reaches every public host at once, without a question (private addresses, "
                "this machine and your network, still never). The header says dev mode."
            )
            when = (
                "From the next cloud request and the agent's next connection; OpenCode fetches and searches the web "
                "from its next start in a folder (a window already open, once it starts again)."
            )
        else:
            said = (
                "Every cloud request then goes as its provider's record says, and each workspace's agent reaches only "
                "the hosts allowed for it, a host not allowed asked for."
            )
            when = (
                "From the next cloud request and the agent's next connection; OpenCode's web tools are refused from "
                "its next start in a folder."
            )
        lines = [said, when, f"The call: PUT /api/v1/runtime/dev {json.dumps(body)}"]
        turned = "on" if on else "off"

        def answered(yes: bool | None) -> None:
            if yes:
                client = self.console.client
                actions.call(self.console, lambda: client.put("runtime/dev", body), done=f"dev mode {turned}")

        self.console.push_screen(ConfirmScreen(f"Turn dev mode {turned}?", lines), answered)

    def _limits(self) -> None:
        limits = (self.console.data.cost or {}).get("limits") or {}

        def shown(value: float | None) -> str:
            return "" if value is None else f"{value:g}"

        fields = [
            Field("day", "A day's limit, US dollars (empty: none)", "5", shown(limits.get("day_usd"))),
            Field("month", "A month's limit, US dollars (empty: none)", "50", shown(limits.get("month_usd"))),
        ]
        note = ("When a limit is reached, cloud requests wait until you raise it or the period ends (this computer's "
                "days and months). OpenRouter can limit the key too. Ctrl+S takes these; Esc leaves them.")  # fmt: skip

        def given(values: dict[str, str] | None) -> None:
            if values is None:
                return
            try:
                body = {f"{key}_usd": dollars(values[key]) for key in ("day", "month")}  # amounts: the service checks
            except ValueError as error:
                self.console.say(str(error), True)
                return
            client = self.console.client
            actions.call(self.console, lambda: client.put("gateway/cost/limits", body), done="the cost limits are set")

        self.console.push_screen(FormScreen("The cloud's cost limits", fields, note), given)

    def _remove_provider(self) -> None:
        lines = ["Its record and its key are removed; its presets must go first, and the main slot must not run one.",
                 f"The call: DELETE /api/v1/{OPENROUTER}"]  # fmt: skip

        def answered(yes: bool | None) -> None:
            if yes:
                client = self.console.client
                actions.call(
                    self.console, lambda: client.delete(OPENROUTER), done="OpenRouter is removed, with its key"
                )

        self.console.push_screen(ConfirmScreen("Remove OpenRouter?", lines), answered)

    def _read_models(self) -> None:
        client = self.console.client

        def work() -> None:
            try:
                found = client.get("runtime/models")
            except Exception:
                return
            self.console.call_from_thread(self._show_models, found)

        self.run_worker(work, thread=True, group="models", exclusive=True, exit_on_error=False)

    def _show_models(self, found: list[dict[str, Any]]) -> None:
        self.models = found
        self.draw(self.console.data, {"models"})


def _host_line(host: dict[str, Any]) -> str:
    kind = f"WSL: {host['distro']}" if host["adapter"] == "wsl" else "this machine"
    return f"{kind}, its Clank folder {host['clank_folder']}"
