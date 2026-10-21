# 0007. Settings, presets and the model catalog are readable files

- Status: Accepted
- Date: 2026-10-11
- Decided by: part of the approach the owner chose (decision [0006](0006-runtime-service-with-adapters.md)), which
  keeps the best property of the settings-file alternative; reinforced by principle 3 (radical transparency)

## Context
The runtime service holds the state, but the user must be able to read, version, compare and edit settings without
going through the console or reading code.

## Decision
Presets, role sampling, the model catalog and the engines' defaults are JSON files: the shared ones in the
repository, the user's own in the local configuration outside version control. The service validates every file it
reads, reloads a file when it changes on disk, and writes the files back when the console changes something, so the
file and the console always agree. What is running at the moment, and the last configuration that worked, are runtime
state, kept outside the repository.

## Alternatives considered
- **TOML.** Friendlier to edit by hand, but Python reads TOML without writing it; writing it needs another dependency.
- **A database.** Not readable or diffable as files.

## Consequences
- A hand edit and a console edit are the same thing; neither can silently overwrite the other (the service reloads
  first, then writes).
- Every file has a documented schema, checked by tests.
