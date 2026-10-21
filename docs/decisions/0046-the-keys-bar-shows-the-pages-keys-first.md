# 0046. The keys bar shows the page's own keys first, from one declaration of named actions per page

- Status: Accepted (the owner approved design 0011 on 2026-10-18)
- Date: 2026-10-18
- Decided by: the owner, approving [design 0011](../design/0011-the-consoles-look.md) ("Approve all three", the
  remaining Choices as recommended)

## Context
The owner, on board A (2026-10-18): "make sure that it is easy for me to navigate this." Today the keys bar shows only
the keys that act anywhere; several pages end with a hint line of their own keys, outside any panel, and Help keeps
its own table of every page's keys (`KEYS` in `clank/console/pages/help.py`), kept in step by hand. Boards E2 to E18
draw each page's keys in the keys bar. Design 0001 §5.5 plans `CLANK_HOME/config/keys.json` (M2), which maps keys to
actions. Design 0011 §7 says how the keys bar is built.

## Decision
Each page declares its keys once, as named actions, each with its key and its words. The keys bar, one row on `bars`,
shows the page's own keys first, then `?` explain and `f1` help, then the other keys that act anywhere (`f5` machine
column, `q` quit), and `^p palette` at the right: each key in `key`, its words in `quiet`. When the row is too narrow,
the other keys that act anywhere go first, then the page's own, from the right; `?` and `f1` always stay, and `f1`
lists every key. The keys bar, Help's panels (board E13) and `?` read that one declaration, so the pages' hint lines
and Help's `KEYS` go. The shell draws the keys bar for the page on screen, wherever the focus is. No panel's key
letter (decision [0043](0043-every-section-is-a-panel.md)) is one of its page's keys.

## Alternatives considered
- **Only the keys that act anywhere, as today** (and as board E1 draws it). Each page's keys would stay in a hint line
  outside any panel and in Help's own table, written again in each and kept in step by hand.

## Consequences
- The keys bar, Help and `?` cannot disagree, and a page's new key shows in all three at once.
- Home's own `s` and `d` come first on its keys bar, though board E1 shows only the keys that act anywhere.
- The named actions are what M2's `keys.json` (design 0001 §5.5) remaps.
- `frame_when` (`tests/console/frames.py`), which waits for "f1 help" in a frame, keeps working: `f1` stays on every
  keys bar.
- R2's tests prove the page's keys first and `?` and `f1` always there, at 80 columns too; that each page declares its
  keys as named actions; and that Help lists every key the pages declare and holds no table of its own. R3 to R7 prove
  each page's keys first on its bar.
