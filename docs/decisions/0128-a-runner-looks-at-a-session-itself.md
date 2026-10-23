# 0128. A flow's runner reads a session's status itself every minute, and the watch opens a stream again after its instance ended

- Status: Accepted (Claude's call, from the first long run of 2026-10-22); revises design 0013 §5's "Nothing polls"
- Date: 2026-10-22
- Decided by: Claude, after the run's sessions ended unheard

## Context
- In the first long run, the PLAN wrote its plan and ended after 25 minutes; the runner waited for
  its limit of 30 and failed it. The orchestrator's checkpoint ended after 91 seconds; the runner waited for its 20.
  The run's sessions counted 0 tokens written: the runner heard nothing of them.
- Measured the same day on the flow's own OpenCode server (1.19.0): after `server.instance.disposed`, OpenCode keeps
  the event stream open but sends nothing more on it; only a stream opened after hears the new instance. The bridge's
  watch expected the stream to end with its instance, and kept the silent one.

## Decision
- **The watch opens the stream again** when it hears `server.instance.disposed`; on opening it reads which sessions
  run, so one that ended meanwhile is said idle (as after a stream that ended).
- **The runner reads a session's status itself** through the bridge every minute while a box or a checkpoint works
  (`LOOK`), and takes its end from there should the watch not say it. Only an end is taken; a server gone is the
  watch's to say.

## Alternatives considered
- **Only the watch's fix**: the next way OpenCode changes its stream would leave runs waiting for their limits again,
  with nothing said; a read a minute costs one `docker exec` and finds the end within a minute.
- **Reading every few seconds**: a `docker exec` each time, for an end the watch says at once when it hears it.

## Consequences
- A box whose end the watch misses ends within a minute of its session, not at its limit.
- The tokens a box writes are still counted from the watch only; a silent watch leaves its token limit unchecked
  until the stream is open again.
