# 0085. A box's first message hands the flow's brief and a map of the flow, before its task

- Status: Accepted
- Date: 2026-10-20
- Decided by: the owner, who chose these additions to a box's first message on 2026-10-20 ("each of the individual
  tasks are brand new sessions that get fresh context windows, but making sure that we are preparing each of these
  tasks with the correct context for the agent at that task to get the work done properly"); where each part goes and
  what the map's lines say, Claude's call while building ([plan s30](../plans/s30-flows-each-box-prepared.md))

## Context
Each box of a flow runs in a new session with none of the history of the boxes before it ([design 0013
§5](../design/0013-flows.md#5-running-a-box-a-fresh-session), decision 0060). Until now its first message held its
type's instructions, its prompt, the files its `sees` lists, what the boxes before it delivered (an INTEGRATE, a
DECOMPOSE's task), its deliverable and *accept when*, and on a later try what happened to the last one. A box whose
`sees` did not list the brief never learned the goal and the limits of the work: a task drafted by a DECOMPOSE lists
the files it needs, rarely the brief. Nor did a box know where it stood: what came before it, and which boxes after it
use what it writes.

## Decision
- **The brief, always.** The flow's brief is the file the first box writes (a flow starts with a YOU, §3; its file is
  usually `BRIEF.md`, the goal and the limits). It is handed to every box a model runs, whether or not its `sees` lists
  it, once: a box whose `sees` also lists it is not handed it twice. It is handed as any file is (§5): whole up to the
  flow's `whole_up_to`, else by its path and size.
- **Where it sits in the flow.** A short map: the flow's title and the run; each box before it, in the order they run,
  on one line with its id, type and title and what it delivered (its files, a VERIFY's verdict, the tasks a DECOMPOSE
  broke the work into, the owner's approval), or that it was skipped or taken as it was; this box, marked, with its
  try; each box after it on one line with its title and, when it uses this box's deliverable, how (it sees or shows a
  file of it, checks it, is told of it, or puts every deliverable together). It orients and carries no history: no
  prompt, no file and no session of another box is in it.
- **The order**, revised in §5: the type's instructions; where it sits in the flow; the brief; its task (its prompt);
  the notes of the boxes before it ([0086](0086-a-box-hands-on-a-short-note.md)); the files it sees, the brief's
  excepted; what the boxes before it delivered; its deliverable, *accept when* and its own note; and, on a later try,
  what happened to the last one. Orientation and the goal come first, the task next, then what it works from, and
  last what it must leave.

## Alternatives considered
- **The brief only when `sees` lists it** (as before): the owner's own boxes would list it, but a DECOMPOSE's tasks
  rarely do, and they are the boxes that most need the goal and the limits.
- **The brief named by its path only**, for the box to read with its tools: shorter, but a model that never opens it
  works without the limits, which a VERIFY then finds broken, a whole try later.
- **A map carrying each box's settings, prompt and history**: a fresh session is fresh because it does not carry the
  history (§5; the model battery of 2026-10-15 did best with one fresh session per task); the map names, it does not
  retell.
- **The map after the task**, or at the end of the message: the instructions already begin "you are one box of a
  flow", and the map continues them, before the box reads what it must do.

## Consequences
- Every first message grows by the brief and by a line a box of the flow: a long brief makes every box's message
  longer, so `clank flow prepare` shows each box's size before the flow runs
  ([0087](0087-a-first-messages-size-is-counted-by-the-engine-else-estimated.md)).
- A VERIFY sees the map too: it names the boxes, not their sessions, so its independence (decision 0063) is kept.
- The owner reads all of it, as always, in the try's `first-message.md` and in the preview.
