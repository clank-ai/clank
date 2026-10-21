# Completion on the CPU

**When:** 2026-10-15, about 20 minutes; the main slot ran `daily 262K` (KVMem, Qwen3.8-27B, 15.7 of
16.3 GB of the GPU taken with the desktop) and was idle.

**Question:** can inline completion in VS Code be served beside the agent's model, and how fast?

## What the main slot can do

- KVMem's server (v0.16.0-rc1) answers `/health`, `/v1/models` and `/v1/chat/completions` only: `/infill`,
  `/completion`, `/v1/completions`, `/props`, `/slots` and `/metrics` answer 404. It has no fill-in-the-middle endpoint,
  and it runs one request at a time (design 0003 §4): a completion would wait behind the agent's whole answer.
- The GPU has about 600 MiB free beside it: not enough for a second model with its own buffers.

So completion needs a model of its own, and the place left for it is the CPU (design 0001 §1: "endpoints and CPU
engines run alongside").

## How

`ghcr.io/ggml-org/llama.cpp:server` (llama.cpp's own CPU image) in Docker Desktop, `--cpus=N -t N -c 8192 -np 1
--cache-reuse 256`, with the fill-in-the-middle models llama.cpp's own VS Code extension suggests:
`ggml-org/Qwen2.5-Coder-0.5B-Q8_0-GGUF` (531 MB) and `ggml-org/Qwen2.5-Coder-1.5B-Q8_0-GGUF` (1.6 GB). Each request is
`POST /infill` from Windows: about 1,000 tokens of the file before the cursor (`input_prefix` and the line so far), about
250 tokens after it (`input_suffix`), greedy. The file was Clank's `gateway/records.py`, cut inside `summary()`'s body.
The sequence: a cold request; four more as typing goes on (`r`, `re`, `ret`, `retu`), which the server answers from its
cache but for the suffix; a jump to another function; a jump back. The script is kept with the session's notes, not in
the repository (a spike).

## Results

Time seen from Windows, milliseconds; in brackets the tokens read again and the server's own prompt time.

**One line** (stop at the end of the line, at most 24 tokens), the 0.5B model:

| Threads | Cold | Typing (four requests) | Jump | Back |
| --- | --- | --- | --- | --- |
| 6 | 1,500 (1,032 in 1,139) | 312-333 (255 in 275-293) | 1,233 | 524 |
| 8 | 1,156 (1,032 in 828) | 277-302 (255 in 230-258) | 1,131 | 441 |
| 12 | 1,210 (1,032 in 850) | 232-280 (255 in 199-244) | 960 | 426 |

**Several lines** (stop at a blank line, at most 48 tokens):

| Model | Threads | Cold | Typing | Jump |
| --- | --- | --- | --- | --- |
| 0.5B | 4 | 2,463 | 1,166-1,238 | 2,404 |
| 0.5B | 8 | 1,516 | 829-912 | 1,502 |
| 1.5B | 4 | 5,261 (prompt cut at its 2 s limit: nothing written) | 3,166-3,207 | 5,402 (cut) |
| 1.5B | 8 | 3,026 (cut) | 2,404-2,815 | 3,374 (cut) |

The engine took 242 MiB of memory with the 0.5B model and 438 MiB with the 1.5B, beside the model's mapped file.

What the 0.5B model wrote was right for the place: inside `summary()` it continued `return {` and then the record's
fields, `"id": record.get("id"), "time": record.get("time"), ...`; at the jump, the docstring `"""Find one record by its
id."""`.

## What it shows

- **The 0.5B model on 6-8 threads serves a line in about 0.3 s while typing**, and about 1.2-1.5 s the first time in a
  file or after a jump. Most of a typing request is reading the suffix again (about 250 tokens), since the suffix comes
  after the prefix in the prompt: a shorter suffix makes it faster.
- More threads than 8 buy little; 6 cost 10-15% more time than 8 and leave more of the CPU to the owner.
- The 1.5B model is too slow on this CPU for completion as one types (2.4-3.4 s).
- Generating is cheap for one line (2-19 tokens in 12-270 ms); several lines take most of a second more.
