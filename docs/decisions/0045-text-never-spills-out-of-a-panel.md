# 0045. Text never spills out of a panel: prose wraps, a row is cut with "…" and shown whole by `?`

- Status: Accepted (the owner approved design 0011 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving [design 0011](../design/0011-the-consoles-look.md) ("Approve all three", the
  remaining Choices as recommended): the Choice of §5, the key that shows cut text whole, its recommended option (a)

## Context
The owner, on a board (2026-10-18): "This is overflowing out of the green box around it, so we need to be careful to
make sure that the text that will be in these boxes is actually placed inside the box properly". The first boards also
cut titles off at their boxes' edges (since fixed), and today the doctor's advice on Machine wraps back to the panel's
edge (the `machine` snapshot). Design 0011 §5 gives each kind of line its rule; its Choice was the key that shows a cut
row whole.

## Decision
Every line inside a panel is one of these:
1. **Prose** wraps at the panel's width, and the panel grows to hold it.
2. **A row of a list or a table** is one line, cut with "…" at the panel's width (`fit` in `gauges.py`, or Textual's
   own ellipsis).
3. **A drawing** (a bar, a graph, a table's columns, the Monitor's flow) is drawn for the width its panel gives, by a
   function of that width, never wider.
4. **A name and its value** (`Rows`): the value wraps under itself, never back under the name; with under 36 columns
   for the values, each name stands above its value.
5. **A panel that may not grow** (a hundred requests) shows a set number of rows and scrolls, taking the focus so that
   the arrows reach it.

Nothing is cut without "…", and no panel cuts its title (decision [0043](0043-every-section-is-a-panel.md)). `?`,
which explains what has the focus in a window (design 0001 §5.4), shows a cut row whole: on a cut row, the window
starts with the row whole. The menu cuts a long name with "…" too, shown whole by `?`. A page keeps its own `v` where
it shows a question whole.

## Alternatives considered
- **(b) A letter of its own on every page.** The letters that suggest it are taken on some page already: `v` is the
  live view on Requests and vision's mode on CPU models; `w` switches on Models.
- **(c) Enter where a page has no use for it.** Enter already switches a preset, lists a server's tools and shows a
  device's traffic, so it would mean "whole" on some pages only.

## Consequences
- One key on every page, and no new key; `?` stays on every keys bar (decision
  [0046](0046-the-keys-bar-shows-the-pages-keys-first.md)).
- A panel of prose may grow taller; one that may not grow scrolls, and Tab reaches it.
- R2's tests prove that no label in a panel is cut without "…" (each wraps, ends in "…" or fits) at 80, 120 and 170
  columns; R5 moves the doctor's advice on Machine under its own column, and its tests prove it.
