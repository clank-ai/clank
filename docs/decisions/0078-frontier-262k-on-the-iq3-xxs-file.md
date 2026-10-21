# 0078. "frontier 262K" runs the IQ3_XXS file with a 73,728-token window and a prompt batch of 256

- Status: Accepted; supersedes the sizes of [0069](0069-a-frontier-preset-over-262k-with-retrieval.md) (its way of
  working, retrieval past an exact window with a reserve for the longest answer, stands). Superseded in part by
  [0088](0088-frontier-262k-runs-the-iq3-s-file-again.md): "frontier 262K" runs the IQ3_S file again, and this
  preset is kept as "frontier 262K lean"
- Date: 2026-10-19
- Decided by: the owner, who approved the measurement and leaving the best-fitting preset loaded; the choice among
  the measured candidates is Claude's, from the measurement below

## Context
"frontier 262K" as decision 0069 sized it (Swift 1.5 IQ3_S, 57,344 tokens exact, a 40,960 reserve, 98,304 cells)
took 14,598 MiB when it started on 2026-10-18 and left 264-448 MiB of the card free beside the desktop. With
"frontier 96K" the card had come down to 130 MiB free, and Windows had pushed the desktop's own memory out to make room
([the measurement](../measurements/2026-10-18-the-frontier-preset.md)). The research of that day ranked a larger exact
window as the lever for long contexts, and Swift 1.5's IQ3_XXS file as the largest source of room: 1,600 MiB less of
the card for a KL divergence from the BF16 model of 0.0978 against 0.0513.

The measurement of 2026-10-18 compared five candidates with synthetic prompts through Clank's gateway, other
computation using most of the CPU (so writing speeds were about half the quiet desktop's for every
candidate alike).

## Decision
"frontier 262K" runs Swift 1.5's IQ3_XXS file (`swift-1.5-qwen3.8-27b-iq3xxs`) with a budget of 73,728 tokens attended
exactly, a 40,960-token reserve (114,688 cells), q4_0, a prompt batch of 256, thinking without a limit and 32,768
tokens out, over the whole 262,144-token context. It took 13,436 MiB and left 1.18-1.34 GB free beside the desktop at
every prompt size up to 237,085 tokens, and passed all six probes of the long-context harness at about 220,000 tokens.

## Alternatives considered
- **The IQ3_S file at 57,344 exact (decision 0069 as it was):** 264-448 MiB free; at about 220,000 tokens it missed the
  system prompt's rule.
- **The IQ3_XXS file at 98,304 exact (139,264 cells):** 734-926 MiB free, but it wrote more slowly (26-35 tokens a
  second against 30-38) and missed an edit and the rule at about 220,000 tokens.
- **"daily 262K" with a batch of 256:** it fits (546-909 MiB free), but keeps the 4,096-token thinking cap and a 36,864
  window.
- **"frontier 96K" with a batch of 256:** 310-545 MiB free, and OpenCode compacts at about 65,000 tokens.

## Consequences
- The IQ3_XXS file's lower precision is the price: its recall and edits held up on the harness, but the owner's own
  work is the real test. "frontier 262K" with the IQ3_S file is one preset file away if it disappoints.
- Speeds were measured under other CPU load; a quiet-desktop measurement of this preset is due.
