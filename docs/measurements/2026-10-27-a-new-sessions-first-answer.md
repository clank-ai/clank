# A new session's first answer (2026-10-27)

A new OpenCode chat often waited 10 to 37 seconds for its first word, while every step after it began in about a second.
This page says what the gateway's records show, why the engine reads the whole prompt again, and a fix tested on this
machine.

## What the records show

Each OpenCode session's first request on 2026-10-26 and 10-27, from the gateway's record of every request
(`logs/traffic/`), times in UTC:

| When | Preset | Prompt, tokens | From the cache | First token |
| --- | --- | --- | --- | --- |
| 10-26 02:24 | frontier 262K fast | 16,901 | 0 | 11.1 s |
| 10-26 06:30 | frontier 262K fast | 17,298 | 0 | 15.5 s |
| 10-26 08:41 | frontier 262K fast | 17,237 | 0 | 12.2 s |
| 10-26 21:09 | frontier 262K | 17,667 | 0 | 33.3 s |
| 10-26 21:11 | frontier 262K | 17,667 | 17,666 | 0.5 s |
| 10-26 21:12 | frontier 262K | 17,654 | 0 | 17.8 s |
| 10-26 21:13 | frontier 262K | 18,056 | 0 | 25.6 s |
| 10-26 22:03 | frontier 262K | 18,348 | 0 | 19.9 s |
| 10-27 00:21 | frontier 262K | 28,771 | 0 | 37.1 s |
| 10-27 02:15 | frontier 262K | 18,348 | 0 | 62.6 s |
| 10-27 02:19 | frontier 262K | 18,348 | 18,347 | 0.4 s |
| 10-27 02:46 | frontier 262K | 18,348 | 18,347 | 1.0 s |

The prompt is OpenCode's system prompt and tools, Clank's instructions, the workspace's `AGENTS.md`, and the first
message. In the owner's SmallWorldMIPT workspace it was 28,771 tokens: 56 tools (71,252 characters, Clank's own about
29,000 of them and the workspace's physics server about 19,000) and a 32,330-character system message. The title
request OpenCode sends with a new session never reaches the engine: the gateway answers it.

## Why

KVMem v0.16.0-rc1 keeps one conversation. For this model, whose 48 linear-attention layers carry a recurrent state, it
can resume only from a snapshot of that state taken at some point of the prompt. It keeps at most four, taken at the
start of the last user message, at the end of the prompt and at the end of the answer, and drops the oldest first
(`tools/kvmem-multimodal-server.h`).

A new session shares the system prompt and the tools with the one before (17,630 tokens here), and nothing after.
When the session before ran a step or two only, one of its snapshots near the start of its first message may still be
kept, and the new session resumes from it: the rows of 0.4 to 1.0 s above, where the first message was even the same.
After a session of a few steps, all four snapshots lie past the shared part, and the engine reads everything again.
Its log says so: `multimodal_reset reason=no_recurrent_checkpoint lcp=17634`.

KVMem's later change `5d1ac0a` ("keep a recurrent checkpoint on the LCP boundary") keeps a snapshot where a
conversation's own prompt changes, and says it "does not add cross-request shared-prefix reuse". Its v0.18 checkpoint
policy (opt-in, experimental) takes one at the system prompt's end among others.

## The fix tested

