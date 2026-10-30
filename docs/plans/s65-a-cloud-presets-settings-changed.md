# Plan s65: a cloud preset's settings changed

Design 0016 §7, §15 and §16, design 0003 §8.2 and design 0012 §4.1, revised after approval on 2026-10-29 at the
owner's request. The owner, testing a free reasoning model of NVIDIA's through OpenRouter: "after the model is set up, I
would like to be able to increase the number of output tokens from the number that I initially set up. How can we do
this?", and "the reason the model keeps stopping is because it is hitting its thinking limit, which I don't want it to
do so I need to be able to change that." A model's thinking counts against the preset's most output (`max_output`; by
default the smaller of 16,384 and the model's own), and nothing changed a cloud preset after Add a model wrote it.

## What exists

- `Endpoints.write_preset` writes a cloud preset from a model of the provider's list, its options validated by the
  adapter (`preset_options`: context, max_output, reasoning, images); a title that exists is refused with 409.
- A cloud slot's route is its launch's, kept when it loaded (`cloud.prepare`, `state.set_route`): the gateway reads
  the thinking effort it adds from it, and the agents read OpenCode's limits from it (`Agents._model`), so a preset
  changed on disk reached neither until the slot loaded again.
- OpenCode reads its model's limits from its configuration when it starts (`prepare`, `configure`); `model_changed`
  tells the owner's window that its model changed (after a flow's box switched the slot) until OpenCode starts again.
- OpenCode caps each answer at 32,000 tokens unless `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` says more; Clank never set
  it. Read in OpenCode 1.19.4's source (the image's version, tag `v1.19.4` of anomalyco/opencode): the variable is read
  once at start as a positive whole number (`effect/runtime-flags.ts`); each request's output limit, sent as
  `max_tokens`, is the smaller of the model's `limit.output` and the variable, else 32,000
  (`provider/transform.ts`'s `maxOutputTokens`, `session/llm/request.ts`); the compaction line is the window it is
  told less that same number (`session/overflow.ts`, through `session/compaction.ts`, checked before each step by
  `session/prompt.ts`; the processor's own check after a step counts 32,000 and so is the higher line); what a
  compaction keeps still counts 32,000, whatever the variable (`session/compaction.ts`'s `preserveRecentBudget`).

## Choices made here

- **One route for every client**: `PATCH /api/v1/runtime/presets/{name}` with any of `context`, `max_output` and
  `reasoning`, merged into the preset's options and checked by the adapter against the model's limits as the provider
  lists them now; written over the record at its revision, with who did it. 404 for no preset; 400 with the adapter's
  words for a value beyond the model; a local preset refused, saying where its options change (its file: `o` on
  Presets, then `e` on Launch options).
- **The slot that runs it follows at once**: nothing runs on this machine for a cloud model, so its kept route is
  planned again as a load plans it (no request is sent), and the gateway follows it from the next request; the last
  configuration that worked keeps the new settings too. A preset's file changed by hand still applies at the next load.
- **The most output is at most half the context**: OpenCode keeps room for a whole answer in every request, so once it
  counts the whole most output, one near the context would leave the conversation no room (it would compact after
  every step). Half, with the margin's quarter at most (decision 0089), leaves at least a quarter of the context.
- **OpenCode is told the whole most output** (decision 0153): above 32,000, Clank sets
  `OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX` to it when OpenCode starts, says so in its notes, and counts the whole limit
  in the compaction line (the Monitor's and Watch for's); what a compaction keeps stays counted with 32,000.
- **Open windows are told** when the main slot's preset changed its limits: the agents hear `runtime.preset_changed`
  and give each running workspace with an OpenCode window the notice `model_changed` gives (This folder, VS Code),
  until OpenCode starts again there. The thinking effort needs no notice: the gateway adds it to the next request.
- **The words are the service's**: the route's answer says what changed, where it applies, and that OpenCode windows
  open now keep the limits they started with until they start again; the console's form takes its fields' words (the
  limits in the labels) from the preset's view (`settings`).

## Tasks

- [ ] 1. The service: `Endpoints.change_preset` and `PATCH /runtime/presets/{name}`; the half-context rule in
  `preset_options`; the slot that runs it following at once (`cloud.follow`); the event `runtime.preset_changed`; the
  words (`guide.preset_changed_said`, `guide.preset_settings`, the view's `settings`). Tests first:
  `tests/components/runtime/test_cloud_preset_change.py`.
- [ ] 2. The command: `clank preset change PRESET [--output N] [--context N] [--reasoning R] [--json]`, printing the
  service's words. Tests first: `tests/cli/test_preset_change_command.py`.
- [ ] 3. The console: `e` on the Presets page (a form filled with the preset's settings, the limits in its labels; the
  answer in a window, a refusal on the message line; on a local preset, where its options change), the keys bar and
  the page's explanation. Tests first: `tests/console/test_preset_change.py`.
- [ ] 4. OpenCode's cap: the variable set from the most output above 32,000 (`prepare`, `configure`), its note, and
  the compaction rule and Watch for's line in step. Tests first: `tests/components/agents/test_opencode_output.py`, and
  the rule's own tests revised.
- [ ] 5. Open windows told: the agents hear `runtime.preset_changed` and tell each OpenCode window open. Tests first:
  in `tests/components/agents/test_model_changed.py`.
- [ ] 6. Records: designs 0016 §6, §7, §15 and §16, 0003 §8.2 and 0012 §4.1 revised; decision 0153; the console's page and
  getting started; the generated pages.

## Progress

Written 2026-10-29, at the owner's request.
