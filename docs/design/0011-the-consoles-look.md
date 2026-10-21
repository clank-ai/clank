# Design 0011: the console's look, in panels, with a style you can change

The owner (2026-10-18), on the first boards of the Monitor: "I love the design choices that you have selected, and I
want you to note that they are different from the current design, so I need you to make sure that the design of Clank
in general is matching the same color scheme as the setup you have created, and I really like the individual boxes for
each thing that you have." On boards E1 and E2: "We also should design the style of Clank so that each of these major
style elements can be changed to different styles in the settings, but this is just for future proofing since I don't
want to worry about adding any more styles other than the single style that we have so far. However, both E1 and E2
look pretty much perfect. This is EXACTLY what I have been envisioning. Separating things into these blocks should in
principle make Clank easier to work on as well, since we need to make sure everything is expandable and that we are
eliminating every bit of technical debt we accumulate as possible." Then: "in the 'The new look, across Clank' section,
I want you to go ahead and sketch up a redesign of each of the pages. You have the home and 'this folder' pages
sketched which both look good, let's go ahead and sketch the others."

**Status:** written 2026-10-18, every section *approved* by the owner the same day ("Approve all three", the remaining
Choices as recommended). The boards are on the owner's canvas "Clank model monitor", in the row "The new look, across
Clank: every section in its own box", and are copied into the repository, in
[boards/](boards/README.md): their source (`*.dc.html`) reads as text, with their titles, panels and figures, and §8
names each board's file. When a board and this design's words differ, the words are the rule and the board is drawn
again (Claude's call, 2026-10-18). Boards A to D and D1 to D4, cited here, are design 0012's and design 0013's, which
name their files. E1 (Home) and E2 (This folder) are approved in the owner's words above; E3 to E18, one for each
other page, were drawn the same day at the owner's request and wait for the owner's look; so does E19, the five
windows (§7), drawn on 2026-10-19 with R2's last task from the windows as built. §12, every key a button, was added
on 2026-10-21 and approved by the owner the same day on board K2. **Choice** marks what the owner
has not decided, with a recommendation. The Monitor page
([design 0012](0012-the-monitor.md)) and flows ([design 0013](0013-flows.md)) are drawn in the same look: they are to
use this design's style and Panel, adding to the style file any element they need. Once approved, this design changes
[design 0001](0001-runtime-and-console.md) §5.5 (the look) and [design 0004](0004-working-in-a-folder.md) §9 ("every
color is a theme variable"): every color becomes a named element of the style.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner gets | Approved 2026-10-18 |
| 2 | The style: a file of named elements | Approved 2026-10-18 |
| 3 | The style in the console | Approved 2026-10-18 |
| 4 | The panel | Approved 2026-10-18; revised 2026-10-19 with R2 (a window's long title is cut in its border and shown whole inside) |
| 5 | Text never spills out of a panel | Approved 2026-10-18; revised 2026-10-19 with R2 (the same exception) |
| 6 | No color written in a page | Approved 2026-10-18 |
| 7 | The header, the menu, the keys bar, the machine column and the windows | Approved 2026-10-18; revised 2026-10-19 with R2 (a window's width and long title; board E19) |
| 8 | The pages, board by board | Approved 2026-10-18 |
| 9 | Narrow windows | Approved 2026-10-18 |
| 10 | What changes in the tests | Approved 2026-10-18 |
| 11 | Build steps | Approved 2026-10-18 |
| 12 | Every key a button | Approved 2026-10-21 (the owner: K2); built 2026-10-21 (plan s36) |

## 1. What the owner gets

- **One look on every page**, the boards' (E1 to E18): a dark background (#1a1b26); the header and the keys bar on a
  darker bar (#16161e); every section a panel, drawn as a box with a thin border (#3b4261) and its title set into the
  top border in bold blue (#7aa2f7); text in #c0caf5 and what explains it quieter (#828bb8); the highlighted row on
  #283457. States keep their meaning: green (#9ece6a) when as wanted, yellow (#e0af68) when something needs attention,
  orange (#ff9e64) for what runs now, red (#f7768e) for what failed and for the pages a later milestone brings.
- **Text stays inside its panel.** The owner, on a board: "This is overflowing out of the green box around it, so we
  need to be careful to make sure that the text that will be in these boxes is actually placed inside the box
  properly". Text wraps and its panel grows, or it is cut with "…" and shown whole one key away; no panel cuts its own
  title (the owner also found titles cut off by their boxes on the first boards, since fixed). §4, §5.
- **Lined up, and easy to move through.** The owner, on board A: "This is looking perfect so far, but we also need to
  make sure that everything is lined up properly as well as make sure that it is easy for me to navigate this." Panels
  in a row share their height, every title starts at the same column, the panel that has the focus has a blue border,
  and Tab goes from panel to panel. §4.
- **A style that can be changed** in the settings: one readable file names every element of the look, the console's
  setting picks it, and only Clank's own style ships. §2, §3.
- **A console easier to work on**: one widget, the Panel, for every section (37 sections in 17 files today); no color
  written in a page, which a check refuses (§6); each page's keys declared once (§7).

Not in this design: the Monitor page (F10) is design 0012's and flows are design 0013's; the phone page and Clank's
views in VS Code keep their own look. What a board shows that the console does not know yet (the agent's context on
Home, the Monitor in the menu) comes with the design that brings it.

## 2. The style: a file of named elements

A **style** is a settings kind ([design 0002](0002-the-foundation.md) §2.2): a readable JSON file
([decision 0007](../decisions/0007-settings-in-readable-files.md)), defined once in Pydantic
([decision 0015](../decisions/0015-kinds-defined-once-in-pydantic.md)), so its schema is generated and Records (7)
lists it: a style's groups (colors, marks, and so on) are its fields there, and `?` on a group explains it and names
its elements. A source for each element (Clank's file or the owner's) waits for a later change to Records, one that
shows nested fields, not R1 (Claude's call, 2026-10-18). Clank's own is `clank/defaults/styles/clank.json`. The
owner's go in `CLANK_HOME/config/styles/<name>.json`, and a `clank.json` there replaces Clank's, as for every kind. An
element a style leaves out takes the value in Clank's own file, the one place Clank's values are written, so a style
copied from Clank's keeps working when a later Clank adds an element.

Its elements, by group:

- **Colors by role**: what each color is for, never what it looks like. Pages, the header, the menu and the bars name
  only these (§6).
- **Data colors**: six colors in order, for the series of a chart; a sparkline takes the first (board A).
- **Named kinds**: what the Monitor and flows draw by kind, each a color by name, so that a kind keeps its color and
  green never says "good" by accident: `parts` (the context's parts: system, tools, yours, text, thinking, calls,
  results, loop), `calls` (reading, running, editing, mcp) and `boxes` (a flow's you, plan, verify, decompose, task,
  integrate, gate), with the boards' values; designs 0012 and 0013 name the group they draw with (Claude's call,
  2026-10-18).
- **Border kind**: `solid`, square corners, as every board draws its boxes; `round` is one word away.
- **Title placement**: in the top border, at the left, bold.
- **Marks**: the glyphs that say a state (● ○ ✓ ✗ ? ·), the header's ◆, the "…" of text Clank cuts (`fit`), the
  spinner's frames, and ✎ for a note of the owner's (boards A and D1 to D4). Every mark a page draws for a state comes
  from the style, through the drawing helpers (§3), never written in the page (§6). Textual's own "…", on a border
  title or a cell that Textual cuts, stays Textual's and is not an element of the style (Claude's call, 2026-10-18).
- **Bar and spark glyphs**: a bar's full cell, its eighths and its empty cell; the room kept for the answer (▒, board
  A); the eight steps of a sparkline (all in `clank/console/gauges.py` today).
- **Tree connectors**: what the Monitor's branching flow (design 0012) is drawn with: │ ├ └ ─ ┬ ▸, and ┄ for a path
  not taken yet, as boards A and D1 to D4 draw them; ╮ ┴ ╯ for a fan-out and ⊘ for a dead end, from the research's
  sketches. Box-drawing characters and marks such as ● are "ambiguous width": one cell in most terminals, two in some.
  The console already draws ●, ✓ and ─ today; whether each new glyph is one cell in the owner's terminal is to check on
  the first build, and a style can swap any of them.
- **Spacing**: a panel's padding (one column on each side), the page's, and the room between panels (one row between
  panels stacked, about two columns between panels side by side, as the boards space them).

The colors, as the boards use them:

| Name | Value | What it colors | Boards |
| --- | --- | --- | --- |
| `background` | #1a1b26 | the page, the panels, the windows | all |
| `bars` | #16161e | the header and the keys bar | all |
| `inset` | #16161e | a diff or a command shown inside a panel | E3 |
| `surface` | #24283b | a button, a choice to pick | D, D3, D4 |
| `border` | #3b4261 | every panel's border, the menu's edge, a divider | all |
| `border-focused` | #7aa2f7 | the border of the panel that has the focus | A |
| `title` | #7aa2f7 | a panel's title | all |
| `key` | #7aa2f7 | a key, in the keys bar, the menu and a sentence | all |
| `brand` | #bb9af7 | the header's ◆ CLANK | all |
| `name` | #e0af68 | the folder's name in the header, a workspace's in a sentence | E1 to E18 |
| `text` | #c0caf5 | text | all |
| `quiet` | #828bb8 | what explains, a time, a key's words, a panel's note | all |
| `dim` | #565f89 | the room kept for the answer, a list's rail, the border of a flow's waiting box | A to D, D1 to D4 |
| `selection` | #283457 | the highlighted row | all |
| `selected-text` | #ffffff | the highlighted row's text, bold | all |
| `good` | #9ece6a | as wanted: running, ready, done | all |
| `attention` | #e0af68 | waits for you; a warning | all |
| `now` | #ff9e64 | what runs now; the spinner | all |
| `failed` | #f7768e | what failed or is not as it should be (the words `BAD` lists in `text.py`) | all |
| `planned` | #f7768e | a page a later milestone brings | all |
| `low`, `busy`, `full` | #9ece6a, #e0af68, #f7768e | a bar by its level: below 60%, below 85%, above | E1 |
| `diff-hunk` | #bb9af7 | a diff's hunk line; added lines take `good`, removed lines `failed` | E3 |
| `scrollbar`, `scrollbar-track` | #3b4261, #1f2335 | a scroll bar | E16 |

The data colors, in order: #7aa2f7, #3d59a1, #bb9af7, #7dcfff, #73daca, #9d7cd8.

The named kinds, as boards A, C, D and D1 to D4 color them:

| Group | Kinds and values |
| --- | --- |
| `parts` | system #7aa2f7, tools #3d59a1, yours #e0af68, text #c0caf5, thinking #bb9af7, calls #73daca, results #9ece6a, loop #f7768e |
| `calls` | reading #7aa2f7, running #e0af68, editing #73daca, mcp #9d7cd8 |
| `boxes` | you #e0af68, plan #7aa2f7, verify #bb9af7, decompose #7dcfff, task #73daca, integrate #c0caf5, gate #e0af68 |

Clank's own file has this shape (every color of the table is in `colors`):

```json
{
  "schema": "style/1",
  "title": "Clank",
  "dark": true,
  "colors": {"background": "#1a1b26", "bars": "#16161e", "border": "#3b4261", "...": "every color of the table"},
  "data": ["#7aa2f7", "#3d59a1", "#bb9af7", "#7dcfff", "#73daca", "#9d7cd8"],
  "border": "solid",
  "titles": {"align": "left", "style": "bold"},
  "marks": {"brand": "◆", "on": "●", "off": "○", "done": "✓", "failed": "✗", "asks": "?", "event": "·", "cut": "…",
            "note": "✎"},
  "spinner": "⣾⣽⣻⢿⡿⣟⣯⣷",
  "bar": {"full": "█", "eighths": " ▏▎▍▌▋▊▉", "empty": "░", "kept": "▒"},
  "sparks": "▁▂▃▄▅▆▇█",
  "tree": {"down": "│", "branch": "├", "last": "└", "across": "─", "split": "┬", "split-end": "╮",
           "join": "┴", "join-end": "╯", "arrow": "▸", "not-yet": "┄", "dead-end": "⊘"},
  "spacing": {"panel-padding": 1, "page-padding": 1, "rows-between": 1, "columns-between": 2}
}
```

A color is written `#rrggbb`; a glyph must be one cell wide; a value that does not fit its element is refused with the
file, line and field, as for every settings file.

**Choice: the bars' colors.** (a) By their level, as today (`BUSY` and `FULL` in `gauges.py`), in the style's `low`,
`busy` and `full`, which Clank's style sets to the colors of `good`, `attention` and `failed`. (b) As board E1 draws
Home's GPU line: blue while the GPU is idle, yellow when its memory is nearly full. Recommendation: (a), the one rule
the machine column and Home share; (b) needs only other values for `low` and `full`, a line of the style file.

## 3. The style in the console

- **At start**, before the first frame, the console reads `CLANK_HOME/config/console.json` (a settings kind with one
  record, `console`, whose first field, `style`, is `clank` unless changed; design 0001 §5.5 meant this file for the
  console's layout too), then that style, and registers it as a Textual theme of its name before it sets it: today an
  unknown theme stops the console from starting (`clank/console/app.py:149`). The console reads these files itself, as
  it reads `console.tcss` today, so it draws in its style before the service answers.
- **What the theme carries.** Textual's own colors come from the roles, so Textual's widgets (the command palette,
  inputs, scroll bars) match: `brand` is Textual's primary, `title` its secondary, `now` its accent, `attention` its
  warning, `failed` its error, `good` its success, `text` its foreground, and `background`, `surface` and `bars` its
  background, surface and `panel` color; `quiet` sets `text-muted`, `border` and `border-focused` set `border-blurred`
  and `border`, `selection` and `selected-text` set the block cursor's background and foreground, and the scroll bar's
  two set Textual's. Every color is also a variable named `$clank-` and its name (`$clank-quiet`), the data colors are
  `$clank-data-1` to `$clank-data-6`, and the border kind, title placement and spacing are variables `clank.tcss`
  reads. The glyphs are read from the loaded style by the drawing helpers (`gauges.py`, `text.py`, `header.py`), and a
  page draws a state's mark (● ○ ✓ ✗ and the style's other marks) only through them; `tone()` in `text.py` reads the
  style's marks (today its lists hold ✓ and ✗ themselves), so a mark takes its state's color in any style.
- **Changing it**, like every setting: its file, `clank records`, the API, or Ctrl+P's "Change style", which lists the
  styles found (Clank's and the owner's) and writes the choice through the service (decision 0007), so it needs the
  service, as every change of a setting does. The console applies a change as soon as the service reports it
  (`settings.changed`). A file that does not read leaves the last good style in force, and the message line names its
  file and field (the service reports `settings.invalid`). A style that is not found falls back to Clank's own, and
  says so: the console always starts.
- **The owner's style sheet** stays: `CLANK_HOME/config/console.tcss`, loaded after Clank's (design 0001 §5.5). It may
  use the style's variables, or any color: it is the owner's own file.
- **The remembered theme.** Today the console keeps its theme in `CLANK_HOME/state/console.json`, and the remembered
  `tokyo-night` was saved there automatically, never picked by the owner (the research of 2026-10-18). The first
  console with styles reads that entry once and removes it, and never writes a theme again; a theme other than
  tokyo-night, which the owner did pick, is handled as the Choice below says.

**Choice: tokyo-night.** The clank style keeps the base colors of Textual's tokyo-night (primary #bb9af7, secondary
#7aa2f7, accent #ff9e64, warning #e0af68, error #f7768e, success #9ece6a, background #1a1b26, surface #24283b) and
changes its text (#c0caf5 for #a9b1d6) and its `panel` color (#16161e for #414868).

- (a) **Styles only.** Ctrl+P offers the styles (`clank` alone today) in place of Textual's own "Theme" command;
  Textual's built-in themes, tokyo-night among them, leave the picker. A theme the owner had picked is named once on
  the message line.
- (b) **Keep tokyo-night** beside the styles. Under it, Textual's own variables come from tokyo-night and every
  `$clank-` element keeps Clank's value (Textual's `get_theme_variable_defaults`: a variable that a style sheet uses and
  a theme lacks otherwise stops the style sheet from loading). Another theme the owner had picked is named once, as in
  (a).
- (c) **Keep every Textual theme**, as today: (b) for Textual 8.2.8's 21 built-in themes, light ones among them
  (textual-light, solarized-light), where Clank's dark values for borders, quiet text and data would sit on a light
  background. A theme the owner had picked is kept.

Recommendation: (a). One place for colors and one picker, nothing kept for its own sake (the owner's "eliminating
every bit of technical debt"); tokyo-night can come back at any time as a style file. The research leaned toward (b),
as a way back.

## 4. The panel

Every section of every page is a **panel**, a `Panel` (`clank/console/panel.py`), one widget shared by all: the 37
sections that `clank.tcss` draws today with one rule (`.section`: a top border and a margin), the machine column's two
and the windows (§7), and later the Monitor's panels and the Flow view's. These are design 0001 §5.6's panels: the
screens "are all made of panels", each one a small module. On screen a panel is drawn as a box, its title set in its
top border; "box" names that drawing only, and in flows ([design 0013](0013-flows.md)) a box is a step of a flow. The
owner's and the boards' "boxes" of a page are these panels (Claude's call, 2026-10-18).

- **Its title** is set into its top border at the left, bold, in `title`, written as the boards write it ("What runs",
  where today's says "what runs"). A title may carry a count ("Waiting for your answer · 3", E3).
- **A key letter**, when the page gives one, follows the title in `quiet`; pressing it moves the focus into the panel. A
  page gives letters only where its own keys leave them free (the Monitor's c, n, f, t and b, board A); no page of E1 to
  E18 needs one.
- **A note**, when the page gives one, sits at the right of the top border in `quiet` ("100 newest requests", E16; "4
  workspaces, 1 running", E15). It yields first: a panel too narrow for both drops its note, never its title.
- **Its content** sits inside one column of padding, clipped by the border, and nothing of a page sits outside a panel.
  Today nine places do: the lists of Questions, Operations, Presets, Models' slots, Workspaces, MCP servers and
  Requests, the History page's filter and lines, and the planned pages. The hint line that ends several pages moves
  into the keys bar (§7). One exception: a page with views (the Monitor, designs 0012 and 0013) keeps its row of tabs
  and one heading line naming what the view shows above its panels, as the page's own heading (Claude's call,
  2026-10-18).
- **The focus.** The panel that holds the focus draws its border in `border-focused`, and only that panel (board A).
  Tab and Shift+Tab go through the menu and each panel that takes the focus, in reading order (board A's "Tab next
  box" is this rule); Right and Left keep their meaning (into the page, between its lists, back to the menu). A panel
  takes the focus when it holds a list, or when its content is taller than the panel may grow, so that the arrows
  scroll it.
- **Its least width** is its title's: the title, its key letter, its corners and the spaces around them. A panel is
  never narrower, so its title is never cut (Textual cuts a border's title with "…" when the panel is narrower than
  it). A window (§7) is the one exception: it is never wider than the screen allows, so a title too long for it is cut
  in its border with "…" and shown whole, as written, as its first line inside (revised after approval, 2026-10-19,
  [decision 0081](../decisions/0081-a-windows-long-title-is-cut-in-its-border-and-shown-whole-inside.md)).
- **Lined up.** Panels in a row share the row's height, so their top and bottom borders line up; every title starts at
  the same column of its panel; a list's columns keep fixed widths, so its rows line up.
- **Rows of panels.** A page puts panels side by side where its board does (`PanelRow`, a row); §9 says when a row
  stacks.
- **Its id.** Each panel has a stable id, and each page declares its panels as an ordered list of ids, which it draws
  in that order, so M2's Layout page (design 0001 §5.5) can later show and rearrange them from `console.json`
  (Claude's call, 2026-10-18).
- **The page's keys, as named actions.** Each page declares its keys as named actions, each with its key and its words
  (§7), so M2's `keys.json` (design 0001 §5.5) can later remap them.
- **No redraw for the look.** A border changes only when the focus moves, and the look adds no animation (design 0001
  §5.7).

A page is then an ordered list of panels and rows of panels, each built from its id, its title, its letter, its note
and its content. The shell needs nothing per page to draw them.

## 5. Text never spills out of a panel

Every line inside a panel is one of these:

1. **Prose** wraps at the panel's width, and the panel grows to hold it.
2. **A row of a list or a table** is one line, cut with "…" at the panel's width (`fit` in `gauges.py`, or Textual's
   own ellipsis); its whole text is one key away (the Choice below).
3. **A drawing** (a bar, a graph, a table's columns, the Monitor's flow) is drawn for the width its panel gives, by a
   function of that width, as the machine column's parts are drawn today (`(seen, width)`), never wider.
4. **A name and its value** (`Rows`, `clank/console/rows.py`): the value wraps under itself, never back under the
   name, and the name stands above its value when the values' column is narrower than 36 columns. Today the doctor's
   advice on Machine wraps back to the panel's edge (the `machine` snapshot); it moves under its own column.
5. **A panel that may not grow** (a list of a hundred requests) shows a set number of rows and scrolls, taking the
   focus so that the arrows reach it.

So nothing is cut without "…", and no panel cuts its title (§4), but a window whose title is longer than the screen
allows, which then shows it whole as its first line (revised after approval, 2026-10-19, decision 0081).

**Choice: the key that shows cut text whole.** (a) `?`, which explains what has the focus in a window (design 0001
§5.4): on a cut row, the window starts with the row whole. One key on every page, and no new key. (b) A letter of its
own on every page: the letters that suggest it are taken on some page already (`v` is the live view on Requests and
vision's mode on CPU models; `w` switches on Models). (c) Enter where a page has no use for it: Enter already switches
a preset, lists a server's tools and shows a device's traffic, so it would mean "whole" on some pages only.
Recommendation: (a); a page keeps its own `v` where it shows a question whole.

## 6. No color written in a page

- **The console names only the style's elements**: `$clank-good`, never `#9ece6a`, `green` or Textual's `$success`.
  Today every color is a theme variable but one: the planned entries' `color: red` in `clank.tcss` (the owner asked on
  2026-10-11 that they be red). It becomes `$clank-planned`, the same red as `failed` in Clank's style.
- **Each generic variable takes the role it means.** `$accent` is used 28 times today: for the spinner (eleven times),
  a highlighted row, a window's border, Help's keys and page names, a sparkline, the header's mark, the tool calls of
  the live view, a pairing code, what the engine receives, the plan mode's name, a server that is on, a tool's name and
  the traffic window's labels. Each use takes its element (`now`, `selection`, `border-focused`, `key`, a data color,
  `brand`, and so on). `$success`, `$warning` and `$error` take `good`, `attention` and `failed` (or a bar's `low`,
  `busy` and `full`); `$text-muted` takes `quiet`; `$panel` and `$panel-lighten-2` take `bars` and `border`.
- **The check**, `tools/check_colors.py`, run by `tools.check` and by `tests/test_repository.py`, reads every file of
  the console (`clank/console/` and each component's `console/`, Python and style sheets, a widget's `DEFAULT_CSS` too)
  and refuses: a hex color; an `rgb()` or `hsl()` value; a color's name in a style rule; a style string or markup that
  names a color; a `$` variable that is not one of the style's; a mark of the style written in a page (● ○ ✓ ✗ ◆ ✎: a
  page takes them from the style, §3), where ?, · and …, which are punctuation too, pass (Claude's call, 2026-10-18).
  Prose is not a style: "Pages in red come with a later milestone" passes. Colors and marks are written only in style
  files. The owner's `console.tcss` lives in `CLANK_HOME`, outside the repository, and is not checked.

## 7. The header, the menu, the keys bar, the machine column and the windows

- **The header**: one row on `bars`, the same on every page, the folder's name included (boards E1 and E13 leave it
  out only because they were drawn before this rule; Claude's call, 2026-10-18). "◆ CLANK" bold in `brand`; the
  folder's name in `name`, as today; each pill, its dot and its words, in its state's color (today only its dot is);
  the spinner in `now` while something runs; the clock in `quiet`, at the right. A narrow header keeps each pill's
  short words (`header.py`).
- **The menu**: a column on `background`, its right edge in `border`. Each entry's key in `key`, its name in `text`,
  its badge at the right in its own color; the highlighted entry on `selection`, in `selected-text`, bold. Under a line
  in `border`, "coming" in `quiet`, then the planned entries in `planned` with their milestone. Its widths stay: 30
  columns, 20 under 100 columns with the planned entries hidden.
- **The keys bar**: one row on `bars`. The page's own keys first, then `?` explain and `f1` help, then the other keys
  that act anywhere (`f5` machine column, `q` quit), and `^p palette` at the right; each key in `key`, its words in
  `quiet`, as boards E2 to E18 show. Board E1 shows only the keys that act anywhere; by this rule, Home's own `s` and
  `d` come first there too. When the row is too narrow, the other keys that act anywhere go first, then the page's own
  from the right; `?` and `f1` always stay, and `f1` lists every key. Each page declares its keys once, as named
  actions, each with its key and its words (§4): the keys bar, Help's panels (E13) and `?` read that one declaration,
  so the hint lines that end several pages and Help's own table of every page's keys (`KEYS` in
  `clank/console/pages/help.py`) go. The shell draws the keys bar for the page on screen, wherever the focus is.
- **The message line** keeps its place above the keys bar: `quiet`, an error in `attention`, bold.
- **The machine column** (today's machine panel: on the right from 130 columns, F5 at any width) is two panels,
  "Machine" and "Clank now"; its own left border and padding go, since its panels have theirs. Bars keep their levels'
  colors (§2), graphs take the first data color, a meter's name is bold. Its class, `Monitor` today, becomes
  `MachineColumn` (its id and F5's action with it, and F5's words become "machine column"; Claude's call, 2026-10-18),
  since the F10 page is the Monitor (design 0012), in R2, which comes before the Monitor's first step (§11). §9 gives
  its arithmetic.
- **The windows**, five today: the details window (`?`, `v`), the form, the picker, an MCP server's tools and a
  device's traffic. Each is one panel (the traffic window two: its list and its body), its title in its top border
  (today a bold first line), its border in `border-focused` since it has the focus, on `background`; its keys ("Esc
  closes this") stay its last line, in `quiet`. A window is never wider than the screen allows (90%): a title too long
  for it is cut in its border and shown whole as its first line (§4, decision 0081). Textual's command palette (Ctrl+P) takes Textual's base colors, which
  the style sets (§3). Board E19 draws the five windows as R2 built them, for the owner's look (§11).

## 8. The pages, board by board

Each page is built against its board, whose file in [boards/](boards/README.md) the table names; where a board and
these words differ, the words are the rule and the board is drawn again. A page's step builds the board's panels,
their titles, their order and their arrangement, the marks and columns inside them, and the page's keys in the keys
bar. What a board shows that the console does not have yet is left out until its design brings it (the agent's
context on Home, the Monitor's entry in the menu: design 0012).

| Board | File | Its panels ("beside": side by side) | What changes from today |
| --- | --- | --- | --- |
| E1 · Home (1), in the new look | [Home.dc.html](boards/Home.dc.html) | Happening now beside Waiting for you; What runs; History | the first two side by side; each row of What runs led by its state's mark |
| E2 · This folder (F4), in the new look | [Folder.dc.html](boards/Folder.dc.html) | Get ready to work here; Then work beside What runs from here; Waiting for you | "what runs" becomes What runs from here, beside Then work; the hint line goes to the keys bar |
| E3 · Questions (2) | [Questions.dc.html](boards/Questions.dc.html) | Waiting for your answer · N; The highlighted question, whole, beside Its options above How it can be answered | the list gets its panel; the highlighted question shows whole beside it (today in a window, `v`), its diff on `inset` |
| E4 · History (3) | [History.dc.html](boards/History.dc.html) | Filter; Everything Clank recorded, newest last | the filter and the lines get their panels |
| E5 · Docker (4) | [Docker.dc.html](boards/Docker.dc.html) | Docker; Containers | in panels; the table of containers as today |
| E6 · Machine (5) | [Machine.dc.html](boards/Machine.dc.html) | Profile; Doctor | in panels; a check's advice wraps under its own column |
| E7 · Operations (6) | [Operations.dc.html](boards/Operations.dc.html) | The newest operations; Steps and log | the list gets its panel, with column headings |
| E8 · Records (7) | [Records.dc.html](boards/Records.dc.html) | Kinds; Records beside Values | Records and Values side by side |
| E9 · Models (8) | [Models.dc.html](boards/Models.dc.html) | Slots beside Memory; Last switches | the slots get their panel, beside Memory |
| E10 · Presets (9) | [Presets.dc.html](boards/Presets.dc.html) | Presets; Settings | the list gets its panel |
| E11 · Providers and models (0) | [Providers.dc.html](boards/Providers.dc.html) | Serving setups; Models | tables with column headings |
| E12 · Launch options (F2) | [LaunchOptions.dc.html](boards/LaunchOptions.dc.html) | (preset): launch options; The command line; Memory | one section becomes three panels |
| E13 · Help (F1) | [Help.dc.html](boards/Help.dc.html) | Keys anywhere beside Keys on This folder; Keys on the other pages beside What each page shows | two sections become four panels, read from the pages' declared keys |
| E14 · MCP servers (F3) | [McpServers.dc.html](boards/McpServers.dc.html) | Workspace; Servers beside Details · (server); Tools of (server) | the head and the list get panels; the highlighted server's tools in a panel of the page (today Enter opens a window) |
| E15 · Workspaces (F6) | [Workspaces.dc.html](boards/Workspaces.dc.html) | Workspaces; The highlighted workspace; Its software beside MCP servers its agent gets | the list gets its panel, its count in the note; the detail splits in three |
| E16 · Requests (F7) | [Requests.dc.html](boards/Requests.dc.html) | Model requests through the gateway; The highlighted request above Asked, beside Answered | the list gets its panel, its count in the note; what was asked and answered beside the request; the live view (`v`) is one panel shown in their place |
| E17 · CPU models (F8) | [CpuModels.dc.html](boards/CpuModels.dc.html) | Served beside Settings; How fast; Vision: the model that reads images | Served and Settings side by side |
| E18 · Phone (F9) | [Phone.dc.html](boards/Phone.dc.html) | Remote access beside Paired devices; Sent to the phone | the first two side by side |

A planned page, which has no board, is one panel: its name and milestone as its title, in `planned`.

## 9. Narrow windows

The console's widths stay (`clank/console/app.py`): under 100 columns the menu narrows to 20 columns and hides the
planned entries; from 130 the machine column shows, 38 columns wide, and from 170 it is 46; F5 shows or hides it at any
width. A panel costs four columns (its two borders, and a column of padding on each side) and one row more than a
section today (its bottom border). The room inside a panel, from the widths in `clank.tcss`:

| Terminal | Menu | Machine column | Inside a panel of the page | Inside a panel of the column |
| --- | --- | --- | --- | --- |
| 80 | 20 | hidden; 38 with F5 | 54; 16 with F5 | 34 with F5 |
| 100 | 30 | hidden; 38 with F5 | 64; 26 with F5 | 34 with F5 |
| 120 | 30 | hidden | 84 | |
| 130 | 30 | 38 | 56 | 34 |
| 170 | 30 | 46 | 88 | 42 |

- **What stacks.** Panels a board puts side by side stand side by side when the page gives each its least width (§4)
  and what its content declares it needs; otherwise they stack in reading order, the left one first. Each page's
  numbers are set with its board, and its tests prove both arrangements (§11). Inside a panel, `Rows` stands each name
  above its value under 36 columns of values, as today.
- **When even one panel does not fit** (F5's machine column in a narrow window leaves 16 to 26 columns inside a
  panel), the page scrolls sideways rather than cut a title.
- **The header** keeps each pill's short words, the **menu** cuts a long name with "…" (shown whole by `?`), and the
  **keys bar** drops keys as §7 says.
- **The machine column's width.** Each meter is drawn for the inside of its panel, where today `Monitor.draw` takes the
  column's own width (`clank/console/monitor.py:297`). The panels leave 34 and 42 columns, one fewer than today's 35
  and 43: the column's left border and padding go, and each panel has two borders and its padding.
- **The machine column's height.** The Machine panel's room is the column's height less the Clank now panel (its lines
  and its two borders), the Machine panel's own two borders and the row between the panels; today's sum counts each
  section's top border only (`clank/console/monitor.py:301`). When the meters do not fit, the blank lines between them
  go first, as today.

## 10. What changes in the tests

- **The ten text snapshots** (`tests/console/snapshots/`): `docker`, `history`, `home-80`, `home-120`,
  `home-question`, `machine`, `operations`, `questions` and `records` (the console's own tests, at 120 columns but
  `home-80`), and `runtime-models-stopped` (`tests/components/runtime/test_console_models.py`). R1 changes none: a
  snapshot is text, without color ([decision 0027](../decisions/0027-console-snapshots-are-text.md)). R2 rewrites all
  ten: each section gains side and bottom borders and a title as the boards write it, and text inside a panel wraps four
  columns sooner (at 80 columns Home's lines already wrap, as at `home-80.txt` lines 6 and 7, and more will). Each page
  step rewrites its pages' snapshots again. Every rewrite is read before it is committed (`CLANK_UPDATE_SNAPSHOTS=1`).
- **The tests that pin a color or the theme.** `tests/console/test_shell.py` pins pure red (`RED = (255, 0, 0)`, line
  28) in two tests, the menu's planned entries (line 88) and a planned page (line 101): they compare with `planned`,
  read from Clank's style file, so they pin the element, not its value. `tests/console/test_monitor.py`'s "the console
  starts in tokyo night and remembers the theme picked" (lines 197 to 205) becomes "the console starts in the style
  `config/console.json` picks, `clank` by default", with the migration's test beside it.
- **What stays**: the test that the owner's `console.tcss` is loaded after Clank's (it writes `.planned { color:
  blue; }`, and the owner's file may name any color); `frame_when` (`tests/console/frames.py`), which waits for "f1
  help" in a frame, since `f1` stays on every keys bar (§7); the test that Clank's own default settings read without a
  problem, which then reads Clank's style too.
- **What is new**: the tests of R1 and R2 (§11), and the repository's own check that no color, and no mark of the
  style, is written outside a style file (§6). `docs/TESTS.md` is generated again with them.

## 11. Build steps

**Before any code**: the sections a step builds are approved and their Choices decided (only approved sections are
built); the decisions below are written; each step gets its plan (`docs/plans/`). No new dependency; each step starts
with its failing tests. R1 and R2 may start once §1 to §7 are approved, with the parts of §9 and §10 they build (the
machine column's arithmetic, the tests they change): R2 titles the panels from §8's table and restyles the windows by
§7's words. The owner's look at boards E3 to E18, and at a board of the five windows drawn before R2 ends, may then
retitle panels in R3 to R7 (Claude's call, 2026-10-18).

**Build order** (Claude's call, 2026-10-18). R1 (the style) and R2 (the panel and the shell) come first, because the
Monitor ([design 0012](0012-the-monitor.md)) and the Flow view ([design 0013](0013-flows.md)) are built of this
design's panels. Then design 0012's steps, then design 0013's: its step 6, the Flow view, needs design 0012's page and
renderer. The bridge's changes both designs need, `prompt` with the agent and the model and the watch reporting a
session's status, are built once, in design 0012's step 4. **Decided by the owner (2026-10-18):** after R1 and R2,
design 0012's steps, then design 0013's.

**R1. The style and its theme** (colors and marks: no frame's text changes).

- The kinds `console` and `style` (`clank/console/kinds.py`, listed in `clank/registry.py`), their generated schemas,
  and Clank's style file.
- The loader (`clank/console/style.py`): `console.json`, then the style over Clank's, registered as a theme before it
  is set; the fallback and its message; the glyphs for the drawing helpers, every state's mark a page draws taken
  through them, and `tone()` reading the style's marks (§3).
- Every color of `clank.tcss` and of the console's Python names a `$clank-` element (§6); `.planned` takes `planned`.
- Ctrl+P's "Change style" (as the Choice of §3 decides); the remembered theme migrated once, and the console no longer
  writes it.
- The check (§6), of colors and of marks, in `tools.check` and `tests/test_repository.py`.
- `docs/console.md` ("Changing the look") and the glossary (Style) say where things are now.

Its tests prove that `clank` is registered and is the default, its theme carrying every value of Clank's file; that a
value changed in the owner's style shows, an element the owner's style leaves out takes Clank's, and an owner's
`clank.json` replaces Clank's; that a style not found, or a file that does not read, falls back to Clank's and says why
on the message line, and the console starts; that a remembered `tokyo-night` is removed once and never written again,
and another remembered theme is handled as the Choice says; that the menu's planned entries and a planned page are
drawn in `planned`, read from the style file; that a state's mark comes from the style (a style whose `done` mark is
another glyph shows that glyph, in `good`); that the check refuses a hex color, an `rgb()`, a named color in a rule
and in a `DEFAULT_CSS`, a style string, markup naming a color, an unknown `$` variable and a mark of the style written
in a page, each planted in the test's own folder, and passes prose that names a color and the repository itself; and
that the ten snapshots are unchanged.

**R2. The panel and the shell** (every section a panel; the snapshots rewritten once).

- `Panel` and `PanelRow` (`clank/console/panel.py`); the 37 sections become panels, titled from §8's table, and each
  page declares its panels by id, in order (§4); the nine places outside any panel get theirs.
- The header, the menu, the keys bar (each page's keys declared as named actions; the hint lines go, and Help reads the
  declarations in place of its own `KEYS`), the message line, the machine column (two panels, its arithmetic,
  `MachineColumn`, F5's words "machine column") and the five windows, restyled by §7's words.
- `docs/console.md` ("The screen") and the glossary (Panel, Machine column).

Its tests prove that every section of every page is a panel with four borders and its title whole, at 80, 120 and 170
columns; that each page declares its panels by id, in order, and draws them in that order; that only the panel with
the focus has the focused border, Tab goes from panel to panel in reading order, and no panel letter is one of its
page's keys; that no label in a panel is cut without "…" (each wraps, ends in "…" or fits), at 80, 120 and 170
columns; that the machine column's lines fit inside its panels at 100 (with F5), 130 and 170 columns, and the blank
lines between meters go first when the column is short; that the keys bar shows the page's keys first and always `?`
and `f1`, at 80 columns too; that each page declares its keys as named actions, and Help lists every key the pages
declare and holds no table of keys of its own; that each window is one panel with its title in its border; that the
phrases the tests look for are still found at 80 columns; and that the ten snapshots are rewritten and their
difference read before the commit.

**R3 to R7. The pages, against their boards** (§8). Each step builds its pages' panels, titles, order and arrangement,
their marks and columns and their keys; leaves out what the console does not have yet (its plan lists it); and rewrites
its pages' snapshots. For each of its pages, its tests prove the board's panels in the board's order with the board's
titles; side by side at 170 columns where the board has them so, and stacked at 80; and the page's keys first in the
keys bar. Besides:

- **R3. Home and This folder** (E1, E2, approved). Tests prove each row of What runs is led by its state's mark, and
  This folder's What runs from here stands beside Then work; snapshots `home-80`, `home-120`, `home-question`.
- **R4. Questions, History, Operations, Records and Help** (E3, E4, E7, E8, E13), and the planned pages. Tests prove
  the highlighted question shows whole beside the list, with its options; Help's keys stand in the four panels of E13;
  a planned page is one panel in `planned`; snapshots `questions`, `history`, `operations`, `records`.
- **R5. Docker, Machine, Workspaces and MCP servers** (E5, E6, E15, E14). Tests prove a check's advice wraps under its
  own column; a workspace's software stands beside the MCP servers its agent gets; the highlighted server's tools fill
  a panel of the page; snapshots `docker`, `machine`.
- **R6. Models, Presets, Providers and models, and Launch options** (E9, E10, E11, E12). Tests prove Slots stand beside
  Memory, and the launch options, the command line and the memory are three panels; snapshot `runtime-models-stopped`.
- **R7. Requests, CPU models and Phone** (E16, E17, E18). Tests prove what was asked and answered stand beside the
  highlighted request, and `v` shows the live view as one panel in their place and brings them back.

R3 can follow R2 as soon as §8 is approved (its boards, E1 and E2, already are); R4 to R7 also wait for the
owner's look at their boards.

### Decisions to record

1. **0041**: the console's look is a style, a readable JSON settings file of named elements (colors by role, data
   colors, border kind, title placement, marks, bar, spark and tree glyphs, spacing), picked in `config/console.json`
   and loaded into a Textual theme; `clank` ships alone and is the default (rather than a theme written in Python, or
   style sheets alone, which cannot color what Python draws).
2. **0042**: the console offers only Clank's styles, Textual's built-in themes (tokyo-night among them) leave the
   picker, and the remembered theme is migrated once (rather than keeping tokyo-night, or every Textual theme): the
   Choice of §3.
3. **0043**: every section of every page is a panel (design 0001 §5.6), one shared widget, `Panel`, drawn as a box:
   its title in the top border, an optional key letter and note, the focused border, a least width that keeps its
   title whole, and a stable id its page lists in order (rather than a style rule on plain containers, as `.section`
   is today).
4. **0044**: no color, and no mark of the style, is written outside a style file: the console names only the style's
   elements, and a repository check refuses color literals, other variables and marks written in a page (rather than
   review alone).
5. **0045**: text never spills: prose wraps and its panel grows, a row is cut with "…" and shown whole by `?` (rather
   than a key of its own, or Enter): the Choice of §5.
6. **0046**: the keys bar shows the page's own keys first, from one declaration per page, of named actions, that Help
   and `?` read too and M2's `keys.json` can remap (rather than only the keys that act anywhere, as today).

## 12. Every key a button

**Status:** approved 2026-10-21 (the owner, on board K2: "K2 is perfect for the buttons. I want you to go ahead and
immediately begin implementing this."). The owner's request: "turning each of the letters that we are displaying into
buttons that we can press, and the ability to navigate between the different buttons with my arrow keys or to click on
them, and pressing enter will then be the same as clicking the button or pressing the corresponding key." The boards
are in the canvas's row "Every key a button" and in [boards/](boards/README.md): K1 (what becomes a button and how the
focus moves: the behavior), K2 (This folder with buttons: the approved look), K3 (the Monitor's Flow view with
buttons), K4 (each state, three widths, a question, a window). What K1 to K4 draw and these words do not build is listed
in §12.11, each a **Choice** for the owner. Claude's calls are recorded in decisions
[0120](../decisions/0120-every-key-is-a-button-of-one-group-widget.md) (one mechanism),
[0121](../decisions/0121-how-the-focus-moves-between-buttons.md) (how the focus moves) and
[0122](../decisions/0122-a-buttons-states-are-colors-of-the-style.md) (the look); the owner may change any of them.

### 12.1 What becomes a button

- **The keys bar**: every key it shows, the page's own (or its view's), `?`, `f1`, `f5`, `q` and `^p`, on every page,
  read from the page's one declaration (`Page.KEYS`, §7): no page writes anything for them.
- **A panel's actions**: where a panel says what can be done here, the same keys are buttons, chosen from the page's
  declaration by key (a button's key, action and help are the declaration's; its words may be the panel's longer
  sentence). This step builds This folder's (board K2): the row under its steps ("Next:" and the keys that do the next
  step, or "Ready:" and `a` and `c`), the column of ways to work in Then work (`a`, `c`, `f`) and the row of its
  settings under it (`m`, `p`, `r`, `w`, `i`).
- **A question's options**: one button for each option and `v` for the question whole, wherever a question shows with
  its options: the first question waiting under Waiting for you on Home and This folder, and each question on the
  Questions page. On the Questions page the list keeps the focus and the letters answer its highlighted question, as
  today; a click on another question's option highlights that question and answers it (K4: "a click answers any").
- **A window's keys**: a window that asks first (`Enter do it`, `Esc leave it`) and the details window (`Esc close`).
- **Stays as it is**: the menu and the page's lists (already one row each, clicked and arrowed as today), values, logs
  and the header's states: nothing to press there.

### 12.2 One group, one cursor

A **group** of buttons is one widget that takes the focus (`Buttons`, `clank/console/buttons.py`): a row or a column,
with its own cursor, drawn as text. Each button is its key in `key` and its words, with one blank cell at each side;
two buttons side by side make today's two-space gap with their blank cells, so the keys bar holds the same keys at the
same columns as before (§7's fitting is unchanged; the last button's blank at the right may fall past the bar's edge).
A row too wide for its room goes on to the next line between two buttons, never inside one; a button of a column wraps
its words under themselves. A group may lead with words of its own ("Next:"), which are not a button. A group inside a
list's row (a question's options on the Questions page) takes no focus: its buttons are clicked, and the list's own
keys act. Textual's `Button` is not used: it is three rows tall with a border, and each is a stop of its own for Tab
(decision 0120).

### 12.3 Pressing a button

A button is pressed by **Enter** or **Space** while it has the focus, by **its key** from anywhere on its page, or by
**a click**, and all three go the same way, so a button can never do what its key does not: a page's key goes to the
page's `press` through the console's one door (`ClankConsole.press_key`), which the keys typed take too; a key that
acts anywhere runs its binding's action (`explain`, `page('help')`, `machine`, `quit`, `command_palette`); a window's
key runs the window's action. Typing a key leaves the focus where it was; a click moves the focus to the button it
pressed. A button pressed shows `pressed` for a fifth of a second, by its key too, wherever it shows; the message line
then says what it did, as today. A key of several (`y n …` on the keys bar) is not one button's: pressed, the message
line says which keys it stands for.

### 12.4 How the focus moves

- **Tab** and **Shift+Tab**: the next and the previous group, in the screen's order (Textual's focus chain): the menu,
  the page's lists and groups in reading order, the keys bar; after the last, the first.
- **Along a group** (← → in a row, ↑ ↓ in a column): the next button; it stops at the group's ends. **Home** and
  **End**: its first and its last.
- **Across a row** (↑ ↓): the nearest group above or below on the screen, the one nearest the focused button's column
  first; when there is none, the focus stays. **Across a column** (← →): as today, between the page's lists and groups
  and the menu (the shell's Right and Left). On the keys bar, ↑ goes back into the page, as Esc does.
- **Lists keep their own arrows**: the menu, a page's lists, the Flow view's boxes and a form's fields take their keys
  first, as today; the arrows move between buttons only while a group has the focus. No binding of the groups is a
  priority binding.
- **Esc** on a group: back to the page's main list (its first list; a page without one, its first group, or the page
  itself). In a window, Esc stays the window's: it leaves it.
- **`?`** with a button focused: the details window says what it does, the keys that press it, or why it cannot act
  now. On the keys bar's own `?`, it explains what had the focus before the keys bar.

### 12.5 Where the focus starts

- The console starts on the menu, as today: ↑ ↓ open the pages as they move.
- **→, Tab or Enter** on the menu goes into the page on screen: where the focus was when the page was last left, else
  its main list. Enter on the menu is new.
- A key typed leaves the focus where it was.
- **A window** with buttons opens with the focus on its first: on "do it" in a window that asks first, so Enter keeps
  its meaning. The key that opened a window never presses its button (the window's `armed` guard, design 0012 §9.1).
  Tab and the arrows stay inside the window; Esc leaves it, and the focus goes back where it was.

### 12.6 The message line says what the focused button does

While a group has the focus, the message line says what its focused button does and how it is pressed, in `quiet`
("g get everything ready: get everything ready: every step that is not done, in order · Enter, Space, g or a click"),
or, for a button that cannot act now, why, in `attention`; it is cut with the style's "…" to its one row. A message of
an action replaces it, as any later message does; when the focus leaves the groups, it is cleared unless a message came
since.

### 12.7 A button that cannot act now

A page may say that one of its keys cannot act now, and why (`Page.unable(key)`: "" when it can). Its buttons are drawn
dimmed (`dim`) and still take the focus, so the message line and `?` can say why; pressed (by Enter, Space, its key or
a click) the message line says why and the page's `press` is not called. The console's one door checks it, so a key
typed and its button say the same. This step: This folder's `a` until every required step is done, and its keys that
work on the workspace (`e`, `m`, `p`, `r`, `w`, `i`) before the workspace is opened, saying the words those keys say
today.

### 12.8 The look, in the style

Five colors join the style's colors (§2): `button_hover` (#292e42), the ground under the mouse; `button_focused`
(#7aa2f7), the focused button's fill, and `button_focused_text` (#1a1b26), its key and words on that fill;
`button_pressed` (#bb9af7), the fill for the fifth of a second a button is pressed; `button_unable_focused` (#3b4261),
the fill of a dimmed button that has the focus. A button's states:

| State | Its fill | Its key | Its words |
| --- | --- | --- | --- |
| normal | none | `key` | `quiet` on the keys bar, `text` in a panel |
| hover (the mouse over it) | `button-hover` | `key` | `text` |
| focused (its group has the focus; one on the screen) | `button-focused` | `button-focused-text` | `button-focused-text` |
| pressed (a fifth of a second) | `button-pressed` | `button-focused-text` | `button-focused-text` |
| cannot act now | none | `dim` | `dim` |
| cannot act now, focused | `button-unable-focused` | `quiet` | `quiet` |

The fill covers the blank cell at each side: no state changes a button's width, so nothing on its row moves. A style
file may set the five like any color.

### 12.9 Narrow windows

The keys bar keeps §7's rule (the other keys that act anywhere go first, then the page's own from the right; `?` and
`f1` stay; one row, never wrapped). A row of buttons in a panel goes on to its next line between buttons, a column's
button wraps its words, and the panel grows (§5): at 128, 88 and 60 columns nothing overlaps or is cut mid-word, and no
state moves a button, which tests prove on This folder and on the Monitor's Flow view.

### 12.10 Over SSH, and without a window

Clicks and the mouse's hover reach the console through Textual's mouse support, in Windows Terminal, VS Code's
terminal and over SSH (Windows OpenSSH, a Linux terminal) wherever the terminal reports the mouse (tmux only with its
`mouse` option on). Nothing here opens a window or starts a program. What only a real terminal can confirm: a click
over SSH, the hover's ground and the focused button's fill in Windows Terminal and over SSH.

### 12.11 Not in this step (Choices for the owner)

- **"… N more" on the keys bar, and shorter words under 70 columns** (board K4): a button that opens the keys that did
  not fit, and each key's short words. They change which keys fit, which §7 and this step keep; `f1` lists every key
  and its letter presses it. Recommendation: build them after the owner's look at K4 in the console.
- **The Monitor's view tabs as buttons** (K1, K3: Flow, Session, Context, without a letter), the Flow view's `Enter
  open its session` and `e another preset` in its panels (K3), the Guide's actions as buttons (K1), and the keys named
  in other panels' sentences (Home's "s stops it"): each needs its page's own panels changed; their keys are buttons on
  the keys bar meanwhile. Recommendation: with each page's next step.
- **A list's first row that waits for the owner** as where the focus starts (K1): the lists keep the row they
  highlight today. Recommendation: with the Questions page's step (R4).
- **What runs from here's buttons** (K2: `F10 watch it`, `l` its log, `s stop it`): keys This folder does not have
  (its `l` loads a model and its `s` starts Docker). Recommendation: decide the keys first.

### 12.12 What changes in the tests

- New tests: the button's text and its six states, each the same width; a group's keys (along, across, Home, End,
  Enter, Space, Esc), its click and hover; the keys bar's buttons at the same columns as before, Tab reaching it, Enter
  and a click pressing a key through the one door; `?` and the message line on a focused button; a button that cannot
  act now; This folder's groups at 128, 88 and 60 columns; a question's option buttons; the windows' buttons and their
  first focus; the five colors in Clank's style and in a style file. The focus is not in a text snapshot: the tests
  read the cells' colors.
- **The text snapshots** change where a group replaces text: This folder's (`folder-*`, new), Home's question
  (`home-question`), the Questions page (`questions`): a button's blank cells for today's separators. Every rewrite is
  read before it is committed (`CLANK_UPDATE_SNAPSHOTS=1`).

### 12.13 Build steps

One step, in [plan s36](../plans/s36-every-key-a-button.md): the style's five colors; the group (`Buttons`): its
drawing, keys, click and hover; the console's one door and `Page.unable`; the keys bar as a group; the message line and
`?`; where the focus goes (Enter on the menu, where the page was left, Esc); This folder's groups; the questions'
options; the windows' buttons; the narrow frames and the snapshots.

## Revision log

- **2026-10-19, §4, §5 and §7 revised after approval, with R2** (Claude's call after the review of
  [plan s8](../plans/s8-the-consoles-look.md)'s task 11,
  [decision 0081](../decisions/0081-a-windows-long-title-is-cut-in-its-border-and-shown-whole-inside.md)): a window
  has no least width, since it is never wider than the screen allows; a title too long for it (a preset's file path) is
  cut in its border with "…" and shown whole, as written, as its first line. Every other panel keeps its least width,
  and its title is never cut. The approved words had said no panel cuts its title, the windows among them, which a
  long title on a narrow screen cannot keep without pushing the window past the screen's edges. §7 also names board
  E19, drawn with R2's last task.
