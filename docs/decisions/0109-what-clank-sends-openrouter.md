# 0109. What Clank sends OpenRouter: the request as the tool sent it, the model's id, no data-keeping providers by default, the session's id for its cache, no attribution

- Status: Proposed (Claude's call)
- Date: 2026-10-20
- Decided by: Claude, writing [design 0016](../design/0016-cloud-models.md) §8, from OpenRouter's documentation read
  2026-10-20

## Context
- The gateway builds its own request for each provider (design 0001 §6.1, step 4), and passes the tool's request as
  sent but its model name (design 0015 §8).
- OpenRouter's `provider.data_collection: "deny"` routes only to providers "which do not collect user data", and a
  request no such provider serves is refused (its provider routing page). OpenRouter itself does not log prompts by
  default (its FAQ).
- Its `session_id` field, or the `x-session-id` header, "serves as the sticky routing key for prompt cache hits"; OpenCode
  already sends `X-Session-Id` to the gateway with each request.
- Its attribution headers (`HTTP-Referer`, `X-OpenRouter-Title`) put an app in OpenRouter's public rankings; they are
  optional for the API.
- The owner's rule is that research stays local; what goes to the cloud goes only with the workspace's consent
  (decision 0103).

## Decision
- The request as OpenCode sent it, its `model` the id OpenRouter lists.
- `provider.data_collection` from the provider's record, **`deny` by default**, and `zdr` when the owner sets it,
  unless the tool sent a `provider` of its own; the Providers page's `o` changes it.
- The preset's thinking effort as `reasoning.effort` when it is not `default` and the tool sent none.
- `x-session-id` with OpenCode's session id, for OpenRouter's prompt cache.
- **No attribution headers**, and no `user` field.
- Every change is listed in the request's record, as an engine's translation is.

## Alternatives considered
- **`data_collection` left as OpenRouter's default (`allow`)**: more models answer, but a provider may keep or train on
  the owner's prompts. With `deny`, a model no such provider serves is refused with words that say how to allow it.
- **`zdr` on by default**: fewer providers still; left to the owner.
- **Attribution as "Clank"**: OpenRouter would list Clank's use publicly; nothing the owner asked for.
- **No session id**: each request might reach another provider and miss its cache, at a higher cost.

## Consequences
- Some models may refuse under `deny` (503); Add a model's test finds it before the model is used, and its words say
  what to do. Which ones is to be checked with a real key.
- The session's id leaves this machine; it is OpenCode's own random id, no content.
