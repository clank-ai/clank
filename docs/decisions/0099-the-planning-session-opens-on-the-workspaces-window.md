# 0099. The planning session is started on the workspace's OpenCode window and shown there, the window started first in this terminal or in Clank's VS Code window

- Status: Accepted, as Claude's call; the owner may reverse it; for the console, revised by [0100](0100-a-planning-opens-beside-the-console.md)
- Date: 2026-10-20
- Decided by: Claude, building [design 0013 §15](../design/0013-flows.md#15-a-flow-built-with-the-model) ([plan
  s32](../plans/s32-flows-a-flow-built-with-the-model.md)), told: "Opening where the owner is: in VS Code (Clank's VS
  Code window, OpenCode in its terminal on that session) when the console runs in VS Code or the owner presses the VS
  Code key, else OpenCode in this terminal on that session, returning to the console when it ends. Check how OpenCode
  1.19.0 attaches a TUI to a given session from the recorded fixtures and the code that already opens OpenCode for a
  folder; if attaching to a given session is not possible, say how you solved it and record it. Do not run the real
  OpenCode."

## Context
The recorded fixtures of OpenCode 1.19.0 (`tests/fixtures/opencode/1.19.0/`) are its server's events, sessions and a
change's permission; they hold nothing of its command line. Clank's code starts OpenCode's terminal interface as
`opencode --port N --hostname 127.0.0.1` (`adapters/opencode.py`) and never names a session there. What is measured is
the server's side: design 0009 §7-§8 (2026-10-16) found that `POST /tui/select-session` shows a session in the window
that serves the port, the window taking that session's last message's agent, and `/implement` starts a session on the
window's own server, sends its first message, then shows it. A session started on another OpenCode server (the flows'
`opencode serve`) runs on that server, whose events the window does not show, even if a flag opened it there.

## Decision
- The planning session is started **on the server of the workspace's OpenCode window**, its first message sent to the
  planner, then **shown there with `/tui/select-session`**, as `/implement` does; the bridge's `implement` gains the
  agent to send to and a wait for the window's server to answer.
- **Here** (the console's `n` outside VS Code, `clank flow new --here`): Clank writes OpenCode's configuration and
  gives the console the command that starts the window (`agents/prepare`, the one-window rule as always); the console
  steps aside while it runs and comes back when it ends.
- **In VS Code** (`N`, `n` when the console runs in VS Code's terminal, `clank flow new --vscode`): the window running
  in the workspace takes the session; with none, Clank's VS Code window is opened and its extension starts OpenCode in
  its terminal through `agents/prepare`, and that window takes it.
- A planning waiting for its window is told the window's port when `agents/prepare` gives one in its workspace. The
  session is started once that port answers (the bridge waits up to 60 seconds), and shown again twice a few seconds
  later, since a terminal interface just started may not yet hear the first `select`; showing the session a window
  already shows changes nothing (measured 2026-10-16).
- No flag of OpenCode's command line is used to open a session; none is recorded or measured for 1.19.0.
- **Over SSH** (the owner's requirement, 2026-10-20: their first real test runs over SSH from a Linux PC into this
  Windows PC, the console in that SSH terminal): when the console or `clank flow new` runs with `SSH_CONNECTION`,
  `SSH_CLIENT` or `SSH_TTY` in its environment, the planning opens here, in that terminal, whatever asked for VS Code
  (`N`, `--vscode`), said so; nothing on the way from `n` to `r` needs the PC's own screen. `clank console --page
  monitor --view flow` opens the Flow view for a terminal that keeps F10 for itself.

## Alternatives considered
- **`opencode --session <id>`** (a session created first on another server): not in the fixtures nor measured, and
  the session would run on the server it was created on, out of the window's sight.
- **The flows' own server** (`opencode serve`, where boxes run): the owner talks to the planning session, so it must
  be in a window; boxes run there because nobody talks to them (design 0013 §5).
- **The service polling the container for a new window**: a `docker exec` every second while the planning waits; the
  window's port is known when `agents/prepare` gives it, so no polling is needed.

## Consequences
The choice of where is the client's (the console, the command), from its own environment, since only it knows
whether it runs in VS Code's terminal or over SSH; the service opens where it is told.
The bridge changes, so the sandbox image does: a workspace's container is made again from it once stopped. Whether a
terminal interface just started hears `/tui/select-session` at once is to measure (plan s32 owes it); shown again
twice covers a window slower to listen. A planning whose window does not answer within the wait fails, said in its
event and in the Flow view; one waiting for a window that is never started (VS Code's window already open without
OpenCode) waits, said the same way: the owner opens OpenCode there (Clank: Open the agent), or presses `n` again.
