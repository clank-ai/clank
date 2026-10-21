# 0027. The console's snapshots are text, made by the console itself

- Status: Accepted. Supersedes the snapshot tool of [0022](0022-development-tools.md)
- Date: 2026-10-11
- Decided by: proposed by Claude in the M0.5 plan, under the owner's instruction to build M0 through the console and
  the VS Code extension's shell (2026-10-11); the owner can revisit it

## Context
Decision 0022 named pytest-textual-snapshot for the console's snapshots. Design 0001 §5.8 also asks the console to
print one frame as text (`clank console --snapshot`), for scripts, bug reports and a model that cannot see a screen.
The plugin keeps each snapshot as an SVG image: clear in a browser, but a diff of one is hundreds of lines of markup
that neither a reviewer nor a small local model can read, and it adds syrupy and Jinja to the development tools.

## Decision
The console renders a frame as text itself (`clank/console/snapshot.py`, from Textual's own compositor, the way
Textual makes its screenshots). `clank console --snapshot` prints it, and the console's tests compare it with text
files checked in under `tests/console/snapshots/`, rewritten when `CLANK_UPDATE_SNAPSHOTS=1` is set. What text cannot
show (colors, such as the red of the menu's planned entries) is checked by tests that read the rendered style.

## Alternatives considered
- **pytest-textual-snapshot (decision 0022).** Catches every change of color and layout, but its diffs are
  unreadable, and `--snapshot` would still need a text renderer of its own.
- **Both.** Two snapshots of each screen to keep up to date, for little more safety.

## Consequences
- One renderer serves the command and the tests; a snapshot's diff reads like the screen.
- A change of color alone fails no snapshot; the colors that carry meaning get tests of their own.
- The renderer reads Textual's compositor, which is not public API; Textual is pinned in the lock, and the snapshot
  tests fail at once if an update changes it.
