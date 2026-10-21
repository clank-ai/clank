# 0086. A box hands on a short note, written in the folder and kept beside its try; a missing note is marked, not failed

- Status: Accepted, as Claude's call; the owner may reverse it
- Date: 2026-10-20
- Decided by: the owner chose that each box a model runs ends by writing a handoff note, handed to every later box
  (2026-10-20); where it lives, who writes one and what a missing note does were left to Claude, decided while building
  ([plan s30](../plans/s30-flows-each-box-prepared.md))

## Context
A box's session ends with its deliverable, but what it decided and what it left open stays in its session, which no
later box sees ([design 0013 §5](../design/0013-flows.md#5-running-a-box-a-fresh-session)). The owner asked that each
box end by writing a few lines (what it did, the decisions it made, what is still open), and that every later box be
handed the notes of the boxes before it, in order, short, each saying where it came from. A box's model writes only in
the workspace's folder, its sandbox; Clank's home, where the runs are kept, is out of its reach (decision 0066). VERIFY
and DECOMPOSE end by tools (`flow_verdict`, `flow_submit`), and a VERIFY changes no file.

## Decision
- **Where it lives.** The box writes its note in the folder at `.clank/handoff/<flow>/<box>.md` (`<flow>` the flow's
  name, `<box>` the box's id). `.clank/` is where Clank and the agent already exchange files (figures, annotations, the
  phone's outbox), kept out of git by a `.gitignore` of its own; the runner writes `.clank/handoff/.gitignore` when it
  is missing. When the box ends, a note written during its try (by its fingerprint, as a deliverable,
  §8) is copied beside the try as `handoff.md` and kept on the try in the run's file (`Try.handoff`); a later box is
  handed that copy, so a later run's note in the folder never changes what an earlier run handed.
- **Who writes one.** PLAN, TASK and INTEGRATE, told so by their type's instructions and by their deliverable's
  section, which names the file. A VERIFY's verdict and a DECOMPOSE's summary (`flow_submit`) are their notes: they
  write no file.
- **A missing note is marked, never a failure.** A box whose deliverable is right is done without its note: its try
  keeps no note, its end's event says "it left no handoff note", and the boxes after it are told that it left none.
  The note is not part of its deliverable: no VERIFY or accept command checks it, and changing it makes nothing stale.
- **Handed on.** Every later box a model runs is handed the notes of the boxes before it, in the order they ran, each
  under a heading naming its box, type, try and where it came from, each cut at the flow's `defaults.note_up_to`
  characters (2,000 by default; a cut says so and names the whole note's path), quoted so its words never pass for
  Clank's. A box not run yet in the run (only in a preview) says its note comes once it has run.
- **But a VERIFY.** A VERIFY is handed no notes: it is handed only the brief, the deliverable it checks and what that
  is accepted when, never the session that made it (§2, decision 0063), and a note is that session's own account of
  its work.

## Alternatives considered
- **Beside the try only, written through a tool** (`flow_note`, as `flow_verdict`): out of the folder entirely, but a
  new tool in the sandbox image (every open workspace reopened), a call the model can forget as easily as a file, and
  nothing the owner can open in VS Code while the flow runs.
- **A file of the owner's choosing in the project** (`NOTES.md`): in git, but shared by every box (each overwrites or
  appends to the last), and mixed with the owner's own files.
- **The session's last answer read as its note**: no file at all, but it depends on the model's final words and on
  reading a session's messages through the bridge, and nothing marks where the note begins.
- **A missing note fails the box**: a right deliverable sent back for its note costs a whole fresh try (§7: a fresh
  prompt read without the cache); a missing note costs the later boxes only some orientation.
- **VERIFY handed the notes too**: it would learn what the plan left open, but read the checked session's claims about
  its own work, which is what its independence keeps it from.

## Consequences
- A box in Review mode has its note's writing reviewed like any change of its session's.
- The last of a long series is handed up to `note_up_to` characters for each box before it (twelve tasks: about 24,000
  characters at most); `clank flow prepare` shows what each box is handed, and its size.
- The owner reads each note in the folder while the flow runs, and beside its try afterwards.
- How well a model writes its note (short, decisions and open points, no retelling) is to see on the real model.
