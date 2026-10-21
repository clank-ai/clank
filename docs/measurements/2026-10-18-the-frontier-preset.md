# The frontier preset

**When:** 2026-10-18, the owner present: the file and the estimate checked first, then "frontier 96K" on the GPU from
21:44 (the owner chose "now").

**Question:** what does the setup of the video "How I Got Frontier Performance on 16GB VRAM (Qwen 3.8 27B)" take on
this machine, how much context fits beside its desktop, and how fast does it answer (decision
[0068](../decisions/0068-the-frontier-preset.md))?

## The file

`Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf` from `ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF` at revision
`d74895bbe5db4bec1e0024e7cc87d59c02d7631a`: 12,120,016,896 bytes, its SHA-256 the one the repository publishes
(`9aecf1cd…677e5`), downloaded into the WSL host's Clank folder, where Clank looks for it
(`models/<repository>/<revision's first 12>/<file>`).

gguf's reader found the same 866 tensors, at the same types and shapes, as in the Qwen3.8-27B file of "daily 262K"
(`ISTA-DASLab/Qwen3.8-27B-GSQ-RCO-GGUF`, 64 bytes larger): the same allocation, other weights. Its architecture is
llama.cpp's `qwen35`; its name `Swift15-GSQ-V1MIX-ISTAalloc-IQ3_S MTP`. So the sizes measured on Qwen3.8 hold for it.

## What KVMem allocates

From KVMem v0.16.0-rc1's source and its recorded start (`tests/fixtures/kvmem-llamacpp/v0.16.0-rc1/program.json`):

- **The KV pool**: `kvmem.budget` plus `kvmem.gen_reserve` cells, or the context when the budget is 0
  (`kvmem_compute_pool`); 16 layers, a key and a value of 1,024 values each: 34,816 bytes a token at q8_0, 18,432 at
  q4_0. Capped at half the GPU's memory, which binds past about 245,000 tokens at q8_0.
- **The MTP head's pool**: as many cells as the KV pool, one layer, at f16 unless `--spec-kv-dtype` says otherwise:
  4,096 bytes a token. Its start logs `KVMEM_TRACE mtp_pool cells=53248 ... bytes=218103808` (208 MiB) for the daily
  preset; Clank's estimate left it in the overhead until now.
- **Exact attention**: with a budget of 0, a prompt is attended exactly until it passes 95% of the context (the pool's
  high watermark, `gpu_high_watermark`), where retrieval would begin. An agent that keeps room for its answer stays
  below it: OpenCode compacts at the context less the answer's room.

## What fits beside this desktop

