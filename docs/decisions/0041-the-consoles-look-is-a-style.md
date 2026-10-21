# 0041. The console's look is a style: a readable file of named elements, loaded as a Textual theme

- Status: Accepted (the owner approved design 0011 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving [design 0011](../design/0011-the-consoles-look.md) ("Approve all three", the
  remaining Choices as recommended)

## Context
The owner, on boards E1 and E2 (2026-10-18): "We also should design the style of Clank so that each of these major
style elements can be changed to different styles in the settings, but this is just for future proofing since I don't
want to worry about adding any more styles other than the single style that we have so far." Today the console takes
one of Textual's themes, its style sheet names Textual's variables, and the bars, sparklines and marks that say a
state are written in its Python (`gauges.py`, `text.py`). Design 0011 §2 and §3 say what a style is and how it is used.

## Decision
A **style** is a settings kind: a readable JSON file ([0007](0007-settings-in-readable-files.md)) defined once in
Pydantic ([0015](0015-kinds-defined-once-in-pydantic.md)). It names every element of the look: colors by role (what
each is for, never what it looks like), six data colors, named kinds for the Monitor and flows (`parts`, `calls`,
`boxes`), the border kind, the title placement, the marks, the bar, spark and tree glyphs, and the spacing. A color is
`#rrggbb`, a glyph one cell wide; a value that does not fit is refused with its file, line and field. Clank's own,
`clank/defaults/styles/clank.json`, is the one place Clank's values are written; the owner's go in
`CLANK_HOME/config/styles/<name>.json`, where a `clank.json` replaces Clank's; an element a style leaves out takes
Clank's value. Only `clank` ships, and it is the default. A bar keeps its color by its level (`low`, `busy`, `full`,
set to the colors of `good`, `attention`, `failed`): §2's Choice, as recommended.

The field `style` of `CLANK_HOME/config/console.json` picks the style. Before its first frame the console reads that
file, then the style, and registers the style as a Textual theme of its name before it sets it: Textual's colors come
from the roles, each color is also a variable `$clank-<name>`, and the drawing helpers read the glyphs. A style not
found falls back to Clank's, a file that does not read leaves the last good style in force (Clank's, at start), the
message line says why, and the console always starts. A change applies when the service reports it. The owner's
`console.tcss` stays, loaded after Clank's.

## Alternatives considered
- **A theme written in Python**, as Textual's own themes are. A change of color would be a change of code, not a
  setting the owner can read and change in a file (decision 0007).
- **Style sheets alone**, as today. They cannot color what the console's Python draws (bars, sparklines, a state's
  mark), nor hold its glyphs.

## Consequences
- The whole look is one file to read, change or copy; a copy of Clank's keeps working when a later Clank adds an
  element. An unknown theme no longer stops the console from starting, as it does today.
- Designs 0012 and 0013 draw in this style and add to it any element they need; design 0001 §5.5 (the look) and
  design 0004 §9 change: every color becomes a named element of the style.
- Whether each new glyph is one cell wide in the owner's terminal is checked on the first build; a style can swap any.
- Built in R1 (design 0011 §11), no new dependency; no snapshot changes ([0027](0027-console-snapshots-are-text.md)).
