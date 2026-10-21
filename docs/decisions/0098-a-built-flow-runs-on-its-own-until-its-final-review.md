# 0098. A built flow runs on its own until its final review: auto-accept on, no gate but the last, no wait after any box, its first YOU box done by the brief written with the model

- Status: Accepted (the owner's answers, built as Claude's call)
- Date: 2026-10-20
- Decided by: the owner's second and third answers ([design 0013 §15](../design/0013-flows.md#15-a-flow-built-with-the-model)):
  "Once built, the owner looks, then runs: ... one key (`r` ...) starts it; the owner can change any box first", and
  "During the run it stops only at the end: task boxes the model proposes are accepted on their own, VERIFY sends work
  back on its own up to its cap, and it waits for the owner only at the final review (INTEGRATE's gate) or when a box
  runs out of tries." How it is built is Claude's call.

## Context
A flow made from Clank's template waits for the owner at its brief (a YOU box), at "You approve the plan", for the
tasks its DECOMPOSE proposes (auto-accept off), and at its last gate. Design 0013 §10's Choice offered "(c) the first
run of a new flow waits after every box"; the owner chose (a), a box goes on unless a gate follows or its *when done*
waits, with a setting "wait after every box", off by default. A flow built with the model starts after a conversation
in which the owner already wrote the brief with the model, so asking for it again would be a stop the owner said not
to make.

## Decision
- **Clank writes a built flow** with `auto_accept` on, with no cap (a built flow accepts every task its DECOMPOSE
  proposes: a cap would stop the run in its middle), `wait_after_every_box` off and `next_flow` ask, whatever the draft
  says; and the mode auto on a box that changes files and names none (a TASK would take the workspace's mode, review by
  default, and each change it asks to make would wait for the owner), on the draft's boxes and on each task accepted
  into the flow. A draft whose box names review is refused (revised before shipping, at the review, 2026-10-20).
- **The model's draft keeps a built flow's own rules**: its first box is a YOU whose first file is the brief, already in
  the folder; its last box is a GATE, the final review; no other GATE, no other YOU; no box whose *when done* waits. A
  draft that breaks one is refused, saying which and why. The owner may change any of it before or after a run (board
  D2): the rules hold the model's draft, not the owner.
- **The first YOU box is done by the brief.** At the start of each run of a built flow (its `built` mark), its first
  box, a YOU, is done by itself when each of its files is in the folder and not empty, and its brief, `BRIEF.md`, is no
  longer as it was when the planning began (its fingerprint then is kept in the mark; a draft is refused while it is):
  kept by their fingerprints as a YOU's are, its event saying it was the brief written with the model. A file missing,
  or the brief as it was, it asks as any YOU.
- **The owner is told** "<title>: flow built: look, then r to run", a question about the flow with the next flow's
  answers (*Run it now*, *Later*), shown by the console, the phone and VS Code as that question is. *Run it now*
  starts the run; a run started otherwise (`r`, `clank flow run`) withdraws it; a draft written again asks again.
- **`r` starts a flow that has not run** at its first box, asked first; the Flow view follows a built flow not run yet
  as of its build, and Waiting for you shows the check's warnings of its last draft.

## Alternatives considered
- **Keep the template's gates and turn them off with a setting**: the owner asked for no "approve the plan" gate in a
  built flow; a gate that is there and skipped is a rule the owner cannot see.
- **The YOU box asks once, at the first run only**: the owner pressed `r` after reading the brief they wrote; asking
  again is the stop they ruled out. A brief missing still asks, so nothing runs on an empty brief.
- **A setting "built" that changes the runner's gates**: the flow's file already says everything that changes (no gate,
  no wait, auto-accept), so the runner reads the file as for any flow; only the first YOU needs the mark.

## Consequences
A built flow runs from its brief to its final review without asking, unless a box fails or runs out of tries, its
DECOMPOSE proposes past the cap, or a session asks. Its last gate makes the next flow as any flow's does (decision
0091), from Clank's template, which still has its gates: building the next flow with the model is the owner's `n`.
