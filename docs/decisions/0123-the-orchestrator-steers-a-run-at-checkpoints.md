# 0123. The orchestrator steers a run at checkpoints, answering its questions as the owner's answers are given

- Status: Accepted (the owner's request of 2026-10-22, built as Claude's call; the owner may change it)
- Date: 2026-10-22
- Decided by: Claude, writing [design 0013](../design/0013-flows.md) §16 from the owner's request and the survey in
  [docs/research/orchestration.md](../research/orchestration.md)

## Context
- A built flow runs on its own until its final review, but stops for the owner at a box that failed or used its
  tries, and never changes its own plan (decision 0098).
- The owner wants a model to read each step's reports, change the flow as the work shows, and decide at every gate,
  so a flow can run overnight unattended.
- Every place a run waits is already a question (decision 0061), and the runner acts on its answer whoever gives it.
- The local model's window is the scarce thing: one session holding a whole night's run would not fit.

## Decision
- **Checkpoints**: after each box ends, and whenever the run asks a question, while the flow's orchestrator is on.
- **A checkpoint is a fresh session**, in Plan mode, on the flow's server and model, handed the run, the box's report,
  the question if any, the budget left, and the **ledger** Clank keeps beside the run (facts and plan, then one entry
  per checkpoint with Magentic-One's five answers: brief met, looping, progressing, what next, the note for the next
  box).
- **It decides with one tool, `flow_decide`**. At a question, its answer is given through the questions API, by the
  orchestrator, so a gate means the same whoever answers it; after a box, it may go on, change boxes not yet run, send
  work back with a note, or stop. Its changes pass the flow's rules like any edit.
- **Off unless turned on**: `O` in the Flow view, `clank flow orchestrator`, or a built flow's draft.

## Alternatives considered
- **One long session watching the whole run**: its context would fill within hours on a local model, and a restart
  would lose it.
- **A separate decision path beside the questions**: two meanings for one gate, and an answer the owner's console
  would not show.
- **Checkpoints only at questions**: the owner asked it to read every step's report; changes made only at a failure
  come too late.

## Consequences
- A run can go from its brief to its final review, through failures and loops, without the owner.
- Each checkpoint costs a few minutes of the model; a flow of ten boxes spends about ten of them.
- The ledger and every decision are kept, so a night's run can be read back step by step.
