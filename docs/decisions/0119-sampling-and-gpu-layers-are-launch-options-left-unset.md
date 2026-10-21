# 0119. An engine's sampling and its GPU layers are launch options, left unset unless a preset sets them, and shown with the engine's own defaults

- Status: Accepted (the owner's request; how it is done is Claude's call, open to the owner's change)
- Date: 2026-10-21
- Decided by: the owner's request, "Let's go ahead and fix this gap in Clank so that these settings are visible"; the
  choices below are Claude's

## Context
KVMem's server (v0.16.0-rc1) takes `-ngl` (the model's layers on the GPU, 99 by default: every layer) and eight
sampling flags (`--temp`, `--top-p`, `--top-k`, `--min-p`, `--presence-penalty`, `--frequency-penalty`,
`--repeat-penalty`, `--seed`). Its sampling defaults differ by thinking mode: temperature 1.0 with thinking and 0.7
without, top_p 0.95 and 0.80, presence penalty 0 and 1.5. Each request gets its mode's defaults, then the flags, then
its own fields. Clank's adapter declared none of them, so the sampling in effect could be neither seen nor changed from
Clank. On 2026-10-18 a runaway answer ran with a presence penalty of 0 that nothing showed. Design 0001 §3.2 named
sampling as request options, set per role by the gateway (decision 0004), which is not built.

## Decision
- **Launch options.** KVMem's adapter declares `gpu_layers` and `sampling.temperature`, `sampling.top_p`,
  `sampling.top_k`, `sampling.min_p`, `sampling.presence_penalty`, `sampling.frequency_penalty`,
  `sampling.repeat_penalty` and `sampling.seed`, with the bounds its server checks. llama.cpp's adapter declares the
  same sampling keys, from its b11588 `--help`.
- **Unset by default.** None has a Clank default. Unset, no flag is passed and the engine keeps its own defaults,
  per mode (and, for llama.cpp, a model file's own). Set, the flag is always passed, even at a value one of the
  engine's defaults has, because it then holds for both modes. No preset Clank ships sets one, so every preset
  launches exactly as before.
- **The engine's own default, in words.** An option may carry `engine_default_words`, what the engine does when it is
  not given, where one value cannot say it ("1.0 thinking, 0.7 not thinking"). Every place that shows a preset's
  settings shows them: the Launch options page, the Presets page, `clank preset show`. The Requests page shows a
  request's own sampling fields beside the preset's.
- **Fewer layers, roughly estimated.** With `gpu_layers` below the model's layers (a new `layers` size in the catalog,
  66 for Qwen3.8-27B as KVMem's log counts them), the estimate puts that share of the weights on the GPU and says the
  rest is in system memory. It keeps the KV cache and the buffers whole on the GPU, the safe side. A value below 0 is
  refused.

## Alternatives considered
- **Clank's own defaults for sampling, written on every launch.** One value would replace both modes' defaults, so
  turning thinking off would no longer lower the temperature or raise the presence penalty. It would also change
  every preset's command line.
- **Sampling only as request options, set by the gateway per role (decision 0004).** It is the right place for values
  that differ by role, and stays to build. But it changes what reaches the engine on every request, which is a larger
  change than showing and setting the engine's own defaults. The engine's defaults would still need showing as the
  base that per-role values replace.
- **Showing a single default value, the thinking mode's.** Simpler, but it would say 0 for the presence penalty, the
  very value that hid the loop, while requests without thinking get 1.5.
- **Leaving a set value out when it equals an engine default (as other options do).** For a per-mode default it is
  not the same: 1.0 set means 1.0 in both modes, which the default does not.
- **Splitting the weights and the KV cache by layer in the estimate.** KVMem's own placement of a cache whose layer
  is in system memory is not known without a launch, so the estimate does not guess it.

## Consequences
- The owner can see every sampling value in effect, and set one in a preset file, from today. A setting is applied at
  the slot's next start, like any launch option.
- A request's own fields still win (OpenCode may send its own temperature). The Requests page shows them, so a
  difference from the preset is visible. Reading the sampling KVMem actually used from its log
  (`KVMEM_TRACE sampling`) is left for later.
- `gpu_layers` below every layer is untested on this machine. The estimate is rough, and only a real launch can say
  how KVMem behaves and what it takes then.
- When per-role sampling (decision 0004) is built, the gateway's role values replace a tool's on each request, and so
  win over a preset's; they are to be shown the same way.
