# The Monitor, step 7: now, tool calls, the live text, growth: implementation plan

> At the owner's request (2026-10-18, design 0012 approved: "Approve all three"; 2026-10-19: the new menu, the Monitor
> and flows built "as quickly as possible"). As for the earlier plans, the files, interfaces and tests by name and
> intent; the code is in the commits.

**Goal:** design 0012 §11 step 7: the Session view's **Now** panel (§5: what the session does this second, by the
phase table of §5.1; its thinking and its answer against their budgets, live counts said "about" and corrected at the
answer's end, §5.2; the prompt, the call being written and the speed, §5.3; the loop guard, §5.4), its **Tool calls**
panel (§7: newest first, Enter reading a call whole through the bridge, which is a `docker exec`, so only while the
page is on screen), **the live text** (`l`, §7: the followed session's request as it is written, from the gateway's
live view), and **growth** (§4.5: the spark of the session's size over its steps in the Context window panel, marked
where OpenCode compacted and where the loop guard stopped an answer). While the model writes, the page redraws at most
four times a second (§2), and the spinner touches only its own cells.

**Architecture:**

- **The gateway** (`clank/components/gateway/activity.py`): a request in flight also says its time to the first token
  (`first_ms`), the kind of the text it wrote last (`newest`: thinking, answer or tool) and, while that is a tool
  call's, the call being written (`writing`: its name and its arguments' newest characters). Only the gateway sees a
  call's arguments as they stream (§5.3).
