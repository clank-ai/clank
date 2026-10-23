# 0130. The Flow view's boxes come in three sizes, medium unless set; the Monitor opens on the Flow view

- Status: Accepted (the owner's request of 2026-10-22, built as Claude's call)
- Date: 2026-10-22
- Decided by: Claude, at the owner's request

## Context
- The owner, watching a run over SSH with the terminal as large as the screen: "the individual blocks in the Flow chart
  are not easy to read and I should have the ability to make this larger so that each of the individual boxes are a
  bit more fleshed out." A wider window gave more boxes to a row, each still 22 to 30 columns and six rows, the title
  cut after a few words.
- The same evening the owner opened the Monitor and found the Session view, not the website's look: the Monitor opened
  on Session the first time (board A, chosen before the website), and F10, which moves between its views, is kept by
  many Linux terminals for their own menu.

## Decision
- **Three sizes** (`boxchart.SIZES`): small (22-30 columns, six rows: its tag, title, model and last result, as
  before), medium (32-44 columns, eight rows: the title over two lines, and its tries, time and tokens, or what one try
  may use before it ran) and large (44-64 columns, ten rows: the title over three lines, and the files it writes or
  the box it checks). A panel too narrow for two boxes of the size asked draws the largest that keeps two (a
  DECOMPOSE and its tasks stand side by side).
- **`+` and `-`** on the Flow view pick the size, drawn again at once and kept in the console's settings
  (`flow_boxes`, medium unless set), so the console opens with them.
- **The Monitor opens on the Flow view**, the website's look; Session and Context are a tab or F10 away.

## Alternatives considered
- **Boxes as wide as the row allows**: a wide window would stretch eight boxes across it; the size is the owner's to
  pick, and a fixed size reads the same in every window.
- **Small unless set**: the owner asked for larger; medium fits two to a row from 70 columns.

## Consequences
- The Flow panel is taller with medium and large boxes; it scrolls, at most 60% of the window high (decision 0125).
- The Monitor's frames show the Flow view first.
