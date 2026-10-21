"""A provider's check and a cloud preset's test (design 0016 §6, design 0015 §11, decision 0076): operations of a few
seconds that send the provider only Clank's own made-up requests.

- **The check** (`runtime.endpoint_check`, `clank endpoint check`, `c` on the Providers page): its agreement, its key
  (asked: `GET /key`), its account, its list of models, the model (`model`, else the first of its presets'), one short
  reply ("Reply with OK.", 16 tokens at most), a call to a made-up tool, a little thinking, its data policy and Clank's
  cost limits; each item `ok`, `fail`, `warn` or `unknown`, with why. A refused key fails the key and leaves the rest
  unknown. The result is the event `runtime.endpoint_checked` and the provider's last check.
- **The test** (`runtime.endpoint_test`, Add a model's last screen): one short request to a cloud preset's model with
  its options; its answer, time and cost, or what failed by its code (`key_refused`, `no_credits`, `no_model`,
  `data_policy`, `cloud_unreachable`, `refused`) and what to do.

What each costs is kept with it (`endpoint_checks`), and the cost totals count it (design 0016 §12).
"""

import json
import time
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from clank.components.runtime import cloud
from clank.components.runtime.adapters import ENDPOINTS
from clank.components.runtime.adapters.endpoint import EndpointAdapter, ModelLine
from clank.components.runtime.cloud import CHAT, KEY, TINY_SECONDS, TINY_TOKENS, TINY_WORDS, money
from clank.components.runtime.kinds import Endpoint
from clank.kernel.api import ApiError
from clank.kernel.clock import from_text
from clank.kernel.events import EventType, Subject
from clank.kernel.operations import OperationContext, OperationType, StepSpec
from clank.kernel.settings import SettingsError

if TYPE_CHECKING:
    from clank.components.runtime.service import Runtime

TOOL_WORDS = "Look up the made-up word blue."
THINK_WORDS = "Think briefly, then reply with OK."
MADE_UP_TOOL = {
    "type": "function",
    "function": {
        "name": "made_up_lookup",
        "description": "Look up a made-up word.",
        "parameters": {"type": "object", "properties": {"word": {"type": "string"}}, "required": ["word"]},
    },
}
ITEMS = ("agreed", "key", "account", "models", "model", "answer", "tools", "thinking", "policy", "limits")
EVENT_TYPES = [
    EventType(
        "runtime.endpoint_checked",
        "A provider's check ended (design 0016 §6): each item passed, failed or warned, with why.",
        {"id": "The provider's record.", "ok": "Whether no item failed.", "items": "Each item: name, status, said."},
        owner="runtime",
    )
]
Items = list[dict[str, str]]


def operation_types(runtime: "Runtime") -> list[OperationType]:
    """The check and the test, each holding its provider while it asks."""
    checks = Checks(runtime)

    def lock(params: Mapping[str, Any]) -> list[str]:
        return [f"endpoint:{params.get('id', 'openrouter')}"]

    return [
        OperationType("runtime.endpoint_check", "Check a provider", (StepSpec("check"),), checks.check, locks=lock,
                      owner="runtime"),
        OperationType("runtime.endpoint_test", "Test a cloud preset", (StepSpec("test"),), checks.test, locks=lock,
                      owner="runtime"),
    ]  # fmt: skip


