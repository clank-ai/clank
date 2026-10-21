# Flows, step 6: the Flow view: implementation plan

> At the owner's request (2026-10-19: the new menu, the Monitor and flows built "as quickly as possible", with the
> same care as always); the Flow view is the part of the console the owner wants most. Design 0013's sixth build step,
> after design 0012's page (step 1) and renderer (step 6). As for the earlier plans, the files, interfaces and tests by
> name and intent; the code is in the commits.

**Goal:** [design 0013](../design/0013-flows.md) §12 and §14 step 6: boards D1-D4 in the Monitor's Flow view (F10).
**D1**, a flow running: its boxes and their lines, the box selected with a Live panel for a running one, Models in this
flow, Waiting for you, and under the flow The brief, checked; Deliverables; Ahead; the run log in a window on `h`.
**D2**, a box's settings (`e`): the flow as a list, the box's fields each with its key, a change marked not saved until
`s`. **D3**, a gate (`Enter` on a gate): where the flow is, what it shows, the VERIFY's report, the brief against the
plan, and its answers. **D4**, proposals (`Enter` on DECOMPOSE while they wait): cards side by side in the order they
will run, each with its own accept, edit and reject, the highlighted card's whole prompt below, accept all. `Enter` on
a running box opens the Session view on its session, `Esc` back to the box. Nothing redraws while nothing changes; a
running box redraws at most four times a second. The layout holds at 128 and 88 columns and below 70, over generated
flows of 1 to 12 tasks: no box, line label or legend touches another, every line stays in its panel, and a flow taller
than its panel scrolls.

**Architecture:**

- **What the view shows is made in the service** (`clank/components/flows/view.py`, a pure function, as a session's
  flow is, decision 0049, and the Now panel's facts, plan s17's call 1: the phone can show it later). `view(...)` takes
  the flow, its latest run, the run's batches of proposals, what the main slot runs, the presets' titles, the brief's
  text and which files are in the folder, and gives: the run (its number, status, where it is, what it waits for, when
  it started and ended); every box in the order it runs, proposals waiting joined where they would join
  (`proposals.joined`) and marked proposed, each with its state, its preset, its mode, its tries (when, how each
  ended, its verdict, its deliverables written, its session), its files, who proposed it, whether it asks the owner
  now; the lines of that flow; the waiting batch (each proposal with its settings and the call that proposed it); the
  next flow when there is one; Models in this flow; Waiting for you; The brief, checked (the brief's listed lines and
  every *accept when*, each with the newest verdict's criterion on it); Deliverables (each file with its box, its try
  and whether its check passed); Ahead (each box still to run with its cost: a switch, a fresh prompt, or that it asks
  the owner); and a fingerprint of all of it. `Flows.view(folder, flow)` picks the flow a folder's Monitor shows (the
  one named, else the workspace's active run's, else the one run last, else the first by name) and reads what the
  function needs; `GET /flows/view?folder=&flow=`. The run log (`h`): `GET /flows/{workspace}/{name}/log?run=`, the
  run's events, oldest first.
