# Plan s57: Clank for iPhone, step 1: the shell and the stream

Design 0025 §1 to §3, §5 and §11 step 1 (decision 0143), on design 0005's listener, pairing and traffic log: the
phone page becomes an installed app that pairs from a QR the console shows, holds a device token renewed on use, is
live from one stream of events, shows Now as the canvas drew it, and says plainly when the stream drops or the PC
cannot be reached. Flows, sessions, Work, Files, More and notifications come in the next steps; until then their tabs
show what today's page shows (workspaces and sessions, files, the log).

## What exists

- The phone listener (`remote/app.py`): its own FastAPI app on `127.0.0.1:7721`, published by Tailscale; every
  request through Tailscale from the owner's login; a paired device's cookie (`devices.py`: codes hashed, used once,
  tokens 30 days from last use and 90 from pairing); the page's files from the package (`page/`); `_overview` (the
  model, the agent's requests, the machine, the workspaces and sessions, the questions, the marks, the files); every
  exchange logged (`traffic.py`).
- The console's Phone page (`remote/console/phone.py`): `x`, `p` (a code to type), `c`, `d`, Enter on a device.
- The kernel's event stream (`kernel/api.py`, `event_stream`): `connected`, the events after `after`, `reset` when
  pruned, keepalives; the events' `summary` is their title.
- The extension's page tests drive a page in headless Edge from Node (`vscode/test/*.page.test.ts`).

## Choices made here

- **The stream is the listener's** (`/api/stream`): `now` (what `_overview` gives, less the files) when it changes
  (looked at every second), the kernel's events with their summary as title and an `attention` flag (a question
  asked, a permission, a flow's gate or end, a box out of tries, a cost limit, a model failed), resumed from
  `Last-Event-ID` through the kernel's event log; a keepalive every fifteen seconds.
- **The QR** is drawn by `segno` (pure Python, no dependency of its own, BSD): a QR encoder is five hundred lines of
  tables that nothing here could check; decision 0144.
- **Pairing from the link**: `GET /pair?code=` pairs the device by the code in the query and serves the install steps;
  the icon's start link carries a one-time install claim (`?claim=`), which the first launch trades for the cookie;
  `GET /manifest.webmanifest` is served per device with that start link. A device's token renews on each use and
  lapses after 30 days unused; the 90-day ceiling goes (design 0025 §2).
- **The page's logic that can be tested without a browser** (the stream's state: live, reconnecting, offline, with the
  ages; Now's cards from the `now` payload) is `page/model.js`, an ES module Node's test runner imports
  (`tests/phone/*.test.mjs`, a step of `tools.check`); `app.js` draws from it.

## Tasks

- [x] 1. **The stream** (`remote/stream.py`, `/api/stream`): `phone_stream(remote, after)`: `connected`; `now` first and
  when it changes; each event with `title` (its summary), `type`, `time`, `attention`; `Last-Event-ID` resumes the
  events; `reset` when they were pruned; keepalives; `closing` with the service. `ATTENTION` names the types. Tests
  (`test_phone_stream.py`) over the listener's test client: the first `now`, an event recorded appears with its title
  and flag, a `now` change comes once, a resume from an id.
- [x] 2. **Install** (`devices.py`, `app.py`, `page/install.html`): `GET /pair?code=` (the login checked, the code
  spent, the cookie set, the steps served); `install_claim(device)` and `GET /?claim=` (the claim spent for the
  cookie; a claim lapses after an hour); the manifest per device; tokens renewed on each use, the 90-day ceiling gone;
  `Remote.pair_link(name)`: the link with the code, for the QR. Tests (`test_phone_install.py`).
- [x] 3. **The console's QR** (`remote/qr.py`, `remote/console/phone.py`): the QR as text (two modules a character,
  `▀▄█`), the link under it, the code's time left; `p` makes it, `r` a new one. Tests: the QR's modules are segno's,
  the frame.
- [x] 4. **The shell** (`page/index.html`, `sw.js`, `manifest.webmanifest`, `icon.svg`, `style.css`): five tabs, the
  header with the PC's name and the stream's state, the launch screen, the service worker caching the shell and
  answering the offline screen, the icon. `page/model.js`: `streamState(events, now)` (live, reconnecting with the
  pause's age, offline after 30 s with the tries), `nowCards(payload)` (the model and machine, Waiting for you with
  its actions, Working now). `app.js` on the stream: Now as §5 draws it; Flows, Work, Files, More as today's views
  under the new tabs. Node tests of `model.js`; `tools.check` runs them.
- [x] 5. **Docs**: design 0025 §11 step 1 built; the roadmap (M9); getting started (install the phone app); the
  console doc's Phone page; the plan index; the generated pages. Live: the QR on the owner's console, a pairing from
  the iPhone when the owner tries it (said in the message to the owner).

## Progress

Written 2026-10-26. Built 2026-10-26, with these differences from the tasks as written: the page's logic is
`model.mjs`, an ES module, so Node's runner and the browser import the same file (`app.js` is a module too), and
`nowCards` became the functions Now draws from (`modelLine`, `machineGauges`, `waitingCount`, `workingRows`,
`lastKnown`); a new QR is `p` again, not `r` (`r` reads the page again, as before); the Flows tab shows the flows'
questions until step 2 brings the Flow view; the icon is a PNG drawn by `icon.py` with the standard library (iOS
takes no SVG for a Home Screen icon, and the package keeps no binary); the install page is served filled in at
`/pair`, never as a static file; the service worker caches the page at `./`, not as `index.html` (the shell's test
found the page is served at the root only, so a cache by that name would have missed). The code map and the tests
page list the phone's JavaScript and its Node tests. Live: the QR drawn by `clank remote pair` on the owner's
machine; the pairing from the iPhone is the owner's to try.
