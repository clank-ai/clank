# 0044. No color, and no mark of the style, is written outside a style file; a repository check refuses them

- Status: Accepted (the owner approved design 0011 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving [design 0011](../design/0011-the-consoles-look.md) ("Approve all three", the
  remaining Choices as recommended)

## Context
A style (decision [0041](0041-the-consoles-look-is-a-style.md)) changes the whole look only if no page writes a color
or a mark of its own (design 0011 §6). Today every color of the console is a theme variable but one, the planned
entries' `color: red` in `clank.tcss` (red at the owner's request, 2026-10-11); but they are Textual's generic
variables: `$accent` alone colors the spinner, a highlighted row, a window's border, Help's keys, a sparkline, the
header's mark and more, and `tone()` in `text.py` holds ✓ and ✗ itself. A color written in a page fails no snapshot,
since a snapshot is text (decision [0027](0027-console-snapshots-are-text.md)).

## Decision
The console names only the style's elements: `$clank-good`, never `#9ece6a`, `green` or Textual's `$success`. Each
generic variable takes the role it means: each use of `$accent` takes its own (`now`, `selection`, `border-focused`,
`key`, a data color, `brand`, and so on); `$success`, `$warning` and `$error` take `good`, `attention` and `failed`
(or a bar's `low`, `busy` and `full`); `$text-muted` takes `quiet`; `$panel` and `$panel-lighten-2` take `bars` and
`border`; `.planned` takes `planned`. A page draws a state's mark only through the drawing helpers, from the style.

The check, `tools/check_colors.py`, run by `tools.check` and `tests/test_repository.py`, reads every file of the
console (`clank/console/` and each component's `console/`, Python and style sheets, a widget's `DEFAULT_CSS` too) and
refuses a hex color; an `rgb()` or `hsl()` value; a color's name in a style rule; a style string or markup that names
a color; a `$` variable that is not one of the style's; and a mark of the style written in a page (● ○ ✓ ✗ ◆ ✎). The
marks that are also punctuation (?, · and …) pass, and so does prose that names a color. The owner's `console.tcss`,
in `CLANK_HOME` outside the repository, is not checked.

## Alternatives considered
- **Review alone.** A color written in a page shows in no snapshot and is easy to miss in a diff, and it would keep
  that color under any style. The check holds every change to the rule, whoever writes it, a person or a model.

## Consequences
- Colors and marks are written only in style files: a change of style reaches every page, and a color the Monitor or
  flows need is first an element of the style.
- The tests that pin pure red for the planned entries (`tests/console/test_shell.py`) compare with `planned`, read
  from Clank's style file: they pin the element, not its value.
- The test that the owner's `console.tcss` loads after Clank's keeps writing `.planned { color: blue; }`.
- R1's tests plant each refused form in the test's own folder, and prove that prose naming a color, and the
  repository itself, pass.
