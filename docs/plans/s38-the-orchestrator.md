# Plan s38: the orchestrator

[Design 0013](../design/0013-flows.md) §16, decisions [0123](../decisions/0123-the-orchestrator-steers-a-run-at-checkpoints.md)
and [0124](../decisions/0124-the-orchestrators-limits-are-always-set.md); the survey behind it,
[docs/research/orchestration.md](../research/orchestration.md). Asked for by the owner on 2026-10-22, built the same
day before the first long run on the Stabilizer Rank Challenge.

**Goal:** a flow setting that lets a model steer a run on its own: a checkpoint after each box a model ran and at each
question, a fresh Plan-mode session that decides with `flow_decide`, within limits that are always set, the ledger
kept by Clank.

## Tasks

- [x] 1. The setting: `Flow.orchestrator` (`on`, `model`, `final_review`, `changes`, `extra_tries`, `stall`, a
  checkpoint's `limits`), its schema regenerated. Test: `tests/cli/test_flow_commands.py` (turned on and off in the
  flow's file).
- [x] 2. The ledger and the decision (`orchestrating.py`): `Orchestration` on the run, `Decision`, `decided` (a choice it
  may make, why given, changes within the limit, only boxes not run, the flow's rules kept, no going on once stalled),
  `changed`, `ledger_text`, `failure_class`, `message`. Tests: `tests/components/flows/test_orchestrator.py`.
- [x] 3. The runner: a checkpoint after a box (`_reviews`) and at a question (`_steers`), its operation
  `flows.orchestrate` (model, server without a box's try, session, work within its limits, apply), `decide`, `_apply`
  (a question answered through the questions API by the orchestrator, set aside when the owner answered first; a note,
  changes, back, stop), `_let_go` (no decision, a failure, a restart), the event `flows.orchestrator`, the ledger as
  `orchestrator.md` beside the run. The orchestrator's notes reach the next box's first message (`steer`, its first try
  included), and a gate it sends back or a try it gives says so. Tests: the same file.
- [x] 4. The way in: `flow_decide` in Clank's MCP server, `POST /flows/decide` forwarded by the gateway (and nothing
  else new), `GET|POST /flows/{workspace}/{name}/orchestrator`, `clank flow orchestrator NAME [on|off] [--final]
  [--model]`. Tests: `tests/components/gateway/test_flows_forwarding.py`, `tests/components/agents/test_sessions.py`,
  the route's 409 in `test_orchestrator.py`.
- [x] 5. The planning knows it: `prompts/build.md` lists `orchestrator.*` (and `accept_command`); a draft may turn it on.
- [x] 6. The console: the Flow view's Orchestrator panel (`flowpanels.orchestrator`, the view's `orchestrator`), `O`
  to turn it on or off, `L` for the ledger (with plan s39, the console as the website shows it).
- [ ] 7. A live run on the owner's machine (the Stabilizer Rank Challenge's first long run), its ledger read back.
