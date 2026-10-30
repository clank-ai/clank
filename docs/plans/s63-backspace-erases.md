# Plan s63: Backspace erases; Esc goes back

Design 0011 §12.4 and design 0012's views, revised 2026-10-29 (decision 0151). The owner, testing Clank on Linux:
"backspace causing me to go back and now being used for me deleting things I am typing is a very, very big issue and
has not been caught. Going back in the clanker menu should be esc while backspace is reserved for actually erasing
things."

## What exists

- Decision 0129: Esc goes to the menu from anywhere in a page; Backspace is the step back inside a page (the Monitor's
  Context view and a box's session, the Flow view's boards D2-D4, Add a model's steps).
- `ClankConsole.on_key` gives a page every key the focused widget did not take. A text field takes Backspace, Delete,
  Home, End and the arrows through its bindings, which Textual checks after the handlers: the page heard them first.

## Tasks

- [x] 1. A failing test first (`tests/console/test_backspace_erases.py`): a field's own keys on a page and in a window
  never reach the page; Add a model's search, its key's field and a setting erase, the step staying; Backspace outside
  a field does nothing; Esc leaves the search, then goes back, then to the menu; the keys bar says `esc back`; no page
  declares Backspace.
- [x] 2. `field_keys` in `clank/console/app.py`: the keys a focused `Input` or `TextArea` binds (but Enter, Tab and Esc)
  are left to it. The key's hidden field takes Backspace even when empty.
- [x] 3. The steps back move to Esc: Add a model (every step with one, the agreement too), the Monitor (the Context view,
  a box's session; its keys bar shows `esc back` only when there is a box to go back to), the Flow view's boards. The
  keys bar shows a page's `esc back` in place of `esc menu`; Help's moves say what Esc and Backspace do.
- [x] 4. The console's tests that went back with Backspace go back with Esc; the frames rewritten and read (only the keys
  bars and Help's words changed).
- [x] 5. Records: decision 0151 (0129 superseded in part), design 0011 §12.4, design 0012's views, `docs/console.md`.

## Progress

Written and built 2026-10-29, for 0.3.0b6.
