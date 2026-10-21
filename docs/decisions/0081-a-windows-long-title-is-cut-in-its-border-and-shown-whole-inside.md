# 0081. A window's title too long for it is cut in its border with "…" and shown whole as its first line

- Status: Accepted, as Claude's call; the owner may reverse it. Supersedes, for the windows only, the "never cut" of
  [0043](0043-every-section-is-a-panel.md)
- Date: 2026-10-19
- Decided by: Claude, without the owner (plan s8's task 11, building design 0011's R2; the review of that task asked
  that the exception be recorded where the rules live)

## Context
Decision 0043 and [design 0011](../design/0011-the-consoles-look.md) §4 say a panel is never narrower than its title,
so its title is never cut, and §5 ends "no panel cuts its title". Design 0011 §7 counts each window over the console
(the details window, the picker, the form, an MCP server's tools, a device's traffic) as a panel, and a window is never
wider than the screen allows (90% of it, as before R2). Some windows take their title from what they show: a preset's
file path, a question's title, a device's name. Such a title can be longer than 90% of a narrow terminal, so a window
cannot both keep its title whole in its border and stay on screen.

## Decision
A window (`WindowPanel`, `clank/console/panel.py`) has no least width. When its title, its corners and the spaces
around it do not fit in its top border, Textual cuts the title there with "…", and the window shows the title whole,
as written (not read as markup), as its first line inside, in bold. A window whose title fits shows no such line. Every
other panel keeps 0043's rule: never narrower than its title, its title never cut.

## Alternatives considered
- **Keep the least width for windows too.** A long title would push the window past the screen's edges, and its
  border, its keys line and its content with it: worse than a cut title, against design 0011 §5 (nothing spills).
- **Wrap the title over two border lines.** Textual draws a border's title on one line only; a title of two lines
  would need a border drawn by hand, for every window, for a case that is rare.
- **Cut the title in the border and say nothing more.** The title would be lost; the rule of §5 is that what is cut is
  shown whole somewhere, so the window shows it inside.

## Consequences
- Design 0011 §4 and §5 are revised after approval to say so (2026-10-19), with a line in its revision log.
- A window with a long title is one line taller. `tests/console/test_windows.py` proves the cut title in the border
  and the whole title inside.
- Board E19 (`docs/design/boards/Windows.dc.html`) draws a cut title, for the owner's look.
