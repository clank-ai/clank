# 0144. The QR code the console shows is drawn by segno

- Status: Accepted (Claude, with plan s57; the owner's standing word: no dependency without a decision that says why)
- Date: 2026-10-26
- Decided by: Claude

## Context

Design 0025 §2: the console shows a QR code that carries the phone's pair link, so pairing takes a scan and no typing.
Clank has no QR encoder. Writing one is some five hundred lines of tables (the Reed-Solomon generator polynomials,
the alignment positions, the format and version bits, eight masks and their penalties), and nothing here could check
the result but a phone's camera.

## Decision

- Clank depends on **segno** (a QR encoder: pure Python, no dependency of its own, BSD-3 license, tested against the
  standard's vectors). It makes the QR's modules; Clank draws them itself (as text for the console, two modules a
  character), so nothing else of the library is used.

## Alternatives considered

- **An encoder of Clank's own**: five hundred lines that a bug in a table would make unscannable, with no way to test
  them here.
- **`qrcode`**: pulls in Pillow for its images; Clank wants the modules only.
- **A link with the code to type**, as today: the owner's words rule it out.

## Consequences

- One dependency more (`segno`), pinned in `uv.lock`; `remote/qr.py` is the one module that imports it.
- The console's Phone page shows the QR with the link under it; `clank remote pair` prints the link for a terminal that
  cannot show one.
