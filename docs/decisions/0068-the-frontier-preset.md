# 0068. The frontier preset: Swift 1.5 at its template's own reasoning effort, thinking without a limit, the whole context attended exactly

- Status: Accepted
- Date: 2026-10-18
- Decided by: the owner, who asked for the setup of the video "How I Got Frontier Performance on 16GB VRAM (Qwen 3.8
  27B)" ("I am interested in replicating exactly what is done in this video"; "the thinking budget and output limit on
  the local model that we have set up is actually really bad ... prioritize getting setup with this new 'frontier
  level' local model setup for my 5080"); its sizes for this machine are Claude's, from Clank's estimate, and the
  measurement checks them

## Context
The preset the main slot ran, "daily 262K", was the prototype's daily profile: Qwen3.8-27B (IQ3_S, GSQ-RCO, with its MTP
head) on KVMem, 36,864 tokens attended exactly and the rest of a 262,144-token context retrieved, thinking cut at 4,096
tokens (`--reasoning-budget 4096`), answers cut at 16,384.

The video's argument: Qwen3.8-27B's published scores (34 on the Artificial Analysis index, above three of February's
frontier models) exist only at its highest reasoning effort, `xhigh`, which its chat template picks when a request sets
none; at that effort a hard question takes about 15,000 thinking tokens on average (GPQA Diamond). A budget that cuts
thinking short throws that away. Its setup for a 16 GB card:

- Swift 1.5 (UkisAI): Qwen3.8-27B retrained to stop re-checking what it has settled, which thinks about 42% less on
  GPQA Diamond at the same score; the GSQ-RCO IQ3_S file with the MTP head, 12.12 GB.
- The reasoning effort left at the template's default (`xhigh`); used as a dial: low for quick jobs.
- No limit on thinking; the vision projector skipped; MTP on.
- The largest context that fits: about 110,000 tokens with an 8-bit KV cache, 128,000 with a 4-bit one.
- The monitor on the integrated GPU, to give the card's 1-2 GB of desktop memory to the context.

On this machine the RTX 5080 drives the monitors (1.2-1.3 GB in use). Clank's estimate (weights 11,160 MiB, buffers 537,
overhead 424, the MTP head's pool 4,096 bytes a token, what the last launch learned) leaves room for about 64,000 tokens
at q8_0 or about 110,000 at q4_0, with Clank's 500 MiB to spare. An agent keeps room for the longest answer: with
32,768 tokens kept for it, 64,000 would leave about 31,000 for the prompt, of which OpenCode's own instructions and
tools take 9,000-17,000. The desktop's share of the card also rises with a video or a stream, and once pushed part of
the model into system memory (10 tokens a second until a restart).

Swift 1.5's file holds the same 866 tensors at the same types as the Qwen3.8 file the daily preset runs (compared on
2026-10-18), so the sizes Clank measured carry over. It has no vision projector. Its license is UkisAI's Swift Open
License v1.0, not Apache.

## Decision
- **Swift 1.5 in the catalog** (`swift-1.5-qwen3.8-27b`): its IQ3_S file with the MTP head, at the repository's
  revision, size and SHA-256.
- **The preset "frontier 96K"** (`frontier-96k.json`), on KVMem v0.16.0-rc1: a budget of 0, so the whole 98,304-token
  context is attended exactly; a q4_0 KV cache; thinking without a limit; 32,768 tokens out; the reasoning effort not
  set, so the template's `xhigh`; MTP with 3 draft tokens; no projector; CUDA graphs off. 98,304 is the largest step
  of 8,192 tokens that leaves about 750 MiB to spare beside this desktop.
- **KVMem's estimate follows KVMem**: with a budget of 0 its pool is the context, with no reserve beside it; with MTP
  on, the MTP head's own pool (f16, one layer) grows with it. The sizes of Qwen3.8 move that pool out of the overhead,
  so its estimate is unchanged.
- "daily 262K" stays as it was. Which preset the main slot runs is the owner's choice.

## Alternatives considered
- **An 8-bit KV cache at about 64,000 tokens**, the video's first choice: too little room beside this desktop for an
  agent's prompt once its answer has its room.
- **Swift 1.5 on KVMem with retrieval** (262,144 tokens, an exact window): KVMem v0.16 fails a request whose answer
  outgrows its generation reserve, so 32,768-token answers need a reserve of as many tokens, about 1 GB of the card; and
  it is not the video's setup. The owner's study of 2026-10-08 found KVMem's retrieval near-lossless for recall, so it
  stays an experiment worth measuring.
- **Qwen3.8-27B itself at `xhigh`, without limits**: the same size, but it thinks about 70% longer for the same
  score; at about 45 tokens a second a hard question would take five and a half minutes instead of three.
- **Raising the daily preset's limits**: it is a different setup (an exact window with retrieval), and its reserve would
  have to double with its output limit.
- **A smaller file (IQ3_XXS, 10.4 GB) for more context**: it costs quality; the video's file is IQ3_S.
- **The monitors on the processor's integrated GPU**: the video's advice, which frees 1.2-1.3 GB and would make 128K
  at q4_0 fit. It changes how the desk's monitors are driven, so it is the owner's to choose; a preset of 128K follows
  if they do.

## Consequences
- Hard questions take minutes: a model that thinks 8,700 tokens at 45 tokens a second answers in about three. On a task
  it cannot solve it can think for many minutes; the gateway's guard (decision 0040) stops an answer that repeats
  itself, not one that keeps reasoning.
- OpenCode compacts a session at 98,304 less 32,768 tokens, about 65,000, where "daily 262K" let it grow to about
  246,000: sessions are compacted more often.
- The measurement of 2026-10-18 ([the frontier preset](../measurements/2026-10-18-the-frontier-preset.md)) records the
  memory it takes, its speed by context size, and how long it thinks.
- A per-role reasoning effort (low for an agent's small jobs) belongs with sampling per role (decision 0004), later.
