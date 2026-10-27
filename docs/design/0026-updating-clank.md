# Design 0026: Updating Clank

How the owner learns that a newer Clank is out and gets it with one command, whichever way Clank was installed. The
owner asked for it on 2026-10-26: "the ability to easily check for updates to Clank from GitHub and to update Clank
easily". Before it, getting-started said to run the installer again.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | What is installed, and what is newer | Approved 2026-10-26 (the owner's request); built 2026-10-26 ([plan s61](../plans/s61-updating-clank.md)) |
| 2 | Updating | Approved 2026-10-26 (the owner's request); built 2026-10-26 ([plan s61](../plans/s61-updating-clank.md)) |
| 3 | Saying it where the owner looks | Approved 2026-10-26 (the owner's request); `clank update --check` built; the console's line and VS Code's next |

## 1. What is installed, and what is newer

`clank update --check` changes nothing. It says:

- **How Clank was installed**, read from uv's own record of the tool (`uv-receipt.toml` beside the tool's Python):
  a **release** (the installer's `uv tool install` from `git+https://github.com/clank-ai/clank@<tag>`), a **clone**
  (an editable install of a working copy, a developer's or the owner's), or **another way** (Clank then says it cannot
  update it and how it was found).
- **What is newer**: for a release, the latest release on GitHub (its tag, from GitHub's API, the newest tag when there
  is no release yet) against the version installed; for a clone, the commits its branch is behind its upstream after a
  `git fetch`, with their titles (the ten newest), and whether its working tree has changes of its own.
- **What it contacts**, in its words: GitHub's API, or the clone's own remote. Nothing else, with a short timeout; no
  answer is said as such ("GitHub did not answer in 10 s"), never as "up to date".

## 2. Updating

`clank update` does what `--check` found, in the way the installation calls for; `--dry-run` says each step without
doing it. The owner's settings and state (`~/.clank`) are never touched.

- **A clone**: refused while its working tree has changes of its own or its branch has no upstream, saying why; else
  `git pull --ff-only`. When the pull changed Clank's dependencies (`pyproject.toml` or `uv.lock`), the tool is
  installed again from the clone; when it changed the VS Code extension (`vscode/`), Clank says the two commands that
  build and install it. Then the service is started again, so the new code runs.
- **A release**: the newest release installed as the installer installs it (`uv tool install --force
  --reinstall-package clank --python 3.12 git+https://github.com/clank-ai/clank@<tag>`, Git allowed long paths for that
  one download).
- **Finishing in a helper** (decision 0145): on Windows a program's files cannot be replaced while it runs, and the
  service, the gateway and `clank update` itself run from the tool's files. So when the tool must be installed again,
  `clank update` stops the service and the gateway, starts a small helper of its own (a PowerShell or sh script under
  `~/.clank/state/`) and ends; the helper waits for it to end, installs, starts the service again and writes each
  step to `~/.clank/logs/update.log`, which `clank update` names before it ends.

## 3. Saying it where the owner looks

- `clank update --check` (built).
- The console's Home and VS Code's status bar say one quiet line when a newer Clank is out, from a check made at most
  once a day and kept in Clank's state, with a setting to turn it off (next).
