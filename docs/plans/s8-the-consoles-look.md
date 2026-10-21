# The console's look, in panels, with a style: implementation plan

> At the owner's request (2026-10-18): "make sure that the design of Clank in general is matching the same color scheme
> as the setup you have created, and I really like the individual boxes for each thing"; "each of these major style
> elements can be changed to different styles in the settings"; then "Approve all three" (designs 0011-0013). As for
> the earlier plans, the files, interfaces and tests by name and intent; the code is in the commits.

**Goal:** design 0011's R1 (the style and its theme), R2 (the panel and the shell) and R3 (Home and This folder as
boards E1 and E2): every page of the console in the boards' look, every section a panel, every color and state mark a
named element of one readable style file.

**Architecture:** A settings kind `style` (one record per style, Clank's own `clank`, its defaults the boards' values)
and a kind `console` (which style) are read by the console itself at start, before the service answers, and loaded
into a Textual theme whose variables are the style's elements (`$clank-good`); pages, the style sheet and the drawing
helpers name only those. One widget, `Panel`, draws every section as a box with its title in its border; pages declare
their panels by id and their keys as named actions. A repository check refuses a color or a state mark written
anywhere else.

**Tech stack:** Python 3.12, Textual 8.2.8 (themes, variables, `:focus-within`, grid), Pydantic 2 kinds, pytest with
the console's text snapshots.

**Spec:** [design 0011](../design/0011-the-consoles-look.md) (§1-§11, approved 2026-10-18); boards E1-E18 in
[docs/design/boards/](../design/boards/README.md); [design 0001](../design/0001-runtime-and-console.md) §5.5-§5.7.

## Global Constraints

- Every color a page, a helper or `clank.tcss` uses is a `$clank-` element of the style (design 0011 §6); colors are
  written only in style files and in the kind's defaults.
- Clank's style's values are design 0011 §2's tables, exactly: background #1a1b26, bars #16161e, border #3b4261,
  border-focused #7aa2f7, title #7aa2f7, key #7aa2f7, brand #bb9af7, name #e0af68, text #c0caf5, quiet #828bb8, dim
  #565f89, selection #283457, selected-text #ffffff, good #9ece6a, attention #e0af68, now #ff9e64, failed #f7768e,
  planned #f7768e, inset #16161e, surface #24283b, low/busy/full #9ece6a/#e0af68/#f7768e, diff-hunk #bb9af7,
  scrollbar #3b4261, scrollbar-track #1f2335; the data colors and the named kinds as its second table.
- No new dependency. Tests first. No test opens a window or a terminal. The console's redraws stay at most four a
  second, nothing redrawn while idle (design 0001 §5.7).
- Each task ends in a commit pushed to `origin main`, after `uv run python -m tools.check --fix` passes, with the
  owner's uncommitted `docs/walkthrough.md` set aside and never committed; the owner is the sole author (no trailer).
- Snapshots are rewritten only with `CLANK_UPDATE_SNAPSHOTS=1`, and every rewritten snapshot's difference is read
  before its commit.

## Review Focus

1. **A terminal that draws ●, ✓ or box corners two cells wide**: the style can swap them; a style with ASCII marks and
   `round` borders must draw every page aligned (Task 4's and Task 7's tests use one).
2. **A narrow window with the machine column shown (F5 at 80 columns)**: no panel's title is cut; the page scrolls
   sideways instead (Task 7).
3. **An owner's style file that does not read** (bad JSON, an unknown field, a color that is not `#rrggbb`, a glyph
   two cells wide): the console still starts, in the last good style or Clank's, and the message line names the file,
   line and field (Task 2).
4. **A panel too narrow for its title and its note**: the note goes, never the title (Task 7).
5. **Focus moving quickly (Tab held down)**: only the borders whose focus changed are redrawn, within the four
   redraws a second (Task 7).

## Tasks

### Task 1: The kinds `style` and `console`, and Clank's style

- [x] **Files:** create `clank/kernel/console_kinds.py` (`StyleSettings`, KIND `style`, FOLDER `styles`;
  `ConsoleSettings`, KIND `console`, SINGLE, `style: str = "clank"`), beside the service's own settings kind, since
  the service reads and writes them and the kernel may not import the console (decision 0019, `tests/test_architecture.py`);
  list both in `clank/kernel/kinds.py`'s `KINDS`; create `clank/defaults/styles/clank.json` (`{"schema": "style/1",
  "title": "Clank"}`: every value is the kind's default); the generated schemas (`clank/schemas/style.schema.json`,
  `console.schema.json`) and `vscode/src/core/kinds.ts`.
- [x] **Interfaces:** `StyleSettings` fields, each a nested model with defaults from the Global Constraints: `dark:
  bool = True`; `colors: StyleColors` (one field per role, `-` in a name written `_` in Python and aliased back);
  `data: list[Color]` (6); `kinds: StyleKinds` (`parts`, `calls`, `boxes`, each a model of named colors); `border:
  Literal["solid", "round"] = "solid"`; `titles: StyleTitles` (`align`, `style`); `marks: StyleMarks` (`brand ◆`, `on
  ●`, `off ○`, `done ✓`, `failed ✗`, `asks ?`, `event ·`, `cut …`, `note ✎`); `spinner`; `bar: StyleBar` (`full █`,
  `eighths`, `empty ░`, `kept ▒`); `sparks`; `tree: StyleTree` (design 0011 §2's names); `spacing: StyleSpacing`
  (`panel_padding 1`, `page_padding 1`, `rows_between 1`, `columns_between 2`). `Color` is a `str` matching
  `^#[0-9a-fA-F]{6}$`; a glyph field accepts only characters one cell wide (`unicodedata.east_asian_width` not `W` or
  `F`, and not a combining mark).
