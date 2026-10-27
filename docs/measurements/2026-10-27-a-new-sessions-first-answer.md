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

## What it does not change

Two sessions taking turns still read each other's part again: KVMem v0.16 keeps one conversation. A workspace with
other instructions or tools has another system prompt, which its first session reads once. Whether the owner's engine
runs the patch is decision [0146](../decisions/0146-kvmem-keeps-a-snapshot-at-the-end-of-the-system-prompt.md).
