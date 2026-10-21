# Sampling and the GPU's layers: implementation plan

> At the owner's request (2026-10-21): "Let's go ahead and fix this gap in Clank so that these settings are visible."
> As for the other plans, the files, interfaces and tests by name and intent; the code is in the commits.

**Goal:** design 0003 §4.1: KVMem's GPU layers and its sampling, and llama.cpp's sampling, become launch options,
unset unless a preset sets them, and every place that shows a preset's settings shows the sampling in effect with the
engine's own defaults; the memory estimate follows fewer layers on the GPU.

**Spec:** [design 0003 §4.1](../design/0003-the-runtime.md#41-sampling-and-the-gpus-layers);
[decision 0119](../decisions/0119-sampling-and-gpu-layers-are-launch-options-left-unset.md); design 0001 §3.2 as revised.

## Global Constraints

- No preset Clank ships changes what it launches: a test holds each one's command line, written first.
- Nothing runs a real engine, the GPU, Docker, the service on 7720 or the gateway on 18210; the flags are checked
  against the recorded `--help` of each engine (`tests/fixtures/`), as the contract test does.
- No new dependency; the owner is the sole author of every commit; American English; tests named as sentences.

## Tasks

- [x] **The shipped presets, held:** each preset in `clank/defaults/presets/` planned with a fixed launch gives exactly
  the command line and environment it gives today (`tests/components/runtime/test_shipped_presets.py`), written before
  any option is added and kept green through the rest.
- [x] **What an option says of the engine's default:** `EngineOption.engine_default_words` (what the engine does when
  the option is not given, where one value cannot say it) and `more_than` (a bound the value must pass, for a
  repeat penalty above 0); the options view carries the words (`engine.py`, `launching.options_view`;
  `tests/components/runtime/test_options.py`).
- [x] **KVMem's options:** `gpu_layers` (`-ngl`, 0 or more, the engine's own 99 leaving the flag out) and
  `sampling.temperature`, `sampling.top_p`, `sampling.top_k`, `sampling.min_p`, `sampling.presence_penalty`,
  `sampling.frequency_penalty`, `sampling.repeat_penalty`, `sampling.seed`, each with KVMem's bounds and its own
  default in words; unset, no flag; set, always the flag, for both modes (`kvmem.py`;
  `tests/components/runtime/test_kvmem_sampling.py`; the contract test finds every flag in the recorded `--help`).
- [x] **The estimate with fewer layers:** the catalog's `layers` (66) for the three Qwen3.8 files under KVMem; with
  `gpu_layers` below it, that share of the weights on the GPU, the rest named in system memory, the KV cache and the
  buffers kept whole, said to be an estimate; without `layers`, the weights kept whole and said so (`kvmem.py`,
  `clank/catalog/models/*.json`; `tests/components/runtime/test_kvmem_sampling.py`).
- [ ] **llama.cpp's sampling:** the same eight keys from b11588's `--help` (`--temp`, `--top-p`, `--top-k`,
  `--min-p`, `--presence-penalty`, `--frequency-penalty`, `--repeat-penalty`, `--seed`), their defaults in words with
  the model file's own where it may carry one; unset, no flag (`llamacpp.py`;
  `tests/components/runtime/test_llamacpp.py`).
- [ ] **The preset's sampling in its view and `clank preset show`:** `GET /runtime/presets` and
  `/runtime/presets/{name}` give each preset's `sampling` (each option's value or its engine's default in words);
  `clank preset show` prints them under "sampling" with a request's own values said to win
  (`service.py`, `cli.py`; `tests/components/runtime/test_presets.py`).
- [ ] **The Launch options page and the Presets page:** an unset option shows the engine's own default in words, a set
  one the default it replaces; a line says a request's own sampling wins; the Presets page's Settings panel lists the
  sampling in effect (`console/options.py`, `console/presets.py`; `tests/components/runtime/test_console_options.py`,
  `tests/components/runtime/test_console_presets.py`).
- [ ] **The Requests page:** a kept request's own sampling fields (`records.find`'s `sampling`; none when the request
  was not kept), shown on the highlighted request beside the preset's values (`gateway/records.py`,
  `gateway/console/requests.py`; `tests/components/gateway/test_recent_requests.py`,
  `tests/console/test_requests_page.py`).
- [ ] **Documents:** the roadmap, the glossary, this plan; the generated files regenerated; the full check.

## What only a real launch can confirm

- That KVMem v0.16 starts, and retrieves as it should, with `gpu_layers` below 66, and what it then takes of the GPU
  and of system memory (the estimate keeps the KV cache whole on the GPU, the safe side).
- That a sampling flag reaches each request: KVMem's log line `KVMEM_TRACE sampling thinking=... temperature=...`
  says what each request ran with.
