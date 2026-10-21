# The Monitor, step 8: Watch for: implementation plan

> At the owner's request (2026-10-18, design 0012 approved: "Approve all three"; 2026-10-19: the new menu, the Monitor
> and flows built "as quickly as possible"). As for the earlier plans, the files, interfaces and tests by name and
> intent; the code is in the commits.

**Goal:** design 0012 §11 step 8: the Watch for rules of §8, each a pure function over a session's flow (decision
0053), run in the service whenever a flow changes, so they act while no console is open; their marks, each saying what
it rests on; the settings file `config/monitor.json` that says what each rule does (mark it, pause, tell the phone,
tell the model and go on), with "tell the model" capped; and "tell the phone": the phone page lists a mark with what
waits.

**Architecture:** A small package beside the session's flow, `clank/components/agents/watchfor/`:

- `rules.py`: the fourteen rules of §8's table, in its order, each a pure function of a flow's view (`Flow.view()`)
  and the slot's facts (`Facts`: the window, the output limit, the thinking budget, whose conversation the engine
  holds; each `None` when not known), returning what it found (`Found`: the rule, a key stable across evaluations, the
  node it shows on, why). A rule over a stretch of calls (the same call three times in the last 12, four failures in
  the last 8, one file edited six times in the last 30) finds the call where a streak reached its count, and again
  only after the streak ended, so a flow read again finds the same marks.
- `marks.py`: `Marks`, the marks kept in the service (in memory, as the flows are: decision 0049): it takes what the
  rules found, keeps each new mark once, and does what `config/monitor.json` says: the mark (an `agents.marked`
  event), "tell the phone" (the mark is listed for the phone until it is seen), "tell the model" (a note in the rule's
  words, through `Acting.note`, at most `notes_in_a_row` times in a row for one rule in a session, after which the
  rule marks, pauses and tells the phone), "pause" (through `Acting.pause`). The note is step 9's and the pause step
  11's: until they are built, `NotYet` says so and the mark tells the phone instead, saying why (decision 0082).
- The kind `monitor` (`MonitorSettings`, `config/monitor.json`) in `clank/components/agents/kinds.py`: one field per
  rule (`RuleSettings`: `do`, the actions; `note`, its words), and `notes_in_a_row` (2).

The agents service runs the rules once a second over the flows that changed (`SessionFlows.changed`), with the facts of
the agent role's slot. The service answers `GET /agents/marks` (the newest marks and how many are not seen),
`POST /agents/marks/seen`, and each flow's answer carries its marks; the phone's overview lists the marks told to it,
and `POST /api/marks/seen` marks one seen from the phone. The console reads the marks as a topic of its own: the
Watch for panel lists the newest, and the menu shows how many are not seen beside "Monitor".

**Tech stack:** Python 3.12 standard library; Pydantic 2 (the kind); FastAPI; pytest with the session-flow lines of
plan s15 (`tests/support/flowlines.py`), the fake clock, and the console driven headless.

**Spec:** [design 0012](../design/0012-the-monitor.md) §8, §2 (the marks beside "Monitor", the Watch for panel), §9.1
(an action a rule takes) and §11 step 8; [decision 0053](../decisions/0053-watch-for-rules-run-in-the-service.md);
[decision 0040](../decisions/0040-the-gateway-stops-an-answer-that-repeats-itself.md) (the loop guard leaves telling
the model to the Monitor); [design 0005](../design/0005-the-phone.md) §6 (what waits).

## Global Constraints

- Nothing here runs OpenCode, a container, Docker or a model: the rules are tested on flows built from lines in the
  bridge's shapes, the marks with a fake `Acting` and the fake clock, the routes against a service served in the test.
- No new dependency; no database table (decision 0049): the marks are kept in memory, bounded (`KEPT` per session,
  the newest `SESSIONS` sessions).
