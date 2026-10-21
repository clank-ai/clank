# 0010. Serving setups are plug and play; the first are llama.cpp, KVMem and NInfer RTX 5080 as published

- Status: Accepted; NInfer RTX 5080 retired by [0034](0034-ninfer-is-retired.md), the rest stands
- Date: 2026-10-11
- Decided by: the owner: "sometimes I may want to load a model with KVMem, sometimes with just the normal llama.cpp,
  or maybe I want to use the implementation here: https://github.com/toddballinger/ninfer-5080 (please note that the
  ninfer-5080 setup is EXACTLY what we should be implementing locally, together with KVMem as another option, and later
  on we will have other setups implemented and we need to be able to just plug and play the model and the way we are
  serving the model ...)"

## Context
The prototype serves models one way (KVMem's fork of llama.cpp, a family of fixed profiles). Ways of serving differ in
program, model format, launch options, API dialects, memory behavior and speed. Two examples, each by its own authors'
measurements: NInfer's RTX 5080 v1.5 release decodes at 112 tokens per second after a 118,001-token prompt with a
131,072-token context (its `ninfer_bench`), and KVMem keeps a 262,144-token logical context by retrieving older KV from
system memory.

## Decision
A **serving setup** is an engine adapter (design 0001 §2), the recipe to build or install the engine at a pinned
version, and its validated launch profile and model artifact. Adding one changes nothing else in Clank: one adapter
module with its tests, its install recipe, and its presets. The first three, built together so the interface is proven
on three different programs from the start:

1. **llama.cpp**, the upstream server, with GGUF models.
2. **KVMem/llama.cpp**, the fork the prototype uses, with GGUF models: a 262K context, older context retrieved.
3. **NInfer RTX 5080, exactly as published**: the `toddballinger/ninfer-5080` v1.5 release (its pinned source, built
   with CUDA 13.4.92 as its release states), its `.ninfer` artifact checked against its published SHA-256, and its
   recommended production profile as the adapter's known-good preset: a 131,072-token context, Q4 KV, MTP with 3 draft
   tokens, CUDA graphs, host-mapped embeddings. Any deviation the local machine forces (a different CUDA version under
   WSL2, for example) is recorded with the setup.

Later setups (KVMem with NInfer, vLLM, others) are added the same way.

## Alternatives considered
- **One engine with many flags.** Not possible: these are different programs with different model formats.
- **Only endpoints ("bring your own server").** Loses what Clank adds for a managed engine: launch control, the memory
  fit check, trials, and measurements.

## Consequences
- The adapter interface must fit three different programs from its first version, and its tests run against all three
  (with fake servers, and with the real engines where installed).
- A model can exist in several formats (GGUF, `.ninfer`); the catalog (design 0001 §2) tracks each file.
- Request options differ per setup (NInfer takes `min_p` only as a launch flag, for example); the gateway's
  translation (design 0001 §6) and the console show each difference.
- Principle 2 now names plug and play explicitly.
