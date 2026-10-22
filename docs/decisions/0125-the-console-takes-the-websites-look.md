# 0125. The console takes the website's look: no menu beside the Monitor, the flow across the width, its colors

- Status: Accepted (the owner's request of 2026-10-22, built as Claude's call; the owner may change any of it)
- Date: 2026-10-22
- Decided by: Claude, from the owner's request: "make sure that we are designing Clank to look almost exactly what we
  have envisioned in the website"; the website's demo (`src/scripts/demo/views.ts` in the site's repository) is the
  reference

## Context
- The website draws the console's Monitor without the menu column ("left out, so the flow being designed has the
  pane's whole width (the owner's call)"), the flow across the whole width, and two panels under it.
- The console drew the menu beside every page, the flow beside four panels, and its own palette (blue titles, a purple
  ◆ CLANK, orange for what runs now). The owner found it "NOTHING like" the website, and no way to hide the menu.

## Decision
- **The menu column** is a page's setting (`Page.MENU_COLUMN`): the Monitor leaves it out; **Ctrl+B** shows or hides
  it on any page (`^b menu` on the keys bar, as VS Code's Ctrl+B its side bar); every page's key still opens it, and a
  hidden menu's focus goes into the page.
- **The Flow view's board D1**: the flow across the whole width (as many boxes to a row as fit), at most 60% of the
  window high (a taller flow scrolls in its panel); under it Selected (or Building it with the model) beside Waiting
  for you, then the Orchestrator (design 0013 §16) beside Models in this flow; then The brief, checked, Deliverables
  and Ahead.
- **The style's defaults take the website's colors**: titles in the text's color (#c0caf5) and bold, ◆ CLANK orange
  (#ff9e64), what runs now and the spinner teal (#73daca), quiet and the folder's name #9aa5ce, borders #414868, the
  selected text #e0e5ff. Keys, selection, good, attention and failed were the same already.

## Alternatives considered
- **Drawing a DECOMPOSE's tasks as one stacked box**, as the website does: it needs the chart's fan, its lines and the
  arrows' order reworked; kept for later, the flow's panel capped and scrolling meanwhile.
- **Hiding the menu everywhere**: the menu is how a new user finds the pages; the website shows the Monitor only.

## Consequences
- The Monitor's frames are 30 columns wider for the page; its tests count page widths with no menu.
- A style file that set the old colors keeps them; Clank's own style is its defaults.
