# 0115. A refusal OpenCode must not retry is never answered with a status it retries by

- Status: Proposed (Claude's call, at the review of plan s34); supersedes in part
  [0110](0110-the-gateway-never-sends-a-cloud-request-again.md) (a refusal reaches the tool with its status)
- Date: 2026-10-21
- Decided by: Claude, fixing what the review of [plan s34](../plans/s34-cloud-service-and-gateway.md) found

## Context

- Decision 0110 passes a provider's refusal to the tool with the provider's status, and words it through `_unretried`
  for the statuses OpenCode must not retry, so a payment refusal never loops.
- OpenCode 1.19 retries a 429 or a 5xx whatever the words say (decision 0040). OpenRouter answers 503 when no provider
  of a model meets the request's routing; with the record's `data_collection: deny`, no retry can change that, yet the
  503 made OpenCode retry it without end, each try a request the owner never meant.

## Decision

- A refusal OpenCode must not retry (the adapter's `retried` false) whose status is one OpenCode retries by (429, 500,
  502, 503, 504, 524) is answered 403, with the same code (`data_policy`), the same words and `Retry-After` when given.
  Today that is OpenRouter's 503 under `data_collection: deny`.
- The request's record keeps the provider's own status (503), so the Requests page says what the provider said.
- Inside a stream whose 200 has gone out, the refusal is worded not to be retried, as before (decision 0110).

## Alternatives considered

- **Keep the 503 and word it**: OpenCode reads the status first; its words never stop the retry.
- **400**: OpenCode reads some 400s as a full context (decision 0090); 403 says "refused" and nothing else.

## Consequences

- A model no provider serves under the data policy ends the run at once, with words that say to pick another model or
  allow it on the Providers page.
- Any later refusal of the same kind (not to be retried, under a retried status) is answered 403 without a new rule.
