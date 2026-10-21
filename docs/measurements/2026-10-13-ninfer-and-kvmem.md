# NInfer and KVMem on this machine (2026-10-13)

The owner asked "how well ninfer-5080 works compared to the KVMem setup that we have been using, along with all the
details (tokens per second, ability to complete the tasks that I want it to complete, context window length, etc)".
Both ran through Clank on the owner's RTX 5080 (16 GB, also driving the desktop), one after the other, the same day.

## What was compared

| | KVMem (`daily 262K`) | NInfer (`NInfer 44K fitted`) |
| --- | --- | --- |
| Engine | KVMem/llama.cpp v0.16.0-rc1 | NInfer RTX 5080 v1.4 (CUDA 13.3) |
| Model | Qwen3.8-27B, IQ3_S GGUF with its MTP head | Qwen3.8-27B, `.ninfer` (Q3 weights, int8 activations) |
| Context | 262,144 tokens: 36,864 attended exactly, older ones retrieved from system memory | 45,056 tokens, all exact (KV cache Q4) |
| Speculation | MTP, 3 draft tokens | MTP, 3 draft tokens |
| Thinking budget (default) | 4,096 tokens | 2,048 tokens |
| Images | yes (projector on the CPU) | no in this preset (vision off to fit) |
| GPU memory taken | 13.8-14.5 GB | 13.5 GB |
| Ready after loading | 19-25 s | 11-17 s |

## How

- **Speed and recall:** a probe sending the same requests to each (Clank's scratch tool, client-side timings): a code
  task after a prompt of about 1K, 8K, 16K, 31K and 40K tokens of unique code (cold), then the same conversation one
  turn later (warm); and eight facts spread through such a prompt, all asked for at once. KVMem was also measured with
  prompts of 59K, 119K and 149K tokens.
- **Capabilities:** thinking on and off, tool calls (whole and streamed), using a tool's result, an image, JSON mode.
- **Coding tasks:** ten tasks of the prototype's benchmark (its `final` and `val` sets: Python, C++, JavaScript and
  TypeScript repositories, each judged by hidden tests), done by OpenCode 1.18 in a sandbox container, talking to the
  engine Clank ran. (The prototype's benchmark served as a measuring instrument only; Clank does not use it, decision
  0033.)

## Results

### Speed (tokens a second; "first token" is the wait before the answer starts)

| Prompt | KVMem first token | KVMem reading | KVMem writing | NInfer first token | NInfer reading | NInfer writing |
| --- | --- | --- | --- | --- | --- | --- |
| ~1K | 7.3 s (first request) | 139 | 83 | 3.6 s (first request) | 280 | 74 |
| ~8K | 13.1 s | 593 | 74 | 5.2 s | 1,448 | 97 |
| ~16K | 22.5 s | 712 | 76 | 19.5 s | 822 | 75 |
| ~31K | 40.8 s | 787 | 31 | 15.6 s | 2,001 | 89 |
| ~40K | 46.8 s | 836 | 72 | 32.2 s | 1,244 | 65 |
| 59K | 70.4 s | 835 | 45 | (beyond its context) | | |
| 119K | 146 s | 815 | 50 | | | |
| 149K | 184 s | 809 | 71 | | | |

The next turn of the same conversation started in 0.4-6 s on both (each keeps the conversation it just read) and was
written at 75-95 tokens a second on KVMem, 45-160 on NInfer. Writing speed varies with the text (its predictability
for the draft tokens) and with what else the GPU draws; reading is where NInfer is clearly faster (about twice).

### Recall (eight facts asked for at once)

| Prompt | KVMem | NInfer |
| --- | --- | --- |
| 8K, 16K, 31K, 39K | 8/8 each | 8/8 each |
| 57K | 1/8 (one run) | beyond its context |
| 116K, 145K | 8/8 each | beyond its context |

### Capabilities

Both thought by default and could be told not to, called tools (whole and streamed) and used a tool's result. KVMem
read an image and kept to JSON mode; NInfer, in this preset, refused images (vision off) and did not keep to JSON
mode. NInfer refuses llama.cpp's request fields (`chat_template_kwargs`) with an error: Clank's gateway puts each
request in each engine's own fields (design 0004 §2).

### Coding tasks

| | KVMem | NInfer |
| --- | --- | --- |
| Passed | 8 of 10 | 8 of 10 (the same two failed) |
| Time, all ten | 23.7 min | 43.1 min |
| Steps (model calls) | 90 | 149 |
| Tokens written | 77,166 | 140,927 |
| Prompt tokens read, all steps | 1.24 M | 2.21 M |

Task by task, NInfer took 1.7-3 times as many steps on six tasks and about as many on four. With the same results it
did more work: more steps, longer outputs. Three likely reasons, not yet separated: its context (OpenCode compacts the
conversation at about 33K tokens with this preset's limits, and three NInfer tasks reached it, losing detail), its
smaller default thinking budget (2,048 against 4,096), and its quantization.

## What it means

- **For speed of reading long prompts,** NInfer is about twice as fast, which matters most when a long prompt is read
  from scratch (a new session, a compaction).
- **For agentic coding as measured,** KVMem finished the same tasks in about half the time, with its 262K context and
  larger thinking budget.
- **For context,** KVMem's 262K works for recall here (8/8 up to 145K, with one 1/8 at 57K), while NInfer's 128K
  cannot fit beside this desktop whatever its version (design 0004 §7).
- **Next:** NInfer with a 4,096 thinking budget on the same tasks, to separate the budget from the context; NInfer
  v1.5; and the desktop's stalls under each (design 0004 §6).
