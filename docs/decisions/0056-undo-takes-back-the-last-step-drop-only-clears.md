# 0056. Undo takes back the last step, drop only clears a tool result, and the gateway never edits what OpenCode sends

- Status: Accepted (the owner approved design 0012 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving design 0012 ("Approve all three"), §9.5's and §9.7's Choices as recommended;
  "undo the turn" was Claude's call (2026-10-18), approved with the design

## Context
The Guide can take back what the model did ([design 0012](../design/0012-the-monitor.md) §9.5, §9.7). OpenCode's
`revert` restores the files changed after a point from its own snapshots and deletes the later messages at the next
prompt; until then, `unrevert` brings everything back. It refuses while the session is busy, and a revert by message
id alone takes back the whole turn, the owner's message included. OpenCode clears an old tool result by setting its
part's `state.time.compacted`, and it can also delete a part; its routes do not check whether the session is busy.
Board D said the gateway would leave a dropped item out of what the model is sent.

## Decision
- **Undo** takes back the last step: when the session is busy, it asks to stop it first; then it reverts at the last
  part of the previous assistant message, always naming the part. A preview shows the steps and the files it takes
  back; `u` again redoes it until the owner's next message, when it becomes final.
- For **the first step after the owner's message**, undo is refused with the reason ("undoing it would take back your
  message too"), and **undo the turn** is offered: a revert at the owner's message, which takes back the message and
  every step after it, and puts the message's text back in the note line.
- **Drop** only clears a tool result, by OpenCode's own clearing: from the next step the model reads "[Old tool result
  content cleared]" in its place, and the call stays. It never deletes, and it is refused for an item of the step in
  progress. Its window says the drop is final.
- **The gateway never edits what OpenCode sends**, so OpenCode's history and what the model reads stay the same.

## Alternatives considered
- **Undo back to any step the owner picks in the flow**: the same call at an earlier part; it can follow once undoing
  the last step is measured.
- **A revert by message id**: it would take back the owner's message with the step.
- **Drop also removing a call with its result** (OpenCode's `DELETE` of the part), which board C's "drop the loop
  text" needs for the looping call itself: not the drop; if it comes, only for an item the owner picks, with its own
  confirmation.
- **The gateway leaving a dropped item out** (board D's words): what the model reads would no longer be OpenCode's
  history.

## Consequences
- That undo takes back exactly one step, files included (a `bash` call's too), what undo and drop cost in reading
  again, and whether a cleared result can be brought back are measured in step 10.
- In the flow, an undone step or turn is a gray side lane, "undone by you", folded once final; a cleared result is
  marked "result cleared by you", with the tokens it freed.
- Board C's "drop the loop text" frees the results that echo a loop, not the looping call.
