# 0122. A button's states are drawn in five new colors of the style, its fill covering a blank cell at each side

- Status: Accepted (Claude's call on board K1, which the owner's approved K2 embodies; the owner may change it)
- Date: 2026-10-21
- Decided by: Claude, writing [design 0011](../design/0011-the-consoles-look.md) §12.8 from boards K1 and K2

## Context
- The console's look is a style: every color an element named for its role, no color written in a page (decisions
  0041 and 0044).
- The owner has complained about overlapping text; a button that grew when focused would push its row.
- The keys bar writes two spaces between keys today.

## Decision
- **Five colors join the style**: `button_hover` (#292e42), `button_focused` (#7aa2f7) and `button_focused_text`
  (#1a1b26), `button_pressed` (#bb9af7) and `button_unable_focused` (#3b4261), each a `$clank-` variable as every
  color is. A button that cannot act now uses `dim`, as a waiting box does.
- **The focused button is inverted**: its fill in `button-focused`, its key and words in `button-focused-text`; only
  the focused group draws its cursor, so one button on the screen is focused.
- **Every button keeps one blank cell at each side, and the fill covers it**: no state changes a width. Two buttons
  side by side make today's two-space gap, so the keys bar's keys stand where they stood.
- **Pressed** shows for a fifth of a second; hover is a lighter ground under the mouse that never moves the focus.

## Alternatives considered
- **Brackets or an underline** around the focused button: a width that changes with the state, or a look a terminal
  may not draw.
- **Reusing `selection`** for the focus: a list's highlighted row and the focused button would look the same.
- **Colors written in the widget**: refused by decision 0044's check, and not changeable in a style file.

## Consequences
- A style file may set the five like any color; Clank's own file stays its title only.
- The settings schema of `style` gains the five; the text snapshots do not change for the look (they hold no color).
