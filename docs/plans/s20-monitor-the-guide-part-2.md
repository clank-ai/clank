# The Monitor, step 10: the Guide, part 2 (Drop and Undo): implementation plan

> At the owner's request (2026-10-18, design 0012 approved: "Approve all three"; 2026-10-19: the new menu, the Monitor
> and flows built "as quickly as possible"). As for the earlier plans, the files, interfaces and tests by name and
> intent; the code is in the commits.

**Goal:** design 0012 §11 step 10 (§9.5, §9.7, decision 0056): the Guide's last two actions on the session the Monitor
follows, its root (§3). **Undo the last step** (`u`, §9.5): OpenCode's `revert` at the last part of the step before
it, never a revert by message id alone; for the first step after the owner's message, refused with the reason ("undoing
it would take back your message too") and **undo the turn** offered, a revert at the owner's message whose text comes
back in the note line; a preview of the steps and the files it takes back; `u` again redoes it (`unrevert`) until the
owner's next message, which makes it final. **Drop an item** (`x`, §9.7): OpenCode's own clearing of a finished tool
call's result, the whole part written back with `state.time.compacted` set; refused for an item of the step in
progress; its window says the drop is final. Each says what §9.1 asks: when it can run and, when not, why; its key;
what it does, in words and as the exact call; what it costs; a confirmation; its states; an `agents.acted` event with
who did it; and a mark in the flow afterward ("undone by you", "result cleared by you, −18.6K").

**Architecture:**

