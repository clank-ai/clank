# The Monitor, step 2: session facts in the gateway: implementation plan

> At the owner's request (2026-10-18, design 0012 approved: "Approve all three"; 2026-10-19: the new menu, the Monitor
> and flows built "as quickly as possible"). As for the earlier plans, the files, interfaces and tests by name and
> intent; the code is in the commits.

**Goal:** design 0012 §11 step 2: the gateway names each model request's session and its parent (OpenCode's headers)
in its activity and in its records' summary; counts the tokens it streams by kind (thinking, answer, tool calls); shows
the loop guard's newest share for each part it reads; and gives the activity and the live text of one session, so the
Monitor's panels follow the session the page shows.

**Architecture:** One small module, `clank/components/gateway/sessions.py`, reads a request's session and parent from
the headers the gateway already keeps with every record (`x-session-id`, `x-parent-session-id`, in any case). The
activity (`activity.py`) keeps, for each request in flight, its session, its counts by kind and its loop guard, and
for each of the newest sessions (and apart from them, of the newest subagents) the last request that ended with its
text; `now` and `live` take a session and then give only that session's own requests and its own last, and with
`subagents` those of the subagents it started too. The records' summary (`records.py`) reads the same headers, so
records kept before this step show their sessions too. The gateway's `GET /activity` and `GET /activity/live`, and the
service's `GET /gateway/activity` and `GET /gateway/live`, take `session` and `subagents`.

**Tech stack:** Python 3.12, FastAPI, pytest with the repository's fake engine (`tests/fakes/engine.py`).

**Spec:** [design 0012](../design/0012-the-monitor.md) §3 (which session), §5.2 (thinking and the answer against
their budgets), §5.4 (the loop guard), §7 (the live text), §11 step 2; decisions
[0048](../decisions/0048-the-monitor-follows-the-newest-session-of-its-folder.md) and
[0049](../decisions/0049-a-sessions-flow-is-built-in-the-service.md); the loop guard's
[decision 0040](../decisions/0040-the-gateway-stops-an-answer-that-repeats-itself.md).

## Global Constraints

- No new dependency. Tests first, each named as a sentence, each file's docstring naming the design sections it
  verifies. Tests use the fake engine and temporary homes only: no GPU, no real model, no container, and never the
  owner's gateway (18210) or service (7720).
- A request that names no session works as before, its session and parent `""`; nothing the gateway sends on to the
  engine changes (the gateway never edits what OpenCode sends, decision 0056).
- Everything in the activity runs on the gateway's event loop, so nothing is locked; what it keeps is bounded (the
  last text of the newest `SESSIONS_KEPT` sessions and of as many subagents, each up to `LIVE_CHARS` characters).
- Every field added to an answer is added, never renamed, so the console's Home, its machine column and its Requests
  page read the activity as before.
- The owner is the sole author of every commit (no trailer); American English.

## Measurements before this step (pending)

Design 0012 §10 lists three before step 2. None could run then: each needs the owner's gateway, a workspace's
container or the real model, which a GPU benchmark used then. The code below does not wait for them; each is
written here as pending, and what it would change.

