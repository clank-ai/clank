"""The providers someone else runs, reached at their URL with the owner's key (design 0016 §4-§6): OpenRouter first.

A provider's record (`config/endpoints/<id>.json`, the kind `endpoint`) is checked against its adapter whenever it is
read or written (`record_problems`): its URL, reach and auth must be the adapter's own, so the key never goes elsewhere,
and its options the adapter's. It is added only with the owner's agreement (design 0016 §9), which marks the MCP
servers the agreement screen named local only (the tools component hears `runtime.endpoint_added`; the runtime uses
no component, decision 0019).

Its key is a secret of the kernel (`endpoint/<id>`, named `key`), kept only once the provider accepts it (its account,
asked with it first), shown by its last four characters and when it was set, and never written anywhere else: not in
the record, an answer, an event or a log. The account is read with the key at most once a minute (`fresh` asks again);
each read of the key is recorded by the kernel (`secret.used`).
"""

import dataclasses
import json
import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx2

from clank.components.runtime import guide
from clank.components.runtime.adapters import ENDPOINTS
from clank.components.runtime.adapters.endpoint import Account, EndpointAdapter, ModelLine, Place
from clank.components.runtime.kinds import Endpoint, Preset
from clank.kernel.adapters import AdapterError
from clank.kernel.api import ApiError
from clank.kernel.clock import from_text, to_text
from clank.kernel.events import Actor, EventType, Subject
from clank.kernel.records import Settings
from clank.kernel.secrets import SecretsError
from clank.kernel.settings import SettingsError

if TYPE_CHECKING:
    from clank.components.runtime.service import Runtime

KIND = "endpoint"
ACCOUNT_SECONDS = 60.0  # how long an account read is kept
MODELS_SECONDS = 3600.0  # how long a list of models is kept
SORTS = ("most-popular", "price", "context", "newest")
KNOWN = "endpoint-models.json"  # in the home's state: each provider's models as last listed
READ_AT = "_read_at"  # in it: when each provider's list was last read
ASK_SECONDS = 15.0  # how long a provider is given to answer one of the service's own requests
RUNS = ("starting", "ready", "stopping")
EVENT_TYPES = [
    EventType(
        "runtime.endpoint_added",
        "A provider someone else runs was added with the owner's agreement (design 0016 §9): its record written.",
        {
            "id": "The provider's record.",
            "adapter": "Its adapter, such as openrouter.",
            "local_mcp": "The MCP servers the agreement marked local only; null: every one already added.",
        },
        owner="runtime",
    ),
    EventType(
        "runtime.endpoint_changed",
        "A provider's options or agreement changed.",
        {"id": "The provider's record.", "fields": "The fields that changed."},
        owner="runtime",
    ),
    EventType(
        "runtime.endpoint_removed",
        "A provider was removed, with its key.",
        {"id": "The provider's record."},
        owner="runtime",
    ),
]


def record_problems(id: str, record: Settings) -> list[tuple[Place, str]]:
    """What a provider's record says that its adapter does not take, each with the place of its field."""
    values = record.model_dump()
    try:
        adapter = ENDPOINTS.get(str(values.get("adapter")))
    except AdapterError as error:
        return [(("adapter",), str(error))]
    return adapter.record_problems(values)


def slug(title: str) -> str:
    """A preset's id from its title: `cloud: Example Coder` is `cloud-example-coder`."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "cloud"


def scope(id: str) -> str:
    """Where a provider's key is kept among the secrets."""
    return f"{KIND}/{id}"


