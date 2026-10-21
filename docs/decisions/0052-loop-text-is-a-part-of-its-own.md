# 0052. Loop text in the context is a part of its own

- Status: Accepted (the owner approved design 0012 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving design 0012 ("Approve all three"), §4.3's Choice as recommended

## Context
Boards A and C draw loop text as a part of the context window's bar ([design 0012](../design/0012-the-monitor.md)
§4.3). An answer the loop guard stops does not stay in the context: OpenCode leaves an answer that ended in an error
out of every later request ([decision 0040](0040-the-gateway-stops-an-answer-that-repeats-itself.md)). So loop text
that stays is a repeat the guard does not catch (a longer or a reworded one), which runs to the answer's limit and is
kept, as board B's step 22 was before the guard existed; or the same call made again across steps.

## Decision
Loop text is a part of its own in the bar, taken out of the part it came from:

- a kept item that compresses as far as a loop over its whole length, by the guard's own measure and share
  (`clank/components/gateway/loops.py`);
- the tool result that echoes it;
- the third and later identical call in the last twelve.

Each item's details say why it counts.

## Alternatives considered
- **No part of its own, only a mark on the items**: the bar would not show how much of the window repeats take, and
  "Could be freed" (§4.6) could not offer the loop text as room to free.

## Consequences
- One measure of a loop serves the guard and the bar. An ordinary item that compresses as far (decision 0040 names a
  list of 900 zeros) counts too, its details saying why.
- Dropping the loop text clears the results that echo it; the looping call itself stays, since a drop only clears tool
  results ([0056](0056-undo-takes-back-the-last-step-drop-only-clears.md)).
- It is built with the other parts, in step 12; its tests find loop text by the guard's measure over whole items.
