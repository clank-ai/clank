# 0058. INTEGRATE's brief starts a next flow, linked to this one, after the last gate

- Status: Accepted (the owner approved design 0013 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving [design 0013](../design/0013-flows.md) ("Approve all three", the remaining Choices
  as recommended): (b) in the Choice of its §3

## Context
The owner asked that the work end with "a brand new session which is only dedicated to taking all the outputs of
this last step and wrapping everything together to then continue working". That session is INTEGRATE: it writes a
summary of every deliverable before it (`STUDY-PLAN.md` in the example) and the next flow's brief (`NEXT.md`).
[Design 0013 §3](../design/0013-flows.md#3-lines-and-loops-that-end) asked what follows it. Board D1 draws a dashed
box after the last gate: "next flow: Run the study", "prompt from INTEGRATE".

## Decision
Once the last gate approves, a new flow is made from a template with INTEGRATE's brief as its YOU box, linked both
ways with this one, and it waits for the owner to start it. The last gate offers the next flow among its answers
(§10), and the Flow view draws it as the dashed box after that gate.

## Alternatives considered
- **(a) The same flow goes on:** the next brief feeds a new PLAN appended to this flow. The flow would grow with every
  round of work, and its run would not end with its deliverables.
- **(c) The last gate offers both.** It keeps (a) open at every last gate, and with it a flow that never ends.

## Consequences
- Each flow stays finite and readable, and its run ends with its deliverables; the history of the work is the chain
  of flows, each linked to the one before it and the one after it.
- A next flow never starts by itself. Its YOU box holds INTEGRATE's brief, which the owner may edit before saying it
  is done, as for any brief (§2).
- The next flow is made from a template, such as the one Clank ships in `clank/defaults/` (§11).
