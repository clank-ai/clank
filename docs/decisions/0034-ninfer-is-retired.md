# 0034. NInfer is retired: KVMem serves the model, and Clank stays built for other engines and models

- Status: Accepted; supersedes [0031](0031-ninfer-follows-the-driver.md), and narrows the first serving setups of
  [0010](0010-serving-setups-are-plug-and-play.md)
- Date: 2026-10-13
- Decided by: the owner: "If NInfer-5080 is dramatically less useful as KVMem, then we should scrap the NInfer
  implementation, delete this so that we aren't taking up too much room, and just continue using KVMem while making
  sure that everything is built for me to be able to change the model out later on (for example, loading smaller
  models)"; Claude judged it so from the measurement below; the owner then said "Go ahead and fully retire NInfer"

## Context
M1 brought two serving setups for Qwen3.8-27B on the owner's RTX 5080 (design 0003): KVMem/llama.cpp, adopted where it
was built, and NInfer RTX 5080 v1.4, built by Clank's recipe. [The measurement of
2026-10-13](../measurements/2026-10-13-ninfer-and-kvmem.md) compared them through Clank:

- **Context.** KVMem serves 262,144 tokens (36,864 attended exactly, the rest retrieved from system memory) and recalled
  8 of 8 facts at 116K and 145K. NInfer fits 45,056 tokens beside this desktop; its published 131,072 needs a 5080 that
  drives no display, whatever its version (design 0004 §7).
- **The owner's work.** On ten coding tasks both passed the same eight, but KVMem took 23.7 minutes and 90 steps, and
  NInfer 43.1 minutes and 149 steps, writing 83% more tokens.
- **What it can do.** KVMem read an image and kept to JSON mode; NInfer's preset had its vision off to fit, and did not
  keep to JSON mode. NInfer also refused llama.cpp's request fields, and once failed to start at random.
- **Speed.** NInfer read long prompts about twice as fast (822-2,001 tokens a second against 593-836, from 8K tokens up); writing was
  similar.

NInfer's files took 20.2 GB in the `Ubuntu` distribution (its build 3.7 GB, its model 16.5 GB).

## Decision
- NInfer leaves Clank: its adapter, its recipes, its presets, its catalog entries and sizes, its recordings, and the
  tests that used it. Its files are taken off the owner's machine with Clank's own commands, `clank model remove` and
  `clank engine uninstall` (design 0003 §7.5), which the owner asked for at the same time.
- KVMem/llama.cpp serves the model, as before.
- What lets Clank change its engine or its model stays, so the next one is a module and a catalog entry, not a
  rewrite: engines are adapters (decision 0010); a model is a catalog entry with its files and the sizes its estimate
  needs; a model's files can be removed and downloaded again with its presets kept. Two engine-neutral parts NInfer
  first needed stay too: the memory fit of an engine that sizes its own KV cache, and the estimate learning from what
  an engine says it needed to start; vLLM and SGLang work that way.
- What was measured and decided while Clank had NInfer stays where it was written: the measurement, decisions 0010
  and 0031, designs 0001-0004 (their NInfer sections marked retired), the finished plans.

## Alternatives considered
- **Keep NInfer beside KVMem, for its faster reading.** Its context and its results on the owner's tasks matter more
  than reading speed, and keeping it means 20 GB of disk, a recipe and an adapter to maintain for a setup the owner
  would not use.
- **Keep NInfer's code without its files.** Code nobody runs drifts, and the owner asked for it gone; its history keeps
  it, should a 5080 that drives no display ever make its 131,072 tokens possible.
- **Remove the engine-neutral parts too.** They are small and tested, and the engines most likely to come next need
  them.

## Consequences
- One serving setup today: the menu, the console's pages and `clank engine list` show KVMem only; the rig in the tests
  has two KVMem presets (8K and 4K), the smaller one made to fail where a test needs a failing switch.
- The catalog lists GGUF files only, and `--format` takes `gguf`.
- No recipe ships until KVMem's own (decision 0033's consequence): the recipe loader takes none as none.
- Decision 0031 no longer applies; NInfer's part of design 0004 §7 is history.
