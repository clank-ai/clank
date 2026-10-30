# 0151. Backspace erases and never moves you; Esc goes back, a step inside a page, then to the menu

- Status: Accepted (the owner's report of 2026-10-29: "backspace causing me to go back and now being used for me
  deleting things I am typing is a very, very big issue and has not been caught. Going back in the clanker menu should
  be esc while backspace is reserved for actually erasing things."); supersedes [0129](0129-esc-goes-back-to-the-menu.md)
  in part (its steps back on Backspace); revises design 0011 §12.4 and design 0012's views
- Date: 2026-10-29

## Context

- Decision 0129 made Esc go to the menu from anywhere in a page, and gave the steps back inside a page to Backspace:
  the Monitor's Context view back to the Session view, a session opened from a flow's box back to the box, the Flow
  view's boards D2-D4 back to D1, and Add a model's step before.
- A key the focused widget does not take goes to the page on screen (`ClankConsole.on_key`). A text field takes
  Backspace through its binding, and Textual checks bindings after a key's handlers, so the console's handler heard
  Backspace first and gave it to the page. On Add a model, Backspace in the models' search, in a setting, or in the
  key's hidden field once it was empty went back a step while the owner typed. Delete, Home, End and the arrows reached
  the page the same way, and so did the keys typed in a window's field: the page under the window heard them.
- No test typed in a field and erased.

## Decision

- **Backspace erases in a field you type in, and never moves you.** No page declares it as a key of its own; outside a
  field it does nothing. The key's hidden field takes it even when empty.
- **A field's own keys stay the field's.** The keys a text field binds (Backspace, Delete, the arrows, Home, End, its
  Ctrl keys) never reach the page, whether the field is on a page or in a window (`field_keys` in
  `clank/console/app.py`). Enter, Tab and Esc still do.
- **Esc goes back.** It takes a step back inside a page when the page has one (the four above), and the page's keys bar
  then says `esc back` in place of `esc menu`; else it goes to the menu, the page staying as it was (0129's rule). A
  window open closes first, and a field being typed in is left first, as before.
- **Tests that catch it.** `tests/console/test_backspace_erases.py` types and erases in a field on a page and in a
  window (both kinds of text field), in Add a model's search, in its key's field and in a setting, and checks that no
  page declares Backspace.

## Alternatives considered

- **Backspace for the steps back outside fields only**: the same key would erase in one place and go back in the next,
  and a field that loses the focus (a list redrawn under it) would turn an erase into a step back.
- **Esc always to the menu, the step back on another key**: Left already moves between a page's lists and the menu, and
  the owner asked for Esc.

## Consequences

- Going back is Esc, as in most programs. From a step inside Add a model, or the Monitor's Context view, the menu may
  take a second Esc.
- Keys bars show `esc back` where a page has a step back; no bar writes `bksp` any more.
