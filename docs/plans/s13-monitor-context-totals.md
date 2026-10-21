# The Monitor, step 3: context totals, for whatever model is loaded: implementation plan

> At the owner's request (2026-10-18, design 0012 approved: "Approve all three"; §4 revised the same day: "please make
> sure that this is generalized to the specific choice of the LLM that is loaded since we will likely end up using
> different models for different purposes"; 2026-10-19: the new menu, the Monitor and flows built "as quickly as
> possible"). As for the earlier plans, the files, interfaces and tests by name and intent; the code is in the commits.

**Goal:** design 0012 §11 step 3: each engine adapter declares its context facts for a preset's options
(`context_facts`), each model of the catalog its template facts and its calibration (or that it has none); the routes
carry the slot's facts; and the Monitor's Context window panel shows the followed session's totals (how much of the
window it uses, how much is left before OpenCode compacts, the share read from the cache, what sits on the GPU, and
whose conversation the engine holds) from those facts only, never from one engine's or one model's numbers
([decision 0067](../decisions/0067-the-monitor-reads-the-loaded-models-facts.md)).

**Architecture:**

- **The engine's facts** (`clank/components/runtime/adapters/engine.py`): `ContextFacts` and `ExactWindow`, and the
  abstract `EngineAdapter.context_facts(options)`. KVMem's (`kvmem.py`) and llama.cpp's (`llamacpp.py`) declare theirs:
  the window and the output limit; the thinking budget when there is one; the exact window (KVMem's retrieval budget,
  in blocks of 128 with the first block kept, picked by likeness to the last user message, or the most recent) or none
  (the whole window attended); whether it runs on the GPU; whether it can count tokens; whether it keeps one
  conversation (so another's request takes it); and where its answer reports each figure (`fields`: dotted paths into
  the answer, `usage.prompt_cache_hit_tokens` for KVMem's cache, `timings.cache_n` for llama.cpp's). A figure an
  engine does not report has no path, and is shown as not reported.
- **The model's facts** (`clank/components/runtime/catalog.py`): a catalog entry may give its `template` (how it
  renders earlier thinking, how it writes tool calls, its reasoning markers, and where that was read) and its
  `calibration` (tokens per character by kind of part, and its measurement). None is calibrated yet (that needs the
  real model, design 0012 §4.2, step 12), so each says so.
- **The routes** (`clank/components/runtime/service.py`): `Runtime.facts(preset)` gives a preset's facts (its engine's,
  its model's), and `Runtime.route(name)` carries the slot's (`facts`, `None` while no engine runs). The gateway's
  service passes a preset's facts on (`Gateway.facts`), the way the agents component reaches the runtime (decision
  0019).
- **The gateway's activity** (`clank/components/gateway/activity.py`): a request that ended names its `preset` and
  keeps its `usage` and `timings` as the engine gave them, so the figures are read where each engine's facts say; and
  `slots` gives each slot's newest request (the oldest in flight, else the last that ended), so the page can say
  whose
  conversation the engine holds. The fake engine reports a prompt's size and its cached tokens in each style's own
  fields (`--fake-prompt-tokens`, `--fake-cached-tokens`).
- **The totals** (`clank/components/agents/context.py`, new): `totals(session, doing, routes, facts_of, compaction)`,
  a pure function: the session's last finished step (its own request that ended well) read by the facts of the preset
  that answered it; the compaction line and what a compaction keeps, by the agent program's own rule
  (`AgentProgram.compaction`, OpenCode's in `adapters/opencode.py`: the window less the output limit counted up to
  32,000, and min(15,000, max(2,000, a quarter of that)) kept); the GPU line; whose conversation the engine holds; and
  the slot's preset now, when it switched since that step. `Agents.context(workspace, session)` gathers what it needs
  from the gateway's service; `GET /agents/context/{workspace}/{session}` serves it.
