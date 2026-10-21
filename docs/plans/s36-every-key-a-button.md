# Every key a button: implementation plan

> At the owner's request (2026-10-21, on board K2: "K2 is perfect for the buttons. I want you to go ahead and
> immediately begin implementing this."). Their request: "turning each of the letters that we are displaying into
> buttons that we can press, and the ability to navigate between the different buttons with my arrow keys or to click
> on them, and pressing enter will then be the same as clicking the button or pressing the corresponding key." The
> files, interfaces and tests by name and intent; the code is in the commits.

**Goal:** [design 0011](../design/0011-the-consoles-look.md) §12: every key the console shows is a button, pressed by
Enter or Space while it has the focus, by its key from anywhere, or by a click, all three through one door; Tab moves
between groups, the arrows inside one; boards K1 (the behavior) and K2 (the look) built, K3 and K4 followed where §12
says so.

**Architecture:** `clank/console/buttons.py` holds the group, `Buttons`: one widget that takes the focus, a row or a
column of `Button`s (a `PageKey` and the words it shows), with its own cursor, drawn as text by pure functions
(`button`, the six states' spans; `lay_out`, the lines and each button's cells for a width). Its keys are its own
handlers (never priority bindings): along its axis it moves and stops at its ends, across a row it goes to the nearest
group above or below, Home and End, Enter and Space press, Esc goes back to the page's main list. A press goes through
a callback: the console's one door by default, `ClankConsole.press_key`, which runs a key that acts anywhere as its
binding's action and a page's key through `press_page_key` (`Page.unable`, then `Page.press`, then the pressed flash on
every group that shows the key), which `on_key` and the digits' `action_key` take too. `KeysBar` becomes a `Buttons`
whose layout is §7's (`fit_keys`, the palette at the right). The message line says what the focused button does
(`ClankConsole.hint`); `?` explains it. This folder places three groups from its `KEYS`; a question's options are a
group wherever a question shows; the windows that ask first and the details window have theirs.

