# 0042. The console offers only Clank's styles; Textual's built-in themes leave the picker

- Status: Accepted (the owner approved design 0011 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving [design 0011](../design/0011-the-consoles-look.md) ("Approve all three", the
  remaining Choices as recommended): the Choice of §3, tokyo-night, its recommended option (a)

## Context
With the look a style (decision [0041](0041-the-consoles-look-is-a-style.md)), something had to become of Textual's
own themes (design 0011 §3). Today Ctrl+P offers Textual's "Theme" command, with Textual 8.2.8's 21 built-in themes,
light ones among them, and the console remembers its theme in `CLANK_HOME/state/console.json`. The `tokyo-night`
remembered there was saved automatically, never picked by the owner (the research of 2026-10-18). Clank's style keeps
tokyo-night's base colors and changes its text (#c0caf5 for #a9b1d6) and its `panel` color (#16161e for #414868). The
owner asked for a Clank that is easier to work on, "eliminating every bit of technical debt we accumulate as
possible."

## Decision
Ctrl+P offers "Change style" in place of Textual's "Theme": it lists the styles found, Clank's and the owner's
(`clank` alone today), and writes the choice through the service. Textual's built-in themes, tokyo-night among them,
leave the picker. The first console with styles reads the remembered theme once, removes it, and never writes a theme
again; a theme other than tokyo-night, which the owner did pick, is named once on the message line.

## Alternatives considered
- **(b) Keep tokyo-night beside the styles.** Under it, Textual's own variables would come from tokyo-night and every
  `$clank-` element would keep Clank's value (through Textual's `get_theme_variable_defaults`, since a variable that a
  style sheet uses and a theme lacks stops the style sheet from loading). The research leaned toward it, as a way
  back; but it keeps a second place for colors and a second picker for their own sake, and tokyo-night can come back
  at any time as a style file.
- **(c) Keep every Textual theme, as today**: (b) for all 21, where on the light ones (textual-light,
  solarized-light) Clank's dark values for borders, quiet text and data would sit on a light background.

## Consequences
- One place for colors and one picker: what the console shows is what its style file says.
- Picking a style changes a setting, written through the service (decision
  [0007](0007-settings-in-readable-files.md)), so it needs the service; the style's file, `clank records` and the API
  change it too.
- `tests/console/test_monitor.py`'s "the console starts in tokyo night and remembers the theme picked" becomes "the
  console starts in the style `config/console.json` picks, `clank` by default", with the migration's test beside it.
- A light look, or tokyo-night itself, is a style file away.
- Built in R1 (design 0011 §11).
