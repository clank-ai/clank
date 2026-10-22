# 0126. The console records what it draws, where it writes to the terminal, in asciinema's format

- Status: Accepted (the owner's request of 2026-10-22, built as Claude's call)
- Date: 2026-10-22
- Decided by: Claude, after a recorder that ran the console in a pseudo console of its own was found to redraw it twice

## Context
- The owner wants to record the console while a flow runs overnight and watch it again "almost like a video in real
  time", without slowing the model (video capture and encoding halved the model's speed on this PC before).
- A recorder that runs a program in its own pseudo console (as asciinema does) works for any program, but the console
  is then drawn by two pseudo consoles, and the owner saw lines shift ("glitching").

## Decision
- **`clank console --record FOLDER`** keeps every write the console's driver sends the terminal, with its time, in
  asciicast version 2 (asciinema's format: a header with the size, then `[seconds, "o", text]`, and `"r"` for a
  resize), so asciinema's player shows it again exactly, at its own pace. Nothing is captured from the screen and
  nothing encoded; what the console draws is what the file holds (a hidden field's key drawn as dots), and no key typed
  is written.
- **In parts**: a new file every 20 minutes, each beginning on a clear screen with the whole screen drawn again, so
  no file grows too large for a player and each plays on its own.
- A view the console does not have (`--view flow.`) is refused, saying which it has, never opened as another.

## Alternatives considered
- **A pseudo-console recorder around the console**: kept for programs Clank does not draw (OpenCode), not for the
  console, which it redraws twice.
- **Textual's screenshots on a timer**: frames, not the stream; a second apart at best.

## Consequences
- A recording is kept to disk every second; a night of the Monitor is a few files of a few tens of megabytes each.
