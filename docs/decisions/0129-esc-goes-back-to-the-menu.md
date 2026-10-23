# 0129. Esc goes back to the menu from anywhere in a page; a step back inside a page is Backspace

- Status: Accepted (the owner's request of 2026-10-22, built as Claude's call)
- Date: 2026-10-22
- Decided by: Claude, at the owner's request

## Context
- The owner (2026-10-22): "the navigation in Clank is not great. Unless otherwise stated (like when I am confirming
  something), the esc key should always bring me back to the Clank menu."
- Esc meant different things by place: on a row of buttons, the page's main list; on the Monitor's Context view, the
  Session view; on a session opened from a flow's box, the box; on the Flow view's boards, board D1; on Add a model, the
  step before; on History's filter, the menu; elsewhere, nothing. Beside the Monitor the menu is hidden (decision
  0125), so even Left could not show where it was.

## Decision
- **Esc goes to the menu** from anywhere in a page: the focus on the menu, its highlight on the page on screen, the page
  staying as it was (its view, its board, its unsaved edits). It acts anywhere, so it is on every keys bar, beside `?`
  and `f1`, its button pressed like any key's.
- **Beside a page that hides the menu** (the Monitor), the menu shows while it has the focus; ↑ ↓ in it pass the
  Monitor's entry without hiding it; going into the page (→, Enter, Tab) hides it again. Left from a page's first list
  goes to the menu the same way. The console still opens the Monitor at its full width.
- **What is "otherwise stated"**: a window (a question, a confirmation, a form, the details) keeps its Esc, which
  leaves it; a field being typed in (History's filter, Add a model's search) is left first. Each says so on its keys bar.
- **Backspace** is a step back inside a page: the Monitor's Context view to the Session view, a session opened from a
  flow's box back to the box, the Flow view's boards D2-D4 back to D1 (D2 asks first when a change is not saved), Add a
  model's step before. The keys bar writes it `bksp`.

## Alternatives considered
- **Esc one step back, then the menu**: as browsers' Back; the owner asked for the menu always, and a page's place is
  kept, so nothing is lost by going to the menu.
- **A key of its own for the menu** (Ctrl+B already shows or hides it): Esc is the key people press to get out.

## Consequences
- Every keys bar is a few columns fuller; on a narrow screen the page's own keys drop a little sooner.
- Tests and frames that pressed Esc to go back press Backspace.