class Endpoints:
    """The providers' records, their keys and what their providers say of them."""

    def __init__(self, runtime: "Runtime") -> None:
        self.runtime = runtime
        self.kernel = runtime.kernel
        self._accounts: dict[str, tuple[float, Account, str]] = {}  # each provider's account, when read
        self._lists: dict[tuple[str, str, bool], tuple[float, list[ModelLine], str]] = {}  # each list, when read

    def record(self, id: str) -> Endpoint:
        """A provider's record; 404 when there is none."""
        try:
            loaded = self.kernel.settings.get(KIND, id)
        except SettingsError as error:
            raise ApiError(404, "not_found", f"there is no provider {id}: Add a model adds one") from error
        return Endpoint.model_validate(loaded.record.model_dump())

    def adapter(self, id: str) -> EndpointAdapter:
        """The adapter of a provider's record."""
        return ENDPOINTS.get(self.record(id).adapter)()

    def views(self) -> list[dict[str, Any]]:
        """Every provider, as clients show it."""
        return [self.view(loaded.id) for loaded in self.kernel.settings.records(KIND)]

    def view(self, id: str) -> dict[str, Any]:
        """A provider as clients show it (plan s34's EndpointView): its record, its key (set, its last four, when),
        the presets that name it, what runs one of them, and its last check."""
        record = self.record(id)
        loaded = self.kernel.settings.get(KIND, id)
        presets = self.presets(id)
        dev = self.dev_mode()
        running = None
        for slot in self.runtime.state.slots(self.runtime.settings().slots):
            if slot.status in RUNS and slot.preset in presets:
                running = {"slot": slot.name, "preset": slot.preset}
        return {
            "id": id, "title": record.title or id, "adapter": record.adapter, "url": record.url,
            "reach": record.reach, "options": dict(record.options), "agreed": record.agreed,
            "key": self.key_view(id), "presets": presets, "running": running, "check": self.last_check(id),
            "source": loaded.source, "file": str(loaded.path or loaded.user_file), "dev_mode": dev,
            "said": {"policy": guide.policy_said(str(record.options.get("data_collection", "deny")), dev)},
        }  # fmt: skip

    def dev_mode(self) -> bool:
        """Whether dev mode is on (decisions 0149 and 0152): every cloud provider asked for any of a model's providers,
        and every public host open to the agent."""
        return self.runtime.settings().dev_mode

    def dev_view(self) -> dict[str, Any]:
        """Dev mode as clients show it: on or off, and what that means."""
        on = self.dev_mode()
        return {"on": on, "said": guide.DEV_SAID[on]}

    def set_dev(self, on: bool, *, actor: Actor) -> dict[str, Any]:
        """Turn dev mode on or off in the runtime's settings, recorded with who did it; the next request and the
        agent's next connection go so (the gateway reads it with its routes, decision 0152)."""
        loaded = self.kernel.settings.get("runtime", "runtime")
        values = loaded.record.model_dump(mode="json")
        if values.get("dev_mode") is not on:
            values["dev_mode"] = on
            self.kernel.settings.write("runtime", "runtime", values, base=loaded.revision, actor=actor)
        return self.dev_view()

    def presets(self, id: str) -> list[str]:
        """The presets that name a provider."""
        return [
            loaded.id
            for loaded in self.kernel.settings.records("preset")
            if loaded.record.model_dump().get("endpoint") == id
        ]

    def last_check(self, id: str) -> dict[str, Any] | None:
        """A provider's last check: when, whether it passed, and each item; None before the first."""
        rows = self.kernel.store.read(
            "SELECT * FROM endpoint_checks WHERE endpoint = ? AND kind = 'check' ORDER BY id DESC LIMIT 1", (id,)
        )
        if not rows:
            return None
        return {"time": rows[0]["time"], "ok": bool(rows[0]["ok"]), "items": json.loads(rows[0]["items"])}

    def keep_check(self, id: str, kind: str, ok: bool, items: list[dict[str, Any]], usd: float) -> None:
        """Keep a check's or a test's result and what its requests cost."""
        with self.kernel.store.transaction() as db:
            db.execute(
                "INSERT INTO endpoint_checks (endpoint, kind, time, ok, items, cost_usd) VALUES (?, ?, ?, ?, ?, ?)",
                (id, kind, to_text(self.kernel.clock.now()), int(ok), json.dumps(items), usd),
            )

    def own_costs(self, since: str = "", until: str = "") -> float:
        """What the runtime's own requests to providers cost from `since` to before `until` (Clank's times; empty:
        no bound), in US dollars: each cloud launch's tiny request, each check and test (design 0016 §12)."""
        last = until or "9999"
        launches = self.kernel.store.read(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM launches"
            " WHERE endpoint != '' AND started_at >= ? AND started_at < ?",
            (since, last),
        )[0][0]
        checks = self.kernel.store.read(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM endpoint_checks WHERE time >= ? AND time < ?", (since, last)
        )[0][0]
        return float(launches) + float(checks)

    def add(self, id: str, adapter: str, *, agree: bool, local_mcp: list[str] | None, actor: Actor) -> dict[str, Any]:
        """Write a provider's record from its adapter's template, agreed now; refused without the agreement, or when
        one of that id exists."""
        if not agree:
            raise ApiError(
                400,
                "agreement_needed",
                "adding a cloud provider needs your agreement that prompts, and the files and command output the "
                "agent reads, go to it (agree)",
            )
        try:
            made = ENDPOINTS.get(adapter)
        except AdapterError as error:
            raise ApiError(400, "invalid", str(error)) from error
        if any(loaded.id.lower() == id.lower() for loaded in self.kernel.settings.records(KIND)):
            raise ApiError(409, "exists", f"there is a provider {id} already")
        now = self.kernel.clock.now()
        values = {**made.template(), "agreed": to_text(now), "notes": f"Added by {actor.describe()}."}
        self._write(id, values, actor, base=None)
        self.kernel.events.record(
            "runtime.endpoint_added",
            summary=f"{actor.describe()} added {made.LABEL} ({id}), agreeing to what goes to it",
            actor=actor,
            subject=Subject(kind=KIND, id=id),
            data={"id": id, "adapter": adapter, "local_mcp": local_mcp},
        )
        return self.view(id)

    def change(self, id: str, values: Mapping[str, Any], *, actor: Actor) -> dict[str, Any]:
        """Change a provider's options (merged with its own), its read timeout or notes, or its agreement (empty
        withdraws it; any other value agrees now)."""
        self.record(id)
        loaded = self.kernel.settings.get(KIND, id)
        record = loaded.record.model_dump()
        changed = dict(record)
        if "options" in values:
            changed["options"] = {**record["options"], **dict(values["options"] or {})}
        for name in ("timeout_seconds", "notes"):
            if name in values:
                changed[name] = values[name]
        if "agreed" in values:
            changed["agreed"] = to_text(self.kernel.clock.now()) if values["agreed"] else ""
        fields = [name for name in changed if changed[name] != record[name]]
        if not fields:
            return self.view(id)
        self._write(id, changed, actor, base=loaded.revision)
        self.kernel.events.record(
            "runtime.endpoint_changed",
            summary=f"{actor.describe()} changed {', '.join(fields)} of the provider {id}",
            actor=actor,
            subject=Subject(kind=KIND, id=id),
            data={"id": id, "fields": fields},
        )
        return self.view(id)

    def remove(self, id: str, *, actor: Actor) -> dict[str, Any]:
        """Remove a provider and its key; refused while a slot runs one of its presets or a preset names it."""
        view = self.view(id)
        if view["running"] or view["presets"]:
            running = view["running"]
            said = [f"the {running['slot']} slot runs {running['preset']}"] if running else []
            said += [f"the preset {preset} names it" for preset in view["presets"]]
            raise ApiError(409, "in_use", f"{id} is in use: {'; '.join(said)}", slot=running, presets=view["presets"])
        loaded = self.kernel.settings.get(KIND, id)
        self.kernel.settings.delete(KIND, id, base=loaded.revision, actor=actor)
        self.kernel.secrets.remove(scope(id), actor=actor)
        self._accounts.pop(id, None)
        self.kernel.events.record(
            "runtime.endpoint_removed",
            summary=f"{actor.describe()} removed the provider {id}, with its key",
            actor=actor,
            subject=Subject(kind=KIND, id=id),
            data={"id": id},
        )
        return {"removed": id}

    def key_view(self, id: str) -> dict[str, Any]:
        """A provider's key as clients see it: whether it is set, its last four characters, when it was set."""
        for shown in self.kernel.secrets.shown(scope(id)):
            if shown.name == "key":
                return {"set": True, "ends": shown.ends, "set_at": shown.set}
        return {"set": False, "ends": "", "set_at": ""}

    def key(self, id: str, *, user: str, why: str) -> str:
        """A provider's key, for whoever sends it (recorded with who and why); 400 `key_not_set` when none is."""
        try:
            return self.kernel.secrets.value(scope(id), "key", user=user, why=why)
        except SecretsError as error:
            raise ApiError(
                400, "key_not_set", f"no key is set for {id}: Providers and models, k; or clank endpoint key {id}"
            ) from error

    def set_key(self, id: str, key: str, *, actor: Actor) -> dict[str, Any]:
        """Keep a provider's key once the provider accepts it (its account, asked with it); a refused key, or no
        answer, keeps nothing."""
        key = key.strip()
        if not key:
            raise ApiError(400, "invalid", "the key is empty")
        account = self._read_account(id, key)
        self.kernel.secrets.put(scope(id), "key", key, actor=actor)
        read_at = to_text(self.kernel.clock.now())
        self._accounts[id] = (self._now(), account, read_at)
        return {"key": self.key_view(id), "account": account.view(read_at)}

    def remove_key(self, id: str, *, actor: Actor) -> dict[str, Any]:
        """Forget a provider's key."""
        self.record(id)
        self.kernel.secrets.remove(scope(id), "key", actor=actor)
        self._accounts.pop(id, None)
        return {"key": self.key_view(id)}

    def account(self, id: str, *, fresh: bool = False) -> dict[str, Any]:
        """The key's own facts, as the provider counts them: read at most once a minute unless `fresh`."""
        kept = self._accounts.get(id)
        if kept is not None and not fresh and self._now() - kept[0] < ACCOUNT_SECONDS:
            return kept[1].view(kept[2])
        key = self.key(id, user="runtime", why=f"reading the account of {id}")
        account = self._read_account(id, key)
        read_at = to_text(self.kernel.clock.now())
        self._accounts[id] = (self._now(), account, read_at)
        return account.view(read_at)

    def models(
        self, id: str, *, search: str = "", sort: str = "most-popular", free: bool = False, everything: bool = False,
        fresh: bool = False,
    ) -> dict[str, Any]:  # fmt: skip
        """The provider's live list of models, read with the key and kept an hour (`fresh` asks again): those that take
        tool calls unless `everything`; narrowed by `search` (a name or an id) and to the free ones (`free`); sorted
        most used first (the provider's own order, within programming), by price (cheapest in first), by window
        (largest first) or newest first."""
        if sort not in SORTS:
            raise ApiError(400, "invalid", f"sort is one of {', '.join(SORTS)}, not {sort!r}")
        lines, read_at = self.lines(id, sort=sort, everything=everything, fresh=fresh)
        wanted = search.strip().lower()
        shown = [
            line for line in lines
            if (not wanted or wanted in line.id.lower() or wanted in line.name.lower()) and (line.free or not free)
        ]  # fmt: skip
        if sort == "price":
            shown.sort(key=lambda line: (line.price_in, line.price_out, line.id))
        elif sort == "context":
            shown.sort(key=lambda line: (-line.window, line.id))
        elif sort == "newest":
            shown.sort(key=lambda line: (-line.created, line.id))
        return {"models": [line.view() for line in shown], "count": len(shown), "sort": sort, "read_at": read_at}

    def lines(
        self, id: str, *, sort: str = "most-popular", everything: bool = False, fresh: bool = False
    ) -> tuple[list[ModelLine], str]:
        """The provider's list as Clank's lines, and when it was read: kept an hour unless `fresh`."""
        asked = (id, "most-popular" if sort == "most-popular" else "", everything)
        kept = self._lists.get(asked)
        if kept is not None and not fresh and self._now() - kept[0] < MODELS_SECONDS:
            return kept[1], kept[2]
        adapter = self.adapter(id)
        key = self.key(id, user="runtime", why=f"reading the models of {id}")
        answer = self.ask(id, key, "GET", "/models", params=adapter.models_query(asked[1], everything=everything))
        if answer.status_code != 200:
            raise self.refused(id, answer)
        try:
            lines = adapter.models(answer.json(), everything=everything)
        except (ValueError, TypeError, AttributeError) as error:
            raise ApiError(502, "refused", f"{adapter.LABEL}'s list of models could not be read: {error}") from error
        read_at = to_text(self.kernel.clock.now())
        self._lists[asked] = (self._now(), lines, read_at)
        self._remember(id, lines)
        return lines, read_at

    def model(self, id: str, model: str) -> ModelLine:
        """One model of the provider's whole list, by its id exactly as listed; 400 `unknown_model` when it lists
        none of that id."""
        lines, _ = self.lines(id, sort="", everything=True)
        for line in lines:
            if line.id == model:
                return line
        raise ApiError(
            400, "unknown_model", f"{self.adapter(id).LABEL} lists no model {model}: clank endpoint models {id}"
        )

    def known(self, id: str, model: str) -> ModelLine | None:
        """A model's line as the provider last listed it (kept in `state/endpoint-models.json`, so its prices outlive a
        restart); None when it was never listed here."""
        found = self._remembered().get(id, {}).get(model)
        if not isinstance(found, dict) or id == READ_AT:
            return None
        try:
            return ModelLine(**{**found, "efforts": tuple(found.get("efforts") or ())})
        except TypeError:
            return None

    def facts(self, id: str, preset: Preset) -> dict[str, Any] | None:
        """A cloud preset's facts, as the Monitor reads them (design 0016 §13): its provider's context facts for its
        options, from the model's line as last listed, and the model's (no template, no calibration: the parts are
        estimated at Clank's plain default); None while its model was never listed here."""
        line = self.known(preset.endpoint, preset.model)
        if line is None:
            return None
        try:
            adapter = self.adapter(preset.endpoint)
        except ApiError:
            return None
        read = str((self._remembered().get(READ_AT) or {}).get(preset.endpoint) or "")
        when = from_text(read).astimezone().strftime("%H:%M") if read else "before"
        context = adapter.context_facts(line, preset.options, when)
        provider = f"cloud {preset.endpoint}"
        engine = {
            "name": preset.endpoint,
            "label": adapter.LABEL,
            "version": "",
            "provider": provider,
            **context.view(),
        }
        model = {"id": line.id, "name": line.name, "template": None, "calibration": None}
        return {"preset": id, "title": preset.title or id, "engine": engine, "model": model}

    def preset_problems(self, preset: Preset) -> list[str]:
        """What stops a cloud preset from loading, one sentence each: its provider not added, not agreed to, or
        without a key; its options wrong for its adapter."""
        id = preset.endpoint
        try:
            record = self.record(id)
        except ApiError as error:
            return [str(error)]
        problems = []
        if not record.is_agreed:
            problems.append(f"{id} is not agreed to: Add a model, or clank endpoint add {id}, asks you first")
        if not self.key_view(id)["set"]:
            problems.append(f"no key is set for {id}: Providers and models, k; or clank endpoint key {id}")
        try:
            problems += ENDPOINTS.get(record.adapter)().option_problems(preset.options)
        except AdapterError as error:
            problems.append(str(error))
        return problems

    def preset_price(self, preset: Preset) -> dict[str, float | None] | None:
        """A cloud preset's model's prices per million tokens, as its provider last listed them; None when not known."""
        line = self.known(preset.endpoint, preset.model)
        if line is None:
            return None
        return {"in": line.price_in, "out": line.price_out, "cached_in": line.price_cached_in}

    def write_preset(
        self, id: str, model: str, *, title: str = "", wanted: Mapping[str, Any], actor: Actor
    ) -> dict[str, Any]:
        """Write a cloud preset for one of the provider's models: never one without tool calls (the agent cannot
        work without them); its options those wanted, else the model's (design 0016 §7)."""
        line = self.model(id, model)
        if not line.tools:
            raise ApiError(
                400, "no_tools", f"{line.id} does not take tool calls, and the agent cannot work without them"
            )
        try:
            options = self.adapter(id).preset_options(line, wanted)
        except ValueError as error:
            raise ApiError(400, "invalid", str(error)) from error
        title = title.strip() or f"cloud: {line.name}"
        name = slug(title)
        for loaded in self.kernel.settings.records("preset"):
            if name in (loaded.id, slug(str(loaded.record.model_dump().get("title") or ""))):
                raise ApiError(409, "exists", f"there is a preset {loaded.id} already: give another title")
        day = self.kernel.clock.now().date().isoformat()
        notes = f"Added on {day}; ${line.price_in:.2f} in, ${line.price_out:.2f} out per million tokens then."
        values = {"title": title, "endpoint": id, "model": line.id, "options": options, "notes": notes}
        try:
            self.kernel.settings.write("preset", name, values, base=None, actor=actor)
        except SettingsError as error:
            raise ApiError(400, "invalid", str(error)) from error
        return self.runtime.preset(name)

    def _remembered(self) -> dict[str, dict[str, Any]]:
        try:
            found = json.loads(self._known_file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return found if isinstance(found, dict) else {}

    def _remember(self, id: str, lines: list[ModelLine]) -> None:
        known = self._remembered()
        mine = known.setdefault(id, {})
        for line in lines:
            mine[line.id] = dataclasses.asdict(line)
        known.setdefault(READ_AT, {})[id] = to_text(self.kernel.clock.now())
        path = self._known_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(f".{path.name}.part")
        partial.write_bytes((json.dumps(known, indent=1) + "\n").encode("utf-8"))
        os.replace(partial, path)

    def _known_file(self) -> Path:
        return self.kernel.home.state / KNOWN

    def ask(
        self, id: str, key: str, method: str, path: str, *, params: Mapping[str, str] | None = None,
        body: Any = None, seconds: float = ASK_SECONDS,
    ) -> httpx2.Response:  # fmt: skip
        """One of the service's own requests to a provider, with its key: its answer, or 502 `cloud_unreachable`
        when it does not answer."""
        record = self.record(id)
        adapter = ENDPOINTS.get(record.adapter)()
        try:
            return httpx2.request(
                method, record.url + path, params=dict(params or {}), json=body, headers=adapter.headers(key, ""),
                timeout=seconds,
            )  # fmt: skip
        except httpx2.HTTPError as error:
            said = str(error) or type(error).__name__
            raise ApiError(
                502,
                "cloud_unreachable",
                f"{adapter.LABEL} did not answer: {said}; check this computer's network",
            ) from error

    def refused(self, id: str, answer: httpx2.Response) -> ApiError:
        """A provider's refusal, as the API's error: a refused key is 400 `key_refused`, anything else 502."""
        adapter = self.adapter(id)
        refusal = adapter.refusal(answer.status_code, answer.content)
        if refusal.code == "key_refused":
            message = f"{refusal.advice} ({adapter.LABEL} said: {refusal.said})" if refusal.said else refusal.advice
            return ApiError(400, "key_refused", message)
        return ApiError(502, refusal.code, refusal.message or f"{adapter.LABEL} answered {answer.status_code}")

    def _read_account(self, id: str, key: str) -> Account:
        answer = self.ask(id, key, "GET", "/key")
        if answer.status_code != 200:
            raise self.refused(id, answer)
        try:
            return self.adapter(id).account(answer.json())
        except (ValueError, TypeError, AttributeError) as error:
            raise ApiError(502, "refused", f"the provider's answer about the key could not be read: {error}") from error

    def _write(self, id: str, values: Mapping[str, Any], actor: Actor, *, base: str | None) -> None:
        try:
            self.kernel.settings.write(KIND, id, dict(values), base=base, actor=actor)
        except SettingsError as error:
            raise ApiError(400, "invalid", str(error)) from error

    def _now(self) -> float:
        """The kernel's clock, in seconds (a test's clock moves the account's minute on)."""
        return self.kernel.clock.now().timestamp()
