# 0057. A flow is a chain of boxes: only a VERIFY's fail line points back, and every loop ends at a gate

- Status: Accepted (the owner approved design 0013 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving [design 0013](../design/0013-flows.md) ("Approve all three"); the shape is Claude's
  call in its §3

## Context
The owner's comment on board D asked for boxes that are big tasks, a verifier with "a conditional loop where if the
verifier catches something then it goes back and keeps planning", and tasks worked "sequentially". The runner must
know which box comes next, the Flow view must draw it, and a flow the runner cannot run must be refused before it
starts. Every box uses the main slot, and KVMem holds one conversation at a time
([design 0013 §6](../design/0013-flows.md#6-the-runner-an-operation-of-the-service)).
[Design 0013 §3](../design/0013-flows.md#3-lines-and-loops-that-end) sets the shapes a flow may take.

## Decision
- Boxes are joined by lines. A box that is done passes to the box its *then* line leads to.
- A VERIFY has two lines: *pass* to the box after it, and *fail* back to the box it checked, carrying the findings.
  Only a VERIFY's fail line may point back. The box it returns to runs again while it has tries (3 by default); when
  they are used up, the fail goes to a gate instead. Such a loop is the only work that runs again by itself.
- DECOMPOSE's accepted tasks run one after another between it and the box after it, each handed the deliverables of
  those before it, and the box after them waits for all of them. The Flow view draws them fanned out from DECOMPOSE
  and joined at the next box, as board D1 does.
- A flow that breaks these rules is refused when saved, naming the file, line and field: a line back that is not a
  VERIFY's fail; a box with two *then* lines, or a join, outside the two exceptions above; a VERIFY checking a box
  that is not before it; a box no line reaches; a deliverable that is not Markdown in a box in Plan mode (the planner
  may not write it). In the Flow view, `c` (connect) offers only what these rules allow.
- Other shapes wait for a later design.

## Alternatives considered
- **Any graph: branches, joins and lines back from any box.** The runner would have to choose among paths or run boxes
  side by side, and a loop that no tries bound could run forever.
- **DECOMPOSE's tasks at once** (board D4 offers "at once"). On one engine they would wait for each other in the
  gateway and evict each other's conversation (§13); "at once" waits for a second provider.
- **A loop that runs until its VERIFY passes.** A deliverable that never satisfies its check would never stop it; at
  the cap, a gate lets the owner decide instead, with three more answers: one more try, take it as it is, or skip the
  box (§10).

## Consequences
- A flow never runs forever, and the runner follows one path, one box at a time.
- The tasks are a chain: editing T1 makes T2 and those after it stale (§8).
- `clank flow check` refuses each rule's flow, naming the file, line and field, as the first build step's tests prove.
- Branches and joins need a later design, and tasks side by side a second provider as well.
