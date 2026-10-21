# The Monitor, step 1: the page itself: implementation plan

> At the owner's request (2026-10-18, design 0012 approved: "Approve all three"; 2026-10-19: the new menu, the Monitor
> and flows built "as quickly as possible"). As for the earlier plans, the files, interfaces and tests by name and
> intent; the code is in the commits.

**Goal:** design 0012 §11 step 1: the Monitor, a page of the console's menu on F10, listed after F9; its three views,
Flow, Session and Context, in a row of tabs, F10 again moving to the next; each view's panels, titled and empty, saying
"no session yet" (the Flow view's "no flow yet"); the machine column hidden on it until F5 shows it; and nothing redrawn
while nothing it shows changes.

**Architecture:** The page belongs to the agents component (`clank/components/agents/console/monitor.py`,
`MonitorPage`), beside This folder. Under its row of tabs and its one heading line (decision 0043 allows a page with
views both) stand the three views' panels, each marked with its view's class and shown by the page's own class (so
the page scrolls sideways to a panel wider than it, as every page does): the Session view as
design 0012 §2 draws it (Context window across the page; Now, Watch for and the Guide beside the Flow; Tool calls beside
Biggest in the context), the Context view as §4.7 lists its panels, the Flow view as design 0013 §12 lists its. A new
`PanelGrid` (`clank/console/panel.py`) sets panels in columns of given widths, one panel spanning several rows (the
Flow beside Now, Watch for and the Guide), and stacks them in the order given when narrow, so the Flow comes second, as
§2 says. An empty panel holds an `Empty` label that takes the focus, so the panels' letters, Tab and the arrows reach
each panel before it has content of its own. The shell sorts F-keys by their number and hides the machine column on a
page that asks (`Page.MACHINE_COLUMN = False`) until F5 shows it; it already gives every key to the page on screen
(`on_key`), the menu's own too, so the Monitor takes F10 on itself as its next view.