- [ ] **Decoding speed with the page on screen**, against the page off (§2's pass mark, 95%): needs step 1's page and,
  after the fake engine, the real model. If it fails, the page takes §2's fallbacks; nothing in this step changes.
- [ ] **OpenCode 1.19.0 sends `X-Session-Id` and `x-parent-session-id` on the wire** (read in its
  `session/llm/request.ts`, not yet seen): one synthetic session in a workspace, its records read for the two headers
  (`clank` reads its own summary: `GET /gateway/requests`, each row's `session` and `parent`). If the names differ,
  only `sessions.py`'s two names change.
- [ ] **Whether one streamed event carries several tokens with MTP drafting**: one answer's events counted against
  its `completion_tokens`. If they do, the live counts stay "about" and are corrected at the answer's end (step 7), as
  §5.2 says already.

## Tasks

### Task 1: A request's session and its parent

- [x] **Files:** create `clank/components/gateway/sessions.py`; change `activity.py` (`_flying`, `_ended`),
  `records.py` (`summary`); the tests' expected activity in `tests/components/gateway/test_activity.py`.
- [x] **Interfaces:** `session_of(headers: Mapping[str, Any] | None) -> tuple[str, str]`: the session and the parent
  a request named (`""` when it named none), its headers' names in any case, the values stripped. Each request in
  flight and the last that ended (`GET /activity`) gain `session` and `parent`; a record in brief
  (`GET /gateway/requests`, and `find`) gains them too.
- [x] **Tests:** `tests/components/gateway/test_session_facts.py` (design 0012 §3, §11 step 2):
  `test_a_session_and_its_parent_are_read_from_opencodes_headers_in_any_case`;
  `test_a_request_with_a_session_id_shows_its_session_in_flight_when_it_ended_and_in_its_record` (through the gateway
  and the fake engine: `GET /activity` mid-stream and after, and `recent` over the records);
  `test_a_subagents_request_shows_its_parent`;
  `test_a_request_without_the_header_still_works_and_names_no_session`;
  `tests/components/gateway/test_recent_requests.py`: `test_a_record_in_brief_names_its_session_and_its_parent`.

### Task 2: Live counts by kind

- [x] **Files:** `server.py` (`_read_event` returns the kinds an event carried; `_relay` counts each), `activity.py`
  (`token(record, kind)`; `_flying` and `_ended` gain `counts`).
- [x] **Interfaces:** `Activity.token(record, kind)`, `kind` one of `thinking`, `answer`, `tool` (the live text's
  kinds); a request in flight and the last that ended carry `counts: {"thinking": n, "answer": n, "tool": n}`, one token
  for each kind a streamed event carried, and `tokens`, their sum while in flight (the engine's own count wins once it
  ended, as before).
- [x] **Tests:** `test_activity.py`: `test_the_tokens_of_a_request_in_flight_are_counted_by_kind_and_add_up`;
  `test_session_facts.py`: `test_the_gateway_counts_a_streamed_answers_thinking_and_its_text_apart` (the fake engine's
  `--fake-loop-after 5 --fake-loop-in thinking`, 12 tokens: 5 of the answer, 7 of thinking).

### Task 3: The loop guard's newest share per part

- [x] **Files:** `loops.py` (`LoopGuard` keeps each part's newest reading: `newest()`), `activity.py`
  (`guard(record, guard)`; `_flying` gains `loop_guard`, `_ended` gains `looped`), `server.py` (the request's guard
  given to the activity).
- [x] **Interfaces:** `LoopGuard.newest() -> list[dict]`: each part fed so far, in the order first fed: `part`
  (`thinking`, `answer`, `tool <index>`), `name` (a tool call's, else `""`), `share` (the lowest of its newest
  reading, rounded to three places) and `stretch` (the characters it was read over), both `None` while the part is
  not yet as long as its shortest stretch (after review: first only parts with a share were listed). A request in flight carries
  `loop_guard: {"ratio": 0.06, "parts": [...]}`, or `None` when no guard reads it (the guard is off, or the answer is
  not streamed); the last that ended carries `looped` (what repeated, else `""`).
- [x] **Tests:** `test_loops.py`: `test_the_guard_keeps_each_parts_newest_share_and_its_stretch`;
  `test_activity.py`: `test_a_request_in_flight_shows_its_loop_guards_shares_against_its_ratio` (and `None` without
  one; `looped` in the last); `test_session_facts.py`:
  `test_the_gateway_shows_the_loop_guards_newest_share_of_a_streamed_answer` (stretches of 256 characters).

### Task 4: One session's activity and live text

- [x] **Files:** `activity.py` (`now(session)`, `live(after, id, session)`; the last that ended of each of the newest
  `SESSIONS_KEPT` sessions, with its text), `server.py` (`GET /activity?session=`, `GET /activity/live?session=`),
  `service.py` and `api.py` (`GET /gateway/activity?session=`, `GET /gateway/live?session=`); the Requests page's test
  double (`tests/console/test_requests_page.py`) takes `session`.
- [x] **Interfaces:** with `session`, `now` gives the requests in flight of that session, and `last` is its own last
  that ended (else `None`); with `subagents` too, those of the subagents it started (their parent is that session) and
  the last of them all. `served` stays the gateway's. `live(after, id, session, subagents)` follows the newest of them
  in flight, else the last of them that ended, and never a named request of another session; `newest` names the newest
  of them. Without `session`, both answer as before. (After review: first a session's subagents were always included.)
- [x] **Tests:** `test_activity.py`:
  `test_the_live_text_of_one_session_follows_its_own_requests_its_subagents_when_asked_and_never_anothers`;
  `test_each_of_the_newest_sessions_keeps_its_last_request_after_another_session_ends_one`;
  `test_a_sessions_subagents_never_push_its_own_last_out`;
  `test_the_activity_of_one_session_gives_its_own_requests_and_its_own_last_and_its_subagents_when_asked`;
  `test_session_facts.py`:
  `test_the_live_view_of_the_gateway_follows_the_session_it_is_asked_for` (two sessions streaming at once);
  `test_service.py`: `test_the_services_activity_and_live_text_follow_one_session` (the route, through `Gateway`, to
  a gateway served in the test).

### Task 5: Documents

- [x] Design 0012: §3, §5.2 and §7 say what the gateway shows now; §11 step 2 marked built with this plan. The
  roadmap's M5 row, the design index, the glossary (**Subagent**), this plan's checkboxes and the plans' index; the
  generated files regenerated (`uv run python -m tools.check --fix`).

### Task 6: After review

- [x] **A session's own last.** The review found that a subagent's request that ended after its parent's became the
  parent's `last`, and the parent's own last (its prompt size, its text) could no longer be reached; parallel
  subagents could also push the parent's entry out of the sessions kept. Now a session's view is its own, its
  subagents' only with `subagents` (on the four routes too), and subagents' lasts are kept apart from root sessions'.
  Tests above (Task 4), and `test_service.py`'s route test asks with and without `subagents`.
- [x] **The loop guard lists every part fed** (Task 3's interface): `test_loops.py`:
  `test_a_part_fed_first_but_not_yet_as_long_as_its_shortest_stretch_is_listed_first_without_a_share`.
- [x] **A tool call counted as `tool` at the gateway:** `test_session_facts.py`:
  `test_the_gateway_counts_a_streamed_tool_calls_tokens_as_tool_while_it_streams_and_at_its_end` (the fake engine's
  `--fake-loop-in tool`).
- [x] **Documents:** design 0012 §3, §5.2 and §7 marked revised 2026-10-19, with a line in its revision log; the
  glossary's **Subagent** points at the revised §3.

- Built 2026-10-19, in six commits after this plan's (one per task, and a tidy), then the review's fixes (Task 6) in
  four more. Found on the way: the loop guard reads a part every 128 characters,
  so a test that feeds it must cross that step to see a new reading; the principles page is shorter than 8,000
  characters, so the guard's test of the long stretch reads the glossary's prose. The console's test doubles of the
  service's `live` and `activity` take the new `session` argument; nothing the console shows changed (the Monitor's
  page is step 1's, its panels steps 3 to 7).

## Claude's calls (2026-10-19)

- **The session is read from the headers each record keeps**, not written as a field of its own: one source, and the
  records kept before this step show their sessions too.
- **A session's view is its own; its subagents' requests come only when asked** (`subagents=true`; revised after
  review). A session's panels show its own (§3: a subagent's only after Enter on it; §5.3: the previous step's prompt),
  so its last is always its own. While a subagent works, its parent waits on its `task` call and makes no request, so
  a page that wants the subagent's text then asks with `subagents`; each request says its own session and parent, so
  the page can tell them apart. A subagent of a subagent comes under its own parent only, since a request names only
  its direct parent.
- **One token for each kind an event carries**, and the total their sum: the engines Clank runs send one kind per
  event, so the total is as before; the counts are "about" (§5.2) and the engine's own count wins at the end.
- **The guard's share per part is the lowest of its newest reading**: of the stretches read at once (2,000 and 8,000
  characters for the thinking and the text), the one nearest the ratio, with its stretch; a part not yet as long as
  its shortest stretch is listed with no share (`None`), and the page says "watching".
- **`SESSIONS_KEPT` is 8**: the last text of the eight newest sessions, and apart from them of the eight newest
  subagents (so a session's subagents never push its own out), each up to `LIVE_CHARS`; a request without a session is
  kept only as the gateway's last, as before.
