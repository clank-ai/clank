# frontier 262K

"frontier 262K" is the preset Clank's main slot runs for long agent work on a 16 GB card: Swift 1.5, a 27B reasoning
model, on KVMem, with a context of 262,144 tokens. A prompt up to 57,344 tokens is attended exactly on the GPU. Past
that, the whole context is kept in system memory, and KVMem keeps 57,344 tokens of it on the GPU: the first block of
128 tokens, and the blocks that look most like the last user message. Thinking has no limit, and an answer may be
32,768 tokens long.

This page says how it is built, so that it can be built again on another machine, and why each choice was made. The
owner, after two days of long sessions on it (2026-10-20): "The model is working extremely well, and I am unaware of a
better model working on a 16GB gpu at the moment."

Its file: [`clank/defaults/presets/frontier-262k.json`](../../clank/defaults/presets/frontier-262k.json). Its
decisions: [0068](../decisions/0068-the-frontier-preset.md) (the model and its thinking),
[0069](../decisions/0069-a-frontier-preset-over-262k-with-retrieval.md) (262K with retrieval, and its sizes),
[0078](../decisions/0078-frontier-262k-on-the-iq3-xxs-file.md) (the smaller file, now "frontier 262K lean") and
[0088](../decisions/0088-frontier-262k-runs-the-iq3-s-file-again.md) (this file again, the owner's choice). Its numbers:
[the frontier preset's measurement](../measurements/2026-10-18-the-frontier-preset.md).

## The model

Swift 1.5 is Qwen3.8-27B retrained by UkisAI to stop re-checking what it has settled. It thinks about 42% less than
Qwen3.8-27B on GPQA Diamond, at the same score (decision 0068). It has 64 layers. Only 16 of them attend fully and keep
a KV cache; the others are linear-attention layers with a small recurrent state. That is why a long context is cheap
here. It has an MTP head, which drafts tokens for speculative decoding. It reads no images.

The file is ISTA-DASLab's GSQ-RCO IQ3_S allocation, refined by UkisAI, with the MTP head inside. In Clank's catalog it
is `swift-1.5-qwen3.8-27b` ([its record](../../clank/catalog/models/swift-1.5-qwen3.8-27b.json)):

| | |
| --- | --- |
| Repository | `ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF` |
| Revision | `d74895bbe5db4bec1e0024e7cc87d59c02d7631a` |
| File | `Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf` |
| Size | 12,120,016,896 bytes |
| SHA-256 | `9aecf1cd41b2cb2f32a74e0d889e33855ebef43b26f43b43feb5720239e677e5` |
| URL | <https://huggingface.co/ukisai/Swift-1.5-Qwen3.8-27B-GSQ-RCO-GGUF/resolve/d74895bbe5db4bec1e0024e7cc87d59c02d7631a/Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf> |
| License | UkisAI's Swift Open License v1.0, not Apache: read it before any commercial use |

Its KL divergence from the BF16 model is 0.0513 (UkisAI's development measure). The smaller IQ3_XXS file of the same
repository takes 1,600 MiB less of the GPU, for 0.0978: that is "frontier 262K lean".

## The engine

KVMem/llama.cpp v0.16.0-rc1: the llama.cpp fork that keeps a long context by retrieving older KV from system memory.
Its program is `llama-kvmem-server`, run in a WSL distribution (Ubuntu 22.04 here). Clank's adapter for it:
[`clank/components/runtime/adapters/kvmem.py`](../../clank/components/runtime/adapters/kvmem.py) (design
[0003](../design/0003-the-runtime.md) §4).

The build Clank runs here, as its checkout and build folder said on 2026-10-20, rebuilt with Clank's patch on
2026-10-27:

- **Source**: the public repository <https://github.com/kvmem/kvmem-llama.cpp>, at its tag `v0.16.0-rc1` (commit
  `db4bc22ee6e8f4b590188dcc0457e72022eb1bbe`, "Pin shared-library mode for reproducible prebuilt builds").
- **One upstream fix on top**: commit `7e20823` of KVMem's master, "fix: handle multimodal query replay exceeding KV
  budget" (2026-09-23, released in v0.17.0), cherry-picked onto the tag. Without it, one tool result larger than the
  exact window fails the request with HTTP 500
  ([KVMem and a long tool result](../measurements/2026-10-15-kvmem-long-tool-results.md)).
- **Clank's patch on top of it**: [`kvmem-pin-the-system-prompt.patch`](kvmem-pin-the-system-prompt.patch) (decision
  [0146](../decisions/0146-kvmem-keeps-a-snapshot-at-the-end-of-the-system-prompt.md)). KVMem keeps a snapshot of the
  model's state where the first message after the system prompt begins, so a new session resumes after OpenCode's
  system prompt and tools (about 18,000 tokens) instead of reading them again: its first word in about a second, not
  10 to 37. A snapshot restored also drops the snapshots past it, which belonged to the conversation before
  ([the tests](../measurements/2026-10-27-a-new-sessions-first-answer.md#the-patch-tested-before-it-was-built)).
  Nothing else in the engine's source is changed.
- **llama.cpp**: the submodule is ggml-org's llama.cpp at KVMem's pin, `b81c99b`, with KVMem's own patch
  (`patches/llama-kvmem-current.patch`) applied by its `scripts/apply-patches.sh`, and nothing else.
- **The build**: KVMem's `scripts/build-cuda.sh`. Its CMake settings: `CMAKE_BUILD_TYPE` Release, `GGML_CUDA` on,
  `GGML_CUDA_FA` on, `GGML_CUDA_FA_ALL_QUANTS` on, `GGML_NATIVE` on (built for this machine's CPU), and
  `CMAKE_CUDA_ARCHITECTURES` `120a-real` (the script's default, right for RTX 50-series cards such as the 5080), with
  the CUDA toolkit 13.2 (nvcc V13.2.86).
- **Clank does not build KVMem.** It has no recipe for it. It *adopts* a build that is already there: it checks that
  the program lists every flag the adapter can give, that its checkout is at `db4bc22`, and records any local changes
  (design 0003 §7.1).
- **CUDA graphs are off** (`GGML_CUDA_DISABLE_GRAPHS=1`): they crashed v0.16 three times on an MTP verify step
  (2026-10-08).

## Every setting, and why

| Setting | Value | Why | Decided in |
| --- | --- | --- | --- |
| Model file | the IQ3_S file above | the better of the two files that fit; the one the owner ran and chose | [0068](../decisions/0068-the-frontier-preset.md), [0088](../decisions/0088-frontier-262k-runs-the-iq3-s-file-again.md) |
| `context` (`-c`) | 262,144 | the model's whole context; past the window it is retrieved | [0069](../decisions/0069-a-frontier-preset-over-262k-with-retrieval.md) |
| `kvmem.budget` | 57,344 | tokens attended exactly on the GPU; with the reserve, 98,304 cells, the GPU memory "frontier 96K" was measured to fit | [0069](../decisions/0069-a-frontier-preset-over-262k-with-retrieval.md) |
| `kvmem.gen_reserve` | 40,960 | KVMem v0.16 fails an answer that outgrows its reserve once it has retrieved older context: 32,768 for the longest answer, and 8,192 for a step's new tool results | [0069](../decisions/0069-a-frontier-preset-over-262k-with-retrieval.md) |
| `kv.type` | q4_0 | half of q8_0; at q8_0 the same memory gives a window of only about 23,800. Retrieval works on quantized caches (blocks move as raw bytes, scored by keys taken before quantization) | [0069](../decisions/0069-a-frontier-preset-over-262k-with-retrieval.md) |
| `max_output` (`-n`) | 32,768 | room for long thinking and a long answer; Clank refuses a preset whose answers could outgrow its reserve | [0068](../decisions/0068-the-frontier-preset.md), [0069](../decisions/0069-a-frontier-preset-over-262k-with-retrieval.md) |
| `thinking`, `thinking.budget` | on, -1 | the model's scores exist only when it thinks as long as it needs; a budget cuts that off | [0068](../decisions/0068-the-frontier-preset.md) |
| Reasoning effort | not set: the template's `xhigh` | the effort its published scores were measured at | [0068](../decisions/0068-the-frontier-preset.md) |
| `spec.type`, `spec.draft_tokens` | `draft-mtp`, 3 | the MTP head drafts 3 tokens a step; 81-87% were accepted | [design 0003](../design/0003-the-runtime.md) §4 |
| `vision` | off | Swift 1.5 has no projector | [0068](../decisions/0068-the-frontier-preset.md) |
| `batch` (`-b`) | KVMem's own, 512 | what ran in the owner's work; 256 saves 105 MiB of compute buffers but is not measured in real use | [0088](../decisions/0088-frontier-262k-runs-the-iq3-s-file-again.md) |
| `kvmem.method` | `retrieval`, KVMem's own | older blocks chosen by likeness to the last user message (at most its last 512 tokens), not by age | [0069](../decisions/0069-a-frontier-preset-over-262k-with-retrieval.md) |
| `cuda_graphs` | off | crashes on an MTP verify step, 2026-10-08 | [design 0003](../design/0003-the-runtime.md) §4 |
| Sampling | temperature 1.0, top_p 0.95, top_k 20, min_p 0, presence penalty 0, repetition penalty 1 | KVMem's own defaults for Qwen3.8-27B when it thinks, as its `--help` says; Clank does not set sampling yet (that comes with [decision 0004](../decisions/0004-sampling-per-role.md)) | KVMem |

The command line Clank runs for it, in KVMem's folder on the WSL host (`MODEL` is the file's path there, `PORT` the
slot's port):

```text
GGML_CUDA_DISABLE_GRAPHS=1 build/bin/llama-kvmem-server -m MODEL -c 262144 -n 32768 --kvmem-budget 57344
  --kvmem-gen-reserve 40960 --kv-dtype q4_0 --spec-type draft-mtp --enable-thinking --host 127.0.0.1 --port PORT
```

When it starts, its log says
`model=Swift-1.5-Qwen3.8-27B-GSQ-RCO-IQ3_S-mtp.gguf kvmem=1 method=retrieval n_ctx=262144 spec=draft-mtp n_max=3
think=1 rbudget=-1 qmax=512`, and its MTP pool has 98,304 cells.

## What it takes on a 16 GB card

On the RTX 5080 (16,303 MiB as `nvidia-smi` counts it, 326 MiB of it reserved by the driver):

| Part | MiB | From |
| --- | --- | --- |
| Weights on the GPU | 11,160 | the file's tensors; its 388 MiB token embedding stays on the CPU |
| KV cache | 1,728 | 98,304 cells × 18,432 bytes (16 layers, a key and a value of 1,024 values, at q4_0) |
| Buffers | 1,141 | the recurrent state and the compute buffers' base (277), the MTP head's pool (98,304 × 4,096 bytes: 384), the compute buffers' growth (98,304 × 5,120 bytes: 480) |
| KVMem's own overhead | 424 | the rest of what its start was measured to take |
| **Total** | **14,453** | Clank's estimate; "frontier 96K", with the same 98,304 cells, took exactly this at its start |

Why it fits: only 16 of the 64 layers keep a KV cache, at 18,432 bytes a token in q4_0, and only 98,304 tokens of it
sit on the GPU whatever the context. The rest of the 262,144 tokens take about 5.6 GiB of system memory. Once a request
passes the window, retrieval also allocates its scratch: about 290 MiB, by KVMem's source.

It is tight. With it loaded in the owner's work, the whole card had 15,753 of 16,303 MiB in use, the desktop included.
In the measurement of 2026-10-18 of 2026-10-18 the same file and sizes (with a batch of 256) left 264-448 MiB free. A
desktop that needs more of the card leaves the model too little: then use "frontier 262K lean", which leaves about
1.2 GB.

## How fast it is

| When | Reading the prompt | Writing |
| --- | --- | --- |
| The desktop quiet, a prompt of 8K-33K (as "frontier 96K": below the window both attend alike) | 1,520-1,601 tokens a second | 74-79 tokens a second |
| The owner's work, 245,411 tokens of context | mostly from KVMem's cache | 57 tokens a second |
| The CPU busy with other work, 8K to 237K (batch 256) | 981 to 576 | 43.6 to 33.2 |
| The desktop busy, a prompt of 8K | 492 | 36.7 |

In four long OpenCode sessions (2026-10-19 and 10-20; 69, 54, 143 and more than 250 steps; prompts up to 123,346,
141,628, 245,411 and 228,232 tokens), about 99% of each prompt was read from KVMem's cache, so a step past the first
reads only what is new ([the measurement](../measurements/2026-10-18-the-frontier-preset.md#in-the-owners-work)).

## Building it on a new machine

What it needs: Windows 11 with WSL 2 and Ubuntu 22.04 in it, an NVIDIA card of 16 GB, the CUDA toolkit 13.2 and
what KVMem's README asks for its build in that distribution, about 6 GB of system memory free for WSL beyond the rest,
12.1 GB of disk for the model, and Clank's working copy (`uv sync`; see [AGENTS.md](../../AGENTS.md)). Clank's
commands run from its working copy.

1. **The NVIDIA driver and its settings.** Install driver 591.74 (610.88 also ran well; 617.42 crashed KVMem, see
   below), and keep the NVIDIA app from updating it by itself. In the NVIDIA Control Panel, under *Manage 3D
   settings*, set *CUDA - Sysmem Fallback Policy* to *Prefer No Sysmem Fallback*. Without it, Windows may move part
   of the model into system memory when the card fills, and the model then crawls: once it wrote 10 tokens a second
   until a restart (decision 0068). With it, a model that does not fit should fail with an out-of-memory error, which
   Clank reports, rather than crawl.
2. **Start Clank and add the host:** `uv run clank serve --background`, then
   `uv run clank host add ubuntu-22.04 --wsl Ubuntu-22.04` (its Clank folder defaults to `~/.clank`).
3. **Build KVMem** in that distribution, by KVMem's README, with the fix picked onto the tag before the patches:

   ```text
   git clone --recurse-submodules https://github.com/kvmem/kvmem-llama.cpp.git
   cd kvmem-llama.cpp
   git checkout v0.16.0-rc1        # commit db4bc22
   git submodule update --init     # llama.cpp at KVMem's pin, b81c99b
   git cherry-pick -n 7e20823      # the replay fix, from KVMem's master, left uncommitted
   scripts/apply-patches.sh        # KVMem's patch, into the llama.cpp submodule
   git apply CLANK/docs/models/kvmem-pin-the-system-prompt.patch   # Clank's patch (decision 0146), uncommitted
   scripts/build-cuda.sh           # makes build/bin/llama-kvmem-server
   ```

   `CLANK` is Clank's working copy as the distribution sees it (`/mnt/c/...` for a folder on drive C). `-n` leaves the
   fix uncommitted, so the checkout stays at `db4bc22`, the commit `clank engine adopt` checks, and `git apply`
   leaves Clank's patch uncommitted too; the build here has them so (`git diff --cached` shows the fix, `git diff`
   the patch). The fix's regression test, `tests/replay-budget-regression.py`, does not exist at the tag,
   so the pick adds it whole. When it was picked here, git stopped at one conflict, resolved to v0.17.0's form with
   v0.16's logging (`fprintf` for `kvmem_diag`;
   [the measurement](../measurements/2026-10-15-kvmem-long-tool-results.md)). A card other than the RTX 50-series
   needs its own CUDA architecture in place of `120a-real`. Then adopt the build where it is (`<checkout>` is its
   folder on the host):

   ```text
   uv run clank engine adopt kvmem-llamacpp --version v0.16.0-rc1 --host ubuntu-22.04
     --program <checkout>/build/bin/llama-kvmem-server --folder <checkout> --library-path <checkout>/build/bin
   ```

   Clank checks its flags and that its checkout is at `db4bc22`, and records the local changes it finds: the fix,
   Clank's patch and the patched submodule.
4. **The model:** `uv run clank model download swift-1.5-qwen3.8-27b --format gguf --host ubuntu-22.04`. It resumes
   after an interruption and is used only once its SHA-256 is the catalog's. A copy you already have:
   `uv run clank model adopt swift-1.5-qwen3.8-27b --format gguf --host ubuntu-22.04 --path <where it is>`.
5. **Check it:** `uv run clank preset check frontier-262k`: valid, installed, its file there, its flags known, and
   whether it fits the GPU now.
6. **Load it:** `uv run clank model switch frontier-262k` (or `load` when the main slot runs nothing). In the console:
   Presets (`9` in the menu), highlight "frontier 262K", `c` to check it, Enter to switch the main slot to it.

## Limits and pitfalls

- **OpenCode must compact before the context fills.** KVMem refuses a request whose prompt plus its `max_tokens` pass
  262,144 tokens. In one session OpenCode compacted too late: its step 143 ended at 245,725 tokens, and its next
  prompt, 246,931 tokens with 16,384 for the answer, was refused. In another, OpenCode compacted from 228,232 tokens to
  37,516, and the session went on. Since 2026-10-20 OpenCode is told the window less a margin for one step's tool
  results (`context_margin`, 16,384 by default, from when OpenCode next starts in a workspace; decision
  [0089](../decisions/0089-opencode-is-told-the-window-less-a-margin.md)), and the gateway answers KVMem's refusal as
  the context overflow OpenCode compacts on (decision
  [0090](../decisions/0090-a-full-context-is-answered-as-an-overflow-opencode-compacts-on.md)). A long session can
  still be compacted by hand before it nears the limit (the Monitor, F10: Compact now, `k`).
- **The desktop shares the card.** A busy desktop, or a video, on the same GPU halves decoding (2026-10-08, 10-11 and
  10-18). With this preset the card has little room to spare; when it is needed elsewhere, switch to "frontier 262K
  lean".
- **An answer longer than 40,960 tokens fails** mid-answer. The preset's longest answer is 32,768, so it stays
  within the reserve.
- **KVMem keeps one conversation.** A request that shares nothing with the one it holds resets its store, so two
  sessions taking turns read their prompts again each time.
- **A new chat reads the system prompt once per workspace.** With Clank's patch, the first session reads OpenCode's
  system prompt and tools (17,000 to 29,000 tokens, 10 to 37 s here), and each new session after it resumes there:
  its first word in 0.5 to 1 s ([the measurement](../measurements/2026-10-27-a-new-sessions-first-answer.md)).
  KVMem keeps one conversation, so another workspace's prompt, or two sessions taking turns, are read again.
- **Past the window, recall is good but not perfect.** In its harness at about 220,000 tokens this file and
  these sizes (with a batch of 256) passed 5 of 6 probes: it missed a rule of the system prompt.
- **A huge tool result** fills the window with itself: with the fix above the model answers, but about the data more
  than the question. Ask the agent to summarize logs and data files with a command (`tail`, `grep`, a short script).
- **The NVIDIA driver.** On driver 617.42, which the NVIDIA app installed on 2026-10-13, 2 of 9 cache clears crashed
  KVMem with a CUDA error, where 36 before it had crashed none; on 591.74, 66 clears in 81 turns crashed none
  ([the driver's measurement](../measurements/2026-10-14-the-nvidia-driver.md), on this one machine). Stay on 591.74
  (or 610.88), keep the NVIDIA app from updating the driver by itself, and if KVMem starts crashing with CUDA errors
  after a driver change, roll the driver back first. `clank doctor` shows the driver's version.

## Its neighbors

| Preset | Model file | On the GPU | When |
| --- | --- | --- | --- |
| "frontier 262K" | IQ3_S | 57,344 exact + 40,960 reserve: 14,453 MiB estimated | long agent work: the default |
| "frontier 262K lean" | IQ3_XXS | 73,728 exact + 40,960 reserve, batch 256: 13,436 MiB measured | when the GPU needs room (decision [0078](../decisions/0078-frontier-262k-on-the-iq3-xxs-file.md)) |
| "frontier 96K" | IQ3_S | the whole 98,304-token context exact: 14,453 MiB measured | shorter work, nothing retrieved; OpenCode compacts at about 65,000 |
| "daily 262K" | Qwen3.8-27B IQ3_S | 36,864 exact + 16,384 reserve, at q8_0, images on the CPU | The prototype's daily profile: thinking cut at 4,096 tokens |
