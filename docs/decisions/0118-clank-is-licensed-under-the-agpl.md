# 0118. Clank is licensed under the AGPL-3.0

- Status: Accepted (the owner's decision)
- Date: 2026-10-21
- Decided by: the owner

## Context
Clank is meant to be forked and rebuilt for each person's needs, and to stay open source as it grows.

## Decision
Clank is released under the GNU Affero General Public License, version 3 only (SPDX `AGPL-3.0-only`), in `LICENSE`,
`pyproject.toml` and the VS Code extension's `package.json`. Contributions are released under the same license.

## Alternatives considered
- **MIT**: the license of the very first publication; it would let a modified Clank be closed.
- **GPL-3.0**: would not cover a modified Clank offered to others as a service.

## Consequences
Anyone may use, change and share Clank; versions that are shared or served stay open source.
