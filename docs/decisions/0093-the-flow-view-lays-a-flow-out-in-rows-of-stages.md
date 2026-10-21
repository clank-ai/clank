# 0093. The Flow view lays a flow out in rows of stages, from what the service says of it, and shows its boards on the page

- Status: Accepted (Claude's call, 2026-10-20, building design 0013's step 6; within design
  0013 §12, approved by the owner on 2026-10-18)
- Date: 2026-10-20
- Decided by: Claude, building [plan s28](../plans/s28-flows-the-flow-view.md); the owner reviews it with the step

## Context
Design 0013 §12 asks the Monitor's Flow view to draw a flow's boxes and lines as board D1 does, to hold at 128 and 88
columns and below 70, and, at the owner's comment on the prototype, never to let a box, a line's label or the legend
overlap another or leave its panel, over flows of 1 to 12 tasks, with proposals waiting, a fail loop, an added box and
the next flow (§14 step 6). Board D1 was arranged by hand for one flow: its first four boxes in a row, its tasks in a
column under it, its gate below INTEGRATE. Boards D2, D3 and D4 are drawn as whole pages under the Monitor's tabs.
What the view shows (each box's state, tries and verdicts, the lines that ran, the brief checked, what is ahead) needs
the runner's rules: which box wrote a file, what a fail line carries, which proposals would join where.

## Decision
- **What the view shows is made in the service** (`clank/components/flows/view.py`, `GET /flows/view`), as a session's
  flow is ([decision 0049](0049-a-sessions-flow-is-built-in-the-service.md)): the console draws it knowing none of the
  runner's rules, and the phone can draw it later. A version (its fingerprint) lets a client draw nothing when it did
  not change.
- **A flow is laid out in stages, in rows that wrap** (`clank/components/agents/console/boxchart.py`): a stage is one
  box, or a DECOMPOSE's tasks stacked as a fan; the stages read left to right as board D1's first row does, as many
  to a row as keep a box 22 columns wide, and wrap as D1 wraps its flow, a line from the row's last stage down and
  back to the next row's first. A DECOMPOSE stands with its fan. A VERIFY's fail line runs on a line of its own under
  its row, labeled, or is a label alone when the box it checks is in another row or in a fan. Every box is six rows,
  every label and the legend on lines of their own, so nothing can overlap; a flow taller than its panel scrolls.
  Narrower than 70 columns the flow is the list of board D2's left.
- **Boards D2, D3 and D4 are shown on the page**, in place of board D1's panels, under the same tabs and heading, as
  the boards draw them; Esc goes back to D1. The keys bar shows the keys of the view, or of the board, on screen.

## Alternatives considered
- **Board D1's arrangement by hand** (a first row, the tasks in a column under it): it fits the one flow it was drawn
  for. Placing boxes freely in two dimensions needs a layout engine that can route lines around boxes, and its edge
  cases (a fan beside a loop, a long chain) are where the owner found overlaps on the prototype.
- **One box a line at every width** (the list): it never overlaps, but it is not the chart the owner asked for, so it
  is kept for below 70 columns only, as §12 says.
- **The view assembled in the console** from the flow, its runs and its proposals: the console would repeat the
  runner's rules, and the phone could not show it without repeating them again.
- **Boards D2, D3 and D4 as windows over the page**: a window is at most 90 columns; D4's cards side by side and D2's
  two columns need the page, and their keys would then be the window's alone. On the page, the board's keys are routed
  by the Flow view while the board is shown.

## Consequences
- The layout's guarantees are tested over 144 generated flows at eight widths (`tests/console/test_box_chart.py`), and
  board D4's cards at six (`tests/console/test_monitor_flow_boards.py`).
- A flow that is long runs over several rows; its next row is a line away from the row before, not beside it.
- The Monitor's page declares its boards (`MonitorPage.BOARDS`), and the panels' test shows each board's panels.
- Board D1's free arrangement, or a layout that routes lines around boxes, would replace `boxchart.render` alone: the
  view's facts, the widgets and the tests of what must never overlap stay.
