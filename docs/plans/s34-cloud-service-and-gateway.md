# Cloud models, part 1: the service and the gateway: implementation plan

> Written 2026-10-20 for builders who have not seen the conversation that led to it. Read
> [design 0016](../design/0016-cloud-models.md) first (it is short on purpose about code), then this plan. Its partner,
> [plan s35](s35-cloud-console-cli-phone-vscode.md) (the console, the commands, the phone, VS Code), is built at the
> same time against **The interface** below: change it only in both plans, in one commit.

**Goal:** design 0016 §4-§12, the service's and the gateway's part: an OpenRouter provider record and its key; the
`endpoint` kind of adapter and its first adapter, `openrouter`; cloud presets, loaded into the main slot with no local
engine; the gateway forwarding to OpenRouter with the key, streaming, tool calls, thinking, usage and exact cost;
workspace keys, bounds and the once-per-workspace question; local-only content kept from the cloud; cost kept per
request, session, workspace and flow, and the optional limits that pause the cloud; the events.

**Architecture:** The runtime owns the provider record (kind `endpoint`, `config/endpoints/<id>.json`), its key (the
kernel's secrets, scope `endpoint/<id>`, name `key`), the adapter (`clank/components/runtime/adapters/openrouter.py`),
cloud presets, and what loading one means (`slots.py`): plan, start (nothing starts), health (`GET /key`, then one tiny
request), measure. A launch keeps its route (migration `runtime 0003`). The gateway component's service hands the key to
the gateway process behind the local token (decision 0106), keeps each workspace's gateway key and bound and the cloud
costs in its own tables (its first migration), and adds the workspaces, the local-only tool names and the spending to
the routes the gateway follows. The gateway process forwards a cloud route's requests to `<base URL>/chat/completions`
with its own HTTP client, checks the workspace's bound and local-only content first, holds at the spending limit,
never sends a cloud request again, and spools each request's cost. The workspaces component owns each workspace's
bound and asks its question; the agents component writes OpenCode's configuration with the workspace's key and without
local-only servers.

**Tech stack:** Python 3.12, AnyIO, FastAPI, httpx2, click, pytest. No new dependency. The fake OpenRouter
(`tests/fakes/openrouter.py`, task 2) stands in for the network in every test.

**Spec:** [design 0016](../design/0016-cloud-models.md) §1-§13 and §18; decisions
[0102](../decisions/0102-the-first-cloud-provider-is-openrouter.md) to
[0112](../decisions/0112-a-workspace-is-asked-before-its-agent-starts-and-at-the-gateway.md); what it builds of
[design 0015](../design/0015-endpoints.md) (§2, §3, §4, §6, §8, §9, §10, §11, §14), as design 0016 §1's table says;
decisions [0055](../decisions/0055-pause-is-the-gateway-holding-the-next-request.md) (holds),
[0074](../decisions/0074-thinking-streamed-as-reasoning-is-read-too.md) (thinking as `reasoning`),
[0084](../decisions/0084-the-gateways-holds-are-set-by-the-service-behind-its-token.md) (routes behind the local
token), [0089](../decisions/0089-opencode-is-told-the-window-less-a-margin.md),
[0090](../decisions/0090-a-full-context-is-answered-as-an-overflow-opencode-compacts-on.md) and
[0096](../decisions/0096-the-census-keeps-no-prompt-text-when-records-are-off.md).

## Global Constraints

- **No real network in any test.** Every test reaches OpenRouter through `tests/fakes/openrouter.py`; the provider's
  URL is the fake's (task 1's test switch). The real checks (task 23) run only under their own marker, never in CI.