- **The flow drawn** (`clank/components/agents/console/boxchart.py`, a pure function, as `flowchart.py` lays a
  session's flow out): `render(view, width, selected, live)` lays the boxes out in **stages** along the order they run
  (one box, or a DECOMPOSE's tasks stacked as a fan), the stages left to right in rows that wrap like text, a line from
  each row's last stage down and back to the next row's first; each box a bordered block of its type's color, title,
  model and last result, its border saying its state (solid, heavy in the `now` color while it runs, dashed while it
  waits, in the proposals' color while proposed); a VERIFY's fail line drawn under its row back to the box it checks,
  labeled, or a label alone when that box is not in its row; the next flow a dashed box after the last gate; the legend
  under the flow. A DECOMPOSE and its fan stand in one row. Narrower than `LIST_BELOW` (70) columns the flow is the list
  of board D2's left. `Chart` says what stands where (each box's rectangle, each label's and legend item's cells), the
  boxes in reading order, and each line's key, so a widget redraws only the lines that changed.
- **The console** (`clank/components/agents/console/`): `boxpanel.py`'s `BoxChart` (a widget of lines, as
  `FlowChart`: the arrows move between boxes, `Enter` opens what a box holds); `flowpanels.py` (the words of Selected
  with its Live panel, Models in this flow, Waiting for you, The brief, checked, Deliverables and Ahead, each a
  function of the view and the width, and `LinesView`, a panel's lines drawn again only when they changed);
  `flowboards.py` (boards D2, D3 and D4: their lines, D4's cards); `flowview.py` (`FlowViewer`, the Flow view's part of
  the Monitor: its readings, its ticks, its keys, its boards), so `monitor.py` composes its panels and hands it the
  Flow view's ticks and keys. `following.py` gains `FlowReading` (the view read one reading at a time, None when its
  fingerprint did not change) and `Following.pin` (the Session view pinned to a box's session, its heading naming the
  box). The view is read once a second while the Flow view is on screen, the running box's session's now on every tick
  while it works (as the Session view reads it, plan s17), and nothing while the page is not on screen.

**Tech stack:** Python 3.12, FastAPI, Textual 8.2.8, pytest with the console's text snapshots, synthetic runs written
as the runner writes them, synthetic folders.

**Spec:** [design 0013](../design/0013-flows.md) §3, §8, §9, §10, §12 and §14 step 6, with the revision log's notes on
the Flow view (D4's cards; the layout's edge cases; no run log under the flow); boards
[D1](../design/boards/FlowRun.dc.html), [D2](../design/boards/FlowNode.dc.html), [D3](../design/boards/FlowGate.dc.html)
and [D4](../design/boards/FlowPropose.dc.html); [design 0012](../design/0012-the-monitor.md) §2 (the page, its keys,
its room, its redraws) and §6 (the renderer); [design 0011](../design/0011-the-consoles-look.md) §2 (the style's
`boxes` group, its marks) and §4 (panels); decisions 0044 (no color outside a style), 0045 (nothing spills), 0049 (a
flow made in the service).

## Global Constraints

- Nothing runs OpenCode, a container, Docker, an engine or a model: the service's view is tested on runs written as the
  runner writes them, the console against a service served in the test; nothing opens a window (Clank's VS Code window
  is asked for through its operation, whose launch the test replaces).
- No new dependency. Tests first, each test file's docstring naming the design sections it verifies, test names
  sentences.
- Every color a `$clank-` element, every mark the style's (decision 0044); no line wider than its panel (decision
  0045).
- Redraws (design 0001 §5.7, design 0012 §2): at most four a second, only what changed, nothing while nothing changed;
  the page reads the service only while it is on screen.
- Another build changes the runner and the flows' routes meanwhile (the next flow, a model per box): the changes to
  `service.py` and `api.py` stay one method and two routes each, rebased on main before the end.
- The owner is the sole author of every commit (no trailer); nothing is pushed from this lane. The generated files are
  regenerated by `uv run python -m tools.check --fix`.

## Tasks

### Task 1: What the Flow view shows, made in the service

- [x] **Files:** create `clank/components/flows/view.py`; `clank/components/flows/service.py` (`Flows.view`,
  `Flows.log`), `clank/components/flows/api.py` (two routes); create `tests/support/flowshapes.py` (board D1's moment:
  its flow, its run as the runner writes it, its batch, its brief), `tests/components/flows/test_flow_view.py`.
- [x] **Interfaces:** `view(id, made, run, batches, *, running, titles, brief, present, ended, next_flow) -> dict`: `flow`,
  `workspace`, `name`, `title`, `run`, `boxes` (each: `id`, `type`, `title`, `state`, `preset`, `mode`, `tries`, `cap`,
  `writes`, `sees`, `shows`, `checks`, `proposed`, `asks`, `why`, `next`), `lines`, `proposals`, `next_flow`, `models`,
  `waiting`, `brief`, `deliverables`, `ahead`, `version`. `Flows.view(folder, flow="")`, `GET /flows/view`;
  `Flows.log(workspace, name, run=0)`, `GET /flows/{workspace}/{name}/log`.
- [x] **Tests:** `test_board_d1s_moment_says_each_boxs_state_tries_verdicts_and_files`;
  `test_the_lines_say_which_ran_which_runs_now_and_which_not_yet_and_the_fail_line_its_findings`;
  `test_the_brief_checked_lists_its_lines_and_every_accept_when_with_the_newest_verdict_on_each`;
  `test_deliverables_ahead_models_and_waiting_for_you_are_said`;
  `test_proposals_waiting_join_where_they_would_join_marked_proposed`;
  `test_a_folders_monitor_shows_the_active_run_else_the_last_run_else_the_first_flow`;
  `test_a_flow_not_run_yet_shows_every_box_waiting`; `test_the_view_is_pure_and_its_version_moves_only_with_what_it_shows`;
  `test_the_routes_give_the_view_and_the_run_log_oldest_first`. As built: a gate and a YOU box keep no try, so when a
  box last ended, and by whom, comes from the run's `flows.box_ended` events (`ended`); the flow run last is the one
  whose run ended (else started) last.

