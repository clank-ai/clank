# 0136. The board's canvas is Clank's own

- Status: Proposed (with design 0022, 2026-10-26)
- Date: 2026-10-26
- Decided by: Claude (proposed; the owner approves design 0022)

## Context

Design 0022 gives the owner and the agent a board: a canvas in VS Code where figures, LaTeX, notes, frames, slots and
annotations are placed, moved and asked about. The agent edits it through tools that place things by where ("below
fig-2"), and the file is JSON in the folder, so the board's item model must be Clank's. Whiteboard libraries exist.

## Decision

The canvas is written in Clank's extension, as its other webviews are: items are positioned elements on a pannable,
zoomable surface, annotations an SVG layer over them, and the item model is the board file's own (design 0022 §1). It
uses only what Clank already keeps: KaTeX for math (decision 0135) and the TeX layer for compiled LaTeX (decision 0134).

## Alternatives considered

- **tldraw**: the closest to what is wanted, but its license asks for a paid key to run without its watermark in
  production, it is React, and its store is its own: the agent's placements and the board file would be translated into
  and out of it.
- **Excalidraw**: MIT, but React and a large bundle, a hand-drawn look the owner did not ask for, no LaTeX, and its own
  scene format.
- **Fabric.js or Konva** (canvas drawing): text and math on a 2D canvas lose selection and KaTeX's layout, and the
  owner's figures would be redrawn rather than shown as files.

## Consequences

More of Clank's own code to keep (selection, snapping, pan and zoom, the pen), tested in headless Edge as the other
pages are. No new dependency, no license to track, nothing from the network, and the board looks like the rest of
Clank in every theme.