**Tech stack:** Python 3.12, Textual 8.2.8 (grid with `row-span`, a page's classes), pytest with the console's text
snapshots.

**Spec:** [design 0012](../design/0012-the-monitor.md) §1 (what the owner gets), §2 (the page, its views, panels, keys,
room and redraws), §3 (no session yet), §10 (the measurement before step 1), §11 step 1;
[design 0013](../design/0013-flows.md) §12 (the Flow view's panels); decisions
[0043](../decisions/0043-every-section-is-a-panel.md) (every section a panel; a page with views keeps its tabs and one
heading line), [0046](../decisions/0046-the-keys-bar-shows-the-pages-keys-first.md) (the keys bar) and
[0047](../decisions/0047-the-monitor-is-a-menu-page-on-f10.md) (the Monitor on F10, three views); plan
[s8](s8-the-consoles-look.md) for the panels.

## Global Constraints

- No new dependency. Tests first, each named as a sentence, each file's docstring naming the design sections it
  verifies. Tests use the console's fixtures (a kernel built in the test, a fake container platform, temporary homes)
  only: no GPU, no model, no container, no window, and never the owner's service (7720) or gateway (18210).
- Every color is a `$clank-` element of the style, every mark the style's (decision 0044); text never spills out of a
  panel (decision 0045): the heading line is cut with "…", and `?` says it whole.
- Redraws: at most four a second, only what changed, nothing while idle (design 0001 §5.7, design 0012 §2). The page
  draws nothing from the console's data in this step; the machine column, hidden on it, draws nothing either.
- The machine column keeps its name in the code (`Monitor`, `#monitor`, `action_monitor`) until plan s8's task 11
  renames it; the page's ids never use `monitor-machine` or `monitor-now`, which are the machine column's.
- The owner is the sole author of every commit (no trailer); American English.

## Measurements (pending)

- [ ] **F10 reaches the console in Windows Terminal** (design 0012 §10, before step 1): `clank console`, F10, in the
  owner's Windows Terminal. It needs a terminal window, which nothing may open here. If F10 does not arrive, the
  Monitor's key becomes F12 (decision 0047): its `ENTRY.key`, the menu tests' lists (`test_shell.py`, `test_pages.py`,
  `test_monitor_page.py`), the snapshots, `docs/console.md` and the walkthrough's keys.
- [ ] **Decoding speed with the page on screen, against the page off** (design 0012 §2's pass mark, 95%; §10, before
  step 2): on the fake engine, then once on the real one with the owner's go-ahead. It needs the owner's terminal and,
  the second time, the GPU, which a benchmark used then. Plan s12 (step 2) waits on it too. If it fails, the page
  takes §2's fallbacks, in their order.

## Tasks

### Task 1: The menu sorts F-keys by their number

- [x] **Files:** `clank/console/menu.py` (`place`), `clank/console/app.py` (`_pages_in_order` sorts by it).
- [x] **Interfaces:** `place(entry: MenuEntry) -> tuple[int, int | str]`: the page a bare `clank` opens first, then the
  digits (0 after 9), then the F-keys by their number (F10 after F9), then any other key.
- [x] **Tests:** `tests/console/test_shell.py`: `test_the_menu_sorts_its_f_keys_by_their_number_so_f10_follows_f9`.

### Task 2: A panel beside several, in columns of set widths

- [x] **Files:** `clank/console/panel.py` (`PanelGrid`, after `PanelRow`).
- [x] **Interfaces:** `PanelGrid(*panels: Panel, columns: str, stack_below: int, spans: Mapping[str, int] = {}, id:
  str | None = None)`, a `PanelRow`: its columns' widths (`"2fr 3fr"`), each panel in `spans` (by id) as tall as that
  many rows, the gutters the style's (`rows-between`, `columns-between`); narrower than `stack_below`, one column, no
  spans, the panels in the order given.
- [x] **Tests:** `tests/console/test_panel.py`:
  `test_a_tall_panel_of_a_grid_stands_beside_the_panels_it_spans_its_borders_lined_up_with_the_row_below`;
  `test_a_narrow_grid_stacks_its_panels_in_the_order_given`.

### Task 3: The Monitor on F10, its three views, their empty panels

- [x] **Files:** create `clank/components/agents/console/monitor.py` (`MonitorPage`, `Empty`, `VIEWS`); change
  `clank/components/agents/component.py` (its pages), `clank/console/panel.py` (a grid's classes); the menu's lists in `tests/console/test_shell.py` and `tests/console/test_pages.py`;
  `tests/console/test_panels_everywhere.py` (a page with views: its tabs and heading line allowed, each view shown in
  turn); `tests/console/test_keys_bar.py` (a page may declare its own menu key); every console snapshot that shows the
  menu (one more line), rewritten and read.
- [x] **Interfaces:** `MonitorPage.ENTRY`: `monitor`, "Monitor", key `F10`. `VIEWS = ("flow", "session", "context")`,
  shown as the tabs Flow, Session, Context; `MonitorPage.view` (the view shown, Session the first time, then the one
  last shown), `show_view(name)`, `panels(view)`. `PANELS`, in order: the Flow view's `monitor-flow-boxes` (Flow),
  `monitor-flow-selected` (Selected), `monitor-flow-models` (Models in this flow), `monitor-flow-waiting` (Waiting for
  you), `monitor-flow-brief` (The brief, checked), `monitor-flow-deliverables` (Deliverables), `monitor-flow-ahead`
  (Ahead); the Session view's `monitor-session-context` (Context window, `c`), `monitor-session-now` (Now, `n`),
  `monitor-session-flow` (Flow, `f`), `monitor-session-watch` (Watch for, `w`), `monitor-session-guide` (Guide, `g`),
  `monitor-session-calls` (Tool calls, `t`), `monitor-session-biggest` (Biggest in the context, `b`); the Context view's
  `monitor-context-totals` (Context window), `monitor-context-parts` (What is in it), `monitor-context-gpu` (On the GPU
  exactly), `monitor-context-growth` (Over this session), `monitor-context-room` (Where the room went),
  `monitor-context-freed` (Could be freed), `monitor-context-sources` (Where these figures come from). `KEYS`: `f10`
  next view, `enter` open (on the Context window panel: the Context view), `escape` back (from the Context view to the
  Session view). In the Session view a panel's letter moves the focus into it.
- [x] **Tests:** `tests/console/test_monitor_page.py` (design 0012 §2, §11 step 1; decision 0047):
  `test_the_monitor_is_on_f10_listed_after_f9`;
  `test_f10_opens_the_monitor_and_f10_again_moves_to_its_next_view_flow_session_context_and_round`;
  `test_each_view_draws_its_panels_titled_and_empty_saying_no_session_yet_or_no_flow_yet`;
  `test_the_monitor_opens_on_the_view_last_shown`;
  `test_enter_on_the_context_window_panel_opens_the_context_view_and_esc_goes_back_to_it`;
  `test_in_the_session_view_a_panels_letter_and_tab_move_the_focus_from_panel_to_panel`;
  `test_question_mark_says_what_the_monitor_shows_and_what_is_built_so_far`; and the extended
  `test_panels_everywhere.py` over every page, the Monitor's three views too.

### Task 4: The machine column hidden on the Monitor; nothing redrawn while idle

- [x] **Files:** `clank/console/pages/__init__.py` (`Page.MACHINE_COLUMN`), `clank/console/app.py` (`show_page` sets
  the screen's class `-no-machine-column` for a page that hides it, and draws the column when it comes back),
  `clank/console/clank.tcss` (the rule, before F5's), `MonitorPage.MACHINE_COLUMN = False`.
- [x] **Interfaces:** `Page.MACHINE_COLUMN: ClassVar[bool] = True`: whether the machine column shows beside the page
  by the terminal's width; False, hidden until F5 shows it.
- [x] **Tests:** `tests/console/test_monitor_page.py`:
  `test_the_machine_column_is_hidden_on_the_monitor_at_160_columns_and_back_on_home_drawn_afresh` (readings that
  arrived while it was hidden show at once);
  `test_f5_shows_the_machine_column_on_the_monitor`;
  `test_the_monitor_on_screen_redraws_nothing_while_nothing_it_shows_changes` (the machine's meters told four times a
  second for two seconds, as the service tells them every second: before this task the machine column drew each, 16
  widgets drawn again; after it, none).

### Task 5: Snapshots at 128, 88 and 60 columns

- [x] **Files:** `tests/console/snapshots/monitor-session-160.txt` (the page 128 columns wide),
  `monitor-session-160-f5.txt` (with the machine column: 90, design 0012's "about 88"), `monitor-session-82.txt` (60,
  stacked), `monitor-flow-160.txt`, `monitor-context-160.txt`.
- [x] **Tests:** `tests/console/test_monitor_page.py`:
  `test_the_session_view_at_128_88_and_60_columns`; `test_the_flow_and_context_views_at_128_columns`.

### Task 6: Documents

- [x] Design 0012 §11 step 1 marked built with this plan, the F10 measurement pending; the roadmap's M5 row; the
  glossary (**Monitor**, **Guide**, **Step**, **Hold**, **Mark**, design 0012 §11's list for step 1); `docs/console.md`
  (the Monitor, `PanelGrid`); this plan's checkboxes and the plans' index; the generated files regenerated
  (`uv run python -m tools.check --fix`).

- Built 2026-10-19, in five commits after this plan's (one per task), then this one. Found on the way: every key
  reaches the page on screen (`on_key`) before Textual's bindings act on it, so the Monitor takes its own F10 with no
  change to the shell; the views' panels first stood in three containers of a `ContentSwitcher`, which clipped a panel
  wider than a narrow page instead of letting the page scroll sideways to it; a grid's spans must be set on the panels
  it is given, since they are not yet its children when it is made; and the machine's meters are not told every second
  in the console's tests (the service's loop does not run there), so the redraw test tells them itself. Every snapshot
  that shows the menu gained its line "F10 Monitor". Seen, not changed: a digit a page acts on (a question's numbered
  option) reaches the page twice, through `on_key` and then through the digit's binding (`action_key`), which asks
  the page again when the focus is in it; it is the shell's, older than this plan, and noted for its review.

### Task 7: After a look of its own

- [x] **Esc on a window over the Context view** closed the window and also took the page back to the Session view:
  every key reaches the page on screen, a window's too, so a page can answer a question from its window; Esc is the
  window's own, and design 0012 §2 says Esc goes back from a window to its view, no further. The Monitor now goes back
  on Esc only when no window is over it. **A click on a tab** shows its view (`view_at`), as a click on the keys bar
  presses a key. **Files:** `monitor.py`. **Tests:** `test_monitor_page.py`:
  `test_esc_on_a_window_over_the_context_view_closes_the_window_and_leaves_the_view`;
  `test_a_click_on_a_tab_shows_its_view`.

### Task 8: The review's fixes

- [x] **`?` says the heading line whole**, as this plan's constraints promise: a narrow page (60 columns) cuts it with
  "…", and `explain` now begins with it. **Tests:** `test_monitor_page.py`:
  `test_question_mark_says_the_heading_line_whole_where_the_page_cuts_it`.
- [x] **The glossary's order**: Guide after Grant, Monitor after Model. **The walkthrough** lists the Monitor on F10,
  in its keys at a glance and in §9.
- [ ] **F10 in Windows Terminal** stays the first pending measurement above: step 1 was built before it, since it
  needs a window, and the key changes in one place if it fails.

## Claude's calls (2026-10-19)

- **The view the page opens on** the first time is Session (board A, the owner's pick); after that, the view last
  shown, for as long as the console runs. Remembering it across runs waits for M2's console settings.
- **F5 stays one choice for every page**, as it is today: until F5 is pressed, the Monitor hides the machine column at
  any width, and the other pages show it by the width; once pressed, F5's choice holds on every page. A choice per page
  would change F5 on every page, and plan s8's task 11 is renaming the column's code.
- **The Session view's two columns are 2fr and 3fr** (board A draws Now at 44%, design 0012 §2 at about 37%), and stack
  below 80 columns: side by side at 88 (the page beside the machine column at 160), stacked at 60. The Context view's
  rows are 3fr and 2fr (board C's 62%), the Flow view's too (board D1's flow, about two thirds).
- **The Flow view's panels are design 0013 §12's**, empty, saying "no flow yet", so the page has its whole shape;
  design 0013's step 6 fills and may arrange them. The Run log is a window (`h`), not a panel.
- **The heading line says what is known**: "No session yet", and that following a session comes with the Monitor's
  next steps; it does not claim that no session runs. `?` says what each view will show and which step builds it.
- **The panels' ids name their view** (`monitor-session-now`): the machine column already uses `monitor-now`.
- **A page's own key pressed again is the page's**, so the Monitor declares `f10` among its keys; the keys test's rule
  (no page key acts anywhere) now leaves a page its own menu key. The shell needs no change for it: every key reaches
  the page on screen (`on_key`) before Textual's bindings run (the menu's F10 then shows the page already shown), so
  the first plan of a branch in `action_page` advanced the view twice and was dropped.
- **The views' panels are the page's own children**, not three containers in a `ContentSwitcher`: a panel inside a
  container as wide as the page was clipped by it at 80 columns with F5 (Context window, 22 columns in 20) instead of
  scrolling sideways, which `test_panels_everywhere.py` caught.
- **The planned entry Agents (M5) stays** in the menu: the Monitor takes over its live watching and guiding (decision
  0047), but its sessions, questions and approvals are still to come; its words change when the Guide is built.
