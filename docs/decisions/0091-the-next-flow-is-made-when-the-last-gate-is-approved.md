# 0091. The next flow is made from Clank's template once the last gate is approved, its brief copied in when it first runs, and the owner asked whether to run it now

- Status: Accepted, as Claude's call; the owner may reverse it
- Date: 2026-10-20
- Decided by: Claude, building what [0058](0058-integrate-starts-the-next-flow.md) decided ([plan
  s31](../plans/s31-flows-the-next-flow.md)), at the request to build it: "once the flow's last gate is approved, a
  new flow is made from Clank's template ... with INTEGRATE's brief as its YOU box's file, linked both ways to the flow
  it came from, and the owner is asked whether to run it now ... never started without their answer unless the flow
  says so"

## Context
Decision 0058 says that once the last gate approves, a new flow is made from a template with INTEGRATE's brief as its
YOU box, linked both ways with this one, waiting for the owner to start it; the last gate offers the next flow among
its answers ([design 0013 §3, §10](../design/0013-flows.md#3-lines-and-loops-that-end)). Nothing built it. Building it
asks what is the last gate and INTEGRATE's brief, what the new flow is called, how the two are linked, how the brief
reaches the new flow's YOU box without clobbering a file of the folder, and how the owner is asked. Both flows work in
the same folder: Clank's template writes `BRIEF.md`, `PLAN.md`, `SUMMARY.md` and `NEXT.md` every round.

## Decision
- **When.** A run ends done after its last box, a GATE, was approved. The next flow is made from the last INTEGRATE
  before that gate. Its brief is the INTEGRATE's file named `NEXT.md`, else the last of its files when it writes two or
  more (the first is its summary); one that writes a single file, or a brief not in the folder, makes none, and an
  event says why.
- **From Clank's template** (`clank/defaults/templates/flow.json`), kept in the same workspace as
  `<name>-<n>` (`study` gives `study-2`, `study-2` gives `study-3`, the first number free), titled by the brief's first
  heading (`# Run the study`), else "<this title>, next". Its defaults' model is this flow's.
- **Linked both ways.** The new flow's `follows` names the flow, its run, the INTEGRATE and the brief's file, and the
  fingerprint of its own YOU box's file when it was made; this flow's `next` names the new flow. The owner sees both
  in `clank flow show` and `clank flow next`.
- **The brief, copied when the next flow first runs.** Nothing in the folder changes when the next flow is made. When
  its first run starts, the brief (`NEXT.md`) is copied into its YOU box's file (`BRIEF.md`), unless the owner changed
  that file since the next flow was made: then it is kept as they left it. Either is an event, and the YOU box says
  where its brief came from; the owner edits it, as any brief, then says it is done.
- **Asked, as a question of its own**, right after the last gate's approval rather than as an extra answer of that
  gate: *run it now* or *later* (`clank flow run` starts it then), from any client, and `clank flow next NAME --run`.
  The flow's `next_flow` setting says otherwise: `ask` (the default), `run` (it starts at once, queued when another
  flow runs), or `off` (none is made). `clank flow next NAME --make` makes one that was not.

## Alternatives considered
- **An extra answer of the last gate** ("approve, then run the next flow"), as 0058 words it: one click fewer, but the
  next flow is made only once the gate is approved and its brief read, and a gate's answers stay those of every gate;
  the question asked right after it offers the same choice.
- **The brief copied when the next flow is made**: simpler, but the approval of one flow's last gate would rewrite a
  file of the folder (`BRIEF.md`) before the owner chose to go on.
- **The next flow's YOU box writing `NEXT.md` itself**: no copy, but its own INTEGRATE writes `NEXT.md` again, which
  would rewrite its own brief and mark every box after the brief stale.
- **A name of the owner's**, asked first: one more question before a flow they may never run; the file can be renamed.

## Consequences
- Each round's files replace the last round's in the folder, as a person starting the next round would; every round's
  deliverables stay in its run's folder, and in git.
- A flow made from another template, or edited, works as well: the brief is copied into whatever its first box writes
  first.
- The phone, VS Code and the console show the question as any question about a flow.
