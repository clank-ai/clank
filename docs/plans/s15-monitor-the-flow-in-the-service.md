# The Monitor, step 5: the flow in the service: implementation plan

> At the owner's request (2026-10-18, design 0012 approved: "Approve all three"; 2026-10-19: the new menu, the Monitor
> and flows built "as quickly as possible"). As for the earlier plans, the files, interfaces and tests by name and
> intent; the code is in the commits.

**Goal:** design 0012 §11 step 5: the service keeps a flow for every session its watchers see (decision 0049), built
from the bridge's lines and rebuilt from OpenCode's history, joined to the gateway's requests by session; each flow's
steps, calls, fan-outs, subagents, notes, compaction bands and branches (decision 0050) are facts the renderer (step 6)
draws and the Watch for rules (step 8) read; the console asks for what changed since its version.

**Architecture:** A small package, `clank/components/agents/sessionflow/` (a session's flow, design 0012; not design
0013's flows of boxes, which live in `clank/components/flows/`), in four pure modules and one that keeps them:

- `flow.py`: `Flow`, one session's flow. It takes the watch's lines about its session (`message`, `part`, `removed`,
  `todo`, `compacted`, `error`, `status`, `session`, `asked`, `replied`), pages of its history (`Sessions.page`) and
  the gateway's requests of the session, and keeps them as they came (messages and parts by id, the todo list's
  revisions, the asks). Its view is built from that state when it is read after a change: the head (the session's
  facts), the nodes in time order (the owner's messages and notes, the steps, their calls, the subagents, the
  compaction bands) and the branches; each node carries the version at which it last changed, so `changes(since)`
  gives only the nodes that changed and those removed.
- `branches.py`: the main branches (decision 0050): a Clank plan's checklist steps when the session carries one out
  (its first message is `/implement`'s, naming the plan's file), else the todo list's items matched across revisions
  by their text, else the owner's messages; and the branch each step joins.
- `pairing.py`: which gateway request answered which step: by their calls' ids where the gateway saw them, else in
  order by time.
- `kept.py`: `SessionFlows`, the flows in the service: it listens to `Sessions` (every watcher line), keeps a flow per
  session seen (children included, bounded), rebuilds a flow from OpenCode's history in a thread of its own when it is
  first seen and after its server's instance ended, reads the plan's file in the workspace's folder, and asks the
  gateway for a session's requests once a second at most after its steps change.

The bridge's message shape gains the error's name (`error_name`), so a step the owner stopped tells apart from one that
failed; the gateway's activity gains each request's tool-call ids (`calls`) and, asked for them, a session's requests
that ended (`ended`). The service answers `GET /agents/flow/{workspace}` (the flows kept, briefly) and
`GET /agents/flow/{workspace}/{session}?since=` (one flow, whole or what changed).

**Tech stack:** Python 3.12 standard library; FastAPI; pytest with the synthetic OpenCode session of plan s14
(`tests/fixtures/opencode/1.19.0/session.json`), lines in the bridge's own shapes (its `seen_message`, `seen_part`).

**Spec:** [design 0012](../design/0012-the-monitor.md) §3, §5.1, §6.1-§6.4, §9.3 and §11 step 5;
[decision 0049](../decisions/0049-a-sessions-flow-is-built-in-the-service.md),
[decision 0050](../decisions/0050-a-flow-branches-by-plan-items-fan-outs-and-side-lanes.md); design 0009 §4
and §5.1 (a plan, `/implement`).

## Global Constraints

- Nothing here runs OpenCode, a container, Docker or a model: a GPU benchmark ran through them. The flow
  is tested on lines in the bridge's shapes, on the fake OpenCode of plan s14 with the bridge run on this machine, and
  on the gateway's `Activity` alone.
- No new dependency; no database table (decision 0049). What is kept is bounded: briefs of text, the flows of the
  newest sessions of each workspace, the gateway's newest requests of each session.
- The flow is never rebuilt from the gateway's records (decision 0049); the gateway's activity gives a session's
  requests in brief only.
