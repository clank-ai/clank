# 0001. Clank is its own product, in its own repository, with the prototype as its template

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner ("let's go ahead and do this in another directory ... which we will call Clank ...
  we should use what we have built as a template for what we are ultimately building here")

## Context
The prototype is a set of tools built for one PC: a local coding agent in a sandbox, a model gateway and monitor, a
model registry, a VS Code workbench, tab completion, a research companion. It works, but it is tied to that machine
(paths, one GPU, one engine) and grew feature by feature. The owner now wants a suite that replaces products like
Codex, that anyone can install, and that they and their local model can understand and change.

## Decision
Clank is built as a new product in its own repository (on GitHub, branch `main`), in a folder of its own next to
the prototype's. The prototype stays as it is and keeps working; it is the template: what worked there is
carried over deliberately, part by part, redesigned where needed ([PROTOTYPE.md](../PROTOTYPE.md)). Work proceeds like a
software product: design documents reviewed section by section, decisions recorded, tests, and every step committed and
pushed to GitHub as it is made.

## Alternatives considered
- **Refactor the prototype in place.** Keeps one code base, but every change risks the tools the owner uses daily, and
  the machine-specific assumptions are everywhere.
- **A fork of the prototype's repository.** Inherits its history and its assumptions; a clean start with explicit
  carry-over keeps Clank portable and readable from the first commit.

## Consequences
- For a while there are two tool sets; the prototype remains the daily driver until Clank replaces each of its parts.
- Every carried-over part needs its machine-specific values replaced by configuration.
- The repository is private for now; publishing it later needs a license (an open question for the owner).