- **No key in the repository.** Tests use the made-up key `made-up-openrouter-key` (never one that starts with `sk-`:
  the repository's secrets check would refuse it). Nothing writes a key to a record, an event, an operation's log, a
  route's answer, a launch, the gateway's records or a process's log; a test for each place (task 10).
- **No new dependency.** Tests first, each test file's docstring naming the design sections it verifies ("Design 0016
  §8"), test names sentences. Each task is one commit, its generated files regenerated with `uv run python -m
  tools.check --fix`. The owner is the sole author of every commit: no trailer.
- **Nothing runs a real model, OpenCode, Docker or the GPU.** Engines are the fake engine (`tests/fakes/engine.py`),
  sessions the fake bridge, as the earlier plans do.
- `clank/components/gateway/server.py` is changed by tasks 11, 12, 16, 17, 18 and 20: never two of them at once.

## The interface (shared with plan s35)

Every route is under the service's `/api/v1`, behind the local token, as every route is (design 0002 §2.7). Errors
have the API's one shape (`{"error": {"code", "message", …}}`, design 0002 §2.14). Times are Clank's (`2026-10-21T09:12:04.120Z`).
Money is US dollars as JSON numbers. Plan s35 builds against these exact shapes; its task 1 serves them from a fake.

### The provider (the runtime component)

`GET /runtime/endpoints` → a list of **EndpointView**; `GET /runtime/endpoints/{id}` → one (404 `not_found`).

```json
{
  "id": "openrouter",
  "title": "OpenRouter",
  "adapter": "openrouter",
  "url": "https://openrouter.ai/api/v1",
  "reach": "cloud",
  "options": { "data_collection": "deny", "zdr": false },
  "agreed": "2026-10-21T09:12:04.120Z",
  "key": { "set": true, "ends": "a1b2", "set_at": "2026-10-21T09:13:00.000Z" },
  "presets": ["cloud-example-coder"],
  "running": { "slot": "main", "preset": "cloud-example-coder" },
  "check": { "time": "2026-10-21T09:15:00.000Z", "ok": true, "items": [] },
  "source": "user",
  "file": "<CLANK_HOME>/config/endpoints/openrouter.json"
}
```

`key` is `{"set": false, "ends": "", "set_at": ""}` without a key; `running` and `check` may be `null`; `agreed` is
`""` when not agreed. `check.items` are **CheckItem**s: `{"name": "key", "status": "ok" | "fail" | "warn" |
"unknown", "said": "set (ends …a1b2), accepted: \"my laptop key\"; …"}`.

`POST /runtime/endpoints` body `{"id": "openrouter", "adapter": "openrouter", "agree": true, "local_mcp": ["lit"]}`
→ 201 EndpointView. Writes the record from the adapter's template with `agreed` now, and marks every MCP server named
in `local_mcp` local only (the agreement screen's marks; omitted: every server already added, design 0016 §10). 400
`agreement_needed` without `"agree": true`; 409 `exists`.

`PATCH /runtime/endpoints/{id}` body `{"options": {"data_collection": "allow"}}` (or `"agreed": ""` to withdraw) →
EndpointView.

`DELETE /runtime/endpoints/{id}` → `{"removed": "openrouter"}`; removes the record and its key; 409 `in_use` naming
the slot and the presets.

`PUT /runtime/endpoints/{id}/key` body `{"key": "<the key>"}` → `{"key": {"set": true, "ends": "a1b2", "set_at":
"…"}, "account": AccountView}`. The service asks OpenRouter `GET /key` with it first and keeps it only on 200. 400
`key_refused` (OpenRouter's 401: `"message": "OpenRouter refused the key: …"`), 502 `cloud_unreachable` (nothing kept).
The key is never answered back. `DELETE /runtime/endpoints/{id}/key` → `{"key": {"set": false, "ends": "", "set_at":
""}}`.

`GET /runtime/endpoints/{id}/account` → **AccountView** (read at most once a minute, then from memory; `?fresh=true`
asks again):

```json
{
  "label": "my laptop key",
  "limit_usd": 20.0,
  "remaining_usd": 18.71,
  "limit_reset": null,
  "used_today_usd": 0.12,
  "used_week_usd": 0.5,
  "used_month_usd": 1.29,
  "free_tier": false,
  "budget": null,
  "expires_at": null,
  "read_at": "2026-10-21T09:14:00.000Z",
  "days": "UTC"
}
```

`budget` is `null` or `{"scope": "api_key", "remaining_usd": 0.0, "resets_at": "…"}` (the budget that refuses first).
400 `key_not_set`, 400 `key_refused`, 502 `cloud_unreachable`.

`GET /runtime/endpoints/{id}/models?search=&sort=most-popular&free=false&all=false&fresh=false` → the models that take
tool calls (`all=true`: every model; `free=true`: only free ones), read with the key, kept for an hour:

```json
{
  "models": [
    {
      "id": "example-vendor/example-coder",
      "name": "Example Coder",
      "description": "A made-up model for coding.",
      "window": 262144,
      "output": 32768,
      "price": { "in": 0.3, "out": 1.2, "cached_in": 0.03, "request": 0.0 },
      "thinking": true,
      "efforts": ["low", "medium", "high"],
      "images": false,
      "tools": true,
      "free": false,
      "limits": "",
      "retires": null
    }
  ],
  "count": 1,
  "sort": "most-popular",
  "read_at": "2026-10-21T09:14:00.000Z"
}
```

Prices are per million tokens. `sort` is one of `most-popular` (OpenRouter's, within `category=programming`),
`price` (cheapest in first), `context` (largest window first), `newest`. `limits` says a free model's ("20 a minute,
50 a day; 1,000 a day once 10 credits were bought"). 400 `key_not_set`, 502 `cloud_unreachable`.

`POST /runtime/endpoints/{id}/presets` body `{"model": "example-vendor/example-coder", "title": "cloud: Example
Coder", "context": 262144, "max_output": 16384, "reasoning": "default"}` (all but `model` optional; defaults from the
model) → 201 **PresetView**: the preset as `GET /runtime/presets/{name}` gives it today, plus `"provider": "cloud
openrouter"`, `"endpoint": "openrouter"`, `"price": {"in": 0.3, "out": 1.2, "cached_in": 0.03}`. 400 `unknown_model`,
400 `no_tools` (the model does not take tool calls), 409 `exists`.

`POST /runtime/endpoints/{id}/check` body `{"model": "example-vendor/example-coder"}` (optional) → the operation it
starts (`runtime.endpoint_check`), as `POST /runtime/slots/{slot}/load` returns one; its result is `{"ok": true,
"items": [CheckItem, …]}`; the event `runtime.endpoint_checked` carries the same.

`POST /runtime/endpoints/{id}/test` body `{"preset": "cloud-example-coder"}` → the operation (`runtime.endpoint_test`);
its result `{"ok": true, "answer": "OK", "seconds": 0.9, "cost_usd": 0.00002, "said": "OK in 0.9 s, $0.00002"}`, or
`{"ok": false, "said": "<what failed and what to do>", "code": "key_refused" | "no_credits" | "no_model" |
"data_policy" | "cloud_unreachable" | "refused"}`.

`GET /runtime/usable` →

```json
{
  "usable": false,
  "why": "no model runs in the main slot, and no preset for it can load here: add one (Add a model)",
  "main": { "status": "stopped", "preset": null, "title": "", "provider": "" },
  "candidates": []
}
```

`candidates` lists the presets for the main slot that can load now, each `{"preset", "title", "provider"}`.

Every preset view (`GET /runtime/presets`, `/runtime/presets/{name}`) gains `provider` (`kvmem-llamacpp v0.16.0-rc1`
or `cloud openrouter`), `endpoint` (`""` for an engine preset) and, for a cloud preset, `price`.

### Workspaces (the workspaces component)

Each workspace view (`GET /workspaces`, `GET /workspaces/folder`'s `workspace`) gains `"models": "this-machine" |
"cloud"`, `"cloud_answered": ""` (or when the owner answered *keep local*), and `"cloud_question": null` (or the open
question's id). *Built 2026-10-21:* `GET /workspaces/folder`'s `workspace` is the workspace's name, so its answer
carries the three at its top level, beside `workspace` (each `null` without a workspace), as plan s35's clients read
them.

`POST /workspaces/{name}/cloud` body `{"allow": true}` (or `false`: keep local) → the workspace view; recorded with who
did it.

`POST /workspaces/{name}/cloud/ask` → `{"needed": true, "allowed": false, "question": "q-1a2b", "why": "…"}`. Called
by a client before it starts the workspace's agent. `needed` is false (and `question` null) when the main slot does not
run a cloud model, or the workspace is already allowed (`allowed: true`) or kept local (`allowed: false`, `why` says
how to allow it). Otherwise it asks the question (or returns the one open) and the client waits for its answer (the
question's event, or `GET /questions/{id}`). *Added 2026-10-21:* every answer carries `"start": true | false`, whether
the client may start the agent now (the main slot runs no cloud model, or the workspace may use it).

The question (`kind: "choice"`, asked by `clank (workspaces)`): title "Let <workspace>'s agent use the cloud model
<title>?"; options `allow` (key `y`, "its requests go to OpenRouter from now on"), `local` (key `n`, "it stays on this
machine; not asked again"); default `local`, expires in 30 minutes (then refused this time only).

### MCP servers (the tools component)

Each MCP server view (`GET /mcp/servers`, `/mcp/servers/{name}`) gains `"local_only": true | false`. `PUT
/mcp/servers/{name}/local` body `{"local_only": true}` → the view. `POST /mcp/servers` takes `"local_only"` too (s35's
form asks it once a provider is agreed); left out, a server is local only while a provider is agreed (*review fix 4*).

### Cost (the gateway component)

`GET /gateway/cost` → **CostView**:

```json
{
  "today": { "usd": 0.42, "requests": 31, "estimated_usd": 0.0 },
  "month": { "usd": 3.1, "requests": 402, "estimated_usd": 0.03 },
  "limits": { "day_usd": 5.0, "month_usd": null, "warn_at": 0.8 },
  "paused": null,
  "warned": null,
  "days": "local"
}
```

`paused` is `null` or `{"by": "day" | "month", "since": "…", "spent_usd": 5.02, "limit_usd": 5.0, "question":
"q-3c4d", "held": 2}`; `warned` is `null` or `{"by": "day", "spent_usd": 4.02, "limit_usd": 5.0}`.
`estimated_usd` is the part of `usd` that is still an estimate.

*Added 2026-10-21 for the phone app (the owner's instruction; every field above stays as it is):* the view also says
`"currency": "USD"`, `"zone"` (this computer's offset, `"UTC-04:00"`), `"revision"` (the newest cost row it counts, a
number that only grows) and `"said"` ("cloud $0.42 today · $3.10 this month"); `today` and `month` each add `"from"`
and `"until"` (the period's bounds in this computer's days, as Clank's UTC times), `"local"` (`"2026-10-21"`,
`"2026-10"`) and `"said"` ("$0.42 today", "≈ $3.10 this month" while part is an estimate); `limits`, `paused` and
`warned` each add `"said"` ("today's limit $5.00; no monthly limit", "cloud paused: today's limit of $5.00 reached
($5.02 spent)", "cloud: $4.02 of today's $5.00"). A client shows these; none recomputes them.

*Added 2026-10-21, as plan s35's clients read it:* `GET /gateway/cost?workspace=notes` gives the same view with
`"workspace": {"name": "notes", "today": {...}, "month": {...}}`, the workspace's own requests in each period with the
same fields as the view's `today` and `month` (the runtime's own requests are no workspace's); the view's `today`,
`month` and `limits` stay the whole cloud's, since the limits are. Without it, `"workspace": null`.

`GET /gateway/cost/sessions?workspace=&limit=50&after=` → `[{"session": "ses_…", "workspace": "notes", "usd": 0.84,
"requests": 142, "estimated_usd": 0.0, "first": "…", "last": "…"}]`, each with its subagents' requests counted in.

`GET /gateway/cost/requests?session=&workspace=&since=&limit=100&after=` → `[{"id": "r-1a2b3c4d", "time": "…",
"session": "ses_…", "workspace": "notes", "preset": "cloud-example-coder", "model": "example-vendor/example-coder",
"tokens": {"in": 41234, "cached": 38000, "out": 512, "thinking": 300}, "usd": 0.0123, "how": "usage" | "generation" |
"estimate"}]`.

*Added 2026-10-21 for the phone app:* each row of both lists adds `"rev"` (the newest cost row it counts) and `"said"`
("$0.84 · 142 requests", "$0.0123", "≈ $0.03"); `after=<rev>` gives only the rows changed since (a session's whole
row, when any of its requests is newer); each answer's header `X-Clank-Revision` is the newest `rev` there is, so a
client asks again with it.

`PUT /gateway/cost/limits` body `{"day_usd": 5.0, "month_usd": null}` (either may be left out; `null` removes it) →
CostView. Writes `config/cost.json` (kind `cost`), recorded with who did it.

Each flow's view (`GET /flows/{id}`) gains `"cost": {"usd": 1.84, "estimated_usd": 0.0, "requests": 310, "boxes":
{"<box id>": {"usd": 0.92, "requests": 140}}}` (`null` when none of its sessions used the cloud). *Added 2026-10-21:*
the cost and each box's add `"said"` ("$1.84 · 310 requests").

The **limit question** (`kind: "choice"`, asked by `clank (gateway)`): title "Cloud spending reached today's limit of
$5.00 ($5.02 spent): raise it?" (or "this month's"); options `double` (key `y`, "raise today's limit to $10.00"),
`raise` (key `r`, an amount in words: the answer's `text`, "raise it to the amount you give"), `keep` (key `n`, "keep
the cloud paused until the day ends"); default `keep`, expires when the day (or month) ends. *Added 2026-10-21:* its
`raise` option declares the number it takes (decision 0114): `"asks": {"kind": "number", "unit": "USD", "min": 5.03,
"max": 100000, "step": 0.01}` (the least a cent above what was spent, so a raise always lets the cloud go on; the
shape plan s35's clients read); an answer out of its bounds or off its step is refused by the kernel, saying them; a
change of the limit that still leaves the spending at it asks again, with the new numbers; its urgency is `high`. The workspace's question's urgency is `high` too.

### Events (new types; `docs/EVENTS.md` lists them)

| Type | Data | When |
| --- | --- | --- |
| `runtime.endpoint_added` | `id`, `adapter`, `local_mcp` | A provider record written (`local_mcp`: the MCP servers the agreement marked local, `null` for every one; the tools component marks them) |
| `runtime.endpoint_changed` | `id`, `fields` | Its options or agreement changed |
| `runtime.endpoint_removed` | `id` | Removed, with its key |
| `runtime.endpoint_checked` | `id`, `ok`, `items` | A check ended |
| `gateway.cost` | `today_usd`, `month_usd`, `estimated_usd` | The totals changed (at most every 5 s) |
| `gateway.limit_warned` | `by`, `spent_usd`, `limit_usd` | 80% of a limit |
| `gateway.limit_reached` | `by`, `spent_usd`, `limit_usd`, `question` | A limit reached: the cloud paused |
| `gateway.limit_raised` | `by`, `limit_usd`, `who` | A limit raised (or the period ended): the cloud goes on |
| `gateway.cloud_wanted` | `workspace`, `session` | The gateway holds a request of a workspace not yet answered |
| `gateway.cloud_refused` | `workspace`, `session`, `code`, `status` | A cloud request refused: by Clank (`model_send_denied`, `local_only`, `service_silent`) or by the provider (`key_refused` 401, `no_credits` 402, `refused` 403, `no_model` 404, `rate_limited` 429, `data_policy` 503); at most one a minute per workspace and code |
| `workspaces.cloud_answered` | `workspace`, `models`, `who` | A workspace allowed the cloud, or kept local |

*Added 2026-10-21 for the phone app:* every event carries `attention` (decision 0113); `gateway.limit_warned`,
`gateway.limit_reached`, `gateway.cloud_refused` and the kernel's `question.asked` need the owner. Every event's
`summary` is a short title in Clank's own words (a provider, a model, a workspace, a flow, a box, an amount), never
prompt or file text, so a live stream or a push notification carries it as it is.

The key's own events stay the kernel's (`secret.set`, `secret.used`, `secret.removed`).

### The gateway process's own routes (port 18210, 127.0.0.1; only the service calls them)

Each takes `Authorization: Bearer <the local token>` (as `/holds` does, decision 0084): 401 otherwise, 503 when the
gateway was given no token.

- `PUT /keys/{endpoint}` body `{"key": "…", "launch": 12, "set": "<when it was set>"}` → `{"endpoint", "ends",
  "launch", "set"}`; `DELETE /keys/{endpoint}` → `{"forgotten": "openrouter"}`; `GET /keys` → `{"keys": [{"endpoint",
  "ends", "launch", "set"}]}`. Never a key's value.
- `GET /spend?after=<n>` → `{"run": "<this gateway's run id>", "entries": [SpoolEntry, …], "last": <n>}`; the entries
  up to `after` are forgotten. A **SpoolEntry**: `{"seq": 7, "time", "id": "r-…", "session", "parent", "workspace",
  "preset", "model", "generation": "gen-…", "tokens": {"in", "cached", "out", "thinking"}, "usd": 0.0123, "how":
  "usage" | "estimate"}`. *Added 2026-10-21:* each entry also says its `endpoint`, its `status` and its `code` (a refusal's,
  at no cost), and the answer how many cloud requests are `held` at a spending limit now.
- `/activity`, `/activity/live` and `/completion` take the local token from task 16 on (design 0015 §10).
- The gateway calls the service's `POST /api/v1/gateway/cloud-wanted` body `{"workspace": "notes", "session":
  "ses_…"}` → `{"question": "q-1a2b"}` (or `{"question": null, "allowed": true | false}` when already answered), as
  it calls `gateway/wanted` for the vision model today; the service records `gateway.cloud_wanted`, which the
  workspaces component acts on.

### What the routes the gateway follows gain (`GET /api/v1/gateway/routes`, every second)

A cloud slot's route (`Runtime.route`): `"provider": "endpoint"`, `"endpoint": "openrouter"`, `"adapter": "openrouter"`
(*added 2026-10-21*: the gateway's way to the endpoint adapter), `"base_url":
"https://openrouter.ai/api/v1"`, `"model_name": "example-vendor/example-coder"`, `"reach": "cloud"`, `"agreed": true`,
`"launch": 12`, `"read_timeout": 600`, `"adds": {"provider": {"data_collection": "deny"}}` (plus `"reasoning":
{"effort": "high"}` when the preset sets one), `"prices": {"in": 0.0000003, "out": 0.0000012, "cached_in": 3e-8}` (per
token), `"engine": null`, `"port": null`, with `context`, `output`, `images`, `facts` as for an engine. An engine's
route gains `"provider": "engine"`, `"reach": "this-machine"`.

At the top level: `"workspaces": {"<sha256 of the key, hex>": {"workspace": "notes", "models": "this-machine",
"answered": false, "question": null}}` (only the workspaces that have a key: *review fix 10*), `"local_only":
["clank_notion_", "lit_"]` (tool-name prefixes; `clank_notion_` always), `"local_only_given": true` (false until the
agents component gave the list: the gateway then sends nothing to the cloud, 503 `local_only_unknown`; *review fix 5*),
`"cost": {"day_usd": 0.42, "month_usd": 3.1, "taken": 7, "run": "<gateway run id>", "limit_day_usd": 5.0,
"limit_month_usd": null}`, `"fresh": "<when the service made this answer>"`.

### What plan s35's clients read that this plan leaves to s35's task 18 (2026-10-21)

Plan s35 built its clients against a fake of these routes. Built here to match it: the typed answer's shape
(`{"kind", "unit", "min", "max", "step"}`), the folder view's bound at its top level, `start` on `cloud/ask`,
`gpu.device: "cloud"`, `GET /gateway/cost?workspace=`. Left to s35's task 18, which wires s35's own modules of words
(`runtime/guide.py`, `gateway/costwords.py`, `workspaces/cloudwords.py`, `clank/money.py`) into these routes: `GET
/runtime/guide` and `/runtime/guide/local`; typed text in presets and limits (here JSON numbers: a wrong type, or a limit
not above 0, is 422 `invalid`; a preset's value out of its model's bounds 400 `invalid`); and the words fields: `said` on a cloud load's result,
`cloud_said` and `cloud_confirm` on the folder view, `held` and `held_said` on `/agents/servers` (here a server held back
from a cloud workspace has `given: false` and its `why`), `cost.said` on a session's head, `how_said` on the cost lists'
rows (here `how` and `said`), `said.policy` on a provider's view, `price_said` on cloud presets (here `price`, and a flow
box's `price_said`), `local_said` on MCP servers (here `local_only`).

## Tasks

### Task 1: The provider's record, and the `endpoint` kind of adapter

- [x] **Files:** `clank/components/runtime/kinds.py` (`Endpoint`: `title`, `adapter`, `url`, `auth`, `reach`,
  `options`, `agreed`, `timeout_seconds`, `notes`; its rules); create `clank/components/runtime/adapters/endpoint.py`
  (`EndpointAdapter`, `ENDPOINTS`, the kind's interface of design 0016 §6), `adapters/openrouter.py` (`URL`, `REACH`,
  `AUTH`, `provider_options`, `template(id)`); `runtime/component.py` (the kind, the adapter kind); the settings schema
  regenerated (`clank/schemas/`). The URL rule has one test switch (`OpenRouter.URL` replaced in a test by the fake's).
  *Built:* `ENDPOINTS` sits beside `ENGINES` in `adapters/__init__.py`; the rules are `runtime/endpoints.py`'s
  `record_problems`, a settings check; the adapter kind joins the component with its contract (task 2).
- [x] **Tests** (`tests/components/runtime/test_endpoints.py`, design 0016 §4, §6): the template reads back the record
  of §4; a `url` other than the adapter's, a `reach` other than `cloud`, or `auth` other than `bearer` is refused with
  the file, line and field; `options` outside the adapter's are refused; `agreed` empty reads as not agreed.

### Task 2: The fake OpenRouter, and the contract over HTTP recordings

- [x] **Files:** create `tests/fakes/openrouter.py` (a FastAPI app served on a free port in a thread, as the console's
  tests serve the service: `/api/v1/key`, `/api/v1/models`, `/api/v1/chat/completions` whole and streamed,
  `/api/v1/generation`; its modes: the key it takes, refuse the key (401), no credits (402), a budget (403), no model
  (404), 429 with `Retry-After`, no provider (503), comment lines, thinking as `reasoning`, a tool call, usage with
  `cost`, a mid-stream error, a stream cut before its usage, silence; it keeps what it was sent);
  `tests/fixtures/openrouter/documented/http.json` (the documented shapes of design 0016 §3, its `source` saying so);
  `tests/fixtures/README.md` (what `http.json` is); `tests/test_architecture.py` (an endpoint adapter's recordings are
  `http.json`); create `tests/contract/test_endpoint.py`.
- [x] **Tests:** the contract test runs over every `http.json` of every endpoint adapter: the adapter reads each
  recorded answer (models, key, a whole answer, a stream, each refusal) without an error; the fake answers each request
  of the recording as recorded. *Built:* the fake plays a recording (`documented` by default), each chat answered by
  the exchange its test names (`play`); the adapter kind joined the runtime here, with its contract.

### Task 3: What the adapter reads and writes

- [x] **Files:** `adapters/openrouter.py` (`account`, `models`, `options`, `translate`, `headers`, `refusal`,
  `says_full` (none declared yet), `cost`, `capabilities`). *Built* before task 2, whose contract reads recordings
  with it; `options` is `preset_options` (and `option_problems`), and `adds`, `models_query` and `generation_cost` join
  the kind's interface.
- [x] **Tests** (`tests/components/runtime/test_openrouter.py`, design 0016 §3, §6, §8): `models` keeps only tool
  models unless asked, takes the smaller window of `context_length` and `top_provider.context_length`, turns string
  prices per token into numbers per million, marks free models and their limits; `account` reads `GET /key`'s fields
  (null limits as none); `translate` puts the listed id in `model`, adds `provider.data_collection` unless the tool sent
  a `provider`, adds `reasoning.effort` unless `default` or the tool sent one, and changes nothing else (a test over a
  request OpenCode sends: tools, `stream_options`, `max_tokens`, messages with `reasoning_content`); `headers` gives the
  bearer key and `x-session-id`; `refusal` gives design 0016 §8's words for 401, 402, 403, 404, 413, 429, 503 (with and
  without `deny`) and says which OpenCode must not retry; `cost` reads `usage.cost`, else estimates from tokens and
  prices, saying how.

### Task 4: Adding the provider, and its key

- [x] **Files:** `clank/components/runtime/endpoints.py` (create: `Endpoints` over the kernel's settings and secrets:
  `add`, `change`, `remove`, `set_key`, `remove_key`, `view`, `account` with its one-minute memory); `runtime/api.py`
  (the provider's routes of **The interface**); `runtime/service.py` (`Runtime.endpoints`); the events
  `runtime.endpoint_added`, `_changed`, `_removed`; `clank/components/tools/kinds.py` (`McpServer.local_only`, false by
  default), `tools/service.py` and `tools/api.py` (`PUT /mcp/servers/{name}/local`; `local_only` in views and in `POST
  /mcp/servers`).
- [x] **Tests** (`tests/components/runtime/test_endpoint_routes.py`, design 0016 §4, §9, §10): adding without
  `agree` is refused; adding writes the template with `agreed` and marks the MCP servers named (every one when none
  are named); a key OpenRouter refuses is not kept and says why; one it takes is kept in `secrets/endpoint/openrouter/key`,
  shown by its last four, and never in any answer, event or log (a search of the home for its value finds only that
  file); removing is refused while a preset names the provider, and removes the key with the record. *Built:* the
  routes are `runtime/endpoint_routes.py`'s; the runtime uses no component, so the agreement's marks reach the tools
  component as `runtime.endpoint_added`'s `local_mcp` (an addition to the interface's event); the account (task 5's)
  is tested here; the refusal while a preset names the provider waits for cloud presets (task 6).

### Task 5: The models list and the account, read with the key

- [x] **Files:** `runtime/endpoints.py` (`models`: kept an hour, `fresh` asks again; the sorts of **The interface**),
  `runtime/api.py`.
- [x] **Tests** (`test_endpoint_routes.py`, design 0016 §6, §14): the list asks the fake with `supported_parameters=tools`
  and, for `most-popular`, `category=programming&sort=most-popular`; `search` narrows by name or id; `price`,
  `context` and `newest` sort as said; a second read within the hour does not ask again; without a key, 400
  `key_not_set`; the fake silent, 502 `cloud_unreachable`.

### Task 6: Presets name an engine or an endpoint

- [x] **Files:** `runtime/kinds.py` (`Preset.endpoint`; `engine` and `engine_version` optional; never both, never
  neither), `runtime/catalog.py` (`preset_problems` for a cloud preset: the provider exists, is agreed, has a key, its
  options valid, its slot `main`), `runtime/service.py` (`_preset_view`'s `provider`, `endpoint`, `price`; `needs`,
  `facts`, `count_tokens` and `check` for a cloud preset), `runtime/endpoints.py` (`write_preset`), `runtime/api.py`.
- [x] **Tests** (`tests/components/runtime/test_cloud_presets.py`, design 0016 §7): every preset Clank ships reads as
  before; a preset with both `engine` and `endpoint`, or neither, is refused; a cloud preset for `fast` or `vision` is
  refused, saying why; a cloud preset's problems name a missing key or agreement; `POST …/presets` refuses a model
  without tool calls; the view carries `provider` and `price`; `needs` says nothing to install or download. *Built:*
  the rule (one of engine and endpoint, the main slot only) is the kind's own; a cloud preset's problems are the
  provider's (`Endpoints.preset_problems`); its prices are the model's as last listed (`state/endpoint-models.json`);
  the refusal to remove a provider a preset names (task 4's) is tested here.

### Task 7: The main slot runs a cloud preset

- [x] **Files:** `clank/components/runtime/migrations/0003_launch_endpoint.sql` (a launch's `endpoint`, `route`);
  `runtime/state.py`; `runtime/launching.py` (a cloud preset's plan: the provider, its agreement, its key, the model in
  the list, the route); `runtime/slots.py` (start does nothing on this machine and says so; health: `GET /key`, then
  `TINY` with the key to the model; measure keeps its time and cost; unload; switch both ways); `runtime/service.py`
  (`route` from the launch's kept route, its reach and agreement read live); `runtime/watching.py` (a cloud slot is
  adopted after a restart when its record, agreement and key remain; `GET /key` every `cloud_health_seconds`, a
  401 failing the slot, a silence marking it "not reached since"); `runtime/kinds.py` (`cloud_health_seconds`, 300;
  `fallback_preset`, `daily-262k`).
- [x] **Tests** (`tests/components/runtime/test_cloud_slot.py`, design 0016 §7, against the fake OpenRouter and the
  fake engine): a load of a cloud preset plans, starts nothing, passes health with one tiny request whose cost is kept,
  and leaves the slot ready with the route of **The interface**; without a key, or not agreed, the plan refuses saying
  what to do; a switch from the fake engine stops it first, and back starts it after; a failed health returns to the
  last configuration that worked; the slot stays ready across a restart of the service; a key refused at the watch
  fails the slot; the fake silent leaves it ready, marked. *Built:* what load, unload, adoption and the watch mean
  for a cloud preset is `runtime/cloud.py`'s, the slots' operations branching to it; the launch also keeps its own
  requests' cost (`cost_usd`, migration `runtime 0003`); a key refused at the watch ends the launch `stopped`, the
  slot `failed`.

### Task 8: Whether a model is usable

- [x] **Files:** `runtime/service.py` (`usable`), `runtime/api.py` (`GET /runtime/usable`).
- [x] **Tests** (`test_cloud_slot.py`, design 0016 §14): nothing installed and no provider: not usable, saying what to
  do; a cloud preset with its key: usable, a candidate; an engine preset whose model is downloaded: usable; the main
  slot ready: usable.

### Task 9: The check and the test

- [x] **Files:** `runtime/endpoints.py` (the operations `runtime.endpoint_check` and `runtime.endpoint_test`; their
  costs kept with the check, counted in the totals by the gateway's service, task 19), `runtime/api.py`, the event
  `runtime.endpoint_checked`.
- [x] **Tests** (`tests/components/runtime/test_endpoint_check.py`, design 0016 §6): the check's items in order
  (agreed, key, account, models, model, answer, tools, thinking, policy, limits), each with its words; a key refused
  fails the key and leaves the rest unknown; the test's result for each refusal code of **The interface**; neither sends
  anything but Clank's made-up requests (the fake keeps what it was sent). *Built:* in `runtime/checking.py`; each
  check's and test's result and cost are kept in the runtime's `endpoint_checks` (migration `runtime 0004`), which the
  provider's view gives as its last check and `Endpoints.own_costs` counts.

### Task 10: The key handed to the gateway

- [x] **Files:** `gateway/server.py` (`PUT`, `DELETE`, `GET /keys`, behind the local token; keys in memory only; every
  record and the live view with a key's value replaced by `…` and its last four), `gateway/service.py` (`sync_keys`: on
  `runtime.slot` and `secret.set` events and every watch, read the key through the kernel, `user="gateway"`, and put it,
  or delete it), `gateway/routing.py` (a cloud route serves only once its key is held for its launch).
- [x] **Tests** (`tests/components/gateway/test_cloud_keys.py`, design 0016 §5): `/keys` refuses a caller without the
  local token; `GET /keys` never answers a value; a load hands the key once, recorded as `secret.used` by `gateway`
  with the launch; a new key set while loaded replaces it; an unload deletes it; a gateway started again gets it within
  one watch; a request waits while the key is not there and goes once it is; a key echoed in an answer is replaced in
  the record and the live view. *Built:* the keys are `gateway/keys.py`'s; `Gateway.sync_keys` runs a quarter second
  after a `runtime.slot` or an endpoint's `secret.*` event and at every watch; a key echoed in an answer's stream is
  tested with the forwarding (task 11).

### Task 11: The gateway forwards to OpenRouter

- [x] **Files:** `gateway/routing.py` (`SlotRoute`'s `provider`, `endpoint`, `base_url`, `reach`, `launch`,
  `read_timeout`, `adds`, `prices`), `gateway/server.py` (`connect` for a cloud route: a client of its own,
  certificates verified, connect 10 s, the read timeout between pieces; the URL; the headers; `endpoint_request` for
  the body; no `again`; `cloud_unreachable` and `cloud_silent`; refusals passed with their status and the adapter's
  words, `_unretried` for those OpenCode must not retry), `runtime/service.py` (`endpoint_request`,
  `endpoint_refusal`, `endpoint_full`: the gateway's way to the adapters, as `translate_request` is).
- [x] **Tests** (`tests/components/gateway/test_cloud_forwarding.py`, design 0016 §8): a streamed request reaches the
  fake with the listed id, the bearer key, `x-session-id`, `provider.data_collection` and nothing else changed; the
  answer streams back line by line, comment lines included; a whole answer too; a tool call's deltas pass unchanged;
  a mid-stream error ends the stream; a connection refused gives 502 `cloud_unreachable` and the fake saw one request
  (never two); a silent answer ends with `cloud_silent`; 401, 402, 403, 404, 429 (with `Retry-After`) and 503 pass with
  their status and the words of design 0016 §8, without OpenCode's retry words for the statuses not retried.
  *Built:* the route also names its `adapter`; a held request of a cloud slot, once resumed, goes the same way inside
  its stream; a 503 under `deny` keeps its status, so OpenCode may still retry it by its status (decision 0040); a key
  echoed in an answer is replaced in the record and the live view (task 10's).

### Task 12: Thinking streamed as `reasoning` (decision 0074)

- [x] **Files:** `gateway/server.py` (`_read_event`, `_guarded`, `_heard`: `reasoning` read as `reasoning_content`; a
  delta with both read once).
- [x] **Tests** (`tests/components/gateway/test_reasoning_field.py`, design 0016 §8, design 0015 §8): thinking as
  `reasoning` shows in the live view, counts as thinking, trips the loop guard when it repeats, and passes to the tool
  unchanged; a delta carrying both is counted once.

### Task 13: Workspace keys and bounds in the gateway's state

- [x] **Files:** create `clank/components/gateway/migrations/0001_gateway.sql` (`workspace_keys`: workspace, the key's
  SHA-256, its bound, answered, question; `cloud_costs`: run, seq, time, request, session, parent, workspace, preset,
  model, generation, tokens, usd, how), `gateway/component.py` (its migrations), `gateway/service.py` (`workspace_key`
  (makes the secret `workspace/<id>/gateway-key` once), `set_bound`, and the routes' `workspaces`).
- [x] **Tests** (`tests/components/gateway/test_workspace_keys.py`, design 0016 §9): a workspace's key is made once and
  kept; the routes carry its hash, never the key; `set_bound` changes the next routes. *Built:* the keys and bounds are
  `gateway/bounds.py`'s; `cloud_costs` also keeps a refused request's status and code, and a `rev` that only grows (the
  phone app's instruction).

### Task 14: A workspace's bound, and its question

- [x] **Files:** `clank/components/workspaces/kinds.py` (`Workspace.models`, `cloud_answered`), `workspaces/service.py`
  (bounds given to the gateway at each start of the service and each change; `ask_cloud`; listens to
  `gateway.cloud_wanted`; acts on the answer; the event `workspaces.cloud_answered`), `workspaces/api.py` (`POST
  /workspaces/{name}/cloud`, `POST /workspaces/{name}/cloud/ask`; the views' new fields).
- [x] **Tests** (`tests/components/workspaces/test_cloud_bound.py`, design 0016 §9, decisions 0103, 0112): every
  workspace starts `this-machine`; `ask` is not needed while the main slot runs a local model; with a cloud model it asks
  once, and returns the open question when asked again; *allow* makes the bound `cloud` and gives it to the gateway;
  *keep local* sets `cloud_answered` and is not asked again; an expired question leaves it unanswered; a workspace that
  existed before the agreement has the stronger words in its question. *Built:* in `workspaces/cloud.py`; the
  question's urgency is `high`; `GET /workspaces/folder` carries the bound at its top level (its `workspace` is a name),
  `GET /workspaces` on each row; every answer of `cloud/ask` says `start` (whether the agent may start now).

### Task 15: OpenCode and Clank's MCP server send the workspace's key

- [x] **Files:** `clank/components/agents/adapters/opencode.py` (`apiKey` the workspace's key), `agents/service.py`
  (`prepare` gets it from the gateway's service; Clank's server's environment gains `CLANK_GATEWAY_KEY` and
  `CLANK_NOTION`; a workspace allowed the cloud gets no MCP server marked local; the agents component gives the gateway
  the local-only tool prefixes at each start and each MCP server change; the agent's start paths (a flow's run) call
  `ask_cloud` and wait; the phone's start is *left for the phone's redesign (the owner, 2026-10-21)*: any client calls
  `POST /workspaces/{name}/cloud/ask` before it starts an agent), `workspaces/image/phone_mcp.py` (sends `Authorization: Bearer
  $CLANK_GATEWAY_KEY` to the gateway; lists no Notion tool when `CLANK_NOTION=off`).
- [x] **Tests** (`tests/components/agents/test_workspace_key_config.py`, design 0016 §9, §10): OpenCode's
  configuration names the workspace's key, never `local`; a cloud workspace's configuration has no server marked local
  and Clank's server is told no Notion; a local workspace's has them all; the gateway's routes carry the prefixes
  `clank_notion_` and `<server>_` for each server marked local. *Built:* a flow's run asks the workspace with task
  21; Clank's server is told `CLANK_NOTION=off` only in a workspace allowed the cloud.

### Task 16: The gateway checks each cloud request's workspace

- [x] **Files:** `gateway/server.py` (the key read from `Authorization`, hashed, looked up; no known key: this machine
  only; not answered: held with comment lines while `POST /api/v1/gateway/cloud-wanted` makes the service record
  `gateway.cloud_wanted`, then goes on when the routes say allowed, or is refused; kept local: 403
  `model_send_denied`; stale routes (older than 3 s): wait up to the hold, then 503 `service_silent`; `/notion/...`
  only for a known key whose bound is `this-machine`; `/activity`, `/activity/live`, `/completion` behind the local
  token), `gateway/service.py` (the service sends the local token to those routes; `cloud_wanted`; `gateway.cloud_refused`),
  `gateway/api.py` (`POST /gateway/cloud-wanted`).
- [x] **Tests** (`tests/components/gateway/test_cloud_bounds.py`, design 0016 §9, §10): a request without a known key
  is refused for the cloud and served by an engine; an unanswered workspace's stream is held, then goes on the same
  stream once allowed; *keep local* refuses it with words that say how to allow; a workspace allowed the cloud is
  refused Notion; the activity routes refuse a caller without the local token; with the service silent, a cloud request
  waits, then is refused `service_silent`. *Built:* the routes' freshness is the gateway's own (the time it last took
  them, when it follows a service); a withdrawn agreement refuses the next cloud request (`model_send_denied`); the
  activity routes take the token whenever the gateway was given one; the refusals reach `gateway.cloud_refused` through
  the spool (task 18).

### Task 17: Local-only content kept from the cloud

- [x] **Files:** `gateway/server.py` (local-only tools removed from a cloud request's `tools`, counted in its notes; a
  request whose messages call one, or whose session or parent is marked, refused 403 `local_only`; a session marked the
  first time any of its requests calls one, kept in `state/local-only.json`), `runtime/endpoints.py` (the agreement
  marks the MCP servers, task 4).
- [x] **Tests** (`tests/components/gateway/test_local_only.py`, design 0016 §10, decision 0111): `clank_notion_page`
  and `lit_search` are removed from a cloud request's tools and kept for a local one; a session that called
  `clank_notion_page` while local is refused the cloud, and stays refused after its requests no longer show the call
  (compacted); its subagent too; a new session is not; the marks survive a restart of the gateway. *Built:* the marks
  are `gateway/marks.py`'s; the agreement marks the MCP servers through the tools component (task 4).

### Task 18: Each cloud request's cost, spooled

- [x] **Files:** `gateway/server.py` (the record's `cost` and `generation`; the spool `state/cloud-spool.jsonl`; `GET
  /spend`), `gateway/service.py` (`take_spend` every 2 s into `cloud_costs`, idempotent by run and sequence; the
  generation lookups at 10 s, 60 s and 5 min for an entry without `usage`, with the key read through the kernel;
  estimates labeled).
- [x] **Tests** (`tests/components/gateway/test_cloud_cost.py`, design 0016 §12, decision 0108): a stream's `usage.cost`
  becomes its cost, `how` `usage`; a stream the client left has an estimate, then the generation's `total_cost`; the
  spool survives a restart of the gateway and nothing is counted twice; a whole answer's cost too. *Built:* the spool
  is `gateway/spool.py`'s (its run and sequence kept with it, so a restart keeps them), the service's side
  `gateway/costs.py`'s; each entry also carries its provider, status and code, so a refusal (Clank's or the
  provider's) reaches `gateway.cloud_refused` as the service takes it; an estimate's generation is asked 10 s, 60 s
  and 5 min after the service took it.

### Task 19: Cost seen by request, session, workspace and flow

- [x] **Files:** `gateway/kinds.py` (`CostSettings`, kind `cost`, `config/cost.json`: `day_usd`, `month_usd`,
  `warn_at`), `gateway/service.py` (`cost`, `cost_sessions`, `cost_requests`, `cost_for(sessions)` for the flows
  component; the runtime's own check and load costs counted; days and months local; `gateway.cost` coalesced),
  `gateway/api.py` (the cost routes of **The interface**), `clank/components/flows/service.py` (a flow's `cost`, from
  its boxes' sessions).
- [x] **Tests** (`tests/components/gateway/test_cost_views.py`, design 0016 §11, §12): today and this month by the
  computer's local day across midnight; a session's total counts its subagents; a flow's total is its boxes'; an
  estimate shows apart until it is exact; `PUT /gateway/cost/limits` writes the file and is recorded. *Built:* the
  views also carry what the phone app's instruction asks (the currency, the zone, each period's bounds and local name,
  the words, the revision; the lists' `rev`, `after=` and `X-Clank-Revision`); the flows component's `cost` gives a
  flow's latest run's.

### Task 20: The limits pause the cloud

- [x] **Files:** `gateway/service.py` (the routes' `cost`; at 80% `gateway.limit_warned`; at the limit
  `gateway.limit_reached` and the limit question; the answer writes `config/cost.json` and `gateway.limit_raised`; a
  period's end releases), `gateway/server.py` (a cloud request held before it is sent while the routes' spending plus
  the entries not yet taken reach a limit: `: held by Clank: the cloud spending limit is reached`; it goes on when the
  limit is raised or the period ends).
- [x] **Tests** (`tests/components/gateway/test_cost_limits.py`, design 0016 §11, decision 0104): at the limit a new
  cloud request is held and the question asked once; *double* raises it and the held stream goes on; *keep* leaves it
  held until the fake clock's day ends; requests in flight finish; a local request is never held; a burst between two
  takes is counted. *Built:* the limit question's *raise* asks its number (decision 0114), its urgency `high`, and
  it expires when the period ends; a request held for its workspace's answer is then held at the limit on the same
  stream; the gateway says how many it holds at a limit in its `/spend` answer (`held`).

### Task 21: A flow's box on a cloud preset

- [x] **Files:** `clank/components/flows/runner.py` (before switching to a cloud preset, `ask_cloud` for the
  workspace, waiting and saying so in the run's file), `flows/service.py` (`prepare`: each box's first message priced
  at its model's input price).
- [x] **Tests** (`tests/components/flows/test_cloud_box.py`, design 0016 §7, §9): a box on a cloud preset in a workspace
  not answered waits for the question, then switches; kept local, the box fails at a gate saying why; `prepare` shows
  the first message's price. *Built:* the workspaces component's `ask_cloud` takes the cloud preset a box is about to
  load, so the workspace is asked whatever the slot runs then; each box `prepare` shows gains `price_usd` and
  `price_said`.

### Task 22: What the census and the Monitor's facts read of a cloud route

- [x] **Files:** `runtime/service.py` (`facts` for a cloud preset: the adapter's `ContextFacts` with `on_gpu` false,
  `exact` none, `one_conversation` false, `fields` for OpenRouter's usage, and the model's facts without template or
  calibration).
- [x] **Tests** (`tests/components/runtime/test_cloud_facts.py`, design 0016 §13): a cloud preset's facts; the
  agents' estimate shares the census out to OpenRouter's `prompt_tokens` at the plain default, saying so; with records
  off the census of a cloud request keeps no text (decision 0096). *Built:* the facts come from the endpoint adapter's
  `context_facts` over the model's line as last listed (kept in `state/endpoint-models.json` with when it was read);
  a cloud preset's engine facts also name its `provider`; a session's context totals (`GET
  /agents/context/{workspace}/{session}`) say `"gpu": {"device": "cloud", ...}` for a step a cloud model answered (added
  2026-10-21, as plan s35's clients read it).

### Task 23: The capture tool, the real tests, the words and the generated files

- [x] **Files:** create `tools/capture_endpoint.py` (Clank's fixed made-up requests to OpenRouter, the key from
  `CLANK_TEST_OPENROUTER_KEY`, the recording written with the key and the account's label replaced); create
  `tests/real/test_openrouter.py` (marker `openrouter`, skipped without the variable; `pyproject.toml` declares the
  marker); `docs/EVENTS.md`, `docs/API.md`, `docs/CODEMAP.md`, `docs/TESTS.md` regenerated; this plan's checkboxes.
- [x] **Tests:** `uv run python -m tools.check --fix` passes. *Built:* the capture is tested against the fake
  (`tests/tools/test_capture_endpoint.py`); the contract runs over a recording made with a key as over the documented
  shapes, requiring of it only what can be asked for on demand.

### The owner's instructions of 2026-10-21: the phone, and a phone app built later

Two instructions came while this plan was built. **The phone is redesigned separately**: what exists only for the
phone (a phone-specific route, payload or notification) is *left for the phone's redesign (the owner, 2026-10-21)*;
the service's routes and events that every client uses stay. **The phone app** (an installed web app with live updates
and push notifications, designed now) must be as easy as possible to build later: every fact and action a client needs
is in the service's API and events, never in a client; every state change is an event whose summary is a short title
of Clank's own words (a provider, a model, a workspace, a flow, a box, an amount; never prompt or file text), and the
events that need the owner say so; the owner's answers are kernel questions with structured options, an amount a typed
answer; every action is one route; the lists a phone syncs take a cursor and carry a revision. Tasks 24 to 26 build
what this adds to the kernel and the design; tasks 18 to 20 build the rest, as **The interface** now says.

### Task 24: An event says whether it needs the owner (decision 0113)

- [x] **Files:** `clank/kernel/events.py` (`EventType.attention`, `Event.attention`, filled when recorded, published
  and read back), `clank/kernel/questions.py` (`question.asked` needs the owner), `tools/eventsdoc.py` ("kept, needs
  you"), `docs/decisions/0113-...`.
- [x] **Tests** (`tests/kernel/test_event_attention.py`, design 0002 §2.3): an event carries its type's attention as
  recorded, heard, published live and read back; the events page says it; a question asked needs the owner.

### Task 25: A question's option may ask for a number (decision 0114)

- [x] **Files:** `clank/kernel/questions.py` (`Option.asks`: a number's `unit`, `min`, `max`, `step`; an
  answer of that option without a number in its bounds, on its step, refused, saying them), `docs/decisions/0114-...`.
- [x] **Tests** (`tests/kernel/test_question_numbers.py`, design 0002 §2.5): an option that asks a number takes one in
  its bounds, refuses none, a word, or one out of bounds, saying the bounds and the unit; the answer keeps the number.

### Task 26: Design 0016 §17 gains "For the phone app"

- [x] **Files:** `docs/design/0016-cloud-models.md` (§17 revised after approval: the routes, events and questions the
  phone app uses; the revision log), `docs/design/README.md`.
- [x] **Tests:** `uv run python -m tools.check --fix` passes.

## The review's fixes (2026-10-21)

An independent review of the 34 commits found eleven faults; each was fixed test-first, one commit each:

1. and 2. **One gate.** Every path to a provider goes through `gate` in `gateway/server.py`, passed right before the
   request is sent and again after each hold (`cloud_through`, the only code that sends): the routes fresh, the slot
   still on a cloud model, the workspace's bound, nothing local-only, the local-only tools taken out, no limit reached.
   A paused session's request resumed while a cloud model served skipped every check, and a request held at a limit was
   sent as first judged (`tests/components/gateway/test_cloud_gate.py`).
3. OpenRouter's 503 under `data_collection: deny` is answered 403 (`data_policy`), the record keeping the 503: OpenCode
   retries any 503 (decision 0115; design 0016 §8 revised).
4. An MCP server added without saying is local only while a provider is agreed.
5. The gateway keeps `clank_notion_` from the cloud itself, and sends nothing to the cloud until the service's routes
   say the local-only list was given.
6. Today's and this month's bounds are each at the offset of their own moment (changes of the clock).
7. A request for this machine whose engine broke off while the slot switched to a cloud model ends `engine_broke_off`,
   never sent to the cloud by the gateway (it was a 500).
8. The record's data policy is merged into a `provider` object the tool sent, the stricter word kept (design 0016 §6,
   §8 revised).
9. The limit question's raise takes at least a cent above what was spent, and a change of the limit that still leaves
   the spending at it asks again.
10. A workspace's key is made only once the cloud is in play (a provider agreed, or the workspace allowed the cloud);
    before, its agent gets `local` as always and nothing is made among the secrets. Notion answers a request that names
    no workspace (a container started before the keys) while no workspace may use the cloud.
11. A refusal inside a held stream says what held it, and is worded to be retried when nothing reached the provider.

*For a running Clank:* the gateway takes the new code at its next start (`clank gateway restart`); the gateway's
migration `0001_gateway.sql` is new on this branch (its `key_hash` may now be empty), so no running state needs it
changed; a workspace's container need not be opened again while no workspace may use the cloud.

## The real checks owed with a key (the owner, 2026-10-21)

Design 0016 §18 lists twelve. With the key typed for the run only (`CLANK_TEST_OPENROUTER_KEY`, never stored):
`uv run python -m tools.capture_endpoint` writes the recording, which replaces `documented/http.json` as the contract's
first; `uv run pytest -m openrouter` runs the real tests on the cheapest model that takes tools. Each answer that
differs from the documentation revises design 0016 §3 and the adapter in one commit.

How each is made, once the key is at hand (`$env:CLANK_TEST_OPENROUTER_KEY = "..."` in the terminal, for the run):

| # | Check (design 0016 §18) | Made by | Then |
| --- | --- | --- | --- |
| 1 | `GET /models` without the key; the order of programming's most used | `test_check_1_…` prints the status; the capture's `models` | Design §3's row; `models_query` |
| 2 | A stream's chunk `id` is the generation; how soon `GET /generation` answers | `test_check_2_and_7_…`; the capture's `generation` (it waits up to 30 s) | `GENERATION_DELAYS` in `gateway/costs.py` |
| 3 | A prompt over the window: its status and words | By hand: a made-up prompt longer than a small model's window, through the gateway | `OpenRouter.FULL`, then `says_full` |
| 4 | `delta.reasoning`; thinking models across tool calls with `reasoning_content` only | The capture's `thinking` (`--thinking-model`); by hand, a session of the main families | A preset's `reasoning: none` for a family that refuses |
| 5 | A 402's body, a 403 from a budget | When they happen: the gateway's record keeps the refusal's words | `OpenRouter.refusal` |
| 6 | A stream's error `code`: a number or a word | When a mid-stream error happens: the record's `error` | `_engine_error` reads either |
| 7 | `usage.cost` in a stream's and a whole answer's last message; none when stopped | `test_check_2_and_7_…`, `test_check_7_…`; the capture's `cut` | `OpenRouter.cost` |
| 8 | `data_collection: deny`: which models it refuses (503) and its words | The check (`c`) on the models used | Add a model's words |
| 9 | `max_tokens` as OpenCode sends it; `x-session-id` raising `cached_tokens` | A session through the gateway: the records' `cached` | Design §8 |
| 10 | `GET /key` without a limit: both `null` | `test_check_10_…` prints them | `OpenRouter.account` |
| 11 | Comment lines and keep-alive through the gateway to OpenCode | A long answer through the gateway, OpenCode's terminal | — |
| 12 | Any transform that shortens a long prompt | Compare `usage.prompt_tokens` with the census on a long session | Design §13 |

## After this plan

Plan s35's last task runs its console, command and phone tests on these routes instead of its fake. Then the owner's
first session: Add a model with the real key, a scratch workspace of made-up content, `clank work`, and a look at the
cost on every page.