**Tech stack:** Python 3.12, Textual 8.2.8 (its focus chain, mouse events and `Content` with the theme's variables),
pytest; the console's test kernel (`tests/console/conftest.py`).

**Spec:** [design 0011](../design/0011-the-consoles-look.md) §12 (and §2, §7, §9 it builds on); decisions
[0120](../decisions/0120-every-key-is-a-button-of-one-group-widget.md),
[0121](../decisions/0121-how-the-focus-moves-between-buttons.md) and
[0122](../decisions/0122-a-buttons-states-are-colors-of-the-style.md); boards K1-K4 in
[boards/](../design/boards/README.md).

## Global Constraints

- Nothing runs a model, the GPU, Docker, the service on its port or the gateway on its port; nothing opens a window:
  the console's test kernel and headless Textual only.
- No new dependency. Tests first, each test file's docstring naming the design sections it verifies, test names
  sentences. The owner is the sole author of every commit, no trailer; files staged by name. Not pushed: a review comes
  next, and the branch is rebased onto the cloud branches when they land.
- No color written outside the style (decision 0044); frames at 128, 88 and 60 columns where a group is new; every
  rewritten snapshot read before its commit.

## Claude's calls (2026-10-21)

Decisions 0120-0122 record the main ones. Also:

1. **The pressed flash** shows on every group that shows the key, whether a click, Enter or the key typed pressed it.
2. **A group's cursor** stays where it was when its buttons change (clamped to their number), so a page that draws
   again does not move it.
3. **The hover** is cleared when the mouse leaves the group; it never moves the focus.
4. **The message line's hint** has no time before it (it says what is, not what happened), and is cleared only when
   no message came since it was drawn.
5. **Main list**: the first of the page's stops that is not a group, else its first stop.

## Tasks

### Task 1: The style's five button colors

- [x] **Files:** `clank/kernel/console_kinds.py` (`StyleColors`: `button_hover`, `button_focused`,
  `button_focused_text`, `button_pressed`, `button_unable_focused`); the generated schemas.
- [x] **Tests first** (`tests/console/test_console_style.py`, design 0011 §12.8): Clank's style has the five with the
  boards' values, each a `$clank-` variable of the theme; a style file may set them.

### Task 2: A button's text in its six states

- [x] **Files:** `clank/console/buttons.py` (`Button`, `State`, `button`).
- [x] **Tests first** (`tests/console/test_buttons.py`, design 0011 §12.2 and §12.8): a button is its key and its
  words with a blank cell at each side; normal, hover, focused, pressed, unable and unable-focused draw the same cells
  in the table's elements, the fill covering the blank cells; on the keys bar its words are `quiet`, in a panel `text`.

### Task 3: A group's lines for a width

- [x] **Files:** `buttons.py` (`lay_out`: the lines and each button's cells).
- [x] **Tests first** (`test_buttons.py`, design 0011 §12.2 and §12.9): a row goes on to its next line between two
  buttons, never inside one; a column's button wraps its words under themselves; a lead's words come first and are no
  button; each button's cells are where its text is drawn, for a click.

### Task 4: The group: its focus, its keys, a click and the hover

- [x] **Files:** `buttons.py` (`Buttons`).
- [x] **Tests first** (`test_buttons.py`, design 0011 §12.3 and §12.4): in a small app of groups, ← → move in a row and
  stop at its ends, ↑ ↓ in a column; Home and End; ↑ ↓ across a row reach the nearest group above or below; Enter and
  Space press the focused button; a click presses it and moves the focus; the hover's ground under the mouse leaves the
  focus where it is; the focused button is drawn focused only while its group has the focus; a group in a list's row
  takes no focus; a group's cursor stays when its buttons change.

### Task 5: The console's one door, and a key that cannot act now

- [ ] **Files:** `clank/console/app.py` (`press_key`, `press_page_key`, `on_key` and `action_key` through it, the
  flash); `clank/console/pages/__init__.py` (`Page.unable`).
- [ ] **Tests first** (`tests/console/test_one_door.py`, design 0011 §12.3 and §12.7): a key typed and its button reach
  the same `press`; a key that acts anywhere runs its binding's action; a key that cannot act now says why and the
  page's `press` is not called, typed or pressed; a key of several says its keys; every group showing a key flashes
  `pressed` when it is pressed, by its key too.

### Task 6: The keys bar is a group

- [ ] **Files:** `clank/console/keys.py` (`KeysBar` a `Buttons`; `drawn` its layout).
- [ ] **Tests first** (`tests/console/test_keys_bar.py`, design 0011 §7 and §12.1-§12.4): the keys stand at the columns
  they stood at; Tab reaches the bar, last; → moves along it and stops at the palette; Enter, Space and a click press a
  key through the one door; ↑ and Esc go back into the page; the focused key is drawn in `button-focused`.

### Task 7: The message line and `?` on a focused button

- [ ] **Files:** `app.py` (`hint`, `action_explain`); `clank/console/clank.tcss` (`#message` on one row, cut).
- [ ] **Tests first** (`tests/console/test_one_door.py`, design 0011 §12.4 and §12.6): a focused button's words, what
  it does and its keys on the message line, a button that cannot act now's reason in `attention`; a message replaces
  it; leaving the groups clears it; `?` opens the details window about the focused button, and on the keys bar's own
  `?` about what had the focus before.

### Task 8: Where the focus goes

- [ ] **Files:** `app.py` (Enter on the menu, where each page was left, `main`, `into_page`).
- [ ] **Tests first** (`tests/console/test_arrows.py`, design 0011 §12.4 and §12.5): Enter on the menu goes into the
  page; → back into a page goes where it was left; Esc on a group goes to the page's main list; the console still
  starts on the menu, its ↑ ↓ opening pages.

### Task 9: This folder's groups

- [ ] **Files:** `clank/components/agents/console/folder.py` (the Next row, Then work's column and its settings row,
  `unable` for `e`, `m`, `p`, `r`, `w`, `i`).
- [ ] **Tests first** (`tests/console/test_folder_buttons.py`, design 0011 §12.1, §12.7 and §12.9): the groups and their
  keys, from `KEYS`; a click on `l` in the Next row loads a model as `l` does; the workspace's keys dimmed until it is
  opened, saying why; frames at 128, 88 and 60 columns (`folder-128`, `folder-88`, `folder-60`), nothing overlapping.

### Task 10: A question's options

- [ ] **Files:** `clank/console/pages/questions.py` (`OptionButtons`), `pages/home.py`, `folder.py`.
- [ ] **Tests first** (`tests/console/test_questions.py`, `test_home.py`, design 0011 §12.1): Home's and This folder's
  first question's options and `v` are a group that answers it; on the Questions page a click on another question's
  option highlights it and answers it, the list keeping the focus; snapshots `home-question` and `questions`.

### Task 11: The windows' buttons

- [ ] **Files:** `clank/console/confirm.py`, `clank/console/details.py`.
- [ ] **Tests first** (`tests/console/test_confirm.py`, `test_windows.py`, design 0011 §12.1 and §12.5): a window that
  asks first opens with the focus on "do it"; Enter does it once armed, never the Enter that opened it; → and Tab reach
  "leave it", which Enter presses; the details window's "close"; the windows' last line is their group.

### Task 12: The Monitor's Flow view at three widths

- [ ] **Tests first** (`tests/console/test_monitor_flow_buttons.py`, design 0011 §12.4 and §12.9): the Flow view's keys
  bar at 128, 88 and 60 columns holds its keys as before; Tab from its boxes reaches the bar and back; the boxes keep
  their arrows; Enter on the bar's `enter open` presses the view's Enter once.

### Task 13: The documents, and every check

- [ ] **Files:** `docs/console.md` (buttons, the keys that move and press), the generated documents, the roadmap, this
  plan's Built note.
- [ ] `uv run python -m tools.check` passes whole.
