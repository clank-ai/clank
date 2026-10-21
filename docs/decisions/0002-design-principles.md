# 0002. The design principles

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner, in three statements the same day: "the entire point of this prototype project is to create an
  entire local LLM suite that can replace my need for products like Codex"; "radical transparency, and the ability
  for me to go in and not only understand what is being implemented and how it works, but also the ability to go and
  alter things myself"; and that the architecture must make it "extremely easy for a human to understand what is
  going on but ALSO for a large language model ... to go in, understand the architecture, and begin improving" it,
  installable by others with "their local model ... or plug in an API key, or even connect to an LLM that is running
  on an HPC".

## Context
Without stated principles, each part would be designed for its own convenience. These statements decide trade-offs
across all parts, so they are written down once and every design is checked against them.

## Decision
Adopt the seven principles in [PRINCIPLES.md](../PRINCIPLES.md): replace hosted assistants; modular; radical
transparency; readable and changeable by people and by models; portable; the computer stays usable; engineered as a
product.

## Alternatives considered
None: these are the owner's goals. Principle 6 (the computer stays usable) comes from measured experience with the
prototype, not from that day's statements: an endless redraw at a high-refresh display's rate cut the model's decoding
speed to about a third (2026-10-08), and long GPU work once froze the desktop for seconds.

## Consequences
- Every design document checks itself against the principles.
- Machine-specific values and secrets never enter the repository (principles 3 and 5).
- Documentation is part of the work, written for a person and for a small model (principle 4).
