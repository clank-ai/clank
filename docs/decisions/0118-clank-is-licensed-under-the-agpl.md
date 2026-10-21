# 0118. Clank is licensed under the GNU Affero General Public License, version 3 (AGPL-3.0-only)

- Status: Accepted (the owner's decision)
- Date: 2026-10-21
- Decided by: the owner, an hour after the first public beta was published under the MIT License: "I don't want
  someone to just take this and resell it since I want this to always remain open source."

## Context
Clank was first published under the MIT License, which lets anyone take the code, change it, keep their changes
closed and sell the result. The owner wants the opposite: Clank, and everything built on it, should always remain
open source, while anyone stays free to use it, study it, change it and build on it as much as they like.

Clank is not only a program people run on their own computer: its service answers an API, its gateway serves models
to other programs, and its phone pages are served over a network. A license that keeps changes open only when a
program is distributed would let a modified Clank be run for others as an online service with its changes kept
closed.

## Decision
Clank is released under the GNU Affero General Public License, version 3 only (SPDX `AGPL-3.0-only`): the `LICENSE`
file holds its text, and `pyproject.toml`, the VS Code extension's `package.json`, the README, CONTRIBUTING.md and the
changelog say so. Anyone may use, study, change and share Clank; whoever shares a modified version, or lets others use
one over a network, must offer its source under the same license. Contributions are released under the same license.
The name Clank and its logo identify the project and are not a permission to present a modified version as Clank.

The public repository's history was replaced by one commit under this license, so the MIT License appears nowhere in
it; copies taken during the hour it was public under MIT keep that license.

## Alternatives considered
- **MIT (the first choice)**: the simplest permissive license, but it allows exactly what the owner wants to prevent:
  a closed, resold version.
- **GPL-3.0**: keeps distributed versions open, but not a modified Clank run as a service for others.
- **A noncommercial license (for example PolyForm Noncommercial)**: forbids any commercial use, but is not open source,
  and keeps many developers and companies from using or contributing to it.
- **A license forbidding harmful uses**: not open source, hard to enforce, and ignored by anyone who means harm.

## Consequences
Clank and every shared or served modification stay open source. Companies may still use Clank, and may sell services
or support around it, but cannot close it. Because the contributors so far are its owner, the owner can also offer
Clank under a separate commercial license later (dual licensing); accepting outside contributions with that in mind
would need a contributor agreement, to be decided when the first outside contribution arrives.
