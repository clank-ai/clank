# 0037. A model that reads images runs on the CPU, loaded on demand: Qwen3-VL 4B

- Status: Proposed (built at the owner's instruction while away; the owner may decide otherwise)
- Date: 2026-10-15
- Decided by: Claude, from [the measurement of 2026-10-15](../measurements/2026-10-15-vision-on-the-cpu.md), on the
  owner's request for "some image model on the CPU" that is "only loaded when I am using it", with off, on demand (the
  default) and always

## Context
Design 0008 has the owner mark up figures for the agent, and the agent check the figures it makes. The main model
(Qwen3.8 27B with its projector on the CPU) sees images, but only while its preset loads the projector, and changing
that means loading the main model again; other models may not see images at all. A model of its own that reads images,
loaded and unloaded freely beside the main one, makes the feature independent of the agent's model.

## Decision
**Qwen3-VL 4B Instruct** (`Qwen/Qwen3-VL-4B-Instruct-GGUF` on Hugging Face: `Qwen3VL-4B-Instruct-Q4_K_M.gguf` and
`mmproj-Qwen3VL-4B-Instruct-Q8_0.gguf`, pinned by revision and SHA-256) runs in llama.cpp's CPU server (decision 0035's
engine, with a new `vision` option that gives it the projector) in a third slot, `vision`, on its own port (18202), for
the gateway's role `vision`. The `vision` settings choose its mode: off, on demand (the default: loaded when a request
for it comes, unloaded after 10 idle minutes) or always.

The files are a new dependency, fetched the way Clank fetches every model: over HTTPS from Hugging Face, checked against
the checksums the catalog holds, and only when the owner asks for them (F8, `g`), or when a request first needs them.

## Alternatives
- **Qwen3-VL 2B.** Faster and smaller (3.4 GB while loaded), but it misread the arrow; the 4B's 7.7 s a reading is fast
  enough.
- **Only the main model's projector.** No model of its own to manage, but the feature would depend on the agent's model
  seeing images, and turning it off or on would load the main model again.
- **A model on the GPU.** The GPU holds the main model with little room to spare.

## Consequences
- About 2.8 GB of disk in the WSL distribution, once downloaded; 6 GB of memory and 8 CPU threads while it reads an
  image (about 8 s), none while it is unloaded.
- The gateway asks the service to load the model when a request for it comes; the first reading after it was unloaded
  waits about 4 s more.
