# 0170. Installs and updates take the versions a release was tested with

- Status: Accepted (the audit of 2026-10-30); revises design 0026 §2 and design 0028 §3
- Date: 2026-11-06
- Decided by: the audit's plan for 0.3.0b8 (a constraints file per release, passed by both installers and by
  `clank update`, and upper bounds below the next majors), which the owner asked to have done before the release

## Context

- `pyproject.toml` gives each dependency a lower bound alone, and `uv.lock` the versions every check ran with. A
  `uv tool install` from a Git tag, which both installers and `clank update` make, reads no lock: uv takes the newest
  version each range allows on the day of the install.
- So two installs of one release could run different code, and neither need be the code that was tested. On the
  owner's machine, an install from 0.3.0b7 ran FastAPI 0.162.0, Starlette 1.10.0 and httpx2 2.16.0, where the lock
  names 0.143.0, 1.7.0 and 2.13.1. Clank also relies on a few things inside its dependencies that are not their public
  promise (Textual's log file setting, which keeps typed keys out of a log, among them), which a release of theirs may
  change.
- uv takes a constraints file (`--constraints`): requirements that restrict the versions it may install and add
  nothing. `uv export` writes the lock as such a file.

## Decision

- **`constraints.txt` at the repository's root names each dependency Clank installs at the version `uv.lock` names**
  (`uv export` of the lock, without the development tools and without Clank itself). It is generated
  (`uv run python -m tools.constraints`, run by `tools.check --fix`), never edited by hand, and a repository test fails
  when it says other than the lock, so every commit, and so every tag, carries its own.
- **`clank update` installs a release with that release's file**: read at its tag
  (`https://raw.githubusercontent.com/clank-ai/clank/<tag>/constraints.txt`), written to
  `~/.clank/state/update-constraints.txt` and passed to uv as `--constraints`; a clone is installed again with its own
  file, as it was pulled. A release from before the file has none: the update says that uv takes the newest versions
  allowed, and goes on. A file that cannot be read (no answer, an error other than "not found") stops the update
  before anything is stopped or changed, saying so.
- **The installers do the same** (`install.ps1`, `install.sh`, on the website): they read the file of the release they
  install and pass it to uv, and say when a release has none.
- **`pyproject.toml` bounds each dependency below its next major version** (`textual>=8.2.8,<9`, `fastapi>=0.143.0,<1`
  and so on), so an install made another way never takes a release that may break what Clank uses.

## Alternatives considered

- **Exact pins in `pyproject.toml`**: every install would match, but a library pinned exactly cannot be installed
  beside anything else, and each bump would be a change to the package itself; the lock already holds the pins.
- **A constraints file attached to each GitHub release as an asset**: one more step in every release that can be
  forgotten; a file in the repository is at every tag already and is checked by every run.
- **Installing from a built wheel with its dependencies pinned in its metadata**: the same pins in a place no one
  reads, and it ends installs from the tag, which the installers, `clank update` and the receipt all rely on.
- **Upper bounds alone**: a minor release can break what Clank uses too (it has: Starlette's and FastAPI's minors move
  quickly); bounds keep out the larger breaks, the constraints the rest.

## Consequences

- An install of a release, by the installer or `clank update`, has the versions its checks ran with, whatever came
  out since; a failure on a user's machine can be reproduced from the lock.
- A fix in a dependency reaches users with Clank's next release, once its checks ran with it, not on the day it is
  published. Clank's own releases have to bump the lock for that (`uv lock --upgrade`, then the checks).
- A dependency's new major version needs a change to `pyproject.toml`, its upper bound raised once Clank was checked
  with it.