class Checks:
    """What the check and the test do."""

    def __init__(self, runtime: "Runtime") -> None:
        self.runtime = runtime

    async def check(self, context: OperationContext) -> dict[str, Any]:
        """The check, item by item; its result kept and announced."""
        id = str(context.params.get("id") or "openrouter")
        async with context.step("check"):
            items, usd = await context.run_blocking(self._check, id, str(context.params.get("model") or ""))
            for item in items:
                context.log(f"{item['status']:<7} {item['name']:<9} {item['said']}")
            ok = not any(item["status"] == "fail" for item in items)
            self.runtime.endpoints.keep_check(id, "check", ok, items, usd)
            self.runtime.kernel.events.record(
                "runtime.endpoint_checked",
                summary=f"the check of {id} {'passed' if ok else 'failed'}",
                actor=context.actor,
                subject=Subject(kind="endpoint", id=id),
                data={"id": id, "ok": ok, "items": items},
            )
        return {"ok": ok, "items": items}

    async def test(self, context: OperationContext) -> dict[str, Any]:
        """One short request to a cloud preset's model: its answer, time and cost, or what failed."""
        id = str(context.params.get("id") or "openrouter")
        async with context.step("test"):
            result, usd = await context.run_blocking(self._test, str(context.params["preset"]))
            context.log(result["said"])
            self.runtime.endpoints.keep_check(id, "test", bool(result["ok"]), [result], usd)
        return result

    def _test(self, name: str) -> tuple[dict[str, Any], float]:
        from clank.components.runtime.launching import preset_of

        preset_id, preset = preset_of(self.runtime, name)
        if not preset.cloud:
            raise ValueError(f"{preset.title or preset_id} is not a cloud preset: its check is clank preset check")
        try:
            prepared = cloud.prepare(self.runtime, preset_id, preset)
        except cloud.CloudError as error:
            return {"ok": False, "said": str(error), "code": _code(error.code)}, 0.0
        except ApiError as error:
            return {"ok": False, "said": str(error), "code": _code(error.code)}, 0.0
        endpoints, adapter, model = self.runtime.endpoints, prepared.adapter, prepared.model.id
        denied = prepared.record.options.get("data_collection", "deny") == "deny"
        try:
            key = endpoints.key(preset.endpoint, user="runtime", why=f"the test of {preset.title or preset_id}")
            sent, _ = adapter.translate(_tiny(), model, prepared.route["adds"])
            began = time.monotonic()
            answer = endpoints.ask(preset.endpoint, key, "POST", CHAT, body=sent, seconds=TINY_SECONDS)
        except ApiError as error:
            return {"ok": False, "said": str(error), "code": _code(error.code)}, 0.0
        seconds = round(time.monotonic() - began, 1)
        if answer.status_code != 200:
            refusal = adapter.refusal(answer.status_code, answer.content, model=model, denied=denied)
            return {"ok": False, "said": refusal.message, "code": _code(refusal.code)}, 0.0
        found = answer.json()
        text = _text(found)
        cost = adapter.cost(found.get("usage"), {}, prepared.route["prices"])
        estimate = "≈ " if cost.how == "estimate" else ""
        said = f"{text} in {seconds:.1f} s, {estimate}{money(cost.usd)}"
        return {"ok": True, "answer": text, "seconds": seconds, "cost_usd": cost.usd, "said": said}, cost.usd

    def _check(self, id: str, wanted: str) -> tuple[Items, float]:
        endpoints = self.runtime.endpoints
        record = endpoints.record(id)
        adapter = ENDPOINTS.get(record.adapter)()
        items: Items = []
        spent = [0.0]

        def add(name: str, status: str, said: str) -> None:
            items.append({"name": name, "status": status, "said": said})

        def rest(why: str) -> tuple[Items, float]:
            for name in ITEMS[len(items) :]:
                add(name, "unknown", why)
            return items, spent[0]

        if record.is_agreed:
            add("agreed", "ok", self._agreed(id, record.agreed))
        else:
            add("agreed", "fail", f"not agreed to: Add a model, or clank endpoint add {id}, asks you first")
        shown = endpoints.key_view(id)
        if not shown["set"]:
            add("key", "fail", f"no key is set: Providers and models, k; or clank endpoint key {id}")
            return rest("not asked: no key")
        try:
            key = endpoints.key(id, user="runtime", why=f"the check of {id}")
            asked = endpoints.ask(id, key, "GET", KEY)
        except ApiError as error:
            add("key", "fail", str(error))
            return rest(f"not asked: {adapter.LABEL} did not answer")
        if asked.status_code != 200:
            add("key", "fail", str(endpoints.refused(id, asked)))
            return rest(f"not asked: {adapter.LABEL} refused the key")
        account = adapter.account(asked.json())
        limit = (
            f"its limit ${account.limit_usd:.2f}, ${account.remaining_usd or 0.0:.2f} left"
            if account.limit_usd is not None
            else f"no limit of its own ({adapter.LABEL} advises one)"
        )
        add("key", "ok", f'set (ends …{shown["ends"]}), accepted: "{account.label}"; {limit}')
        used = f"used today ${account.used_today_usd:.2f}, this month ${account.used_month_usd:.2f}"
        used += f" ({adapter.LABEL}'s count, UTC days)" + ("; a free-tier key" if account.free_tier else "")
        budget = account.budget
        if budget is not None and budget["remaining_usd"] <= 0:
            add("account", "warn", f"{used}; a budget ({budget['scope']}) refuses until {budget['resets_at']}")
        else:
            add("account", "ok", used)
        try:
            lines, read_at = endpoints.lines(id, sort="most-popular", fresh=True)
        except ApiError as error:
            add("models", "fail", str(error))
            return rest("not asked: no list of models")
        moment = from_text(read_at).astimezone().strftime("%H:%M")
        add("models", "ok", f"{len(lines)} take tool calls (listed {moment})")
        name = wanted or next((self._model_of(preset) for preset in endpoints.presets(id)), "")
        if not name:
            add("model", "unknown", "no model named: give one (--model), or add a cloud preset")
            return self._closing(id, record, items, spent, None)
        try:
            line = endpoints.model(id, name)
        except ApiError as error:
            add("model", "fail", adapter.refusal(404, b"", model=name).advice if error.code == "unknown_model"
                else str(error))  # fmt: skip
            return self._closing(id, record, items, spent, None)
        output = f"{line.output:,}" if line.output else "not said"
        add("model", "ok", f"{line.id}: window {line.window:,}, output {output}, ${line.price_in:.2f} in, "
                           f"${line.price_out:.2f} out per million")  # fmt: skip
        return self._closing(id, record, items, spent, (key, line))

    def _closing(
        self, id: str, record: Endpoint, items: Items, spent: list[float], asked: tuple[str, ModelLine] | None
    ) -> tuple[Items, float]:
        """The answer, tools, thinking, policy and limits items."""
        adapter = ENDPOINTS.get(record.adapter)()
        denied = record.options.get("data_collection", "deny") == "deny"
        adds = adapter.adds(record.options, "default")

        def add(name: str, status: str, said: str) -> None:
            items.append({"name": name, "status": status, "said": said})

        answered = False
        if asked is None:
            for name in ("answer", "tools", "thinking"):
                add(name, "unknown", "not asked: no model")
        else:
            key, line = asked
            answer, seconds, cost, refusal = self._ask(id, key, adapter, line, _tiny(), adds, denied)
            spent[0] += cost
            if refusal:
                add("answer", "fail", refusal)
                add("tools", "unknown", "not asked: the short reply failed")
                add("thinking", "unknown", "not asked: the short reply failed")
            else:
                answered = True
                add("answer", "ok", f"{answer} in {seconds:.1f} s, cost {money(cost)}")
                body = {"messages": [{"role": "user", "content": TOOL_WORDS}], "tools": [MADE_UP_TOOL],
                        "tool_choice": "required", "max_tokens": 64, "stream": True}  # fmt: skip
                events, cost, refusal = self._stream(id, key, adapter, line, body, adds, denied)
                spent[0] += cost
                called = any(_delta(event).get("tool_calls") for event in events)
                if refusal:
                    add("tools", "fail", refusal)
                elif called:
                    add("tools", "ok", "a call to the made-up tool came back as a tool call")
                else:
                    add("tools", "fail", "it answered without calling the made-up tool")
                if not line.thinking:
                    add("thinking", "warn", f"{line.id} does not think")
                else:
                    effort = "low" if not line.efforts or "low" in line.efforts else line.efforts[0]
                    body = {"messages": [{"role": "user", "content": THINK_WORDS}], "max_tokens": 64,
                            "stream": True, "reasoning": {"effort": effort}}  # fmt: skip
                    events, cost, refusal = self._stream(id, key, adapter, line, body, adds, denied)
                    spent[0] += cost
                    if refusal:
                        add("thinking", "fail", refusal)
                    elif any(_delta(event).get("reasoning") for event in events):
                        add("thinking", "ok", "streamed as reasoning")
                    else:
                        add("thinking", "warn", "no thinking came back as reasoning")
        policy = str(record.options.get("data_collection", "deny"))
        if policy != "deny":
            add("policy", "warn", f"data_collection {policy}: any of the model's providers may keep what it is sent "
                                  "(o on the Providers page)")  # fmt: skip
        elif answered:
            add("policy", "ok", f"answered with data_collection {policy}")
        else:
            add("policy", "unknown", f"data_collection {policy}; no answer showed whether a provider serves it so")
        add("limits", *self._limits())
        return items, spent[0]

    def _ask(
        self, id: str, key: str, adapter: EndpointAdapter, line: ModelLine, body: dict[str, Any],
        adds: Mapping[str, Any], denied: bool,
    ) -> tuple[str, float, float, str]:  # fmt: skip
        """A whole answer: its text, its time, its cost, and the refusal's words when there is one."""
        sent, _ = adapter.translate(body, line.id, adds)
        began = time.monotonic()
        try:
            answer = self.runtime.endpoints.ask(id, key, "POST", CHAT, body=sent, seconds=TINY_SECONDS)
        except ApiError as error:
            return "", 0.0, 0.0, str(error)
        seconds = time.monotonic() - began
        if answer.status_code != 200:
            refusal = adapter.refusal(answer.status_code, answer.content, model=line.id, denied=denied)
            return "", seconds, 0.0, refusal.message
        found = answer.json()
        return _text(found), seconds, adapter.cost(found.get("usage"), {}, line.prices()).usd, ""

    def _stream(
        self, id: str, key: str, adapter: EndpointAdapter, line: ModelLine, body: dict[str, Any],
        adds: Mapping[str, Any], denied: bool,
    ) -> tuple[list[dict[str, Any]], float, str]:  # fmt: skip
        """A streamed answer, read whole: its events, its cost (its last usage), and the refusal's words."""
        sent, _ = adapter.translate(body, line.id, adds)
        try:
            answer = self.runtime.endpoints.ask(id, key, "POST", CHAT, body=sent, seconds=TINY_SECONDS)
        except ApiError as error:
            return [], 0.0, str(error)
        if answer.status_code != 200:
            refusal = adapter.refusal(answer.status_code, answer.content, model=line.id, denied=denied)
            return [], 0.0, refusal.message
        events = _events(answer.text)
        usage = next((event["usage"] for event in reversed(events) if isinstance(event.get("usage"), dict)), None)
        return events, adapter.cost(usage, {}, line.prices()).usd if usage else 0.0, ""

    def _agreed(self, id: str, agreed: str) -> str:
        """When the owner agreed (UTC), and by whom when the history says."""
        said = from_text(agreed).strftime("%Y-%m-%d %H:%M") + " UTC"
        for event in self.runtime.kernel.events.latest(20, types=["runtime.endpoint_added"]):
            if event.data.get("id") == id:
                return f"{said}, by {event.actor.describe()}"
        return said

    def _model_of(self, preset: str) -> str:
        try:
            return str(self.runtime.preset(preset)["model"])
        except Exception:  # noqa: BLE001: a preset gone since is no model to check
            return ""

    def _limits(self) -> tuple[str, str]:
        """Clank's own cost limits (the gateway's `config/cost.json`), as they are now."""
        try:
            values = self.runtime.kernel.settings.get("cost", "cost").record.model_dump()
        except SettingsError:
            values = {}
        day, month = values.get("day_usd"), values.get("month_usd")
        if day is None and month is None:
            return "warn", "no daily or monthly limit in Clank (L on the Providers page)"
        shown = [
            f"today's ${day:.2f}" if day is not None else "",
            f"this month's ${month:.2f}" if month is not None else "",
        ]
        return "ok", "limits: " + ", ".join(each for each in shown if each)


def _tiny() -> dict[str, Any]:
    return {"messages": [{"role": "user", "content": TINY_WORDS}], "max_tokens": TINY_TOKENS, "stream": False}


def _text(found: Any) -> str:
    try:
        return str(found["choices"][0]["message"].get("content") or "").strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        return ""


def _events(text: str) -> list[dict[str, Any]]:
    found = []
    for line in text.splitlines():
        if line.startswith("data:") and line[5:].strip() not in ("", "[DONE]"):
            try:
                event = json.loads(line[5:])
            except ValueError:
                continue
            if isinstance(event, dict):
                found.append(event)
    return found


def _delta(event: Mapping[str, Any]) -> dict[str, Any]:
    choices = event.get("choices") or []
    if choices and isinstance(choices[0], dict) and isinstance(choices[0].get("delta"), dict):
        found: dict[str, Any] = choices[0]["delta"]
        return found
    return {}


def _code(code: str) -> str:
    """A refusal's code as the test's result names it."""
    known = ("key_refused", "no_credits", "no_model", "data_policy", "cloud_unreachable")
    return code if code in known else "refused"