- The flow (`clank/components/agents/sessionflow/flow.py`) gives what the Guide reads: each step names the part a
  revert at its end cuts at (`cut`: its last part, when a text or a tool part comes before it, as OpenCode's
  `session/revert.ts` requires to keep the cut inside the step; "" when none does) and the files its patch parts list
  (`files`, what OpenCode's revert restores); the head names the revert pending (`reverted`); the steps a revert undid
  stay in the flow once OpenCode removes them at the next message, `final`; a call whose result the Guide cleared says
  so (`cleared_by`, `freed`: `Flow.cleared`, `SessionFlows.cleared`).
- What the Guide offers (`clank/components/agents/guide.py`, `offer`) gains **Undo** (`u`) and **Drop** (`x`):
  - Undo's `mode`: `step` (a revert at the step before's `cut`; a step before it with no `cut` is taken back with it,
    since a revert there would take back the turn), `turn` (the step follows the owner's message, or a note, in
    OpenCode's order: a revert at the oldest of those messages, which come back as text), or `redo` (a revert is
    pending: `unrevert`); `revert` (the exact message and part), `takes` (the steps, the files, the owner's messages
    and the subagents it takes back); refused while the session works (OpenCode refuses), without a server, with no
    step, and across a compaction.
  - Drop, for an item (`item`, a call's part id): refused for a call not in the session's flow, undone, cleared
    already, not finished, or in the step in progress; its cost, the tokens it frees (the result's characters at the
    model's calibration for tool results, else 0.3 tokens a character, as decision 0087's estimate) and everything after
    it read once (the session's last total less the prompt of the step that first read it). Without an item, what Drop
    does and whether any result can be cleared.
  - Their states, read from the flow: undone (redo until the next message), the turn undone, final, redone; cleared.
- The actions (`Guide.undo`, `Guide.redo`, `Guide.drop`) go through the session bridge (`Sessions.revert`,
  `unrevert`, `clear`, each recorded as `agents.acted`: undo, redo, clear) to the server that runs the session. An
  undo carries the revert the owner confirmed and is refused when the session moved on since; the turn's text is read
  back from the session's newest page of history (`Sessions.page`), else the flow's words of it.
- Routes: `GET /agents/guide/{workspace}/{session}?item=`; `POST .../undo` (`message`, `part`: the revert confirmed),
  `.../redo`, `.../drop` (`part`); a refusal is a 409 in the Guide's words.
- The console: the Guide panel lists Undo (or Undo turn, or Redo) and Drop with their keys and states
  (`guidepanel.py`); on the Session view the page takes `u` (a window with the preview, Enter does it; after the turn
  is undone the note window opens with its text) and `x` (the call highlighted in Tool calls when that panel has the
  focus, else the call under the flow's cursor; its window asks first and says the drop is final); the flow draws a
  result cleared by the owner "result cleared by you, −18.6K", and steps undone "undone by you · u redoes" until final
  (`flowtree.py`).

**Tech stack:** Python 3.12 standard library; FastAPI; Textual; pytest with the fake OpenCode (`tests/fakes/
opencode.py`), the bridge run on this machine, the session-flow lines (`tests/support/flowlines.py`), and the console
driven headless against a service served in the test.

**Spec:** [design 0012](../design/0012-the-monitor.md) §9.1, §9.5, §9.7, §3 and §11 step 10;
[decision 0056](../decisions/0056-undo-takes-back-the-last-step-drop-only-clears.md),
[decision 0079](../decisions/0079-every-action-on-a-session-goes-to-the-server-that-runs-it.md),
[decision 0087](../decisions/0087-a-first-messages-size-is-counted-by-the-engine-else-estimated.md) (the plain estimate
of tokens a character). Read for this step: OpenCode 1.19.0's `packages/opencode/src/session/revert.ts` and
`summary.ts` (2026-10-20). The review (2026-10-20) checked the rules the fake OpenCode now follows (where a revert cuts,
a busy session refused, what the next message removes) by text search of OpenCode 1.18.31's program on this machine,
not of 1.19.0, and recorded nothing: they are confirmed against 1.19.0 with the measurements below.

## Global Constraints

- Nothing here runs OpenCode, a container, Docker or a model: the actions are tested against the fake OpenCode with
  the bridge run on this machine, as step 9's are. The bridge is not changed (its `revert`, `unrevert` and `clear` were
  built in step 4), so no sandbox image needs building again.
- No new dependency. Tests first, named as sentences; each test file's docstring names the design sections.
- Every field added to an answer is added, never renamed.
- The owner is the sole author of every commit (no trailer); nothing is pushed from this lane.

## Measurements of §10 for this step (pending)

- [ ] **Confirm the revert's rules against OpenCode 1.19.0 in the sandbox** (the fake OpenCode's, read in 1.18.31): a
  revert at a part with no text or tool part before it in its message reverts from the owner's last message; a busy
  session refuses a revert and an unrevert; the owner's next message keeps the cut message, removing its parts from the
  cut part on, and removes the messages after it.
- [ ] **That undo takes back exactly one step, files included** (§9.5), under OpenCode 1.19.0, a `bash` call's changes
  too: a step that edits a file and one that runs a command that writes one, each undone, the files compared.
- [ ] **Whether a cleared result can be brought back** (§9.7): the part written back without `compacted`; until it is
  measured the drop's window says the drop is final.
- [ ] **What an undo and a cleared item cost in reading again** (§9.1): the prompt the engine reads after each, against
  the estimates the Guide shows (an undo: nothing expected; a drop: everything after the item, once).
- [ ] **A subagent's changes and an undo** (read in `revert.ts`, to see): a revert restores the patches of the
  session's own messages, so the files a subagent changed in its own session are not taken back; the preview says so.
- [ ] **The step before an undo, once final** (read in `revert.ts`, to see): the revert names that step's last part,
  which OpenCode removes at the next message; its patch part is often that last part, so undoing that step later takes
  back its messages but not its files. The preview lists the files from the parts OpenCode still keeps, so it says
  what will happen.

Until they are made, the costs say they are estimates, to measure.

## Review Focus

1. **The cut**: never a revert by message id alone for a step (OpenCode takes back the turn then); the part named is
   the step before's last part only when a text or a tool part comes before it, the rule `revert.ts` applies.
2. **The owner's messages are never taken back by surprise**: a step that follows one of them (a note included, in
   OpenCode's order) is undone only as the turn, said so, its text given back.
3. **What was confirmed is what is done**: the undo carries the revert the owner saw; the service refuses one the
   session moved on from, and Drop names its item.
4. **Drop never touches the step in progress** (OpenCode's routes do not check), nor a call not finished.
5. **States read from the flow**, never guessed: final only once OpenCode removed the steps; cleared once the part
   says so.

## Tasks

### Task 1: The flow says what Undo and Drop read

- [x] **Files:** `clank/components/agents/sessionflow/flow.py` (a step's `cut` and `files`, the head's `reverted`,
  steps undone kept `final`, `Flow.cleared`), `kept.py` (`SessionFlows.cleared`); `tests/support/flowlines.py`
  (`finish`, `patch`, `removed`, `reverted`: the parts and events these tests need); create
  `tests/components/agents/test_session_flow_undo_and_drop.py`.
- [x] **Interfaces:** a step node's `cut: str`, `files: list[str]`; the head's `reverted: {message, part} | None`; an
  undone node's `final: True` once OpenCode removed it; a call node's `cleared_by: str`, `freed: int | None`;
  `Flow.cleared(part, freed)`, `SessionFlows.cleared(workspace, session, part, freed)`.
- [x] **Tests:** `test_a_step_names_the_part_a_revert_cuts_at_and_the_files_it_changed`;
  `test_steps_undone_stay_in_the_flow_final_once_opencode_removes_them`;
  `test_a_result_the_guide_cleared_is_marked_by_you_with_the_tokens_it_freed`.

### Task 2: What the Guide offers: Undo and Drop

- [x] **Files:** `clank/components/agents/guide.py` (`offer`'s `item`, `_undo`, `_drop`, their states); create
  `tests/components/agents/test_guide_undo_and_drop.py`; `tests/console/test_monitor_guide.py` (its lines gain Undo
  and Drop).
- [x] **Interfaces:** `offer(view, *, port, totals, ended, kept, item="")`; Undo `{..., mode, revert: {message, part},
  takes: {steps, files, said, text, subagents}, refused}`; Drop `{..., item: {message, part, step, tool, title, length,
  freed} | None}`, its cost with `freed`.
- [x] **Tests:** `test_undo_cuts_at_the_previous_steps_last_part_and_previews_its_steps_and_files`;
  `test_a_step_with_nothing_before_its_last_part_is_taken_back_with_the_step_after_it`;
  `test_undo_of_the_first_step_after_your_message_is_refused_and_offers_undo_the_turn`;
  `test_undo_waits_for_the_session_to_stop_and_redo_follows_until_your_next_message`;
  `test_drop_is_refused_for_the_step_in_progress_and_says_what_it_frees_and_costs`;
  `test_undo_and_drop_states_are_read_from_the_flow`.

### Task 3: The actions, against the fake OpenCode

- [x] **Files:** `guide.py` (`Guide.undo`, `Guide.redo`, `Guide.drop`, the turn's text); `clank/components/agents/
  service.py` (the pause listed before Undo); create `tests/components/agents/test_guide_undo_actions.py`.
- [x] **Interfaces:** `Guide.undo(workspace, session, *, actor, message="", part="")`, `Guide.redo(workspace, session,
  *, actor)`, `Guide.drop(workspace, session, part, *, actor)`.
- [x] **Tests:** `test_undo_reverts_at_the_previous_steps_last_part_on_the_server_that_runs_it`;
  `test_undo_the_turn_names_your_message_and_gives_its_text_back`;
  `test_redo_unreverts_and_each_action_leaves_an_agents_acted_event`;
  `test_an_undo_the_session_moved_on_from_is_refused_and_sends_nothing`;
  `test_drop_sends_the_whole_part_with_its_time_compacted_and_the_flow_says_by_you`;
  `test_a_drop_of_the_step_in_progress_sends_nothing_and_says_why`.

### Task 4: The routes

- [x] **Files:** `clank/components/agents/api.py`; `tests/components/agents/test_guide_undo_actions.py`.
- [x] **Tests:** `test_the_routes_offer_undo_and_drop_act_and_refuse_with_the_reason`.

### Task 5: The console: the panel, `u`, `x`, and the marks in the flow

- [x] **Files:** `clank/components/agents/console/guidepanel.py` (Undo, Drop, their states), `monitor.py` (the keys
  `u` and `x`, their windows, the note window after the turn), `flowtree.py` (a result cleared by you, steps undone
  until final); create `tests/console/test_monitor_undo_and_drop.py`; `tests/components/agents/test_flow_tree.py`;
  the Session view's snapshots written again.
- [x] **Tests:** `test_the_panel_lists_undo_and_drop_with_their_keys_and_states`;
  `test_u_asks_first_then_undoes_and_the_turns_text_opens_in_the_note_window`;
  `test_x_drops_the_call_under_the_flows_cursor_once_confirmed`;
  `test_a_result_cleared_by_you_and_steps_undone_for_good_are_drawn_so`; the frames of the Session view with the
  Guide panel.

### Task 6: The documents

- [x] Design 0012's step 10 note, §9.5 and §9.7 as built, its index and revision log; a decision record for the cut
  and the preview; the roadmap; the glossary (the Guide's Undo and Drop); this plan's ticks and Claude's calls,
  `docs/plans/README.md`; the walkthrough's Monitor; the generated pages (`uv run python -m tools.check --fix`).

## Claude's calls (2026-10-20)

1. **Undo is grayed while the session works**, its reason "the session works: stop it first (.)": OpenCode refuses to
   revert a busy session, §9.1's own example of a reason is "Undo stops the session first", and stopping then undoing
   in one key would undo the step the stop just ended, not the one the owner saw.
2. **The preview comes from the flow**, not from `/session/:id/diff`: in OpenCode 1.19.0 that route answers only a
   user message's turn (`summary.ts`), while the revert restores exactly the patch parts after the part it names
   (`revert.ts`), which the flow keeps; so the files listed are the files OpenCode will restore, read without a
   `docker exec`.
3. **A step with no text and no call before its last part is taken back with the step after it**: OpenCode would turn
   a revert at its last part into a revert of the whole turn, the owner's message included; the cut moves to the newest
   earlier step it can name, and the preview lists every step it takes back.
4. **A note counts as the owner's message**: in OpenCode's order a note sent while step n ran comes after step n, so
   undoing step n+1 alone would take the note back too; it is the turn case, said so, the note's text given back.
5. **Undo does not cross a compaction**: a step whose step before is a compaction's message is refused, "undo does not
   take back a compaction", since reverting there would take back the summary the session now stands on.
6. **What was confirmed is what is done**: the console sends the revert it showed; the service refuses one the session
   moved on from ("look again"), so a step that ended between the window and Enter is never undone unseen.
7. **The turn's text is read back from OpenCode** (the session's newest page, ten messages, whole up to the bridge's
   6,000 characters a part), else the flow's words of it, said cut; the console opens the note window with it.
8. **Drop's estimate**: the result's characters at the model's calibration for tool results, else 0.3 tokens a
   character (decision 0087's plain estimate), labeled an estimate; what it costs in reading again, everything after
   the item once: the session's last total less the prompt of the step that first read it, or nothing when no step has
   read it yet.
9. **Steps undone stay in the flow once final**, a folded lane "undone by you", since OpenCode deletes their messages at
   the next message and the flow is the log of the owner's guidance (§9.5); they go with the flow, as everything the
   flow keeps (decision 0049).
10. **The commands of `clank` for the Guide wait**, as for steps 9 and 11: design 0012 §2 asks that every Guide action
    be a command too; they come together, with the phone's Guide.
11. **The flow shows OpenCode's answer at once** (`SessionFlows.reverted`): an undo or a redo sets the session's revert
    pending in its flow from OpenCode's own answer, so the Guide never reads "brought back" in the moment before the
    watch's line about the session comes; an answer that names another message than the one asked is said ("more than
    the preview said; u redoes it"), and one that names none is a failure.
12. **Drop refuses what the model no longer reads**, besides the step in progress (§9.7): a call that failed (it has no
    result), one in a step undone, one in a step that left the context (it ended in an error), and one before a
    compaction that summarized it. Undo also refuses a step whose message before is not in Clank's flow, since it
    could not name where to cut.
13. **The pause is listed before Undo** by the Guide itself (`Guide.offer`), so the panel reads Stop, Note, Compact now,
    Pause, Undo, Drop; `service.py` did not need to change.
14. **The words of every message of the owner's an undo takes back come back whole**: the turn's, and one sent after
    the last step that no step answered yet (the preview says "and your message after it"). Revised after the review
    (its fix 2): not flattened into the note's one-line field, which lost code blocks and indentation, but in a window
    of several lines (the console's `EditScreen`), their line breaks, indentation and each message's text kept,
    messages a blank line apart; Ctrl+S sends them as a note, about nothing, since what they were about is taken back,
    which makes the undo final; Esc keeps them, and `m` opens them again on that session, so no word is lost.
15. **`x` reads Drop for its call before its window opens** (`GET /agents/guide/{workspace}/{session}?item=`), so the
    window says what that call frees and costs, or the message line why it cannot run; its title names the step and
    the tool ("Drop step 18's `bash` result").
16. **"freed about 18.6K"** (revised after the review, its fix 5: the first "-18.6K", an ASCII minus, did not say it
    is an estimate), as the Guide says "frees about"; the undone lane says "u redoes" (not "u redoes it", which pushed
    its calls under it at 88 columns) until final.

## Built (2026-10-20)

Tasks 1 to 6, in six commits on the lane, each test seen failing first. Calls 11 to 16 above are this build's own. Left
for later: the Biggest panel and the Context view marking a cleared item (§9.7), which come with their step 12; undo
back to a step the owner picks (decision 0056's alternative); the `clank` commands for the Guide (call 10). The keys
bar now holds `u undo` and `x drop`, so at 160 columns it gives up `^p palette` first, as its rule says (design 0011).
Decision 0094 records the cut, the preview and the revert confirmed; its number follows 0093, the Flow view's. Built
on main before the Flow view, then rebased onto it: the Session view's keys bar lists `u` and `x`, the Flow view's keep
their own (`VIEW_KEYS`). Drop's plain 0.3 tokens a character is kept in the Guide too, since the agents component does
not use the runtime's (decision 0019); a test holds the two equal. The six measurements above wait for the owner,
with the real model.

**The review's fixes** (2026-10-20, nothing must-fix; each test seen failing first, one commit each): an undo that
names no revert is refused, the field required, never read as what is offered now (fix 3); the undo is confirmed by
what it takes back too, the steps and the owner's messages its window showed, so the same cut taking back more after
a further step is refused (fix 4); the undo answers with OpenCode's cut alone, not its snapshot and text diff (fix 6);
the fake OpenCode reverts as OpenCode's `revert.ts` reads (a cut with nothing OpenCode counts before it becomes the
turn, a busy session refused, the next message's cleanup), read in 1.18.31's program and owed against 1.19.0 above
(fix 7); when OpenCode takes back more than the preview, what it took back is read from the flow, the words of every
message of the owner's in it given back, and the warning shown in a window, `?` saying each action's last state whole
(fix 1); the words come back whole in a window of several lines, kept on Esc (fix 2, call 14); the flow says "freed
about 18.6K" (fix 5, call 16); and `u` and `x` are shown to do nothing of the Guide's on the Flow view (fix 8).
