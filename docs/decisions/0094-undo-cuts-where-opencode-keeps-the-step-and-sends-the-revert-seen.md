# 0094. Undo cuts where OpenCode keeps the step, previews from the flow, and sends only the revert the owner saw

- Status: Accepted, as Claude's call; the owner may reverse it
- Date: 2026-10-20
- Decided by: Claude, without the owner (building design 0012's step 10, [plan
  s20](../plans/s20-monitor-the-guide-part-2.md)); it says how
  [0056](0056-undo-takes-back-the-last-step-drop-only-clears.md)'s "reverts at the last part of the previous assistant
  message" and its preview are done

## Context
Decision 0056 makes Undo OpenCode's `revert` at the last part of the step before the last, always naming the part,
with a preview of the steps and the files it takes back (design 0012 §9.5 named `/session/:id/diff` for it), and "undo
the turn" for the first step after the owner's message. Read in OpenCode 1.19.0's `session/revert.ts` and `summary.ts`
(2026-10-20):

- A revert at a part looks at the parts before it in its message: when none is a text or a tool call, OpenCode drops the
  part and reverts from the last message of the owner's instead, the whole turn, the owner's message included. A step
  that only thought before its finish is such a step.
- It restores the files of the patch parts after the part it names, from its own snapshots; it refuses a busy session.
  At the owner's next message it removes the messages after the cut and the parts of the cut message from the named
  part on.
- `/session/:id/diff` answers the turn of an owner's message only, not a revert at a part.
- A note the owner sends while step n runs is stored at once: in OpenCode's order it comes after step n and before
  step n+1, so a revert at step n's last part takes the note back too.

## Decision
- **The cut**: the last part of the step before the last, when a text or a tool part comes before it in that step (the
  flow's `cut`). A step before with none is taken back with the last, and the cut moves to the newest earlier step
  that can be named; the preview lists every step it takes back.
- **The turn**: when the owner's message, or a note, comes before the step reached, undoing the step alone is refused
  with that reason and the turn is offered: a revert at the oldest of the owner's messages there, by message id alone,
  their words given back for the note line (read from the session's newest page of history, whole up to the bridge's
  cap, else the flow's words, said cut).
- **Never across a compaction**: a step reached whose step before is a compaction's message is refused ("undo does not
  take back a compaction"), since the session now stands on its summary.
- **The preview comes from the flow**: the steps, the files their patch parts list (what OpenCode restores, read without
  a `docker exec`), the owner's messages and the subagents those steps started, whose own sessions' files a revert does
  not restore.
- **What was confirmed is what is done**: the console sends the revert its window showed and what it said that revert
  takes back (the steps, the owner's messages); the service compares both with the undo it would make now and refuses
  one the session moved on from, sending nothing ("look again"), and an undo that names no revert is refused, never
  read as whatever is offered now. OpenCode's answer is shown in the flow at once (its cut alone, not its snapshot and
  text diff); when it cut elsewhere, the Guide reads from the flow what that cut took back, gives back the words of
  every message of the owner's in it, and says in a window that it took back more than the preview said.
- **Undo waits for the session to stop**: it is grayed while the session works, with the reason; a stop and an undo on
  one key would undo the step the stop just ended, not the one the owner saw.

## Alternatives considered
- **Always the step before's last part**: for a step that only thought, OpenCode would take back the whole turn, the
  owner's message with it, unannounced.
- **A revert by the last step's message id**: OpenCode takes back the turn from the owner's message.
- **The preview from `/session/:id/diff`**: in 1.19.0 it answers only an owner's message's turn, and each read is a
  `docker exec`.
- **Undoing what is offered when Enter is pressed**: a step that ended between the window and Enter would be taken back
  unseen.
- **Stop, then undo, on `u`**: the step undone would be the one the stop ended, which the owner did not see finish.

## Consequences
- An undo may take back several steps, which its title and preview say ("takes back steps 2 and 3").
- Once an undo is final, OpenCode has removed the cut part of the step before, often its patch part, so undoing that
  step later takes back its messages but not its files; the preview lists only the files OpenCode still keeps, so it
  says what will happen. That undo takes back exactly one step, files included, waits for the owner's measurement
  (design 0012 §10).
- A subagent's changes in its own session are not taken back by its parent's undo; the preview says so (to see).
- Undo back to a step the owner picks (0056's alternative) is the same call at an earlier cut, and can follow.
