# 0124. The orchestrator's limits are always set, and past one the question waits for the owner

- Status: Accepted (Claude's call; the owner may change any number)
- Date: 2026-10-22
- Decided by: Claude, writing [design 0013](../design/0013-flows.md) §16

## Context
- Microsoft's magentic orchestration leaves its round and reset limits unlimited by default; a loop with no limit
  can spend a night on one failing box.
- The owner wants the orchestrator to decide at every gate, the final review included, yet to stay in charge.

## Decision
- **Five limits**, a flow setting each: `changes` per run (12: each change, send back, skip and extra try counts
  one), `extra_tries` per box past its cap (2), `stall` (3 checkpoints without progress, after which *go on* is
  refused), the checkpoint's own `limits` (20 minutes, 60,000 tokens written), and `final_review` (`orchestrator`,
  the default, or `owner`).
- **Past a limit the orchestrator cannot act**: the question waits for the owner, saying which limit was reached.
- **The owner may answer first**, and may turn the orchestrator off at any moment; the run goes on either way.

## Alternatives considered
- **No limits, the prompt asking for restraint**: a local model's restraint is not a guarantee.
- **The final review always the owner's**: the owner asked for decisions "at any of the Gate sections"; `owner` is
  one setting away.

## Consequences
- The longest a stalled run can go on is bounded by `stall` and `changes`.
- A run whose orchestrator used its changes waits for the owner as a run without one does.
