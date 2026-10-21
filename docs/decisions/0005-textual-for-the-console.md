# 0005. The console is built with Textual

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner's answer to "What should the terminal console be built with?" (chose "Textual")

## Context
The console is a full-screen terminal application with live panels, pickers and edit forms (decision
[0003](0003-one-terminal-console.md)). The prototype's terminal view uses Python's curses, which has no widgets.

## Decision
Build the console with [Textual](https://textual.textualize.io/) (MIT license, pure Python), pinned to an exact
version in Clank's environment, together with Rich, which it uses. Layout and colors go in Textual's CSS files, so the
user can change how the console looks without touching its logic (principle 3).

## Alternatives considered
- **curses (standard library).** No dependency, but pickers, forms, scrolling and mouse handling are all hand-built:
  more code and a plainer result.
- **A Rust (ratatui) or Go (Bubble Tea) binary.** Fast and light, but a second toolchain, and harder for the user and
  their local model to change.

## Consequences
- Two pinned dependencies (textual, rich).
- Textual's test harness (running the app headless and pressing keys) is used for the console's tests.
- The console must cap its redraws (principle 6): Textual animates at up to 60 frames per second unless told otherwise.
