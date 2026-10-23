# 0127. The orchestrator tells the owner at once, may pause the run or leave a question to them, and may only watch

- Status: Accepted (the owner's request of 2026-10-22, built as Claude's call); adds to 0123
- Date: 2026-10-22
- Decided by: Claude, after the first long run with the orchestrator on

## Context
- The owner (2026-10-22, after stopping the first long run): "we should include the ability to have the orchestrator
  be the LLM running on the local model we are using, where the orchestration occurs after each completed step just
  to make sure things are on track and to get my attention if there is anything that I need to be aware of out of
  nowhere."
- The orchestrator of decision 0123 already ran on the flow's model (the local model, unless the flow names another)
  and checked each box a model ran. It had no way to reach the owner: its words stayed in the ledger, read only when
  the owner opened it.
- Clank reaches the owner through its questions: they show in the console's Waiting for you, in VS Code and on the
  phone, and one of high urgency reaches the phone at once.

## Decision
- **Its word for the owner.** `flow_decide` takes `tell_user`: what the owner should know now. Clank asks it as a
  question of high urgency that the run does not wait for, its answers *Seen*, *Pause the run* and *Stop the run*.
  The ledger keeps it ("told you: ..."), and the Flow view's Orchestrator panel shows the last one.
- **Pause and leave.** After a box it may choose `pause` (the run pauses for the owner, who goes on with `r`); at a
  question, `leave` (the question waits for the owner). Both need `tell_user`, saying why.
- **Its role.** `orchestrator.role`: `steer` (as in 0123: it decides the questions too, and may change the boxes
  ahead) or `watch` (after each box it goes on or pauses, tells the owner what they should know, and decides no
  question). `O` on the Flow view turns it on steering, then watching, then off; `clank flow orchestrator NAME --role
  watch` sets it.
- **Its instructions** add a check that the run is on track (the right files, the right target, within the limits)
  and say when to tell the owner: a surprise, a result against the plan, a failure that comes back, anything that
  costs them time, money or their machine; nothing when all is as planned.

## Alternatives considered
- **A notification system of its own** (a feed, a sound): a second path to the owner beside the questions, which
  already reach every client and the phone.
- **Pausing the run at every word**: the owner asked to be told, not stopped; the run goes on unless the owner, or the
  orchestrator for a reason it gives, pauses it.
- **Watching as a separate feature**: the same checkpoint with fewer choices; one setting keeps one ledger and one
  panel.

## Consequences
- A run with the orchestrator on can reach the owner's phone in the middle of the night; its instructions keep that to
  what the owner would want to hear of now.
- The first-message and the tool's description grow by a few lines; a local model reads them in every checkpoint.
