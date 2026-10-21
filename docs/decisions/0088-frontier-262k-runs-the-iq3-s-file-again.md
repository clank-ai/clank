# 0088. "frontier 262K" runs the IQ3_S file again, as decision 0069 sized it; the IQ3_XXS preset stays as "frontier 262K lean"

- Status: Accepted (the owner's decision). Supersedes the part of
  [0078](0078-frontier-262k-on-the-iq3-xxs-file.md) that put the IQ3_XXS file in "frontier 262K" (its preset stays,
  as "frontier 262K lean"), and restores the sizes of [0069](0069-a-frontier-preset-over-262k-with-retrieval.md)
- Date: 2026-10-20
- Decided by: the owner, from real use. Of the IQ3_S preset they ran: "The model is working extremely well, and I am
  unaware of a better model working on a 16GB gpu at the moment." Then: "Good, keep IQ3_S as the default."

## Context
Decision 0078 (2026-10-19) moved "frontier 262K" to Swift 1.5's IQ3_XXS file, with 73,728 tokens exact, a 40,960
reserve and a prompt batch of 256. The measurement of 2026-10-18 chose it because it left about 1.2 GB of the card free,
where the IQ3_S pool left 264-448 MiB. The price was precision: a KL divergence from the BF16 model of 0.0978 against
0.0513. Its consequences said the owner's own work was the real test, and that the IQ3_S file was one preset file away.

The owner's copy of Clank kept running the preset of decision 0069: the IQ3_S file, 57,344 tokens exact, a 40,960
reserve, KVMem's own batch. Its engine's log said so:
`model=Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf kvmem=1 method=retrieval n_ctx=262144 spec=draft-mtp n_max=3
think=1 rbudget=-1 qmax=512`, with an MTP pool of 98,304 cells. Updating that copy from main would have swapped the
owner's model without asking.

On 2026-10-19 and 10-20 that preset carried four long OpenCode sessions, of 69 to more than 250 steps, with prompts up
to 245,411 tokens, about 99% of each read from KVMem's cache
([the measurement](../measurements/2026-10-18-the-frontier-preset.md#in-the-owners-work)).

## Decision
- **"frontier 262K"** (`frontier-262k.json`) is decision 0069's preset again, value for value: Swift 1.5's IQ3_S file
  (`swift-1.5-qwen3.8-27b`) on KVMem v0.16.0-rc1, a context of 262,144 tokens, `kvmem.budget` 57,344,
  `kvmem.gen_reserve` 40,960, `kv.type` q4_0, `max_output` 32,768, `thinking.budget` -1, and KVMem's own prompt batch
  (512).
- **"frontier 262K lean"** (`frontier-262k-lean.json`) is decision 0078's preset, unchanged but for its name: the
  IQ3_XXS file, 73,728 tokens exact, a 40,960 reserve, a batch of 256. It is for when the GPU needs room.

## Alternatives considered
- **Keep the IQ3_XXS file in "frontier 262K"** (decision 0078): about 1 GB more room, and 6 of 6 probes at about
  220,000 tokens against 5 of 6. But it is the less precise file, and the owner, after long sessions on the IQ3_S
  preset, chose that one.
- **The IQ3_S file with a batch of 256** (the second row of that comparison): 105 MiB less of compute buffers.
  It is not what ran in the owner's work, so it would be a change to measure on its own.
- **Remove the IQ3_XXS preset**: its room is measured and real; a busy desktop can need it.

## Consequences
- The default leaves little of the card beside the desktop. With it loaded the card had 15,753 of 16,303 MiB in use,
  the desktop included. A busy desktop or a video on the same GPU halves decoding. When the card is needed elsewhere,
  "frontier 262K lean" is one `clank model switch` away.
- One of the four sessions failed at the context limit, because OpenCode compacted too late: KVMem refuses a prompt
  whose tokens plus the answer's `max_tokens` pass its context. The margin Clank gives OpenCode is being fixed on its
  own (the context margin fix).
- The tests now say that the shipped "frontier 262K" is the IQ3_S file at 57,344 + 40,960, and "frontier 262K lean"
  the IQ3_XXS file at 73,728 + 40,960 with a batch of 256.
- The quiet-desktop measurement decision 0078 called for is still due, for both presets.
