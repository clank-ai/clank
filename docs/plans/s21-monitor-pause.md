# The Monitor, step 11: Pause, the gateway's hold: implementation plan

> At the owner's request (2026-10-18, design 0012 approved: "Approve all three"; 2026-10-19: the new menu, the Monitor
> and flows built "as quickly as possible"). As for the earlier plans, the files, interfaces and tests by name and
> intent; the code is in the commits.

**Goal:** design 0012 §11 step 11 (§9.4, decision 0055): **pause after this step**. The gateway holds a paused
session's next model request, and its subagents': it answers at once (200, an event stream) and sends a comment line
well within every 300 s, until the owner resumes; then the request goes to the engine on the same stream. A note while
held closes the held request (an empty step) and the pause stays; an error after resuming is worded on purpose, to be
retried or not. The service pauses and resumes a session's root (the Guide's `p`, and a Watch for rule set to pause),
each an `agents.acted` event, and the session's flow shows the hold as a band on its main line, "⏸ held by you 12:22
to 12:25".

**Architecture:**

- `clank/components/gateway/holds.py` (new): `Holds`, kept by the gateway process on its event loop: the paused
  sessions (`Pause`: when, by whom), the requests held, and each session's parent as the requests named it, so a
  subagent at any depth is held with its root. `take(id, session, parent)` registers a request it holds; `keep(held)`
  yields a comment line at once and then one every `keep_seconds` (15) until the pause ends, and raises `Released` when
  a note closed it (`wait(held)` is the same without a word, for a request not streamed); the wait is given (`wait=`),
  so the tests run it on a fake clock. Pauses outlive a gateway restart (`state/holds.json`); requests held do not.
