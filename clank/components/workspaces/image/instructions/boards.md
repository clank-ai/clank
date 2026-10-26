# Boards

A board is a canvas you share with the user: a `.board` file in the folder, open in their VS Code window. You place
figures, LaTeX, notes and frames on it; the user moves them, draws on them, pins comments and asks you about what they
select. Use one when the user wants to lay out figures (a paper's figure, a talk's slide, a comparison), or asks for
a board.

Work on it only through Clank's tools, never by editing the file: `board_read` first (it says every item with its id,
and the user's pen marks, arrows, highlights and pins by what they are over), then `board_add`, `board_update` and
`board_remove`. Place by where, never by pixels: `{"below": "fig-1"}`, `{"right_of": "latex-2"}`, `{"in": "frame-3"}`,
`{"slot": "slot-4"}`. Clank aligns the item with its neighbor, keeps it clear of the others and grows a frame to hold
it.

- A **figure** is an image file of the folder: make it first (a script; a job for a long one), then add it. When a
  script writes the same file again, the board shows the new figure by itself.
- **LaTeX**: math (`mode` math, without `$`) for an equation or a derivation; `mode` compiled for TikZ, pgfplots or a
  table, built with the folder's TeX.
- A **slot** is a place the user drew for a figure: when asked to fill one, make the figure and add it with
  `{"slot": id}`; it takes the slot's place and size.
- A **frame** groups items under a name (Figure 3) and exports as one figure for a paper: `board_export` with the
  frame makes a PDF (or PNG, or SVG) beside the board, its LaTeX typeset by TeX; `keep` true makes it again each time
  the frame changes. Notes, slots and the user's marks are left out of it.
- A **pin** is the user's comment on an item: do what it asks, then close it (`board_update` with `open` false) and
  say in a line what you changed.
