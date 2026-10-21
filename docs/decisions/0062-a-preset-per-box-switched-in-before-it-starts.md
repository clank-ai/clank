# 0062. A box's model is a preset, switched into the main slot before the box starts

- Status: Accepted (the owner approved design 0013 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving [design 0013](../design/0013-flows.md) ("Approve all three"); what concerns the
  owner's own window is Claude's call in its §7

## Context
The owner: "it would enable us to select different models for different tasks, so we could just straight up load and
unload models as we go along this flowchart." Every request of a box reaches the main slot through the gateway as the
role `agent`, and the owner's own OpenCode session in the workspace uses the same slot. A switch takes time: KVMem's
`daily 262K` was ready 19-25 s after loading ([2026-10-13](../measurements/2026-10-13-ninfer-and-kvmem.md)).
[Design 0013 §7](../design/0013-flows.md#7-a-model-per-box-and-what-a-switch-costs) says when a box's model is loaded.

## Decision
- A box's model is a preset. Before the box starts, when the main slot does not run it, the runner starts the
  runtime's switch (`runtime.switch`: plan, stop, start, health, measure; design 0003 §6.1) and waits for it.
- It starts the switch only while the gateway's activity shows no request in flight on the slot (the *wait* of design
  0001 §4.2's busy check) and while the owner's own OpenCode session in that workspace is not working, as the watcher
  reports. Until then it waits, and the Flow view says "waiting for your session to be idle to load <preset>".
- A switch that fails returns the slot to the last configuration that worked, and the box fails with the engine's
  reason, waiting at a gate.
- After a switch, the owner's window is told its model changed, on This folder and in VS Code, and its configuration
  is refreshed when it next starts (the one-window rule, design 0004 §5). A preset whose context is smaller than what
  the owner's session already holds is named in that message as too small for it.

## Alternatives considered
- **Switching at once** (the busy check's "switch now"). The requests in flight would end with an error.
- **Switching while the owner's own session works.** Its next steps would be answered by another model.
- **Giving the owner's window the new configuration at once.** Changing OpenCode's configuration while it runs
  restarts its instance and closes every event stream (design 0007 §2).
- **A box on another slot,** such as a small model on the CPU in `fast`. OpenCode's configuration would have to name
  that role as a second model: later.

## Consequences
- Each switch is recorded with its duration; the Flow view shows the last one for each preset, a flow's switches and
  fresh starts before it runs, and the presets the flow uses (**Models in this flow**).
- A flow may wait on the owner's own session, and says what it waits for.
- The owner's own sessions and a running box interleave on the slot, each evicting the other's conversation from the
  engine; the Flow view says so when it happens.
- Before the fifth build step, with the owner's go-ahead and on synthetic folders: a whole switch measured for each
  preset.
