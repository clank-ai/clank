# 0019. Components use one another only through declared public functions, checked by a test

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner's approval of design 0002 §2 ("Everything looks great now"), which listed this choice in §2.18

## Context
The Clank service holds nine components (design 0002 §1). Without a rule, convenient imports between them accumulate
until no component can be replaced (principle 2) or understood on its own (principle 4), by a person or by a model.

## Decision
A component uses another only through the public functions in that component's `service.py`, only if its own
`component.py` declares the dependency, and never in a cycle. The kernel uses no component. A test reads every import
in the `clank` package and fails on anything else.

## Alternatives considered
- **A convention written in AGENTS.md.** Nothing checks it, so it erodes.
- **A separate package per component.** Enforced by the packaging itself, but each would need its own version and
  installation, for parts of one service.
- **import-linter**, a tool that checks import contracts. It does the same job but cannot read the components' own
  declarations, and our test is short and needs no dependency.

## Consequences
- A new dependency between components is a visible one-line change to a declaration, reviewed like any other change.
- The code map shows each component's dependencies.
- Work that crosses components goes through public functions, which therefore stay small and documented.