- **The panel** (`clank/components/agents/console/contextpanel.py`, new): `ContextWindow`, the Session view's Context
  window panel's content, drawn from the totals alone by a pure `lines(totals, width, zone)`; `following.py` reads the
  totals of the followed session with its flow (once a second while the page is on screen, off the screen's thread),
  and the page draws them only when they changed (design 0001 §5.7).

**Tech stack:** Python 3.12, FastAPI, Textual 8.2.8, pytest with the repository's fake engine in its two styles
(`tests/fakes/engine.py`: KVMem and upstream llama.cpp) and the console's text snapshots.

**Spec:** [design 0012](../design/0012-the-monitor.md) §3 (the engine holds one conversation), §4 (whatever model is
loaded), §4.1 (how full, and how much is left), §4.4 (on the GPU exactly; its totals), §11 step 3; decisions
[0067](../decisions/0067-the-monitor-reads-the-loaded-models-facts.md) and
[0019](../decisions/0019-components-use-declared-public-functions.md) (a component uses another through its service).

## Global Constraints

- No new dependency. Tests first, each named as a sentence, each file's docstring naming the design sections it
  verifies. Tests use the fake engine and temporary homes only: no GPU, no real model, no container, never the owner's
  gateway (18210) or service (7720).
- Nothing in the Monitor names an engine or a model: every figure is read through the facts of the slot's preset. A
  new engine brings its facts with its adapter, a new model with its catalog entry.
- A fact an engine does not report shows as "not reported by this engine", never a number; a figure the engine
  reports but the last step's answer did not carry says that instead.
- Every field added to an answer is added, never renamed (the routes, the gateway's activity), so the gateway's
  process, Home, the machine column and the Requests page read them as before.
- The owner is the sole author of every commit (no trailer); American English.

## Measurements before this step (pending)

Design 0012 §10 lists two before step 3. Neither could run then: each needs the real model, which a GPU benchmark
used then. The code below does not wait for them.

- [ ] **Whether the pool's cap shrinks KVMem's 36,864 for Clank's preset** (`--kvmem-gpu-ratio`, 0.50 by default):
  `KVMEM_TRACE`'s pool line at the start of "daily 262K". The adapter's docstring reads that the cap binds only past
  about 245,000 tokens at q8_0 on a 16 GB card; if it binds sooner, `KvmemLlamacpp.context_facts` gives the smaller
  window, and nothing else changes.
- [ ] **Whether KVMem's refusal of a full context makes OpenCode compact or fail** (§4.1). Until then KVMem's facts
  say nothing of how it says the context is full (`full` is ""), and the compaction line is OpenCode's own rule only.
- [ ] **llama.cpp b11588's figures, recorded**: its answer's `usage` and `timings` (the cache in `timings.cache_n`, as
  its server's source reads), and its words for a prompt over its context, from the recorded install, into
  `tests/fixtures/llamacpp/b11588/`. Until then its `full` is "" too.

## Tasks

### Task 1: The engine's context facts

- [x] **Files:** `clank/components/runtime/adapters/engine.py` (`ExactWindow`, `ContextFacts`, abstract
  `context_facts`), `kvmem.py`, `llamacpp.py`; the tests' engine adapters that subclass `EngineAdapter`, if any.
- [x] **Interfaces:** `EngineAdapter.context_facts(options: Mapping[str, OptionValue]) -> ContextFacts`: the facts for
  a preset's options (its own, else Clank's defaults). `ContextFacts(window, output, thinking_budget, exact, on_gpu,
  counts_tokens, one_conversation, fields, full, source)`; `ExactWindow(tokens, block, first, picks)`;
  `ContextFacts.view()`, the facts as JSON.
- [x] **Tests:** `tests/components/runtime/test_context_facts.py` (design 0012 §4, §4.4, decision 0067):
  `test_kvmem_declares_its_window_its_output_its_thinking_budget_and_its_exact_window_for_a_presets_options`;
  `test_kvmem_with_a_budget_of_0_attends_its_whole_window_and_its_method_says_how_it_picks`;
  `test_kvmem_with_thinking_off_or_unlimited_has_no_thinking_budget`;
  `test_llamacpp_attends_its_whole_window_in_system_memory_counts_tokens_and_reports_its_cache_in_its_timings`;
  `test_every_engine_adapter_declares_its_context_facts_for_its_default_options`.

### Task 2: The model's template facts and its calibration

- [x] **Files:** `clank/components/runtime/catalog.py` (`TemplateFacts`, `Calibration`, `ModelEntry.template`,
  `ModelEntry.calibration`, `ModelEntry.facts_view()`), the Qwen3.8 entries of `clank/catalog/models/`.
- [x] **Interfaces:** `TemplateFacts(earlier_thinking: "dropped" | "kept" | "none", tool_calls: "xml" | "json",
  reasoning: list[str], source: str)`; `Calibration(tokens_per_character: dict[str, float], measured: str)`; both
  optional. `ModelEntry.facts_view()`: `{"id", "name", "template", "calibration"}` (`None` for what it has not).
- [x] **Tests:** `tests/components/runtime/test_context_facts.py`:
  `test_a_catalog_entry_may_give_its_templates_facts_and_its_calibration_and_says_when_it_has_neither`;
  `test_the_qwen38_models_say_their_template_leaves_earlier_thinking_out_and_writes_calls_as_xml`;
  `test_no_model_of_the_catalog_is_calibrated_yet`.

### Task 3: The routes carry the slot's facts

- [x] **Files:** `clank/components/runtime/service.py` (`Runtime.facts`, `Runtime.route`), `clank/components/gateway/
  service.py` (`Gateway.facts`); the routes' expected answer in `tests/components/gateway/test_service.py`.
- [x] **Interfaces:** `Runtime.facts(preset: str) -> dict | None`: `{"preset", "title", "engine": {"name", "label",
  "version", **ContextFacts.view()}, "model": ModelEntry.facts_view()}`, `None` for a preset, engine or model not
  known. `Runtime.route(name)` gains `facts` (the slot's preset's, `None` while no engine runs).
  `Gateway.facts(preset)` passes it on.
- [x] **Tests:** `tests/components/gateway/test_service.py`:
  `test_the_routes_give_the_main_slots_engine_its_model_name_and_its_limits` (its expected answer gains `facts`, and
  the ready slot's carry its engine's and its model's);
  `tests/components/runtime/test_context_facts.py`:
  `test_a_presets_facts_are_its_engines_for_its_options_and_its_models` (and `None` for an unknown preset).

### Task 4: The gateway's activity names what the totals read

- [x] **Files:** `clank/components/gateway/activity.py` (`_ended`: `preset`, `usage`, `timings`; `now`: `slots`),
  `tests/fakes/engine.py` (`--fake-prompt-tokens`, `--fake-cached-tokens`: KVMem's cache in its usage, llama.cpp's in
  its `timings`), the gateway's expected activity in `tests/components/gateway/test_service.py`.
- [x] **Interfaces:** a request that ended carries `preset` and `usage` and `timings` as the engine gave them (`None`
  when it gave none); `now()` gains `slots: {slot: {"id", "session", "parent", "time", "flying"}}`: each slot's newest
  request that reached its engine, in flight (the oldest begun: an engine that runs one request at a time reads them in
  turn, the others queue behind it) else the last that ended.
- [x] **Tests:** `tests/components/gateway/test_activity.py`:
  `test_a_request_that_ended_keeps_its_preset_and_the_engines_own_usage_and_timings`;
  `test_each_slots_newest_request_is_its_oldest_in_flight_else_its_last_that_ended`;
  `test_session_facts.py`:
  `test_each_fake_engine_style_reports_its_cached_tokens_in_its_own_field_through_the_gateway`.

### Task 5: A session's context totals in the service

- [x] **Files:** create `clank/components/agents/context.py`; `clank/components/agents/adapters/program.py`
  (`Compaction`, `AgentProgram.compaction`), `adapters/opencode.py`, `service.py` (`Agents.context`), `api.py`
  (`GET /agents/context/{workspace}/{session}`).
- [x] **Interfaces:** `Compaction(line, keeps, rule)`; `AgentProgram.compaction(window, output) -> Compaction | None`
  (OpenCode's: `line = window - min(output or 32000, 32000)`, `keeps = min(15000, max(2000, line // 4))`).
  `totals(session, doing, routes, facts_of, compaction) -> dict`: `slot` (`name`, `status`, `preset`, `title`: the
  slot now), `facts` (those the figures were read with: the last step's preset's, else the slot's now), `step` (the
  last finished step's request: `id`, `time`, `preset`), `window`, `output`, `line`, `keeps`, `rule`, `prompt`,
  `answer`, `used`, `left`, `share` (of the window), `cached`, `cache_reported` (the engine declares where),
  `cache_share`, `gpu` (`device`, `exact`, `block`, `first`, `picks`, `stored`, `attended`, `elsewhere`), `holder`
  (the slot's newest request with `this`, `subagent`, `taken`, and `lost`: why the engine holds no conversation, ""
  when it may), `switched` (the slot's preset now, when another than the step's: `preset`, `title`, `window`,
  `output`), `gateway` (its state, and why it did not answer). A preset's
  facts for the runtime and the tests alike: `clank.components.runtime.service.preset_facts(id, preset, model)`.
- [x] **Tests:** `tests/components/agents/test_monitor_context.py` (design 0012 §3, §4.1, §4.4, §11 step 3; decision
  0067), each with the facts of both real adapters, KVMem's and llama.cpp's:
  `test_262144_and_16384_give_a_compaction_line_of_245760_and_a_compaction_keeps_15000`;
  `test_used_is_the_last_finished_steps_prompt_and_answer_and_left_is_the_line_less_it`;
  `test_under_kvmem_a_stored_size_of_at_most_36864_is_all_on_the_gpu`;
  `test_under_kvmem_above_36864_the_rest_is_in_system_memory`;
  `test_under_llamacpp_the_whole_window_is_attended`;
  `test_the_cache_share_is_read_where_each_engine_says_it_reports_it`;
  `test_a_figure_an_engine_does_not_report_is_absent_never_a_number`;
  `test_a_slot_switch_to_another_preset_changes_the_window_at_the_next_step`;
  `test_another_sessions_request_marks_the_engine_as_taken` (in flight or ended; a subagent's; a request of no
  session; never for an engine that keeps more than one conversation);
  `test_with_no_step_ended_the_window_is_the_slots_and_what_is_used_is_not_known`;
  `test_the_totals_read_each_fake_engine_styles_own_fields_through_the_gateway` (a streamed request of a session
  through the gateway to the fake engine in each style, its activity read into `totals`);
  `test_the_services_context_route_gives_a_sessions_totals`.

### Task 6: The Context window panel

- [x] **Files:** create `clank/components/agents/console/contextpanel.py`; `following.py` (`Seen.context`; the totals
  read with the flow), `monitor.py` (the Session view's Context window panel holds a `ContextWindow`); the snapshots
  of the Session view with board A's flow (`tests/console/snapshots/monitor-session-flow-*.txt`: its Context window
  panel says "no model runs in the main slot", since no model runs in the tests), and a new one with a session on
  KVMem (`monitor-session-context-160.txt`); the page's test of empty panels (`test_monitor_page.py`).
- [x] **Interfaces:** `lines(totals: dict | None, width: int, zone) -> list[Content]`: the totals line (used of the
  window and its share, left before OpenCode compacts, the share read from the cache), the bar (used, the room left
  to the compaction line, the output kept for the answer in the style's `kept` cells), the GPU line, whose
  conversation the engine holds, where the figures come from (the engine and its version, the preset, the model and
  whether it is calibrated) and what a compaction keeps, and the slot's preset now when it switched; each cut with
  "…" to the width. `ContextWindow`, a
  focusable widget that draws them and draws again only when they changed.
- [x] **Tests:** `tests/console/test_monitor_context.py` (design 0012 §2, §4.1, §4.4, §11 step 3):
  `test_the_panel_says_used_left_and_the_cache_share_from_the_totals`;
  `test_the_gpu_line_under_kvmem_and_under_llamacpp`;
  `test_a_figure_not_reported_by_this_engine_is_said_so_and_a_model_without_calibration_too`;
  `test_the_panel_says_whose_conversation_the_engine_holds_and_when_another_took_it`;
  `test_the_panel_says_when_the_slot_switched_to_another_preset`;
  `test_no_line_is_wider_than_the_panel`;
  `test_the_monitor_shows_the_followed_sessions_totals_in_the_context_window_panel` (a snapshot at 160 columns, the
  gateway's activity and routes those of a session on KVMem);
  `test_totals_that_did_not_change_are_not_drawn_again`.

### Task 7: Documents

- [x] Design 0012: §11 step 3 marked built with this plan (and §4 revised if building it changed what it says); the
  design index; the roadmap's M5 row; the glossary (**Context facts**); this plan's checkboxes and the plans' index;
  the generated files regenerated (`uv run python -m tools.check --fix`).

- Built 2026-10-19, in six commits after this plan's (one per task), then this one. Found on the way: the console's
  snapshots replace an engine's version (`v0.16.0`) by `v0.0.0`, so the panel's frame reads "v0.0.0-rc1"; the
  gateway's activity of a session, faked in a console test, must carry every field a request that ended has, since
  Home and the machine column read the same route; a parametrized argument named like a fixture (`engine`) takes its
  place for the fixtures that depend on it, so the test's is named `adapter`.
- **Left for later**: the Context view's own panels (its totals across the page, the parts, the GPU's picks, the
  growth, where the figures come from) are step 12's, with the parts' estimate; the growth spark is step 7's. The
  gateway's `prompt_tokens` of a request that ended still prefers llama.cpp's `timings.prompt_n` (the tokens it read,
  not the prompt's size); the totals read `usage.prompt_tokens` through the facts, so they are right, and the Requests
  page's figure for llama.cpp is left as it was.

## Claude's calls (2026-10-19)

- **The totals are made in the service**, by the agents component, from the gateway's figures and the slot's facts,
  and the console only draws them: design 0012 §2 keeps the session's flow in the service "so the phone can show it
  later", and the totals are its companion.
- **Used is the gateway's**, the engine's own count of the session's last finished step (its prompt and its answer,
  read where the engine's facts say), not OpenCode's step tokens: they come from the same answer, and the gateway has
  them for every engine without knowing how OpenCode stores them.
- **The window is the step's**: the totals read the facts of the preset that answered the session's last finished
  step, and say when the slot runs another preset now; the window, the line and the GPU line change with the next step
  (§4: "when the slot switches, the panel says so ... change with the next step"). With no step yet, the slot's facts
  now.
- **"Taken" only for an engine that keeps one conversation** (`one_conversation`: KVMem, design 0012 §3). llama.cpp
  may keep several (its slots, its prompt cache in system memory), so for it the panel names whose request came last
  and claims nothing more. Any request that reached the engine counts, a subagent's or one of no session too, since
  each is another conversation.
- **llama.cpp's `full` stays ""** until its answer to a full context is recorded, and KVMem's until it is measured:
  "nothing claimed that is not known".
- **The engine's newest request is the oldest in flight**, else the last that ended: an engine that runs one request at
  a time reads them in turn, so the oldest in flight is the one it reads (or will read first); one that never reached
  the engine (refused, or a title the gateway answered itself) never counts.
- **The compaction rule is the agent program's** (`AgentProgram.compaction`, OpenCode's), not the engine's: OpenCode
  decides when to compact from the limits Clank gave it. The totals assume OpenCode was given the limits of the preset
  that answered the last step (Clank writes them when it prepares the agent); a preset switched under a running
  OpenCode leaves OpenCode's own limits as they were until it is prepared again, which the panel cannot see.
- **The Qwen3.8 models' template facts are the reference template's**, as design 0012 §4.2 reads it, marked as still
  to read in the model file (§10); the vision and completion models give none yet, and say so.

## After review (2026-10-19)

The review of the built step found two gaps on error and state-change paths and three smaller ones; each is fixed and
tested:

- **A stream the engine broke off is not a finished step.** The gateway's activity now says `broken` for a request
  whose engine broke off its answer, and the totals skip it, so the panel keeps the step before it. A step that ended
  well but whose answer did not report its size says so ("the last step's answer did not report its size"), instead of
  "no step has ended".
- **An engine that stopped, started again or was switched holds no conversation** (`holder.lost`). The gateway's
  routes count each slot's engine (`Routes.generation`: it moves when the slot's state, preset or port changes), and a
  slot's last request that ended is `gone` once it moved, which catches a crash the runtime restarted with the same
  preset. The totals add the slot's state now (not ready) and a switch. The panel then says the engine holds no
  conversation and that this session's tokens are read again at its next step, and never that it holds this one.
- **A request the gateway refused after routing it** (`engine_unreachable`, `engine_broke_off`) is never a slot's
  newest request.
- **Two requests in flight that began at the same moment** no longer break the activity (its sort compared records).
- **Totals the service refused** are drawn as "context totals not available: why", not as "no session yet".
