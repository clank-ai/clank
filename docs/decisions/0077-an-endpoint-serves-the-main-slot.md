# 0077. An endpoint serves the main slot in an engine's place, or a slot of its own beside it

- Status: Proposed: the owner chooses; for cloud models, decision
  [0107](0107-a-cloud-model-serves-the-main-slot.md) proposes (a)
- Date: 2026-10-19
- Decided by: not yet: the owner chooses (a) or (b) below; Claude recommends (a). Written with
  [design 0015](../design/0015-endpoints.md) §6

## Context

- Design 0001 §1 (approved): "managed providers that need the GPU share it one at a time; endpoints and CPU engines
  run alongside." Design 0001 §3.8 (approved): "A candidate that fits beside the live model (an endpoint, an engine on
  the CPU) runs alongside it."
- A workspace's OpenCode knows one model, the role `agent` (`clank/components/agents/service.py:58`;
  `clank/components/agents/adapters/opencode.py:142-146`), which the gateway sends to the main slot
  (`clank/components/gateway/service.py:44`), as it does any role it does not know
  (`clank/components/gateway/routing.py:94`). OpenCode's limits (`clank/components/agents/service.py:305-324`), the
  Monitor's figures (decision 0067), the folder page, `clank work` and a flow's boxes (decision 0062) all follow the
  main slot.
- Design 0013 §7 (approved): a box on another slot "would need OpenCode's configuration to name that role as a second
  model: later."
- The Pi has no engine: the endpoint is its only model. On this PC, KVMem serves the owner's research in the main
  slot, and the GPU holds one large model at a time.
- Decision 0075: each workspace has a bound, and the gateway checks each request against what serves its role's slot
  at that moment.

## Decision

**Not yet made: the owner chooses one of these.**

**(a) The main slot, in an engine's place** (recommended). An endpoint serves `main`, one provider at a time: loading
one stops the main slot's engine first, as a switch between engines does (design 0015 §6), and switching back starts
it again. `fast` and `vision` stay on this machine. An endpoint's check connects alongside the live model, on a tunnel
of its own (decision 0076), and so will its trial when M2 builds trials, as design 0001 §3.8 says. This reverses
design 0001 §1's "endpoints run alongside" for serving, until (b) is built.

**(b) A slot of its own, beside `main`.** The owner adds a slot for the endpoint, with a port of its own (the
runtime's `ports`, `clank/components/runtime/kinds.py:104-108`), and a role that reaches it. A workspace's record
names the role its agent uses, and its OpenCode gets that role as a second model. KVMem goes on serving research in
`main` while a scratch workspace's requests go to the cluster. It costs about four more steps (an estimate): roles as
settings instead of a constant (`clank/components/gateway/service.py:44`); a role per workspace, in its record and in
OpenCode's configuration; OpenCode's limits, the Monitor and the folder page by the workspace's role; and a flow box's
slot (decision 0062). The Pi needs none of them.

**Claude recommends (a)** for the first session: everything that follows the main slot works unchanged, the Pi loses
nothing, and T1 runs on this PC at a time without GPU work (design 0015 §15). (b) stays open: nothing in (a) is in its
way, and design 0015 §17 lists it.

## Alternatives considered

- **(b)**, above: the per-workspace bounds of decision 0075 at their most useful on this PC, for about four more steps
  before the first session.
- **The endpoint as a fallback of the main slot**, used while KVMem is busy or stopped. A request's provider would
  change without a switch the owner sees, and each workspace's content would follow it.
- **A slot per workspace, chosen by the gateway from the request's key.** The same cost as (b), and a slot's provider
  would depend on who asks, which no client could show as one state.

## Consequences

- With (a), the per-workspace bounds still hold, but on this PC they act as all or nothing: while `main` runs an
  endpoint, KVMem does not run, and every workspace still bound to this machine is refused, saying why, instead of
  being served by KVMem. On the Pi, nothing is lost.
- With (a), design 0001 §1 is revised for serving, and its §3.8 is kept: an endpoint's check, and later its trial,
  run alongside on a tunnel of their own.
- With (b), plan s10 gains its steps before the first session, and design 0013 §7's second model is built first.
- Either way, `fast` and `vision` stay on this machine (designs 0006 and 0008).
