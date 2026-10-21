# The model at work: thirteen tasks in a simulator's repository (2026-10-15)

The owner: "run some big tests with the model and inspect the work that it did to determine what we need to do to
make the model work even better." The tasks are the kind of work Clank is for, simulation studies and changes to a
simulator (a Python package with Numba kernels, a command line and an MCP server for agents), on a clone of its
repository in a workspace of its own.

## How it ran

- Clank 0.2.0 at `4cdd270`..`21be87f`; model `daily 262K` (Qwen3.8-27B IQ3_S on KVMem/llama.cpp v0.16.0-rc1, RTX 5080,
  NVIDIA driver 591.74); OpenCode 1.19.0 in the workspace's container (16 CPUs, 12 GB), the simulator installed by the
  workspace's setup and its MCP server allowed (design 0004 §10).
- Each task started from the same commit and ran OpenCode headless (`opencode run`, the argv `clank work` uses), one
  fresh session per task. Its answer, its tool calls, the files it changed and the gateway's records were kept. The
  results under `runs/` were kept between tasks, as a study's are (b5 builds on t2).

## The tasks and what came of them

| Task | Outcome | Seconds | Requests | Prompt tokens | Cached | Out | Tok/s | First token ms |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| t1 explain how a core decision of the simulator is made, citing code | right, with file and line | 42 | 5 | 79,364 | 72% | 1,294 | 64 | 4,128 |
| t2 pilot study (8 runs via MCP), analysis script, figure, table | right; looked at its own figure | 204 | 14 | 412,272 | 93% | 10,082 | 68 | 3,346 |
| t3 add `median_and_iqr` with a test | right; caught its own wrong quantile (75 for 0.75) | 66 | 9 | 206,271 | 86% | 2,622 | 70 | 2,606 |
| t4 find a planted bug (error bars √n too small) | found from the tests, fixed, whole suite run (all passed) | 127 | 10 | 238,637 | 88% | 2,524 | 65 | 2,443 |
| t5 a long run in the background (command line) | right: setsid nohup, checked it runs, said how to follow it | 144 | 9 | 213,192 | 87% | 5,612 | 65 | 2,623 |
| t6 a figure on request | made; chose a graph the prompt did not name, and said so | 95 | 9 | 178,038 | 88% | 3,667 | 69 | 4,670 |
| t7 a docstring, ruff clean | right | 54 | 8 | 130,664 | 86% | 2,430 | 68 | 2,106 |
| t8 run two test files, report | right (26 passed) | 26 | 4 | 48,325 | 67% | 320 | 65 | 3,522 |
| b1 read three long files, write a summary | **failed**: the engine broke at a 68K-token prompt | 61 | 3 | 16,008 | 0% | 108 | 80 | 11,690 |
| b2 a study with background jobs, a derived quantity, figure | right, and careful about what was averaged over | 644 | 26 | 1,125,228 | 97% | 35,294 | 63 | 2,625 |
| b3 a `--quiet` flag on the command line, with a test | right; 20 CLI tests, ruff clean | 147 | 16 | 455,263 | 94% | 6,934 | 67 | 1,565 |
| b4 review a module for numerical problems | thorough: 4 real findings, the rest checked | 134 | 4 | 66,152 | 59% | 6,297 | 58 | 6,668 |
| b5 fit the pilot's results (no new runs) | right, with the censoring caveat | 59 | 9 | 150,971 | 87% | 2,897 | 72 | 1,784 |

Twelve of thirteen were done right, most of them well: the model plans with the simulator's own estimate, uses its MCP
tools and background jobs, writes and runs analysis scripts, looks at the figures it makes, checks its own work with the
tests, and reports with the right caveats. Each request re-reads 16-70K tokens of prompt, mostly (86-97%) from the
engine's cache, so the first token comes in about 2-4 s; answers stream at 58-72 tokens a second.

## What it found to fix

1. **The engine breaks on a long prompt (b1).** After reading 68,159 tokens, KVMem trimmed its GPU cache to its budget
   (`mandatory_trim policy=topk kept=287 dropped=121 budget=288`) and then failed the query's replay (`kvmem_fill_slot_info:
   block 125 has no GPU slot`, `decode: failed to find a memory slot for batch of size 512`, then its query replay
   failed). A conversation of the owner's at 79K tokens had worked the day before, so it is the replay
   path after a trim, not a fixed size. **Not fixed: it is the engine's** (KVMem's own fork); until it is, a
   conversation that has grown past about 60K tokens is best started afresh, and the preset's KV budget is the knob.
2. **The engine's error reached OpenCode as a parse error.** KVMem's error event carries a plain string where OpenAI's
   streams carry an object, so OpenCode said "expected object, received string" and nothing else. **Fixed**: the
   gateway passes an engine's error on as OpenAI writes one and records it, so OpenCode shows the engine's words and the
   Requests page shows the request failed and why (`gateway/server.py`, `_engine_error`).
3. **git refused the workspace's folder (b3).** The folder is mounted from Windows, owned by another user than the
   container's `agent`, and git says "dubious ownership" until told it is safe; the model worked around it with `git -c
   safe.directory=/workspace` each time. **Fixed**: the image marks `/workspace` safe.
4. **`/tmp` is outside what OpenCode may touch (t6).** The model's first try at a scratch script in `/tmp` was
   refused, and it wrote the script in the folder and removed it after. Left as it is: OpenCode's rule for paths
   outside the folder takes patterns, but opening `/tmp` alone needs its precedence checked first; the cost was one step.
5. **Unnamed parameters are chosen, and said (t6).** Asked for a figure without a graph, the model chose one and said
   which. For figures asked for from the phone, the page should show the model's stated choices next to the figure.
