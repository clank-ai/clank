# 0137. A board exports through one SVG, made PDF or PNG by librsvg in the TeX layer

- Status: Accepted (building design 0022 §7, which the owner approved on 2026-10-26)
- Date: 2026-10-26
- Decided by: Claude, building design 0022 while the owner was away, as the owner asked ("take the liberty to make any
  functional design choices that I could use")

## Context

Design 0022 §7 exports a frame of a board as one figure for a paper: PDF for `\includegraphics`, PNG, or SVG, with
figures that are vector staying vector and the LaTeX typeset by TeX. The board's parts are figures (SVG from a script,
or pictures), LaTeX (made SVG by pdfLaTeX and `pdftocairo`, design 0022 §6) and arrows. Something must turn the
composed figure into a PDF in the folder's container, where TeX is. The TeX layer (decision 0134) has pdfLaTeX,
Poppler and Ghostscript, none of which reads SVG; LaTeX's `svg` package needs Inkscape.

Measured 2026-10-26 in the TeX layer's image with librsvg 2.58: an SVG nested as `<svg>` in the composed SVG stays
vector in the PDF `rsvg-convert` makes; the same SVG given as an `<image>` is made pixels at 96 per inch.

## Decision

- Clank composes the export as one SVG itself (`boardexport.py`): each figure's SVG nested with ids of its own, each
  picture embedded as it is, the LaTeX and the captions as TeX made them, the arrows as lines.
- The TeX layer adds Ubuntu's `librsvg2-bin` (librsvg's `rsvg-convert`, LGPL 2.1 or later), which makes that SVG a
  PDF, or a PNG at the resolution asked. SVG exports need nothing more.
- A container from before this layer says so, and how to build it again (`clank latex setup`).

## Alternatives considered

- **A LaTeX document placing the parts** (TikZ at the board's coordinates, `\includegraphics` for each figure): the
  PDF would be TeX's own, but pdfLaTeX cannot include SVG, so SVG figures would still need a converter.
- **Inkscape** in the layer (for LaTeX's `svg` package, or to convert): it does the same, at several hundred
  megabytes more.
- **CairoSVG** (Python): another way to the same cairo drawing, as a Python package in the container, with a smaller
  share of SVG.
- **The page makes the files** (the browser draws the SVG on a canvas): PNG only; no PDF, and nothing for the agent.

## Consequences

- The TeX layer is built again once (its folder changed); a workspace using it is offered the new image as before.
- Export is the same for the owner (the board editor's Export) and the agent (`board_export`), and works without the
  owner's window open.
