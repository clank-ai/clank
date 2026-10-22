# Plan s39: the console as the website draws it, and its recording

[Design 0011](../design/0011-the-consoles-look.md) §13, decisions
[0125](../decisions/0125-the-console-takes-the-websites-look.md) and
[0126](../decisions/0126-the-console-records-what-it-draws.md). Asked for by the owner on 2026-10-22, before the first
long run on the Stabilizer Rank Challenge: the console must look "almost exactly" as the website draws it, the menu
must be possible to hide, and a run must be recorded as the terminal showed it.

## Tasks

- [x] 1. The menu column a page's (`Page.MENU_COLUMN`), the Monitor's off; Ctrl+B anywhere (`^b menu`, the last of the
  keys that act anywhere to stay on a narrow bar but the palette); a hidden menu's focus goes into the page. Tests:
  `tests/console/test_keys_bar.py`, the Monitor's frames.
- [x] 2. Board D1 as the website draws it: the flow across the whole width, at most 60% of the window high; Selected
  beside Waiting for you; the Orchestrator (plan s38's task 6) beside Models in this flow. Tests:
  `tests/console/test_monitor_page.py` (the panels, the page's widths with no menu), the Flow view's frames rewritten
  and read.
- [x] 3. The style's defaults the website's colors (titles, ◆ CLANK, what runs now, quiet, the border, the selected
  text). Tests: `tests/kernel/test_console_kinds.py`, `tests/console/test_console_style.py`.
- [x] 4. `clank console --record FOLDER` (`clank/console/recording.py`): the driver's writes kept as asciicast, a resize
  as `r`, parts of 20 minutes each beginning on a clear screen; `--view` refuses a view the console does not have.
  Tests: `tests/console/test_recording.py`; a live recording through a pseudo console read back (2026-10-22).
- [ ] 5. Kept for later: a DECOMPOSE's tasks as one stacked box in the flow, as the website draws them.
