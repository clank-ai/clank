# 0153. OpenCode is told the whole most output: above 32,000, Clank lifts OpenCode's own cap, and a cloud preset's most output is at most half its context

- Status: Accepted (Claude's call, building the owner's request of 2026-10-29); revises how design 0012 §4.1 counts the
  output limit in the compaction line
- Date: 2026-10-29
- Decided by: Claude, building the owner's request: "after the model is set up, I would like to be able to increase the
  number of output tokens from the number that I initially set up", and "the reason the model keeps stopping is because
  it is hitting its thinking limit, which I don't want it to do so I need to be able to change that"

## Context

- A cloud preset's most output (`max_output`) holds a model's thinking and its answer together. Add a model sets it to
  the smaller of 16,384 and the model's own most; a reasoning model that thinks longer than that stops mid-thought. On
  2026-10-29, 316 of the 366 models OpenRouter lists with tool calls gave a most output above 32,000 (NVIDIA's free
  reasoning models 65,536 or 131,072).
- OpenCode caps each answer at 32,000 tokens unless `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` says more. Read in the
  source of OpenCode 1.19.4, the version Clank's sandbox image installs (tag `v1.19.4` of anomalyco/opencode, formerly
  sst/opencode):
  - `packages/opencode/src/effect/runtime-flags.ts` reads the variable once, when OpenCode starts, as a positive whole
    number; anything else counts as unset.
  - `packages/opencode/src/provider/transform.ts`: `maxOutputTokens(model, cap = 32_000)` is
    `min(model.limit.output, cap)`. `packages/opencode/src/session/llm/request.ts` sends that as each request's output
    limit (`max_tokens`), the variable as the cap.
  - `packages/opencode/src/session/overflow.ts`: the compaction line is the window it is told less that same number.
    `session/compaction.ts` passes the variable to it, and `session/prompt.ts` checks the last finished step against
    it before each step. The processor's own check after a step (`session/processor.ts`) counts 32,000; when the
    variable is larger, that line is the higher one, so the variable's decides.
  - `session/compaction.ts`'s `preserveRecentBudget` sizes what a compaction keeps from `usable` without the variable,
    so it still counts 32,000.
- So without the variable, raising a preset's most output above 32,000 would change nothing in what OpenCode asks for.

## Decision

- **The variable follows the most output.** When the model the agent's role runs has an output limit above 32,000,
  Clank starts OpenCode with `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` set to that limit: from a terminal (`prepare`)
  and without one (`configure`, the phone's sessions and the flows' servers). At 32,000 or under, it sets nothing.
  `clank work` and the agent's plan say so in their notes.
- **The compaction rule follows OpenCode.** The Monitor's compaction line and Watch for's count the whole output
  limit. What a compaction keeps is still counted with 32,000, as OpenCode counts it (`OpenCode.compaction`,
  `counted_output`).
- **A cloud preset's most output is at most half its context.** OpenCode keeps room for a whole answer in every
  request. Once it counts the whole most output, one near the context would leave the conversation no room, and
  OpenCode would compact after every step. Half the context, with the margin's quarter at most (decision 0089), leaves
  the conversation at least a quarter. The adapter refuses more, in words (`preset_options`), whether Add a model
  writes the preset or a change makes it. A preset's default most output stays within half its context.

## Alternatives considered

- **Leave OpenCode's cap, and say it** (what Clank would do had the source not been read): the words would say that
  OpenCode sends at most 32,000 an answer, but the owner's reasoning model would still stop at 32,000, with a most
  output of 65,536 set and shown.
- **Always set the variable** to the most output, at 32,000 and under too: it would change nothing in what OpenCode
  does, and would add a setting to every OpenCode start for no reason.
- **Set it to the model's own most** in place of the preset's: OpenCode would ask for more than the owner chose, and
  the compaction line would move with a number the owner never set.
- **No bound but the model's most**: a most output near the context would make OpenCode compact after every step, an
  agent that never gets anything done, and the owner's request was the opposite.
- **Clamp the most output silently** when OpenCode starts: a setting the owner sees and one Clank uses would differ,
  which AGENTS.md calls a bug.

## Consequences

- A reasoning model's thinking can use all of the most output the owner sets, up to the model's own and half the
  context. OpenCode then compacts sooner, since it keeps that much room free in every request. The change's words say
  so, and so does the Presets page's form.
- The variable is experimental in OpenCode. When the image moves to another version of OpenCode, its source is read
  again for this variable and the rule, and design 0012 §4.1 and this decision say what changed.
- Changing a preset's most output reaches an open OpenCode window only when it starts again: the window is told so.
