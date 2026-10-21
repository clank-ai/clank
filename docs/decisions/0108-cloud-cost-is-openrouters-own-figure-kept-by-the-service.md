# 0108. Cloud cost is OpenRouter's own figure, kept by the service from the gateway's spool, in this computer's days and months

- Status: Proposed (Claude's call)
- Date: 2026-10-20
- Decided by: Claude, writing [design 0016](../design/0016-cloud-models.md) §12; it says how decision
  [0104](0104-cloud-cost-is-shown-with-an-optional-limit.md) is built

## Context
- OpenRouter returns each answer's usage with `cost`, "the total amount charged to your account", in its last message
  (its usage accounting page, read 2026-10-20). A stream stopped before its end has no usage; `GET /generation?id=…`
  gives a request's `total_cost` afterward.
- The gateway is a process of its own that writes no database; the service keeps state in SQLite (decision 0014) and
  answers every client. The limit is enforced where a request can be stopped: the gateway (decision 0020).
- The owner answered "from the provider's prices and token counts"; OpenRouter's own figure is those, as it billed
  them (its cache discounts and thinking tokens included).

## Decision
- **A request's cost** is its `usage.cost`; for a stream cut short, its generation's `total_cost`, asked by the service
  10 s, 60 s and 5 min later; until then, or if it never comes, an estimate from the tokens counted at the model's
  prices, labeled as an estimate wherever it shows.
- **The gateway's spool**: each cloud request that ends appends its cost to `state/cloud-spool.jsonl`; `GET
  /spend?after=<n>` (the local token) gives the entries after `n` and forgets those up to `n`.
- **The service keeps them** in the gateway component's table `cloud_costs`, taken every two seconds, idempotent by
  the gateway's run and sequence, and answers every total from it (today, this month, by session, workspace and flow).
- **The limit at the gateway**: the routes carry today's and this month's spending and the limits; the gateway adds its
  entries not yet taken, and holds cloud requests at the limit.
- **Days and months are this computer's local ones.**

## Alternatives considered
- **Prices times tokens, computed by Clank**: misses cache discounts, thinking tokens billed as output, per-request
  fees, and price changes during a session.
- **OpenRouter's own `usage_daily` and `usage_monthly` from `GET /key`**: per key and per UTC day, not per session or
  flow, and counting whatever else uses the key. Shown beside Clank's, never used for the limit.
- **The gateway keeps the totals itself, in a file**: one more record of the same spending, and the service could not
  answer per session or per flow without it.
- **UTC days**: OpenRouter's, but the owner's day ends at their midnight.

## Consequences
- Costs survive a restart of the gateway and of the service.
- An estimate shows for a few seconds to minutes after a stream cut short.
- The flows component asks the gateway's service for its boxes' sessions' costs.
