# 0159. Clank follows no link in a workspace's folder

- Status: Accepted (the audit of 2026-10-30); revises design 0004 §3; refined by 0164 (the way held while used)
- Date: 2026-11-04

## Context

- Clank keeps some of its own state in the workspace's folder, under `.clank/`: the artifacts' versions and exports
  (design 0021 §5), the agent's jobs and their logs (§6), the boards' history and compiled LaTeX (design 0022), the
  figures' marked copies (design 0008). The service reads and writes them as the owner.
- The folder is the agent's to write, `.clank/` included. A record there (an artifact's entry page) or a link there (a
  folder or file standing for another place) could lead the service to read or write a file outside the folder.

## Decision

- **One helper says where such a file is** (`kernel/infolder.py`, `inside`): the path below the folder only when its
  name stays below it (not absolute, no `..`, no drive, no `:`) and nothing on the way to it, the file itself
  included, is a link: a symbolic link, or on Windows a junction or any other reparse point that names another place.
  A name not there yet is fine. Anything else is refused, saying which part is a link.
- **The artifacts, jobs, boards and figures' copies go through it** for every file Clank keeps in `.clank/`: an
  artifact's entry page and files when exported, its new version, its record and its export; a job's folder and its
  files (a job reached through a link is not listed, read or written); a board's history, LaTeX and export drawings;
  a figure's marked copy, its record and the geometry Matplotlib left. A file the export finds through a link is left
  out of it.

## Alternatives considered

- **Keep Clank's state in CLANK_HOME instead of the folder**: the surest, and still to be weighed, since the agent
  reads some of these files (its jobs' logs, its artifacts' versions) inside its container; it changes where every
  one of them lives and what the agent is told.
- **Resolve each path and compare it with the folder** (what the sources of an artifact were checked by): a link that
  stays inside the folder is harmless to read, but a write must not follow even that, and the check and the use would
  still name the path twice.

## Consequences

- An agent's link in `.clank/` makes the operation that would follow it fail, saying so; nothing is read or written
  outside the folder through it.
- Links the person made in the folder's own files are untouched: only Clank's own records and copies are checked.
