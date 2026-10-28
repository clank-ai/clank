# Design 0016: cloud models, with an API key and nothing else

Roadmap parts 1 (the runtime: providers, presets, slots), 2 (the gateway), 3 (the console) and 4 (the setup guide:
its first slice), with what the phone (part 12) and VS Code (part 6) show of it. Started 2026-10-20 at the owner's
request. It builds the part of [design 0015](0015-endpoints.md) (endpoints, proposed, not approved) that a hosted API
needs, specialized to one provider, OpenRouter, and leaves the rest of 0015 (the tunnel, the cluster) to 0015.

A citation like `gateway/server.py:264` names `clank/components/gateway/server.py`, line 264, at commit 00de95c; other
paths start at the repository's root. Model ids, key labels and keys here are made up (`example-vendor/example-coder`,
`my laptop key`, `sk-or-v1-EXAMPLE`, `…a1b2`): a real key lives only in the owner's `CLANK_HOME/secrets/`, never in
the repository.

## Goal

The owner's request (2026-10-20, their words): "make sure that we are completely able to attach an API key from some
cloud provider in order to run their model, and that I can configure this entirely through the Clank menu when adding
this model. I need the ability to use the entire Clank setup with a cloud provider from an API key so that anyone can
download this and immediately begin using Clank without any kind of complicated model setup."

The owner's four answers, the same day, are the approved shape (decisions 0102-0105):

1. **Providers**: OpenRouter only, for now (one key, every major model behind it). Other providers later.
2. **Privacy**: ask once per workspace. Adding the provider asks the owner once to agree that prompts and the files the
   agent reads go to that provider; each workspace then asks the first time it would use the cloud model; existing
   workspaces stay local until the owner says otherwise; Notion pages and MCP servers marked local never go to the
   cloud.
3. **Cost**: show cost and an optional limit. Each request, session and flow shows what it cost (from the provider's
   prices and token counts) on the console, phone and Monitor; an optional daily or monthly limit pauses cloud requests
   when reached, until the owner raises it.
4. **First run**: a guided first step. With no usable model, the console opens on "Add a model": Cloud (pick
   OpenRouter, paste the key hidden, pick a model from its live list, Clank tests it with one short request) or Local
   (today's setup guide). One pass and they are working.

**Status:** written 2026-10-20 by Claude. Sections 2, 9, 11 and 14 are built on the owner's answers and are approved
as their shape; the screens, keys and words inside them are Claude's and change freely at the owner's look. Every
other section was proposed with Claude's calls (decisions 0106-0112) and approved for building on 2026-10-20 by
the owner, those calls staying open to the owner's change. Every fact about OpenRouter
was read in its public documentation on 2026-10-20 and names its page (§3); what the documentation does not say is
marked *to be checked with a real key*, which the owner provides on 2026-10-21 (§18). Nothing here was run against
OpenRouter.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner gets, and what this design takes from design 0015 | Approved 2026-10-20 for building, the owner's go-ahead |
| 2 | OpenRouter, the first cloud provider | Approved 2026-10-20 (the owner's answers: 1; decision 0102) |
| 3 | What OpenRouter offers, as its documentation says | Approved 2026-10-20 for building, the owner's go-ahead (each fact cited; what is unsaid is marked) |
| 4 | The provider's record, and its key | Approved 2026-10-20 for building, the owner's go-ahead |
| 5 | How the gateway gets the key | Approved 2026-10-20 for building, the owner's go-ahead (Claude's call, decision 0106) |
| 6 | The OpenRouter adapter | Approved 2026-10-20 for building, the owner's go-ahead |
| 7 | Cloud presets, and the main slot running one | Approved 2026-10-20 for building, the owner's go-ahead (Claude's call, decision 0107) |
| 8 | The gateway forwards to OpenRouter | Approved 2026-10-20 for building, the owner's go-ahead (Claude's calls, decisions 0109 and 0110; decision 0074 built); revised after approval 2026-10-21 (decision 0115: a refusal not to be retried is never answered 503) |
| 9 | Where a workspace's requests may go | Approved 2026-10-20 (the owner's answers: 2; decision 0103); how it asks is Claude's call (decision 0112) |
| 10 | Local-only content never reaches the cloud: how it is enforced | Approved 2026-10-20 for building, the owner's go-ahead (Claude's call, decision 0111) |
| 11 | Cost: each request, session and flow, and the limits | Approved 2026-10-20 (the owner's answers: 3; decision 0104) |
| 12 | How cost is known and kept | Approved 2026-10-20 for building, the owner's go-ahead (Claude's call, decision 0108) |
| 13 | What the Monitor shows of a cloud model | Approved 2026-10-20 for building, the owner's go-ahead |
| 14 | The first run: Add a model | Approved 2026-10-20 (the owner's answers: 4; decision 0105) |
| 15 | The Providers and models page, and the other pages | Approved 2026-10-20 for building, the owner's go-ahead |
| 16 | The commands | Approved 2026-10-20 for building, the owner's go-ahead |
| 17 | The phone and VS Code | Approved 2026-10-20 for building, the owner's go-ahead; revised after approval 2026-10-21 (the owner's instruction: a subsection For the phone app) |
| 18 | Tests, the fake OpenRouter, and the checks owed with a real key | Approved 2026-10-20 for building, the owner's go-ahead |
| 19 | Build steps | Approved 2026-10-20 for building, the owner's go-ahead |
| 20 | What this design does not cover | Approved 2026-10-20 for building, the owner's go-ahead |

## 1. What the owner gets, and what this design takes from design 0015

*Approved 2026-10-20 for building, the owner's go-ahead.*

Someone who downloads Clank, runs `uv sync` and `uv run clank`, and has an OpenRouter key, is working within minutes:
the console opens on Add a model (§14), they agree once to what goes to the cloud, paste the key (never shown), pick a
model from OpenRouter's live list, and Clank tests it with one short request and loads it into the main slot. Then This
folder (F4) starts the agent as it does today, asking once whether this workspace may use the cloud model (§9). Every
request, session and flow shows what it cost, and an optional daily or monthly limit pauses the cloud when reached
(§11). Everything the rest of Clank does with the main slot (OpenCode, the Monitor, flows, the phone, VS Code) works
with a cloud model as it does with KVMem: the gateway forwards to OpenRouter instead of to an engine (§8).

**What this design builds of design 0015**, specialized to OpenRouter, and what stays 0015's:

