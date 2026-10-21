# 0038. Plan mode is an agent of Clank's in OpenCode, with its own rules

- Status: Proposed (the owner reads design 0009 before it is built)
- Date: 2026-10-15
- Decided by: Claude, on the owner's request (2026-10-15) for a plan mode that writes plans and nothing else, toggled
  from Clank, whose plans are handed to review or auto

## Context
The owner wants a mode in which the agent plans a study and writes the plan, with no code, figures or runs, and a way
to hand the plan to the agent in review or auto mode. OpenCode 1.19 has a planner of its own (design 0009 §2), and
design 0002 §2.6 names a plan mode enforced by the container.

## Decision
Clank's OpenCode configuration defines a primary agent, `planner`, with its own instructions and its own rules (design
0009 §3): it may write Markdown files and nothing else, run reading commands, and use the MCP tools their servers mark
read-only. OpenCode's own `plan` agent is disabled. A command, `/implement`, hands a plan to `build`.

## Alternatives
- **OpenCode's own `plan` agent.** It writes its plan under `.opencode/plans/` with a name OpenCode picks, its exit
  continues the same session (the whole planning conversation in a small context), it knows nothing of review and auto,
  and under Clank its edit rule is overridden by Clank's (design 0009 §2).
- **Design 0002 §2.6's read-only folder.** The strongest: no command could change the folder. But the planner could not
  write its plan, and each switch restarts the container. It stays the later form.
- **Clank's review answering for plan mode** (rejecting edits to anything but plans). It works without a new agent,
  but the model keeps Build's instructions and tools, and commands are not covered.

## Consequences
Tab in OpenCode switches between Build and Planner; Clank's configuration now holds an agent, a command and two prompts
of its own, tested like the rest of it. Enforcement is OpenCode's rules: a command the owner allows in plan mode may
still change files (design 0009 §9).