### Task 2: The flow laid out: stages in rows, boxes that never touch

- [x] **Files:** create `clank/components/agents/console/boxchart.py`; `tests/support/flowshapes.py` (generated flows
  of 1 to 12 tasks, with and without proposals waiting, a fail loop, an added box, the next flow, titles longer than a
  box; the checks every drawing passes); create `tests/console/test_box_chart.py`; snapshots of the chart alone.
- [x] **Interfaces:** `render(view, width, selected="", live=None, zone=None) -> Chart`; `Chart` (`lines`, `keys`,
  `cells`, `boxes`: each box's `Rect`, `labels` and `legend`: their cells, `order`, `listed`, `style_at`);
  `stages(view) -> list[list[str]]`; `tag`, `state_mark`, `last_said`, `model_said` (a box's words, which the list and
  the panels share); `LIST_BELOW`, `BOX_ROWS`.
- [x] **Tests:** `test_board_d1_is_laid_out_in_rows_of_stages_its_tasks_a_fan_at_the_widths_of_the_flow_panel`
  (snapshots); `test_below_70_columns_the_flow_is_the_list_of_board_d2s_left`;
  `test_a_fail_line_runs_under_its_row_back_to_the_box_it_checks_labeled_or_is_a_label_alone`;
  `test_lines_are_green_for_pass_red_for_fail_the_now_color_on_the_path_run_and_dashed_for_what_has_not_run`;
  `test_over_generated_flows_no_box_label_or_legend_touches_another_and_every_line_fits_its_panel`;
  `test_a_flow_taller_than_its_panel_keeps_its_boxes_whole_and_apart`; also
  `test_board_d1s_stages_are_its_boxes_in_the_order_they_run_its_tasks_one_fan`,
  `test_the_running_box_shows_its_step_and_speed_and_the_selected_box_is_lit`. As built: the edge cases are 144
  generated flows (`flowshapes.shapes`, made by the service's own `view`), each laid out at eight widths (the Flow
  panel's at 128 columns, 79, and at 88, 81; the list at 60; and 70, 74, 96, 110, 126); a row's wrap leaves its last
  box two cells in from its right side, and a fail line leaves the VERIFY four in, so a line under a row of adjacent
  boxes holds its label whole ("fail ⟲ 3 findings · 2 of 3 tries used").

### Task 3: The Flow view on the page: D1's moment

- [x] **Files:** create `clank/components/agents/console/boxpanel.py`, `flowpanels.py`, `flowview.py`;
  `following.py` (`FlowReading`); `monitor.py` (the Flow view's panels, its heading, its keys and ticks handed to
  `FlowViewer`); create `tests/console/test_monitor_flow_view.py`; snapshots `monitor-flow-d1-128`, `-88`, `-60`; the
  Monitor's empty Flow view snapshot (`monitor-flow-160`) says why no flow is shown.
- [x] **Interfaces:** `BoxChart.show(view, live)`, `.selected`, `.laid_out`; `flowpanels.selected(view, box, now,
  context, width, zone)`, `models(view, width)`, `waiting(view, width, zone)`, `brief(view, width)`,
  `deliverables(view, width)`, `ahead(view, width)`, `LinesView`; `FlowReading(client, folder).read(flow="")`;
  `FlowViewer` (`compose`, `tick`, `press`, `explain`).
- [x] **Tests:** `test_the_flow_view_shows_board_d1s_moment_at_128_88_and_60_columns` (snapshots);
  `test_the_arrows_move_between_boxes_and_selected_says_the_box_chosen`;
  `test_without_a_flow_the_view_says_why`. As built: Selected's Live is a box drawn inside the panel (`LiveBox`, its
  title in its border), not a panel of its own, so it is no section of the page; the Flow view's grid is `2fr 1fr` and
  stacks below 100 columns (`flowview.STACK_BELOW`), so at 88 the panels beside the flow move under it, as §12 says;
  the keys bar shows the keys of the view on screen (`Page.shown_keys`, `MonitorPage.VIEW_KEYS`), not every view's; a
  DECOMPOSE's task says the next task as what comes after it (they run one after another); the Monitor's empty Flow
  view (`monitor-flow-160`) waits for its reading, which says why no flow is shown.

### Task 4: Redraws: nothing while nothing changes, a running box at most four times a second

- [x] **Files:** `flowview.py` (the running box's session's now read each tick while it works, only its rows drawn
  again), `boxpanel.py` (`laid_out`); `tests/console/test_monitor_flow_view.py`.
- [x] **Tests:** `test_nothing_redraws_while_nothing_changes`;
  `test_a_running_box_redraws_at_most_four_times_a_second_and_only_its_rows`. As built: the view reads the flow
  once a second and the running box's now on each tick while it works; each `LinesView` draws only when its lines
  changed, and the chart refreshes only the lines whose key moved (the running box's tag and model lines).

### Task 5: Enter on a running box opens its session; Esc comes back; the other keys of D1

- [x] **Files:** `following.py` (`Following.pin`, `unpin`), `monitor.py` (`heading` names the box; `Esc` on a session
  opened from a box goes back to it), `flowview.py` (`Enter` by what the box holds; `h` the run log; `p` pause or
  resume; `r` run from here, asked first; `?` why a box is stale, failed or waiting); `tests/console/test_monitor_flow_view.py`.
- [x] **Tests:** `test_enter_on_a_running_box_opens_the_session_view_on_its_session_and_esc_comes_back_to_the_box`;
  `test_enter_on_a_finished_box_shows_its_deliverable_and_h_the_run_log`;
  `test_p_pauses_the_flow_and_r_runs_it_again_from_the_box_once_confirmed`. As built: `MonitorPage.open_session`
  pins the page to the box's session (`Following.pin`, `Seen.box`), the heading naming the box ("the flow's box A new
  simulation study · T2 · try 1 (Esc goes back to it)"); `back_to_box` unpins it and chooses the box again
  (`FlowViewer.back`); `r` and `h` join the Monitor's keys, and `p`'s words say what it does on each view. `?` on the
  Flow view says the flow's heading and the box chosen whole (`FlowViewer.explain`).

### Task 6: Board D4: proposals as cards

- [x] **Files:** `flowboards.py` (`cards(view, width, highlighted)`: the cards side by side, wrapped into rows, each
  its own bordered block), `flowview.py` (the D4 board: its panels, its keys `a` `e` `r` `A` and the arrows, `Esc`);
  create `tests/console/test_monitor_flow_boards.py`; snapshot `monitor-flow-d4-128`.
- [x] **Tests:** `test_d4_shows_each_proposal_as_a_card_in_the_order_they_will_run`;
  `test_d4s_decisions_accept_edit_reject_and_accept_all_reach_the_service`;
  `test_d4s_cards_never_touch_at_any_width`. As built: `BoxChart` and `CardsView` share one widget of lines
  (`boxpanel.ChartView`); a prompt is edited in a window of its own (`clank/console/editor.py`, `EditScreen`, on
  Textual's own `TextArea`: no new dependency); the service's view gives the run's newest batch when none waits, so
  D4 says what became of each card, and the flow's own settings (its auto-accept); the boards are the page's
  (`MonitorPage.BOARDS`, `show_board`), and `test_panels_everywhere.py` shows a board's panels through `show_board`.
  D4's cards were laid out before their test was written in this pass; the test was then seen to hold them.

### Task 7: Board D3: a gate

- [x] **Files:** `flowboards.py` (the gate's lines: where the flow is, what it shows, the VERIFY's report, the brief
  against the plan, its answers), `flowview.py` (`a` `e` `s` `d` `x`); `clank/components/agents/api.py` and
  `vscode.py` (Clank's VS Code window opens a file of the folder too: *edit, then approve*);
  `tests/console/test_monitor_flow_boards.py`, `tests/components/agents/test_vscode.py`; snapshot
  `monitor-flow-d3-128`.
- [x] **Tests:** `test_d3_shows_the_gate_what_it_shows_the_verifys_report_and_the_brief_against_the_plan`;
  `test_d3s_answers_approve_send_back_with_a_note_and_stop_answer_its_question`;
  `test_e_opens_the_file_in_clanks_vs_code_window_and_d_diffs_the_last_two_tries`;
  `test_clanks_vs_code_window_opens_a_file_of_the_folder`. As built: the service's view gives a gate's files with the
  box that wrote each (`shown`) and the workspace's folder; D3 reads the file as its writer's newest try kept it and
  how much it changed since the try before (the routes `copy` and `diff`) when it opens; its answers are the gate
  question's own (`POST /questions/{id}/answer`), and an answer takes the view back to board D1; `e` asks for Clank's
  VS Code window on the folder and the file (`agents.vscode` takes a `file`, named from the folder), then `a` approves
  it once saved; "Where the flow is" is the list at any width (`boxchart.listed`).

### Task 8: Board D2: a box's settings

- [x] **Files:** `flowboards.py` (the settings' lines, each field with its key, an unsaved change marked),
  `flowview.py` (`e`, the field keys opening a form, `s` saving through `PUT /records/flow/{id}` on the revision read,
  `v` the whole first message, `Esc` asking before it leaves a change not saved); `tests/console/test_monitor_flow_boards.py`;
  snapshot `monitor-flow-d2-128`.
- [x] **Tests:** `test_d2_shows_each_field_with_its_key_and_the_flow_as_a_list`;
  `test_a_change_is_marked_not_saved_until_s_saves_it_into_the_flows_file`;
  `test_a_save_on_a_flow_changed_meanwhile_is_refused_and_said`;
  `test_v_shows_the_boxs_whole_first_message`. As built: `e` reads the flow's file (`GET /flows/{workspace}/{name}`)
  for its values and revision; the changes wait in the view, by box (`FlowViewer.changed`), marked beside each field
  and in the list (`boxpanel.FlowList`, `boxchart.listed(noted=)`); `s` writes the whole file through
  `PUT /records/flow/{id}` on the revision read, so a file changed meanwhile is refused in the settings files' own
  words and the changes stay, to save again; type, mode and when done are picked from a list, the prompt and *accept
  when* edited in a window of several lines (`EditScreen`), the others in a form; Network says that grants come with
  M7; `v` reads the box's first message as `clank flow prepare` builds it (`GET /flows/{workspace}/{name}/prepare`);
  Esc with a change not saved asks first.

### Task 9: Documents

- [x] Design 0013 §14 step 6 marked built with this plan, and its index; the roadmap's M5 row; the plans' index;
  `docs/console.md` (the Flow view's keys); the glossary's new words; a decision record for the Flow view's layout;
  the generated files (`uv run python -m tools.check --fix`); this plan's boxes and its Built note. As built: design
  0013's index and its decisions list say step 6 built (decision 0093, the layout and the boards on the page); the
  glossary gains Board, Flow view and Stage; the walkthrough is left as it is (the owner's copy holds edits to it not
  yet committed, which a change here would collide with when it is pulled): its Monitor paragraph and keys row gain
  the Flow view with the walkthrough's next change.

- Built 2026-10-20, in eleven commits after this plan's (then the review's fixes, task 10, and this
  note's update): the view made in the service
  (task 1) and, after a rebase on the next flow, the next flow named once made; the layout (task 2); board D1, its
  redraws, its keys and board D4 (tasks 3 to 6, one commit: the Flow viewer holds them all); board D3 (task 7); board
  D2 (task 8) and `e` on the keys bar; the documents (task 9); and, after a rebase on a model per box, Ahead's
  switch costs from `Flows.switches`; and the brief read only from inside the folder.
  Found on the way: a frame of board D1 could be taken before what the running box's session does was read, so its
  Live box said "reading what it does" in one run and "idle" in the next: the frames wait for that reading; the
  Monitor's empty Flow view frame was taken before the view's first reading, so it now waits for the reading that
  says why no flow is shown; `ChartView.layout` would have shadowed Textual's own `Widget.layout` (renamed
  `lay_out`); the keys bar showed the Session view's keys on every view, so a page now says the keys of the view it
  shows (`Page.shown_keys`); the brief was read through a link wherever it led, so it is now read from inside
  the folder only, as the phone reads a file (its test makes a link, so it is skipped on a Windows that makes none for
  its user, and runs on Linux). The full check (`uv run python -m tools.check`) passed: 1,771 tests, 9 skipped. Nothing
  ran a real model, OpenCode or a container: every flow here is a run written as the runner writes it.

### Task 10: The review's fixes

- [x] **Files:** `flowview.py` (D2 on a proposed box, D3's answers, the Deliverables list, `o`), `flowboards.py`
  (`asked`, `answers`, `decision`), `flowpanels.py` (`DeliverablesList`), `boxchart.py` (a box's top line),
  `monitor.py` (`o`), `clank/components/flows/view.py` (`deliverables.written`), `service.py` (each waiting
  question's options, `_took` kept, `_followed`, a flow named without its workspace), `agents/vscode.py`
  (`_in_the_folder`); the tests below.
- [x] **Found and fixed** (the independent review of 2026-10-20):
  1. D2 on a box still proposed (dashed) said its change saved though nothing was written: the save merged only into
     the boxes of the flow's file. D2 now shows the proposal's own settings and saves its changes into the proposal
     (`POST .../proposals/edit`), where it still waits for the owner; only what was written is said saved.
  2. D3 offered approve, edit and send back for every gate, though a gate the flow waits at only because it waits
     after every box asks go on or stop: D3's answers are now the question's own (the view gives each waiting
     question's options), each key answering with its option, a key the question does not offer refused, said.
  3. The view said a try wrote a file by its fingerprint alone, where the runner also counts its size and time: it now
     uses the runner's `deliverables.written`, so a try that writes a file again with the same bytes is credited.
  4. `Flows.view` asked for the newest operations and launches on every reading (a second): how long each preset took
     is now read once and kept until an operation finishes (`Flows._took`, cleared on `operation.finished`).
  5. A queued flow could be shown before the one running, by its name: the running one comes first.
  6. `GET /flows/view?flow=study` (no workspace) failed with a 500: it is a 400 saying how to name it.
  7. Clank's VS Code window took a Windows drive-relative name (`C:x.md`): a name with a drive, a root, a backslash or
     `..` is refused.
  8. A box's top line cut its type or its tries before its step ("TASK T2 … ● step 14"): the step is shortened
     (`● 14`), then left to its mark, first.
  9. Enter on Deliverables (design 0013 §12) and `o` (§8) were approved but not built: Deliverables is a list, Enter
     shows the file highlighted as its try kept it, and `o` opens it (on the flow, the newest file of the box chosen)
     in Clank's VS Code window.
  10. Three tests were weak: Esc back from a session now has the flow move on to another box meanwhile; the brief's
      link test has a junction variant that runs on Windows; D2's save checks that the whole record round-trips.
- [x] **Tests:** `test_d2_on_a_proposed_box_saves_its_changes_into_the_proposal_never_the_flows_file`;
  `test_d3_offers_the_answers_of_the_question_the_gate_waits_for_go_on_after_every_box`;
  `test_a_try_that_rewrites_a_file_with_the_same_bytes_is_said_to_have_written_it_as_the_runner_counts_it`;
  `test_how_long_each_preset_took_is_read_once_and_again_only_when_an_operation_has_finished`;
  `test_a_folders_monitor_shows_the_flow_running_before_one_queued_behind_it`;
  `test_a_flow_named_without_its_workspace_is_refused_saying_how_to_name_it`;
  `test_a_file_named_with_a_drive_or_a_root_or_out_of_the_folder_is_refused`;
  `test_a_boxs_type_and_tries_are_kept_whole_its_step_shortened_or_left_out_first`;
  `test_enter_on_a_deliverable_shows_it_and_o_opens_it_in_clanks_vs_code_window`;
  `test_a_brief_in_a_folder_linked_out_of_the_workspaces_folder_is_not_read`; and the three strengthened.
  Each new test was seen failing first, the strengthened ones against the code broken by hand (`FlowViewer.back`
  for the Esc test, the folder's guard for the junction test); each fix is its own commit, twelve in all.

## Left for later

- **`a` add a box and `c` connect two boxes** (board D1's keys, design 0013 §12, §3: "`c` offers only what these rules
  allow"): changing the flow's shape from the view is not among step 6's tests; the flow's file, `clank flow check`
  and the model's proposals change it today. They are the Flow view's next small step, through the same save as D2.
- **The header's pill for the flow** ("flow running: T2", board D1's header): the header's pills are the console's,
  and the Monitor's own pill for the followed session's phase (design 0012 §2) is not built either; the Flow view's
  heading says where the flow is meanwhile.
- **Waiting for you lists the flow's own question and its proposals**; the questions and changes to review of the
  sessions its boxes run are the Session view's and the Questions page's until the view gathers them.
- **Board D3's "how the next try answered each finding"**: a verdict holds its findings, not how a later try answered
  each, so D3 shows each try's findings and the newest verdict's criteria (Against the brief), not a pairing of them.
- **Board D4's order** (the prototype's `o`: one after another or at once): tasks run one at a time on one engine
  (design 0013 §13), so the cards say the order they will run in, and nothing changes it.
- **Seeing it with a real flow running**: the view was tested on runs written as the runner writes them, and on the
  service's routes served in the test; the owner's first real flow will show whether a running box's step and speed
  read once a tick feel right on the real engine (design 0012 §2's pass mark, its measurement still pending from plan
  s17), and whether three boxes a row at 128 columns read well.

## Claude's calls (2026-10-20)


1. **The view's facts are made in the service** (decision 0049's precedent; plan s17's call 1): one route gives the
   console everything it draws, so the phone can draw the same later, and the console knows none of the runner's rules
   (which box wrote a file, what a VERIFY's fail line carries).
2. **Stages in rows that wrap.** A flow is a chain with two exceptions (decision 0057): its stages, one box or a
   DECOMPOSE's tasks, read left to right as board D1 draws its first row, and wrap to the next row as D1 wraps its
   flow (the line from the last gate's row down and back); a fan stays in the row of its DECOMPOSE. Board D1's
   arrangement by hand (its first row, its tasks under it) is not a rule a program can keep for every flow: rows that
   wrap are, at every width.
3. **A box is six rows**: its tag and state, its title, its model, its deliverable or last result, each on one line
   cut with the style's "…" (Selected and `?` say them whole); as many boxes a row as keep a box 22 columns wide (three
   in the Flow panel at 128 and 88 columns, two at 70), each row keeping room after its last stage for the line that
   wraps to the next. A title on two lines was tried on paper: it made every box a row taller for the few titles that
   need it.
4. **Board D1's legend and Flow panel note** stay: the legend under the flow, wrapped by items; the panel's note says
   how many boxes are done, running and waiting.
5. **Boards D2, D3 and D4 are boards of the Flow view on the page**, as the boards draw them (under the same tabs and
   heading), not windows over it: each is a set of panels the Flow view shows in place of D1's, and `Esc` goes back to
   D1. A window is at most 90 columns, and D4's cards and D2's two columns need the page.
6. **The box chart's own glyphs.** The boxes and the lines between them are drawn in box-drawing characters of the
   chart's own, their corners those of the style's border kind; the arrows and the dashes of what has not run are the
   style's tree glyphs (`arrow`, `not_yet`). Their colors are the style's elements.
7. **The view is read once a second while the Flow view is on screen**, as the Session view reads its session's flow,
   and drawn only when its fingerprint changed; the running box's now is read on every tick while it works, as the
   Session view reads it.
8. **The keys bar shows the keys of the view on screen**, and of the board while one is shown (`Page.shown_keys`):
   the Monitor's keys are declared once (`KEYS`, for Help), and `p` says what it does on each view; a board's keys
   (D2's field letters, D3's and D4's answers) are the board's own, routed by the Flow view while the board is shown,
   since several of them are panel letters or keys of another view.
9. **A gate's answers are its question's** (`POST /questions/{id}/answer`, from the console as any client), and an
   answer takes the view back to board D1, since the gate no longer waits; `e` asks for Clank's VS Code window on the
   file (the `agents.vscode` operation takes a `file`), and `a` approves once it is saved, as design 0013 §10 says.
10. **D2 saves the whole flow's file on the revision it read** (`PUT /records/flow/{id}`), as every client changes a
    settings record, so a file changed meanwhile refuses the save in the settings files' words; the changes stay, to
    save again on the new version. A box's field the rules forbid (a model for a GATE) is refused at the save, in the
    rules' words, not hidden.
11. **Ahead counts a switch from what the main slot runs now**, along the boxes still to run, and says how long that
    preset last took to come in here (`Flows.switches`, step 5's), so its words match `clank flow show`'s.
12. **Decision 0093** records calls 1, 2 and 5 (the next number: 0091 and 0092 went to the next flow and a model per
    box, built at the same time).
