# 0020. Each permission is enforced by the part that can actually stop it

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner's approval of design 0002 §2 ("Everything looks great now"), which listed this choice in §2.18

## Context
Modes (plan, ask, auto) and grants say what an agent may do. An agent program such as OpenCode has permission prompts
of its own, but a shell command run in a writable folder can change any file there, whatever the program's settings
say; the outside review of 2026-10-11 (design 0002) pointed this out. Decision
[0011](0011-agent-programs-are-plugged-in.md) requires that safety never depend on the agent program.

## Decision
Policy decides; the part that can stop an action enforces the decision:

- the sandbox's container: what the agent can see (only the workspace's folders are mounted), and in plan mode that it
  can change nothing (the workspace is mounted read-only; entering or leaving plan mode restarts the sandbox);
- the edge: the network and git;
- the tool hub: tool calls;
- the gateway: which model providers receive a workspace's content (`model.send`);
- the kernel and the edge: secrets (no sandbox holds one; the edge adds it on the way out);
- the service: files sent to the user, slot switches, sessions.

Where the only check is the agent program's own prompt (asking before an edit or a command in a writable workspace),
every client labels it as the program's.

## Alternatives considered
- **Modes enforced through the agent program's permission settings.** One shell command goes around them.
- **Intercepting every command the agent runs.** A shell command cannot be judged safely by reading it, and tracing
  every system call is heavy and fragile.

## Consequences
- An agent's session must survive the restart of its sandbox when its mode changes (a test in M5).
- "Ask before each edit" is a convenience, not a guarantee. A workspace that needs a guarantee has its agent work on a
  copy whose changes the user accepts (designed in M4 and M5).
- Each enforcement point is proven by the escape tests of M4.
