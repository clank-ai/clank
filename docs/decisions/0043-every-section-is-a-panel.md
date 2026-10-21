# 0043. Every section of every page is a panel: one widget, drawn as a box with its title in its border

- Status: Accepted (the owner approved design 0011 on 2026-10-18); for the windows, its "never cut" is superseded by
  [0081](0081-a-windows-long-title-is-cut-in-its-border-and-shown-whole-inside.md)
- Date: 2026-10-18
- Decided by: the owner, approving [design 0011](../design/0011-the-consoles-look.md) ("Approve all three", the
  remaining Choices as recommended)

## Context
The owner (2026-10-18): "I really like the individual boxes for each thing that you have"; "Separating things into
these blocks should in principle make Clank easier to work on as well, since we need to make sure everything is
expandable"; and, on board A, "make sure that everything is lined up properly". Design 0001 §5.6 meant the screens to
be "all made of panels". Today 37 sections in 17 files are plain containers drawn by one style rule, `.section` in
`clank.tcss` (a top border and a margin), and nine places, such as the list of Questions, sit outside any section.

## Decision
Every section of every page, the machine column's two, each window, and later the Monitor's and the Flow view's, is a
`Panel` (`clank/console/panel.py`), drawn as a box (design 0011 §4):
- its title in its top border at the left, bold, in `title`, never cut: no panel is narrower than its title;
- an optional key letter after the title, where the page's own keys leave it free, which moves the focus inside;
- an optional note at the right of the top border, dropped first when the panel is too narrow for both;
- its content inside one column of padding, clipped by its border; nothing of a page outside a panel, but a page with
  views (the Monitor) keeps its row of tabs and one heading line;
- `border-focused` on the panel with the focus only; Tab and Shift+Tab go from panel to panel in reading order;
- panels in a row (`PanelRow`) share its height, and every title starts at the same column;
- a stable id: each page declares its panels as an ordered list of ids and draws them in that order.

The shell needs nothing per page to draw them. A border changes only when the focus moves; the look adds no
animation. "Box" names the drawing only: in flows (design 0013) a box is a step of a flow.

## Alternatives considered
- **A style rule on plain containers, as `.section` is today.** Each page would arrange its titles, notes, widths,
  focus and order itself, as the nine places outside any section show; one widget keeps those rules in one place, for
  every page, the Monitor's and the Flow view's too.

## Consequences
- R2 makes the 37 sections panels, titled from design 0011 §8, and gives the nine places theirs; R3 to R7 arrange each
  page as its board does. Each step rewrites the text snapshots it changes, read before the commit.
- A panel costs four columns and a row more than a section: text inside wraps four columns sooner. Panels side by side
  stack in reading order when the page cannot give each its least width; when one panel does not fit, the page
  scrolls sideways rather than cut a title.
- The machine column becomes two panels, and its class `Monitor` becomes `MachineColumn`: F10's page is the Monitor.
- The ids let M2's Layout page (design 0001 §5.5) later show and rearrange the panels from `console.json`.
- The Monitor (design 0012) and the Flow view (design 0013) are built of panels, so R1 and R2 come first.