- Nothing the watcher's thread does waits on Docker or on the gateway: history reads and the gateway's requests are
  asked from the keeper's own thread.
- Every field added to an answer is added, never renamed. Tests first, named as sentences; each test file's docstring
  names the design sections. The owner is the sole author of every commit (no trailer); nothing is pushed from this
  lane.

## Measurements before this step (pending)

- [ ] **Whether KVMem streams an id with every tool call** (design 0012 §10, before step 5): one answer with two calls,
  its stream read at the gateway for `tool_calls[].id`. Until then a step pairs with its request in order by time when
  the gateway saw no ids (`pairing.py`), and says so; with ids, the pairing is confirmed by them.
- [ ] **How OpenCode 1.19.0's messages page** (before step 4, still pending from plan s14): the rebuild reads pages by
  OpenCode's own cursor, as `page` does.
- [ ] **The clocks of the container and of this machine**: a step's start is OpenCode's (the container's clock), a
  request's the gateway's (this machine's); pairing by time allows `SKEW` (2 s) between them. One session's steps and
  requests compared on the real machine say whether that is enough.

## Review Focus

1. **Pairing by time** when the gateway saw no call ids: a request pairs with the step, after the one the request
   before it paired with, that began nearest to when it began, among those that began no later than `SKEW` after it;
   steps passed over had requests the gateway no longer keeps; when no later step began by then, the request is another
   try of the step before it. Two clocks a second or more apart, with steps quicker than that, can pair a request with
   the next step; the call ids, when the engine streams them, settle it.
2. **History and live lines together**: a rebuild reads pages while lines keep coming; what a line said after the
   reading began wins over the history.
3. **The view built on read**: lines only change the state; the view (and the version) is built when it is read after a
   change, so a burst of a hundred lines costs one build.
4. **A step in or out of the context**: OpenCode leaves an answer that ended in an error out of every later request,
   except one the owner stopped that has content beyond its start and thinking (its `message-v2.ts`, read 2026-10-18).
5. **Branches from a plan**: the plan's ticks are its file's now; a step's branch is the first not ticked when it began,
   worked out from the ticks the implementer's edits of the plan made since.

## Tasks

### Task 1: The bridge says how a step ended

- [x] **Files:** `clank/components/workspaces/image/bridge.py` (`seen_message`); `tests/components/agents/test_monitor_bridge.py`.
- [x] **Interfaces:** a step's `error_name`: the name of the error OpenCode kept (`MessageAbortedError` when the owner
  stopped it, `APIError`, ...), "" for none.
- [x] **Tests:** `test_a_steps_error_keeps_its_name_so_a_stop_tells_apart_from_a_failure`.

### Task 2: A step with its fan-out, in or out of the context

- [x] **Files:** create `clank/components/agents/sessionflow/__init__.py`, `flow.py`;
  `tests/components/agents/test_session_flow.py` (with helpers that turn the fixture's history and bursts into the
  bridge's lines, by the bridge's own functions).
- [x] **Interfaces:** `Flow(session, workspace="")`; `heard(line)`; `history(page, joined=False)`; `view() -> dict`
  (`head`, `nodes`, `items`, `version`). Nodes: `said` (the owner's message), `step` (`n`, `said`, `agent`, `model`,
  `created`, `completed`, `tokens`, `finish`, `error`, `ended`: working, finished, stopped or failed; `context`: in
  or left; `calls`; `together`: the calls made at once; `thinking`; `text`), `call` (`step`, `tool`, `call`,
  `status`, `title`, `input`, `length`, `error`, `exit`, `failed`, `dead_end`, `cleared`); each with `at`, its place
  in time.
- [x] **Tests:** `test_parts_become_a_step_with_its_calls_made_at_once_fanned_out`;
  `test_a_step_that_ended_in_an_error_is_marked_not_in_the_context_and_a_stopped_one_is_kept`;
  `test_a_failed_call_becomes_a_dead_end_once_the_agent_moves_on`;
  `test_a_message_or_a_part_removed_leaves_the_flow`;
  `test_a_line_about_another_session_or_a_status_changes_only_its_own_facts`.

### Task 3: Subagents, and an ask on its call

- [x] **Files:** `flow.py`; `test_session_flow.py`.
- [x] **Interfaces:** a `subagent` node for each `task` call whose metadata names a session (`session`, `call`, `step`,
  `title`, `status`, `gave`: what it gave back, briefly; `steps` and `state` when its own flow is kept: `child(session,
  brief)`); the session's own subagents named by their `parent` without a call yet hang from the newest step. A
  permission asked for a call (`asked`, its `tool.callID`) marks the call `asking` until it is `replied`.
- [x] **Tests:** `test_task_metadata_becomes_a_subagents_branch_from_its_call`;
  `test_a_permission_asked_for_a_call_waits_on_that_call_until_it_is_replied`.

### Task 4: A Clank plan's steps are the main branches

- [x] **Files:** create `clank/components/agents/sessionflow/branches.py` and `text.py` (a text kept on one line,
  cut); `flow.py` (`plan`, `planned`);
  `tests/components/agents/test_session_flow_branches.py`.
- [x] **Interfaces:** `plan_named(text) -> str`: the plan's file a message of `/implement` names ("Implement the plan
  in this file: ..."); `checklist(text) -> list[(title, ticked)]`: the plan's Steps section's checklist (every
  checklist line of the file when it has no Steps section); `from_plan(...)`: each branch's `key`, `title`, `source`
  (`plan`, `todo` or `said`), `state` (done, now, planned or canceled), `guessed` and `why`, its `steps`; each step's
  `item`. A plan's ticks are its file's now; the edits of the plan's file that ticked a box (`[ ]` to `[x]` in an
  `edit` call's input) say which item each step worked on.
