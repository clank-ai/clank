# 0120. Every key the console shows is a button of a group: one widget that takes the focus, pressed through the same door as its key

- Status: Accepted (Claude's call; the owner may change it)
- Date: 2026-10-21
- Decided by: Claude, writing [design 0011](../design/0011-the-consoles-look.md) §12 after the owner approved board K2
  ("K2 is perfect for the buttons. I want you to go ahead and immediately begin implementing this.")

## Context
- The owner asked that each key the console shows become a button: pressed by a click, by Enter once the arrows reach
  it, or by its key, all three the same.
- Each page declares its keys once (`Page.KEYS`, decision 0046), and the keys bar, Help and `?` read that declaration.
  A key typed reaches the page's `press` (`ClankConsole.on_key`); a click on the keys bar simulated the key.
- Textual's `Button` is three rows tall with a border, and each one is a stop of its own for Tab: a keys bar of eleven
  keys would be eleven Tab stops and three rows.
- The console's lists (ListView, the Flow view's boxes) already move with the arrows and take the focus as one widget.

## Decision
- **A group of buttons is one widget** (`Buttons`, `clank/console/buttons.py`) that takes the focus, a row or a
  column with its own cursor, drawn as text: each button its key and its words with one blank cell at each side. The
  keys bar is one; a panel's actions, a question's options and a window's keys are others. A group inside a list's row
  takes no focus and is only clicked.
- **Its buttons are the page's declared keys**: the keys bar's from `shown_keys()`, a panel's chosen by key from
  `KEYS` (its words may be longer there), a question's from its options; a window's are its bindings.
- **One door**: Enter, Space and a click on a button, and the key typed, all reach the same handler: a page's key
  `ClankConsole.press_key` (the page's `press`, after `Page.unable`), a key that acts anywhere its binding's action, a
  window's key the window's action. No button holds an action of its own.

## Alternatives considered
- **Textual's `Button`**: three rows and a border each, and one Tab stop per button; it would change every page's
  height and the keys bar's single row.
- **Clickable text** (Textual's `@click` links in a label): no focus and no arrows, so Enter could not press it.
- **Buttons made by each page**: a second way for each page to act on a key, and code on every page; the keys bar
  alone already gives every page its buttons.
- **A click that simulates the key** (as the keys bar did): Enter on a button whose key is Enter would press itself
  again.

## Consequences
- Every page has buttons on its keys bar without code of its own; a panel's buttons need only the keys it shows.
- A key typed and its button can never differ, and a button that cannot act now says the same as its key
  (`Page.unable`).
- The keys bar takes the focus, so Tab reaches it, last in the screen's order.
