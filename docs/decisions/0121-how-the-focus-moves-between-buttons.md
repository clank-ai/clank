# 0121. Tab moves between groups, the arrows inside one and stop at its ends, and the lists keep their own keys

- Status: Accepted (Claude's calls on board K1, which the owner's approved K2 embodies; the owner may change any)
- Date: 2026-10-21
- Decided by: Claude, writing [design 0011](../design/0011-the-consoles-look.md) §12.4-§12.5 from boards K1 and K2

## Context
- The owner asked to "navigate between the different buttons with my arrow keys or to click on them".
- The console is keyboard-first: the arrows already move in the menu and the page's lists, and Right and Left move
  between the menu and the page's lists (design 0001 §5.1). An input takes the left and right arrows, Home and End.
- Textual's Tab and Shift+Tab move through the screen's focus chain, wrapping at its ends.
- A window that asks first opens on a key (Enter on a row) that must not press its "do it" (design 0012 §9.1).

## Decision
- **Tab, Shift+Tab**: the next and the previous group or list, wrapping (Textual's focus chain, unchanged).
- **Along a group** the arrows move its cursor and **stop at its ends**; Home and End go to its first and last.
  **Across a row**, ↑ ↓ go to the nearest group above or below on the screen; across a column, ← → are the shell's, as
  today. On the keys bar, ↑ goes back into the page.
- **Enter and Space** press the focused button; **its key** presses it from anywhere without moving the focus; **a
  click** presses it and moves the focus to it.
- **Lists keep their keys**: the groups' keys are their own handlers, never priority bindings, so a list, an input or
  the Flow view's boxes take their keys first and the arrows move between buttons only while a group has the focus.
- **Esc** on a group goes back to the page's main list (its first list, else its first group, else the page); in a
  window Esc stays the window's.
- **Where the focus starts**: the console on the menu, as today; →, Tab or Enter on the menu into the page, where it was
  left, else its main list; a window on its first button, which the key that opened it never presses (`armed`).
- **A button that cannot act now** is dimmed and still takes the focus, so the message line and `?` say why.
- **`?` on a focused button** opens the details window, as `?` does everywhere, rather than K2's message line; the
  message line already says what the focused button does.

## Alternatives considered
- **Arrows that wrap** at a group's ends, or that run on into the next group: the owner could not tell where a row ends.
- **A disabled button skipped by the focus**: nothing could say why it cannot act.
- **Arrows as priority bindings** of the groups: an input or a list beside a group would lose its own arrows.
- **The focus starting in the page** when the console opens: ↑ ↓ on the menu would no longer open the pages.

## Consequences
- Every existing arrow, Tab and Enter keeps its meaning where no group has the focus; Enter on the menu is new.
- A page's main list is found from its focus order; a page may later name its own.
