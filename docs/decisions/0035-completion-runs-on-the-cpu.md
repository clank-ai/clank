# 0035. Completion runs on the CPU: upstream llama.cpp's server and a small coder model

- Status: Proposed (built at the owner's instruction while away; the owner may decide otherwise)
- Date: 2026-10-15
- Decided by: Claude, from the measurement below, on the owner's instruction to "begin working on the ... completion
  ... section of the menu"

## Context
Design 0002 §3.3 put inline completion in VS Code in M3, served through Clank, meeting its latency target while the
agent is writing. [The measurement of 2026-10-15](../measurements/2026-10-15-completion-on-the-cpu.md) found that the
main slot cannot serve it (KVMem has no fill-in-the-middle endpoint and runs one request at a time) and that the GPU has
no room for a second model beside it, while Qwen2.5-Coder 0.5B on 6-8 CPU threads in llama.cpp's server writes a line
in about 0.3 s as one types.

## Decision
Completion is served by a new engine, **upstream llama.cpp's `llama-server`** (its CPU build for Ubuntu x64, from the
project's release archive on GitHub, pinned by build and SHA-256), installed in the WSL host by a recipe, with the model
**Qwen2.5-Coder 0.5B** (`ggml-org/Qwen2.5-Coder-0.5B-Q8_0-GGUF` on Hugging Face, pinned by SHA-256), in the `fast` slot
on 6 threads (design 0006).

Both are new dependencies, and both are fetched the way Clank already fetches engines and models: over HTTPS from the
project's own release page and from Hugging Face, checked against the checksum the recipe and the catalog hold. Nothing
else runs with them; the engine listens on 127.0.0.1 only.

## Alternatives
- **The main slot.** Impossible with KVMem 0.16 (above). A later engine that serves several requests and fill in the
  middle on the GPU may take completion back to the GPU; the role then names another slot, and VS Code sees no change.
- **A small model on the GPU beside the main one.** About 600 MiB is free; a 0.5B model with its buffers needs about
  1 GB, and the main engine's crashes were tied to a GPU with little headroom. Rejected while the main model fills it.
- **Docker** (`ghcr.io/ggml-org/llama.cpp:server`), as measured. It runs the same server, but Clank's engines run on
  hosts (design 0003 §2), whose processes it can follow, adopt and restart; a container would be a host kind of its own.
- **The 1.5B model.** Better completions, but 2.4-3.4 s a line on this CPU.

## Consequences
- About 0.5 GB of disk (the model) and 18 MB (the engine) in the WSL distribution; about 250 MB of memory while it runs.
- Up to 6 of the 32 hardware threads busy for about 0.3 s after each pause in typing; none while the owner does not
  type.
- Completion keeps working while the agent writes: the engines do not share anything.
