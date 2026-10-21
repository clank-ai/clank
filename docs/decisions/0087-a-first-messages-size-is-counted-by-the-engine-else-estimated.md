# 0087. A first message's size is counted by the engine when it can, else estimated and said so; the check warns past a quarter of the window

- Status: Accepted, as Claude's call; the owner may reverse it
- Date: 2026-10-20
- Decided by: the owner asked for a preview of each box's first message with its size in tokens against its model's
  window, and for `clank flow check` to warn past a quarter of the window and on a file a box sees that nothing gives
  it (2026-10-20: "use what Clank already has ... else an estimate clearly labeled as one; never pretend an estimate is
  exact"); how it counts and what it says, Claude's call while building ([plan
  s30](../plans/s30-flows-each-box-prepared.md))

## Context
A box's first message now hands the brief, a map, the notes of the boxes before it and the files it sees
([0085](0085-a-boxs-first-message-hands-the-brief-and-a-map-of-the-flow.md),
[0086](0086-a-box-hands-on-a-short-note.md)), so its size grows with the flow. A first prompt is read without the
cache: KVMem took 13 s to the first token for about 8K tokens and 41 s for about 31K (design 0013 §7). What Clank knows
of a preset's context is its engine adapter's context facts (design 0012 §4, decision 0067): the window, and whether
the engine counts tokens (upstream llama.cpp's `/tokenize`; KVMem cannot); and its model's calibration in the catalog
(tokens per character, by kind of part), which no model has yet. Clank has no tokenizer of its own.

## Decision
- **Exact only from the engine.** A first message is counted exactly when the main slot runs the box's preset now and
  its engine counts tokens: the runtime asks the engine (`Runtime.count_tokens`, the adapter naming its route,
  llama.cpp's `/tokenize`). Nothing is loaded to count.
- **Else an estimate, said so.** From the model's calibration (its figure for a user's message), else Clank's plain
  default of 0.3 tokens per character (about 3.3 characters a token: above what prose takes, near what code takes, so
  the estimate errs large). Every estimate is labeled "estimate" with how it was made, in the API (`exact: false`,
  `counted`) and in every command's words.
- **The window** is the box's preset's (its own, a VERIFY's the box it checks', else the flow's), else, for a box
  naming none, the preset the main slot runs now; with neither, the window is not known, and the preview says so.
- **What is counted:** the first message alone. OpenCode adds its own instructions and tool definitions (their size is
  to measure, §7), and files and notes not written yet are not counted; the preview says both.
- **Served like the other flow commands:** `GET /flows/{workspace}/{name}/prepare` (every box a model runs, or `box`
  alone), each first message built by the runner's own function from the files as they are now and, while a run is
  active, its state, so the preview is the message that would be sent; `clank flow prepare NAME [BOX]` lists each
  box's size, or shows one box's message whole.
- **The check warns, never refuses.** `clank flow check` lists warnings after the problems, and only problems fail
  it: a box whose first message would be over a quarter of its window; a file a box sees or shows that is neither in
  the folder nor written by that box or one before it.

## Alternatives considered
- **A tokenizer in Clank** (the model's own, from its files): exact everywhere, but a new dependency and a tokenizer
  per model to keep.
- **Loading the box's preset to count**: exact, but a switch costs about 20 s and evicts the owner's conversation from
  the engine (§7), for a preview.
- **Refusing a flow past a quarter**: the folder's files change while a flow runs, and a large first message may be
  the owner's intent; the owner decides.
- **No count without the engine**: the owner's main engine (KVMem) cannot count, so the preview would say nothing
  useful there.

## Consequences
- On KVMem every count is an estimate, and says so; once a model is calibrated (design 0012 §4.2), its estimates come
  closer with no change here.
- A box's preview reads the folder and may ask the engine to count: a few milliseconds of the engine's time while it
  runs that preset, nothing loaded or switched.
- How far the estimate is from the engine's own count on a real first message, and how large OpenCode's own part is,
  are to measure on the real model.
