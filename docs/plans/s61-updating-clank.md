# Plan s61: Updating Clank

Design 0026 §1 and §2 (decision 0145): `clank update --check` says what is installed and what is newer, and `clank
update` updates Clank the way it was installed, a helper finishing an update that installs the tool again. The owner
asked for it on 2026-10-26.

## What exists

- The installer (`install.ps1` and `install.sh` on clank-ai.github.io) installs the latest release tag with `uv tool
  install --force --reinstall-package clank --python 3.12 git+https://github.com/clank-ai/clank@<tag>`, Git allowed long
  paths for that download; a developer installs a clone with `uv tool install --editable .`.
- uv keeps its record of the tool in `uv-receipt.toml` beside the tool's Python: the requirement, editable or from Git.
- `clank stop`, `clank gateway stop` and `clank serve --background`.

## Choices made here

- **How Clank was installed is uv's record**, not a guess from paths; with no record, a working copy Clank runs from is a
  clone (`uv run`).
- **GitHub's API for a release** (the latest release's tag, the newest tag when none), standard library only; **git
  for a clone** (fetch, then how far its branch is behind its upstream).
- **A helper finishes an install** (decision 0145), its script written in Clank's state folder and its steps in
  `logs/update.log`; a clone whose pull touches no dependency is updated in place and its service started again.
- **Every outside call is injected** (`run`, `fetch`, and the service's stop, restart and the helper's start), so the
  tests reach no network, no git and no uv.

## Tasks

- [x] 1. What is installed, from uv's record (`clank/updates.py`: `installed`); tests: a release, a clone, another
  way, no record in a working copy.
- [x] 2. What is newer (`newer`, `later`): GitHub's latest release against the version installed, no answer said as
  such; a clone's commits behind, their titles, its own changes, whether they touch the dependencies or the extension.
- [x] 3. `clank update` (`clank/cli/update.py`): `--check` (and `--json`), `--dry-run`, a clone refused with changes of
  its own, else pulled and its service started again; a release (or a clone whose dependencies changed) installed by
  the helper after the service and the gateway stopped.
- [x] 4. Docs: design 0026, decision 0145, getting-started's "Update Clank", the indexes, the issues page.

## Progress

Written and built 2026-10-26. The console's line and VS Code's when a newer Clank is out (design 0026 §3) come next.