| Design 0015 | Built here | Stays 0015's |
| --- | --- | --- |
| §2 the endpoint record | The kind `endpoint` with `title`, `adapter`, `url`, `auth`, `reach`, `timeout_seconds`, `notes`, and two fields of its own: `options` (the adapter's) and `agreed` (§4) | `tunnel` and `insecure`, and the rules that use them |
| §3 the adapter | A kind of adapter `endpoint`, its first adapter `openrouter` (§6) | `openai-compatible` (vLLM, SGLang, `llama-server`) |
| §4 presets name an engine or an endpoint | As written; a cloud preset is for the main slot only (§7) | |
| §5 the tunnel, §7 the watcher's reopening | Nothing: a cloud model is reached by its URL | All of it |
| §6 a slot runs an endpoint | Load, unload and switch of a URL endpoint; the route kept with the launch (migration `runtime 0003`); no tunnel, no job, no wrong-key probe (§7) | The tunnel's start, the server's identity by a wrong key |
| §8 the gateway forwards | As written for a URL, with OpenRouter's fields and cost (§8) | |
| §9 keys | The key's place, its setting never from an argument, read once per launch; how the gateway gets it is decided for the cloud by decision 0106 (§5) | The cluster's server side |
| §10 where requests may go | Workspace keys, bounds, the gateway's check, Notion by a known key, the activity routes by the local token (§9, §10); a question in place of a refusal | `my-servers`, and the owner's question about the cluster (decision 0075) |
| §11 the check | `clank endpoint check openrouter` and `c`: the key, the account, the models, one short request, a tool call (§6) | ssh, the job, the tunnel |
| §12 the commands | `clank endpoint add`, `key`, `list`, `show`, `models`, `preset`, `check`, `remove` for OpenRouter (§16) | `--ssh`, `--jump`, `--remote`, `set` |
| §13 `clank work` and the folder page | As written, with the fallback preset (§7) | |
| §14 recordings and fakes | The fake server for OpenRouter, the contract test over HTTP recordings, `http.json` accepted (§18) | The fake `ssh`, the cluster's recordings |

**The reach.** Design 0015 names three reaches, `this-machine`, `my-servers` and `hosted`. This design uses the owner's
word for the third, `cloud`; 0015's `hosted` is the same reach, and 0015 takes the name when it is next revised.

**What it changes in approved text:**

| Approved | It says | This design | Where |
| --- | --- | --- | --- |
| Design 0001 §1 | "Endpoints and CPU engines run alongside" the engines on the GPU | A cloud model serves the main slot in an engine's place, one provider at a time (decision 0107); `fast` and `vision` stay on this machine | §7 |
| Design 0001 §7.3 | The first-run guide: five steps, `clank setup` or the console's first screen | Its steps 2-4 for "With an API key", as Add a model, ahead of the rest of M10 (§14) | §14 |
| Design 0001 §7.6 | Templates for known hosted providers; keys in `secrets/`; the guide tests a key with a request of a few tokens and lists the models | OpenRouter's template is its adapter (§6); the test is one short request (§14) | §4, §6, §14 |
| Design 0002 §2.6 | `model.send`, a workspace's bounds checked by the gateway | Built for the cloud; beyond its bound a workspace is asked once instead of refused (decision 0112) | §9 |
| Design 0002 §2.7 | A data-plane process gets a `process` token | Not built: the gateway is handed the key by the service, behind its local token (decision 0106) | §5 |
| Decision 0021 | `secret.use` and `model.send` to a third party are decided at the moment of use | For the key, the moment is the launch (as decision 0073 proposed); a cloud request waits for the service's routes when they are stale, instead of being refused at once | §5, §9 |

## 2. OpenRouter, the first cloud provider

*Approved 2026-10-20 (the owner's answers: 1; decision 0102).*

- **One provider, OpenRouter.** One account and one key reach the major models (OpenAI's, Anthropic's, Google's, the
  open-weight ones), each at its own price, through one OpenAI-compatible API (§3). The owner picks the model; Clank
  never picks one for them.
- **One adapter, `openrouter`**, of a new kind of adapter, `endpoint` (§6). Another provider later is another module
  of the same kind (principle 2): nothing in the gateway, the slots, the Monitor or the console names OpenRouter except
  through its adapter, its record and its words.
- **Other providers later**, each with its own design note and decision: OpenAI's, Anthropic's and Google's own APIs,
  and 0015's `openai-compatible` (any server that speaks Chat Completions, a hosted one among them).

## 3. What OpenRouter offers, as its documentation says

*Approved 2026-10-20 for building, the owner's go-ahead (each fact cited; what is unsaid is marked).*

Read on 2026-10-20 in OpenRouter's public documentation. Each fact names its page; *to be checked with a real key*
marks what the pages do not say, or say in two ways.

| Fact | What the documentation says | Page |
| --- | --- | --- |
| Base URL | `https://openrouter.ai/api/v1`; chat at `POST /chat/completions` | [API reference](https://openrouter.ai/docs/api-reference/overview), [Authentication](https://openrouter.ai/docs/api-reference/authentication) ("set the `api_base` to `https://openrouter.ai/api/v1`") |
| The key | Sent as `Authorization: Bearer <key>`. OpenRouter is a GitHub secret-scanning partner, emails the owner when a key is found exposed, and "recommend[s] setting a credit limit on every key". Its format is not documented | [Authentication](https://openrouter.ai/docs/api-reference/authentication) |
| Compatibility | OpenAI's Chat Completions: `messages`, `model`, `stream`, `tools`, `tool_choice` (`none`, `auto`, `required`, a named tool), `parallel_tool_calls`, `max_tokens` (deprecated for `max_completion_tokens`, still accepted), `stream_options` (its `include_usage` has no effect), `provider`, `reasoning`, `session_id`, `user` | [Chat completion request](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request.md) |
| The models list | `GET /models`: `{data, total_count, links}`; each model's `id` (what a request names), `name`, `context_length`, `architecture.input_modalities`, `pricing` (strings, US dollars per token: `prompt`, `completion`, `request`, `image`, `input_cache_read`, `input_cache_write`, `internal_reasoning`, …), `top_provider` (`context_length`, `max_completion_tokens`, `is_moderated`), `supported_parameters` (`tools`, `tool_choice`, `reasoning`, …), `reasoning` (`mandatory`, `default_effort`, `supported_efforts`), `expiration_date`. Filters: `supported_parameters=tools`, `category=programming`, `sort` (`most-popular`, `pricing-low-to-high`, `context-high-to-low`, `newest`, …), `q` (search) | [List models](https://openrouter.ai/docs/api/api-reference/models/get-models.md), [Models](https://openrouter.ai/docs/overview/models) |
| Whether listing needs the key | The reference applies the key to every route; the examples call it without one: *to be checked with a real key*. Clank always sends it | the same |
| The key's own facts | `GET /key`: `label`, `limit` and `limit_remaining` (US dollars, `null` without a limit), `limit_reset`, `usage`, `usage_daily`, `usage_weekly`, `usage_monthly` (US dollars, UTC days, weeks Monday to Sunday), `is_free_tier`, `budgets` and `effective_budget` (a budget whose `remaining_usd` is zero or less refuses with 403 until it resets), `expires_at`; 401 for a key refused | [Get current API key](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key.md), [Limits](https://openrouter.ai/docs/api-reference/limits) |
| The account's balance | `GET /credits` takes a management key only (403 otherwise): a plain key cannot read the account's balance | [Get remaining credits](https://openrouter.ai/docs/api-reference/get-credits) |
| Cost of a request | "Full usage details are now always included automatically in every response": `usage.prompt_tokens`, `completion_tokens`, `total_tokens` (the model's own tokenizer), `prompt_tokens_details.cached_tokens`, `completion_tokens_details.reasoning_tokens`, `cost` ("the total amount charged to your account", in credits), `cost_details`, `is_byok`; in a stream, in the last message before `[DONE]`; `usage: {include: true}` is deprecated and does nothing | [Usage accounting](https://openrouter.ai/docs/use-cases/usage-accounting), [API reference](https://openrouter.ai/docs/api-reference/overview) |
| Credits | "a credit system where the base currency is US dollars"; "no markup on inference pricing"; a fee when credits are bought; unused credits may expire after a year | [FAQ](https://openrouter.ai/docs/faq) |
| A request's record afterward | `GET /generation?id=gen-…`: `total_cost`, `tokens_prompt`, `tokens_completion`, `native_tokens_*`, `model`, `provider_name`, `streamed`, `finish_reason`, `latency`. That a stream's chunk `id` is this `gen-…` id: *to be checked with a real key* | [Get a generation](https://openrouter.ai/docs/api/api-reference/generations/get-generation.md) |
| Streaming | Server-sent events; "comments to prevent connection timeouts" (`: OPENROUTER PROCESSING`), to be ignored. A stream is stopped by closing the connection, which "immediately stops model processing and billing" for the providers that support it (a list), and otherwise the whole answer is billed | [Streaming](https://openrouter.ai/docs/api-reference/streaming) |
| Errors | `{"error": {"code", "message", "metadata"}}`, the status as the code: 400, 401 (key refused), 402 (credits used up: `openrouter_credits`; the key's limit: `openrouter_key_limit`), 403 (permissions, a guardrail, moderation, a budget), 404, 408, 413, 422, 429 (with `Retry-After` when every provider gave one), 500, 502 (the model is down), 503 (no provider meets the request's routing), 524, 529. Before the first token, a plain error; after it, an event with `error` and a choice whose `finish_reason` is `error`, under a 200. Where `openrouter_credits` appears in a 402's body, and whether a stream's error `code` is a number (the errors page) or a word (`server_error`, the streaming page): *to be checked with a real key* | [Errors and debugging](https://openrouter.ai/docs/api-reference/errors), [Streaming](https://openrouter.ai/docs/api-reference/streaming), [Limits](https://openrouter.ai/docs/api-reference/limits), [Chat completion request](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request.md) |
| Rate limits | None documented per key for paid models ("different rate limits for different models"); free models (ids ending `:free`) 20 a minute, 50 a day, 1,000 a day once 10 credits were bought; a negative balance refuses free models too | [Limits](https://openrouter.ai/docs/api-reference/limits) |
| Thinking | `reasoning: {effort | max_tokens, exclude, enabled}`, effort one of `max`, `xhigh`, `high`, `medium`, `low`, `minimal`, `none`; thinking tokens are billed as output; a whole answer's `message.reasoning` and `reasoning_details`; a stream's `delta.reasoning` and `delta.reasoning_details`; earlier thinking sent back as `reasoning` (or `reasoning_content`, an alias) or as `reasoning_details`, which some models need whole across tool calls | [Reasoning tokens](https://openrouter.ai/docs/use-cases/reasoning-tokens), [Chat completion request](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request.md) |
| Tool calls | OpenAI's: `tools`, `tool_choice`, `message.tool_calls`, streamed `delta.tool_calls`, `finish_reason: "tool_calls"`; a model takes them when its `supported_parameters` holds `tools` | [Chat completion request](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request.md), [List models](https://openrouter.ai/docs/api/api-reference/models/get-models.md) |
| Where data goes | "Prompt and completion are not logged by default" by OpenRouter; each provider has its own policy; `provider.data_collection: "deny"` routes only to providers "which do not collect user data", and a request no provider can serve so is refused; `provider.zdr: true` only to zero-data-retention endpoints | [FAQ](https://openrouter.ai/docs/faq), [Provider logging](https://openrouter.ai/docs/features/privacy-and-logging), [Provider routing](https://openrouter.ai/docs/features/provider-routing) |
| Its prompt cache | `session_id` (or the `x-session-id` header) "serves as the sticky routing key for prompt cache hits" | [Chat completion request](https://openrouter.ai/docs/api/api-reference/chat/send-chat-completion-request.md) |
| Attribution | `HTTP-Referer` (required for an app page and its rankings), `X-OpenRouter-Title` (`X-Title`, the older name), `X-OpenRouter-Categories`; all optional for the API | [App attribution](https://openrouter.ai/docs/app-attribution) |

## 4. The provider's record, and its key

*Approved 2026-10-20 for building, the owner's go-ahead.*

The runtime component's settings kind `endpoint` (design 0015 §2), one file per provider:
`CLANK_HOME/config/endpoints/<id>.json`, its id the name the owner gives it (`openrouter` by default). Clank ships none;
Add a model (§14) and `clank endpoint add openrouter` (§16) write it from the adapter's template.

| Field | Holds |
| --- | --- |
| `title` | Its name in every client: `OpenRouter` |
| `adapter` | `openrouter` (§6) |
| `url` | The adapter's own base URL, `https://openrouter.ai/api/v1`; any other is refused for this adapter, so the key never goes elsewhere |
| `auth` | `bearer`: the key, kept in `secrets/` (below) |
| `reach` | `cloud` (§1): refused as anything else for this adapter |
| `options` | The adapter's provider options (§6): `data_collection` (`deny` by default, decision 0109) and `zdr` (`false`) |
| `agreed` | When the owner agreed that prompts and the files the agent reads go to this provider (§9); empty: not agreed, and nothing loads from it |
| `timeout_seconds` | The longest the gateway waits for the next piece of an answer (§8); 600 |
| `notes` | Anything worth knowing |

```json
{
  "schema": "endpoint/1",
  "title": "OpenRouter",
  "adapter": "openrouter",
  "url": "https://openrouter.ai/api/v1",
  "auth": "bearer",
  "reach": "cloud",
  "options": { "data_collection": "deny", "zdr": false },
  "agreed": "2026-10-21T09:12:04.120Z",
  "timeout_seconds": 600,
  "notes": "Added by Add a model."
}
```

- **The key** is a secret of the kernel (design 0002 §2.8, `kernel/secrets.py:59-113`): scope `endpoint/<id>`, name
  `key`, the file `CLANK_HOME/secrets/endpoint/openrouter/key`, readable by the owner only, shown by its last four
  characters and when it was set. It is never written anywhere else: not in the record, a preset, a launch, a route,
  an event, an operation's log, the gateway's records or a process's log.
- **Set only after OpenRouter accepts it.** The console's field and the command take it hidden (§14, §16); the service
  asks `GET /key` with it first and keeps it only when the answer is 200, so a mistyped key is never kept. A refused
  key is said in words (§6) and not kept. Setting it again replaces it, and a cloud model loaded is handed the new one
  (§5).
- **Never from an argument**: `clank endpoint key openrouter` asks without echo, or reads one line of standard input
  with `--stdin` for a script; the API takes it in a request's body over the loopback, behind the local token, and no
  route ever answers with it.
- **Removed with the record.** `clank endpoint remove openrouter` and the Providers page's `r` remove the record and
  its key, refused while the main slot runs one of its presets or a preset names it (the refusal names them).
- **When a change applies.** `options` and `timeout_seconds` apply at the next load; `agreed` cleared stops the next
  load and, at the gateway, the next request (§9); the key at once (§5).

## 5. How the gateway gets the key

*Approved 2026-10-20 for building, the owner's go-ahead (Claude's call, decision 0106).*

Decision 0073 (proposed with design 0015) offers (a) a process token and routes only processes may call, a change to
the kernel, and (b) the gateway reading the key's file itself. Decision 0106 takes a third way, the one decision 0084
already built for pauses: **the service hands the key to the gateway, behind the service's local token, while a cloud
model is loaded.**

- **The gateway's own routes** (on its port, `127.0.0.1` only), each taking the local token as `the_owners` checks it
  (`gateway/server.py:185-193`): `PUT /keys/{endpoint}` (`{"key": "…", "launch": 12, "set": "<when the key was set>"}`),
  `DELETE /keys/{endpoint}`, and `GET /keys`, which answers each key it holds by its endpoint, its last four, its launch
  and when it was set, never its value. No route of the gateway answers with a key.
- **Who hands it.** The gateway component's service, which uses the runtime: when the main slot's route names an
  endpoint that needs a key (§7), it reads the key through the kernel (`Secrets.value(…, user="gateway", why="launch
  12: cloud: Example Coder")`, one `secret.used` event) and puts it to the gateway; when no slot runs that endpoint, it
  deletes it there. It does so on each `runtime.slot` event and each `secret.set` of that scope, and checks `GET /keys`
  in its watch every five seconds (`gateway/service.py:416-429`), so a gateway started again (with nothing in memory)
  gets it within seconds.
- **Held in memory only**, while that launch is the route. A request for the slot while the key is not there yet waits
  as for a starting slot (`Routes.ready`, `gateway/routing.py:132-143`), up to the hold, then is refused saying why.
- **While the service does not answer**, the gateway keeps the key it was handed for the launch (decision 0073's
  refinement of 0021: the moment of use is the launch), but cloud requests wait for fresh routes (§9).
- **Containers never reach it.** Every container reaches the gateway through the edge (`workspaces/image/edge.py:1-6`)
  and never holds the local token (decision 0084), so it can neither hand a key nor list one.
- **Removed from what is written.** The gateway replaces the key's value by `…` and its last four wherever it appears
  in a record or the live view, even when echoed back in an answer (design 0002 §2.8's last rule); credential headers
  are never kept already (`gateway/records.py:24`).

## 6. The OpenRouter adapter

*Approved 2026-10-20 for building, the owner's go-ahead.*

A new kind of adapter of the runtime component, `endpoint` (design 0002 §2.10; design 0015 §3), beside `engine` and
`host`; its first adapter, `clank/components/runtime/adapters/openrouter.py`, is OpenRouter's template and its words.
Its interface (the kind's, so the next provider meets it too):

- `URL`, `REACH`, `AUTH`: `https://openrouter.ai/api/v1`, `cloud`, `bearer` (§4).
- `provider_options()`: the record's `options`: `data_collection` (`deny`, `allow`) and `zdr` (a boolean).
- `options(model)`: a cloud preset's options (§7): `context` (at most the model's), `max_output` (16,384 or the model's
  `top_provider.max_completion_tokens` when smaller), `reasoning` (`default`, or an effort the model lists in
  `reasoning.supported_efforts`, else one of OpenRouter's seven), and `images` (from `architecture.input_modalities`).
- `account(answer)`: `GET /key` read into what clients show: its label, its limit and what is left, its use today and
  this month (OpenRouter's own count, UTC), whether it is a free-tier key, a budget that refuses and when it resets.
- `models(answer)`: `GET /models?supported_parameters=tools` read into Clank's model line: its id exactly as listed,
  its name, its window (the smaller of `context_length` and `top_provider.context_length`), its most output
  (`top_provider.max_completion_tokens`), its prices per million tokens (in, out, cached in), whether it thinks
  (`reasoning` in `supported_parameters`) and reads images, whether it is free (`:free`) and its limits then, and its
  `expiration_date`. Models without `tools` are listed only when asked (`--all`): the agent cannot work without tool
  calls.
- `translate(body, route)`: the request as the tool sent it (§8), its `model` the listed id, with the preset's thinking
  effort added where the tool set none (decision 0109), and the provider options always, merged into a `provider` the
  tool sent with the stricter word kept (§8, revised 2026-10-21).
- `headers(key, session)`: `Authorization: Bearer <key>`, and `x-session-id` when the tool named its session (§8).
- `refusal(status, body)`: what a refused request means, in words that say what to do (§8's table).
- `says_full(status, body)`: whether a refusal is the model's context being full (decision 0090). The words are *to be
  checked with a real key* (§18); until then none are declared, and such a refusal passes on as OpenRouter said it.
- `cost(usage)`: the request's cost from `usage.cost`, else an estimate from its tokens and the model's prices (§12).
- `capabilities()`: tool calls, thinking streamed as `reasoning`, usage at the end of a stream, cost in the usage.
  Never `/infill`: completion stays on this machine (design 0006).
- **The check** (design 0015 §11, decision 0076), `clank endpoint check openrouter` and `c` on the Providers page, an
  operation of a few seconds, sends only Clank's own made-up requests: the key (`GET /key`), the list, one short reply
  ("Reply with OK.", 16 tokens at most) and a call to a made-up tool, the last two to the model named (the preset's,
  or `--model`). Each item passes, fails or warns, with why; the result is an event (`runtime.endpoint_checked`).

```
 CHECK  openrouter (OpenRouter)
  ok    agreed    2026-10-21 09:12, by you (console)
  ok    key       set (ends …a1b2), accepted: "my laptop key"; its limit $20.00, $18.71 left
  ok    account   used today $0.12, this month $1.29 (OpenRouter's count, UTC days)
  ok    models    211 take tool calls (listed 09:14)
  ok    model     example-vendor/example-coder: window 262,144, output 32,768, $0.30 in, $1.20 out per million
  ok    answer    "OK" in 0.8 s, cost $0.000021
  ok    tools     a call to the made-up tool came back as a tool call
  ok    thinking  streamed as reasoning
  ok    policy    answered with data_collection deny
  warn  limits    no daily or monthly limit in Clank (L on the Providers page)
```

## 7. Cloud presets, and the main slot running one

*Approved 2026-10-20 for building, the owner's go-ahead (Claude's call, decision 0107).*

**A cloud preset** names `endpoint` in place of `engine` and `engine_version` (design 0015 §4, which makes those two
optional beside `endpoint`, never both, never neither); its `model` is the id OpenRouter lists, sent exactly as listed.

```json
{
  "schema": "preset/1",
  "title": "cloud: Example Coder",
  "endpoint": "openrouter",
  "model": "example-vendor/example-coder",
  "options": { "context": 262144, "max_output": 16384, "reasoning": "default" },
  "notes": "Added by Add a model on 2026-10-21; $0.30 in, $1.20 out per million tokens then."
}
```

- Every preset written before reads the same (`preset/1`, optional fields added). Each preset as clients see it gains
  `provider`: `kvmem-llamacpp v0.16.0-rc1`, or `cloud openrouter`; the picker, the Presets and Models pages, `clank
  preset list` and VS Code print it (design 0015 §4). Every reader of a preset's engine handles a cloud preset: its
  problems (the endpoint exists and is agreed, its key is set, its options are valid), its needs (nothing to install or
  download), its facts (§13).
- **The main slot only.** `fast` needs `/infill` on this machine (design 0006) and `vision` a model loaded on demand
  here (design 0008 §7): a cloud preset for either is refused, saying why.
- **A smaller context costs less.** OpenCode sends a session's whole history with every request, so the preset's
  `context` is also the owner's lever on cost: OpenCode compacts sooner, and each request is smaller. Add a model says
  so (§14).

**What load means for a cloud preset** (design 0003 §6.1's steps; design 0015 §6, without the tunnel):

| Step | An engine, today | A cloud preset |
| --- | --- | --- |
| plan | The launch: its command line, its memory, its fit | The connection: the provider, its agreement, its key (set, its last four), the model in OpenRouter's list (window, output, prices, tool calls, its `expiration_date`), and the route it will give the gateway. Refused, saying what to do, when the provider is not agreed, the key is not set, or the model is not listed. No GPU, install or catalog is read |
| start | The engine started on its host | Nothing starts on this machine, and the step says so; the gateway is handed the key (§5) |
| health | Its log, its model listed, a tiny request | The key accepted (`GET /key`), then the same tiny request (`runtime/slots.py:52`, "Reply with OK.", 16 tokens at most), for the model, with the key: its answer, its time and its cost, shown |
| measure | The GPU memory it took | The tiny request's time and cost; the configuration kept as the last that worked |

- **The route**, kept with the launch (migration `runtime 0003`: a launch's `endpoint` and its `route` as JSON, never
  a key; `engine` and `engine_version` empty, so the GPU's learned memory never reads it): the provider (`endpoint`),
  the endpoint's id, the base URL, the model id, the reach (`cloud`), the window (the smaller of the preset's and the
  model's), the output limit, `images`, the read timeout, the request fields the adapter adds (§8), the model's prices
  (for estimates, §12), and the launch's id (for the key, §5). Its reach and the endpoint's `agreed` are read from the
  record each time the routes are asked for (every second), so clearing the agreement applies to the next request.
- **Unload** tells the gateway to forget the key (§5) and leaves the slot stopped; nothing is stopped at OpenRouter.
  Requests already streaming finish.
- **Switch.** From KVMem to the cloud, the engine stops first (the GPU freed), then the cloud preset's start; from the
  cloud to KVMem, the gateway forgets the key, then the engine starts. A failed switch returns to the last
  configuration that worked, either way (design 0001 §4.3). The console's busy check (wait, switch now, cancel; design
  0001 §4.2) applies as for engines.
- **Adopted after a restart.** A cloud slot has no process: after a restart of the service, or of the computer, it
  stays ready when its record, agreement and key are still there (the key is handed to the gateway again, §5), and its
  health is asked once; today a slot without a process is skipped (`runtime/watching.py:96`).
- **Watched** every `cloud_health_seconds` (a runtime setting, 300): `GET /key`, which costs nothing. A 401 fails the
  slot at once ("OpenRouter refused the key: it may have been deleted; set a new one"); a network that does not answer
  leaves it ready, marked "not reached since 09:41" on every client, since the gateway answers each request as it goes
  (§8). An engine's crash rule (`runtime.restart`) never applies.
- **A flow's box** may name a cloud preset (design 0013 §7, decision 0062): the runner switches the main slot as for
  any preset, after the workspace has allowed the cloud (§9); `clank flow prepare` shows each box's first message
  priced at the model's input price, and the Flow view what each box cost (§11).
- **`clank work`, `clank code` and This folder** use what the main slot runs, else its last configuration that worked,
  else the runtime's `fallback_preset` (design 0015 §13): on a machine with only a cloud model, the last that worked is
  the cloud preset Add a model loaded.
- **OpenCode's limits follow the route** (`agents/service.py:126`): the window less the margin (decision 0089), and
  the output limit; its configuration says `attachment` from `images`. A model that does not take tool calls is never
  offered for the main slot (§6).

## 8. The gateway forwards to OpenRouter

*Approved 2026-10-20 for building, the owner's go-ahead (Claude's calls, decisions 0109 and 0110; decision 0074 built).*

Today the gateway forwards only to an engine on this machine (`gateway/server.py:364-415`: `http://127.0.0.1:<port>`,
`translate_request` by engine). With a cloud route:

- **Where.** `<base URL>/chat/completions` (`https://openrouter.ai/api/v1/chat/completions`), with an HTTP client of
  its own for the cloud (certificates verified, as httpx2 does by default; a connect timeout of 10 s; the endpoint's read
  timeout between pieces, below). The engines' client keeps no read timeout (`gateway/server.py:159`).
- **What** (decision 0109). The request as OpenCode sent it, but: `model` is the listed id; `provider` gets
  `data_collection` (and `zdr` when set) from the record's options, merged into a `provider` the tool sent of its own
  with the stricter word kept (`deny` over `allow`, `zdr` on over off: revised after approval 2026-10-21, since a tool's
  own `provider` dropped the record's `deny`);
  `reasoning` gets the preset's effort when it is not `default` and the tool sent none. Nothing else is added or
  removed: `stream_options` and `max_tokens` pass as sent (both accepted, §3), and no `usage` field is sent (deprecated,
  §3). The record's `notes` say each change, as an engine's translation does.
- **Headers.** `Authorization: Bearer <key>` (§5), `Content-Type`, and `x-session-id` with the session's id when
  OpenCode sent `X-Session-Id` (OpenRouter's prompt cache keeps a session on one provider, §3, which lowers its cost).
  No attribution header (decision 0109). Never the tool's own headers: the gateway builds its own request, as today.
- **The workspace's bound first** (§9), and what never goes (§10), before anything is sent.
- **The spending limit** (§11): while it is reached, the request is held before it is sent.
- **Streamed** as today (`_relay`, `gateway/server.py:509-586`): whole lines passed on as they come. OpenRouter's
  comment lines pass to OpenCode as the gateway's own comments do while it holds a request (decision 0055); a
  mid-stream error event, which carries a choice whose `finish_reason` is `error`, ends the stream as one
  (`_finishes`, `:593-610`), and its words are recorded (`_engine_error`, `:619-636`).
- **Thinking streamed as `reasoning`** (decision 0074, proposed with design 0015, built here): the loop guard, the live
  view and the count of a request's tokens read `delta.reasoning` as they read `reasoning_content` today
  (`gateway/server.py:674, 683, 696`); the stream reaches OpenCode unchanged. OpenCode sends earlier thinking back as
  `reasoning_content` (`agents/adapters/opencode.py:161`), which OpenRouter takes as an alias of `reasoning` (§3). It
  does not send `reasoning_details`, which some models want whole across tool calls: *to be checked with a real key*,
  per family (§18); until then a preset's `reasoning` can be set to `none` for a model that refuses.
- **Usage and cost** from the stream's last message (`usage`, read already: `_read_event`, `:661-663`), its `cost` kept
  in the record with how it was known (§12); the chunk's `id` kept as the request's `generation`.
- **The loop guard** runs as for an engine (decision 0040). When it stops an answer, the gateway closes the
  connection, which stops OpenRouter's billing for providers that support it (§3); the usage never arrives, and the
  cost comes from the generation's record (§12).
- **A read timeout, never sent again** (design 0015 §8): an answer silent for the endpoint's `timeout_seconds` (600; a
  live stream carries OpenRouter's comments) ends with `cloud_silent` (an error event in a stream, 504 otherwise).
- **Never sent again by the gateway** (decision 0110). Today a request an engine broke off before its first token is
  sent again once the slot is back (`again()`, `gateway/server.py:382-401`). A cloud request that broke off may have
  been billed, so it is never sent again by the gateway: a connection refused or lost before any answer ends with 502
  `cloud_unreachable` ("OpenRouter did not answer: <error>; check this computer's network"), which OpenCode retries by
  its own rule (decision 0040), each try recorded with its cost.
- **Refusals reach the tool with their status** (decision 0110), their message OpenRouter's words then Clank's,
  passed through `_unretried` (`gateway/server.py:779-788`) for the statuses OpenCode must not retry, so a payment
  refusal never loops:

| Status | OpenRouter means | Clank adds | Retried by OpenCode |
| --- | --- | --- | --- |
| 400 | The request is wrong; or the context is full (§6's `says_full`) | The full context is answered as decision 0090 says (400, `context_length_exceeded`), so OpenCode compacts | No |
| 401 | The key was refused | "OpenRouter refused the key: it may have been deleted or disabled. Set a new one: Providers and models, k; or clank endpoint key openrouter" | No |
| 402 | Credits used up, or the key's own limit reached | "Your OpenRouter credits are used up, or this key's own limit is reached: add credits or raise the key's limit at openrouter.ai, then ask again" | No |
| 403 | A budget, a guardrail or moderation refused | "OpenRouter refused this request: <its words>"; a budget names when it resets (§6's `account`); moderation's flagged text is kept in the record only when records are on (decision 0096) | No |
| 404 | No such model | "OpenRouter lists no model <id>; it may have been retired (its expiration_date). Pick another: Add a model, or clank endpoint models openrouter" | No |
| 408, 524 | Timed out | As OpenRouter said | Yes |
| 413 | Too large to send | "The request is larger than OpenRouter takes" | No |
| 429 | A limit of requests, OpenRouter's or the provider's; `Retry-After` when given | Passed on with `Retry-After` | Yes |
| 502, 529 | The model is down or overloaded | As OpenRouter said | Yes |
| 503 | No provider meets the request's routing | "No provider of <model> serves it with data_collection deny: pick another model, or allow it on the Providers page (o)" when the record denies, answered 403 (decision 0115: OpenCode retries any 503); else as OpenRouter said | No, with `deny`; else yes |

- **Records.** A request's record names the provider (`cloud openrouter`), the model id sent, its workspace (§9), the
  reach, its usage, its `cost` (with how it was known), its `generation`, and any refusal in OpenRouter's words. The
  census of decision 0096 is made as for an engine, and keeps no text of the prompt when records are off. Keys are never
  kept (§5).
- **Completion and vision** stay with this machine's engines (§7): an infill request for a role whose slot runs a cloud
  model is refused (`no_engine`), as design 0015 §10 says.

## 9. Where a workspace's requests may go

*Approved 2026-10-20 (the owner's answers: 2; decision 0103); how it asks is Claude's call (decision 0112).*

- **Agreed once, per provider.** Adding OpenRouter asks the owner once to agree that prompts, and the files and
  command output the agent reads, go to OpenRouter and the model's provider (§14's agreement screen, or `clank endpoint
  add openrouter`, which asks; `--agree` for a script). The agreement is the record's `agreed`; without it nothing
  loads from that provider, and a request already in flight is the last to go.
- **A bound per workspace** (decision 0075's, built for the cloud). Each workspace record gains `models`, the farthest
  its content may go: `this-machine` (every workspace, new or existing, until the owner says otherwise) or `cloud`
  (0015 adds `my-servers` between them); and `cloud_answered`, when the owner last answered the cloud question for it.
- **A key per workspace** (decision 0075, design 0015 §10). Each workspace's OpenCode sends a key of its own, in place
  of `local` (`agents/adapters/opencode.py:170`), and so does Clank's MCP server in its container (`CLANK_GATEWAY_KEY`):
  the workspace's name at the gateway. The gateway's service makes it (the secret `workspace/<id>/gateway-key`) and
  keeps its SHA-256 with the workspace and its bound in the gateway's own state (its first migration); the agents
  component gets the key when it writes OpenCode's configuration, and the workspaces component gives each bound at
  every change and at each start of the service, so no component cycle forms (decision 0019). The routes the gateway
  follows carry each key's hash, its workspace, its bound, whether it was answered, and the question open for it.
- **Asked once per workspace** (decision 0112):
  - **Before its agent starts** with a cloud model in the main slot (This folder's `a`, `clank work`, `clank code`,
    VS Code's open, a session the phone starts, a flow's run): a question, "Let <workspace>'s agent use the cloud
    model?", answered in the console (a window), in the terminal before OpenCode takes it (`clank work`), on the phone
    and in VS Code. Its detail says what goes (every request of its sessions: the owner's messages, what the agent
    reads of the folder, command output) and what never does (§10). A workspace that existed before the provider was
    agreed says so first: its earlier sessions and its folder may hold research; a workspace made for the purpose is
    recommended.
  - **At the gateway**, a request from a workspace not yet answered (the main slot switched to the cloud while its
    OpenCode ran, or a flow's box): held as a paused request is held (decision 0055: a 200 with comment lines for a
    stream, nothing for a whole one), while the question is asked on every client. *Allow* lets it go on the same
    stream; *keep local* refuses it.
  - Its answers: **allow** (the record's `models` becomes `cloud`), **keep local** (`models` stays, `cloud_answered`
    is set, and the workspace is not asked again). It expires after 30 minutes as *keep local this time*: refused, and
    asked again at the next start. Every answer is recorded with who gave it, from which client (design 0002 §2.5).
- **Refused, after a *keep local***: 403 `model_send_denied`, "<workspace> is kept on this machine. Allow the cloud
  for it on This folder (u), or clank workspace allow FOLDER --cloud; or load a local model". OpenCode shows it as an
  error and stops the step; the owner sends the message again after allowing.
- **A request with no known key** (a script, an OpenCode started before workspace keys) goes to this machine only: to
  the cloud it is refused, "this OpenCode was started before Clank named workspaces to the gateway: leave it, and
  start it again here".
- **Changing it later**: This folder's `u` (allow, or keep local again) and `clank workspace allow FOLDER --cloud |
  --local`; narrowing applies to the next request.
- **While the service does not answer**, a cloud request waits up to the hold (300 s) for the service's routes to be
  fresh again (at most three seconds old), then is refused (`service_silent`): decision 0021 decides `model.send` to a
  third party at the moment of use, and a service starting again takes seconds.

## 10. Local-only content never reaches the cloud: how it is enforced

*Approved 2026-10-20 for building, the owner's go-ahead (Claude's call, decision 0111).*

What the owner's answer names: **Notion pages** (design 0010), and **MCP servers marked local**. An MCP server's record
(`config/mcp-servers/<name>.json`, `tools/kinds.py:14`) gains `local_only` (a boolean). When the owner agrees to a
provider, every MCP server already added is marked local (they were added when everything stayed here; the agreement
screen lists them, and Space unmarks one); one added later asks (`clank mcp add … --local | --cloud-ok`, the console's
form). Clank's own Notion tools are always local, whatever is set.

It is kept from the cloud in four places, the last three at the gateway (decision 0020: where it can be stopped):

1. **The agent's configuration.** A workspace allowed the cloud gets no MCP server marked local in OpenCode's
   configuration, and Clank's MCP server in its container lists no Notion tools (`CLANK_NOTION=off`), from OpenCode's
   next start; This folder lists them as "held back: local only".
2. **Notion at the gateway.** `/notion/...` answers only a request with a known workspace key whose bound is
   `this-machine` (decision 0075's (i)); a workspace allowed the cloud reads no Notion page, whatever its slot runs now
   (403, `notion_denied`, saying so).
3. **The tools passed on.** Before a request goes to the cloud, the gateway removes from its `tools` each tool of a
   server marked local (OpenCode names an MCP tool `<server>_<tool>`, its unsafe characters made `_`:
   `agents/adapters/opencode.py:72, 102-104`) and Clank's Notion tools (`clank_notion_*`), so the cloud model is never
   offered them; the record's notes count them. The agents component gives the gateway these names at each start of
   the service and each change of an MCP server's record.
4. **A session that used one.** Before a request goes to the cloud, the gateway refuses it (403, `local_only`) when
   its messages hold a call to such a tool, or when its session, or the session that started it, is marked: the gateway
   marks a session (by `X-Session-Id`, and `x-parent-session-id` for a subagent) the first time it sees such a call in
   one of its requests, whatever slot serves it, and keeps the marks in `state/local-only.json`, so a compaction that
   folded the call into a summary does not clear it. The words: "this session used Notion (or <server>, marked local),
   which never goes to the cloud model: start a new session to use it, or load a local model".

What this cannot see, and says: what the agent wrote into the folder's files from a Notion page or a local server's
answer goes with the folder. The workspace's question (§9) says so when its sessions have used one.

## 11. Cost: each request, session and flow, and the limits

*Approved 2026-10-20 (the owner's answers: 3; decision 0104).*

- **Each request** shows its cost in US dollars, from OpenRouter's own figure (§12): the Requests page (F7) on each
  line and in its details (with the tokens: in, cached, out, thinking), the Monitor's Now and a step's details.
- **Each session** shows what it cost so far, its requests and its subagents' together: the Monitor's session line
  ("this session: $0.84 · 142 requests"), This folder's "Then work", the phone's session, VS Code's tooltip.
- **Each flow** shows what each box cost and the flow's total: the Flow view's boxes and its "Models in this flow"
  panel, `clank flow show`, the phone's flow. A box's cost is its sessions' (design 0013 §5).
- **Today and this month**: Home and the console's header ("cloud $0.42 today · $3.10 this month"), the Providers
  page, the phone, VS Code, `clank cost`.
- **Estimates are labeled.** A cost not yet known exactly (a stream cut short, §12) shows as an estimate ("≈ $0.03")
  until it is.
- **The limits, optional**: a daily and a monthly limit in US dollars, in `config/cost.json` (kind `cost`: `day_usd`,
  `month_usd`, each empty for none; `warn_at`, 0.8). Days and months are this computer's (decision 0108). Set in Add a
  model (§14), on the Providers page (`L`), with `clank cost limit`.
- **At 80%** of a limit, one notice on every client and the phone ("cloud: $4.02 of today's $5.00").
- **When a limit is reached, cloud requests pause**: the gateway holds each new cloud request before it is sent, as a
  paused session's are held (decision 0055: a stream kept alive with comment lines, `: held by Clank: the cloud
  spending limit is reached`), and the service asks the owner, on every client and the phone: "Cloud spending reached
  today's limit of $5.00 ($5.02 spent): raise it?", with *raise today's limit to $10.00* (twice the limit), *raise it
  to …* (an amount), and *keep paused*. A raise is a change of `config/cost.json`, recorded with who made it, and the
  held requests go on at once on their streams. A daily pause also ends when the day does, a monthly one when the month
  does. Requests in flight when the limit is reached finish, so the spending can pass the limit by what they cost; the
  question says by how much.
- **What the owner sees while paused**: the console's header and Home ("cloud paused: today's limit reached · L
  raise"), the Monitor's Now ("held: the cloud spending limit"), This folder, the phone's banner with the question, VS
  Code's status bar item, and OpenCode's own spinner, which keeps waiting.
- **OpenRouter's own limits** stay the owner's too: a key's own limit on openrouter.ai refuses with 402, a budget with
  403 (§8). Add a model recommends one, as OpenRouter does.

## 12. How cost is known and kept

*Approved 2026-10-20 for building, the owner's go-ahead (Claude's call, decision 0108).*

- **Exact, from OpenRouter.** Each answer's `usage.cost` (§3), in its last message, is the request's cost; the gateway
  keeps it as `{"usd": 0.0123, "how": "usage"}`.
- **A stream cut short** (the client left, the loop guard stopped it, the connection dropped, a read timeout) has no
  usage. The gateway keeps the chunk's `id` (`generation`); the service asks `GET /generation?id=…` with the key 10
  s, 60 s and 5 min later and keeps its `total_cost` (`"how": "generation"`). Until then, and if it never comes, an
  estimate: the tokens counted (the census's characters at the model's plain estimate, decision 0087, and the answer's
  pieces) at the model's prices from the route (`"how": "estimate"`), labeled everywhere.
- **The gateway's spool.** Each cloud request that ends appends an entry to `state/cloud-spool.jsonl` (its sequence
  number, time, request id, session, parent session, workspace, preset, model, tokens, cost and how, generation), so a
  restart of the gateway loses none. `GET /spend?after=<n>` (the local token) answers the entries after `n`, and
  forgets those up to `n`.
- **The service keeps them**: every two seconds the gateway component's service takes the new entries into its own
  table (`cloud_costs`, the gateway's first migration, beside the workspace keys of §9), idempotent by the gateway's run
  and sequence, and answers every total from it: today, this month, by session (with its subagents), by workspace, by
  flow (the flows component names its boxes' sessions). The runtime's own requests (a load's health, a check, a test)
  are kept by the runtime with their launch or check, and counted in the totals.
- **The limit at the gateway.** The routes carry today's and this month's spending as the service has it, the limits,
  and the last sequence it took; the gateway adds its entries not yet taken, so a burst between two takes is counted.
- **Days and months** are this computer's local ones, as the owner lives them; OpenRouter's own figures (`GET /key`)
  count UTC days, and the Providers page shows them as OpenRouter's, beside Clank's.
- **Events**: `gateway.cost` (the totals, at most every five seconds while they change), `gateway.limit_warned`,
  `gateway.limit_reached`, `gateway.limit_raised`. Each request's cost is a row, not an event.

## 13. What the Monitor shows of a cloud model

*Approved 2026-10-20 for building, the owner's go-ahead.*

The Monitor reads every figure from the route of the slot a session's requests reach (design 0012 §4, decision 0067).
A cloud route carries the same two declarations an engine's does:

- **Its context facts** (`ContextFacts`, `runtime/adapters/engine.py:174-196`), from the adapter and the model's line:
  `window` and `output` (§7); `thinking_budget` none (an effort is not a budget); `exact` none (the provider attends
  the whole window, as far as anyone outside it knows); `on_gpu` false; `counts_tokens` false; `one_conversation` false
  (OpenRouter's providers keep no single conversation as KVMem does); `fields` (`prompt`: `usage.prompt_tokens`,
  `output`: `usage.completion_tokens`, `cached`: `usage.prompt_tokens_details.cached_tokens`); `full`, its words once
  checked (§6); `source`, "OpenRouter's list, read 09:14".
- **The model's facts**: its id and name; no template facts and no calibration (Clank's catalog does not hold it), so
  the parts are estimated at Clank's plain default and say so (decision 0087), shared out to OpenRouter's exact
  `prompt_tokens` (decision 0051).
- **What does not apply, said in its place**: "On the GPU exactly" ("the model runs at OpenRouter's provider, not on
  this machine"), the GPU line, whose conversation the engine holds (design 0012 §3), and the engine's timings.
- **What a cloud model adds**: the cost of the step, of the session and of the flow (§11), and the share of the prompt
  read from the provider's cache (`cached_tokens`), which is cheaper (`pricing.input_cache_read`).
- The compaction line, the margin (decision 0089) and the overflow answer (decision 0090) are the same: the window is
  the route's.

## 14. The first run: Add a model

*Approved 2026-10-20 (the owner's answers: 4; decision 0105).*

**When it opens.** The service answers `GET /runtime/usable`: a model is usable when the main slot is ready, or a
preset for it can load now (an engine preset whose engine is installed and whose model is downloaded on a host; a
cloud preset whose provider is agreed and whose key is set). When none is, `clank` and `clank console` open on **Add a
model** in place of This folder or Home; a page named on the command line opens as asked, and the header says "no model:
Add a model". It is also in the menu, and `a` on the Providers and models page (0) opens it.

Each screen is a panel of the page, one at a time; Esc goes back one screen, and from the first leaves for This folder
with the header still saying so. What a new user types: `c`, Enter, `y`, the key (pasted), Enter, a search or arrows,
Enter, Enter.

1. **Add a model.** "How should Clank run its model?" **Cloud** (`c`): "a model at OpenRouter, with your key; no GPU
   needed; each request costs money, shown as it goes". **Local** (`l`): "a model on this computer's GPU", with this
   machine's GPU and memory from its profile.
2. **Cloud: the provider.** OpenRouter, the one choice for now ("one key, the major models behind it; other providers
   later"), with where to get a key (openrouter.ai, Keys). Enter.
3. **What goes to OpenRouter.** Once, for the provider: what goes (each request of an agent's session: your messages,
   what it reads of the folder, command output, its instructions), where (OpenRouter, then the model's provider;
   OpenRouter does not log prompts by default; Clank asks only for providers that do not keep data, `data_collection
   deny`, which `o` changes), what never goes (Notion pages; the MCP servers marked local, listed here, every one
   already added marked, Space to unmark; a workspace you have not allowed), that each workspace asks once, and that
   every request costs money from your OpenRouter credits. `y` agrees (the record is written with `agreed`), `n` goes
   back.
4. **Your key.** A hidden field ("paste your OpenRouter key"): dots as it is pasted, then its last four. Enter: Clank
   asks OpenRouter (`GET /key`); accepted, the line says its label, its own limit and what is left, and the key is
   kept; refused, OpenRouter's words and what to do, and the field is cleared. A key with no limit of its own gets
   OpenRouter's advice to set one.
5. **The model.** OpenRouter's live list of models that take tool calls, read with the key: by default most used
   first (`sort=most-popular`; OpenRouter refuses `category=programming` beside `supported_parameters`, §18); `/`
   searches by name or id; `s` sorts (most used, price, window, newest); `f` shows the free ones (their limits said).
   Each line: name, window, price in and out per million tokens, thinking, images; under the list, the highlighted
   model's description's first sentence, its most output, and its retirement date if it has one. Enter picks.
6. **Its settings**, a form already filled: its title ("cloud: Example Coder"), its context (the model's window; "a
   smaller one makes OpenCode compact sooner and each request cost less"), its output (16,384 or the model's most), its
   thinking effort (the model's own), and the cost limits, a day and a month (empty: none; "OpenRouter can limit the key
   too"). Enter takes it.
7. **The test.** The preset is written; when the main slot runs nothing, it is loaded, and the load's health is the
   one short request (§7); when a local model runs, the test is the check's short request, and then "load it now? This
   stops <local model> in the main slot" (`y`/`n`). Either way the screen shows the answer, its time and its cost ("OK
   in 0.9 s, $0.00002"), or what failed and what to do, with `b` back to the model and `k` back to the key.
8. **Ready.** "cloud: Example Coder runs in the main slot." What working needs next: Docker for a workspace's
   container (its state, as This folder shows it). Enter goes to This folder, where `a` starts the agent (it asks the
   workspace once, §9).

**Local** (`l`) opens today's setup for this machine, on one screen: Clank's presets for the main slot, each with its
fit on this GPU and what it needs here (`runtime/needs`: its engine installed or Clank's recipe for it; its model's
files downloaded, and their size); Enter on one does what is missing in order (install by the recipe, download, load),
each asked first and followed on the screen as the Providers page's `i` and `d` and This folder's `l` do today. The
fuller guide (the machine checked, recommendations, other computers) is M10's (design 0001 §7.3).

**A computer without Docker.** The model works without it, but the agent runs only in a workspace's container. Ready
(screen 8) says so in its line for Docker: not installed, with where to get Docker Desktop (Windows, macOS) or Docker
Engine (Linux, design 0014); installed and stopped, with `s` to start it, as This folder does. This folder then goes on
from there. Nothing in Add a model needs Docker.

## 15. The Providers and models page, and the other pages

*Approved 2026-10-20 for building, the owner's go-ahead.*

- **Providers and models (0)** gains a panel **Cloud**: each endpoint record: its title, its agreement (when, by whom),
  its key (set, its last four, its label; or "no key"), its provider options (`data_collection`), OpenRouter's account
  line (§6: the key's limit and what is left, OpenRouter's count today and this month), Clank's spending today and
  this month against the limits, its last check, and its presets. Keys: `a` add a cloud model (Add a model, from screen
  2, or 5 when the provider is there), `k` set the key again (the hidden field), `c` check (§6), `o` its options, `L`
  the cost limits, `r` remove the provider (asked first; refused while used).
- **Presets (9) and the picker** show a cloud preset's provider as `cloud openrouter` and its prices; a switch to it is
  a switch like any (§7).
- **Models (8)** shows the main slot's cloud model: its provider, its window, its last health, "not reached since …".
- **This folder (F4)** shows the model's line with "cloud", the workspace's bound ("this workspace: may use the cloud"
  or "kept on this machine"), `u` to change it (asked first; `c` stays VS Code's), the MCP servers held back as local
  only, and the cost of its sessions today.
- **Requests (F7)** shows each request's cost, provider and model, and a refusal's words.
- **Home (1)** and the header show cloud spending today and this month, a pause, and its key.
- **The Monitor (F10)**: §11 and §13. **The Flow view**: each box's cost, the flow's total, and a box waiting for the
  workspace's answer.
- **MCP servers (F3)** shows each server's mark (local only, or may go to the cloud), with a key to change it.

## 16. The commands

*Approved 2026-10-20 for building, the owner's go-ahead.*

```
clank model add                                    the console's Add a model, in the terminal: cloud or local, step by step
clank endpoint add openrouter [--agree]            the record from the adapter's template, after the agreement (asked)
clank endpoint key openrouter [--stdin]            asked without echo; checked with OpenRouter before it is kept
clank endpoint list | show openrouter              show: the record, the key's last four and label, the account, the last check
clank endpoint models openrouter [--search TEXT] [--sort most-popular|price|context|newest] [--free] [--all]
clank endpoint preset openrouter MODEL [--title T] [--context N] [--output N] [--reasoning EFFORT]   written, then tested
clank endpoint check openrouter [--model MODEL]    §6
clank endpoint remove openrouter                   with its key; refused while a slot runs it or a preset names it
clank model load "cloud: Example Coder"            as for any preset (§7)
clank workspace allow FOLDER --cloud | --local [--yes]       a workspace's bound, asked first unless --yes (§9)
clank mcp local NAME [--off]                       mark an MCP server local only, or not (§10)
clank cost [--today | --month | --sessions | --flows] [--json]
clank cost limit [--day USD|none] [--month USD|none]
```

- Each is a client of the API (design 0002 §2.15), with `--json`. A key is never an argument (§4).
- `clank model add` asks what Add a model asks, in the same order, in the terminal; the key is read without echo.
- `clank work` with no usable model says so and how to add one ("clank, or clank model add"), and asks the workspace
  once (§9) in the terminal before OpenCode starts.

## 17. The phone and VS Code

*Approved 2026-10-20 for building, the owner's go-ahead; revised after approval 2026-10-21: the subsection For
the phone app, at the owner's instruction that the phone app (an installed web app with live updates and push
notifications, designed separately) be as easy as possible to build later; its phone part left for the phone's
redesign (the owner, 2026-10-21).*

- **The phone** (design 0005): its model line says "cloud · OpenRouter · Example Coder"; its overview gains the
  spending today and this month against the limits, and a pause's banner; each session shows its cost, each flow its
  boxes' and its total; the workspace's question and the limit's question are Clank's questions, answered there like
  any (design 0002 §2.5: a paired device answers questions). The phone never sets a key, adds a provider or writes a
  setting directly: raising a limit from the phone is the question's answer, which says exactly what it does.
- **VS Code**: the status bar's model item says "cloud" and today's spending in its tooltip, and the pause; *Clank:
  Switch model* lists cloud presets as `cloud openrouter · example-vendor/example-coder`; the workspace's question and
  the limit's question come as its questions do (`vscode/src/core/controller.ts:167-180`); a refusal reaches the
  agent's terminal in OpenCode's own words.

**For the phone app** (revised after approval, 2026-10-21). The phone is being redesigned apart; what it needs of the
cloud is in the service's API and events, which every client reads alike, and nothing of it is the phone's alone:

- **Facts, never recomputed by a client.** `GET /gateway/cost`: today and this month in this computer's days, each
  with its bounds (as Clank's times), its local name (`2026-10-21`, `2026-10`), the part still an estimate, and its
  words ("$0.42 today"); the currency, the zone, the limits, a pause and a warning with their words, and the newest
  revision; `?workspace=` adds that workspace's own today and this month. `GET /gateway/cost/sessions` and `/gateway/cost/requests`: each row with its words and its `rev`; `after=`
  gives only what changed since, the header `X-Clank-Revision` the newest. A flow's cost is in its view (`GET
  /flows/{id}`), each box's too. The provider (`GET /runtime/endpoints/{id}`: its agreement, its key by its last four
  only, its last check), its account (`…/account`), its live list of models (`…/models`), the presets with their
  provider and prices (`GET /runtime/presets`), whether a model is usable (`GET /runtime/usable`), each workspace's
  bound and open question (`GET /workspaces`).
- **Every change is an event** on the one stream (`GET /events`), its summary a short title in Clank's own words (a
  provider, a model, a workspace, a flow, a box, an amount; never prompt or file text), and those that need the owner
  carry `attention` (decision 0113): `question.asked`, `gateway.limit_warned`, `gateway.limit_reached`,
  `gateway.cloud_refused` (a refusal by Clank or by the provider: the key, credits, a budget, the model, a limit of
  requests, the data policy). The others: `secret.set` and `secret.removed` (the key), `runtime.endpoint_added`,
  `_changed`, `_removed`, `_checked`, `runtime.slot` (a model loaded or switched), `settings.changed` (a cloud preset
  written, a limit set), `gateway.cloud_wanted`, `workspaces.cloud_answered` (a workspace allowed, kept local, or
  narrowed), `gateway.cost`, `gateway.limit_raised`.
- **The owner's answers are the kernel's questions** (design 0002 §2.5), answered with `POST /questions/{id}/answer`
  from any client: the workspace's ("Let <workspace>'s agent use the cloud model <title>?": `allow`, `local`), and the
  limit's (`double`, `raise`, `keep`), whose `raise` declares the number it takes, its bounds and its unit (decision
  0114), so a client draws a number field from the declaration alone; both `high` urgency.
- **Every action is one route**, with the same checks and the same refusal words for every client: `POST
  /workspaces/{name}/cloud` (allow, or keep local), `POST /workspaces/{name}/cloud/ask` (before an agent starts), `PUT
  /gateway/cost/limits`, `POST /runtime/slots/main/switch` (a cloud preset like any). Adding a provider, setting a key
  and writing a preset stay the console's and the commands' (a phone never sets a key, as this section says above).

## 18. Tests, the fake OpenRouter, and the checks owed with a real key

*Approved 2026-10-20 for building, the owner's go-ahead.*

- **No network in tests.** `tests/fakes/openrouter.py`, a fake server of OpenRouter's routes (`/api/v1/models`,
  `/key`, `/chat/completions` whole and streamed, `/generation`), built from the shapes of §3 and marked so, plays
  what a test asks: a made-up key it accepts (`made-up-openrouter-key`, never `sk-…`, so the repository's secrets check
  passes), a refused key, 402, 403, 404, 429 with `Retry-After`, 503, a stream with comment lines, thinking as
  `reasoning`, a tool call, usage with `cost`, a mid-stream error, a stream cut before its usage, and a silence for the
  read timeout. The gateway's and the runtime's tests point the endpoint's URL at it (a test's own record; the rule
  that fixes the URL for the adapter has a test switch, as the runtime's other test points do).
- **The contract test**, `tests/contract/test_endpoint.py` (design 0015 §14), runs over every HTTP recording of every
  endpoint adapter: first the fake's documented shapes, then the owner's recording.
- **The recording**, after the owner's key: `tools/capture_endpoint.py` (design 0015 §14, built for a URL only) sends
  Clank's fixed made-up requests and writes `tests/fixtures/openrouter/<date>/http.json` with the key and the account's
  label replaced by made-up ones; the repository's checks learn to accept `http.json` for an endpoint adapter.
- **Real tests**, `tests/real/test_openrouter.py`, under their own marker (`openrouter`), never in CI: the key from an
  environment variable typed for the run (`CLANK_TEST_OPENROUTER_KEY`), made-up prompts only, the cheapest model that
  takes tools.

**Checks owed with a real key** (the owner, 2026-10-21; each a line of the capture or a real test):

1. Whether `GET /models` needs the key; the order of `category=programming&sort=most-popular`. *Answered from its
   public list, 2026-10-28:* it needs no key; it refuses `category` beside `supported_parameters` (400, "Cannot provide
   both category and supported_parameters"), so the list Clank asked for by default was refused; `category=programming`
   alone gives the first twenty; `sort=most-popular` orders every model by use. Clank asks `supported_parameters=tools`
   with `sort=most-popular`. The list also showed two lines Clank now reads: a `context_length` of 0 beside the
   provider's real window (read as none), and a router priced per request, `-1` (left out).
2. That a stream's chunk `id` is the `gen-…` id `GET /generation` takes, and how soon it answers.
3. A prompt over a model's window: its status and words (`says_full`), and whether OpenCode compacts on them as they
   are.
4. `delta.reasoning` in a thinking model's stream; whether models of the main families (Anthropic, Google, OpenAI,
   an open-weight one) take a session's tool calls across turns with only `reasoning_content` sent back.
5. A 402's body (`openrouter_credits`, `openrouter_key_limit`), and a 403 from a key's budget.
6. A stream's error `code`: a number or a word.
7. `usage.cost` in the last message of a stream and of a whole answer; whether it is there when the stream is stopped
   (expected not, §12).
8. `data_collection: deny`: which models of the list it refuses (503), and its words.
9. `max_tokens` accepted as sent by OpenCode; `x-session-id` raising `cached_tokens` on a session's later requests.
10. `GET /key` with a key without a limit: `limit` and `limit_remaining` both `null`.
11. Comment lines and OpenRouter's keep-alive through the gateway to OpenCode, unharmed.
12. Whether OpenRouter applies any transform that shortens a long prompt by default for some models, which would make
    the Monitor's counts wrong (the documentation read says nothing of one).

## 19. Build steps

*Approved 2026-10-20 for building, the owner's go-ahead.*

Two plans, built in parallel against one interface: [plan s34](../plans/s34-cloud-service-and-gateway.md) (the
service and the gateway: the record, the key, the adapter, presets and the slot, the gateway's forwarding, workspace
keys and the question, local-only content, cost and limits, events) and [plan
s35](../plans/s35-cloud-console-cli-phone-vscode.md) (Add a model, the Providers page, the questions, cost on every
page, the commands, the phone, VS Code). Plan s34 holds the interface (its routes and payloads); plan s35 builds against
a fake of it until s34's routes land. Each task is one commit that starts with a failing test (design 0001 §8.6).

## 20. What this design does not cover

*Approved 2026-10-20 for building, the owner's go-ahead.*

- **Other providers**: OpenAI's, Anthropic's and Google's own APIs, and design 0015's `openai-compatible`; the adapter
  kind is ready for them (decision 0102).
- **The cloud beside a local model** (decision 0077's (b)): a cloud model in a slot of its own, reached by a second
  role, so KVMem keeps serving research while a scratch workspace uses the cloud. With this design, loading the cloud
  model stops KVMem, and a workspace kept local is refused meanwhile (decision 0107).
- **Completion and vision from the cloud**: `fast` and `vision` stay on this machine.
- **Bring your own provider key at OpenRouter (BYOK)**, OpenRouter's guardrails and budgets set from Clank, the
  account's balance (a management key, §3), other request options (`transforms`, `models` fallbacks, `max_price`).
- **`reasoning_details` kept across tool calls** for models that need them (§8): after the real check of §18, its own
  decision if needed.
- **The setup guide's rest** (M10): the machine checked first, recommendations, other computers, tools.
- **Cost in another currency**; OpenRouter's fee for buying credits.
- **The flows routes** (`/flows/...`) keep their rule (design 0013 §9); a known workspace key is not required there.
- **The tunnel and the cluster**: design 0015.

## Decisions to record

- [0102](../decisions/0102-the-first-cloud-provider-is-openrouter.md): the first cloud provider is OpenRouter, alone
  for now (the owner's).
- [0103](../decisions/0103-the-cloud-is-agreed-once-and-asked-once-per-workspace.md): agreed once per provider, asked
  once per workspace, existing workspaces local, Notion and local MCP servers never (the owner's).
- [0104](../decisions/0104-cloud-cost-is-shown-with-an-optional-limit.md): each request, session and flow shows its
  cost; an optional daily or monthly limit pauses the cloud until raised (the owner's).
- [0105](../decisions/0105-with-no-usable-model-the-console-opens-on-add-a-model.md): with no usable model, the
  console opens on Add a model (the owner's).
- [0106](../decisions/0106-the-service-hands-the-cloud-key-to-the-gateway.md): the service hands the key to the
  gateway, behind its local token, while a cloud model is loaded (Claude's call).
- [0107](../decisions/0107-a-cloud-model-serves-the-main-slot.md): a cloud model serves the main slot in an engine's
  place (Claude's call).
- [0108](../decisions/0108-cloud-cost-is-openrouters-own-figure-kept-by-the-service.md): cost is OpenRouter's own
  figure, kept by the service from the gateway's spool, in this computer's days and months (Claude's call).
- [0109](../decisions/0109-what-clank-sends-openrouter.md): what Clank sends OpenRouter (Claude's call).
- [0110](../decisions/0110-the-gateway-never-sends-a-cloud-request-again.md): the gateway never sends a cloud request
  again; refusals pass on with their status, in words that say what to do (Claude's call).
- [0111](../decisions/0111-local-only-content-is-kept-from-the-cloud-in-four-places.md): local-only content is kept
  from the cloud in four places (Claude's call).
- [0112](../decisions/0112-a-workspace-is-asked-before-its-agent-starts-and-at-the-gateway.md): a workspace is asked
  before its agent starts, and a request that reaches the gateway first is held while it asks (Claude's call).
- [0113](../decisions/0113-an-event-says-whether-it-needs-the-owner.md): an event type says whether its events need the
  owner's attention, and each event carries it (Claude's call, on the owner's instruction of 2026-10-21; §17).
- [0114](../decisions/0114-a-questions-option-may-ask-for-a-number.md): a question's option may ask for a number, with
  its bounds and unit (Claude's call, on the owner's instruction of 2026-10-21; §11, §17).
- [0115](../decisions/0115-a-refusal-not-to-retry-is-never-answered-with-a-status-opencode-retries.md): a refusal
  OpenCode must not retry is never answered with a status it retries by (Claude's call, at the review of plan s34;
  §8).

## Revision log

- **2026-10-20, written.** From the owner's request and four answers of the same day, and OpenRouter's documentation
  read that day.
- **2026-10-21, §17 revised after approval:** the subsection For the phone app, at the owner's instruction that the
  phone app be as easy as possible to build later: the facts, events, questions and routes it uses, all the service's;
  decisions 0113 (an event says whether it needs the owner) and 0114 (a question's option may ask for a number) with
  it.
- **2026-10-21, §8 revised after approval:** the review of plan s34 found OpenCode retrying OpenRouter's 503 under
  `data_collection: deny` without end; such a refusal is answered 403 (decision 0115). And a `provider` object the tool
  sent dropped the record's `deny`: the record's data policy is now merged into it, the stricter word kept (§6, §8).
- **2026-10-28, §14 and §18 revised after approval:** OpenRouter's public list refused the default models query
  (`category` beside `supported_parameters`): the most used now come from `sort=most-popular` over the tool models;
  §18's first check is answered, and the fake refuses that query as OpenRouter does.