- **What the session does now, in the service** (`clank/components/agents/now.py`), a pure function, as the context
  totals and the Guide are, so the phone can show it later: `now(session, doing, view, routes, facts_of, guard,
  moment)` reads the gateway's activity of the session (its request in flight and its requests that ended), its flow
  (OpenCode's status, its calls running, its asks, a compaction under way), the slot's facts and the loop guard's
  setting, and gives the phase of §5.1 with its source and its detail, the step and its seconds, the thinking and the
  answer against their budgets, the prompt, the call being written, the speed and its steps' speeds, and the loop
  guard's state. `Agents.now(workspace, session)`; `GET /agents/now/{workspace}/{session}`.
- **The bridge** (`clank/components/workspaces/image/bridge.py`): a new action, `part`, gives one call whole (its
  input and output, up to `WHOLE` characters each, saying when it cut them), read from OpenCode's
  `GET /session/:id/message/:mid`; `Sessions.part`; `GET /agents/sessions/{workspace}/{port}/{session}/part/{message}/
  {part}`. The sandbox image's tag follows its files, so a workspace opened next gets it; an older image's refusal is
  said in the window, with what the flow keeps.
- **The console** (`clank/components/agents/console/`): `nowpanel.py` (the Now panel's lines and its widget, the
  spinner a widget of its own one cell wide), `callspanel.py` (the Tool calls panel's rows, newest first, and its list,
  Enter opening a call whole), `livepanel.py` (the live text, a panel under the Flow, hidden until `l`), and the growth
  spark in `contextpanel.py`. The Monitor (`monitor.py`) gets one timer of four ticks a second instead of its reading
  every second: each tick draws what the readings brought since the last (so the page redraws at most four times a
  second, whatever arrives), starts the session's reading every fourth tick (`Following`, as before), and reads what
  the session does now (and the live text while shown) every tick while the session works, every fourth while it does
  not (`Watching`, in `following.py`). Nothing is read while the page is not on screen.

**Tech stack:** Python 3.12, FastAPI, Textual 8.2.8, pytest with the console's text snapshots, the fake OpenCode
(`tests/fakes/opencode.py`) with the bridge run on this machine, and synthetic sessions (`tests/support/flowlines.py`,
`tests/support/boards.py`).

**Spec:** [design 0012](../design/0012-the-monitor.md) §2 (keys, redraws), §4.5 (growth), §5 (now), §7 (tool calls
and the live text), §11 step 7; [design 0001](../design/0001-runtime-and-console.md) §5.7 (redraws); [design
0011](../design/0011-the-consoles-look.md) §2 (the style's marks and colors); decisions 0040 (the loop guard), 0044 (no
color outside a style), 0045 (nothing spills), 0048 (which session).

## Global Constraints

- Nothing here runs OpenCode, a container, Docker or a model: the bridge's new action is tested against the fake
  OpenCode with the bridge run on this machine, the gateway's figures with its activity alone, the console against a
  service served in the test with the gateway's answers given by the test.
- No new dependency. Tests first, named as sentences; each test file's docstring names the design sections.
- Every field added to an answer is added, never renamed.
- Every color is a `$clank-` element of the style, every mark the style's (decision 0044); no line wider than its
  panel (decision 0045).
- Redraws (design 0001 §5.7, design 0012 §2): at most four a second, only what changed, nothing while nothing changed;
  the page reads the service only while it is on screen.
- The owner is the sole author of every commit (no trailer); nothing is pushed from this lane. American English.

## Measurements (pending)

- [ ] **Decoding speed with the page on screen** (design 0012 §2's pass mark, 95%; §10, before step 2; still pending
  from plans s11 and s16): now with Now and the live text read four times a second while the model writes. If it
  fails, §2's fallbacks in their order: the page's rhythm is one constant (`clank/console/app.py`'s
  `REDRAWS_PER_SECOND`, which the page's tick reads), so "at most once a second" is a one-line change; then freezing
  the live text and the flow while the model writes.
- [ ] **Whether one streamed event carries several tokens with MTP drafting** (§10, before step 2): the live counts
  say "about" until then, and are corrected from the engine's count at the answer's end whatever the measurement says.

## Tasks

### Task 1: The gateway says what a request in flight writes now

- [x] **Files:** `clank/components/gateway/activity.py` (`_flying`); `tests/components/gateway/test_activity.py`.
- [x] **Interfaces:** each request in flight gains `first_ms` (its time to the first token, None until it came),
  `newest` (the kind of the text it wrote last, "" before any) and `writing` (while its newest text is a tool call's:
  `{"tool": its name, "arguments": the newest WRITING characters of its arguments}`, else None).
- [x] **Tests:** `test_a_request_in_flight_says_its_time_to_the_first_token_what_it_writes_now_and_the_call_being_written`;
  the first test's dict gains the three fields.

### Task 2: What the session does now, in the service

- [x] **Files:** create `clank/components/agents/now.py`; `clank/components/agents/service.py` (`Agents.now`),
  `clank/components/agents/api.py` (the route); `tests/components/agents/test_monitor_now.py`.
- [x] **Interfaces:** `now(session, doing, view, routes, facts_of, guard, moment) -> dict`: `phase` (§5.1's words),
  `state` (its key), `source` (gateway or OpenCode), `detail`, `working`, `step`, `seconds`, `request`, `prompt`
  (`first_ms`, `reading`, `tokens`, `cached`, `of`), `thinking` and `output` (`tokens`, `about`, `budget`), `writing`,
  `speed` (`now`, `steps`), `guard` (`on`, `ratio`, `parts`, `stopped`, `said`). `GET /agents/now/{workspace}/{session}`.
- [x] **Tests:** `test_each_row_of_the_phase_table_is_said_from_its_source` (every row of §5.1, and OpenCode working
  between its steps);
  `test_reading_the_prompt_is_said_or_queued_and_queued_is_never_claimed_alone`;
  `test_live_counts_say_about_and_the_answers_end_corrects_them_from_the_engines_count`;
  `test_the_prompt_is_this_steps_time_and_the_previous_steps_size_and_the_speed_keeps_each_steps`;
  `test_the_loop_guard_says_off_watching_each_parts_share_or_what_it_stopped`;
  `test_the_route_says_what_the_followed_session_does_now`.

### Task 3: The Now panel, its spinner in its own cell

- [x] **Files:** create `clank/components/agents/console/nowpanel.py`; `monitor.py` (the Now panel holds it);
  `tests/console/test_monitor_now.py`; the Monitor's snapshots that show the panel.
- [x] **Interfaces:** `lines(now, width, zone) -> list[Content]`; `NowView` (its spinner, `NowSpin`, one cell; its
  phase line; its other lines), `show(now)`, `spin(frame)`, `draws`.
- [x] **Tests:** `test_the_now_panel_says_the_phase_its_budgets_the_prompt_the_call_being_written_the_speed_and_the_loop_guard`;
  `test_no_now_line_is_wider_than_the_panel`;
  `test_the_spinner_touches_only_its_own_cells`;
  `test_the_session_view_while_the_model_writes_at_128_columns` (a snapshot).

### Task 4: Four ticks a second: what the session does now, read while it works, and at most four redraws

- [x] **Files:** `clank/components/agents/console/following.py` (`Watching`), `monitor.py` (one timer, `TICKS`,
  pending readings drawn on the tick, `redraws`); `tests/console/test_monitor_now.py`.
- [x] **Interfaces:** `Watching(client).read(workspace, session) -> dict | None` (None when unchanged or a reading is
  under way); `MonitorPage.redraws` (ticks that drew something). As built: the console calls `Page.tick()` on each of
  its redraw ticks (`clank/console/app.py`'s `_drain`, before it draws the header, so the header's spinner follows),
  and the Monitor draws there what its readings brought, instead of a timer of its own; `Following` no longer reads
  what the session does now. **Files** also: `clank/console/app.py`, `clank/console/pages/__init__.py`.
- [x] **Tests:** `test_while_the_model_writes_the_page_redraws_at_most_four_times_a_second`;
  `test_now_is_read_four_times_a_second_only_while_the_session_works_and_never_while_the_page_is_not_on_screen`.

### Task 5: Tool calls, and one call whole through the bridge

- [x] **Files:** `clank/components/workspaces/image/bridge.py` (`part`), `clank/components/agents/sessions.py`
  (`Sessions.part`), `api.py` (the route); create `clank/components/agents/console/callspanel.py`; `monitor.py` (the
  panel, Enter); `tests/components/agents/test_monitor_bridge.py`, `tests/console/test_monitor_calls.py`.
- [x] **Interfaces:** the bridge's `part <port> <session> <message> <part> [limit]` → `{"part": {id, message, tool,
  call, status, title, input, output, error, length, cut}}` (`WHOLE`, 200,000 characters each: an input's start, an
  output's end); `Sessions.part(workspace, port, session, message, part)`; `rows(view) -> list[dict]`,
  `line(row, width, zone) -> Content` and `whole(row, found, why, zone)`; `CallsList` (a list, Enter on the page opens
  the call highlighted in `CallScreen`, a window that scrolls). As built: a panel's letter now focuses the first thing
  in it that is shown (`Panel.enter`), not its empty label once hidden; board A's calls are timed as OpenCode times
  them (`tests/support/boards.py`).
- [x] **Tests:** `test_the_bridge_gives_one_call_whole_its_input_and_output_cut_only_past_a_cap`;
  `test_tool_calls_are_listed_newest_first_with_their_time_tool_what_they_do_and_their_size_a_failed_one_in_red`;
  `test_enter_on_a_call_reads_it_whole_through_the_bridge_once_and_only_while_the_page_is_on_screen` (the
  `docker exec` only while shown); `test_a_call_the_bridge_cannot_give_whole_shows_what_the_flow_keeps_and_why`.

### Task 6: The live text

- [x] **Files:** create `clank/components/agents/console/livepanel.py`; `following.py` (`Watching` reads the live text
  from its offset while asked); `monitor.py` (`l`, the panel under the Flow, hidden until asked);
  `tests/console/test_monitor_live.py`.
- [x] **Interfaces:** `LiveView` (`take(found, asked)`, its text kept and grown from the offset, a new request read
  from its start; `forget()` when another session is followed); `Watching.text(session, after, request)`; the page's
  key `l`. As built: the panel is the Session view's (`view-session live-text`), shown by the page's class `-live`,
  with no letter of its own, since `l` is the key that shows it; `test_panels_everywhere.py` shows it with `l`.
- [x] **Tests:** `test_l_shows_the_followed_sessions_live_text_and_hides_it_again`;
  `test_the_live_text_is_read_from_its_offset_only_while_shown_and_a_new_request_from_its_start`.

### Task 7: Growth: the spark of the session's size, marked

- [x] **Files:** `clank/components/agents/console/contextpanel.py` (`growth`, `spark_line`, the panel shows the flow's
  steps too); `monitor.py`; `tests/console/test_monitor_context.py`; the snapshots that show the panel.
- [x] **Interfaces:** `growth(view) -> list[Point]` (each finished step's size as OpenCode counts it, a compaction and
  a loop guard stop marked); `spark_line(points, width, window, zone) -> Content`; `lines(totals, width, zone, view)`
  and `ContextWindow.show(totals, zone, view)`. Board A's steps are counted as OpenCode counts them, so its frames show
  the spark.
- [x] **Tests:** `test_the_growth_spark_marks_compactions_and_loop_guard_stops`;
  `test_the_growth_spark_fits_the_panel_and_says_nothing_before_a_step_ended`.

### Task 8: Documents

- [x] Design 0012 §11 step 7 marked built with this plan; the roadmap's M5 row; the plans' index; `docs/console.md`;
  the walkthrough's Monitor keys (`l`); the glossary if a word is new; the generated files (`uv run python -m
  tools.check --fix`); this plan's boxes and its Built note.

- Built 2026-10-20, in eight commits after this plan's (one per task, then the full check's findings), then this one.
  Found on the way: with a session
  that works, the Now panel's spinner turned in every Monitor test, so no frame was the same twice: the Monitor's tests
  hold the console's spinner still (`still_spinner`, `tests/console/conftest.py`) and turn it themselves; a frame could
  be taken between the flow's drawing and the Now panel's, so the frames wait for both (`known`); a `Static`, not a
  `Label`, holds the spinner's cell, since the console's style sheet gives every label of a page its whole row; the
  call lines leave the list's scroll bar its two columns; and the Tool calls panel's empty label, hidden, still took
  the focus from `t` until `Panel.enter` skipped what is not shown. The full check (`tools.check --fix`) found that
  the agents read the gateway's phases from its activity module, where a component may use another only through
  its service (the service now names them), and the live text's drawing in the gateway's console, now the
  console's own (`clank/console/text.py`), and two glyphs written in the Monitor's help instead of the style's
  marks; its one other failure, `tests/kernel/test_service.py`'s stop of the event stream, passed alone and
  touches nothing of this step. Reviewing the growth spark, a compaction said with no summary seen was drawn after
  the steps that followed it; it is drawn where it was.

### Task 9: The review's fixes

- [x] **Files:** `following.py` (`Watching.forget`), `monitor.py` (`_show`, `tick`, `_live_shown`, `CallsRow`,
  `TURN_SECONDS`; no `busy` or `spin` of its own), `nowpanel.py` (`NowView.turn`, its own `frame`; the loop guard's
  line), `callspanel.py` (`NO_CALL`, the list's rows as laid out, its docstring), `clank/components/agents/now.py` and `service.py`
  (the guard as applied), `clank/components/gateway/server.py` (`/activity` says the guard it applies),
  `tests/console/conftest.py` (`still_spinner` holds the Now cell too); the tests below; the Monitor's frames.
- [x] **Found and fixed:** the Now panel stayed "no session yet" for a session followed again whose state had not
  changed, since `Watching` left out a reading equal to its last: the page now makes it forget its last reading when
  it follows another session. The live text was read on the Flow and Context views, where it is not shown: it is read
  only on the Session view. The Monitor made the console busy while its session ran a tool or worked between steps, so
  the console's spinner turned ten times a second in the header and the column: the Now cell now turns on the page's
  ticks, at most four times a second, and the console's spinner only for its operations and model requests, as
  before. At 160 by 40 the Session view scrolled: Tool calls now gives up rows first (design 0012 §2's room): side by
  side, its row takes the rows the page has left, down to one row of calls and up to what it holds, laid out by
  Textual in the same pass as the panels above it; stacked, it keeps its rows and the page scrolls. Tool calls said
  "no session yet" for a session with no call: "no tool call yet". The loop guard was said from its settings file as
  it is now, though the gateway applies it when it starts: the gateway's activity now says the guard it applies, and
  the Now panel says a change in the file that waits for its restart. A docstring said a failed call's whole line was
  red: its mark and what it does are.
- [x] **Tests:** `test_a_session_followed_again_shows_what_it_does_now_though_that_did_not_change`;
  `test_a_tool_running_turns_only_the_now_cell_at_most_four_times_a_second_not_the_consoles_spinner` (it does not hold
  the spinners still); `test_the_live_text_is_read_from_its_offset_only_while_shown_and_a_new_request_from_its_start`
  (now through the Context and Flow views); `test_a_session_followed_with_no_call_yet_says_so_in_tool_calls`;
  `test_when_rows_are_short_tool_calls_give_up_rows_so_no_panel_is_cut`;
  `test_the_loop_guard_is_said_as_the_running_gateway_applies_it_and_a_change_waiting_for_its_restart_too`;
  `test_a_loop_guard_setting_that_waits_for_the_gateways_restart_is_said`; the gateway's activity test says its guard.

## Left for later

- **`s`, picking another session** and **`z`, a panel on the whole page** (plan s16 said they would come with this
  step): neither is among §11 step 7's tests, and each changes how the page follows or lays out every panel; they are
  the next small step of the page, with **Enter on a subagent opening its own panels** (§3), which needs the same
  choice of session.
- **Where another session took the engine** on the growth spark (§4.5): the gateway keeps whose request each slot read
  last only for now (`slots`), not for each request that ended; marking it on each step needs the gateway to keep it
  per request, which step 12's figures per request will do.
- **The Context view's chart, "Over this session"** (§4.5, board C): step 12, with the parts it splits it by.
- **Biggest and Watch for giving up rows** (§2's room): Biggest has one line until step 12 fills it, and Watch for
  lists few marks; when they hold more, they give up rows after Tool calls, as `_fit` does for it.

## Claude's calls (2026-10-20)

1. **Now is made in the service**, as the context totals and the Guide are: the phone can show it later, and the
   console draws it without knowing an engine's or a model's numbers (decision 0067).
2. **The page has one tick, four times a second**, and draws on it what its readings brought: so the page redraws at
   most four times a second however the readings arrive, as the shell does with the events (`_drain`).
3. **Now is read every tick while the session works** (OpenCode busy or retrying, or a request of it in flight), every
   fourth tick otherwise; the live text only while it is shown. Both cost the service a question to the gateway, no
   `docker exec`.
4. **The answer's line counts everything the model writes** (its thinking, its text and its calls) against the output
   limit, as the engine's `max_tokens` does and as Watch for's budget rule reads it; the thinking's line its thinking
   against its budget. At the answer's end the answer's count is the engine's own, and the thinking's is the live count
   scaled to it, still "about", since usage has no separate count for thinking (§5.2).
5. **OpenCode working with no request in flight and no tool running** is said "working, between its steps": the table
   of §5.1 has no row for it, and nothing is claimed beyond what OpenCode says.
6. **The speed's spark is the session's steps' speeds**, the newest last, so it says the same at every look.
7. **The live text is a panel across the page under the Flow's row**, hidden until `l`: the Flow panel spans the rows
   beside it, and a panel under it alone would leave a hole in the grid.
8. **A call's size is its characters**, as the flow keeps them (plan s16's call 5).
9. **The Monitor draws on the console's own ticks** (`Page.tick`, a hook of the shell, called before it draws the
   header): one rhythm for the shell and the page, so together they redraw at most four times a second, and the
   header's spinner follows what the page just drew.
10. **The prompt takes two lines**: `prompt` (this step's time to its first token, or how long it has been read, "or
    queued") and `last prompt` (the last prompt whose size is known, read from the cache and new): one line did not fit
    the Now panel's 46 columns, and a size of the step before said beside this step's time read as this step's.
11. **A call's arguments are shown without their first name** (`bash python -m …`, not `bash {"command": "python -m
    …`), as board A draws it; the window of the call has them whole.
12. **The loop guard's line says each part's share and the limit** ("thinking 31%, bash 12% · limit 6%"), and "the
    gateway is stopped" when it is: the guard runs in the gateway, so nothing is watched then.
13. **A call's window shows an input's start and an output's end** past the bridge's cap (200,000 characters each),
    since a command's end says how it ended; it scrolls.
14. **Board A's support data is timed and counted as OpenCode does** (each call a second after its step began, each
    finished step's tokens growing from 9,000 by 7,000 a message), so the frames show the Tool calls panel's times and
    the growth spark; nothing else that reads board A changed.
15. **The session's work does not turn the console's spinner** (after the review; call 9's "the header's spinner
    follows what the page just drew" no longer holds): a page's `busy` is the console's own work (`Page.busy`), and the
    console's spinner turns ten times a second in the header and the column, which design 0012 §2 does not allow the
    page. The Now cell turns on the page's own ticks instead, at most four times a second, whatever runs.
16. **Tool calls gives up rows in the layout itself** (`CallsRow`): side by side, the row of Tool calls and Biggest is
    as tall as the rows the page has left (`1fr`), at least one row of calls and at most what Tool calls holds, so
    Textual fits it in the same pass as everything above it. Measuring the rows left after each layout and fitting the
    list then lagged a layout behind, and a frame between could stand with the page scrolling (its scroll bar then
    came and went, and the panels drew again for the width). Stacked (a narrow window), the panels keep their rows and
    the page scrolls, as a stacked page does.
17. **The loop guard is said as the running gateway applies it**: the gateway's `/activity` says it (its settings
    file is read when it starts, design 0012 §5.4), and the Now panel adds that a change in the file waits for its
    restart; with the gateway stopped, or one from before this said nothing, the file's setting is said, which its
    next start applies.
