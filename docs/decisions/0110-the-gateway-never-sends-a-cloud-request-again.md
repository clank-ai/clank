# 0110. The gateway never sends a cloud request again by itself; refusals reach the tool with their status, in words that say what to do and never OpenCode's retry words

- Status: Proposed (Claude's call); its "with their status" superseded in part by
  [0115](0115-a-refusal-not-to-retry-is-never-answered-with-a-status-opencode-retries.md): a refusal not to be
  retried is never answered with a status OpenCode retries by
- Date: 2026-10-20
- Decided by: Claude, writing [design 0016](../design/0016-cloud-models.md) §8

## Context
- Today the gateway sends a request again, once the slot is served again, when an engine broke off before its first
  token (`again()`, `clank/components/gateway/server.py:382-401`): a crashed engine never answered it.
- A cloud request that broke off may have reached the provider and been billed; OpenRouter bills a stream stopped
  early in full for providers that do not support stopping (its streaming page).
- OpenCode 1.19 retries a 429 or a 5xx, and any error whose words hold one of its retry patterns ("rate limit",
  "exhausted", "unavailable", …; decision 0040); it ends the run on any other. The gateway already has `_unretried` to
  word a refusal so OpenCode does not retry it.
- OpenRouter's refusals: 401 (key refused), 402 (credits or the key's limit), 403 (budget, guardrail, moderation), 404
  (no such model), 429 (with `Retry-After`), 502, 503 (no provider meets the routing), and others (design 0016 §3).

## Decision
- The gateway never sends a cloud request again on its own. A connection refused or lost before any answer ends with
  502, `cloud_unreachable`, which OpenCode retries by its own rule; each try is recorded with its cost.
- A refusal reaches the tool with OpenRouter's status, its message OpenRouter's words followed by Clank's words of what
  to do (design 0016 §8's table). For the statuses OpenCode must not retry (400, 401, 402, 403, 404, 413, and 503 when
  the provider's record denies data collection), the words pass through `_unretried`, so a payment refusal never loops.
- A context full is answered as decision 0090 says, once the adapter knows OpenRouter's words for it.
- An answer silent for the endpoint's read timeout ends with `cloud_silent` and is never sent again (design 0015 §8).

## Alternatives considered
- **Send again before the first token, as for engines**: a billed request could be billed twice, unseen.
- **Pass OpenRouter's words unchanged**: OpenCode would retry a 402 whose words held "exhausted" without end, and a new
  user would not learn what to do.
- **Replace OpenRouter's words with Clank's**: the provider's own words are what the owner can search for.

## Consequences
- A dropped network costs the owner one step of OpenCode, retried by it, never a hidden second charge.
- Every refusal names what to do, in the console's Requests page and in OpenCode alike.
