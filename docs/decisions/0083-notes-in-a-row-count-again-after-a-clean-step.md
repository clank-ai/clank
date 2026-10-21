# 0083. A Watch for rule's notes in a row count again from the owner's message and from a step that finished cleanly

- Status: Accepted, as Claude's call; the owner may reverse it
- Date: 2026-10-19
- Decided by: Claude, without the owner (the review of [plan s18](../plans/s18-monitor-watch-for.md), building design
  0012's step 8); it makes [0053](0053-watch-for-rules-run-in-the-service.md)'s cap exact

## Context
Decision 0053 caps "tell the model": "at most twice in a row for the same rule in a session; after that, the rule marks,
pauses and tells the phone" ([design 0012](../design/0012-the-monitor.md) §8). Its default after a loop guard stop is to
tell the model and go on, chosen "so a run left alone goes on"; the alternative it turned down would "stop at its first
loop". Plan s18 counted "in a row" from the owner's own last message alone. The review found what that does to a run
left alone for hours: a loop guard stop at step 1, another at step 41 and a third at step 81, with clean steps between,
are three notes "in a row", so the third pauses the run and calls the owner, though each note worked.

## Decision
- A rule's notes in a row in a session count again from **the owner's own next message** (one that is not a note Clank
  sent), as plan s18 built, **and from a step of the model's that finished cleanly** (no error, not a compaction's
  summary, not undone) after the step the rule's last note was sent on, and before the step of the new mark: the note
  worked for at least a step, so the next one is not in a row with it.
- Where a note was sent from is its mark's step (a call's or a subagent's step for a mark on one of them); the step of
  the mark itself never counts, since the rule fired on it again.
- A note that could not go (decision 0082) is not counted, so it starts no row either.

## Alternatives considered
- **From the owner's message alone** (plan s18 as first built): a run left alone stops at the third loop, however far
  apart, which undoes 0053's reason for telling the model by default.
- **Notes within a span of steps or of time** (three in the last 20 steps, or in an hour): a number neither the design
  nor the owner set; "in a row" already says when the model did not recover.

## Consequences
- The cap still stops a model the notes do not help: stopped at three steps in a row, with no clean step between, the
  third mark pauses the session and tells the phone.
- A rule over a stretch of calls (the same call again, failing again, one file again) marks again only after its streak
  ended, and those calls' steps usually finish cleanly, so its notes rarely reach the cap; its own count and window
  already keep it from noting every call.
- Nothing changes yet: the note itself is design 0012's step 9, and until then the rule tells the phone instead
  (decision 0082).
