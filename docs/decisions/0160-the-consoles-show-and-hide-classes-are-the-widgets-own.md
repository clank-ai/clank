# 0160. The console's show and hide classes are the menu's and the machine column's own

- Status: Accepted (the audit of 2026-10-30, measured); revises design 0011 §12.5
- Date: 2026-11-04

## Context

- Whether the menu and the machine column show (Ctrl+B, Esc to the menu, F5, and a page beside which either hides:
  the Monitor) was said by classes of the screen: `-menu-off`, `-menu-on`, `-menu-focus`, `-no-menu-column`,
  `-machine-off`, `-machine-on`, `-no-machine-column`.
- Textual restyles every widget below a node whose classes change. Every page is mounted, so each of those keys
  restyled about 690 widgets: 0.1 to 0.3 seconds with the keys held up, most of the lag the owner felt. The same
  toggle on the menu itself took about a hundredth of that.

## Decision

- **The classes are the widgets' own**: the menu's on `#menu`, the column's on `#machine`, the stylesheet's rules
  written `Screen #menu.-menu-off` (as specific as before, so the width's rules still give way to them).
- **Two classes that change together change in one restyle** (Ctrl+B and F5 set both at once).
- A test counts the widgets each toggle restyles and fails past 150; before the change Ctrl+B restyled 692.

## Alternatives considered

- **Mount each page when it is first shown**: fewer widgets for every restyle, but a larger change (menu badges, pages
  that read each other); left for later (design 0001 §8.7's budget).

## Consequences

- The screen's own classes now say only its size (`-wide`, `-wider`, `-small`), which change only when the terminal
  does.