- A rule reads only the flow's view and the facts it is given; it never reads Docker, the gateway or a file.
- A mark on a step from before Clank watched (decision 0049's `before`) is kept and shown, and does nothing more: the
  rules never act on what happened before the service saw it (after a restart, every finished step is `before`).
- Every field added to an answer is added, never renamed. Tests first, named as sentences; each test file's docstring
  names the design sections. The owner is the sole author of every commit (no trailer); nothing is pushed from this
  lane.

## Measurements before this step (pending)

- [ ] **That `model_looped` and an engine breaking off lead to no retry and a dropped step** (design 0012 §10, before
  step 8): one answer stopped by the loop guard and one broken off by a fake engine, under OpenCode 1.19.0, its steps
  read through the bridge. Until then the rule "The loop guard stopped an answer" marks the step whose request the
  gateway marked `looped` (or whose error is the guard's words), whatever OpenCode then did; its note (step 9) waits
  for this measurement too.

## Review Focus

1. **Streaks**: a rule over the last N calls marks the call where the count was reached, once, and again only after
   the count fell below it; the same flow read again (after a restart) finds the same keys, so nothing is marked or
   told twice.
2. **The cap**: "in a row" is counted per rule and session, and starts again when the owner writes a message of their
   own (one that is not a note Clank sent); a note that could not be sent does not count.
3. **What acts**: only a new mark acts, never one on a step from before Clank watched; an action not built yet (the
   note, the pause) tells the phone instead, and the mark says which action waits for which step.
4. **The facts a rule needs**: a rule whose fact is not known (the compaction line without the slot's window, the
   budgets, whose conversation the engine holds before step 3) stays quiet; it never guesses a number.

## Tasks

### Task 1: The settings file, `config/monitor.json`

- [x] **Files:** `clank/components/agents/kinds.py` (`RuleSettings`, `MonitorSettings`); `clank/components/agents/
  component.py` (its kinds); the generated `clank/schemas/monitor.schema.json` and `vscode/src/core/kinds.ts`;
  `tests/components/agents/test_watch_for_settings.py`.
- [x] **Interfaces:** `MonitorSettings` (KIND `monitor`, SINGLE, ON_CHANGE now): one `RuleSettings` per rule, named as
  §8's table (`waiting_for_you`, `engine_broke_off`, `loop_guard_stopped`, `asks_about_a_repeat`, `same_call_again`,
  `failing_again`, `one_file_again`, `call_then_step_failed`, `stopped_with_an_ask_waiting`, `note_not_read`,
  `retrying`, `compaction_near`, `budget_near`, `engine_taken`); `RuleSettings.do: list["mark" | "pause" | "tell the
  phone" | "tell the model"]` (empty: the rule is off; any action marks too), `RuleSettings.note: str` (the words of
  its note, `{why}` replaced by what the mark rests on); `notes_in_a_row: int = 2`; `rule(name) -> RuleSettings`.
- [x] **Tests:** `test_the_rules_defaults_are_the_designs_table`;
  `test_a_rule_changed_in_its_file_is_read_and_an_unknown_action_is_refused`.

### Task 2: What the rules read: the engine broke off, and the counts by kind on a step

- [x] **Files:** `clank/components/gateway/activity.py` (`_ended`: `broken`, the engine's words when it broke off a
  streamed answer); `clank/components/agents/sessionflow/flow.py` (a step's `request` carries `counts` and `broken`);
  `tests/components/gateway/test_activity.py`; `tests/components/agents/test_session_flow_pairing.py`.
- [x] **Tests:** `test_a_request_whose_engine_broke_off_says_so_once_it_ended`;
  `test_a_steps_request_carries_its_counts_by_kind_and_whether_its_engine_broke_off`.

### Task 3: The rules

- [x] **Files:** create `clank/components/agents/watchfor/__init__.py`, `rules.py`;
  `tests/components/agents/test_watch_for_rules.py`.
- [x] **Interfaces:** `RULES: dict[str, Rule]` (`title`, `fires`: when, in words, `source`: whose facts);
  `Facts(context, output, thinking, holds)`; `Found(rule, key, node, why, offer="")`; `find(view, facts) ->
  list[Found]`; the thresholds as constants (`SAME_CALL = (3, 12)`, `FAILING = (4, 8)`, `ONE_FILE = (6, 30)`,
  `NEAR = 0.9`, `OUTPUT_MOST = 32_000`); the compaction line, the window less the output limit counted up to 32,000
  (§4.1); a step's total, OpenCode's `total`, else its prompt and answer added.
- [x] **Tests:** `test_each_rule_fires_on_its_synthetic_flow_and_says_why` (one flow per rule, through `Flow` and the
  bridge's shapes); `test_every_rule_stays_quiet_on_a_clean_flow`;
  `test_a_streak_is_marked_where_it_reached_its_count_and_again_only_after_it_ended`;
  `test_a_rule_whose_fact_is_not_known_stays_quiet`.

- Built 2026-10-19: the rules' titles and when each fires are `rules.py`'s `RULES`, which the kind's fields read, so
  the settings' help and the marks say the same words. Found on the way: OpenCode's `question` tool waits with no
  permission ask, so "Waiting for you" also marks a `question` call still running; the doom_loop ask is left to its
  own rule, so the phone is not told it twice.

### Task 4: The marks, kept and acted on

- [x] **Files:** create `clank/components/agents/watchfor/marks.py`; `clank/components/agents/service.py` (the event
  types); `tests/components/agents/test_watch_for_marks.py`.
- [x] **Interfaces:** `Marks(settings, clock, events, acting=NotYet())`; `check(workspace, session, view, facts) ->
  list[dict]` (the new marks); `marks(workspace="", session="", limit) -> list[dict]` (newest first); `unseen() ->
  int`; `phone() -> list[dict]` (told to the phone, not seen); `seen(ids, *, actor)`; a mark: `id`, `workspace`,
  `session`, `title` (the session's), `rule`, `name` (the rule's title), `fires`, `node`, `why`, `time`, `before`,
  `phone`, `seen`, `did` (each action with `done` and its reason when not), `offer`. `Acting.note(workspace, port,
  session, text)`, `Acting.pause(workspace, session)`; `NotYet` raises `Unavailable` naming the step that builds it.
  Events: `agents.marked` (a new mark that acts: the rule, the session, why, what it did), `agents.marks_seen`.
- [x] **Tests:** `test_a_rule_marks_once_and_each_action_follows_its_setting`;
  `test_a_rule_turned_off_marks_nothing`; `test_tell_the_model_stops_at_its_cap_then_marks_pauses_and_tells_the_phone`;
  `test_the_cap_starts_again_after_the_owners_own_message`;
  `test_an_action_not_built_yet_tells_the_phone_instead_and_says_why`;
  `test_a_mark_on_a_step_from_before_clank_watched_does_nothing_more`;
  `test_marks_seen_leave_the_count_of_those_not_seen`.

- Built 2026-10-19: the count of notes in a row is taken when a mark is made, under the lock, and given back when the
  note could not be sent, so two checks of one session never both send the last note allowed; a note Clank sent is
  told from the owner's own message by its text, as the session's flow keeps it.

### Task 5: In the service, and its routes

- [x] **Files:** `clank/components/agents/sessionflow/kept.py` (`changed(versions)`: the views of the flows whose
  version moved); `clank/components/agents/watchfor/marks.py` (`round`, `run`, `slot_facts(kernel)`);
  `clank/components/agents/service.py` (`Agents.marks`, run beside the flows); `clank/components/agents/api.py`
  (`GET /agents/marks`, `POST /agents/marks/seen`, `marks` in a flow's answer);
  `tests/components/agents/test_watch_for_service.py`.
- [x] **Tests:** `test_the_rules_run_when_a_flow_changes_while_no_console_is_open`;
  `test_the_routes_list_the_marks_mark_them_seen_and_a_flow_carries_its_own`;
  `test_the_facts_come_from_the_agent_roles_slot`.

- Built 2026-10-19: the agents component does not use the runtime (decision 0019), so the thinking budget the rules
  read comes with the slot's route, beside its window and output limit (`thinking`: the preset's `thinking.budget`
  while thinking is on), through the gateway's routes. Design 0012's step 3 (each engine's `context_facts`) may move
  it there; the rules read only `Facts`.

### Task 6: Tell the phone

- [x] **Files:** `clank/components/remote/app.py` (`_overview`'s `marks`; `POST /api/marks/seen`);
  `clank/components/remote/page/app.js` (what waits: a mark with its rule, its session, why, and "seen");
  `tests/components/remote/test_phone_marks.py`.
- [x] **Tests:** `test_a_mark_told_to_the_phone_is_listed_with_what_waits_until_it_is_seen`;
  `test_the_phone_page_draws_a_mark_with_what_waits` (the page's script reads the overview's `marks`).

- Built 2026-10-19: a mark on the phone says what its rule could not do and why (a note not built yet, a pause), and
  "seen" takes it off the list; a mark seen on the computer leaves it too. The page's drawing of a mark was also run
  under Node against a small stand-in for the page (not kept: the test checks the script reads the marks and its
  syntax).

### Task 7: The console: the Watch for panel and the count beside "Monitor"

- [x] **Files:** `clank/console/data.py` (the topic `marks`, read from `agents/marks`, touched by `agents.marked` and
  `agents.marks_seen`); `clank/components/agents/console/watchfor.py` (the panel's lines); `clank/components/agents/
  console/monitor.py` (the Watch for panel draws them); the menu entry's count is the page's own badge (`MonitorPage.badge`), which the shell already draws;
  `tests/console/test_monitor_watch_for.py`.
- [x] **Tests:** `test_the_watch_for_panel_lists_the_newest_marks_each_with_why`;
  `test_the_menu_shows_how_many_marks_are_not_seen_beside_monitor`.

- Built 2026-10-19: the page does not follow a session yet (design 0012 §3 comes with the renderer, step 6, built
  apart the same day), so the panel lists the newest marks of every session, each naming its session; once the page
  follows one, `_draw_marks` takes that session's (`GET /agents/marks?session=`, or the flow's own `marks`). With no
  mark the panel says what it said before, so no snapshot changed. Enter on the panel marks the marks it lists seen;
  `?` there says each whole, with when its rule fires and what it did. Marks on their nodes in the flow are the
  renderer's to draw: each flow's answer carries its marks, by node.

### Task 8: After the self-review

- [x] **A subagent's mark never notes the subagent.** The rules run over every flow, subagents' included, and the note
  went to the session marked; design 0012 §3 says the Guide acts on the root session and a note to a subagent comes
  later. A subagent's note now tells the phone instead, saying so. Test:
  `test_a_subagents_mark_tells_the_phone_and_never_the_subagent`.
- [x] **A mark dropped to keep the newest is never made again.** A session with more than `KEPT` marks dropped its
  oldest, which the rules found again at the next change, made again and acted on again. The ids of every mark made
  in a session are kept apart from the marks. Test: `test_a_mark_dropped_to_keep_the_newest_is_never_made_again`.

### Task 9: Documents and generated files

- [x] **Files:** design 0012 §11 step 8 (*built*) and its index row; decision 0082 and its index line; the roadmap's
  M5 row; the glossary (**Watch for**, **Mark**); the plans' index; `docs/API.md`, `docs/EVENTS.md`, the code map, the
  tests page, the schemas regenerated (`uv run python -m tools.check --fix`); this plan's boxes.
- [x] **Tests:** `uv run python -m tools.check --fix` passes.

- Done 2026-10-19: `uv run python -m tools.check --fix` ran once (1,210 passed); its one failure was the Records page's
  snapshot, whose list of kinds holds one more (`monitor`), so its scroll bar's thumb is a little shorter: rewritten
  with `CLANK_UPDATE_SNAPSHOTS=1`, the difference read (that one cell row only). The Monitor page's own snapshots did
  not change: with no mark, the Watch for panel is as it was.

### Task 10: After the review

- [x] **A note not read from before Clank watched acted after a restart** (major). The flow marked only steps `before`;
  a note's node has no step, so a note left unread in the history was made again as a new mark after every restart,
  acted on (an `agents.marked` event, the phone told) and counted as unseen. The flow now marks the owner's messages
  read in its first reading `before` while the step that decides their state (the one that read it, else for a note
  the one under way when it was sent) was done before Clank watched, or there is none; a note left waiting when Clank
  joined, whose run ended after, still acts. Tests: `test_a_note_not_read_from_before_clank_watched_does_nothing_more`,
  `test_a_note_waiting_when_clank_joined_whose_run_ended_after_acts`.
- [x] **A rule given in part lost its own defaults.** Only `do` given left the note empty; only `note` given made the
  rule mark alone. A rule's keys now fill in over its own defaults, and the schema shows each rule's defaults (no empty
  note offered). Tests: `test_a_rule_given_in_part_keeps_its_own_defaults_for_the_rest`,
  `test_the_schema_shows_each_rules_own_defaults`; the marks tests' settings no longer copy the note in by hand.
- [x] **"In a row" also counts again after a step that finished cleanly** (decision 0083): three loop guard stops hours
  apart are not in a row, so a run left alone goes on. Test:
  `test_a_step_finished_cleanly_after_a_note_starts_the_count_again`.
- [x] **The phone listed an ask twice, and after it was answered.** A mark of an ask (`WAITS`) is over once its rule no
  longer finds the ask waiting, and leaves the phone's list (it stays in the Watch for panel until seen); while the ask
  waits, the overview leaves out its mark, since OpenCode's own box shows it. Tests:
  `test_a_mark_of_an_ask_no_longer_waiting_leaves_the_phones_list`,
  `test_an_ask_shown_in_opencodes_own_box_is_not_listed_again_as_a_mark`.
- [x] **The answer half of "Thinking or answer near its budget" had no test.** Test:
  `test_an_answer_within_a_tenth_of_the_output_limit_is_marked_naming_the_limit`.
- [x] **Enter on Watch for opens the marks**, each whole, in a window over the page, and so sees them (design 0012 §2's
  keys: Enter opens a mark); it no longer marks them seen unread. Test:
  `test_the_watch_for_panel_lists_the_newest_marks_each_with_why`.
- [x] **Decision 0053's status names 0082 and 0083**, which make it exact.
- [x] **A session whose flow the service no longer keeps is forgotten** (`SessionFlows.keys`, `Marks._forget_gone`), so
  the records of each session no longer grow while the service runs. Test:
  `test_a_session_whose_flow_is_no_longer_kept_is_forgotten`.

## Left for later

- The measurement above (the loop guard's stop and an engine breaking off under OpenCode 1.19.0).
- **The service started again from this code** (the owner's release, then its update): the rules run in the service,
  and the slot's route gives the thinking budget only from this code on. The gateway, started again too, gives
  `broken` for an answer its engine broke off; until then "The engine broke off" reads the step's own error words.
- **Telling the model and pausing**: the Guide's steps 9 and 11 give `Marks.acting` its `note` and its `pause`; until
  then the loop guard's rule tells the phone instead (decision 0082), so a run the guard stopped waits for the owner.
- **The page following a session** (design 0012 §3, built with the renderer, plan s16, and on main now): the Watch for
  panel still lists every session's marks, each naming its own; listing only the followed session's (`_draw_marks`),
  and drawing each mark on its node in the flow (each flow's answer carries `marks`, by node), is the next step's, with
  the owner's word on whether a subagent's marks show under its root.
- **Whose conversation the engine holds** (design 0012 step 3): until it is known, "The engine taken by another
  session" stays quiet.

## Claude's calls (2026-10-19)

1. **A package of its own**, `watchfor/`, beside `sessionflow/`: the rules read a flow's view and nothing else, so
   they are tested on views alone, and the flow's code does not change for them (but for two fields a step's request
   carries).
2. **The settings file names each rule** (one field per rule, in §8's order, each with its label and help), so every
   rule and what it does is listed in the schema and in the file's help; `do` lists the actions, the empty list turns
   the rule off, and any action marks too, since a rule that acts unseen breaks the transparency rule.
3. **The thresholds are the design's** (3 in 12, 4 in 8, 6 in 30, a tenth of a budget), constants each mark's `why`
   and the settings' help state; they become settings if the owner asks.
4. **A rule's note is a setting**, its words in the file, `{why}` replaced by what the mark rests on; the loop guard's
   is decision 0053's sentence.
5. **"In a row"** counts the notes one rule sent in a session since the owner's own last message, and since a step
   that finished cleanly after the rule's last note (decision 0083, after the review): a model the notes do not help
   gets at most two in a row, and a run left alone goes on past loops far apart.
6. **An action not built yet tells the phone instead** (decision 0082): until step 9 the note, and until step 11 the
   pause, cannot run; the mark says which waits for which step, and the owner hears of it, so a run left alone is not
   left unseen.
7. **A mark told to the phone is listed with what waits, not asked as a question** (decision 0082): a mark waits for
   no answer, and the questions page, VS Code and the phone would each have asked it again.
8. **Marks are kept in memory** and made again from the flows after a restart, those of steps before Clank watched
   acting nothing and counted as seen.
9. **A subagent's mark never notes the subagent**: the Guide acts on the root session (design 0012 §3) and a note to a
   subagent comes later, so it tells the phone instead; noting its root in its place would tell the root of something
   it did not do.
10. **The thinking budget comes with the slot's route** (`thinking`, beside the window and the output limit), since the
    agents component may not use the runtime itself (decision 0019); design 0012's step 3 (`context_facts`) may take
    it over.
11. **Until the page follows a session, the Watch for panel lists every session's marks**, each naming its session,
    and keeps its empty words while there is none, so the renderer's step, built apart, follows the session without
    a snapshot of this step's in its way.
12. **Enter on Watch for opens the marks it lists, each whole**, and opening them sees them (after the review): §2's
    keys give Enter "open what is highlighted: ... a mark", and the panel highlights none yet; a mark highlighted alone
    comes with the renderer's list.
13. **A mark of an ask is listed on the phone only while OpenCode's own box does not show the ask** (after the review):
    the page lists each ask once, and a mark whose ask was answered leaves the list without being seen.
