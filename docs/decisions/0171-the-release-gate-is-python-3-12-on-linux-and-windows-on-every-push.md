# 0171. The release gate is Python 3.12 on Linux and Windows, on every push

- Status: Accepted (the audit of 2026-10-30); revises the line of decision 0022 on continuous integration's Python
  3.14, and design 0028 §6
- Date: 2026-11-06
- Decided by: the audit's plan for 0.3.0b8 (Windows on Python 3.12 on every push, 3.14 a canary, a tag only on a
  commit whose push run passed), which the owner asked to have done before the release

## Context

- Clank installs with Python 3.12 (both installers and `clank update` ask uv for it), and develops with it. CI ran
  3.12 on Linux alone; Windows ran only on Python 3.14, and only for pull requests and tags.
- The Windows 3.14 lane failed on every tag from 0.3.0b2 to 0.3.0b6, mostly on console tests that timed the wall clock
  (the audit's D6), so the release job, which needed it, never ran: those releases were made by hand, and a Windows
  failure showed up an hour after the tag, never at the push that caused it.
- Each push to `main` canceled the run of the push before it, so most pushes had no verdict at all, and a tag could
  not be put on a commit known to pass.
- The installers took the newest tag, so a tag whose checks failed reached new users anyway (0.3.0b5, for hours).

## Decision

- **Python 3.12 runs on Linux and on Windows on every push** (`oldest-python`, both systems, `tools.check` whole), and
  so does an install made as the installers make it (`installed`: `uv tool install` with `constraints.txt`, each
  dependency checked at its version, decision 0170).
- **A push to `main` runs to its end**: only a pull request's newer push cancels its older run.
- **The release job needs the two 3.12 lanes and the install**, and nothing else. Python 3.14, on Linux and Windows, is
  a canary: it runs for pull requests, tags, each night and on demand, and holds no release.
- **A tag is pushed only on a commit whose push run passed** every lane; the release job checks the tag again.
- **Each Monday the checks run on the newest dependencies** the ranges allow (`uv lock --upgrade` in the job alone), so
  a break upstream is known before a release bumps the lock.
- **The installers follow the newest published release**, as `clank update` does since decision 0163.

## Alternatives considered

- **Windows 3.14 kept in the gate**: the lane that never passed would keep every release a hand-made one; 3.14 is not
  the Python users get.
- **Windows sharded across several jobs**: quicker, but its tests would need a split by folder kept in step with the
  tests; one lane of about the same length as Linux's comes first, and a split can follow.
- **Running Windows only before a tag**: what failed before; a Windows break would still be found long after the push
  that made it.

## Consequences

- Every push to `main` costs a Windows run as long as the Linux one, and its verdict is the one to read before a tag.
- A failure on Windows shows at the push that made it.
- A failure of the 3.14 canary is a warning to act on before 3.14 is the Python Clank installs, not a reason to hold a
  release.
