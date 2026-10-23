# Plan s42: larger boxes in the Flow view

[Design 0013](../design/0013-flows.md) §12, decision [0130](../decisions/0130-the-flows-boxes-come-in-three-sizes.md).
Asked for by the owner on 2026-10-22, watching a run over SSH full screen.

**Goal:** the flow's boxes readable on a large screen: three sizes, picked with `+` and `-`, kept; the Monitor opening
on the Flow view.

## Tasks

- [x] 1. `boxchart.SIZES` (small, medium, large), `render(..., size=)`, `fitting` (the largest that keeps two to a
  row), a wrapped title, a box's tries, time and tokens, the files it writes. Tests: `tests/console/test_box_chart.py`.
- [x] 2. `ConsoleSettings.flow_boxes` (medium), read by the chart when mounted; `+` and `-` on the Flow view, written
  through the records route. Test: `tests/console/test_monitor_flow_view.py`.
- [x] 3. The Monitor opens on the Flow view (`FIRST_VIEW`); the frames redrawn and read.
- [x] 4. The running box's session under Selected (decision 0131, the owner's request of 2026-10-23): Thinking beside
  Selected, Tool calls beside Context window, then the Orchestrator beside Waiting for you, then Models in this flow;
  read through a second `Following` pinned to the box's session, and its live text. Test:
  `tests/console/test_monitor_flow_view.py`.
