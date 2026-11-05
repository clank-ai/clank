# 0165. An artifact's page runs in a sandboxed frame of Clank's panel, as the one page the service builds

- Status: Accepted (the audit of 2026-10-30); completes 0156's guard on Open in browser; revises design 0021 §5
- Date: 2026-11-04

## Context

- An artifact's page and Clank's bar over it shared one webview document. The page's own scripts could call
  `acquireVsCodeApi()` (before the bar did: the bar came last) and send any of the bar's messages. Decision 0156 made
  Open in browser ask the owner first, and left the full fix for later: the page in a sandboxed frame that cannot
  reach the extension. This is that fix.
- The webview loaded the page's files and Clank's libraries from the folder and the extension (`localResourceRoots`).
  The service's export already built a version as one self-contained page: its files inside it, its libraries
  inlined, its fetches of its own files answered from inside it, its content policy first (decision 0156).
- A frame can be given its page as `srcdoc`, as a `blob:` address or as a `data:` address. Measured 2026-11-04 in
  headless Edge (Chromium 156), the panel's HTML taken through the steps VS Code 1.144's webview host takes (parsed,
  written out again, and written with `document.write` into a frame of its own origin), with a page of 4.56 MB
  (Plotly inlined):
  - `srcdoc` drew the plot; the panel was written in about 60 ms.
  - `blob:` drew it too, once the panel's policy allowed `frame-src blob:`.
  - `data:` (an address of 6 MB) drew nothing.
  - The frame took the panel's content policy as well as its own: with a nonce policy in the panel, the page's
    inline scripts did not run.
- An export writes a page's own script or style sheet (`app.js`, `style.css`) into it as a `data:` address, which the
  export's policy did not allow: since 0.3.0b7 such a page broke in the browser, and it would have broken in the
  panel too.

## Decision

- **The panel's document is Clank's alone** (`artifactPanel` in the extension): Clank's bar (the title, the versions,
  Comment, Open in browser), the panel's one script, the only code that calls `acquireVsCodeApi()`, and an
  `<iframe sandbox="allow-scripts">` that holds the page. The frame gets no other flag. Without `allow-same-origin` the
  page has an origin of its own, out of reach of the panel's document and of VS Code's API; it cannot move the window,
  open one, submit a form, show a dialog or start a download. The panel's document listens to no message, so nothing
  the page posts reaches the extension: only the bar's clicks do.
- **The page reaches the frame whole, as its `srcdoc`**, in the panel's HTML, its ampersands and quotes escaped so the
  attribute ends only where Clank ends it. It needs no script, no message and no `frame-src`.
- **The service builds the page** (`Artifacts.page`): the very page an export writes, answered by `GET
  /agents/artifacts/{workspace}/{name}/page` with the artifact's title and how many versions it has. The panel loads
  nothing from disk (its `localResourceRoots` is empty).
- **The panel holds itself to the page's own policy.** The frame takes the panel's policy as well as the page's, so
  the panel allows what the page needs (inline scripts and `eval`, its files as data and blob) and nothing on the
  network. Its own script is inline too, since a nonce would stop the page's scripts. A test of the extension reads
  the service's policy and holds the two equal.
- **A page's own scripts and style sheets run**: the policy allows `data:` for scripts and styles. It already allowed
  inline ones, so nothing more can run, and still nothing on the network.
- **Open in browser still asks first** (decision 0156): in the browser the page runs outside any frame, held by its
  own policy alone.

## Alternatives considered

- **A `blob:` address**, made by the panel's script: it works as well, but needs a script, the page carried to that
  script anyway, and `frame-src blob:` in the panel's policy, which the page would take too.
- **A `data:` address**: a page of several megabytes drew nothing (Chromium takes no address over 2 MB).
- **A nonce for the panel's script**: the frame takes the panel's policy too, so the page's inline scripts and
  handlers would stop.
- **A page's own scripts and style sheets inlined as elements**, rather than allowed as data: `defer`, `async` and the
  order they load in would be lost.
- **More sandbox flags**: `allow-same-origin` would give the page the panel's document and VS Code's API back;
  `allow-downloads`, `allow-popups` or `allow-modals` would let the page put a file, a window or a dialog before the
  owner from inside VS Code.
- **The page left in the panel's document**, with 0156's question as its only guard: its scripts could still reach VS
  Code's API.

## Consequences

- An agent's page can no longer reach VS Code's API or send the bar's messages; a version, a comment and Open in
  browser come only from Clank's bar.
- The page is drawn as a browser draws it: on white, in its own colors and fonts, where before it took VS Code's
  theme for what it did not set. Clank's Markdown page too.
- While the page has the focus, VS Code's own keys (Ctrl+P, Ctrl+W) do not reach VS Code; a click on the bar, or
  outside the panel, gives them back.
- In the panel, the page's own downloads (Plotly's camera button) and its storage (`localStorage`) do nothing; in the
  browser they work. A page that reads its files with `XMLHttpRequest` rather than `fetch`, and a style sheet's own
  `url()` and `@import`, read nothing in either place, as in an export always.
- Each version shown is built by the service and sent to the panel whole (Plotly alone is 4.5 MB): the panel needs
  the service running, as listing, commenting on and exporting artifacts already did.