- [x] **Tests** (`tests/console/test_style_kinds.py`, design 0011 §2): Clank's style reads with no problem and holds
  the boards' values (`background`, `border`, `title`, `quiet`, `planned`, `kinds.boxes.verify`, `marks.done`); an
  owner's `config/styles/clank.json` naming three colors keeps every other value of Clank's; a color `#12345` is
  refused naming `colors.good`; a glyph `全` in `marks.on` is refused; `console.json` with no file says `clank`.

- Built 2026-10-18 (Claude's calls): a style file's keys are written with underscores, as in every Clank settings
  file (`border_focused`), and the theme's variables with hyphens (`clank-border-focused`); reading one settings
  file is now a function of its own (`read_record` in `clank/kernel/settings.py`), which the settings files and
  the console's loader share.

### Task 2: The loader and the theme

- [x] **Files:** create `clank/console/style.py`; change `clank/console/app.py` (`__init__` registers and sets the
  theme before the first frame; `DEFAULT_THEME` goes); `docs/console.md` ("Changing the look") and the glossary
  (Style).
- [x] **Interfaces:** `load_style(home: Home) -> LoadedStyle` (`name: str`, `style: StyleSettings`, `problem: str`):
  reads `config/console.json` for the name, then `config/styles/<name>.json`, else `clank/defaults/styles/<name>.json`,
  each validated by its kind; a file that does not read, or a style not found, gives Clank's built-in values and a
  `problem` naming the file, line and field (the settings files' own wording, `SettingsProblem`).
  `theme_of(loaded: LoadedStyle) -> Theme`: Textual's base colors from the roles (primary=brand, secondary=title,
  accent=now, warning=attention, error=failed, success=good, foreground=text, background, surface, panel=bars,
  `dark`), and `variables`: every role as `clank-<role>`, the data colors as `clank-data-1`..`6`, the kinds as
  `clank-part-<kind>`, `clank-call-<kind>`, `clank-box-<kind>`, `clank-border-kind`, and Textual's own overrides
  (`text-muted`=quiet, `border`=border-focused, `border-blurred`=border, `block-cursor-background`=selection,
  `block-cursor-foreground`=selected-text, `block-cursor-blurred-background`=selection, `footer-background`=bars,
  `scrollbar`, `scrollbar-background`). `current() -> StyleSettings` returns the style in force, for the helpers.
- [x] **Tests** (`tests/console/test_console_style.py`, design 0011 §3): the console starts in the theme `clank` with
  `clank-quiet` #828bb8 among its variables; an owner's style changing `quiet` shows; `console.json` naming a style
  that is not found starts in Clank's and the message line says so; a style file with a bad value starts in Clank's
  and names its file, line and field; the console starts whatever the files hold.

- Built 2026-10-18 with Task 1, in one commit: the console no longer remembers a theme (the old test of tokyo-night
  went with it); the remembered entry's migration and its message are Task 6's.

### Task 3: Every color by its role

- [x] **Files:** `clank/console/clank.tcss` (every `$` variable becomes a `$clank-` element: `$panel` → `bars`,
  `$panel-lighten-2` → `border`, `$text-muted` → `quiet`, `$accent` per use as design 0011 §6 lists, `.planned` →
  `planned`); `clank/console/text.py` (`tone`: good, attention, failed); `clank/console/gauges.py` (`level`: low, busy,
  full; the empty cells: border; `spark` and `tall_spark` default: `data-1`); `header.py`, `monitor.py` and every
  page that names a theme variable (20 files, as the research of 2026-10-18 listed them); each `$accent` takes the
  role design 0011 §6 names for its use (the spinner `now`, a highlighted row `selection`, a window's border
  `border-focused`, Help's keys and page names `key`, a sparkline `data-1`, the header's mark `brand`), and a use §6
  does not name takes the role whose description fits, listed in the commit message.
- [x] **Tests:** `tests/console/test_shell.py`'s planned entries and planned page compare with Clank's `planned`
  (#f7768e) read from the style, not pure red; the owner's `console.tcss` still wins (blue); every console snapshot is
  unchanged (colors are not in them); `grep` finds no `$success`, `$warning`, `$error`, `$accent`, `$panel`,
  `$text-muted` left in the console (Task 5's check proves it for good).

- Built 2026-10-18 (Claude's calls, from the boards): the windows' background is `background`, as design 0011 §2's
  table says (the page, the panels, the windows), not `bars`; the pairing code is `now` (board Phone draws it so),
  what the engine receives `text` (board LaunchOptions), a tool's name `title` (board McpServers), the traffic
  window's labels `title` (they head its two parts), the plan mode's name `box-plan` (the Planner's color, as a flow's plan box), a server that is on but
  not running `now` (its color today: it starts with the next agent), the live view's tool calls `part-calls`; the
  highlighted row is `selection` (half of it while its list does not have the focus) with `selected-text` bold; the
  message line's error stays `attention`, as today. `docs/console.md` ("Changing the look") and the glossary's "Style",
  listed in Task 2, were written with this task.

### Task 4: Marks from the style

- [x] **Files:** `text.py` (`GOOD`, `CHANGING` and `BAD` take the style's `done`, `cut` and `failed` marks from
  `current()`, and `tone` reads them); `gauges.py` (`SPINNER`, `SPARKS`, `EIGHTHS`, the bar's cells from the style);
  `header.py` (the `brand` mark); every page that writes ● ○ ✓ ✗ ◆ ✎ draws `mark("on")` and so on
  (`clank/console/style.py`: `mark(name: str) -> str`).
- [x] **Tests** (`tests/console/test_console_style.py`): with an owner's style whose marks are ASCII (`on "*"`, `done
  "+"`, `failed "x"`) and borders `round`, Home and This folder draw those marks and no ●, ✓ or ✗, and `tone("+")` is
  `$clank-good`; the default style's frames are unchanged.

- Built 2026-10-18 (Claude's calls): `tone` knows a mark by the first word of a state (`"✗ 4"`), so a plain mark (`x`)
  never colors a word that begins with it; a page's local `mark` became `sign` where the page now calls the style's
  `mark()`; the waiting `?` of an operation is the style's `asks`, the queued `·` and every separator stay punctuation;
  the `…` of a step under way is the style's `cut`, as `tone` reads it; text cut by hand now uses `fit` (the menu's
  names, a record's values, a model's line) or the `cut` mark (a request's text, the traffic window's body). A bar's
  `eighths` must be eight glyphs (the kind refuses others: the bar divides a cell in eighths). This folder's marks are
  tested on `checklist_rows` itself, as its page needs the folder tests' fixtures, and Home's through the console; a
  fixture of the console's tests puts Clank's style back after each test, since the style in force is the process's.

### Task 5: The check

- [x] **Files:** create `tools/check_colors.py`; run it in `tools/check.py` and `tests/test_repository.py`; the
  check's own test `tests/tools/test_check_colors.py`.
- [x] **Interfaces:** `problems(roots: list[Path], names: set[str]) -> list[str]` (each `path:line: what`): in
  `clank/console/` and every component's `console/` (Python and `.tcss`, a widget's `DEFAULT_CSS` too) it refuses a
  hex color, an `rgb(` or `hsl(` value, a color's name as a value in a style rule, a style string or markup naming a
  color (`"bold red"`, `[green]`), a `$` variable not among the style's names (`names`, from `theme_of`), and the
  marks ● ○ ✓ ✗ ◆ ✎ written in a string; prose (a docstring, a sentence shown to the owner) that names a color
  passes; `?`, `·` and `…` pass (they are punctuation too).
- [x] **Tests:** each refusal on a file planted in the test's folder (a hex color, an `rgb()`, `color: red` in a rule,
  `red` in a `DEFAULT_CSS`, `"bold red"`, `[green]`, `$success`, a `"✓"` in a page); a docstring naming "red" passes;
  the repository itself passes.

- Built 2026-10-18 (Claude's calls): the check runs where the secrets and spelling checks run, in
  `tests/test_repository.py`, which `tools.check` runs with the tests (`uv run python -m tools.check_colors` runs it
  alone); `console_roots(repository)` and `style_names()` (the theme's `clank-` variables only, so Textual's
  `$text-muted` is refused too) give it the repository's folders and names. A color's name is a word Textual or Rich
  reads as a color (`transparent` passes); a style string is one made of nothing but words of style, which is how
  prose naming a color passes; a three-digit hex is refused in a rule's value only, as `#add` may be a widget's id
  elsewhere; docstrings and comments are prose. Run over the console as it was before task 3, it finds 53 problems.

### Task 6: Changing the style, and the remembered theme

- [x] **Files:** `clank/console/commands.py` ("Change style": lists Clank's styles and the owner's, writes
  `console.json`'s `style` through the service, `PUT /records/console/console` over its revision); `app.py` (Textual's
  "Change theme" command leaves the palette; the theme follows the style when the service reports
  `settings.changed` for `console` or `style`; `watch_theme` writes nothing); the migration in `style.py`:
  `forget_theme(home: Home) -> str | None` removes `theme` from `state/console.json` once and returns a theme other
  than tokyo-night that the owner had picked, which the message line names once.
- [x] **Tests:** a remembered `tokyo-night` is removed and never written again; a remembered `nord` is removed and
  named once on the message line; the palette offers "Change style" and not "Change theme"; picking a style writes
  `console.json` through the API, and the console's theme changes when the service reports it.

- Built 2026-10-18 (Claude's calls): "Change style" lists `GET records/style` in the console's own picker
  (`PickScreen`, each style's title, whose it is, and which is in force) and writes `PUT records/console/console` over
  its revision; the console reads its style again (`restyle`) on `settings.changed` for `console` or `style` and on
  `settings.invalid` for `config/console.json` or `config/styles/` (`restyles` in `app.py`); `load_style(home, last)`
  keeps `last` in force when a file no longer reads, as design 0011 §3 says, and gives Clank's when the style is not
  found; Textual's "Theme" leaves the palette through `get_system_commands`. `forget_theme` removes the file when the
  theme was all it held, and returns nothing when it cannot be read or written, so a theme is never named twice. The
  tests make the service notice a file with `kernel.settings.reload_changed()`, as its file watcher does. Added: an
  edit of the style in force shows at once, and one that no longer reads keeps the last good style.

### Task 7: The panel

- [x] **Files:** create `clank/console/panel.py`; `clank.tcss` (the panel's rules, using `$clank-border-kind`); the
  glossary (Panel, Machine column); `docs/console.md` ("The screen").
- [x] **Interfaces:** `Panel(*children, title: str, id: str, key: str = "", note: str = "", classes: str = "")`, a
  `Vertical`: its title in its top border at the left, bold, in `title`, the key letter after it in `quiet`; its note
  at the right of its bottom border in `quiet` (Textual draws one title on a border: a deviation from design 0011 §4's
  "top border", to record in the design with this task); its border in `border`, and `border-focused` while the focus
  is inside it (`:focus-within`); one column of padding; a least width that keeps its title and key whole (the note
  goes first). `PanelRow(*panels, stack_below: int)`: panels side by side in a grid row of equal height, stacked in
  reading order when the row is narrower than `stack_below` columns. `Page.PANELS: ClassVar[tuple[str, ...]]` lists a
  page's panels by id, in order (design 0011 §4, for M2's layout).
- [x] **Tests** (`tests/console/test_panel.py`): a panel's frame has four borders and its title whole in the top one;
  a narrow panel drops its note and keeps its title; the focused panel's border, and only its, is `border-focused`;
  Tab goes from panel to panel in reading order; two panels of a `PanelRow` share their height at 170 columns and stack
  at 80; with `round` borders the corners are ╭╮╰╯; holding Tab redraws within four times a second.

- Built 2026-10-18 (Claude's calls): the note stands at the right of the top border after all, as design 0011 §4 and
  the boards draw it, so the deviation planned above was not needed: the border's one label is the title, a run of the
  border's line sized to the panel's width, and the note, drawn again when the width changes; the run carries no color
  of its own and the border's title color follows the border (`:focus-within`), so the run is the border in both
  states. When a style centers or right-aligns titles, the note stands in the bottom border. The panel's rules live in
  its `DEFAULT_CSS`, beside it, with the style's spacing and title alignment as theme variables
  (`$clank-panel-padding`, `$clank-page-padding`, `$clank-rows-between`, `$clank-columns-between`,
  `$clank-title-align`). What a panel in a row holds must have its own height (a list's `height: auto`), as a grid row
  measures its cells by it. `Panel.enter()` moves the focus into a panel, for a page's key letter; no page has one yet
  (the Monitor's will). Not built: a test that holding Tab redraws within four times a second, since moving the focus
  runs no code of the console's (Textual's `:focus-within` restyles the two borders), so there is nothing of its own
  to count; the bound on its own redraws is `test_shell`'s. Added: a panel is never narrower than its title.

### Task 8: The shell's pages in panels

- [x] **Files:** `clank/console/pages/` (home, questions, history, operations, records, help, planned): each section a
  `Panel` titled as design 0011 §8's table and its board, declared in `PANELS`; the lists outside any panel today
  (Questions, Operations, History's filter and lines, the planned pages) get theirs; the hint lines move to the page's
  keys (Task 10). Snapshots `home-80`, `home-120`, `home-question`, `questions`, `history`, `operations`, `records`.
- [x] **Tests:** every page's composed panels are its `PANELS`, in order, each with its title whole, at 80, 120 and
  170 columns (one test over every page of the shell, `tests/console/test_panels_everywhere.py`, extended by Task 9);
  the phrases the console's tests wait for are still found at 80 columns; the snapshots, rewritten and read.

- Built 2026-10-18 (Claude's calls): Home's panels keep its sections' ids (`now`, `runs`, `waiting`, `history`) and its
  order until task 12 sets board E1's; the other panels are named for their page (`questions-waiting`,
  `history-filter-panel`, `history-events`, `operations-newest`, `operations-steps`, `records-kinds-panel`,
  `records-records`, `records-values`, `help-keys`, `help-pages`, and `planned` on each planned page). Questions' title
  carries the count ("Waiting for your answer · 2"); History's Filter panel says "/ filters the history by what you
  type; Esc leaves the filter" until `/` is pressed, as board E4 draws it; a planned page is one panel titled in
  `planned` (`Panel(title_color=...)`); Help keeps its two panels ("Keys", "What each page shows") until task 10 reads
  every page's declared keys into board E13's four. A panel's title can change (`Panel.title`). `test_command` looks for
  "What runs", the title as the boards write it. The seven snapshots were rewritten and read. Found on the way: Home wrapped
  What runs for its panel's width before the page's scroll bar narrowed the panel, so a line could break twice (a word
  alone on a line, a hint back under the name); a panel now says when its size changes (`Panel.Resized`), and Home
  wraps What runs again then.

### Task 9: The components' pages in panels

- [x] **Files:** each component's `console/` page (This folder, Requests, CPU models, Machine, Phone, Models, Presets,
  Providers and models, Launch options, MCP servers, Docker, Workspaces), as Task 8; snapshots `docker`, `machine`,
  `runtime-models-stopped`.
- [x] **Tests:** `test_panels_everywhere.py` covers every page; the snapshots, rewritten and read.

- Built 2026-10-18, in four commits (Claude's calls): every component's page draws its sections as panels titled as
  design 0011 §8's table and its board write them, in today's order and with today's keys (the boards' arrangements
  side by side and their changes of behavior are R3 to R7's). A panel's id is its page's prefix and what it shows,
  with `-panel` added only when a widget inside already has that id; the ids kept from sections are `folder-items`,
  `requests-detail` and `requests-live`. Every page's panels: This folder `folder-items`,
  `folder-work-panel`, `folder-runs`, `folder-waiting-panel`; Docker `docker-state-panel`, `docker-containers-panel`;
  Machine `machine-profile-panel`, `machine-doctor-panel`; Models `models-slots-panel`, `models-memory-panel`,
  `models-switches`; Presets `presets-list-panel`, `presets-settings`; Providers and models `providers-setups`,
  `providers-models-panel`; Launch options `launch-options-panel`; MCP servers `mcp-workspace`, `mcp-servers`,
  `mcp-detail-panel`; Workspaces `workspaces-list-panel`, `workspaces-highlighted`; Requests `requests-list-panel`,
  `requests-detail`, `requests-live`; CPU models `completion-served-panel`, `completion-speed-panel`,
  `completion-settings-panel`, `completion-vision`; Phone `phone-access`, `phone-devices-panel`, `phone-sent`. The
  counts of Workspaces and Requests are their list panels' notes, as boards E15 and E16 write them, and the
  highlighted workspace's name the note of its panel, in `quiet` as design 0011 §4 says (the board draws the name in
  `name`); the lists' head lines went, and "No workspace yet" or "No request kept yet" shows in the list's panel only
  when there is none. MCP servers' head is the panel "Workspace", without its own word "Workspace"; the column
  headings stand at the top of "Servers" in `quiet`, no longer a hint line (whose margin left a blank line in the
  panel); the details' title follows the highlighted server ("Details · fake"). The live view of Requests is one
  panel, "Live: the newest request as it is written", shown by `v` in place of the other two, as before. Launch
  options is one panel, titled "(preset): launch options" ("Launch options" until a plan is read), its command line
  and memory still inside it: E12's three panels are R6's, as design 0011 §11 lists them. This folder's messages name
  "What runs from here". No component page wraps text for a width of its own (its rows and labels wrap in Textual's
  layout), so none needed `Panel.Resized`. `test_panels_everywhere.py` now runs over every page the menu lists (the
  shell's, each component's and the planned ones), and also checks that nothing of a page but its hint line sits
  outside a panel. Left out: the doctor's advice still wraps back to the panel's edge, and a list's long rows wrap
  rather than end in "…" (design 0011 §5, with R5 to R7). Found on the way: Task 7's test of a narrow panel read its
  frame before its row had stacked, and failed about four runs in ten (stacked, the panel was wide enough for its
  note); it now reads the frame once the row has stacked and the frame has settled, at 28 columns, where the stacked
  panel is still too narrow for its note.
- Reviewed 2026-10-18; its findings fixed (Claude's calls): the tests page (`tools/testspage.py`) reads a list of
  sections of one design ("Design 0011 §4, §8 and §11") and a reference broken across lines, so these tests are listed
  under §8 and §11 too, and sections of other designs found the tests that already named them in lists (104 of 211
  sections had tests then, from 90; a range, "§6.1-§6.5", still counts for its first section, as AGENTS.md now says);
  the roadmap's M5 row says designs 0012 and 0013 are approved. With F5 at 80 or 100 columns a page cut its panels at
  its right edge (Textual's `VerticalScroll` hides what stands beyond it): a page now scrolls sideways (`overflow-x:
  auto` on `Page`), and shows the sideways bar where Textual's guard against flicker leaves it off, a panel wider than
  the page by no more than the vertical bar's two columns (`Page._refresh_scrollbars`; Providers' "Serving setups" at
  80 columns). `test_panels_everywhere.py` now proves it on every page with F5 at 80 and 100 columns, and on a page
  made for that one case; reads each panel's title in its own top border, and its bottom border (the page scrolled to
  it), Requests' live view too (shown by `v`), where it read the whole frame and the menu's "4 Docker" could stand for
  a cut "Docker"; lets only the hint line that ends a page stand outside a panel; and proves a list is drawn on its
  panel's background, focused or not (`clank.tcss`: Textual's lists draw on `surface`, which the style keeps for a
  button or a choice). `docs/console.md` states the rule the panels' ids follow, and that a count or a name goes in
  the title or the note as the board draws it. The notes say "1 workspace, 1 running" and "1 newest request"
  (`count()`), and their tests read them in the frame, where they read `Panel.note`, so a note not drawn, or not drawn
  again when it changes (after `x` stops a workspace), fails them; the Requests tests prove `v` shows the live view in
  place of the other two panels and brings them back (their `text()` reads hidden labels too); "No workspace yet" and
  "No request kept yet." are tested to show only while the list is empty; Launch options' title is tested to follow
  the preset; Task 7's narrow panel is tested on its whole top line, so a note cut by the border fails where only a
  dropped one passes, and a note set or changed after a panel is drawn has a test of its own; `steady_frame` in
  `tests/console/frames.py` is the one wait for a frame that stopped changing, which `frame_when` and the narrow
  panel's test share.

### Task 10: The header, the menu, the keys bar and the message line

- [x] **Files:** `app.py`, `header.py`, `clank/console/menu.py`, `clank/console/keys.py` (new),
  `clank/console/pages/help.py`, `clank.tcss`.
- [x] **Interfaces:** `PageKey(key: str, action: str, words: str)`; `Page.KEYS: ClassVar[tuple[PageKey, ...]]` (each
  page's own keys, named actions for M2's `keys.json`); `KeysBar` (replaces Textual's `Footer`): the page's keys first,
  then `?` explain, `f1` help, `f5` machine column, `q` quit, and `^p palette` at the right; when too narrow, the keys
  that act anywhere go first, then the page's from the right, `?` and `f1` always kept. Help's panels list every page's
  `KEYS` (its own `KEYS` table goes). The header: one row on `bars`, `◆ CLANK` in `brand`, the folder's name in `name`
  on every page, each pill whole in its state's color, the clock in `quiet`. The menu: keys in `key`, the highlighted
  entry on `selection` in `selected-text`, bold; "coming" in `quiet`; planned entries in `planned`.
- [x] **Tests:** the keys bar shows This folder's keys first, then `? explain` and `f1 help`, at 120 and 80 columns
  (`frame_when`'s "f1 help" still found); Help lists every page's declared keys and has no table of its own; the
  header names the folder on every page; the menu's highlighted entry is `selection`.

- Built 2026-10-19 (Claude's calls): `PageKey` has a fourth field, `help`, what Help says of a key when its words on
  the bar are too short to say it alone (`q quit`: "quit; the service and what it runs go on"), so one declaration
  serves the bar, Help and `?`. A key is written as Textual names it (`slash`, `escape`, `enter`) and shown as the bar
  writes it (`keys.shown`: `/`, `esc`); a question's option keys are one declaration, "y n …". The actions are named,
  not yet dispatched by name: a page still acts on its keys in `press`, until M2's `keys.json` remaps them. A key's
  words do not follow the page's state (CPU models says "x turns it off or on in VS Code", where board E17 says "turns
  it off"; Requests "v live view or the list"): the page's rows say the state. The keys that act anywhere are
  `keys.ANYWHERE` (`?`, `f1`, `f5`, `q`), from which the shell's bindings are made, and `PALETTE`; the keys that move
  (the digits, Esc, the arrows, Tab) are `MOVES`, which Help lists. The narrow rule is taken as decision 0046 words it:
  once a page's key would not fit, `f5`, `q` and the palette are gone already (Home at 120 columns shows its own keys,
  `?` and `f1`). Help is board E13's four panels, stacked ("Keys anywhere", "Keys on This folder", the page a bare
  `clank` opens, "Keys on the other pages", each page with keys on one line, and "What each page shows"); side by side
  is R4's. `?` ends its window with "Its keys: …", on a page and on a menu entry. A click on a key of the bar presses
  it, as Textual's footer did. The header is no longer bold as a whole: only "◆ CLANK" is, and the folder's name is in
  `name` at normal weight, as every board draws it (the review's catch). A change of the style in force redraws every
  widget (`restyle`): the keys bar's keys and Help's lines name `$clank-key` in their text, which Textual draws again
  only when a widget's own rules change, so an edit of `key` alone left them in the old color (the review's catch, now a
  test in `test_console_style.py`); `?` is tested in the page as well as on its menu entry. The menu's highlighted entry
  stays on `selection` while the focus is in the page, the page on screen; its keys are not padded to a column (tests
  and other steps read "1 Home"). The hint lines went from ten pages (This folder, Models, Presets, Providers and
  models, Launch options, MCP servers, Workspaces, Requests, CPU models and Phone); the windows' own ("Esc closes this")
  are task 11's. `test_panels_everywhere.py` no longer lets a hint line stand outside a panel. The ten snapshots were
  rewritten and read: the keys bar, and Models' hint line gone.

### Task 11: The machine column and the windows

- [x] **Files:** `clank/console/monitor.py` becomes `clank/console/machine.py` (`MachineColumn`, `#machine`,
  `action_machine`, F5's words "machine column", `MACHINE_FROM`), its two parts the panels "Machine" and "Clank now";
  `details.py`, `pick.py`, `form.py` and the tools and traffic windows: each window one panel (traffic: two), its
  title in its border, its border `border-focused`.
- [x] **Interfaces:** `MachineColumn.draw(seen: Seen, machine: bool = True)` draws each meter for its panel's inner
  width; the Machine panel's room is the column's height less Clank now (its lines and two borders), its own two
  borders and the row between them.
- [x] **Tests:** the column's lines fit inside its panels at 100 (with F5), 130 and 170 columns; when the column is
  short, the blank lines between meters go first; each window is one panel with its title in its border;
  `tests/console/test_monitor.py` becomes `test_machine_column.py`.

- Built 2026-10-19 (Claude's calls): the column's panels are `machine-meters-panel` and `machine-now-panel`, holding
  `#machine-meters` and `#machine-now`; with the class and F5's action, `MONITOR_TOPICS` became `MACHINE_TOPICS` and the
  screen's classes `-machine-on` and `-machine-off`. A rule in the owner's `console.tcss` that named `#monitor` names
  `#machine` now (`docs/console.md`'s example says so). The width a meter is drawn for is the Machine panel's inside (34
  and 42 columns), and the room is counted with the style's padding and `rows_between`; the Clank now panel has no row
  under it, so the two panels fill the column. When even the meters without blank lines do not fit, the last meters go,
  whole, the CPU always kept, and the Machine panel's note says "3 meters hidden" (`stacked`): before, they ran past the
  column's bottom and pushed Clank now out of sight. The column draws itself again when its size changes, and on a
  spinner's turn when Clank now's lines change in number (which changes the Machine panel's room); found on the way:
  shown again on the Monitor by F5, the column had drawn its meters 20 columns wide until the next reading, which the
  Monitor's F5 snapshot showed, rewritten and read. The windows are a `WindowPanel` (`panel.py`): ids `details`, `pick`,
  `form`, `tools`, each with the style's padding (one column, where `#details` had `1 2`) and its border
  `border-focused` whether or not something in it takes the focus; the form, which had no rule and filled the screen, is
  centered like the others. A window is never wider than the screen allows: a title too long for it (a preset's file
  path) is cut in the border with "…" and shown whole as its first line, as written (not read as markup), rather than a
  panel's least width pushing the window past the screen's edges. The traffic window (`#traffic`) is the panels
  `traffic-list-panel` ("my phone · everything it and this computer exchanged", its count and what was sent to it in the
  note, no note while nothing was exchanged) and `traffic-body-panel` ("The highlighted exchange", the keys its last
  line), a row between them, each border following the focus. Board E19, the five windows, is drawn in
  `docs/design/boards/Windows.dc.html` from the windows as built (design 0011 §7 and §11: before R2 ends); it is not on
  the owner's canvas yet, and waits for the owner's look with E3 to E18. Left out: a details window taller than 80% of
  the screen is still clipped, not scrolled, as before (R4 shows a question whole beside its list, design 0011 §8);
  `docs/walkthrough.md` still says "Machine panel" for F5, since the owner has changes of their own in it.
- Reviewed 2026-10-19; the review's fixes: a window's cut title, an exception to approved words, is recorded where the
  rules live, as [decision 0081](../decisions/0081-a-windows-long-title-is-cut-in-its-border-and-shown-whole-inside.md)
  (superseding 0043's "never cut" for the windows only) and design 0011 §4, §5 and §7 revised after approval, with a
  revision log; the `.section` rule, without users since the column's sections became panels, is gone from
  `clank.tcss`; the column-fit test now compares each panel's inside on screen with the lines drawn (its old last
  assertion could never fail: every row of the rightmost column ends in its border); a new test proves the Machine
  panel is drawn again on the spinner's turn when Clank now changes its number of lines (it fails without that
  clause); design 0004 §9 names `clank/console/machine.py`. Still left: `docs/walkthrough.md`'s F5 row, for when the
  owner's own changes to it are committed.

### Task 12: Home and This folder as boards E1 and E2 (R3)

- [x] **Files:** `clank/console/pages/home.py` (Happening now beside Waiting for you, then What runs, each row led by
  its state's mark, then History); `clank/components/agents/console/folder.py` (Get ready to work here; Then work
  beside What runs from here; Waiting for you).
- [x] **Tests:** each row of Home's What runs is led by its state's mark; Happening now stands beside Waiting for you
  at 170 columns and above it at 80; This folder's What runs from here stands beside Then work at 170; snapshots
  `home-80`, `home-120`, `home-question`, rewritten and read.

- Built 2026-10-19 (Claude's calls, from the boards and design 0011 §9): Home's `PANELS` are `now`, `waiting`, `runs`,
  `history`, the first two a `PanelGrid` (`home-top`) of columns `2fr 1fr` (board E1: Waiting for you 34%), This
  folder's Then work and What runs from here one of `3fr 2fr` (board E2: 38%); both stack below 80 columns, as the
  Monitor's rows do, so they stand side by side at 120 and 170 and stack at 80 and 130 (the machine column shown). A
  question in a third of the row read in 25 columns, eleven lines beside an empty Happening now (`home-question`), so
  while a question waits Waiting for you asks for 44 columns in Clank's own style (`QUESTION`'s 40 inside its border
  and padding) and the row stacks unless it gives them
  (design 0011 §9: what a panel's content declares it needs): `PanelRow.stack_below` is now a property a page sets
  anew, and the row stacks or stands side by side again at once (`tests/console/test_panel.py`). Each row of What runs
  that says a state is led by its mark (`run_mark`): `on` in `good` as wanted, or in `attention` while it starts or
  stops; `off` in `quiet` when it does not run, as the board draws a stopped slot (a part may be off as the owner wants
  it), not in `failed` as `tone` colors the word "stopped"; `failed` in `failed`; `cut` in `attention` while not read
  yet. The models' row has a mark for each slot, its parts set apart by three spaces as on the board; the GPU, the
  machine and the folder say no state and have none, as on the board. The marks carry the color, so the state's words
  are no longer painted (`workspace_containers`, which only listed the words to paint, went). A row's name and its
  key's hint are in `quiet`, the hint without its parentheses, as the board writes them; a row wraps under its value
  after its mark. Waiting for you says "✓ Nothing waits for you." (the style's `done`), and, while nothing waits,
  "questions from the agent and from Clank land here" in `quiet`, as the board; This folder's says "✓ No question
  waits.". Home's `?` explains the marks. Found on the way: Home's questions were given to their label as a string, so
  a question's text was read as markup; it is now shown as written. Left out, as design 0011 §8 lists no change for
  them: board E1's GPU row drawn as bars (§8's table lists no change for that row; when a later step draws them, they
  follow design 0011 §2's Choice (a), approved as recommended: colored by their level, as `gauges.py` does), the
  History's lines led by a mark for each event (board E4 draws the same marks: R4 builds them for both pages), Happening now's agent with its
  context (design 0012), and This folder's board details beyond its arrangement: the steps' keys in a column of their
  own in `key`, "Folder" in `quiet`, Then work's shorter lines (the mode on one line with its keys), and What runs from
  here's container and OpenCode lines (the container's CPUs and memory, the agent's state: nothing on the page reads
  them yet; it shows the steps it follows, as before). The tests are `tests/console/test_home_and_folder_boards.py`;
  `test_home.py`'s rows read `.plain` now, and its test of a row's wrapping moved there, with the mark.
- Reviewed 2026-10-19; the review's fixes: a question whose words look like markup ("Delete [/tmp]?") no longer
  stops Home's drawing, since the History's lines, which repeat its title, are shown as written too (the "found on
  the way" fix had covered Waiting for you only; `test_home.py` asks such a question). A row of What runs colors each
  mark where it put it, not where its glyph is next found, since a style may make a mark a letter of the words before
  it ("o" in "frontier", design 0011 §2): each mark is held by a character of Unicode's private use while the row
  wraps, and glued to its first word by a no-break space, so a wrapped row never ends a line with a mark parted from
  its slot (it did at some 15 widths). The question's room counts the style in force: `QUESTION` is now the 40
  columns inside Waiting for you, and `asking_below` adds its border, the style's `panel_padding` and
  `columns_between` (Clank's own style gives 134, as before; a style of 8 columns between let a question sit side by
  side in 42). This Built note's reason for leaving out the GPU bars was wrong and is corrected above.

## After this plan

R4-R7 (the other pages arranged as boards E3-E18) wait for the owner's look at those boards (design 0011 §11); then
design 0012's steps, then design 0013's (the owner's order, 2026-10-18).
