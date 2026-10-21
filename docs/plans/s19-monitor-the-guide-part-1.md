# The Monitor, step 9: the Guide, part 1 (Stop, Note, Compact now): implementation plan

> At the owner's request (2026-10-18, design 0012 approved: "Approve all three"; 2026-10-19: the new menu, the Monitor
> and flows built "as quickly as possible"). As for the earlier plans, the files, interfaces and tests by name and
> intent; the code is in the commits.

**Goal:** design 0012 §11 step 9: the Guide's first three actions on the session the Monitor follows, its root (§3):
**Stop now** (`.`, §9.2), **a note** (`m`, §9.3) and **Compact now** (`k`, §9.6). Each shows what §9.1 asks: when it
can run, and when not, why; its key, taken by the page; what it does, in words and as the exact call to OpenCode; what
it costs (the tokens read again, and the time that takes at the engine's reading speed, measured from the gateway's
records); a confirmation, but for Stop; its states; an `agents.acted` event with who did it; and a node in the flow
afterward. Watch for's "tell the model" (step 8) now sends its note through the Guide.

**Architecture:** A module of the agents component, `clank/components/agents/guide.py`:

- `offer(view, *, port, totals, ended, kept)`: a pure function of the session's flow (its view), the server that runs
  it, its context totals (`used`, `keeps`, and the engine's facts' `fields`), the gateway's requests of the session that
  ended (with the time to their first token, `first_ms`), and what the Guide did last in the session (`kept`): each
  action with its key, `can`, `why` (not), `brief` and `does` (words), `calls` (the exact calls), `cost` (`tokens`,
  `seconds`, `words`), `confirm`, and `state` (its last run's, read from the flow).
- `Guide`, kept by the agents service: `offer(workspace, session)` gathers what `offer` reads (the flow, where the
  session runs, the totals, the gateway's figures); `stop`, `note` and `compact` act through the session bridge
  (`sessions.py`, which records `agents.acted`), each refused with its reason (`GuideError`) when it cannot run, and
  keep the action's state, in memory (as the flows are, decision 0049), the last of each kind per session.
- The flow (`sessionflow/flow.py`) learns that the Guide asked a compaction (`Flow.compaction_asked`): the next band
  is the owner's (`asked`), drawn "compacted by you", though the Guide asks with `auto` on as §9.6 says.
- The gateway's request that ended keeps its time to the first token (`first_ms`), the measure of the reading speed.
- Routes: `GET /agents/guide/{workspace}/{session}`, `POST /agents/guide/{workspace}/{session}/stop`, `.../note`
  (`text`, `about`, `reject`), `.../compact`; a refusal is a 409 in the Guide's words.
- The console: the Guide panel (`guidepanel.py`) lists the three actions with their keys, grayed with the reason when
  one cannot run, each with its cost and its last state; on the Session view the page takes `.`, `m` and `k`: `.` stops
  at once, `m` opens the note window (about the node under the flow's cursor, to the session's agent, its cost), `k`
  a window that says what the compaction does and costs, Enter to do it, Esc to leave it (`confirm.py`).

**Tech stack:** Python 3.12 standard library; FastAPI; Textual; pytest with the fake OpenCode (`tests/fakes/
opencode.py`), the bridge run on this machine, the session-flow lines (`tests/support/flowlines.py`), and the console
driven headless against a service served in the test.

**Spec:** [design 0012](../design/0012-the-monitor.md) §9.1, §9.2, §9.3, §9.6, §3 (the Guide acts on the root session,
on the server that runs it) and §11 step 9; [decision 0048](../decisions/0048-the-monitor-follows-the-newest-session-of-its-folder.md),
[decision 0054](../decisions/0054-a-note-is-a-real-user-message.md),
[decision 0079](../decisions/0079-every-action-on-a-session-goes-to-the-server-that-runs-it.md),
[decision 0082](../decisions/0082-a-watch-for-action-that-cannot-run-tells-the-phone.md).

## Global Constraints

- Nothing here runs OpenCode, a container, Docker or a model: a GPU benchmark ran through them. The
  actions are tested against the fake OpenCode with the bridge run on this machine, as step 4's are.
- No new dependency. Tests first, named as sentences; each test file's docstring names the design sections.
- Every field added to an answer is added, never renamed.
- The owner is the sole author of every commit (no trailer).

## Measurements of §10 for this step (pending)

- [ ] **That a note is read at the next step, and the session keeps its agent** (§9.3), under OpenCode 1.19.0: a note
  sent while a planner session works, its next step's request read at the gateway.
- [ ] **The race of a note at a run's end** (§9.3, §8): a note sent as the run's last step ends; the flow marks it not
  read, with "send again".
- [ ] **Stop with an approval waiting, and Stop while a subagent runs** (§9.2): nothing left waiting, the subagent's
  request canceled at the gateway.
- [ ] **What a note and a compaction cost in reading again** (§9.1): the prompt the engine reads after each, against the
  estimates the Guide shows (the note: everything since the owner's previous message; the compaction: the whole history).

Until they are made, each cost the Guide shows says it is an estimate, to measure.

## Review Focus

1. **The server**: every action goes to the server whose stream carried the session's run (decision 0079); with none
   known, the Guide refuses and says why, and sends nothing.
2. **Stop must be quick**: no confirmation; the abort first, then the reject of what waits, so a slow reject never
   delays the stop.
3. **The note's agent**: the bridge sends the agent and the model of the session's last message of the owner, however
   far back, so a planner session stays planner; the Guide's answer says which were used.
4. **A note while a call waits for approval** rejects that call with the note as the reason, adding no message.
5. **States read from the flow**, never guessed: a stop is "stopped" once the session is idle; a note is "waiting",
   "read by step n", "answered" or "not read" as the flow says of its message; a compaction "compacting" once its band
   begun, "done" when the flow says so.

## Tasks

### Task 1: The time to the first token, and the band the owner asked for

- [x] **Files:** `clank/components/gateway/activity.py` (`_ended`: `first_ms`); `clank/components/agents/sessionflow/
  flow.py` (`Flow.compaction_asked`, a band's `asked`), `kept.py` (`SessionFlows.compaction_asked`);
  `clank/components/agents/console/flowtree.py` (a band the owner asked for is "by you");
  `tests/components/gateway/test_activity.py`; `tests/components/agents/test_session_flow.py`.
- [x] **Tests:** `test_a_request_that_ended_keeps_its_time_to_the_first_token`;
  `test_the_band_of_a_compaction_the_guide_asked_for_is_the_owners`.

### Task 2: What the Guide offers

- [x] **Files:** create `clank/components/agents/guide.py` (`offer`, `reading_speed`, `KEYS`, `TITLES`);
  `tests/components/agents/test_guide.py`.
- [x] **Interfaces:** `offer(view, *, port, totals, ended, kept) -> list[dict]`, each `{action, key, title, can, why,
  brief, does, calls, cost: {tokens, seconds, words}, confirm, state}`; `reading_speed(ended, fields) -> (tokens a second,
  tokens read) | None`.
- [x] **Tests:** `test_each_action_says_its_key_what_it_does_its_exact_call_and_its_cost`;
  `test_an_action_that_cannot_run_says_why`;
  `test_the_reading_speed_comes_from_the_gateways_records_else_the_time_is_not_known`;
  `test_each_actions_state_is_read_from_the_flow`.

### Task 3: The actions, against the fake OpenCode

- [x] **Files:** `guide.py` (`Guide`, `GuideError`); `clank/components/agents/sessions.py` (`send` gives what the
  bridge said it sent); `clank/components/agents/service.py` (`Agents.guide`); `tests/components/agents/
  test_guide_actions.py`.
- [x] **Interfaces:** `Guide.offer(workspace, session)`, `Guide.stop(workspace, session, *, actor)`,
  `Guide.note(workspace, session, text, *, about="", reject=True, actor)`, `Guide.compact(workspace, session, *,
  actor)`.
- [x] **Tests:** `test_stop_aborts_the_session_and_rejects_a_waiting_ask_on_the_server_that_runs_it`;
  `test_a_note_carries_the_agent_the_model_and_what_it_is_about`;
  `test_a_note_while_a_call_waits_for_approval_rejects_that_call_with_the_note`;
  `test_compact_now_asks_summarize_with_the_agent_role_and_auto_on_and_returns_at_once`;
  `test_each_action_leaves_an_agents_acted_event_with_who_did_it`;
  `test_an_action_that_cannot_run_sends_nothing_and_says_why`.

### Task 4: Watch for's note through the Guide

- [x] **Files:** `clank/components/agents/service.py` (the marks' `acting`: the Guide's note, as the rule; the pause
  still step 11's); `clank/components/agents/watchfor/marks.py` (its docstring and `NotYet`);
  `tests/components/agents/test_watch_for_marks.py`; `tests/components/agents/test_guide_actions.py`.
- [x] **Tests:** `test_a_rules_note_goes_through_the_guide_as_the_rule`; the test of an action not built yet keeps the
  pause (step 11) only.

### Task 5: The routes

- [x] **Files:** `clank/components/agents/api.py`; `tests/components/agents/test_guide_actions.py`.
- [x] **Tests:** `test_the_routes_offer_the_actions_act_and_refuse_with_the_reason`.

### Task 6: The Guide panel and its keys

- [x] **Files:** create `clank/components/agents/console/guidepanel.py` (`GuideList`, `lines`, `about`) and
  `clank/console/confirm.py` (`ConfirmScreen`); `following.py` (`Seen.guide`); `monitor.py` (the panel, the keys `.`,
  `m`, `k`, the windows); `tests/console/test_monitor_guide.py`; the Session view's snapshots written again.
- [x] **Tests:** `test_the_panel_lists_stop_note_and_compact_with_their_keys_costs_and_states`;
  `test_an_action_that_cannot_run_is_grayed_with_its_reason`;
  `test_the_note_is_about_the_node_under_the_flows_cursor`;
  `test_dot_stops_at_once_m_sends_a_note_and_k_asks_first`; a frame of the Session view with the Guide panel.

- Built 2026-10-20: the note's window has two fields, the note and what it is about (filled in from the flow's
  cursor, which the owner may change or empty); when no action can run for one reason (no server known), the panel
  says the keys on one line and the reason once.

### Task 7: The documents

- [x] Design 0012's step 9 note and index, the roadmap, the glossary (the Guide's actions), this plan's ticks and
  Claude's calls, `docs/plans/README.md`; the generated pages (`uv run python -m tools.check --fix`).

## Claude's calls (2026-10-20)

1. **Stop aborts first, then rejects what waits**: §9.2 lists the abort first; it is what must be quick, and a reject
   that finds nothing costs one call of the bridge.
2. **The note's agent and model are the bridge's**: the bridge reads the session's last message of the owner however
   far back (step 4), so the Guide names no agent itself, and its answer says which were used; the panel says the
   agent the flow shows.
3. **What a note is about is in words the console makes** ("step 12, `bash pytest -q`"), from the node under the flow's
   cursor, as the renderer words it; the service puts "About …: " before the text, so the phone can send its own words.
4. **The costs are estimates until measured** (§10): a note, everything since the owner's previous message (the last
   finished step's prompt and answer, less the prompt of the first step after that message); a compaction, the whole
   history (the totals' `used`); the time, at the reading speed of the newest step that read at least `READ_LEAST`
   tokens anew (llama.cpp's `prompt_per_second`, else the tokens read anew over the time to the first token).
5. **A compaction the Guide asked for is drawn "by you"**: OpenCode's band of a compaction asked with `auto` on looks
   like its own, so the flow is told which band the owner asked for (the next one after the asking).
6. **States live in memory**, the last of each action per session, as the flows and the marks do (decision 0049).
7. **The keys bar lists `.`, `m` and `k` on every view of the Monitor**, as it lists Enter and Esc, since the bar is the
   page's; Help and `?` say they act on the Session view, where the Guide panel is.
8. **A Watch for rule's note never rejects a call**: a rule does not answer an approval the owner may still give; its
   note is a message, as before this step (decision 0082's "tell the model").
9. **A stop whose reject failed is still a stop**: the abort went, so the state stays "stopping" and says that what
   waits could not be rejected, for the owner to answer.
