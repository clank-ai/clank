# 0112. A workspace is asked before its agent starts with a cloud model loaded, and a request that reaches the gateway first is held while it asks

- Status: Proposed (Claude's call)
- Date: 2026-10-20
- Decided by: Claude, writing [design 0016](../design/0016-cloud-models.md) §9; it says how decision
  [0103](0103-the-cloud-is-agreed-once-and-asked-once-per-workspace.md)'s "each workspace then asks the first time it
  would use the cloud model" is built

## Context
- `clank work` and This folder's `a` give OpenCode the terminal: a question asked while it runs is seen only in another
  client (the console, the phone, VS Code), which a new user may not have open.
- The main slot can switch to a cloud model while a workspace's OpenCode runs (the owner, a flow's box); its next
  request is then the first that would use the cloud.
- Decision 0075 (proposed) refuses a request beyond its bound, never asks, and gives a widened workspace a new key so
  that an OpenCode started before keeps the old bound: what its sessions read while local stays local.
- The gateway already holds a paused session's requests, kept alive with comment lines, and lets them go on the same
  stream (decision 0055).

## Decision
- **Before its agent starts** in a workspace not yet answered, with a cloud model in the main slot (This folder, `clank
  work`, `clank code`, VS Code, the phone, a flow's run), Clank asks the workspace's question: in a window of the
  console, in the terminal before OpenCode takes it, as a question on the phone and in VS Code. Its detail says what
  goes and what never does; for a workspace that existed before the provider was agreed, that its earlier sessions and
  folder may hold research.
- **At the gateway**, a cloud request from a workspace not yet answered is held as a paused session's is, while the
  workspaces component asks the same question on every client; allowed, it goes on on the same stream; kept local, it
  is refused (403, `model_send_denied`) in words that say how to allow it.
- **Answers**: allow (its bound becomes `cloud`), keep local (not asked again), or none within 30 minutes (refused this
  time, asked again at the next start).
- **No new key** when a workspace is allowed: the question names what goes, the session's history included, which is
  what 0075's new key was for.

## Alternatives considered
- **Only at the gateway**: a new user's first request would wait on a question they cannot see from OpenCode.
- **Only before the start**: a switch of the main slot while OpenCode runs would send the workspace's next request
  unasked, or refuse it unexplained.
- **A new key on allowing** (decision 0075): every OpenCode running at the time would have to start again before using
  the cloud, after a question that already showed the owner what goes.

## Consequences
- The workspaces component asks the question (it owns the record); the gateway reports a held request with the event
  `gateway.cloud_wanted`, which it listens to.
- A held request may wait up to the question's 30 minutes; OpenCode keeps waiting (its provider has no timeout).
