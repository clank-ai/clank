# 0107. A cloud model serves the main slot in an engine's place, one provider at a time

- Status: Proposed (Claude's call; decision 0077's (a), for cloud models)
- Date: 2026-10-20
- Decided by: Claude, writing [design 0016](../design/0016-cloud-models.md) §7, following the recommendation of
  decision [0077](0077-an-endpoint-serves-the-main-slot.md) (proposed with design 0015)

## Context
- A workspace's OpenCode knows one model, the role `agent`, which the gateway sends to the main slot; OpenCode's limits,
  the Monitor's figures, This folder, `clank work` and a flow's boxes all follow the main slot (decision 0077's
  context).
- Decision 0077 asks whether an endpoint serves `main` in an engine's place (a), or a slot of its own beside it (b),
  about four more steps: roles as settings, a role per workspace, OpenCode's second model, the Monitor by the
  workspace's role.
- The owner's request is that a new user, with no GPU and no local model, works with a cloud model at once.

## Decision
- A cloud preset is for the main slot only; loading it is a load or a switch like any (plan, start, health, measure),
  and switching between it and a local preset stops one before the other starts.
- `fast` (completion's fill in the middle) and `vision` (loaded on demand on this machine) stay local; a cloud preset
  for either is refused, saying why.

## Alternatives considered
- **(b), a slot of its own**: KVMem would keep serving research while a workspace allowed the cloud uses it; about four
  more steps before the first cloud request, and nothing a new user without a GPU needs.
- **The cloud as a fallback of the main slot**: a request's provider would change without a switch the owner sees.

## Consequences
- On this PC, while the main slot runs a cloud model, KVMem does not run, and a workspace kept on this machine is
  refused (design 0016 §9), saying so.
- Everything that follows the main slot works unchanged with a cloud model.
- (b) stays open (design 0016 §20).
