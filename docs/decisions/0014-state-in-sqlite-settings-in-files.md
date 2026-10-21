# 0014. State lives in one SQLite database; settings stay in readable files

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner's approval of design 0002 §2 ("Everything looks great now"), which listed this choice in §2.18

## Context
Clank keeps two sorts of records (design 0002 §2.2). **Settings** are what the user decides: presets, roles, modes,
workspaces. Decision [0007](0007-settings-in-readable-files.md) put them in readable files. **State** is what Clank
records about what happens: what runs, sessions, questions, grants, paired devices, operations, events. The service
writes state many times a minute; every client reads it; the history is queried by time and by record; and some of it
must change together or not at all, such as an answer, the grant it creates, and the events that record both.

## Decision
State lives in one SQLite database, `CLANK_HOME/state/clank.db`, written only by the service, with numbered migrations
that are never edited once released. Settings stay in JSON files (decision 0007). Large streams (the gateway's records,
the output of processes) stay in files, each with its retention setting.

## Alternatives considered
- **State in JSON files**, as the prototype keeps it. Readable in any editor, but without transactions a crash between
  two writes leaves them inconsistent, every query is code, and concurrent writers need locks.
- **A database server** (PostgreSQL). Stronger under heavy concurrent load, but another program to install, run and
  upgrade, for the state of one user.
- **Everything in SQLite, settings included.** One store, but settings would stop being files the user reads, diffs
  and edits (decision 0007).

## Consequences
- Whatever must change together is written in one transaction.
- State is read through the API (the supported way), the console, `clank state` commands, or any SQLite tool.
- Every migration has a test, as every settings migration does (design 0001 §7.7).
- SQLite is part of Python: no new dependency.
- The history (design 0001 §4.8) moves from a JSON-lines file into the database; `clank events export` writes it out as
  JSON lines.
