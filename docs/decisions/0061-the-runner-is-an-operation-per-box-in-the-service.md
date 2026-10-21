# 0061. The runner is an operation per box in the service; one flow runs at a time; nothing starts again on its own

- Status: Accepted (the owner approved design 0013 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving [design 0013](../design/0013-flows.md) ("Approve all three")

## Context
A flow runs for hours through sessions, model switches and gates, followed from the console, VS Code and the phone.
Every box uses the main slot, and KVMem holds one conversation at a time (its source, read 2026-10-18). A restart of
the service, or an edit to a finished box, must neither lose a gate nor repeat work the owner did not ask for.
[Design 0013 §6](../design/0013-flows.md#6-the-runner-an-operation-of-the-service) places the runner.

## Decision
- The flows component (`clank/components/flows/`) runs flows in the service, behind its `/flows/` routes, so closing
  a client stops nothing and every client shows the same state.
- A run is a readable JSON file in the run's folder: the flow's version, each box's state (waiting, running, done,
  failed, stale) and tries, where the run is, its deliverables' fingerprints, and what waits for the owner.
- Each box's work is an operation, `flows.box` (design 0002 §2.4), with the steps *model*, *server*, *session*, *work*
  and *collect*; every step but *session* is safe to run again.
- Gates, YOU boxes and proposals are questions, asked outside any operation (design 0002 §2.5).
- One flow runs at a time: a second one started waits, and the Flow view says behind which.
- The owner's controls: pause (no box starts; the running one goes on), stop (the running box's session is stopped,
  a failed try), and run from here (the chosen box and every box after it run again, as new tries).
- After a restart, a box's operation is *interrupted*, then reconciled through the bridge: a session still working is
  followed, one that ended is collected, one that is gone (the container stopped) fails the box. No session is ever
  started again on its own, and an edit to a finished box marks the boxes after it stale without rerunning them (§8).
- Each step is an event with its actor (the owner through a client, auto-accept, the runner); no event holds the text
  of a prompt or a deliverable.

## Alternatives considered
- **A runner in a client.** Closing the client would stop the flow, and clients would show different states.
- **Flows side by side.** They would evict each other's conversation and switch models back and forth; they wait for
  a second provider.
- **A gate as an operation waiting for the owner.** An operation cut short by a restart is interrupted; a question
  survives a restart.
- **Starting a session again after a restart, or rerunning stale boxes.** Either repeats work the owner did not ask
  for; the owner runs again from a box (`r`) or keeps what is there.

## Consequences
- A gate asked before a restart still waits after it, and a restart never makes a box's work run twice.
- The Operations page shows each box's step ("4 of 5: work"), and the run log of board D1 is the events.
- A run is a file beside what it made, as Notion's batches are (design 0010 §5); its operations, questions and events
  are state in the database ([decision 0014](0014-state-in-sqlite-settings-in-files.md)).
- `clank flow list|show|check|run|pause|stop` and `clank flow proposals|accept|reject` serve scripts and back up the
  view.
