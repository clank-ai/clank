# Plan s49: boards

Builds [design 0022](../design/0022-boards.md), approved by the owner on 2026-10-26: a canvas the owner and the agent
share, a file in the folder. Each task starts with a failing test; each ends with a commit pushed to `main`. The owner
asked for functional choices to be made while building; each is recorded in the design section it changes.

## The board file

`<name>.board`, JSON, two-space indented, the items in the order they are drawn (later on top):

```json
{
  "board": 1,
  "title": "Resonance",
  "settings": { "grid": 20, "preamble": "\\usepackage{amsmath}\n\\usepackage{siunitx}" },
  "items": [
    { "id": "fig-1", "kind": "figure", "x": 80, "y": 80, "w": 360, "h": 240, "file": "figures/amp.png",
      "caption": "(a) Amplitude", "by": "agent" },
    { "id": "latex-2", "kind": "latex", "x": 80, "y": 360, "w": 360, "h": 80, "source": "A(f) = ...", "mode": "math" },
    { "id": "note-3", "kind": "note", "x": 480, "y": 80, "w": 280, "h": 160, "text": "**Why** ..." },
    { "id": "frame-4", "kind": "frame", "x": 60, "y": 60, "w": 720, "h": 420, "name": "Figure 3",
      "export": { "file": "figures/fig3.pdf", "width_cm": 17.8, "keep": true } },
    { "id": "slot-5", "kind": "slot", "x": 480, "y": 280, "w": 280, "h": 200, "label": "phase", "state": "open" },
    { "id": "pen-6", "kind": "pen", "points": [[100, 100], [140, 90]], "color": "ink" },
    { "id": "arrow-7", "kind": "arrow", "from": { "item": "note-3" }, "to": { "item": "latex-2" } },
    { "id": "mark-8", "kind": "highlight", "x": 120, "y": 100, "w": 80, "h": 40 },
    { "id": "pin-9", "kind": "pin", "x": 230, "y": 96, "text": "Mark Q here", "open": true }
  ]
}
```

Ids are a kind and a number, the next number one more than the highest. What is inside a frame, and which item an
annotation sits on, follows from where they are (an item inside a frame's rectangle moves with it; a pen stroke,
highlight or pin over an item moves with the item), so neither is kept twice. Figures name their file; nothing is
copied. The agent's changes are written by the service (read fresh, changed, written whole, a copy of the board before
each kept in `.clank/boards/<name>/history/`); the owner's by the editor, saved as they are made.

## Tasks

- [x] 1. **Boards in the service** (`agents/boards.py`): the file read and checked, `new`, `describe` (the board in
  words for the model: each item with its id, kind, place, size and what it shows, what each frame holds, the open
  slots and pins, and the owner's annotations said by what they are over), `add`, `update`, `remove`, with history;
  figures sized from their files (PNG, JPEG, GIF, WebP, SVG). Placement (`boards_place.py`, pure): `at` is
  `right_of`, `left_of`, `below`, `above` (an item), `in` (a frame), `slot` (a slot, which the item then takes the
  place of), `{x, y}`, or nothing (the first free place); aligned with the item named, a gap of two grid steps, moved
  on until it overlaps nothing. Routes `POST /agents/boards` (new), `GET /agents/boards?workspace=`,
  `GET /agents/boards/read?workspace=&board=`, `POST /agents/boards/add|update|remove`; events
  `agents.board_changed`; `clank board new|list`.
- [x] 2. **The agent's tools**: `board_new`, `board_read`, `board_add`, `board_update`, `board_remove` in Clank's MCP
  server, forwarded by the gateway; the instructions (`boards.md`); the agent panel's line for each change.
- [x] 3. **The editor** (`clank.board`, a custom text editor for `*.board`): the pure part (`core/board.ts`: geometry,
  snapping, what moves with what, the operations) with Node tests; the page (`media/board.{html,js,css}`) with its Edge
  test: pan and zoom, figures, notes (Markdown), math (KaTeX), frames, slots, select, move, resize (a figure keeps its
  aspect), snap, align, delete, duplicate, nudge, the toolbar's tools, files dropped and images pasted; saved as made;
  VS Code's undo and redo; the agent's changes drawn when the file changes.
- [x] 4. **Annotations and asking**: pen, arrow, highlight and pin; select-and-ask, Fill a slot, Send pins, each a
  message to the agent's session naming the items.
- [x] 5. **Compiled LaTeX**: `POST /agents/boards/latex` builds a `standalone` document with the board's preamble in
  the folder's container (the TeX layer), pdfLaTeX then `pdftocairo -svg`, glyphs flattened, kept by the source's hash
  in `.clank/boards/<name>/latex/`; a LaTeX item in `compiled` mode shows it, or its error.
- [x] 6. **Export**: a frame or the selection to SVG and PNG (made in the page), and to PDF (a `standalone` LaTeX
  document placing the figures and the LaTeX, built in the container); kept exports made again when the frame changes.
- [x] 7. **Live**: the real model, in a throwaway folder, adds figures and an equation, fills a slot the owner drew and
  answers a pin; a frame exported to PDF; seen in screenshots of that window only.
- [ ] 8. **Documentation**: getting started, the extension's README, the roadmap, and the website.

## Progress

Written 2026-10-26.

- Tasks 1-4 built and pushed 2026-10-26 (the service, the agent's tools, the editor, annotations and asking).
- Task 7, first half: the real model made a board in a throwaway folder (two plots side by side, the period formula
  under them, all framed as "Figure 1") with the tools alone. The editor had opened it at 10 %: it was fitted while its
  tab was behind another and had no size. Now a fit waits for a size, and the view follows what the agent places until
  the owner pans or zooms (fitting follows again).
- Task 5 built: compiled LaTeX (`boardlatex.py`). Found while building: this TeX layer's `pdftocairo` writes sizes
  without units (points still), and the agent should hear at once whether its TikZ builds, so `board_add` and
  `board_update` of a compiled item build it, size it from its drawing and say so, or say LaTeX's error.
- Task 6 built: export (`boardexport.py`, decision 0137). Measured first: librsvg keeps a nested `<svg>` vector in the
  PDF but makes an SVG given as an `<image>` pixels, so the export nests each figure with ids of its own. The TeX layer
  adds `librsvg2-bin`; a real build in it (`tests/docker/test_board_layer.py`) compiles a pgfplots drawing at its own
  size and exports its frame as a PDF with no pictures in it. Found there: a plot on a board with no preamble failed, so
  pgfplots and booktabs load by default. The agent has `board_export`; the owner's Export asks for the format and once
  or kept; kept exports are made again by the service after the agent's changes and by the editor after the owner's.
  Fixed on the way: `test_sessions`' list of the agent's tools had not been given the board tools.
- Task 7 done (2026-10-26, frontier 262K fast, the throwaway folder, driven through the service with the editor's
  messages word for word): a slot drawn below the tables was filled (`fig-13`, a new decay plot, placed in the slot,
  which it took; 226 s with the model's script); a pin on `fig-1` ("label both axes with their units") was answered
  honestly: the model looked at the figure with vision, found the units already there, closed the pin and said so
  (146 s); `board_export` with `keep` made `figures/figure-1.pdf` (31 KB, one page, no raster image in it: the plots,
  the tables, the formula and the new plot as placed) and the frame remembers it (29 s). Found: the model still wrote
  its SVG by hand, since its session's history said Matplotlib was missing (it is there since decision 0138): the
  board instructions now say what the container has. Sends took 3 to 12 s through the bridge (design 0023).
