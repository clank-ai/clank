# 0011. Agent programs are plugged in through adapters; OpenCode is the first

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner's answer to "How should Clank run the coding agent itself (the program that plans, reads,
  edits and runs commands)?" (chose "Plug in existing agents")
- Wording: "Clank requests" became "questions to the user" on 2026-10-11, when design 0002 named them; the decision
  is unchanged.

## Context
Clank must give its user a coding agent good enough to replace hosted products like Codex (principle 1), with modes,
approvals, questions, tools and skills, contained so that it can touch only what the user allows. Writing an agent
program (planning, editing, running commands, keeping its context in order) is months of work, and capable open ones
exist. OpenCode is the one the prototype runs every day, inside its sandbox: a headless server with an HTTP API and an
event stream, its own permission prompts, agents (its word for modes), MCP servers and skills. Others, such as Codex
CLI, have their own interfaces. Principle 2 asks that every piece of Clank can be swapped.

## Decision
Clank runs agent programs through **agent adapters**, one per program, the way it runs engines (decision
[0010](0010-serving-setups-are-plug-and-play.md)). OpenCode is the first.

Clank owns everything around the agent: the workspace and its container, the network, the tools (MCP servers, reached
through Clank's tool hub), the skills, the modes, approvals and questions, the sessions as the user sees them, and how
the user is reached. An agent adapter translates Clank's settings (the mode, the model by its role name, the tools and
skills turned on) into the program's own configuration; starts the program inside the workspace's container; follows
its sessions and events; and turns its permission prompts into questions to the user, which the user can answer
from any client.

Safety never depends on the agent program. The container, its only network door (the edge) and the tool hub enforce
what is allowed, whatever the program does or fails to do.

An agent written for Clank can be added later as one more adapter, if the Codex gap list (roadmap part 7) shows a
need for one.

## Alternatives considered
- **Write Clank's own agent now.** Full control over modes, questions and context handling tuned to local models, but
  months of work before it matches OpenCode, with everything else waiting on it.
- **Use one agent program directly, without an adapter.** The fastest start, but it ties Clank's modes, approvals and
  phone flow to one program's features and breaks principle 2.

## Consequences
- An agent adapter interface with contract tests and fixtures recorded from each program's real API, as for engines
  (design 0001 §8.2-8.3).
- What Clank can offer partly depends on the program (for example, whether it asks permission before each command).
  Each adapter declares what its program supports, and the console shows it.
- Clank's own tools for agents (ask the user, ask for access, send the user a file) reach any program that speaks MCP.
- Agent programs are pinned to tested versions; an upgrade is tested before it is used, like an engine's.
