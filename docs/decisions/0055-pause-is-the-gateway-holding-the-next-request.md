# 0055. Pause is the gateway holding the session's next model requests until the owner resumes

- Status: Accepted (the owner approved design 0012 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving design 0012 ("Approve all three"), §9.4's two Choices as recommended

## Context
The Guide offers "pause after this step" ([design 0012](../design/0012-the-monitor.md) §9.4), and a Watch for rule
can pause a session ([0053](0053-watch-for-rules-run-in-the-service.md)). OpenCode cannot pause, and it reads its
rules only when a run starts. It gives up on a model request after 300 s without headers or bytes, and then retries
(OpenCode's `provider/provider.ts`).

## Decision
- `p` marks the session paused in the gateway. The request in flight finishes, OpenCode runs that step's calls, and
  the session's next model request, and any of its subagents' (by `x-parent-session-id`), is **held**.
- The gateway answers a held request **at once** (200, an event stream) and sends a **comment line** well within every
  300 s. The same keep-alive serves the slot's own wait while it starts (`hold_seconds`).
- The hold lasts **until the owner resumes** (`p` again); the held request then goes to the engine. The pause belongs
  to the session in the gateway, so a held request that a timeout broke is held again when OpenCode asks again.
- **A note while held**: the gateway closes the held request (OpenCode drops that empty step), the note is sent, and
  the request that carries it is held until the owner resumes. A compaction asked for while held waits too.
- Once the 200 has gone out, an engine failure can only be told inside the stream, so the gateway words it on
  purpose, to be retried or not.
- **The fallback**: Clank stops the run at the step's end (OpenCode's `abort` when the step finishes), and a note
  continues it.

## Alternatives considered
- **Stopping the run at the step's end**: OpenCode shows it as a stop, and it costs up to a reading of the prompt
  already begun; a hold stops nothing, holds subagents too, and OpenCode's own terminal still shows the session
  working. It stays the fallback.
- **A hold limited by a setting, then a stop at the step's end**: a pause the owner set would end without the owner.

## Consequences
- That comment lines keep OpenCode waiting past 300 s, and for an hour, is measured before step 11; if they do not,
  the fallback serves.
- The gateway keeps a state per session that outlives a request.
- In the flow, a hold is a band on the main line ("⏸ held by you 12:22 to 12:25"); its states are pausing after this
  step, held (with a timer), and resumed.
