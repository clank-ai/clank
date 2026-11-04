# 0158. No thread waits for the event loop

- Status: Accepted (the audit of 2026-10-30, reproduced); revises design 0002 §2.3
- Date: 2026-11-04

## Context

- The service's API, its event streams, its operations and the flows' runner live on one event loop. Watcher threads,
  operations' threads and the routes' worker threads record events and answer questions.
- Each open stream (the API's, the agent panel's, the phone's) heard an event on the thread that recorded it, and
  handed it to the loop with AnyIO's `from_thread.run_sync`, which waits until the loop has taken it. The operations'
  waiters and the flows' runner did the same.
- So every recording thread waited for the loop once per open stream, and stalled whenever the loop was busy. Worse, a
  thread holding a lock waited for a loop that was waiting for that lock: review mode asks its question and records its
  event under its lock, on a watcher thread, while the flows' runner takes that lock on the loop at every box start and
  end. Both waited for good, and with them the API, every client and `clank stop`. A test reproduces it.

## Decision

- **Work is handed to the loop without waiting** (`kernel/handoff.py`, `Handoff`): made on the loop, its `call`
  schedules the work there (`call_soon_threadsafe`) and returns at once; on the loop's own thread it runs at once. The
  loop runs what is handed over in order.
- **The three streams, the operations' waiters and the flows' runner use it.** A stream's `put` catches what it
  expects (a full buffer says the client fell behind, as before). The runner's nudge no longer needs a thread of its
  own to avoid waiting.
- **A test refuses `from_thread.` anywhere in the package**, so new code hands work over the same way.

## Alternatives considered

- **Ask review mode's question and record its event after releasing its lock**: it removes this one cycle, not the
  stall, and the next lock held while recording would freeze the service again. It remains worth doing for review
  mode's own sake, with an "asking" state that keeps the order.
- **A thread per delivery** (what the runner's nudge did): it never waits, but it costs a thread per event per stream
  and loses the order.

## Consequences

- Recording an event costs the same with ten streams open as with none, and never freezes a thread.
- A stream that falls behind (1,000 events not yet sent) is told to reload, as before; nothing else changes for
  clients.
