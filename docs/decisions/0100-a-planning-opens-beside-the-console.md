# 0100. Starting a planning from the console never takes its terminal: OpenCode runs beside it, in a second terminal with `clank flow attach`, a Windows Terminal pane, or Clank's VS Code window

- Status: Accepted (the owner's choice of two SSH windows, built as Claude's call)
- Date: 2026-10-20
- Decided by: the owner, before their first real test: "I would prefer to work with the model to build the flow in a
  way where I can watch the flow being built while the model is working, which means that I should be able to open
  OpenCode on one side and keep the Clank menu on the other side, and I also want to start the building of the flow
  from the monitor section as well as the ability to start it from the 'This folder' section". From two mockups they
  chose two SSH windows side by side on another computer: the console on the left, `clank flow attach` on the right.
  How it is built is Claude's call ([design 0013 §15](../design/0013-flows.md#15-a-flow-built-with-the-model),
  [plan s33](../plans/s33-flows-watch-the-flow-built.md)). Revises [0099](0099-the-planning-session-opens-on-the-workspaces-window.md)
  for the console.

## Context
Decision 0099 opened the planning session in the console's own terminal: the console stepped aside while OpenCode ran
and came back when it ended, so the owner could not watch the flow being built while talking with the model. Over SSH,
nothing may open on the PC's own screen. A terminal cannot be split from inside a program reached over SSH; Windows
Terminal, at the PC, can be split from its command line (`wt -w 0 split-pane`, its documented CLI: `-w 0` the current
window, `-V` a vertical split, the new pane on the right, `-d` its starting folder, then its command line).

## Decision
- **`n` on the Flow view and `f` on This folder** open a planning that waits for its window, and bring the console to
  the Flow view, which shows it (decision 0101). The console's terminal is never handed over. `f`, because `n`
  answers the first question waiting on This folder ("y n ..."). `clank flow new` keeps OpenCode in its own terminal.
- **Where OpenCode opens, from the console:** over SSH (`SSH_CONNECTION`, `SSH_CLIENT` or `SSH_TTY`), nothing: the
  Flow view and the message line say "talk with the model: in another terminal, cd <folder> then clank flow attach".
  At the PC in Windows Terminal (`WT_SESSION`, not SSH): `wt -w 0 split-pane -V -d <folder> <python> -m clank flow
  attach --workspace <W>` (with `--home` when `CLANK_HOME` is set, since a new pane does not inherit the console's
  environment; each `;` of an argument escaped, which `wt` reads as a separator); when `wt` is missing or refuses, the
  message. In VS Code's terminal, or with `N`: Clank's VS Code window, as before. Elsewhere, the message.
- **`clank flow attach [--workspace W]`** prepares OpenCode's window (`agents/prepare`, the one-window rule: another
  window in the workspace is closed first, and said) and runs it in this terminal: a planning waiting for its window
  starts its session there; one already talking is shown there (the bridge's new `show`, waiting for the window and
  showing it again as `implement` does); with none open, it says so and how to open one.
- **No clipboard.** The console has no way to copy, so the command is shown, never copied.

## Alternatives considered
- **The console steps aside, as before**: the owner cannot watch the flow being built.
- **The console starts a second SSH session or a terminal window itself**: over SSH it can open nothing on the
  owner's computer; at the PC, a new window would cover the console.
- **Copying the command with OSC 52**: the console has no copy mechanism, and a terminal over SSH may refuse it.
- **OpenCode inside the console** (a terminal widget): a dependency, and OpenCode's own interface drawn twice.

## Consequences
Two terminals, side by side: the console watching, OpenCode talking. The bridge gains `show`, so the sandbox image
changes again. A planning whose window never attaches waits, said in the Flow view; `n` again sets it aside.
