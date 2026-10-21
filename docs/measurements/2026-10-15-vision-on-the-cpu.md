# A model that reads images, on the CPU (2026-10-15)

Design 0008 §7 wants a model that reads a marked-up figure for an agent whose own model cannot see it, and that the
agent can ask about a figure it made; on the CPU, since the GPU holds the main model, and loaded only while it is
used, since the owner's simulations need the CPU. Two models were tried, both in llama.cpp's server (b11588, the CPU
build Clank installs for completion, decision 0035), with their projector files, on 8 threads at a low priority, at an
8,192-token context.

## How

A made-up study figure (three curves of an entropy crossing near p = 0.16, synthetic data), marked up as the annotator
draws it: mark 1 a red circle around the crossing, mark 2 a red arrow at the legend, each numbered in a filled red
circle. The question: for each mark, what it marks and where in the plot's data coordinates. Each model was started,
asked twice, and stopped (`scratchpad` scripts of the session: `make_figure.py`, `bench.sh`).

## What it showed

| Model (files) | Start | First reading | Again (cached) | Memory | Mark 1 | Mark 2 |
| --- | --- | --- | --- | --- | --- | --- |
| Qwen3-VL 2B, Q8_0 (1.7 GB + 0.4 GB) | 2.7 s | 5.6 s (433 tokens read in 3.0 s, 28 tokens/s) | 3.9 s | 3.4 GB | "the intersection of the L = 32 and L = 64 curves ... (0.15, 1.8)" | wrong: "a point on the L = 64 curve" |
| Qwen3-VL 4B, Q4_K_M (2.4 GB + 0.4 GB) | 4.0 s | 7.7 s (433 tokens read in 3.6 s, 19 tokens/s) | 4.1 s | 6.1 GB | "the intersection of the orange (L=32) and green (L=64) curves, around (p=0.15, S=1.5)" | "points to the upper right region of the plot" |

Both are fast enough to load when wanted and read a figure in under ten seconds. The 4B read the marks better (it
named the curves by color and label and placed the crossing well); neither said the arrow points at the legend, which
the figure's geometry says exactly (design 0008 §4), so the two are given together.

## Choice

**Qwen3-VL 4B** (Qwen's own Q4_K_M and the Q8_0 projector), in the preset `vision 4B`: 8 threads, images up to 1,024
tokens. Its 6 GB are freed when it is unloaded, which on demand (the default) happens after 10 minutes without use.