Clank's estimate, as corrected by the start below (its compute buffers grow 5,120 bytes a cell), with the GPU as it was
at 20:30 (15,091 MiB free of 16,303; 1,212 in use by the desktop and other programs). The fixed part is 11,861 MiB
(weights 11,160, recurrent state and the compute buffers' base 277, overhead 424); each cell takes its KV, 4,096 bytes
of the MTP head's pool and 5,120 of compute buffers: 44,032 bytes at q8_0, 27,648 at q4_0.

| Context | KV cache | Per-cell part | Total | To spare |
| --- | --- | --- | --- | --- |
| 57,344 | q8_0 | 2,408 MiB | 14,269 MiB | 822 MiB |
| 65,536 | q8_0 | 2,752 MiB | 14,613 MiB | 478 MiB (tight) |
| 98,304 | q4_0 | 2,592 MiB | 14,453 MiB | 638 MiB |
| 106,496 | q4_0 | 2,808 MiB | 14,669 MiB | 422 MiB (tight) |
| 131,072 | q4_0 | 3,456 MiB | 15,317 MiB | does not fit (226 MiB short) |

With the monitors on the processor's integrated GPU the 5080 would have about 1 GB more free, enough for 131,072 tokens at
q4_0 with about 770 MiB to spare. The video's "about 110,000 tokens at q8_0" does not fit here even then: KVMem's MTP
pool, the compute buffers' growth and its 424 MiB of overhead take what the video's arithmetic leaves.

## Over 262K with retrieval

"frontier 262K" (decision [0069](../decisions/0069-a-frontier-preset-over-262k-with-retrieval.md)) spends the same
98,304 cells otherwise: 57,344 attended exactly and a 40,960-token reserve, over a 262,144-token context whose older
blocks stay in system memory (about 5.6 GiB at q4_0 for the whole context). Its estimate equals "frontier 96K"'s; a
request past the window also allocates retrieval scratch (about 290 MiB at this window, by the source), which only a
measurement after such a request shows.

## On the GPU

"frontier 96K" in the main slot, 2026-10-18 from 21:44, the owner at the PC (they chose "now"), the monitors on the
5080. Requests went through the gateway as the role `bench`, with synthetic prompts only (Python helpers, salted so
nothing was cached; a known math question). The engine's own figures come from its log's `KVMEM_CHAT_TURN` and
`spec_stats` lines.

**The start.** Ready in 11 s. Clank measured 14,453 MiB taken; the estimate said 14,308. The log: weights
11,159.69 MiB, KV 1,728.00 (98,304 cells at q4_0), recurrent state 163.20, compute 594.28 (and 116.28 in system
memory), the MTP head's pool 384 (402,653,184 bytes, f16), budget 98,304 (the whole context), `rbudget=-1`. The
compute buffers took 220 MiB more than at 53,248 cells: 5,120 bytes a cell, which the estimate now counts
(`compute_bytes_per_cell`), so it says 14,453.

**Speed, the desktop quiet** (a prompt read cold, about 250-500 tokens written, thinking on):

| Prompt | Reading | Writing | MTP drafts accepted |
| --- | --- | --- | --- |
| 7,994 | 1,520 tokens a second (5.3 s) | 78.8 tokens a second | 86% |
| 27,710 | 1,601 (17.3 s) | 79.2 | 87% |
| 32,939 | 1,526 (21.6 s) | 74.4 | 83% |
| 66,566 | 1,274-1,376 (48-52 s) | 54.9-66.5 | 86% |
| 94,015 | 617-633 (149-152 s) | 25.3-27.0 | 81-86% |

**Past 95% of the context KVMem changes path.** At 94,015 tokens (95.6% of 98,304) the log says
`path=query_replay reason=selection_or_attention_view_changed` instead of `path=all_resident`, though every block stayed
on the GPU (`n_host=0`): reading halves and writing falls to a third, the same in two runs. OpenCode compacts at
98,304 less 32,768 tokens, so its prompts stay below the mark.

**Speed, the desktop busy.** At 21:58 the same 8K prompt read at 492 tokens a second and wrote at 36.7; Windows'
counters gave the desktop's compositor 2,323 MiB of the card and the WSL machine 15,234 MiB plus 1,054 MiB of shared
memory, with 15,854 MiB of 16,303 in use. Desktop activity costs about half the speed, as on 2026-10-08 and 10-11.

**Thinking.** AIME 2025 I problem 1 (answer 70) at each effort: right every time, in 995 tokens at `low`, 981 at
`medium` and 912 at `xhigh` (1,015, 1,144 and 1,688 characters of thinking), 25-32 s, the desktop busy. Too easy to
tell the efforts apart; Swift 1.5 thinks briefly here.

**An answer past the old limit.** Copying 5,500 random codes back (thinking off; a prompt of 38,418 tokens), the model
wrote all 30,000 tokens it was allowed and stopped at the limit (`finish=length`), with no error at 16,384 or after:
with a budget of 0 an answer takes the pool's free cells, not the 16,384-token reserve. It copied 4,297 codes, 4,296 in
their place. But it wrote at 16.8 tokens a second (31 minutes), each MTP step taking 179 ms against 44 ms at 66K in the
speed table, though 99% of drafts were accepted. Afterwards Windows gave the WSL machine 15,200 MiB of the card, 747 more
than at the start, with 476 MiB left free; KVMem's recurrent-state checkpoints (786 MB for this conversation) are in
system memory, so the growth is the engine's other buffers, allocated as the context grows. Whether the slowness came
from that growth crowding the card, from the desktop's load, or both, is not settled: it needs a run with the desktop
quiet, reading the memory counters as it goes.

## The comparison

2026-10-18 to 2026-10-19, about five and a half hours, with no one at the computer (a runner started each step only
after 15 minutes without input), but other computation used 43-100% of the CPU throughout, so writing speeds are about
half the quiet desktop's for every candidate alike; memory figures are unaffected. Each candidate was loaded through
Clank, timed on cold synthetic prompts (512 tokens out), and run through the long-context harness of 2026-10-08
(synthetic OpenCode-like sessions: three edits, a rule of the system prompt, a recall from the middle, a detail of the
last step; one repetition). "Free" is nvidia-smi's, beside the desktop and the driver's 326 MiB.

| Candidate | Took | Free | Writing, 8K to 237K | Reading, 8K to 237K | Harness at ~118K | Harness at ~220K |
| --- | --- | --- | --- | --- | --- | --- |
| IQ3_XXS, 73,728 exact + 40,960 reserve, batch 256 | 13,436 MiB | 1,182-1,337 MiB | 38.3 to 31.7 | 998 to 544 | 4 of 6 (two edits missed) | 6 of 6 |
| IQ3_S, 57,344 + 40,960, batch 256 | 14,598 MiB | 264-448 MiB | 43.6 to 33.2 | 981 to 576 | 3 of 6 | 5 of 6 (the rule missed) |
| IQ3_XXS, 98,304 + 40,960, batch 256 | 14,080 MiB | 734-926 MiB | 34.8 to 25.8 | 973 to 501 | not run | 4 of 6 |
| "daily 262K", batch 256 | 14,259 MiB | 546-909 MiB | 45.1 to 30.1 (to 172K) | 885 to 716 | not run | not run |
| "frontier 96K", batch 256 | 14,594 MiB | 310-545 MiB | 45.0 to 28.0 (to 94K) | 926 to 858 | not run | not run |

The first was "frontier 262K" from decision [0078](../decisions/0078-frontier-262k-on-the-iq3-xxs-file.md), and is
"frontier 262K lean" since decision [0088](../decisions/0088-frontier-262k-runs-the-iq3-s-file-again.md); "frontier
262K" is again the second's file and sizes, with KVMem's own batch of 512. A batch of 256 cut the compute buffers by
105 MiB at 98,304 cells (489.27 against 594.28 MiB). Its estimate was 13,426 MiB against the 13,436 it took. Still due:
its speed on a quiet desktop, and how it does in the owner's own work.

## In the owner's work

2026-10-19 and 10-20, "frontier 262K" as decision
[0069](../decisions/0069-a-frontier-preset-over-262k-with-retrieval.md) sized it (the IQ3_S file, 57,344 tokens exact,
a 40,960 reserve, KVMem's own batch). Its engine's log:
`model=Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf kvmem=1 method=retrieval n_ctx=262144 spec=draft-mtp n_max=3
think=1 rbudget=-1 qmax=512`, an MTP pool of 98,304 cells. Counts only, from the gateway's records; nothing else of the
owner's work was read.

| Session | Steps | Largest prompt | Read from KVMem's cache |
| --- | --- | --- | --- |
| 1 | 69 | 123,346 tokens | about 99% |
| 2 | 54 | 141,628 | about 99% |
| 3 | 143 | 245,411 | about 99% |
| 4 | more than 250 | 228,232 | about 99% |

- **Writing**: 57 tokens a second at 245,411 tokens of context, against about 79 at the start of a session (the speed
  table above, below the window, where it attends as "frontier 96K" does).
- **The card**: 15,753 of 16,303 MiB in use with it loaded, the desktop included.
- **Compacting**: OpenCode compacted session 4 from 228,232 tokens to 37,516, and it went on. Session 3 failed at the
  context limit, because OpenCode compacted too late: its step 143 ended at 245,725 tokens, and its next prompt of
  246,931 tokens, with 16,384 for the answer, passed 262,144. The engine refuses a prompt whose tokens plus the
  answer's `max_tokens` pass its context.
- **The owner's verdict** (2026-10-20): "The model is working extremely well, and I am unaware of a better model working
  on a 16GB gpu at the moment"; the default stays this file (decision
  [0088](../decisions/0088-frontier-262k-runs-the-iq3-s-file-again.md)).
