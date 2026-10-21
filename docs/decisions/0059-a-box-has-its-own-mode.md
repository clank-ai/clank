# 0059. A box's mode (Plan, Review or Auto) applies to its own session; the workspace's mode to every other

- Status: Accepted (the owner approved design 0013 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving [design 0013](../design/0013-flows.md) ("Approve all three")

## Context
The owner wants to "select individual sections of the plan to also make sure we are editing certain settings", and a
flow mixes boxes that write nothing but Markdown (a plan, a verdict, proposals) with tasks that change code. Today the
mode is the workspace's: its record says review or auto, and Clank answers every change asked in the container by it
([design 0007 §3](../design/0007-reviewing-changes.md#3-review-and-auto-clank-answers)). Board D2 shows the mode as one
of a box's settings (`o`), and [design 0013 §4](../design/0013-flows.md#4-a-boxs-settings) says whose it is.

## Decision
- A box's mode is Plan, Review or Auto, the three the owner already knows (design 0009 §7): Plan is the planner;
  Review and Auto are `build`, its changes waiting for the owner or accepted at once (design 0007).
- The mode is the box's, for its session only. Clank knows which session asks, so it answers a box's session by the
  box's mode, and every other session, the owner's own included, by the workspace's.
- A box that names no mode takes the workspace's. PLAN, VERIFY, DECOMPOSE and INTEGRATE are Plan by default; a VERIFY
  that must run tests needs Review or Auto, since Plan mode runs reading commands only (design 0009 §3).
- The box's first message is sent with the agent of its mode (§5), and until OpenCode 1.19 is measured to take tools
  per message, the mode also decides the box's tools (§4).

## Alternatives considered
- **The workspace's mode for every session, as today** (design 0007 §3). A flow's boxes and the owner's own session
  would share one rule: a TASK in Auto would put the owner's own work in Auto too, and the owner's Review would hold
  every change a TASK makes, even in a run the owner left to go on by itself.

## Consequences
- A TASK can run in Auto while the owner reviews their own work; the second build step proves it, the workspace
  staying in Review.
- Design 0007 §3's rule, one mode for every agent in the container, gains this one exception: a box's session.
- A box in Plan mode is never told to write anything but Markdown: a flow that asks it to is refused when saved
  ([0057](0057-a-flow-is-a-chain-of-boxes.md)).
- The planner's rules gain the flow tools, so PLAN, VERIFY, DECOMPOSE and INTEGRATE can all run in Plan mode
  ([0064](0064-the-model-changes-a-flow-only-by-proposals.md)).
