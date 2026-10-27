# 0146. KVMem keeps a snapshot at the end of the system prompt, for the next session

- Status: Proposed
- Date: 2026-10-27
- Decided by: the owner, to answer: "Should frontier 262K's KVMem build carry the patch that keeps a snapshot at the
  end of the system prompt, and should the change be offered to KVMem?"

## Context

A new OpenCode chat waited 10 to 37 seconds for its first word on this machine (62 s once), while each later step
began in about a second ([the measurement](../measurements/2026-10-27-a-new-sessions-first-answer.md)). KVMem
v0.16.0-rc1 resumes a hybrid model like Swift 1.5 only from a snapshot of its recurrent state, keeps four, and drops
the oldest first. After a session of a few steps none lies within the 17,000 to 29,000 tokens a new session shares with
it (OpenCode's system prompt, its tools, Clank's instructions), so the new session reads them all again.

Clank's build of KVMem carries one change of its own today, the cherry-pick of `7e20823` for long tool results
([frontier 262K](../models/frontier-262k.md)); its page says nothing else in the engine's source is changed.

## Decision

Proposed: build the KVMem that frontier 262K runs with [the patch](../models/kvmem-pin-the-system-prompt.patch), after
the cherry-pick, and offer the change to KVMem's project. The patch keeps one more snapshot, apart from the four and
never dropped for them: where the first turn after the system message begins, taken when a request is read across that
point. A new session with the same system prompt and tools resumes there.

Measured on the same recorded requests: after a six-step session, a new session's first token came in 0.73 s from
17,630 tokens of cache, against 10.34 s from none.

## Alternatives considered

- **Keep the build as it is.** Every new chat after a session of a few steps waits for its system prompt again: 10 to
  37 s here, more on a busy desktop.
- **KVMem v0.18 and its checkpoint policy.** Its experimental `spread` policy takes a snapshot at the system prompt's
  end among others, and it can keep several conversations. It is 386 commits past the build measured here, with new
  flags and a new driver, and was not measured on this machine.
- **Fewer tools for the agent.** Clank's own tools are about 29,000 characters of the prompt; offering the flow and
  Notion tools only where they are used would save about 4,000 tokens, 3 to 5 s of the wait, not the wait.
- **A warm-up request from the gateway.** In an engine that keeps one conversation it would erase the running
  session's snapshots, so the session would read everything again at its next step.

## Consequences

- A new session starts in under a second after the first in a workspace, whatever ran before with the same system
  prompt; two sessions taking turns still read each other's part again.
- About 157 MB more of system memory for the extra snapshot; nothing more on the GPU.
- The build has a second local change: `clank engine adopt` records it, and frontier 262K's page gains a step.
- Until KVMem takes the change or an equivalent, each new KVMem release needs it again.
