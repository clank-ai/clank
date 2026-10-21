# 0067. The Monitor reads every context figure from the loaded slot's engine and model

- Status: Accepted (the owner's request, 2026-10-18, revising design 0012 §4 after its approval)
- Date: 2026-10-18
- Decided by: the owner ("please make sure that this is generalized to the specific choice of the LLM that is loaded")

## Context
Design 0012 §4 described the context window with KVMem's own figures: its 36,864-token exact window, its first block
of 128 tokens, its pick by likeness to the last user message, its `prompt_cache_hit_tokens`, its lack of a counting
route. The owner, the same day it was approved: "when you are building the context monitor, please make sure that this
is generalized to the specific choice of the LLM that is loaded since we will likely end up using different models for
different purposes, so this should be built in a way that will let allow us to generalize easily." Flows already load
a preset per box (design 0013 §7), so one session may meet several engines and models in an afternoon.

## Decision
Every figure the Monitor shows about the context comes from the slot the followed session's requests reach, through
two declarations:

- **The engine's context facts**, declared by its adapter for a preset's options (`context_facts`): the window and the
  output limit; the thinking budget, when it has one; an exact-attention window and how it chooses (KVMem's), or none
  (the whole window attended); whether it can count tokens (upstream llama.cpp's `/tokenize`; KVMem cannot); the fields
  it reports its cache and timings in; and how it says the context is full.
- **The model's template facts and calibration**, in its catalog entry: how its template renders earlier thinking and
  tool calls, its reasoning markers, and its tokens per character by kind of part, measured once per model.

A fact an engine does not report shows as "not reported by this engine", never as a number. A new engine brings its
facts with its adapter, a new model with its catalog entry; the Monitor does not change.

## Alternatives considered
- **KVMem's figures in the Monitor, others added later.** Each new engine would then change the page, and the figures
  of one would be shown for another.
- **Asking each engine at run time for its facts.** Engines report few of them (KVMem only usage totals); the adapter
  already knows its engine's options, and the catalog its model's template.
- **One calibration for every model.** Tokens per character differ by tokenizer; a model with none uses a plain
  default and says so.

## Consequences
- Design 0012's step 3 builds the adapters' `context_facts` and the catalog's template facts, and is tested with both
  fake engine styles (KVMem and upstream llama.cpp).
- A model added from Hugging Face needs its template facts and a calibration run before its estimate is labeled as
  calibrated.
- The figures in design 0012 are the preset "daily 262K"'s, given as examples.
