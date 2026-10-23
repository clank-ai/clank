"""Add a model (design 0016 §14, decision 0105): the console's guided first step, so a new user is working after one
pass. It opens by itself when no model is usable, is in the menu, and `a` on Providers and models opens it at Cloud.

The page draws the service's guide (`GET /runtime/guide`, its words made by `clank.components.runtime.guide`): each
step's title and words, where Cloud starts, what the test does and asks, what Ready says; and the service's answers
for the rest (the models and their settings, the key's account, the Local presets and what each needs). It works out
no cost, consent or fit of its own, and checks no setting: the service refuses one in words, shown as they are. So the
commands and the phone's app to come walk the same steps in the same order and say the same things (the owner's rule
of 2026-10-21). The keys are the console's own.

Each step is a panel of the page, one at a time; Backspace goes back one step, Esc to the menu (decision 0129).
What a new user types: `c`, Enter, `y`, the key (pasted), Enter, a search or the arrows, Enter, Enter.

1. **Add a model** (`choice`): `c` Cloud, `l` Local, as the guide words them (this machine's GPU and memory with Local).
2. **Cloud: the provider** (`provider`): OpenRouter, and where to get a key. Enter goes on.
3. **What goes to OpenRouter** (`agreement`): the guide's words, its MCP servers each marked local (Space unmarks the
   highlighted one), and its data policy (`o` changes it); `y` agrees, which writes the provider's record (`POST
   /runtime/endpoints`, the servers marked as shown, then the policy when it is `allow`); `n` goes back, writing
   nothing.
4. **Your key** (`key`): the hidden field (`clank.console.form.SecretField`). Enter sends it once (`PUT
   /runtime/endpoints/openrouter/key`), and the page holds it no longer: accepted, the next step says the key's account
   (the answer's `said`); refused, the service's words, and the field is cleared.
5. **The model** (`model`): OpenRouter's live list (`GET .../models`, each model's words its `said`), the highlighted
   one under it; `/` searches, `s` sorts (most used, price, window, newest), `f` shows the free ones. Enter picks.
6. **Its settings** (`settings`): the model's `settings` as fields, filled as the service fills them; Enter in any field
   sends them as typed (`POST .../presets`), and a limit changed (`PUT /gateway/cost/limits`); a refusal is said.
7. **The test** (`test`): as the guide's test step says (`mode`): `load` loads the preset into the main slot (`POST
   /runtime/slots/main/load`), its operation followed on the screen; `ask` tests it beside the local model that runs
   (`POST .../test`), then asks the guide's question (`y` switches, `n` keeps it). The answer, its time and its cost are
   the operation's `said`; a failure says what to do, `b` back to the model, `k` back to the key.
8. **Ready** (`ready`): the guide's words: what runs, Docker's state (`s` starts it), what comes next. Enter goes to
   This folder.

**Local** (`local`, from `l`): the main slot's presets as the service lists them (`GET /runtime/guide/local`), each with
its fit and what it still needs here; Enter walks its steps in the service's order, each asked first in a window with
the service's words and the exact call, and followed.

Everything the page asks of the service runs off the screen's thread.
"""

import json
import time
from functools import partial
from typing import Any, ClassVar

from textual.app import ComposeResult
from textual.widget import Widget
from textual.widgets import Input, Label, ListItem, ListView

from clank.components.runtime.cloudclient import written
from clank.console.actions import ENDED, follow
from clank.console.confirm import ConfirmScreen
from clank.console.data import ConsoleData
from clank.console.form import SecretField
from clank.console.keys import PageKey
from clank.console.keysbar import KeysBar
from clank.console.menu import MenuEntry
from clank.console.pages import Page
from clank.console.panel import Panel
from clank.money import dollars

