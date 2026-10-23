# Plan s41: Esc goes back to the menu

[Design 0011](../design/0011-the-consoles-look.md) §12.4 and §12.5, decision
[0129](../decisions/0129-esc-goes-back-to-the-menu.md). Asked for by the owner on 2026-10-22: "the esc key should
always bring me back to the Clank menu."

**Goal:** Esc from anywhere in a page puts the focus on the menu, shown beside the Monitor while it has it; the steps
back inside a page move to Backspace.

## Tasks

- [x] 1. `keys.ANYWHERE` gains `esc menu`, always on the keys bar with `?` and `f1`; `bksp` written for Backspace;
  Help's moves say both. Test: `tests/console/test_esc_to_menu.py`, `tests/console/test_keys_bar.py`.
- [x] 2. The shell: Esc (no window open, no field taking it) runs `to_menu`; the menu shows while Esc or Left put the
  focus on it (`-menu-focus`), the arrows in it passing the Monitor without hiding it; a group of buttons no longer takes
  Esc. Test: `tests/console/test_esc_to_menu.py`.
- [x] 3. Backspace for the steps back: the Monitor's Context and Session views, the Flow view's boards, Add a model's
  steps; History's filter leaves for the menu as before. Tests: the console's tests that went back, now with Backspace.
- [x] 4. The frames redrawn (every keys bar shows `esc menu`) and read.
