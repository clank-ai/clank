# KVMem and a tool result larger than its GPU budget (2026-10-15)

The owner saw the agent's requests fail on long prompts (about 68K tokens). This is what failed, why, the fix applied
to the KVMem build Clank uses on this machine, and how it was checked.

## What failed

The engine's log of 2026-10-15 (`logs/processes/main-22.log`) holds the failing request: an OpenCode session whose
last user message sat at about token 16,000, followed by one tool result of about 52,000 tokens (68,159 in all). The
engine answered HTTP 500, `multimodal query replay failed or cancelled` <!-- spelling: keep (KVMem's own words) -->
after these lines:

```text
KVMEM_TRACE mandatory_trim policy=topk kept=287 dropped=121 budget=288
KVMEM_TRACE multimodal_decode context=... rows=[16116,16628) model_pos=16116 image=0 replay=1
kvmem_fill_slot_info: block 125 has no GPU slot (pos 16116)
```

It was not a crash: the server kept running, and the same session had reached 227,730 tokens earlier that day, its
history growing a little at a time.

## Why

KVMem v0.16.0-rc1 reads a request's new rows once, picks the history blocks to keep on the GPU (`daily 262K`: 288
blocks of 128 tokens, 36,864 tokens), then replays the rows from the user's message to the end of the prompt with
that selection. The replay needs every one of those rows on the GPU at once. When one append is larger than the
budget (here 52,043 rows), the selection drops the oldest of them, and the replay fails on the first dropped block. A
check existed only for prompts with images (`multimodal_validate_capacity` returns early for text).

## The fix

Upstream KVMem fixed it in commit `7e20823` ("fix: handle multimodal query replay exceeding KV budget", in v0.17.0):
the selection keeps the newest rows first, and when any replay block was dropped the replay is skipped, keeping the
first pass's recurrent state, logits and MTP carry (`path=query_replay_skipped reason=replay_exceeds_budget`). It was
cherry-picked onto the adopted checkout (`~/src/kvmem-llama.cpp` in `Ubuntu-22.04`, db4bc22), its one conflict
resolved to v0.17.0's form with v0.16's logging (`fprintf` for `kvmem_diag`), and the server rebuilt (11 s). The change
is uncommitted in the checkout, beside its earlier local changes; it is also saved as `~/kvmem-replay-fix-7e20823.patch`,
and the build before it as `build/bin.before-replay-fix`.

## How it was checked

A synthetic request through the gateway (role `agent`): a short question, one tool call, and a tool result of 2,600
rows of made-up trajectories (95,294 tokens in all), then an ordinary short request.

| Build | Long tool result | Short request |
| --- | --- | --- |
| Before (db4bc22) | HTTP 500 after 95 s, `multimodal query replay failed or cancelled` <!-- spelling: keep (KVMem's own words) --> | answered, 3 s |
| With the fix | answered (`query_replay_skipped`), prefill 79 s, then 48 tokens/s | answered, 2 s |

With the fix the model answers, but about the data rather than the question: with 36,864 of 95,294 tokens on the GPU,
a question 95,000 tokens back carries little weight. So an agent should not read huge outputs whole: ask it to
summarize a log or a data file with a command (`tail`, `grep`, a short script), which the walkthrough says too.

## Later

KVMem v0.17.0 (source only for llama.cpp) carries this fix and much more (several conversations at once, `--parallel`
up to 4); moving to it is its own step: a new version for the adapter, a rebuild, and these checks again.
