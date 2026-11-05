# 0164. Nothing on the way changes while Clank reads or writes a workspace's folder

- Status: Accepted (the audit of 2026-10-30); refines 0159; revises design 0004 §3
- Date: 2026-11-04

## Context

- Decision 0159 had Clank check a path in a workspace's folder before using it: no `..`, no link on the way. The agent
  works in the folder at the same time, from its container, so a name checked a moment before can be a link by the
  time it is opened.
- The service reads more of the agent's files than the ones it keeps in `.clank/`: an artifact's sources, a flow's
  deliverables (kept beside each try and handed to the boxes after it), the files a review shows before and after, a
  session's files shown on the phone and in the console, a job's log, the files sent to the phone. Some of those were
  read with no check at all.

## Decision

- **One way to reach the folder, held while it is used** (`kernel/infolder.py`, `Place`): a path below the folder is
  taken a folder at a time from the workspace's folder, each folder opened without following it and kept open until
  the file is read, written or listed.
  - On Linux and macOS each folder is opened from the one before it (`dir_fd`, `O_NOFOLLOW`), and the file too: the
    system itself refuses a link anywhere on the way, and a name changed meanwhile changes nothing already open.
  - On Windows each folder on the way is opened without following it (a junction, a symbolic link, or any other
    reparse point that names another place, is refused) and held so that nothing can rename or remove it while it is
    open; the file itself is opened without following it. A folder someone else has open to rename or remove is tried
    again for a moment, then the operation fails, saying why.
  - A file is written whole under a name of its own, then put in place, so a link standing in its name is replaced,
    never written through.
- **Every read and write the service makes in a workspace's folder goes through it**: the files Clank keeps in
  `.clank/` (artifacts, jobs, boards, figures' copies, handoff notes, LaTeX's pages, the outbox) and the agent's own
  files the service reads (an artifact's sources, deliverables, a review's files, a session's files, a job's log).

## Alternatives considered

- **Keep Clank's records in CLANK_HOME** (0159's alternative, still to be weighed then): the container itself writes
  much of `.clank/` (jobs' logs, the outbox, the figures' geometry, the handoff notes, LaTeX's builds), and the service
  reads the agent's files anyway, so a safe way to read the folder is needed whatever lives where; moving the records
  would also change every path the agent, the extension and the phone are told.
- **Open, then ask the opened file where it is** (Windows' final path of a handle, Linux's `/proc/self/fd`): enough for
  a read, but a write and a folder made on the way still need the way held, so two mechanisms instead of one.
- **Open relative to a folder's handle on Windows too** (`NtCreateFile`): the exact match of Linux's way, at the cost
  of much more native code than holding the folders on the way.

## Consequences

- A link the agent makes in the folder, wherever and whenever it makes it, makes the operation that would pass
  through it fail, saying so; nothing is read or written outside the folder through it.
- While Clank holds a folder, the agent's rename or removal of that folder waits or fails; Clank holds each one only
  for the moment of one read or write.
- Links the person made inside the folder are not followed by Clank either: an artifact's file reached through a link
  is refused, saying so.