SCREENS = ("choice", "provider", "agreement", "key", "model", "settings", "test", "ready", "local")
TITLES = {  # until the guide is read: the guide's titles replace them
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
SORTS = ("most-popular", "price", "context", "newest")
FIELDS = ("title", "context", "max_output", "reasoning", "day_usd", "month_usd")
LIMITS = ("day_usd", "month_usd")
POLL_SECONDS = 0.2
SHOWN_LINES = 6  # an operation's last lines the test screen shows
GUIDE_READ_BY = {"all", "usable", "endpoints", "mcp", "docker", "slots", "machine", "presets"}
ESC_BACK = PageKey("backspace", "back", "back")  # a step back; Esc is the menu (decision 0129)
SCREEN_KEYS: dict[str, tuple[PageKey, ...]] = {
    "choice": (
        PageKey("c", "cloud", "cloud", "a model at OpenRouter, with your key"),
        PageKey("l", "local", "local", "a model on this computer's GPU"),
    ),
    "provider": (PageKey("enter", "next", "go on"), ESC_BACK),
    "agreement": (
        PageKey("y", "agree", "agree"),
        PageKey("n", "back", "back"),
        PageKey("space", "mark", "mark", "mark the highlighted MCP server local only, or not"),
        PageKey("o", "policy", "policy", "the data policy: only providers that keep no data (deny), or any (allow)"),
    ),
    "key": (PageKey("enter", "check", "check it", "ask OpenRouter whether it takes the key"), ESC_BACK),
    "model": (  # Enter last: the keys a narrow bar keeps are those only this step has
        PageKey("slash", "search", "search", "search the models by name or id"),
        PageKey("s", "sort", "sort", "sort by most used, price, window or newest"),
        PageKey("f", "free", "free", "show only the free models, or every one"),
        ESC_BACK,
        PageKey("enter", "pick", "pick", "pick the highlighted model"),
    ),
    "settings": (
        PageKey("enter", "take", "take", "write the preset (and the limits), then test it"),
        PageKey("tab", "next", "next", "the next field"),
        ESC_BACK,
    ),
    "test": (
        PageKey("y", "switch", "load it now", "stop the local model and load the cloud one"),
        PageKey("n", "keep", "keep it", "keep the local model running"),
        PageKey("b", "model", "back to the model"),
        PageKey("k", "key", "back to the key"),
    ),
    "ready": (
        PageKey("enter", "folder", "this folder", "This folder, where a starts the agent"),
        PageKey("s", "docker", "start Docker"),
    ),
    "local": (PageKey("enter", "set_up", "set it up", "do what it needs here, each step asked first"), ESC_BACK),
}
POLICY_KEY = {"deny": "o allows any provider.", "allow": "o asks only for those that keep no data."}


class AddModelPage(Page):
    """Add a model: cloud or local, one step at a time, in the service's words."""

    ENTRY = MenuEntry(
        "addmodel",
        "Add a model",
        "The guided first step: a cloud model at OpenRouter with your key (agreed once, the key hidden, a model from "
        "its live list, tested with one short request), or a local model on this computer's GPU.",
        "design 0016 §14",
        key="F12",
    )
    PANELS = tuple(f"add-{screen}" for screen in SCREENS)
    SCREENS = SCREENS
    SCREEN_OF: ClassVar[dict[str, str]] = {f"add-{screen}": screen for screen in SCREENS}
    KEYS: ClassVar[tuple[PageKey, ...]] = tuple(
        {key.key: key for screen in SCREENS for key in SCREEN_KEYS[screen]}.values()
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.screen_name = "choice"
        self.trail: list[str] = []  # the steps before this one, for Esc
        self.guide: dict[str, Any] | None = None  # the service's guide, as last read
        self.guide_said = ""  # why it could not be read
        self.policy = "deny"
        self.unmarked: set[str] = set()  # the MCP servers unmarked on the agreement step
        self.listed: list[str] = []  # the servers the agreement step lists, in order
        self.writing = False
        self.account: dict[str, Any] | None = None  # the key's account, as the service tells it
        self.models: list[dict[str, Any]] | None = None
        self.sort = SORTS[0]
        self.free = False
        self.search = ""
        self.model: dict[str, Any] | None = None  # the model picked
        self.filled: dict[str, str] = {}  # each setting as the service filled it
        self.preset: dict[str, Any] | None = None  # the preset written from it
        self.testing = ""  # the test's state: running, asking (load it now?), failed, or empty
        self.test_lines: list[str] = []
        self.answered = ""  # the short request's answer, its time and its cost, as the operation said them
        self.kept = False  # the local model kept running instead of the cloud one
        self.local: list[dict[str, Any]] | None = None  # the Local step's presets, as the service lists them

    def compose(self) -> ComposeResult:
        """One panel for each step; one shows at a time."""
        yield Panel(Label(id="add-choice-text"), title=TITLES["choice"], id="add-choice")
        yield Panel(Label(id="add-provider-text"), title=TITLES["provider"], id="add-provider")
        yield Panel(
            Label(id="add-agreement-text"),
            Label(id="add-servers-said", classes="hint"),
            ListView(id="add-servers"),
            title=TITLES["agreement"],
            id="add-agreement",
        )
        yield Panel(
            Label(id="add-key-text"),
            SecretField("", id="add-key-field"),
            Label(id="add-key-said"),
            Label(id="add-key-hint", classes="hint"),
            title=TITLES["key"],
            id="add-key",
        )
        yield Panel(
            Label(id="add-account"),
            Label(id="add-model-head", classes="hint"),
            Input(placeholder="a name or an id; Enter searches, Esc clears", id="add-search"),
            ListView(id="add-models"),
            Label(id="add-model-about", classes="hint"),
            title=TITLES["model"],
            id="add-model",
        )
        fields: list[Widget] = [Label(id="add-settings-text")]
        for key in FIELDS:
            fields += [Label(classes="form-label", id=f"add-{key}-label"), Input(id=f"add-{key}")]
        fields.append(Label(id="add-settings-note", classes="hint"))
        yield Panel(*fields, title=TITLES["settings"], id="add-settings")
        yield Panel(Label(id="add-test-text"), title=TITLES["test"], id="add-test")
        yield Panel(Label(id="add-ready-text"), title=TITLES["ready"], id="add-ready")
        yield Panel(
            Label(id="add-local-text"),
            ListView(id="add-presets"),
            Label(id="add-local-about", classes="hint"),
            title=TITLES["local"],
            id="add-local",
        )

    def on_mount(self) -> None:
        """Only the step on show is drawn."""
        super().on_mount()
        self._show_screen()

    def draw(self, data: ConsoleData, changed: set[str]) -> None:
        """Read the guide again when what it says may have changed."""
        if changed & GUIDE_READ_BY:
            self._read_guide()

    def shown_keys(self) -> tuple[PageKey, ...]:
        """The keys of the step on show (the test's: those that act as it stands)."""
        if self.screen_name == "test":
            wanted = {"asking": ("y", "n"), "failed": ("b", "k")}.get(self.testing, ())
            return tuple(key for key in SCREEN_KEYS["test"] if key.key in wanted)
        if self.screen_name == "ready" and self.step("ready").get("docker") in ("running", "not installed", None):
            return SCREEN_KEYS["ready"][:1]
        return SCREEN_KEYS[self.screen_name]

    @property
    def busy(self) -> bool:
        """While the test runs."""
        return self.testing == "running"

    def step(self, id: str) -> dict[str, Any]:
        """A step of the service's guide, as last read ({} before it is)."""
        return next((each for each in (self.guide or {}).get("steps", []) if each["id"] == id), {})

    def show_screen(self, screen: str) -> None:
        """Show one step as it stands, starting nothing (the tests of every page's panels)."""
        self._go(screen, keep=False)

    def start(self, screen: str = "choice") -> None:
        """Open on a step: `cloud` goes where the guide says Cloud starts (the provider, its key, or the model)."""
        self.trail = []
        if screen == "cloud":
            self._cloud()
        else:
            self._go(screen, keep=False)
        self._focus()

    def press(self, key: str) -> bool:
        """The keys of the step on show."""
        return bool(getattr(self, f"_press_{self.screen_name}")(key))

    def explain(self) -> tuple[str, list[str]]:
        """What the page is, and the step on show."""
        return f"Add a model · {self.step(self.screen_name).get('title') or TITLES[self.screen_name]}", [
            "Add a model is the first step: a model Clank can run, in the cloud with your OpenRouter key, or on this "
            "computer's GPU. Each step says what it does and what it costs, in the service's words; Backspace goes "
            "back a step, Esc to the menu.",
            "A key is never shown, logged or copied: it goes once to the service, which asks OpenRouter whether it "
            "takes it and keeps it only then, in CLANK_HOME/secrets, readable by you alone.",
        ]

    # Each step's keys.

    def _press_choice(self, key: str) -> bool:
        if key == "c":
            self._cloud()
        elif key == "l":
            self._go("local")
        else:
            return False
        return True

    def _press_provider(self, key: str) -> bool:
        if key == "enter":
            self._go("agreement")
        elif key == "backspace":
            self._back()
        else:
            return False
        return True

    def _press_agreement(self, key: str) -> bool:
        if key == "y":
            self._agree()
        elif key in ("n", "backspace"):
            self._back()
        elif key == "o":
            self.policy = "allow" if self.policy == "deny" else "deny"
            self._draw_agreement()
            self.console.say(f"data_collection {self.policy}: written when you agree")
        elif key == "space":
            self._toggle()
        else:
            return False
        return True

    def _press_key(self, key: str) -> bool:
        if key == "backspace":
            self._back()
            return True
        return False

    def _press_model(self, key: str) -> bool:
        search = self.query_one("#add-search", Input)
        if key == "escape" and search.display:
            search.value, self.search, search.display = "", "", False
            self._read_models()
            self.query_one("#add-models", ListView).focus()
        elif key == "backspace":
            self._back()
        elif key == "slash":
            search.display = True
            search.focus()
        elif key == "s":
            self.sort = SORTS[(SORTS.index(self.sort) + 1) % len(SORTS)]
            self._read_models()
        elif key == "f":
            self.free = not self.free
            self._read_models()
        else:
            return False
        return True

    def _press_settings(self, key: str) -> bool:
        if key == "backspace":
            self._back()
            return True
        return False

    def _press_test(self, key: str) -> bool:
        if self.testing == "asking" and key in ("y", "n"):
            if key == "y":
                self._follow("runtime/slots/main/switch", {"preset": self._preset_id()}, loading=True)
            else:
                self.kept, self.testing = True, ""
                self._go("ready", keep=False)
            return True
        if self.testing == "failed" and key in ("b", "k"):
            self.testing = ""
            self.trail = ["choice"]
            self._go("model" if key == "b" else "key")
            return True
        return False

    def _press_ready(self, key: str) -> bool:
        if key == "enter":
            self.console.show_page("folder")
        elif key == "s" and self.step("ready").get("docker") not in ("running", "not installed", None):
            self.console.ask_docker(stop=False)
        else:
            return False
        return True

    def _press_local(self, key: str) -> bool:
        if key == "backspace":
            self._back()
            return True
        return False

    def on_secret_field_submitted(self, event: SecretField.Submitted) -> None:
        """Enter in the key's field: send it once, and hold it no longer."""
        event.stop()
        if not event.field.filled:
            self.console.say("paste your key first", True)
            return
        self._send_key(event.field.take())

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Enter on a model: its settings; on a local preset: its steps, each asked first."""
        index = event.list_view.index
        if event.list_view.id == "add-models" and self.models and index is not None:
            event.stop()
            self.model = self.models[index]
            self._go("settings")
        elif event.list_view.id == "add-presets" and self.local and index is not None and index < len(self.local):
            event.stop()
            self._next_step(list(self.local[index]["steps"]))

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """The highlighted model, in its own words, under the list."""
        if event.list_view.id == "add-models":
            self._about()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Enter in the search: the list, narrowed; in a setting: take them all."""
        event.stop()
        if event.input.id == "add-search":
            self.search = event.value.strip()
            self._read_models()
            self.query_one("#add-models", ListView).focus()
        elif self.screen_name == "settings":
            self._take_settings()

    # The guide.

    def _read_guide(self, then: Any = None) -> None:
        client, folder, preset = self.console.client, self.console.folder, self._preset_id()

        def read() -> None:
            try:
                found = client.get("runtime/guide", preset=preset, folder=folder)
            except Exception as error:
                self.console.call_from_thread(self._guide_read, None, f"Add a model's steps could not be read: {error}")
                return
            self.console.call_from_thread(self._guide_read, found, "")
            if then is not None:
                self.console.call_from_thread(then)

        self.run_worker(read, thread=True, group="add-guide", exclusive=then is None, exit_on_error=False)

    def _guide_read(self, found: dict[str, Any] | None, said: str) -> None:
        if found is not None:
            self.guide = found
        self.guide_said = said
        self._draw_steps()

    def _draw_steps(self) -> None:
        """Every step's words from the guide; the step on show's lists too."""
        for screen in SCREENS:
            self.query_one(f"#add-{screen}", Panel).title = self.step(screen).get("title") or TITLES[screen]
        choice = self.step("choice")
        options = [f"{each['key']}  {each['said']}" for each in choice.get("options", [])]
        text = "\n\n".join([*choice.get("said", []), *options]) or self.guide_said or "Reading Add a model's steps..."
        self.query_one("#add-choice-text", Label).update(text)
        self.query_one("#add-provider-text", Label).update("\n\n".join(self.step("provider").get("said", [])))
        key = self.step("key")
        self.query_one("#add-key-text", Label).update(" ".join(key.get("said", [])))
        field = self.query_one("#add-key-field", SecretField)
        if field.placeholder != key.get("placeholder", ""):
            field.placeholder = key.get("placeholder", "")
            field.refresh()
        self.query_one("#add-key-hint", Label).update(f"Enter: {key['hint']}" if key.get("hint") else "")
        local = self.step("local")
        self.query_one("#add-local-text", Label).update(" ".join(local.get("said", [])))
        if self.screen_name == "agreement":
            self._draw_agreement()
        if self.screen_name == "ready":
            self._show_ready()
        if self.screen_name == "test":
            self._show_test()

    # Moving between steps.

    def _go(self, screen: str, keep: bool = True) -> None:
        if keep and screen != self.screen_name:
            self.trail.append(self.screen_name)
        self.screen_name = screen
        if self._ready:
            self._show_screen()
            self._focus()

    def _back(self) -> None:
        self._go(self.trail.pop() if self.trail else "choice", keep=False)

    def _cloud(self) -> None:
        """Cloud: where the guide says it starts."""
        self._go(str((self.guide or {}).get("cloud_from") or "provider"))

    def _show_screen(self) -> None:
        for screen in SCREENS:
            self.query_one(f"#add-{screen}", Panel).display = screen == self.screen_name
        self._draw_steps()
        if self.screen_name == "model":
            self.query_one("#add-search", Input).display = bool(self.search)
            self._show_account()
            self._read_models()
        if self.screen_name == "settings":
            self._fill_settings()
        if self.screen_name == "test":
            self._run_test()
        if self.screen_name == "local":
            self._read_local()
        self.scroll_home(animate=False)
        self._keys()

    def _keys(self) -> None:
        if self.console.query("#keys"):
            self.console.query_one("#keys", KeysBar).show_keys(self.shown_keys())

    def _focus(self) -> None:
        """The focus where the step's keys act: its field or list, else the page itself."""
        target: Widget = self
        if self.screen_name == "key":
            target = self.query_one("#add-key-field", SecretField)
        elif self.screen_name == "agreement" and self.listed:
            target = self.query_one("#add-servers", ListView)
        elif self.screen_name == "model":
            target = self.query_one("#add-models", ListView)
        elif self.screen_name == "settings":
            target = self.query_one("#add-title", Input)
        elif self.screen_name == "local" and self.local:
            target = self.query_one("#add-presets", ListView)
        target.focus()

    # The agreement.

    def _draw_agreement(self) -> None:
        step = self.step("agreement")
        policy = step.get("policy", {}).get(self.policy, "")
        said = [*step.get("said", []), f"{policy} {POLICY_KEY[self.policy]}" if policy else ""]
        self.query_one("#add-agreement-text", Label).update("\n\n".join(line for line in said if line))
        self.query_one("#add-servers-said", Label).update(step.get("servers_said", ""))
        names = [server["name"] for server in step.get("servers", [])]
        listing = self.query_one("#add-servers", ListView)
        if names != self.listed:
            self.listed = names
            listing.clear()
            listing.extend(ListItem(Label(self._server_line(name))) for name in names)
            listing.index = 0 if names else None
        listing.display = bool(names)

    def _server_line(self, name: str) -> str:
        marks = self.step("agreement").get("marks", {})
        return f"{name}  {marks.get('cloud' if name in self.unmarked else 'local', '')}"

    def _toggle(self) -> None:
        listing = self.query_one("#add-servers", ListView)
        if listing.index is None or not self.listed:
            return
        name = self.listed[listing.index]
        self.unmarked ^= {name}
        listing.children[listing.index].query_one(Label).update(self._server_line(name))

    def _agree(self) -> None:
        """Agree to what was shown: never to a screen whose words were not read. The servers as marked; when none is
        listed, none is named, which the service reads as every server already added."""
        if self.writing:
            return
        if not self.step("agreement").get("said"):
            self.console.say("the agreement is not read yet: nothing is agreed to a screen that says nothing", True)
            self._read_guide()
            return
        self.writing = True
        client, policy = self.console.client, self.policy
        body: dict[str, Any] = {"id": "openrouter", "adapter": "openrouter", "agree": True}
        if self.listed:
            body["local_mcp"] = [name for name in self.listed if name not in self.unmarked]

        def write() -> None:
            try:
                client.post("runtime/endpoints", body)
                if policy == "allow":
                    client.patch("runtime/endpoints/openrouter", {"options": {"data_collection": "allow"}})
            except Exception as error:
                self.console.call_from_thread(self._refused, str(error))
                return
            self.console.call_from_thread(self._agreed)

        self.run_worker(write, thread=True, group="add-model", exit_on_error=False)

    def _agreed(self) -> None:
        self.writing = False
        self.console.say("OpenRouter is added, with your agreement: now your key")
        self.trail = [step for step in self.trail if step not in ("provider", "agreement")]  # done: Esc skips them
        self._go("key", keep=False)

    def _refused(self, words: str) -> None:
        self.writing = False
        self.console.say(words, True)

    # The key.

    def _send_key(self, key: str) -> None:
        """Send the key once, in the body of one call, off the screen's thread; the page keeps nothing of it."""
        client = self.console.client
        self.query_one("#add-key-said", Label).update("Asking OpenRouter whether it takes the key...")

        def send(given: str) -> None:
            try:
                answer = client.put("runtime/endpoints/openrouter/key", {"key": given})
            except Exception as error:
                self.console.call_from_thread(self._key_refused, str(error))
                return
            self.console.call_from_thread(self._key_taken, answer)

        self.run_worker(
            partial(send, key),
            thread=True,
            group="add-model",
            description="send the key to the service",  # Textual logs a worker as its description, else its call's repr
            exit_on_error=False,
        )
        del key  # the worker holds it for its one call, and no longer

    def _key_taken(self, answer: dict[str, Any]) -> None:
        self.account = answer.get("account")
        self.query_one("#add-key-said", Label).update("")
        self.console.say(f"OpenRouter took the key; Clank keeps it (ends …{answer['key']['ends']})")
        self._go("model")

    def _key_refused(self, words: str) -> None:
        self.query_one("#add-key-said", Label).update(f"{words}\n{self.step('key').get('refused', '')}".strip())
        self.console.say(words, True)

    # The model.

    def _show_account(self) -> None:
        self.query_one("#add-account", Label).update(
            (self.account or {}).get("said", "The key's account is being read.")
        )
        if self.account is not None:
            return
        client = self.console.client

        def read() -> None:
            try:
                found = client.get("runtime/endpoints/openrouter/account")
            except Exception as error:
                self.console.call_from_thread(self.query_one("#add-account", Label).update, f"The account: {error}")
                return
            self.console.call_from_thread(self._account_read, found)

        self.run_worker(read, thread=True, group="add-account", exclusive=True, exit_on_error=False)

    def _account_read(self, found: dict[str, Any]) -> None:
        self.account = found
        self.query_one("#add-account", Label).update(found.get("said", ""))

    def _read_models(self) -> None:
        client, search, sort, free = self.console.client, self.search, self.sort, self.free
        self.query_one("#add-model-head", Label).update("Reading OpenRouter's list...")

        def read() -> None:
            try:
                found = client.get("runtime/endpoints/openrouter/models", search=search, sort=sort, free=free)
            except Exception as error:
                self.console.call_from_thread(self._models_read, {"models": [], "said": str(error)})
                return
            self.console.call_from_thread(self._models_read, found)

        self.run_worker(read, thread=True, group="add-models", exclusive=True, exit_on_error=False)

    def _models_read(self, found: dict[str, Any]) -> None:
        self.models = list(found["models"])
        self.query_one("#add-model-head", Label).update(found.get("said", ""))
        listing = self.query_one("#add-models", ListView)
        listing.clear()
        listing.extend(ListItem(Label(f"{model['said']['name']}\n  {model['said']['facts']}")) for model in self.models)
        listing.index = 0 if self.models else None
        self._about()

    def _about(self) -> None:
        index = self.query_one("#add-models", ListView).index
        model = self.models[index] if self.models and index is not None and index < len(self.models) else None
        self.query_one("#add-model-about", Label).update(model["said"]["about"] if model else "")

    # Its settings.

    def _fill_settings(self) -> None:
        model = self.model
        if model is None:
            return
        fields = [*model["settings"], *self.step("settings").get("limits", [])]  # the model's, then the limits
        self.filled = {field["id"]: field["value"] for field in fields}
        for field in fields:
            self.query_one(f"#add-{field['id']}-label", Label).update(field["said"])
            self.query_one(f"#add-{field['id']}", Input).value = field["value"]
        self.query_one("#add-settings-text", Label).update(f"{model['name']} ({model['id']})")
        hint = self.step("settings").get("hint", "")
        self.query_one("#add-settings-note", Label).update(
            f"{hint} One short request: {model['said']['test']} at its prices. Enter takes these."
        )

    def _take_settings(self) -> None:
        model = self.model
        if model is None or self.writing:
            return
        typed = {key: self.query_one(f"#add-{key}", Input).value for key in FIELDS}
        body = {"model": model["id"], **{key: typed[key] for key in FIELDS if key not in LIMITS}}
        try:
            limits = {key: dollars(typed[key]) for key in LIMITS if typed[key] != self.filled.get(key)}
        except ValueError as error:
            self._refused(str(error))
            return
        client, folder = self.console.client, self.console.folder
        self.writing = True

        def write() -> None:
            try:
                preset, _ = written(client, body)
                if limits:
                    client.put("gateway/cost/limits", limits)
                guide = client.get("runtime/guide", preset=preset["id"], folder=folder)
            except Exception as error:
                self.console.call_from_thread(self._refused, str(error))
                return
            self.console.call_from_thread(self._written, preset, guide)

        self.run_worker(write, thread=True, group="add-model", exit_on_error=False)

    def _written(self, preset: dict[str, Any], guide: dict[str, Any]) -> None:
        self.writing = False
        self.preset, self.guide = preset, guide
        self.console.say(f"{preset['title']} is written: now its test")
        self.testing, self.test_lines, self.answered, self.kept = "", [], "", False
        self._go("test")

    # The test.

    def _preset_id(self) -> str:
        return str((self.preset or {}).get("id", ""))

    def _run_test(self) -> None:
        """As the guide's test step says: load the preset, or test it beside the local model that runs."""
        if self.testing or not self.preset:
            self._show_test()
            return
        test = self.step("test")
        self.test_lines = list(test.get("said", []))
        if test.get("mode") == "ask":
            self._follow("runtime/endpoints/openrouter/test", {"preset": self._preset_id()}, loading=False)
        else:
            self._follow("runtime/slots/main/load", {"preset": self._preset_id()}, loading=True)

    def _follow(self, path: str, body: dict[str, Any], loading: bool) -> None:
        """Start an operation and follow it on the screen: its log as it is written, then how it ended."""
        client = self.console.client
        self.testing = "running"
        self._show_test()

        def work() -> None:
            try:
                operation = client.post(path, body)
                ended, seen = None, 0
                while ended is None and self.console.is_running:
                    values = client.get(f"records/operation/{operation['id']}")["values"]
                    lines = client.get(f"operations/{operation['id']}/log", after=seen)
                    if lines:
                        seen = lines[-1]["number"]
                        self.console.call_from_thread(self._logged, [line["text"] for line in lines])
                    if values["status"] in ENDED:
                        ended = values
                    else:
                        time.sleep(POLL_SECONDS)
            except Exception as error:
                self.console.call_from_thread(self._test_ended, {"status": "failed", "error": str(error)}, loading)
                return
            if ended is not None:
                self.console.call_from_thread(self._test_ended, ended, loading)

        self.run_worker(work, thread=True, group="add-test", exclusive=True, exit_on_error=False)

    def _logged(self, lines: list[str]) -> None:
        self.test_lines = [*self.test_lines, *lines][-SHOWN_LINES:]
        self._show_test()

    def _test_ended(self, ended: dict[str, Any], loading: bool) -> None:
        result = ended.get("result") or {}
        if ended["status"] == "done" and result.get("ok", True):
            self.answered = str(result.get("said") or (self.test_lines[-1] if self.test_lines else ""))
            if loading:
                self.testing = ""
                self._read_guide()
                self._go("ready", keep=False)
                return
            self.testing = "asking"
        else:
            self.testing = "failed"
            self.answered = str(result.get("said") or ended.get("error") or ended["status"])
        self._show_test()

    def _show_test(self) -> None:
        test = self.step("test")
        lines = list(self.test_lines)
        if self.testing == "asking":
            lines += ["", f"It answered: {self.answered}", "", test.get("ask", "")]
        elif self.testing == "failed":
            lines += ["", f"It failed: {self.answered}", "", test.get("failed", "")]
        self.query_one("#add-test-text", Label).update("\n".join(lines) or "Starting the test...")
        if self.screen_name == "test":
            self._keys()

    # Ready.

    def _show_ready(self) -> None:
        ready = self.step("ready")
        runs = ready.get("kept" if self.kept else "runs", "")
        answered = f" Its test: {self.answered}." if self.answered else ""
        said = [f"{runs}{answered}", *ready.get("said", [])]
        self.query_one("#add-ready-text", Label).update("\n\n".join(line for line in said if line))
        if self.screen_name == "ready":
            self._keys()

    # Local.

    def _read_local(self) -> None:
        client = self.console.client

        def read() -> None:
            try:
                found = client.get("runtime/guide/local")
            except Exception as error:
                self.console.call_from_thread(self.console.say, f"the presets could not be read: {error}", True)
                return
            self.console.call_from_thread(self._local_read, found["presets"])

        self.run_worker(read, thread=True, group="add-local", exclusive=True, exit_on_error=False)

    def _local_read(self, presets: list[dict[str, Any]]) -> None:
        self.local = presets
        listing = self.query_one("#add-presets", ListView)
        index = listing.index
        listing.clear()
        listing.extend(ListItem(Label("\n  ".join(preset["said"]))) for preset in presets)
        listing.index = index if index is not None and index < len(presets) else (0 if presets else None)
        self.query_one("#add-local-about", Label).update("" if presets else "Clank has no preset for the main slot.")
        if self.screen_name == "local":
            self._focus()

    def _next_step(self, steps: list[dict[str, Any]]) -> None:
        """The next step a local preset needs, as the service gives it: asked first, with its words and its call."""
        if not steps:
            return
        step, rest = steps[0], steps[1:]
        call = step["call"]
        if call is None:  # a step that cannot be done from here: the service says what to do instead
            self.console.say(step["asks"], True)
            return
        lines = [step["asks"], f"The call: {call['method']} /api/v1/{call['path']} {json.dumps(call['body'])}"]

        def answered(yes: bool | None) -> None:
            if not yes:
                self.console.say("nothing was done")
                return
            client = self.console.client

            def work() -> None:
                try:
                    operation = client.post(call["path"], call["body"])
                except Exception as error:
                    self.console.call_from_thread(self.console.say, str(error), True)
                    return
                ended = follow(client, operation["id"], lambda: not self.console.is_running)
                if ended is None:
                    return
                if ended["status"] != "done":
                    words = ended.get("error") or ended["status"]
                    self.console.call_from_thread(self.console.say, f"{step['said']}: {words}", True)
                elif step["kind"] == "load":
                    self.console.call_from_thread(self._local_loaded)
                else:
                    self.console.call_from_thread(self._next_step, rest)

            self.console.say(f"{step['said']}: started")
            self.run_worker(work, thread=True, group="add-local-step", exit_on_error=False)

        self.console.push_screen(ConfirmScreen(step["title"], lines), answered)

    def _local_loaded(self) -> None:
        self.preset, self.kept = None, False
        self._read_guide()
        self._go("ready", keep=False)