- `server.py`: a request is held at the gateway's door, once it is read and before its slot is woken or waited for (a
  title the gateway answers itself is never held). A streamed one gets its 200 and its comment lines from `hold`; once
  resumed, the rest of the request (`answer`'s routing and relay) runs as before, under the same keep-alive while it
  waits for the slot; a refusal or the engine's own error then becomes an error event, worded to be retried or not
  (`worded`). One not streamed waits without headers. The activity shows a held request (`phase` "held: its session
  is paused", `held`), and the gateway's `GET /holds`, `PUT /holds/{session}`, `DELETE /holds/{session}` and
  `POST /holds/{session}/release` take only the service's local token (decision 0084).
- The service's gateway part (`service.py`, `api.py`): `pause`, `resume`, `release`, `holds`; `GET /gateway/holds`.
- The agents component: `clank/components/agents/pausing.py` (new): `Pausing.pause(workspace, session, *, actor)` and
  `resume`, on the session's root (the flows' heads name each parent), each an `agents.acted` event (`pause`,
  `resume`); `state` (pausing after this step, held with its timer, resumed) and `action` (the Guide's `p` in the shape
  of its other actions: key, whether it can run and why not, what it does, its exact call, its cost, its state). A
  message sent to a session (`Sessions.send`) closes its held request after the bridge sent it. Watch for's pause goes
  through `Pausing` as the rule. Routes: `GET`, `POST /agents/guide/{workspace}/{session}/pause` and `.../resume`.
- The flow (`sessionflow/flow.py`): a request the gateway held becomes a `hold` node on the main line, before the step
  it answered; the renderer (`flowtree.py`) draws it "⏸ held by you 12:22 to 12:25", or "⏸ held by you since 12:22".

**Tech stack:** Python 3.12, anyio, FastAPI, pytest with the repository's fake engine (`tests/fakes/engine.py`), the
session-flow lines (`tests/support/flowlines.py`) and the fake bridge.

**Spec:** [design 0012](../design/0012-the-monitor.md) §9.1, §9.4, §3 (the Guide acts on the root session) and §11
step 11; [decision 0055](../decisions/0055-pause-is-the-gateway-holding-the-next-request.md) (the hold),
[decision 0040](../decisions/0040-the-gateway-stops-an-answer-that-repeats-itself.md) (the words OpenCode retries by),
[decision 0053](../decisions/0053-watch-for-rules-run-in-the-service.md) and
[decision 0082](../decisions/0082-a-watch-for-action-that-cannot-run-tells-the-phone.md) (a rule's pause).

## Global Constraints

- Nothing here runs OpenCode, a container, Docker or a model; never the owner's gateway (18210) or service (7720).
  The hold is tested through a gateway served in the test with the fake engine, its keep-alive on a fake clock.
- No new dependency. Tests first, named as sentences; each test file's docstring names the design sections.
- A request of a session that is not paused goes exactly as before: nothing the gateway sends on changes (decision
  0056), and the routes, records and activity only gain fields.
- The gateway's control routes take the local token; the agent, which reaches the gateway through the edge, never
  can pause or resume (decision 0084).
- The owner is the sole author of every commit (no trailer); nothing is pushed from this lane.

## Measurements of §10 for this step (pending)

Design 0012 §10 lists one before step 11; it needs OpenCode and a model, which a GPU benchmark used then. Two more
belong with it. Until they are made, the hold's words say what is measured and what is not.

- [ ] **A hold past 300 s, and for an hour** (§9.4): one synthetic session paused under OpenCode 1.19.0, its held
  request kept alive by the comment lines; OpenCode must not give up and ask again. If it does, the pause still holds
  (OpenCode's next asking is held again), and the fallback of decision 0055 (a stop at the step's end) is built.
- [ ] **That OpenCode drops the empty step a note's release ends, and reads the note next** (§9.4: "the order is
  measured with the hold"): the note sent first, then the hold closed; the next request carries the note and is held.
- [ ] **What OpenCode does with each error event after a resume**: one worded to be retried is retried; one worded
  not to be is not, and the run ends.

## Tasks

### Task 1: The holds

- [x] **Files:** create `clank/components/gateway/holds.py`; create `tests/components/gateway/test_holds.py`.
- [x] **Interfaces:** `Holds(keep_seconds=KEEP_SECONDS, wait=..., clock=None, file=None)`; `seen(session, parent)`;
  `holding(session, parent) -> str` (the paused session that holds such a request: its own, else its parent's, up the
  parents the requests named; "" when none); `pause(session, by) -> dict`; `resume(session) -> dict | None`;
  `release(session, before="") -> int` (the requests of the session itself closed, those held before `before` when it
  is given: task 9); `view() -> list[dict]` (each pause: session, since, by, its requests held with their seconds);
  `take(id, session, parent) -> Held | None`; `keep(held)`, an async iterator of comment lines that ends when the
  pause ends and raises `Released` when a note closed it; `wait(held)`, the same without a word; `drop(held)`.
- [x] **Tests:** `test_a_paused_session_holds_its_own_requests_and_its_subagents_at_any_depth`;
  `test_a_held_request_gets_a_comment_line_at_once_and_one_within_every_keep_alive_until_resumed` (a fake clock: every
  wait asked is at most `keep_seconds`, well under OpenCode's 300 s);
  `test_a_release_closes_only_the_requests_of_the_session_itself_and_the_pause_stays`;
  `test_pausing_twice_keeps_the_first_pause_and_resuming_one_not_paused_says_so`;
  `test_pauses_are_kept_in_their_file_and_read_again_at_the_next_start`.

### Task 2: A held request through the gateway

- [x] **Files:** `server.py` (the hold at the door; `create_gateway(..., holds=None, token=None)`; the control routes;
  `main` reads the local token and the pauses' file), `activity.py` (a held request's phase and `held`; `held` kept by a
  request that ended), `records.py` (`held` in brief); `tests/components/gateway/test_hold_gateway.py`.
- [x] **Interfaces:** `GET /holds`; `PUT /holds/{session}` (`{"by": ...}`); `DELETE /holds/{session}`;
  `POST /holds/{session}/release` (`{"before": ...}`, task 9); all behind `Authorization: Bearer <local token>` (401
  without it, 503 when the gateway was given none). A request in flight carries `held: {session, since, by}` while
  held; one that ended keeps `held: {session, since, until, by, how, seconds}` (`how`: resumed, released, or left).
- [x] **Tests:** `test_a_held_request_gets_its_headers_at_once_and_comment_lines_while_held_and_reaches_no_engine`;
  `test_resuming_forwards_the_held_request_on_the_same_stream`;
  `test_a_held_request_shows_as_held_in_the_activity_and_its_record_keeps_the_hold`;
  `test_a_request_of_a_session_not_paused_is_not_held`;
  `test_the_holds_routes_refuse_a_caller_without_the_services_token`.

### Task 3: Subagents, a note, a request not streamed, a client that leaves

- [x] **Files:** `server.py`; `tests/components/gateway/test_hold_gateway.py`.
- [x] **Tests:** `test_a_subagent_is_held_with_its_parent`;
  `test_a_note_closes_the_hold_with_an_empty_step_and_the_next_request_is_held_again`;
  `test_a_request_not_streamed_is_held_without_headers_until_resumed`;
  `test_a_held_request_whose_client_left_is_forgotten_and_reaches_no_engine`.

### Task 4: Errors after resuming, worded on purpose

- [x] **Files:** `server.py` (`worded`; the slot's wait under the keep-alive); `tests/components/gateway/test_holds.py`,
  `test_hold_gateway.py`.
- [x] **Interfaces:** `worded(message, retried) -> bytes`: an error event; retried, its words hold "unavailable" (a word
  OpenCode retries by, decision 0040); not retried, none of OpenCode's retry words or numbers.
- [x] **Tests:** `test_words_not_to_be_retried_hold_none_of_opencodes_retry_words`;
  `test_a_slot_that_is_not_served_after_resuming_is_an_error_event_worded_to_be_retried`;
  `test_an_engines_own_refusal_after_resuming_is_worded_so_opencode_does_not_retry_it`;
  `test_the_wait_for_a_starting_slot_after_resuming_keeps_the_comment_lines`.

### Task 5: The service pauses a session's root

- [x] **Files:** `clank/components/gateway/service.py` (`pause`, `resume`, `release`, `holds`), `api.py`
  (`GET /gateway/holds`); create `clank/components/agents/pausing.py`; `agents/service.py` (`Agents.pausing`; the
  marks' pause), `agents/sessions.py` (`send` closes the session's hold; `acted` for pause and resume),
  `agents/api.py` (the routes), `watchfor/marks.py` (its docstring); `tests/components/gateway/test_service.py`,
  `tests/components/agents/test_pausing.py` (a rule's pause is tested there; `test_watch_for_marks.py` was not
  changed).
- [x] **Interfaces:** `Gateway.pause(session, by)`, `resume(session)`, `release(session, before)` (task 9), `holds()`;
  `Pausing.pause(workspace, session, *, actor)`, `resume(...)`, `state(workspace, session)`, `action(workspace,
  session)`; `GET /agents/guide/{workspace}/{session}/pause`, `POST .../pause`, `POST .../resume`.
- [x] **Tests:** `test_the_service_pauses_and_resumes_a_session_in_the_gateway_with_its_token`;
  `test_pausing_a_subagent_pauses_its_root_and_leaves_an_agents_acted_event`;
  `test_the_pauses_state_is_pausing_after_this_step_then_held_with_its_timer_then_resumed`;
  `test_the_pause_action_says_its_key_what_it_does_its_exact_call_and_its_cost`;
  `test_a_message_sent_to_a_paused_session_closes_its_held_request`;
  `test_a_rule_set_to_pause_pauses_the_session_through_the_gateway`;
  `test_the_routes_pause_and_resume_and_refuse_with_the_reason`.

### Task 6: The hold in the flow

- [x] **Files:** `sessionflow/flow.py` (a step's request keeps the gateway's `held`), `sessionflow/kept.py` (a session
  whose request is held is asked of the gateway each round: no line comes while it is held), `console/flowtree.py` (a
  `hold` node on the step's line, before its work; its times in the console's zone, which `flowchart.render` and the
  Flow panel pass on), the style's mark `held` (⏸, `clank/kernel/console_kinds.py`);
  `tests/components/agents/test_session_flow_pairing.py`, `test_session_flows_kept.py`, `test_flow_tree.py`.
- [x] **Tests:** `test_a_step_whose_request_the_gateway_held_carries_its_hold`;
  `test_a_session_whose_request_the_gateway_holds_is_asked_again_each_round_until_it_goes_on`;
  `test_a_hold_is_drawn_held_by_you_from_when_to_when`. (After the plan: the hold rides on its step's request, not a
  node of the flow's own, so the flow's pairing places it and its step's branch holds it.)

### Task 7: Into the Guide

Step 9 (the Guide's Stop, Note and Compact now, `guide.py`, its panel and its keys, plan s19) was built beside this step
then and reached main after task 6; this lane was rebased on it, and the pause joined the Guide as a task of its own.

- [x] **Files:** `clank/components/agents/guide.py` (`Guide(..., pausing)`, whose `offer` lists the pause after Compact
  now; `Ruled.pause` pauses through it, as the rule), `pausing.py` (the action's `brief` and `paused`; the title
  "Pause", as the panel's column takes it; `RulePause` gone, `Ruled` does it), `agents/service.py`;
  `console/guidepanel.py` (`p` among the keys; the pause's states, held with its timer), `console/monitor.py` (`p` on
  the Session view: the window that says what it does, its call and its cost, then pause or resume); the Monitor's
  frames written again (the keys bar's `p pause`, the Guide panel's fourth line); `tests/components/agents/
  test_pausing.py`, `test_guide_actions.py` (the routes' keys), `tests/console/test_monitor_guide.py`.
- [x] **Tests:** `test_the_guide_offers_the_pause_after_compact_now`;
  `test_a_rule_set_to_pause_pauses_the_session_through_the_gateway` (its note through the Guide, its pause through the
  gateway); `test_the_panel_lists_the_pause_with_its_state_and_its_timer`;
  `test_p_pauses_the_session_once_confirmed_and_p_again_resumes_it`.

### Task 8: The documents

- [x] Decision 0084 (the gateway's holds are the service's, behind its local token) and its index line; design 0012
  §11 step 11 marked built with this plan, §9.4 revised for what it decides beyond the design (marked as such, with a
  line in its revision log); the roadmap, the design index, the glossary (**Hold**, **Guide**); this plan's ticks and
  the plans' index; the generated files (`uv run python -m tools.check --fix`).

### Task 9: The review's fixes

The review of this step found two faults and five smaller points; each fault was fixed test first.

- [x] **A note's release closes only what was held before the note was sent.** `Sessions.send` reads the clock before
  the bridge sends the message, and the gateway closes only the session's requests held before then
  (`Holds.release(session, before)`, `POST /holds/{session}/release {"before": ...}`, `Gateway.release(session,
  before)`). Before, it closed every request held, the one that carries the message too when the session was paused
  while idle, stopped while held, or its step ended while the message was sent: that request ended as an empty step,
  and OpenCode ended the run with the message unanswered. Tests:
  `test_a_release_never_closes_a_request_held_after_the_message_was_sent`,
  `test_a_release_leaves_held_a_request_that_came_after_the_time_it_names`,
  `test_a_messages_release_closes_only_what_was_held_before_the_message_was_sent`.
- [x] **A gateway from before pausing is never taken for one that paused.** The service adopts the gateway that runs,
  so right after an update the gateway may be an older build without `/holds`; its FastAPI 404 was read as success
  (a pause recorded, nothing held). Now only the gateway's own `not_paused` answers a resume with "not paused"; any
  other 404 is a `HoldError` that says to restart it (`clank gateway restart`). Test:
  `test_a_gateway_from_before_pausing_is_never_taken_for_one_that_paused`.
- [x] **A hold a note closed stays in the flow.** The activity keeps a released request among its session's requests
  that ended (never counted, never the session's last; sessions with only such requests bounded), pairing places it
  only on an empty step of its own (never as the step before's answer when OpenCode kept no such step), and the flow
  draws it "held by you 12:22 to 12:25, until a note". Tests:
  `test_a_request_a_note_released_stays_among_its_sessions_ended_but_is_never_counted_nor_its_last`,
  `test_a_request_a_note_released_pairs_with_its_own_empty_step_and_never_takes_the_step_befores_place`,
  `test_a_hold_a_note_closed_is_drawn_until_the_note`, and the note's test through the gateway.
- [x] The Guide's console test names §9.4 in its docstring (the tests page lists it under §9.4); the route
  `GET /agents/guide/{workspace}/{session}` names the pause and its call to the gateway (the API page written again);
  this plan's interfaces say the names as built (`clock=`, `take`, `keep`, `wait`, `seconds`).
- Tasks 3 and 4's tests came after their code (below, in Progress): disclosed, not redone; later steps keep tests
  first.

## Progress

- Built 2026-10-20 in nine commits after this plan's. Tasks 3 and 4 have no code of their own: a held request's path
  is one function of the gateway's (`held_stream`), written whole in task 2, so their tests came after it; each was
  checked failing for the right reason by breaking the code it tests (no parent walked, no wait for a request not
  streamed, every error worded to be retried, no keep-alive while the slot starts), then passing again.
- Step 9 (plan s19) reached main after task 6. This lane was rebased on it (the plans' index, the activity's test, the
  agents service's construction, `send`'s return and the marks' docstring met step 9's changes; the generated pages were
  written again), and task 7 joined the pause to its Guide.
- The Monitor's frames were written again for task 7, each difference read: the keys bar gains `p pause`; the Guide panel
  gains a fourth line, and since the pause's reason (the test's gateway does not run) is not the others', each action
  now says its own reason on its line, where the three shared one before.
- `uv run python -m tools.check --fix` (12 minutes on this busy machine) regenerated nothing more and passed every
  check but one test of the folder page (`test_r_switches_the_agents_changes_between_review_and_auto`), whose message
  line was empty once under the run's load; it passes alone and with its file, twice, and touches nothing this step
  changed.
- Measurements: the three above wait for the owner; nothing here ran OpenCode, a container or a model.
- The review's fixes (task 9): each new test failed first for the reason it names, then passed; ruff, mypy as on
  Windows and as on Linux, and the gateway's, the agents', the Monitor console's and the repository's tests pass.

## Claude's calls (2026-10-20)

1. **The pause is set in the gateway, behind the service's local token** (decision 0084): the gateway owns it, as
   decision 0055 says, and its control routes take the token the service's clients prove themselves with, which the
   agent in a container never has (it reaches the gateway through the edge). Following the pauses with the routes every
   second was the other way: no new route, but a pause up to a second late, and a service that started again would
   have resumed every pause.
2. **Held at the door**: after the request is read and its title answered (a title reaches no engine), before the
   slot is woken or waited for, so a held request never wakes the vision model nor waits on a slot.
3. **Subagents at any depth**: a request names only its direct parent, so the gateway keeps each session's parent from
   the requests it saw (the newest `PARENTS_KEPT`), and a pause on the root holds a subagent's subagent too.
4. **A note releases only the session's own held request**, never a subagent's: an empty step ends a subagent's run,
   which would hand its parent an empty answer. The note is sent first and the hold closed after, so OpenCode finds a
   newer message of the owner when the empty step ends and goes on; any message sent through Clank (the Guide's note,
   the phone's, the console's) does this, since each is a note to a held session.
5. **A request not streamed is held without headers**, since a JSON answer has no comment line; if its client gives
   up, its next asking is held again (decision 0055). OpenCode streams its steps.
6. **A client that leaves while held** is forgotten, as one that left before its answer began is today: not counted,
   not recorded.
7. **Errors after resuming are worded as the same failure would be answered without the hold**: one the gateway answers
   with a 5xx or 429 status (no engine, its engine not answering, the engine's own 5xx) holds "unavailable", so OpenCode
   retries it as it would that status; the engine's own 4xx passes in its words, with OpenCode's retry words and numbers
   taken out, so the run ends as it would have.
8. **Pauses outlive a gateway restart** (`state/holds.json`), since a pause the owner set ends only when the owner
   resumes (decision 0055's choice); the requests held do not (a restart cuts every request in flight), and OpenCode's
   next asking is held again.
9. **A keep-alive every 15 seconds**: well within OpenCode's 300 s, a few bytes each.
10. **A note's release closes only the requests held before the note was sent** (task 9): the service reads its clock
    before the bridge sends the message, and the gateway compares that with when each request was held, on the same
    machine's clock. A request held since may carry the note, so it stays held until the owner resumes, as §9.4 says
    the request that carries the note is. One held in the moment between the clock's reading and the message being
    stored, which does not carry the note, also stays held; resumed, it runs its step, and OpenCode then finds the
    owner's newer message and reads it, so the note is late but never lost. Telling requests apart by their content
    (whether one carries the note) was the other way: the gateway would need the note's text and OpenCode's message
    format.
11. **A 404 from the holds is an answer only as the gateway's own `not_paused`** (task 9): every other 404 is a gateway
    from before pausing, and the service says to restart it, never that a pause was set.
12. **A hold a note closed stays in its session's flow** (task 9), on the empty step OpenCode keeps of it, "until a
    note"; if OpenCode keeps no such step (to measure with the hold), it is left out of the flow rather than taking
    the place of the step before's answer.
