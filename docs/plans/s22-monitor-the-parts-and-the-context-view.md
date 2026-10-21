# The Monitor, step 12: the parts, the biggest items, loop text and the Context view: implementation plan

> At the owner's request (2026-10-18, design 0012 approved: "Approve all three"; 2026-10-19: the new menu, the Monitor
> and flows built "as quickly as possible"). As for the earlier plans, the files, interfaces and tests by name and
> intent; the code is in the commits.

**Goal:** design 0012 §11 step 12 (§4.2, §4.3, §4.6, §4.7; decisions 0051 and 0052): what fills the context window,
part by part. During a long session the owner sees what fills it (the system prompt, the tool definitions, their
messages, the model's text, the thinking sent back, the calls, the tool results, and loop text), which single items are
biggest and in which step they came, and how close the session is to the window; it is also where they look after a
session failed at a full context. The Session view's Context window panel draws its bar by part with what each part
holds, and its **Biggest in the context** panel lists the largest items; Enter on the Context window opens the
**Context view** (board C): the totals and the bar across the page, **What is in it** (each part: its tokens, share,
items, the biggest, its last ten steps; ↑↓ through the parts, Enter lists a part's items), **On the GPU exactly**,
**Over this session** (a chart of the session's size at each step, split by part), **Where the room went**, **Could be
freed** (Enter on Compact now asks, as `k` does) and **Where these figures come from**. Every figure is the loaded
model's (decision 0067); every estimate says it is one.

**Architecture:**

- **The census, in the gateway** (`clank/components/gateway/census.py`, new, pure): one pass over a request's body as
  the gateway parsed it, no engine work, no new dependency (§4.2): the characters of each part (the thinking apart
  before and after the last real user message, so the template's rule can be applied where the model's facts are
  read), each item (a message's text, a thinking, a call, a result, a tool's definition) with what it is, its call id
  (a result's `tool_call_id`, which is OpenCode's call id; a message's own calls' ids), its place, and the characters
  after it (for the tail a compaction keeps); loop text by the guard's measure over whole items (`loops.py`'s share,
  its ratio, its shortest stretch), the result that echoes a call that looped, and the third and later identical call
  in the last twelve (§4.3, decision 0052); the earlier results of a call made again with the same arguments (what
  "could be freed" names "the earlier reads of a file read again", §4.6). It keeps the biggest items (`KEPT`, and each
  part's `PER_PART`), so a request of hundreds of items is kept in a few kilobytes.
- **The gateway** (`server.py`, `activity.py`): each request's census, made off the event loop once its body is read
  (a title the gateway answers itself has none); a request that ended keeps it among its session's requests that
  ended (`ended`), whole for the newest one that ended well and the ones after it, numbers only for the older ones
  (their parts, for the last ten steps). Never in the records: a census holds words of the request, which the records
  may be told not to keep.
- **The estimate, in the service** (`clank/components/agents/estimate.py`, new, pure): the census's characters, weighted
  by the model's calibration (each part's tokens per character; without one, every part alike, said so), with the
  template's rule for earlier thinking (`dropped`: left out; `kept`; `none`: no thinking part), shared out so the parts
  add up to the engine's own `prompt_tokens` exactly (largest remainder); each item's tokens, its step (its call id
  joined to the flow's call and its step's number; a message without calls by its neighbors in the request), whether
  OpenCode cleared it, whether it lies in the tail a compaction keeps; where the room went (results by tool, thinking,
  loop text, OpenCode's own system prompt and tools); what could be freed (the loop text, the earlier results of calls
  made again, compact now); the tokens from the last user message on (KVMem's newest block, about). The context totals
  (`context.py`) carry it (`parts`), and each ended request's parts (`steps`), from the facts of the preset that
  answered it. The scaling is done here, where each engine's figures are read by its facts (decision 0067), and the
  pass over the body in the gateway, which has it (decision 0051's "estimated in the gateway").
- **The console** (`clank/components/agents/console/`): `parts.py` (new: each part's label and color, tokens briefly,
  the bar by part and its legend), `contextpanel.py` (the Session view's bar by part and its legend line),
  `biggestpanel.py` (new: the Biggest panel's list, Enter an item's details), `contextview.py` (new: the Context view's
  panels and their lines), `monitor.py` (the Context view's widgets, its keys: ↑↓, Enter, `k`, Esc).

**Tech stack:** Python 3.12, FastAPI, Textual 8.2.8, zlib (the standard library's, as the loop guard), pytest with the
console's text snapshots at 128, 88 and 60 columns of page (as the Flow view's), synthetic requests and sessions
(`tests/support/requests.py`, new: board A's request as OpenCode would send it at its step 21).

**Spec:** [design 0012](../design/0012-the-monitor.md) §2 (keys, room, redraws), §4 (whatever model is loaded), §4.2,
§4.3, §4.4, §4.5, §4.6, §4.7 and §11 step 12; decisions
[0051](../decisions/0051-the-contexts-parts-are-estimated-in-the-gateway.md) (the estimate),
[0052](../decisions/0052-loop-text-is-a-part-of-its-own.md) (loop text),
[0067](../decisions/0067-the-monitor-reads-the-loaded-models-facts.md) (the loaded model's facts),
[0044](../decisions/0044-no-color-written-outside-a-style.md) (no color outside a style) and
[0045](../decisions/0045-text-never-spills-out-of-a-panel.md) (nothing spills).

## Global Constraints

- Nothing runs OpenCode, a container, Docker, the GPU or a model; never the owner's gateway or service. The census is
  tested on synthetic bodies, through a gateway served in the test with the fake engine; the console against a service
  served in the test, the gateway's answers given by the test.
- No new dependency. Tests first, each seen failing before its code, named as sentences; each test file's docstring
  names the design sections.
- Every field added to an answer is added, never renamed; a request goes to the engine exactly as before (the census
  reads the body, never changes it); a census that cannot be made leaves the request as it was, without one.
- Every color is a `$clank-` element of the style (the parts' are `$clank-part-<kind>`), every mark the style's
  (decision 0044); no line wider than its panel (decision 0045), what is shortened first said in each module.
- The owner is the sole author of every commit (no trailer); nothing is pushed from this lane. American English.

## Measurements of §10 for this step

- [ ] **The chat template inside the model file, and whether its markers are single tokens** (§4.2, §4.4): needs the
  model's file read on the owner's machine, and the engine to count; owed to the owner. Until then the catalog's
  `template` is the reference template's, as its `source` says, and the estimate's sources say so.
- [x] **The estimate's CPU cost on a 262,144-token request** (§4.2): measured on synthetic requests of that size
  (task 7, [the measurement](../measurements/2026-10-20-the-estimates-cost.md)): about 8 ms a census, about 40 ms at
  the worst seen (one `write` of 860,000 characters; corrected after the review, which also found a chat of answers
  without calls quadratic, now linear), in a worker thread once per request; the estimate 0.1 ms.
- [ ] **The estimate's error against the exact sizes** (§10, before step 13): needs an engine that counts each part
  (llama.cpp's `/tokenize`, or the KVMem patch); owed to the owner.

## Tasks

### Task 1: The census of a request

- [x] **Files:** create `clank/components/gateway/census.py`; create `tests/components/gateway/test_census.py`.
- [x] **Interfaces:** `PARTS` (`system`, `tools`, `yours`, `text`, `thinking`, `calls`, `results`, `loop`, the style's
  names); `census(body, ratio, shortest) -> dict`: `chars` (each part's characters; the thinking after the last real
  user message), `earlier` (the characters of thinking before it), `counts` (each part's items), `items` (the biggest:
  `part`, `chars`, `at`, `after`, `call`, `calls`, `tool`, `what`, `loop`, `again`, `earlier`), `tools` (the results'
  characters and count by tool, loop text apart), `again` (the earlier results of calls made again: characters and
  count), `from_last_user`, `images`, `messages`.
- [x] **Tests:** `test_a_requests_characters_are_counted_part_by_part`;
  `test_thinking_before_the_last_user_message_is_counted_apart`;
  `test_a_tool_result_carries_its_call_id_and_its_tool_and_a_message_the_ids_of_its_calls`;
  `test_loop_text_is_found_by_the_guards_measure_over_whole_items_and_taken_out_of_its_part`;
  `test_the_result_of_a_call_that_looped_echoes_it_and_is_loop_text_too`;
  `test_a_call_made_a_third_time_in_the_last_twelve_is_loop_text_with_its_result`;
  `test_the_earlier_results_of_a_call_made_again_could_be_freed`;
  `test_only_the_biggest_items_are_kept_and_each_parts_biggest`;
  `test_a_body_of_odd_shapes_is_counted_without_failing`. As built: the loop guard's measure is public
  (`loops.share_of`), which the census reads; a call made again is the same tool with the same arguments, whole.

### Task 2: The gateway keeps each request's census

- [x] **Files:** `clank/components/gateway/activity.py` (`census`, `_slimmed`), `server.py` (`counted`: the census
  made off the event loop once the body is read); `tests/components/gateway/test_activity.py`,
  `test_session_facts.py` (the gateway's facts for the Monitor, where the plan said `test_server.py`).
- [x] **Interfaces:** `Activity.census(record, found)`; a request among a session's `ended` carries `census`: whole for
  the newest that ended well and those after it, without its `items` for the older ones; never in `last`, the records
  or a request in flight.
- [x] **Tests:** `test_a_sessions_requests_that_ended_keep_their_census_whole_only_from_the_newest_that_ended_well`;
  `test_the_gateway_makes_a_census_of_each_request_and_keeps_it_out_of_its_records`.

### Task 3: The estimate in the service

- [x] **Files:** create `clank/components/agents/estimate.py`; `clank/components/agents/context.py` (`totals(...,
  view=None)` carries `parts` and `steps`), `service.py` (the flow given to the totals); create
  `tests/components/agents/test_monitor_estimate.py`; `tests/components/agents/test_monitor_context.py` (a request
  with a census).
- [x] **Interfaces:** `estimate(census, prompt, facts, view=None, keeps=None, cached=None) -> dict`: `tokens`,
  `calibrated`, `how`, `thinking` (the rule applied), `parts` (each: `part`, `label`, `tokens`, `share`, `items`,
  `biggest`), `items` (biggest first: `part`, `tokens`, `what`, `tool`, `call`, `step`, `loop`, `again`, `cleared`,
  `kept`), `groups` (where the room went), `freed` (could be freed), `suffix`, `images`; `steps(ended, facts_of)` (each
  ended request's parts, by its id). The totals: `parts` (None without a census), `steps`.
- [x] **Tests:** `test_for_a_synthetic_request_with_known_parts_the_shares_add_up_to_prompt_tokens`;
  `test_earlier_thinking_is_left_out_by_the_templates_rule_and_kept_by_another`;
  `test_a_model_whose_template_has_no_thinking_has_no_thinking_part`;
  `test_a_calibrated_model_weighs_each_part_by_its_tokens_per_character`;
  `test_tool_results_map_to_their_call_ids_and_their_steps_and_a_cleared_one_is_marked`;
  `test_items_in_the_tail_a_compaction_keeps_are_marked`;
  `test_where_the_room_went_and_what_could_be_freed`;
  `test_the_totals_carry_the_parts_of_the_last_finished_step_and_of_each_step_before`. As built: the census names the
  calls around an item without one of its own (`near`, `next`; `test_an_item_without_a_call_names_the_calls_around_it`),
  so the owner's message is said with the step that read it and a text with no call with the step after the call
  before it, when the flow says that step made none; `shares(census, prompt, facts)` gives one step's parts alone. The
  code map and the tests page are written again here for tasks 1 to 3 (tasks 1 and 2 left them out).

### Task 4: The Session view: the bar by part, and the biggest items

- [x] **Files:** create `clank/components/agents/console/parts.py`, `biggestpanel.py`; `contextpanel.py` (the bar by
  part, the legend line), `monitor.py` (the Biggest panel's list, Enter on it, its rows given up with Tool calls'),
  `tests/console/test_monitor_context.py`; create `tests/console/test_monitor_biggest.py`; the Session view's frames.
- [x] **Interfaces:** `parts.tokens(n)`, `parts.legend(found, width)`, `parts.bar(totals, width)`; `biggestpanel.rows`,
  `line(row, width)`, `whole(row)`, `BiggestList`.
- [x] **Tests:** `test_the_bar_is_drawn_by_part_and_the_legend_says_what_each_part_holds`;
  `test_the_legend_gives_up_its_smallest_parts_first_and_no_line_is_wider_than_the_panel`;
  `test_the_biggest_items_are_listed_with_their_tokens_their_step_and_what_they_are`;
  `test_a_biggest_line_cuts_what_it_is_first_then_its_marks_then_its_step_never_its_tokens`;
  `test_enter_on_an_item_shows_it_whole_with_why_it_is_marked`;
  `test_the_session_view_with_the_parts_at_128_88_and_60_columns` (snapshots);
  `test_enter_on_biggest_opens_the_item_highlighted`. As built: board A's request is `tests/support/requests.py`
  (the request of its last finished step, with a loop kept in a thinking and a file read twice); the legend gives up
  loop text last; what an item is keeps 20 characters before its marks go; a call with arguments that hold no text
  is said by its name alone (the census's `_first`); the Session view's frames say "the parts come with the session's
  next finished step" in Biggest while the gateway has made no census of the session's last finished step.

### Task 5: The Context view: the totals, what is in it, where the room went, where the figures come from

- [x] **Files:** create `clank/components/agents/console/contextview.py`; `monitor.py` (the view's widgets, ↑↓ and
  Enter on What is in it); create `tests/console/test_monitor_context_view.py`; the Context view's frames.
- [x] **Interfaces:** `contextpanel.summary(totals, width, zone)` (the Context view's Context window), `contextview`'s
  `contents(totals, width)` (header and a row per part), `room(totals, width)`, `sources(totals)`, `items_of(totals,
  part)`, `waiting(totals)`, `Drawn` (a panel drawn by one of `DRAWINGS`), `PartsList`.
- [x] **Tests:** `test_what_is_in_it_lists_each_part_with_its_tokens_share_items_biggest_and_last_ten_steps`;
  `test_what_is_in_it_gives_up_the_biggests_words_first_then_its_trend_then_its_items`;
  `test_enter_on_a_part_lists_its_items_biggest_first`;
  `test_where_the_room_went_names_the_biggest_groups`;
  `test_where_these_figures_come_from_names_the_engines_facts_the_template_and_the_calibration`;
  `test_the_context_view_at_128_88_and_60_columns` (snapshots); `test_enter_on_a_part_of_what_is_in_it_opens_its_items`.
  As built: What is in it names the parts by the legend's short names (system, tools, you, text, thinking, calls,
  results, loop), which leaves the biggest room at 128 columns; a part's items list says how many more the part holds
  than the census kept (it keeps the 40 biggest and each part's 8); the Monitor page's test of empty panels reads the
  drawn ones too, and its Context frame gains the panel's note "estimate" and the keys bar's `enter open`.

### Task 6: The Context view: on the GPU exactly, over this session, could be freed

- [x] **Files:** create `contextgpu.py` (`gpu`, `gpu_drawn`), `contextchart.py` (`over_session`, `CHART_ROWS`, `AXIS`),
  `contextfreed.py` (`freed`, `freed_whole`, `FreedList`): one subject a file, where the plan said `contextview.py`;
  `contextpanel.py` (`gpu_line` and `mark_words` made public; a growth point names its step's request), `estimate.py`
  (`since`: the newest from the cache's end or the last user message), `monitor.py` (Enter on Could be freed; `k` on
  the Context view); `tests/console/test_monitor_context_view.py`; the frames.
- [x] **Tests:** `test_on_the_gpu_exactly_says_the_first_block_the_newest_the_picked_and_the_rest_under_kvmem`;
  `test_on_the_gpu_under_an_engine_without_an_exact_window_says_it_attends_its_whole_window`;
  `test_the_chart_draws_each_steps_size_split_by_part_and_marks_compactions_and_loop_stops`;
  `test_no_chart_line_is_wider_than_its_panel`;
  `test_could_be_freed_says_what_each_frees`;
  `test_enter_on_compact_now_in_could_be_freed_asks_first_as_k_does`. Found on the way: the Enter that opened Compact
  now's window was taken by it as "do it" (the window's binding is read after the page's key), so a single Enter would
  have compacted; the window now opens once that Enter is done, and the test holds it open.

### Task 7: The census's CPU cost on a 262,144-token request

- [x] **Files:** create `docs/measurements/2026-10-20-the-estimates-cost.md`; `docs/measurements/README.md`.
- [x] A synthetic request of about 262,144 tokens (OpenCode's shape: a system prompt, tool definitions, a long
  session of calls and results, code and prose), its census timed on this machine, the share of it zlib takes, and
  what it means for the gateway (a thread, not the event loop; once per request). As measured: 8.1 ms a census on a request of mixed text (5.0 ms of it zlib's),
  2.3 ms with short thinking, 19.1 ms at worst (every item the model's own); the estimate 0.1 ms.

### Task 8: Documents

- [x] Design 0012 §11 step 12 marked built with this plan, §4.2's "As built" item, the sections' table and the revision
  log (§4.2 revised with step 12); the design index; the roadmap's M5 row; the plans' index; `docs/console.md`; the
  walkthrough's Monitor (its paragraph and its keys); the glossary (context parts, loop text); the Monitor's help
  (`explain`: the Context window's bar by part, Biggest, the Context view) and its docstring; the generated files
  (the code map, the tests page, the API and events pages); this plan's boxes, its Built note and Claude's calls.

## Built

- Built 2026-10-20, in eight commits after this plan's (one per task). Each task's tests were seen failing before its
  code: the new modules' at their import, the others on their first assertion. Some expectations changed while the
  code was written, each for a reason said in its task: the bar's cells (the largest remainders were counted wrong by
  hand), the Biggest line's room for what an item is, What is in it by short names, the GPU's words kept short for
  its panel, "frees about N" for "−N".
- Found on the way: the Enter that opened Compact now's window from Could be freed was taken by that window as "do
  it" (Textual reads the window's binding after the page has taken the key), so one Enter would have compacted the
  session; the window now opens once that Enter is done, and the test holds it open. A call with arguments that hold
  no text was said as `name {}`; it is said by its name. The code map and tests page were left out of tasks 1 and 2's
  commits and written again in task 3's.
- The Session view's frames gain "the parts come with the session's next finished step" in Biggest, where a session is
  followed but the gateway made no census of its last finished step; the Context view's empty frame gains its panel's
  note "estimate" and the keys bar's `enter open` and `k compact`. Each difference was read.
- Measured here: the census's CPU cost on a 262,144-token request ([the
  measurement](../measurements/2026-10-20-the-estimates-cost.md)). Owed to the owner: the chat template inside the model
  file and whether its markers are single tokens, and the estimate's error against an engine's exact counts.
- The full check (`uv run python -m tools.check`) before the rebase: every check passed (1,833 tests passed and 10
  skipped). After the rebase and the three commits: one failure, step 10's
  `test_u_asks_first_then_undoes_and_the_turns_text_opens_in_the_note_window`, which failed once of three alone too;
  the windows' arming caused it, and is fixed in its own commit. The full check after it: every check passed but one
  test, `tests/test_repository.py::test_the_tests_page_is_up_to_date` (the arming fix added two tests without writing
  the tests page again), which fails alone too; the page is written again in the commit that says so, and the
  repository's tests pass.
- Rebased on main (d5ecdbf), which step 10 (plan s20, the Guide's Undo and Drop) reached while this was built: the
  Monitor's help keeps both steps' "Built so far"; the roadmap's M5 row, design 0012's index row and its revision log,
  and the walkthrough's Monitor keep both steps' words; the tests page and the code map were written again; the three
  Session view frames that met (Biggest's label beside step 10's Guide lines) and Biggest's own three were written
  again, their differences step 10's (the Guide's `u` and `x` lines, so Tool calls and Biggest give up a row; the keys
  bar's `u undo` and `x drop`) and this step's label.
- After the rebase, three commits, each test first:
  1. **`x` through step 10's Drop.** On the Context view, Enter or `x` on a part of What is in it, and Enter on a row of
     Could be freed that drops, open the window of their items (`itemsscreen.py`), where `x` drops the one
     highlighted; on the Session view, `x` with Biggest in the context focused drops its item. Each goes through the
     Session view's own path (`_drop`, now given the call: the Guide asked about that call, then its window, Enter
     there alone clearing it); an item that is not a call's result says why. Each item names its call's part in the
     flow (`node`). The Context view's frames gain `x drop` in the keys bar.
  2. **Cleared items.** An item whose result step 10's Drop cleared says "cleared by you, freed about 18.6K" (one
     OpenCode cleared itself, "cleared by OpenCode"), in Biggest and the items' windows, and Could be freed leaves it
     out: its totals and its items less the results already cleared.
  3. **The key that opens a window never acts in it.** A bare app showed it: Textual reads a new window's bindings for
     the key that pushed it, so an Enter that opens a window that asks first was taken as "do it". The window that asks
     first (`clank/console/confirm.py`, every page's) and the window of items are armed once the console has done with
     the message they were made in, so the key that opened one never acts in it; Enter does nothing in the window of
     items; the Monitor still opens its windows once the key is done. Armed once drawn, as first written, step 10's
     test of `u` then Enter failed in the full check (and once of three alone): a key pressed before the window was
     drawn was lost. Armed after the message, it passed four times of four, and the full check passed (below).
- The independent review (5d22f63) found nothing that had to be fixed and nine things to fix, each fixed test first
  in a commit of its own (the eighth, a document's wrap, has no test):
  1. Esc in the window of items said "Drop cannot run now: no item is highlighted": it closes quietly.
  2. Keys in that window reached the page too (`k` opened a second window over it, `x` set the page's message while
     Drop asked): the Monitor's new keys act only with no window over the page.
  3. Two answers without calls in a row both showed the step of the first: the census says how many answers on from
     the last call an answer is (`hops`), and the service takes that many steps on when none made a call, else none.
  4. Could be freed offered Drop loop text it cannot clear: Drop is offered only results (the loop text in tool
     results, the earlier results of calls made again); the loop text the model wrote is a row on `k`, which only
     compacting clears.
  5. The census was quadratic in answers without calls (3,000 took about 250 ms): one pass and a binary search now
     (15 ms), a test holds 10,000 under a second, and the measurement says the worst seen is about 40 ms (one huge
     `write`), not under 20.
  6. **Privacy**: the census's `what` held up to 80 characters of the owner's message, the model's words or a call's
     arguments, and `/activity` served it whatever the records said. With `records` off, it now says only kinds, tool
     names, sizes and places; with them on, as the records allow
     ([decision 0096](../decisions/0096-the-census-keeps-no-prompt-text-when-records-are-off.md)).
  7. A census error could fail a request: every error is caught, the request goes on without one, and the log counts
     the failures without the request's text.
  8. A line of design 0012's step 12 note ran to 207 columns: wrapped at 120.
  9. Every snapshot line naming KVMem's version had its right border a cell left (the lines also held curly quotes,
     which looked the cause): the frames' version stand-in shortened `v0.16.0` to `v0.0.0`; stand-ins now keep each
     line's width, and the nine frames were written again.
- Rebased on main (fa85fec, the flow template's default model) with no conflict before shipping. The full check then:
  1,880 tests passed and 10 skipped; the types failed on one test's list the privacy test left unannotated, annotated
  in its own commit, after which both type checks, the lint and the census's tests pass (the code under test is
  unchanged).

## Claude's calls (2026-10-20)

1. **The census in the gateway, the sharing out in the service.** The gateway has the body and counts its characters
   by part, one pass, no model facts; the service shares them out to the engine's own count where each engine's
   figures are read by its facts and the model's template and calibration are known (decision 0067). Decision 0051's
   "estimated in the gateway" is kept for the work that needs the body; no decision record, since nothing it decides
   changed (design 0012 §4.2's "As built" says how).
2. **Made once the body is read, in a worker thread, and awaited** before the request goes on: about 8 ms on a
   262,144-token request, nothing against the engine's reading of it, and the event loop never held. Never in the
   records: a census holds words of the request, which `records: false` must keep out.
3. **Whole only from the newest request that ended well on**: older ones keep their parts' numbers alone (the last ten
   steps, the chart), so the activity's answer, read every second by the service, stays near 15 KB.
4. **The 40 biggest items and each part's 8** are kept; Enter on a part says how many more it holds and their tokens.
5. **A model without a calibration counts every part alike by its characters**, and says so: Clank's plain 0.3 tokens a
   character is a scale, which the sharing out cancels.
6. **A model whose template is not in the catalog keeps its earlier thinking**, counted whole, and says so.
7. **Loop text is measured over what the model wrote** (its text, its thinking after the last user message, a call's
   arguments): a tool's result is never measured by itself, since a log or a table compresses that far with no loop;
   it is loop text when it echoes a call that looped, or a call made a third time in the last twelve.
8. **"The earlier reads of a file read again"** (§4.6) are the earlier results of any call made again with the same name
   and arguments, whole: a file read again among them, a command run again too, loop text apart.
9. **An item's step is the flow's**: by its call id; the owner's message, the step that read it (the first call of the
   answer after it); a text whose answer made no call, the step after the call before it, only when the flow says that
   step made none. Else no step, never a guess.
10. **The tail a compaction keeps**: an item whose characters after it and its own, at the prompt's tokens a character,
    fit within the agent program's `keeps` (15,000 for daily 262K).
11. **The bar by part** shares the room used by the largest remainder over the parts and the last answer, the answer's
    cells in the color nearing the line takes; a part too small for a cell has none, and the legend says it.
12. **The legend gives up its smallest parts first, loop text last** (what the owner looks for after a session went
    wrong), and says how many it left out.
13. **Biggest**: what an item is is cut first, down to 20 characters (a file's name), then its marks go, then its step;
    its tokens and color never. A result is said as its call (`read src/grid.py`), the container's `/workspace/` left
    out; a call as `call: ...`.
14. **What is in it names the parts by the legend's short names**, so the biggest has room at 128 columns; narrower, the
    biggest's words are cut first (down to 16), then the last ten steps go, then the items, then the biggest.
15. **On the GPU exactly**: the newest is the later of where the cache stopped matching and the last user message (what
    KVMem keeps on the GPU at every step), about; picked is the exact window less the first block and the newest; the
    picks are worded by the engine's facts; the owner's message the steps pick by is the flow's newest of the owner's.
16. **Over this session**: eight rows against the window (how close to it the session came), each cell in the color of
    the part covering most of it, the step's parts scaled to OpenCode's count of it; the loop guard's stops and the
    compactions in the Session spark's colors, marked under their columns and said.
17. **Could be freed** says "frees about N" (an ambiguous minus sign is refused by the lint, and words read better);
    Enter on a drop lists its items and says how the Guide's Drop drops them; Enter on Compact now opens the Guide's
    window once the Enter is done.
18. **Frames**: the Context view at 160 by 60 (128 columns, all of it on screen), 160 by 50 with F5 (88; the page
    scrolls) and 82 by 80 (60, stacked); the Session view with the parts at 160 by 50, 160 by 50 with F5 and 82 by 70.
19. **`x` on the Context view opens a window of items** rather than dropping a part's biggest at once: What is in it
    highlights parts, not items, and a drop is final, so the item is picked where it is seen whole, then step 10's
    window asks. Enter on a part opens the same window, so its items can be dropped from where they are read.
20. **Biggest takes `x` on the Session view** when it has the focus, as Tool calls does: the same item, the same path.
21. **The guard is in the windows themselves** (armed once drawn), not only in the Monitor's way of opening them, so no
    page that opens a window that asks first on Enter can have that Enter taken as "do it".

## Left for later

- **Where another session took the engine** on the chart, as on the Session view's spark (plan s17): the gateway keeps
  whose request each slot read only for now.
- **Board C's pace line** ("after the next step, about 147,000 at this pace") is not among §4.7's panels; not built.
- **Images** in a prompt are counted, not by part: their tokens are shared among the parts, and the sources panel
  says so.
- **The KVMem patch** (§4.4, step 13): the exact parts and the picks. Until then the GPU's picks say "not reported by
  this engine".
- **A calibration for the Qwen3.8 models** (§4.2: synthetic requests that differ by one part, counted by the engine):
  it needs the engine; owed to the owner with the template's measurement.
