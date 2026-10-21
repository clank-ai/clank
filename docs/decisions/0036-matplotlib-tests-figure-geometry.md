# 0036. Matplotlib is a development tool: the figure geometry is tested on real figures

- Status: Proposed (built at the owner's instruction while away; the owner may decide otherwise)
- Date: 2026-10-15
- Decided by: Claude, for design 0008 §3, on the owner's request to annotate the figures the model makes

## Context
Design 0008 §3 has the sandbox image wrap Matplotlib's `Figure.savefig`, so every raster figure saved in a workspace
gets its geometry written beside the folder's notes: each plot's box in the image's pixels, its data limits and scales,
its lines. A mark the owner draws is said in data coordinates from it, so a wrong pixel is a wrong sentence to the
agent. The geometry has to be checked against figures Matplotlib really draws: tight bounding boxes, several plots, log
scales, the dots per inch of the file.

## Decision
**Matplotlib** (and NumPy, which it needs) joins Clank's development dependencies (`uv add --dev matplotlib`), pinned by
uv's lock like the other tools of decision 0022. Clank itself does not import it: the hook runs inside the workspaces'
containers, with the Matplotlib the folder's own software installed, and does nothing where there is none.

## Alternatives
- **Test in the sandbox image.** It has no Matplotlib (each folder brings its own), and Docker tests run only when asked:
  the geometry would go untested on most runs.
- **A fake figure object.** It would test the arithmetic, not what Matplotlib draws, which is what can be wrong (the
  tight box moves every plot).

## Consequences
- About 40 MB more in the development environment; nothing more for someone who installs Clank.
- The tests draw small figures off screen (the Agg backend): no window opens.
