# 0065. A finished box goes on by itself, unless a gate follows it or its *when done* waits

- Status: Accepted (the owner's choice, 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, choosing (a), as recommended, in the Choice of
  [design 0013 §10](../design/0013-flows.md#10-gates)

## Context
The owner's comment on board D: "when we have verified that a task is completed the model moves on to the next one",
and "in this loop while the model is working we can add/change certain things". Whether each box waits for the
owner's OK decides whether a flow can run while the owner is away. Board D2's *when done* reads "go on to T3 (or: wait
at a gate)", and the example places its gates after the plan's check and after INTEGRATE.

## Decision
A finished box passes to the next unless a gate follows it or its *when done* says wait, so the flow runs unattended
between gates. A flow setting, "wait after every box", off by default, makes every box wait, for a run the owner
wants to step through. Whatever the settings, these always wait for the owner: a loop at its cap, a failed box, the
model's proposals (unless auto-accept is on, [0064](0064-the-model-changes-a-flow-only-by-proposals.md)) and the
sessions' own questions and changes to review.

## Alternatives considered
- **(b) Every box waits for the owner's OK** until the owner switches the flow to (a). The owner would answer every
  box, and a long flow would stand still whenever the owner is away.
- **(c) As (a), but the first run of a new flow waits after every box.** The setting "wait after every box" steps
  through any run the owner chooses, the first or a later one.

## Consequences
- The owner decides where a flow stops by placing gates and by each box's *when done*.
- Everything a flow waits for is listed in **Waiting for you**; a gate is answered from the console, VS Code or the
  phone, and until Web Push the phone shows a gate only while its page is open (design 0005 §6).
- Unattended work stays bounded: each box by its limits (time, and the tokens the model writes), each loop by its
  tries ([0057](0057-a-flow-is-a-chain-of-boxes.md)).
- The owner still steers a running flow: a change to a box applies from its next try, and the flow can be paused or
  stopped ([0061](0061-the-runner-is-an-operation-per-box-in-the-service.md)).
