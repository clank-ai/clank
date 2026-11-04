# 0157. What the phone serves and the proxy lets through

- Status: Accepted (the audit of 2026-10-30); revises design 0025 §8
- Date: 2026-11-04

## Context

- The phone's listener serves the files the agents sent (`send_to_phone`, design 0005 §3) from each workspace's
  `.clank/outbox/`, a folder the agent can write. It served any of them but the notes with the type its name gave, so
  a page, a drawing (SVG) or a script was served as one, in the app's own origin, where the device's cookie is.

## Decision

- **A sent file is seen in place only when it is of an inert kind**, by its name's ending (`SEEN` in
  `remote/outbox.py`): a raster image (PNG, JPEG, GIF, WebP), a PDF or plain text, served as its own type, inline,
  with `X-Content-Type-Options: nosniff` so no browser takes it for another.
- **Any other file is a download**: served as `application/octet-stream` with `Content-Disposition: attachment`.
- **Every answer under `/api/files` carries `Content-Security-Policy: sandbox`**, in place of the app's own policy: what
  is served there has an origin of its own, and runs no script and sends no form.
- The list of files says each one's type as it is served, and the page's links save a download (`download`).

## Alternatives considered

- **A list of active types refused** (HTML, SVG, scripts): a list of what is dangerous is never complete; a list of
  what is inert is.
- **The files on an origin of their own**, without the device's cookie: the strongest, but it needs a second name or
  port published on the tailnet and its own pairing; kept for later. The sandbox gives the file an origin of its own
  now.

## Consequences

- A picture, a PDF or a text the agent sent opens on the phone as before. A page, a drawing or a notebook is saved,
  then opened from the phone's files, outside the app.
- A file whose name ends otherwise than its content is served by its name: an image's type never makes a page run, and
  `nosniff` keeps the browser from guessing.
