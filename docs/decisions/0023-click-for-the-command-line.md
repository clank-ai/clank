# 0023. The `clank` command is built with click

- Status: Accepted
- Date: 2026-10-11
- Decided by: proposed by Claude in the M0.1 plan, under the owner's instruction to "plan M0.1, and start building"
  (2026-10-11); the owner can revisit it

## Context
Every action in Clank is also a command, `clank <component> <verb>` (design 0002 §2.15). Components add their own
commands, and every kind of record also gets generic commands (list, show, change) made from the kind's definition
when the program starts, as the API's generic routes are (design 0002 §2.2). Every command prints readable text, or
JSON with `--json`, and tests run commands in-process.

## Decision
The `clank` command is built with click.

## Alternatives considered
- **argparse**, in Python's standard library. No dependency, but subcommands contributed by many components, and
  commands made at run time, take much more code, and there is no in-process test runner.
- **Typer**, built on click. It reads options from type hints, which suits commands written by hand but not commands
  made from a kind's definition at run time, and it adds its own layer and dependencies.

## Consequences
- click is a runtime dependency.
- Commands are tested in-process with click's `CliRunner`.
- Each component's `cli.py` builds a click group, which `clank/cli/main.py` adds to the top-level `clank` group.
