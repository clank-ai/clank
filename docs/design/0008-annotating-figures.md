# Design 0008: annotating figures, and a model that reads images

The owner (2026-10-15): "the ability to add annotations to the plots that the model makes ... largely resemble the way
that ChatGPT figure annotation works ... This should not be a feature specific to the model, but we should also make
sure that this works when the model can look at images (either with something loaded on the GPU or some image model on
the CPU ...). Since I use my CPU for the simulations, I really only want the image model loaded when I am using it, and
I want the ability to fully disable/enable it as well as have it on some mode that only loads the image model when we
need it (and this should be the default ...)." The prototype had an annotator (pen and comment bubbles, design of
2026-10-08) that did not work as the owner wanted.

**Status:** written 2026-10-15, every section *proposed*, built as proposed at the owner's
instruction; **Choice** marks what the owner may decide otherwise.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What the owner gets | Proposed 2026-10-15 |
| 2 | What was learned | Proposed 2026-10-15 |
| 3 | A figure's geometry | Proposed 2026-10-15 |
| 4 | A mark in words | Proposed 2026-10-15 |
| 5 | Sending to the agent | Proposed 2026-10-15 |
| 6 | The annotator in VS Code | Proposed 2026-10-15 |
| 7 | The vision model and its modes | Proposed 2026-10-15 |

## 1. What the owner gets

A figure (PNG or JPEG) in Clank's VS Code window opens in the annotator: the figure, a few drawing tools (pen, box,
circle, arrow, text) in a few colors, and under it a message box like ChatGPT's. The owner circles what matters, each
mark numbered as it is drawn (1, 2, ...), writes what to do ("make 1 a log scale; why does 2 dip?") and sends it
(Enter). The agent of the workspace receives, in its session:

- the figure's path and the marked-up copy;
- each mark in the figure's own terms: the plot it is on, its range in data coordinates, the lines it touches, the
  text under it (§3, §4), so a model that cannot see images still knows what was marked;
- the marked-up copy as an image when the agent's model can see images, else, unless vision is off, what the vision
  model read in it (§7);
- the message.

The agent changes the script, renders the figure again, and the annotator shows the new version.

## 2. What was learned

- **ChatGPT.** Its mobile app's markup draws on the image before it is sent: the marks are in the picture the model
  sees, and the words go beside it. OpenAI documents nothing more; a proposal on its forum keeps the marks as a second
  layer of shapes and coordinates for the model, beside the image. Clank does both: the marked-up picture, and the
  marks in words.
- **Drawn marks work.** Models that see images follow marks drawn on them (a red circle directs attention, Shtedritski
  et al. 2023; "visual referring prompting" in the GPT-4V report), and numbered marks let the words name them
  (Set-of-Mark prompting). So marks are numbered, in a color that stands out, with the number drawn beside each.
- **OpenCode 1.19** takes an image as a message part (`{"type": "file", "mime": "image/png", "url":
  "file:///workspace/..."}`): it reads the file and sends it to a model that takes images as a data URL, after a line
  saying the file was read (checked 2026-10-15 with a scripted model).

## 3. A figure's geometry

A picture alone says nothing about the data. When Matplotlib saves a raster figure (PNG, JPEG) anywhere in the folder
of a workspace's container, Clank writes its geometry beside the folder's other notes, in
`.clank/figures/<path of the figure>.json`: the image's size and checksum; for each plot (axes) its box in the image's
pixels, its data limits and scales (linear or log), its title and axis labels, its lines and scatters (label, color,
their data, at most 400 points each; a line with error bars is one line, named as its legend names it) and
its legend's entries and box. The sandbox image puts a small
`sitecustomize` on every Python's path (`PYTHONPATH=/opt/clank/python`) that wraps Matplotlib's `Figure.savefig`
when Matplotlib is imported: no script, no agent and no prompt has to know. A figure without geometry (made by another
tool, or saved before) is still annotated, its marks given in the image's own terms; geometry whose checksum no longer
matches the image is not used.

## 4. A mark in words

Each mark becomes a sentence: its number, kind and color; the plot it is on (its title, or its place among the plots);
its range in data coordinates on each axis (in the axis's own scale); the lines and points inside it, with their
labels and the range of their values there; for an arrow, what its tip points at (the nearest line, the legend, a
title or a label; a tip that stops within 30 pixels of a legend points at it, unless a line is nearer); for a text
mark, its words. Outside any plot, the element under it (the legend, a title, an axis
label), else its place in the image ("upper right"). For example: *Mark 1 (red circle) on "MSD vs time" (left plot):
time 0.12 to 0.18, MSD 2.1 to 4.0; inside it, "n = 16" (5 points, MSD 2.3 to 3.9).*

## 5. Sending to the agent

The annotation is kept in the folder's `.clank/annotations/` (the marks, the message and the words as JSON, the
marked-up copy as PNG; `.clank/.gitignore` keeps git out), then sent as a message to the workspace's agent: to the
session most recently active among the OpenCode servers in its container (the one in the window's terminal, as a rule).
The marked-up copy goes as an image part when the main slot's preset can see images and vision is not off. Nothing is
sent while no agent runs: the annotator says to start it (`c` or `a`).

## 6. The annotator in VS Code

A custom editor of Clank's extension for PNG and JPEG files, the default for them in Clank's VS Code window (its
settings' editor associations) and an "Open With" choice elsewhere. Tools: pen (the default), box, circle, arrow, text;
four colors (red first); undo, redo, clear; the figure fit to the window, zoom with Ctrl and the wheel. A note (the
text tool) is a bubble tied to a pin, as a comment is in ChatGPT's figures (the owner, 2026-10-15: "a little bubble that
pops up so that nothing trails off the screen", moved "without changing the position of the marking point"): a click
puts the pin (the mark's number) where the note is about and opens a bubble beside it to write in, its words wrapped
(Enter keeps it, Shift+Enter starts a new line, Escape drops it). The bubble is white, edged in the note's color, with a
thin line to its pin, and is always kept on the figure. Dragged, only the bubble moves (`bubble`, its top left corner,
kept with the mark for the marked-up copy; the agent is told the pin's place); a click on it edits the note, and a note
emptied goes. The composer under the figure: Enter sends, Shift+Enter starts a new line. After a send the marks are cleared and the message says
where it went; when the figure's file changes (the agent re-rendered it), the new version is shown.

## 7. The vision model and its modes

A small model that reads images runs on the CPU in a slot of its own, `vision` (port 18202, role `vision` in the
gateway): llama.cpp's CPU build (decision 0035's engine) with **Qwen3-VL** and its projector (**Choice**: the 2B or the
4B, chosen by the measurement). It is used to read a marked-up figure for an agent whose model cannot see images, and by
the agent's tool `look_at_figure` (Clank's own MCP server), to check a figure it made. The `vision` settings choose:

- **off**: no image is read: the vision model is never loaded, annotations go as words only, and the agent's model is
  told it takes text only;
- **on demand** (the default): the vision model is loaded when an image is to be read and unloaded after
  `idle_minutes` (10) without use, so the CPU is the simulations' the rest of the time;
- **always**: it is loaded with the service and kept.

The main model's own projector (its preset's `vision` option, now `cpu`) is separate: it reads images sent to the main
model, uses the CPU only while it reads one, and changes only when the main model is loaded again (Launch options).
