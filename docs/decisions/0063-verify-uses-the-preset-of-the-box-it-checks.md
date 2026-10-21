# 0063. VERIFY uses the checked box's preset, in a fresh session, unless it names another

- Status: Accepted (the owner approved design 0013 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving [design 0013](../design/0013-flows.md) ("Approve all three", the remaining Choices
  as recommended): (a) in the Choice of its §7

## Context
A VERIFY gives a verdict on one earlier box's deliverable: *pass*, or *fail* with numbered findings that send the
checked box back for its next try, up to three. A check is only as good as its independence from the work it checks,
and each switch of the main slot costs time (KVMem's `daily 262K` was ready 19-25 s after loading, 2026-10-13).
[Design 0013 §7](../design/0013-flows.md#7-a-model-per-box-and-what-a-switch-costs) asked which model checks.

## Decision
By default a VERIFY runs on the checked box's preset, in a fresh session: no switch, and its independence comes from
being handed only the brief, the deliverable it checks and that box's *accept when*, never the session that made it
(§2). Any VERIFY is free to name another preset, and the switches' cost is shown before the flow is saved.

## Alternatives considered
- **(b) Another preset by default,** for a second model's view: up to two switches a try, so up to six for three
  tries.
- **(c) A small model on the CPU,** as the vision model is (design 0008): no GPU switch, but its quality is yet to be
  measured, and a box on another slot waits until OpenCode's configuration names a second model (§7).

## Consequences
- A check and its loop cost no switch unless the flow names another preset, and then the owner sees the cost before
  saving the flow.
- A second model's view is one setting away, for any VERIFY.
- Its independence rests on what its first message hands it, kept as a file for the owner to read (§5).
- A check on the CPU can be chosen later, once a small model's quality is measured.
