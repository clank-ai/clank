# 0009. A configuration can be checked, and tested in a trial run, before it is applied

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner ("the ability to 'check' the settings that we have selected as well as running tests ...
  headless to test the settings before they are applied"), approving design 0001 §3.8 and §4

## Context
A new engine, model or option can fail to start, run slower, use more memory than estimated, or answer worse. Finding
out by applying it to the live model interrupts the user's work, and with one GPU the candidate cannot simply run
beside the live model.

## Decision
Two steps, both recorded with the preset. A **check** starts nothing: validity, memory fit, cost, and what the
engine's adapter can verify without a launch (program and version, accepted flags, the model file's size, checksum and
format). A **test** is a trial run inside the runtime service (headless; the console only watches): the candidate is
started, test suites run against it (smoke, speed, memory, context, quality; each suite a file the user can change),
the results are saved, and then the configuration that was running before comes back, unless the user chose to keep
the candidate and every test passed. When the candidate needs the GPU the live model uses, the trial goes through the
switch procedure with an automatic return, and can be scheduled for when the slot is idle.

## Alternatives considered
- **Check only (no trial).** Fast, but the failures that matter (speed, memory in practice, answer quality) appear only
  when the model runs.
- **Test only when the user is away.** Safe, but a choice the user wants to make now would wait; scheduling for an
  idle slot remains an option.
- **A second GPU or machine for tests.** Not available on most machines.

## Consequences
- A trial on the GPU interrupts the live model for its duration; the console says so before it starts.
- Presets carry their test results, with the date and engine version, so a choice rests on measurements.
- Test suites need fixed prompts and answers kept in the repository.
