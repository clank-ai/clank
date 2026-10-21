# The Monitor, step 6: the renderer: implementation plan

> At the owner's request (2026-10-18, design 0012 approved: "Approve all three"; of board A: "make sure that
> everything is lined up properly as well as make sure that it is easy for me to navigate this"; of the prototype: "we
> need to be sure we are testing out edge cases for dealing with this in practice"; 2026-10-19: the new menu, the
> Monitor and flows built "as quickly as possible"). As for the earlier plans, the files, interfaces and tests by name
> and intent; the code is in the commits.

**Goal:** design 0012 §11 step 6: the session's branching flow drawn in the Monitor's Flow panel, as board A draws it:
time running down, the branches opening to the right, joined by box-drawing lines aligned in columns, stacked under
their node when the room is short; folds, the current node, moving in it; nothing spilling out of a node or the panel;
only the rows that changed laid out again. Tested by snapshots of board A's flow, calls made at once, subagents, a dead
end, a compaction band and a note, at 128, 88 and 60 columns, and over generated sessions at every width.

**Architecture:** Three small modules of the agents component's console, each pure but the last:

- `flowtree.py`: `tree(view, folds, subagents)`, the flow the service keeps (step 5's `Flow.view()`, as
  `GET /agents/flow/{workspace}/{session}` serves it) as a tree of drawable nodes: the owner's message the root; the
  main branches (a plan's steps, the todo list's items or the owner's messages, decision 0050) under it, each marked by
  its state; each branch's work in time order, a step's calls made at once gathered into one node that fans out, a run
  of one tool folded into one node (`read ×3`), a call that failed then passed into its tries, a subagent with its own
  flow's work when given, the owner's notes, the step working now, a step that failed or was stopped, dead ends, steps
  undone; a compaction a band, the branches above it folded into it. Each node says whether it folds, and whether it is
  folded by default (§6.4) or as the owner set it.
- `flowchart.py`: `render(view, width, cursor, folds, subagents)`, the tree laid out in lines of styled text no wider
  than `width`: a node's children to its right (`─┬─`, `├─`, `└─`, `│` in one column), or under it when what is left to
  the right is too narrow (always under `STACK_BELOW` columns); a node's words cut with the style's "…" so nothing
  spills; each line's spans (which node stands in which cells), the nodes in reading order, and the newest node.
- `flowpanel.py`: `FlowChart`, a widget of lines (Textual's line API): it keeps each line's strip until that line
  changes, so a change lays out only its rows again; ↑↓ move from node to node, ←→ fold and open, End goes back to now
  and follows it; it draws "no session yet" until it has a flow.

The Monitor (`monitor.py`) puts a `FlowChart` in its Flow panel and follows a session (`following.py`): design 0012
§3's choice (a), the newest active root session of the console's folder, else the newest root session heard; it reads
the folder's workspace, the flows kept of it and, for the followed session and its subagents, only what changed since
the version it holds, every second while the page is on screen, off the screen's thread, and draws nothing when nothing
changed.

**Tech stack:** Python 3.12, Textual 8.2.8 (`ScrollView` and its line API, `Content`, `Strip`), pytest with the
console's text snapshots and the synthetic sessions of plan s15 (`tests/support/flowlines.py`).

**Spec:** [design 0012](../design/0012-the-monitor.md) §2 (keys, room, redraws), §3 (which session), §6.2-§6.5 (what
branches, how it is drawn, folds and dead ends, moving in it), §11 step 6 and its revision (edge cases); board A
([Main.dc.html](../design/boards/Main.dc.html)); [design 0011](../design/0011-the-consoles-look.md) §2 (the tree's
glyphs, the `calls` colors), §6 (no color or mark written in a page); decisions 0047, 0048, 0050.

## Global Constraints

- No new dependency. Tests first, named as sentences; each test file's docstring names the design sections it
  verifies. Tests use the console's fixtures (a kernel built in the test, temporary homes) and synthetic sessions only:
  no GPU, no model, no container, no OpenCode, no window, never the owner's service (7720) or gateway (18210).
- Every color is a `$clank-` element of the style, every mark and every tree glyph the style's (`mark()`,
  `current().tree`): `tools/check_colors.py` refuses anything else in a console folder.
- Nothing spills (decision 0045): every line of the flow is at most the panel's inside wide, a node's words cut with
  the style's cut mark; a node's whole text is one key away (its details, Enter).
- Redraws (design 0001 §5.7, design 0012 §2): only the rows that changed are laid out again; nothing is drawn while
  nothing changed; the page reads the service only while it is on screen.
- The owner is the sole author of every commit (no trailer); nothing is pushed from this lane. American English.

## Measurements (pending)

- [ ] **The tree's glyphs in the owner's terminal** (design 0011 §2, design 0012 §6.3: "the layout has not been tried
  in a terminal yet"): ┬ ├ └ │ ┄ ⊘ ▸ and the marks, one cell each in Windows Terminal, so the columns line up as the
  snapshots pin them. It needs a terminal window, which nothing may open here. If one is two cells wide, the style
  file names a plain glyph for it (design 0011 §2).
- [ ] **Decoding speed with the page on screen** (design 0012 §2's pass mark, still pending from plan s11): now with a
  flow drawn and read every second. A factor to watch (Task 10): a flow that changed is laid out whole on the screen's
  thread, once per change; the review timed `render` at 25 ms for 200 steps (701 nodes) and 211 ms for 1,000 steps
  (3,501 nodes). If the measurement shows it, the layout moves into the reading thread, the widget given the finished
  `Drawn`.

## Tasks

### Task 1: The flow's tree: the owner, the branches, their calls

- [x] **Files:** create `clank/components/agents/console/flowtree.py`; `tests/components/agents/test_flow_tree.py`
  (flows made by step 5's `Flow` from synthetic sessions, `tests/support/flowlines.py`).
- [x] **Interfaces:** `Node` (`id`, `kind`, `words`, `tone`, `mark`, `detail`, `children`, `folds`, `folded`,
  `line`: solid or not yet, `end`: the dead end's glyph, `why`); `tree(view, folds=None, subagents=None) -> Node`;
  `what(call)`: a call's words (its command, its file, its pattern or its title), `tone_of(tool)`: the style's `calls`
  kind of a tool.
- [x] **Tests:** `test_the_owner_is_the_root_and_the_main_branches_are_its_children_each_marked_by_its_state`;
  `test_a_branchs_calls_come_in_time_order_and_a_run_of_one_tool_folds_into_one_node`;
  `test_calls_made_at_once_are_one_node_that_fans_out_to_each`;
  `test_a_call_that_failed_then_passed_folds_as_its_tries`;
  `test_steps_that_join_no_branch_hang_from_a_branch_of_their_own`.

### Task 2: Subagents, notes, now, stops, dead ends, undone steps and bands

- [x] **Files:** `flowtree.py`; `test_flow_tree.py`.
- [x] **Tests:** `test_a_subagent_is_a_branch_of_its_own_with_its_own_flows_work_when_given`;
  `test_a_note_joins_the_branch_of_the_step_under_way_when_it_was_sent_with_its_state`;
  `test_the_step_working_now_is_the_newest_node`;
  `test_a_step_that_left_the_context_is_drawn_apart_from_one_stopped_and_kept`;
  `test_a_dead_end_ends_in_its_mark_and_a_failed_call_still_under_way_does_not`;
  `test_steps_undone_are_a_side_lane_folded`;
  `test_a_compaction_is_a_band_and_the_branches_above_it_fold_into_it`.

### Task 3: Folds

- [x] **Files:** `flowtree.py`; `test_flow_tree.py`.
- [x] **Tests:** `test_a_done_branch_folds_to_one_line_and_the_branch_in_progress_is_always_open`;
  `test_the_owners_fold_or_open_wins_over_the_default`;
  `test_a_fold_that_holds_the_newest_node_is_open_by_default`.

### Task 4: The renderer: board A's fan-out, stacked when narrow

- [x] **Files:** create `clank/components/agents/console/flowchart.py`; `tests/console/test_flow_chart.py`;
  `tests/support/boards.py` (board A's session, and one with every kind of node, made as OpenCode keeps them);
  snapshots `tests/console/snapshots/flow-board-a-{128,88,60}.txt`, `flow-every-kind-{128,88,60}.txt`.
- [x] **Interfaces:** `render(view, width, cursor="", folds=None, subagents=None) -> Drawn`: `lines` (`Content`, each
  at most `width` cells), `spans` (each line's `Span(start, end, id)`: a node's cells, or a line's, `id` ""), `order`
  (the nodes in reading order), `row` (each node's line), `now` (the newest node), `nodes` (by id). `STACK_BELOW`
  (70): narrower, every node's children stand under it; wider, to its right while at least `CHILD_ROOM` columns are
  left for them.
- [x] **Tests:** `test_board_as_flow_at_128_88_and_60_columns`;
  `test_calls_made_at_once_subagents_a_dead_end_a_band_and_a_note_at_128_88_and_60_columns`;
  `test_every_junction_lines_up_with_the_branches_it_joins`; `test_nothing_spills_out_of_a_node_or_the_panel`;
  `test_the_current_node_alone_is_highlighted`; `test_a_folded_node_says_what_it_holds`.

### Task 5: Edge cases, over generated sessions

- [x] **Files:** `tests/support/flowgen.py` (sessions generated from a seed: many steps, many calls made at once,
  subagents within subagents, long names, wide characters, notes, failures, compactions, steps undone; and the
  checks every drawing passes, `junctions_line_up` and `drawn_once`, counting cells, as a wide character takes two);
  `tests/console/test_flow_chart_edges.py`.
- [x] **Tests:** `test_over_generated_sessions_at_every_width_no_node_junction_or_label_overlaps_and_every_line_fits`;
  `test_over_generated_sessions_every_node_is_drawn_once_and_reached_in_reading_order`;
  `test_a_session_of_one_message_and_nothing_yet_draws_its_root`.

### Task 6: The flow panel: moving, folding, following now, laying out only what changed

- [x] **Files:** create `clank/components/agents/console/flowpanel.py`; `tests/console/test_flow_panel.py` (the
  widget in a small app of the test's own).
- [x] **Interfaces:** `FlowChart(id=...)`: `show(view, subagents, key=session, empty=words)`, `cursor`, `following`,
  `folds`, `laid_out` (lines laid out so far); keys ↑ ↓ (the previous or next node), ← (fold, else the parent), → (open, else the first child),
  End (back to now, following it), declined when they do nothing, so the console's own arrows act.
- [x] **Tests:** `test_up_and_down_move_from_node_to_node_in_reading_order`;
  `test_left_folds_and_right_opens_a_branch_and_left_on_a_leaf_goes_to_its_parent`;
  `test_end_goes_back_to_now_and_the_cursor_follows_it_until_moved`;
  `test_only_the_rows_that_changed_are_laid_out_again`;
  `test_with_no_flow_it_says_no_session_yet`.

### Task 7: The Monitor follows the folder's newest active session and draws its flow

- [x] **Files:** create `clank/components/agents/console/following.py` (`Following`: which session, and its flow and
  its subagents' kept up to date from what changed since a version); `monitor.py` (the Flow panel holds a
  `FlowChart`; the heading line names the session followed; `?` says what is built); `tests/console/test_monitor_flow.py`;
  the Monitor's snapshots (`monitor-session-160.txt`, `-160-f5`, `-82`, new `monitor-session-flow-*.txt`).
- [x] **Interfaces:** `pick(heads) -> head | None` (the newest active root session, else the newest root session);
  `merged(held, changes) -> view` (a flow brought up to date by `GET /agents/flow/{workspace}/{session}?since=`).
- [x] **Tests:** `test_the_newest_active_root_session_is_followed_else_the_newest_root`;
  `test_what_changed_since_a_version_brings_a_flow_up_to_date`;
  `test_the_monitor_draws_the_followed_sessions_flow_and_names_it_in_the_heading`;
  `test_the_session_view_with_board_as_flow_at_128_88_and_60_columns`;
  `test_a_flow_that_did_not_change_is_not_read_again_or_drawn`;
  `test_with_no_session_the_heading_says_why`.

### Task 8: A node's details

- [x] **Files:** `flowpanel.py` (`details`, Enter), `flowtree.py` (`why`: what an inference rests on);
  `test_flow_panel.py`.
- [x] **Tests:** `test_enter_on_a_node_shows_it_whole_and_what_an_inference_rests_on`.

### Task 9: Documents

- [x] Design 0012 §11 step 6 marked built with this plan, §6.3's last sentence; the roadmap's M5 row; the plans'
  index; `docs/console.md`; the glossary if a word is new; the generated files (`uv run python -m tools.check --fix`);
  this plan's boxes and its Built note.

- Built 2026-10-19, in eight commits after this plan's (tasks 1-3 in one, then one per task), then this one. Found on
  the way: the page's Flow panel spans the rows of Now, Watch for and the Guide, and a spanning panel clips what it
  holds (`PanelGrid`), so a flow taller than them lost its last rows with no way to scroll to them: the flow now fills
  the panel and scrolls inside it (stacked, it is as tall as its flow, 24 rows at most); `scrollbar-gutter: stable`
  added a row under auto height, so the lines are laid out a column narrower than the widget instead, and never lose
  their last cell when the scroll bar comes; the first edge-case run flagged a junction that hung from nothing, which
  was the check indexing text by characters where a wide character takes two cells; `NO_SESSION` moved to the
  widget, which says it in the Flow panel now. The Monitor's snapshots of plan s11 changed by their heading line only
  ("this folder has no workspace: This folder (F4) opens one"), which lane 2's plan s8 task 11 also touches in
  `monitor-session-160-f5.txt` (its machine column): whoever merges second writes the snapshot again.

### Task 10: The review's fixes

- [x] **A node's details show its text as written** (major): `DetailsScreen` read its lines as Textual markup, so a
  closing tag in a command (`sed -e "s/[/]/_/g"`) crashed the console and `list[str]` showed as `list`; its lines and
  title are now plain text, for every window that uses it (a question's text and a preset's file held brackets too).
  Test: `test_details_show_a_nodes_text_as_written_brackets_and_all`.
- [x] **What changed keeps the flow whole after the service forgets old removals** (major): `merged` took a response
  as the whole flow whenever its `base` moved, though the service moves its base when it forgets its oldest removals
  and still sends only what changed; the page then held only the nodes that changed. Now only `whole` makes it whole.
  Test: `test_a_flow_kept_up_to_date_stays_whole_after_the_service_forgets_old_removals`.
- [x] **One reading at a time**: the page's worker was `exclusive`, which cancels a thread worker without stopping it,
  so two readings could change what `Following` holds together and deliver an older flow after a newer one. A reading
  asked for while one is under way now returns at once and asks nothing, and the page no longer cancels one under way.
  Test: `test_one_reading_at_a_time_a_second_one_meanwhile_asks_nothing`.
- [x] **A branch keeps its id when a compaction comes**: a branch's id carried its era (`todo:3@0`), so when a
  compaction came the branch in progress took a new id and the old one named its copy in the band: the owner's folds
  and a cursor not following now moved into the band. The branch after the last band is now its item's key
  (`todo:3`), a copy in a band its key and the band's id (`todo:3@<band>`). Test:
  `test_a_branch_keeps_its_id_when_a_compaction_comes_so_the_owners_folds_and_cursor_stay_on_it`.
- [x] **Nothing is read while the page is not on screen**, now proven: `test_nothing_is_read_while_the_page_is_not_on_screen`
  (it fails when the page's check is taken out).
- [x] **A flow that changed is laid out once**: the panel laid a flow out, then again when the cursor followed a new
  now. `render(..., follow=True)` works out the node to light from the tree's folds before the layout (`Drawn.cursor`
  says which), laid out again only when the layout left that node out for lack of room. Tests:
  `test_a_flow_that_changed_is_laid_out_once_with_the_cursor_on_now`, and over the generated sessions the node lit
  while following is now, laid out as without a cursor, and a cursor folded away lights the fold that hides it.
- [x] **`_subagent`'s `depth` parameter, never passed, is gone**: how deep subagents are drawn is counted by the '/' in
  their work's ids (`DEEPEST`), as its docstring now says.

## Left for later

- **Picking another session (`s`, which pins it)** and **a session idle since the service started**: the service
  keeps no flow of a session until a watcher line names it (plan s15, "For step 6"), and listing OpenCode's own
  sessions needs the bridge's list per server; they come with the session picker, with step 7's Now panel, which
  needs the same choice. Until then the page follows the newest active root session of its folder, else the newest
  root session heard, and says so in its heading.
- **`z`, a panel on the whole page** (design 0012 §2): a key of the page for every panel, built with the other
  panels' content (step 7), so the grid's columns are rearranged once. Until then the Flow panel scrolls.
- **Enter on a subagent opens its own flow and panels** (§3): its work is drawn under its node when its flow is kept,
  and Enter shows its details; following it with every panel comes with step 7.
- **A note's arrow into the step that read it** (§9.3) and **calls made at once joining again** (§6.2): a note shows
  its state ("waiting", "not read"), and the next step follows the fan-out below it; the style's join glyphs (┴ ╯)
  stay unused.
- **The warnings per lane** (§6.4: the same call again, failing again, one file again) are step 8's rules and marks;
  **the Guide's nodes** (stopped by you, held, undone by you) are steps 9 to 11's, except "undone by you", drawn now.
- **Times on branches** (board D's "11:58–12:00") and **tokens per item**: sizes are characters, as the flow keeps
  them, until step 12's estimate.

## Claude's calls (2026-10-19)

1. **Three modules, not one**: the tree (what is drawn), the layout (where), and the widget (when), so each stays
   short and the two pure ones are tested without a screen.
2. **A compaction's band holds the branches above it**, so folding it folds them, and what it folds stands under it;
   a branch worked on both sides of a compaction is drawn on both sides, each with its own work.
3. **A fold opens for the newest node only while that node works** (running, or waiting for an approval), never for a
   step undone, and **a failed call never folds into a run**: a fold never hides work under way or a failure, and a
   finished run stays folded.
4. **Calls made at once are one node**, `read ×3 at once` or `3 at once: read, grep`, open by default; in a group of
   one tool, each call shows only what it did; a group's sizes line up in one column when they fit.
5. **Sizes are characters** ("18.6K chars"), as the flow keeps a result's length; the board's token sizes come with
   step 12's estimate, so nothing is claimed that is not known.
6. **The layout's constants**: `STACK_BELOW` 70 (design 0012 §6.3); beside its children a node takes at most half the
   room and 40 columns (`WORDS_SHARE`, `WORDS_MOST`), its words cut only while it keeps 24 (`CUT_LEAST`), else its
   children stand under it, as they do where fewer than 24 columns (`CHILD_ROOM`) are left to its right. Tuned on
   the snapshots: a branch's title reads whole in the side-by-side Flow panel (72 columns) and the work keeps its room
   at 128.
7. **The flow fills the panel beside Now, Watch for and the Guide and scrolls inside it**, since a spanning panel
   clips what it holds; stacked, it is as tall as its flow, 24 rows at most.
8. **The arrows**: ← folds, else goes to the parent; → opens, else goes to the first child; a key with nothing to do
   is left to the console (`SkipAction`), so ← on the root goes back to the menu as on every page.
9. **What the page reads**: once a second while on screen, the flows kept of the workspace (heads and versions, which
   cost the service nothing) and a flow only when its version moved, only what changed; the folder's workspace every
   ten readings, since that route asks Docker. Nothing changed, nothing drawn.
10. **The heading without a session says why**: the folder has no workspace, or none of its sessions has been seen
    working since the service started; it never claims that no session runs.
11. **In branches from the owner's messages**, a branch's words are in the "your messages" color and its state is its
    mark; a note is no branch of its own (it joins the branch of the step under way when it was sent), and while the
    session works the last message left is the branch in progress.
12. **A tool OpenCode does not have itself is an MCP server's** (its `calls` color `mcp`), as OpenCode names an MCP
    server's tools after the server.
13. **Ruff allows the multiplication sign** (`allowed-confusables`), the boards' `read ×3`.
14. **The details window shows plain text for every page** (Task 10), not only the Monitor's: no page writes markup
    into it, and what it shows is often someone else's text.
15. **A second reading is skipped, not queued** (Task 10): the next tick, a second later, reads what changed meanwhile.
