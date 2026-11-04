# 0163. `clank update` follows published releases, never a bare tag

- Status: Accepted (the audit of 2026-10-30); revises design 0026 §1 and §2
- Date: 2026-11-04

## Context

- `clank update` read GitHub's latest release, and, since GitHub answers 404 there while every release is a
  pre-release, it then took the newest tag. A tag is pushed before its checks run and its release is published; the
  Windows lane failed on every tag from 0.3.0b2 to b6, and 0.3.0b5's tag had no release for hours, yet updates
  followed it.
- The helper that finishes an update after `clank update` ends wrote the log's path, and each part of uv's command,
  in single quotes: a home folder with an apostrophe (`o'brien`) made PowerShell refuse the script after Clank had
  already been stopped, so Clank stayed stopped.

## Decision

- **Only published releases are followed**: the latest release, or, when every one is a pre-release, the newest
  published one in GitHub's list of releases (drafts left out); a tag without a release is never followed.
- **A release whose tag is not a version Clank reads is refused**, saying so, and nothing is installed.
- **Every value the helper writes is quoted for its shell**: PowerShell's single quotes with each quote doubled;
  `shlex.quote` for sh.

## Alternatives considered

- **A version file on the website**: no API limit, but one more thing to publish with each release; the releases'
  list is what the installers can read too.

## Consequences

- A release appears to `clank update` only once it is published, with its extension and checksums.
- The installers still take the newest tag (Git's list, no API): they are to follow the same rule with the release
  gate (a version the website publishes with each release), so that a tag reaches no one before its release.
