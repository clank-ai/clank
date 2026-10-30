# Plan s66: an answer cut off at the output limit

Design 0012 §8, revised 2026-10-29 (decision 0154). The owner, with a free cloud model: "the cloud model I am using
has stopped twice without getting any large amount of work done, and there is nothing indicating why specifically the
model stopped working … the reason the model keeps stopping is because it is hitting its thinking limit".

## What exists

- Each step of Clank's flow of a session keeps OpenCode's finish for it (`sessionflow/flow.py`): `length` when the
  answer reached the output limit before it ended.
- The Watch for rules (`agents/watchfor/rules.py`) and what each does (`MonitorSettings` in `agents/kinds.py`, the
  owner's `config/monitor.json`): mark, pause, tell the phone, tell the model and go on (at most twice in a row).

## Tasks

- [x] 1. Failing tests first: the rule fires on a step whose finish is `length`, naming the slot's limit and OpenCode's
  count of the thinking, marks it once (`cut:<step>`), even with no limit known, and never on a step that finished;
  its defaults are the design's table (mark, tell the model) with its words (`tests/support/flowlines.py`'s `step`
  takes a finish).
- [x] 2. The rule `answer_cut`, after the loop guard's, and its settings; the settings schema and the extension's types
  generated again.
- [x] 3. Records: decision 0154, design 0012 §8's table and its revision log.

## Progress

Written and built 2026-10-29, for 0.3.0b6.
