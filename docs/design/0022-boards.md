# Design 0022: boards, a canvas the owner and the agent share

Part of Clank Code ([design 0018](0018-clank-code.md)), beside artifacts ([design 0021](0021-all-llm-work-in-clank.md)
§5). Asked for by the owner on 2026-10-26: "One of the major things the artifacts that we are building need to include
is the ability to create an "artboard" where I can have the model add figures onto the board and where I can organize
different things, and it should have the ability to write latex on this artboard and I need the ability to move
things around on the board and to annotate things and ask the model to place certain figures in certain places."

An artifact (§5 of design 0021) is a page the agent makes and the owner comments on. A board is a place both work on:
the agent puts figures, LaTeX and notes on it, the owner moves them, annotates them, and asks for more, in VS Code,
on this PC. Proposed 2026-10-26, drawn on the design canvas (page "Boards"), and approved the same day: "I will
step away from the computer so that you can begin building the board. Note that this board needs to be fleshed out
some more while you are building it, so while you are testing things I want you to take the liberty to make any
functional design choices that I could use". The choices made while building are recorded in the sections they
change, each marked as added while building.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | A board is a file in the folder | Approved 2026-10-26 |
| 2 | What a board holds | Approved 2026-10-26 |
| 3 | The owner on the board | Approved 2026-10-26 |
| 4 | The agent on the board | Approved 2026-10-26 |
| 5 | Asking the agent about the board | Approved 2026-10-26 |
| 6 | LaTeX on the board | Approved 2026-10-26 |
| 7 | A board's figures out: export | Approved 2026-10-26 |
| 8 | Order of work | Approved 2026-10-26 |

## 1. A board is a file in the folder

A board is `<name>.board` anywhere in the folder (`figures/resonance.board`), JSON the owner can read, diff and keep
in git: its items, each with an id, a kind, a place and a size on the board, and what it shows; its frames; its
annotations; its settings (the LaTeX preamble, the grid). Figures are not copied into it: an item names its file, so a
figure a job writes again is drawn again on the board. What the agent changes is kept as history beside it
(`.clank/boards/<name>/history/`), one step per change, so any of its changes can be taken back.

It opens in VS Code as a document of its own (a custom editor for `*.board`) in the files' group, beside the agent: it
saves itself as the owner works, takes VS Code's undo and redo, and draws a change the agent made the moment the file
changes. `clank board new NAME` and the agent's `board_new` make one; the console and the phone list a folder's boards
and show them read-only.

## 2. What a board holds

- **Figures**: an image of the folder (PNG, JPEG, SVG, a page of a PDF), at its own aspect, with an optional caption.
- **LaTeX**: an equation, an aligned derivation, a table, a TikZ or pgfplots drawing (§6), drawn on the board and kept
  as its source.
- **Notes**: Markdown with math, for the reasoning between figures.
- **Frames**: a named region ("Figure 3") that holds what is inside it, moves it as one, and exports as one figure (§7).
- **Slots**: an empty, labeled place ("residuals vs time") for the agent to fill (§5).
- **Annotations**: the owner's pen strokes, arrows (from one item to another, or to a point on one), highlights, and
  pins with a comment for the agent (§5). Annotations sit over the items, and stay with them when they move.

## 3. The owner on the board

A canvas to pan and zoom (the wheel, the space bar held), with the items as they are drawn:

- **Select, move, resize**: click, drag, a box around several, Shift to add; handles keep a figure's aspect; items
  snap to the grid and to each other's edges and centers (Alt to place freely); align and spread a selection.
- **Make**: a toolbar of text (a note), LaTeX, frame, slot, pen, arrow, highlight and pin; a file dragged from the
  Explorer or an image pasted becomes a figure where it is dropped.
- **Edit in place**: a double click opens a note's Markdown or a LaTeX item's source beside its drawing, drawn again as
  it is typed (math at once, a compiled drawing when it builds).
- **Keys**: Delete, Ctrl+D (duplicate), Ctrl+G (group into a frame), arrows to nudge, Ctrl+Z and Ctrl+Y, 0 to fit the
  board, 1 for its real size.
- The colors are the agent panel's theme tokens (design 0021 §4): VS Code's theme, or Clank Night.

## 4. The agent on the board

Clank's MCP server gives the agent the board as tools, so it never writes the JSON by hand:

- `board_read(board)`: every item with its id, kind, title, place, size and source; the frames and slots by name; and
  the owner's annotations in words ("a pen loop around the peak of fig-2", "an arrow from note-4 to fig-1", "a pin on
  fig-3: use a log scale").
- `board_add(board, kind, source, at)`: a figure, LaTeX or a note, placed by where, not by pixels: `at` is
  `{"right_of": id}`, `{"below": id}`, `{"in": frame}`, `{"slot": id}` or a free spot. Clank works out the place:
  next to its neighbor, aligned with it, clear of the others, at a size that fits.
- `board_update(board, id, changes)`: a new source, caption, size, or place (the same `at`).
- `board_remove(board, id)` and `board_new(name, folder)`.

Each change is one step of the board's history and comes into the owner's window at once; the agent panel says it as
one line ("Placed fig-5 in the slot 'residuals'").

## 5. Asking the agent about the board

- **Select and ask**: the owner selects items (or draws a pen loop) and writes what they want ("put the residuals
  under this, the same width"); the message goes to the agent's session with the items named by id and title, so the
  model knows exactly what "this" is.
- **Slots**: the owner draws a labeled slot where a figure should go; "Fill" asks the agent for it, and the agent makes
  the figure (a script, a job for a long one, design 0021 §6) and places it in the slot.
- **Pins**: a pin with a comment on an item is kept on the board; "Send pins" sends every open pin to the agent at
  once, and the agent's answer closes the pins it dealt with.

## 6. LaTeX on the board

Math is drawn at once with KaTeX (decision 0135): an equation, an `aligned` derivation, a matrix. Anything KaTeX cannot
draw (TikZ, pgfplots, a `tabular`, a package of the owner's) is compiled in the folder's container with the TeX layer
(design 0020, decision 0134): a `standalone` document with the board's preamble, built with pdfLaTeX and made into SVG
with `pdftocairo -svg` (the TeX layer's image has it; it has no `dvisvgm`, found 2026-10-26), each glyph flattened into
its own path drawn in the text's color, kept by its source's hash so it is compiled once. The design canvas's math was
made this way, from real LaTeX, after the owner found the first drawing's imitation of it "terrible" (2026-10-26). A LaTeX item says which it is ("math" or "compiled"), shows its error under it
when it does not build, and keeps its last drawing until it does.

## 7. A board's figures out: export

A frame (or a selection) exports as one figure for a paper or slides: SVG (figures that are vector stay vector, the
LaTeX as its SVG), PNG at a chosen resolution, and PDF made from the SVG in the container, at a paper's width (one or
two columns) or one of the owner's. The export is a file of the folder (`figures/fig3.pdf` beside the board); doing
it again replaces it, and a frame can be kept exported (made again each time it changes), so a paper's
`\includegraphics` always shows the board's latest layout.

## 8. Order of work

1. The board file, its schema and history, and `clank board new`; the custom editor drawing figures, notes and math,
   with move, resize, snap, pan and zoom, autosave, undo and redo.
2. The agent's tools (§4), the placement by where, and the panel's line for each change.
3. Annotations, pins, slots and select-and-ask (§5).
4. Compiled LaTeX (§6) and frames with export (§7).

Each step has its plan, starts with failing tests, and ends with a live test: the real model places a figure the owner
asked for, in a throwaway folder, seen in a screenshot of that window only.

The canvas is Clank's own (decision 0136): no new dependency.
