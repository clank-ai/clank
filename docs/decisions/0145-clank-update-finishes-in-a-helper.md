# 0145. `clank update` finishes in a helper process when the tool must be installed again

- Status: Accepted (Claude, with plan s61, at the owner's request for an easy update)
- Date: 2026-10-26
- Decided by: Claude

## Context

Design 0026 §2: Clank updates itself with one command. Clank is a uv tool: its Python and its files live in uv's tool
folder, and `uv tool install --force` replaces them. On Windows a running program's files cannot be replaced, and three
programs run from those files while an update is asked for: the service, the gateway, and `clank update` itself (an
earlier reinstall, by hand, failed while the service and the gateway ran: AGENTS.md says so).

## Decision

- When the tool must be installed again (a release; a clone whose dependencies changed), `clank update` stops the
  service and the gateway, writes a small script under `~/.clank/state/` (PowerShell on Windows, sh elsewhere) and starts
  it detached, then ends. The script waits for `clank update`'s process to end, runs uv's install, starts the service
  again, and writes each step to `~/.clank/logs/update.log`.
- A clone whose pull changed no dependency needs no install: `clank update` pulls and starts the service again itself.

## Alternatives considered

- **Tell the owner to run the installer again**: what getting-started said; the owner asked for one command.
- **Install in place from `clank update`**: fails on Windows, the files in use.
- **A second copy of the tool to update from** (an updater installed beside Clank): one more thing to install and keep
  in step, for what a script of a dozen lines does.

## Consequences

- An update that installs ends `clank update` before it is done: it says so, and names the log the helper writes.
- The helper is plain text in Clank's state folder, readable before it runs (`--dry-run` prints it).
