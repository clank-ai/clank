# 0069. A second frontier preset keeps 262K of context: 57,344 tokens exact, the rest retrieved, a reserve for the longest answer

- Status: Accepted; its sizes superseded by [0078](0078-frontier-262k-on-the-iq3-xxs-file.md), then restored by
  [0088](0088-frontier-262k-runs-the-iq3-s-file-again.md)
- Date: 2026-10-18
- Decided by: the owner ("is there any way that we could get a larger context window with some kind of 'merge' of
  kvmem and swift 1.5?"; "can we go for even larger context windows by using my system memory without dramatically
  slowing the model down? We need to explore every avenue"); its sizes are Claude's, from KVMem's source and Clank's
  estimate, and the measurement checks them

## Context
"frontier 96K" (decision [0068](0068-the-frontier-preset.md)) attends to its whole context exactly, so OpenCode compacts
a session once it nears 98,304 less the answer's 32,768 tokens. The owner's agent prompts of 2026-10-13 to 10-18 (721
requests, read as sizes only) had a median of 47,653 tokens; 43% were above 65,536 and 29% above 98,304; the median of
2026-10-18 was 118,549. On "frontier 96K" most of those sessions would have been compacted, their older steps replaced
by a summary.

KVMem was built for this: it keeps the whole KV cache in system memory and attends exactly to a window on the GPU,
retrieving older blocks by their likeness to the last user message. The owner's study of 2026-10-08 found its retrieval
near-lossless for recall at 57K-183K tokens with a 36,864-token window. Its source at v0.16.0-rc1 (read on 2026-10-18)
says:

- **Quantized caches work with retrieval**: blocks move between the GPU and system memory as raw bytes at the cache's
  row size, and blocks are scored by keys taken from the activations before quantization (f32). K and V must share a
  type.
- **An answer must fit its reserve**: once older context has been retrieved, the working set is pinned and new tokens
  take only free slots of the generation reserve; when none is left the request fails ("no free GPU slot for block N").
  Nothing in KVMem checks `max_tokens` against the reserve, and versions 0.17 and 0.18 behave the same.
- **System memory**: the whole 262,144 tokens take about 5.6 GiB at q4_0 in the host store; WSL may use 48 GB here.

## Decision
- **The preset "frontier 262K"** (`frontier-262k.json`): Swift 1.5 on KVMem v0.16.0-rc1 as in "frontier 96K"
  (thinking without a limit, 32,768 tokens out, q4_0, MTP, no projector), but over the whole 262,144-token context:
  a budget of 57,344 tokens attended exactly and a reserve of 40,960. Its 98,304 cells take the same GPU memory as
  "frontier 96K"; below 57,344 tokens of prompt the two attend alike.
- **Clank refuses a KVMem preset with a budget whose `max_output` is more than its reserve** (0 meaning KVMem's own
  256), with a sentence that says why. "daily 262K" pairs 16,384 with 16,384 and passes.

## Alternatives considered
- **q8_0 instead of q4_0**: the same memory gives a window of about 23,800 tokens beside a 32,768 reserve, smaller than
  the daily preset's 36,864.
- **A reserve of exactly 32,768**: a window of about 65,000 tokens, but each agent step past the window then needs its
  new tokens plus the answer to fit the reserve, or KVMem retrieves and replays on every step; 40,960 leaves 8,192
  tokens for a step's new tool results.
- **Only "frontier 96K"**: exact attention throughout, but most of the owner's long sessions would be compacted.
- **Bigger contexts by other means** (weights or KV in system memory, smaller files, other engines, pruning old tool
  output): being researched on 2026-10-18; each that holds up gets its own decision.

## Consequences
- The measurement of 2026-10-18 ([the frontier preset](../measurements/2026-10-18-the-frontier-preset.md)) compares
  the two presets: recall and edits past the window (the study harness of 2026-10-08), speed, and GPU memory after a
  request past the window (retrieval allocates its scratch then: about 290 MiB at this window, by the source).
- Which of the two the main slot runs is the owner's choice; each is one `clank model switch` away.
- An answer longer than 40,960 tokens would still fail mid-answer; OpenCode is told its output limit is 32,768.