One more snapshot, kept apart from the four: where the first turn after the system message begins (the second
`<|im_start|>`), taken when a request is read across that point and never the one dropped. It is
[the patch](../models/kvmem-pin-the-system-prompt.patch), on top of the build in
[frontier 262K's page](../models/frontier-262k.md) (it applies after the cherry-pick of `7e20823`).

How it was checked. The patched server was built beside the owner's build: its one changed file compiled with the
build's own flags, linked with the build's other objects and libraries, the owner's build untouched. Each server ran
with frontier 262K's flags on a port of its own, the main slot unloaded meanwhile, and was sent the same recorded
requests, with `max_tokens` 16: the six steps of the session of 21:11, then the first requests of two new sessions
(the one recorded at 21:12, and the same with "yes" for "ok").

| Request | The owner's build | | The patched build | |
| --- | --- | --- | --- | --- |
| | First token | From the cache | First token | From the cache |
| Session, step 1 | 12.85 s | 0 | 11.16 s | 0 |
| Session, steps 2 to 6 | 0.39 to 0.95 s | 17,666 to 18,410 | 0.53 to 0.85 s | 17,666 to 18,410 |
| New session 2 | 10.34 s | 0 | 0.73 s | 17,630 |
| New session 3 | 0.70 s | 17,632 | 0.61 s | 17,632 |

The owner's build reproduces the records (the new session after six steps read all 17,654 tokens again); the patched
build resumed it from the system prompt's end. Each answer began with the model's thinking about the same request.
The extra snapshot holds about 157 MB of system memory (the snapshots' peak was 943 MB against 786 MB), and nothing on
the GPU.

An earlier run sent each session one step only: there both builds resumed every new session (0.5 to 0.6 s), which is
why the order above matters.

## The patch tested before it was built

Before the owner's engine took it, the patch was tested against the build it patches, on the real model with frontier
262K's flags, the main slot unloaded meanwhile. Three builds: the owner's, the patch as first proposed, and the patch
revised by these tests. Each scenario started a fresh server and sent its requests in order: recorded OpenCode
requests, and requests built from the recorded system prompt and tools (files read by a tool, follow-up messages, a
revert into the history). Each was greedy (temperature 0) and 32 tokens long. Every checked answer was compared with
the same request read whole from scratch (`cache_reset`), read twice: all 44 such reads repeated exactly.

| Scenario | The owner's build | The revised patch |
| --- | --- | --- |
| A new session after a session of six steps | 12.21 s, nothing from the cache | 1.02 s, 17,630 from the cache |
| A new session after a second session of six steps | 14.83 s, nothing | 0.92 s, 17,630 |
| Each step of a session | 0.56 to 1.73 s | 0.63 to 1.51 s |
| A conversation reverted into its history, after another conversation ran | resumed from the other's snapshot (row 19,397) | resumed from its own (row 17,632) |
| A request broken off after its pinned snapshot was taken, then sent again | read again whole | read again whole; the broken one's snapshots dropped |
| A session resumed from the pinned snapshot and broken off, then a new session | 1.18 s, from 17,632 | 1.11 s, from 17,632; the pinned snapshot kept |
| A session of 77,789 tokens (past the exact window), then a new session | 0.90 s, from 17,632 | 1.04 s, from 17,632 |
| Requests with no system message (the template adds one of 42 tokens) | the third read again | the third resumed from row 42 |
| Workspaces with other instructions taking turns | each read once | each read once, pinned at its own end |

Neither build failed a request, and the revised patch never kept more than one pinned snapshot and four others. Its
snapshots took at most 750 MiB of system memory over all the scenarios, against 899 MiB for the owner's build, which
kept snapshots of conversations it had left.

The first patch failed the test it was made for: like the owner's build, it resumed the reverted conversation from a
snapshot of the conversation before. Restoring a snapshot left the snapshots past it in place; one taken on another
conversation's rows could then be restored. Here the 3,000 rows read after it pulled the answer back (its first words
matched the reference), but it is the wrong state, and with fewer rows after it the answer would follow it. KVMem's
later checkpoint design says "Restoring a prefix invalidates the edited suffix"; the revised patch drops them so.

The answers. Of 26 checked answers in each build, 22 were the reference's word for word, in the owner's build and in
the revised patch alike. The 4 others began the same thought in other words (for example, "Added a `mean` function"
against "Added the `mean` function"): a request resumed from a snapshot is computed in other batches than one read
whole, and greedy decoding follows the slightly different numbers. For the same reason, read whole, the patched build
answered 5 of 22 requests in other words than the owner's: it reads the system prompt in a batch of its own.

Then through Clank, on the owner's engine rebuilt with the patch, in the benchmark workspace: a session of four steps
(its first request read 18,389 tokens in 16.0 s, its steps began in 0.37 to 0.39 s), then two new sessions, whose first
words came in 0.66 s and 0.51 s, with 18,323 and 18,325 tokens from the cache.

## What it does not change

Two sessions taking turns still read each other's part again: KVMem v0.16 keeps one conversation. A workspace with
other instructions or tools has another system prompt, which its first session reads once. The owner's engine runs
the revised patch since 2026-10-27 (decision [0146](../decisions/0146-kvmem-keeps-a-snapshot-at-the-end-of-the-system-prompt.md)).