- [x] **Tests:** `test_a_clank_plans_checklist_steps_become_the_main_branches_even_beside_a_todo_list`;
  `test_a_step_joins_the_plan_step_first_not_ticked_when_it_began`;
  `test_a_plans_steps_section_is_read_and_its_other_checklists_are_not`.

### Task 5: Without a plan, the todo list; without either, the owner's messages

- [x] **Files:** create `clank/components/agents/sessionflow/todos.py` (`written`, `follow`); `branches.py`
  (`from_said`); `flow.py` (the todo list's revisions, from `todo` lines and from `todowrite` calls in the history);
  `test_session_flow_branches.py`.
- [x] **Interfaces:** each todo revision placed after the step that wrote it; items matched across revisions by their
  text, exactly, else by likeness (a guess, `guessed` with `why`); a step joins the item in progress when it began;
  without a plan or a todo list, each owner's message is a branch and the steps that answer it its run.
- [x] **Tests:** `test_without_a_plan_todo_revisions_become_items_matched_by_their_text_a_guess_flagged`;
  `test_a_step_joins_the_todo_item_in_progress_when_it_began`;
  `test_without_either_the_owners_messages_and_the_runs_of_steps_between_them_are_the_branches`.

### Task 6: Compactions, notes and undone steps

- [x] **Files:** `flow.py`; `test_session_flow.py`.
- [x] **Interfaces:** a `band` node for each compaction (OpenCode's compaction message, `auto`, its summary step,
  `done` once `session.compacted` came); the owner's message sent while the session was busy is a note (`note`), its
  `state` waiting, read (with `read_by`, the step that answered it) or not read (the run ended without it); steps from
  a revert's message on are `undone`.
- [x] **Tests:** `test_a_compaction_becomes_a_band_across_the_flow`;
  `test_a_note_sent_while_busy_is_delivered_at_the_next_step`;
  `test_a_note_the_run_ended_without_reading_is_marked_not_read`;
  `test_steps_a_revert_took_back_are_marked_undone`.

### Task 7: The gateway names each answer's calls and a session's requests that ended

- [x] **Files:** `clank/components/gateway/server.py` (`_read_event` keeps each tool call's id in the record's
  `calls`), `activity.py` (`calls` and `time` for a request in flight, `calls` for one that ended; `now(session,
  subagents, ended)`: the session's own requests that ended, oldest first, up to `ENDED_KEPT`), `server.py`'s
  `GET /activity?ended=`, `service.py` (`Gateway.activity(..., ended)`), `api.py`; the expected activity in
  `tests/components/gateway/test_activity.py`, and the folder page's double of `Gateway.activity`
  (`tests/console/test_folder.py`), which the full check found still without `ended`.
- [x] **Tests:** `test_activity.py`: `test_a_sessions_requests_that_ended_are_given_when_asked_oldest_first_and_bounded`;
  `test_session_facts.py`: `test_the_gateway_keeps_the_ids_of_the_calls_an_answer_made`.

### Task 8: N requests pair with N steps

- [x] **Files:** create `clank/components/agents/sessionflow/pairing.py`; `flow.py` (`requests(found)`; a step's
  `request`: its id, time, seconds, speed, prompt, error, looped, left, `confirmed` and `why`; `tries`);
  `tests/components/agents/test_session_flow_pairing.py`.
- [x] **Interfaces:** `pair(steps, requests) -> dict[step id, Paired]`: anchored by call ids, else in order by time
  (the nearest step begun by `SKEW` after the request); a step from before Clank watched is never paired;
  `history(page, since, joined)` marks the steps a first reading found finished as `before`.
- [x] **Tests:** `test_n_requests_pair_with_n_steps_in_order`;
  `test_call_ids_confirm_a_pairing_and_win_over_time`;
  `test_a_request_again_for_one_step_is_a_try_and_the_last_its_answer`;
  `test_steps_whose_requests_the_gateway_no_longer_keeps_stay_unpaired`;
  `test_a_clock_a_second_apart_still_pairs_in_order`.

### Task 9: The console gets only what changed since its version

- [x] **Files:** `flow.py` (`changes(since)`); `test_session_flow.py`.
- [x] **Interfaces:** `changes(since) -> {"version", "base", "whole", "head", "nodes", "removed", "items"?}`: whole
  when `since` is 0 or older than the flow's base (it was rebuilt), else only the nodes changed after `since`, the ids
  removed after it, and the branches when they changed; nothing changes the version while nothing changed.
- [x] **Tests:** `test_the_console_gets_only_what_changed_since_its_version`;
  `test_a_version_older_than_a_rebuild_gets_the_whole_flow`.

### Task 10: The flows kept in the service

- [x] **Files:** create `clank/components/agents/sessionflow/kept.py`; `clank/components/agents/service.py`
  (`Agents.flows`, run beside the watchers), `api.py` (`GET /agents/flow/{workspace}`,
  `GET /agents/flow/{workspace}/{session}`); `clank/components/workspaces/image/bridge.py` (it prints UTF-8 whatever
  the locale says: on Windows, in the tests, a text cut with "…" did not decode); `branches.py` (`same_file`);
  `tests/components/agents/test_session_flows_kept.py`.
- [x] **Interfaces:** `SessionFlows(sessions, ask, read)` (`gateway_asker(kernel)`: the gateway's activity of a
  session with its requests that ended; `plan_reader(kernel)`: a plan's file in the workspace's folder, a Markdown
  file whose header says it is a plan, never outside the folder); `heard(workspace, line)` (a listener of `Sessions`);
  `flows(workspace)`; `flow(workspace, session, since)`; `work()` (one round: history reads, the gateway's requests,
  the plans, each subagent's flow told to its parent's) and `run()` (a round a second); a session first seen is read
  from its history, its finished steps then marked `before` (before Clank watched); a `disposed` or a watcher
  `started` again makes its flows read again; the newest `KEPT` flows of a workspace are kept, those working first.
- [x] **Tests:** `test_a_session_joined_mid_run_marks_its_earlier_steps_before_clank_watched` (the fake OpenCode and
  the bridge run on this machine, through the API); `test_a_flow_is_read_again_after_its_servers_instance_ended`;
  `test_a_sessions_requests_are_asked_of_the_gateway_after_its_steps_change_and_paired`;
  `test_a_plans_file_is_read_in_the_workspaces_folder_and_again_when_it_is_edited`;
  `test_a_subagents_flow_tells_its_parents_what_it_says`; `test_only_the_newest_flows_of_a_workspace_are_kept`;
  `test_a_session_deleted_leaves_the_flows_kept`; `test_session_flow.py`:
  `test_a_flow_keeps_texts_briefly_with_their_whole_lengths` (`flow.slim`: what a flow keeps of a part, `KEEP`
  characters, so the flows of 64 sessions stay small).

### Task 11: Documents and generated files

- [x] **Files:** design 0012 §11 step 5 (*built*) and its index row; the roadmap's M5 row; the glossary (**Session's
  flow**); the plans' index; a decision record for the pairing; `docs/API.md`, the code map and the tests page
  regenerated (`uv run python -m tools.check --fix`); this plan's boxes.
- [x] **Tests:** `uv run python -m tools.check --fix` passes.

### Task 12: After review

- [x] **A reading that failed is tried again.** The review found that a flow whose first history reading failed (a
  `docker exec` refused, a container gone) was never read again until a `disposed` or a watcher `started`, so a
  session joined mid-run lost its earlier steps and their `before` marks. Now the keeper tries again after
  `RETRY_SECONDS` (2 s), twice as long each time up to `RETRY_MOST` (60 s); once the session's server is `gone` the
  flow waits for its watcher to start again or its session to be heard again. Test: `test_session_flows_kept.py`:
  `test_a_flow_whose_reading_failed_is_read_again_later_and_still_marks_its_earlier_steps`.
- [x] **A first reading stays the first.** A watcher's `started` line made a flow just made, still waiting for its
  first reading, read as a later one, so its finished steps were not `before` and paired with older requests. The
  keeper now keeps the flows not read yet apart (`_first`). Test:
  `test_a_watcher_started_again_leaves_a_new_flows_first_reading_its_own`.
- [x] **Two notes in one step are both read by the next.** A note was read only by the step whose parent it is, so the
  earlier of two notes sent during one step read as not read (and design 0012 §9.3 offers "send again" for it). A
  note is now read by the first step that began after it, whatever message that step answers, as OpenCode gives every
  message stored to the next step. Test: `test_session_flow.py`:
  `test_two_notes_sent_during_one_step_are_both_read_by_the_next_step` (live and from the history).
- [x] **An unchanged todo keeps its item.** A reworded or new todo listed before an unchanged one could take the
  unchanged one's item by likeness. A revision now pairs every exact text first, then guesses among what is left.
  Test: `test_session_flow_branches.py`:
  `test_an_unchanged_todo_keeps_its_item_when_a_new_one_alike_is_listed_before_it`.
- [x] **A long todo list read from the history comes whole.** The bridge cuts a call's input at 400 characters and
  its output at 1,500, so a list longer than that was lost after a restart; the bridge's `seen_part` now keeps a
  `todowrite` call's list whole in `todos` (`TODOS`, 200 items at most), read before the output and the input. Test:
  `test_a_long_todo_list_read_from_the_history_is_kept_whole` (through the bridge's own `seen_part`).
- [x] **A subagent continued by a later `task` call** is a branch from each call: a subagent node's id is its call's
  and its session's (`session` beside it), so two calls that continue one session no longer share an id. Test:
  `test_a_subagent_session_continued_by_a_later_task_call_is_a_branch_from_each_call`.
- [x] **Stopping the service does not wait for a round.** The round ran in a thread that could not be canceled and
  read every flow due, each page a `docker exec` of up to 30 s. Now a round reads `READS` (8) flows at most, stops
  between two readings (and two pages) when the service stops (`stop`), and `run` leaves a round under way to end by
  itself (`abandon_on_cancel`). Tests: `test_a_round_reads_a_few_flows_and_stops_between_them_when_the_service_stops`;
  `test_stopping_the_service_does_not_wait_for_a_reading_under_way`.
- [x] **A plan's name with a drive is refused.** On Windows, `Path(folder, "D:", ...)` drops the folder, and a
  subagent's first message, which names the plan, is the model's. `plan_path` refuses a name with a drive (so
  `implement` does too), and the keeper's reader checks that the resolved path lies in the folder. Tests:
  `test_plans.py`: `test_no_other_file_is_one` (`D:/other/plan.md`, `D:plan.md`, `c:/notes/plan.md`);
  `test_a_plans_file_is_read_in_the_workspaces_folder_and_again_when_it_is_edited`.
- [x] **Documents:** the sentence below on the gateway corrected (an old gateway pairs nothing); the step 6 item on
  idle sessions; call 6 revised; this task.

- Built 2026-10-19, in fifteen commits from this plan's on (one or more per task, and the documents), then the
  review's fixes (Task 12) in three more. Found on the way: on Windows the bridge printed a cut text's "…" in the
  console's code page, which the service could not read as UTF-8 (the bridge now prints UTF-8 whatever the locale
  says); the console's double of the gateway's `activity` takes the new `ended` argument. Nothing the console shows
  changed: the Monitor's drawing of the flow is step 6.

## Left for later

- The three measurements above.
- **The sandbox image made again**, so the workspaces' containers get the bridge of this plan (a step's `error_name`;
  a `todowrite` call's `todos`; its output in UTF-8) as well as plan s14's: until a workspace is reopened (F6: `x`,
  then `o`), its old bridge gives no error names, so a step the owner stopped reads as one that failed (left the
  context), and a todo list longer than the bridge's cut is read only from the live `todo.updated` lines.
- **The gateway started again from this code** (the owner's release, then its update): until then, the running gateway
  gives no `calls`, no `ended` and no `time` for a request in flight, so no request is paired with a step at all.

## For step 6

- **An idle session has no flow after the service starts again.** The bridge's watch, when it opens a server's
  stream, says only the sessions busy or retrying, and a flow is made when a line names its session; so until
  something happens in it, an idle session's flow is not kept, and `GET /agents/flow/{workspace}/{session}` answers
  404. The Monitor's list of sessions (step 6) reads OpenCode's own list through the bridge; a session it shows that
  has no flow is to be made and read from its history then (design 0012 §6.1: flows rebuilt from the history when the
  service starts again).

## Claude's calls (2026-10-19)

1. **A package of its own in the agents component**, `sessionflow/`, since design 0013's flows of boxes take the name
   `flows` (`clank/components/flows/`); its docstrings say which flow is meant.
2. **The view is built when it is read after a change**, not at every line: a burst costs one build, and the version
   moves once per build that changed something (design 0012 §2: no stutter).
3. **The gateway gives a session's requests that ended** (`ended`, up to 64, numbers only, no text), so pairing never
   depends on asking at the right moment; the records are never read for it (decision 0049).
4. **Pairing**: call ids first, then order by time with `SKEW` of 2 s; recorded as a decision, since the measurement
   of KVMem's ids is pending.
5. **A step's place in or out of the context** follows OpenCode's own rule (an error leaves it out, except a stop with
   content), and a stop is told by the error's name, which the bridge now keeps.
6. **A note** is the owner's message heard while the session was busy (from history: sent while a step of the session
   was under way); it is read by the first step that began after it, whatever message that step answers (revised
   after review: it was the step whose parent it is, which left the earlier of two notes unread).
7. **A plan's branch for each step** is worked out from the ticks the implementer's edits made, so steps read from the
   history join their items as well as steps seen live.
8. **The bridge prints UTF-8** whatever the locale says: the service reads UTF-8, and a Windows test found a text cut
   with "…" written in the console's code page.
9. **A session deleted in OpenCode leaves the flows kept**, and a client asking for it is told there is none (404).
10. **A reading that failed is tried again** after 2 s, doubled each time up to a minute: soon enough for the owner, and
    a container that stays down costs one `docker exec` a minute per flow waiting; once its server is gone, the flow
    waits for its watcher or its session to be heard again. A round reads eight flows at most.
11. **A subagent node's id is its call's and its session's** (its session's alone while no call is known), not one node
    per session listing its calls: each `task` call gives back something of its own, a branch of its own.
