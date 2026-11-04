# 0157. What the phone serves and the proxy lets through

- Status: Accepted (the audit of 2026-10-30); revises design 0025 §2 and §8, and design 0024 §7
- Date: 2026-11-04

## Context

- The phone's listener serves the files the agents sent (`send_to_phone`, design 0005 §3) from each workspace's
  `.clank/outbox/`, a folder the agent can write. It served any of them but the notes with the type its name gave, so
  a page, a drawing (SVG) or a script was served as one, in the app's own origin, where the device's cookie is.
- The agent's proxy (design 0024 §7) refuses private addresses, the tailnet's range among them, but judged an IPv6
  address only as IPv6: one that carries an IPv4 address (mapped, `::ffff:a.b.c.d`, which reaches a.b.c.d; 6to4;
  Teredo) passed when the IPv4 one was in the tailnet's range, as a literal or as what a name resolved to.
- The phone's traffic log (design 0025 §2) masked an install claim in the link asked for, but kept the bodies sent
  whole: the page the icon is added from and the manifest carry the claim in their links. Its test masked a claim it
  had made up, never the one `/pair` issued.

## Decision

- **A sent file is seen in place only when it is of an inert kind**, by its name's ending (`SEEN` in
  `remote/outbox.py`): a raster image (PNG, JPEG, GIF, WebP), a PDF or plain text, served as its own type, inline,
  with `X-Content-Type-Options: nosniff` so no browser takes it for another.
- **Any other file is a download**: served as `application/octet-stream` with `Content-Disposition: attachment`.
- **Every answer under `/api/files` carries `Content-Security-Policy: sandbox`**, in place of the app's own policy: what
  is served there has an origin of its own, and runs no script and sends no form.
- The list of files says each one's type as it is served, and the page's links save a download (`download`).
- **The proxy judges an IPv6 address by the IPv4 one it carries** (`private_address` in `gateway/proxy.py`): a mapped
  one by that IPv4 address alone, a 6to4 one and a Teredo one (its server and its client) by each IPv4 address as well
  as by itself; as a literal and as what a name resolves to, before any allowance and in dev mode too.
- **An address that is not public is refused**: what `ipaddress` calls not global, besides the private, loopback,
  link-local, unspecified, multicast and reserved addresses and the ranges the proxy names (the tailnet's, this host's,
  unique local and link-local IPv6).
- **The phone's log masks an install claim in every body it keeps** (`remote/traffic.py`): a link's `claim=` value,
  in a page, the manifest or any other text or JSON, as it was already masked in the link asked for. The test takes
  the claim `/pair` issued, trades it, and finds it nowhere in the log.

## Alternatives considered

- **A list of active types refused** (HTML, SVG, scripts): a list of what is dangerous is never complete; a list of
  what is inert is.
- **The files on an origin of their own**, without the device's cookie: the strongest, but it needs a second name or
  port published on the tailnet and its own pairing; kept for later. The sandbox gives the file an origin of its own
  now.
- **Refuse every IPv6 address that carries an IPv4 one**: simpler, but a mapped public address is a public address,
  and a program may be given one.
- **Rely on `ipaddress` alone**: what it says of a mapped, 6to4 or Teredo address has changed between Python
  releases; the proxy now says it itself, the same on every Python Clank runs on.
- **Keep no body of the install page and the manifest**: simpler, but the log is there so the owner sees everything a
  phone was sent; masking the claim alone keeps the rest of what was sent visible.

## Consequences

- A picture, a PDF or a text the agent sent opens on the phone as before. A page, a drawing or a notebook is saved,
  then opened from the phone's files, outside the app. How each browser's PDF viewer takes the sandbox is to be seen
  on the owner's iPhone; a viewer that refuses it leaves the PDF to save.
- A file whose name ends otherwise than its content is served by its name: an image's type never makes a page run, and
  `nosniff` keeps the browser from guessing.
- No way of writing a private IPv4 address reaches it through the proxy; a public one written as IPv6 still goes out.
- The phone's log keeps no install claim; a text that happens to hold `claim=` is masked there too, which costs
  nothing but those characters in the log.
