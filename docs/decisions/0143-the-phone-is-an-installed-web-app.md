# 0143. The phone is an installed web app on the iPhone, not a native app

- Status: Accepted (the owner's choice, 2026-10-21: an installed web app, not native; the canvas approved the same day);
  written 2026-10-26 with design 0025
- Date: 2026-10-21
- Decided by: the owner (the choice), Claude (the design)

## Context

Design 0005's phone page is a Safari tab: a link to find, a code to type once, a page that asks the PC every few
seconds, no notifications. The owner wants "something much closer to a full phone application instead of having to go
to a link every time", on an iPhone.

## Decision

- Clank's phone is a **web app installed from the PC** (Add to Home Screen): full screen from its own icon, a service
  worker for its shell and its notifications, one device token renewed on each use, one live stream of events. It is
  served by the phone listener from Clank's package, as the page is today, and updates with Clank.
- It is **not a native app**: no store, no signing, no second code base; what iOS gives a Home Screen web app (full
  screen, web push since iOS 16.4, its own storage) is what the design needs.
- It stays **inside the tailnet** (decision 0012): installed from a QR the console shows, paired by a one-time code
  that rides in the link, and reached through Tailscale only; pushes, the one thing that leaves, go encrypted through
  Apple's push service, and can be turned off.

## Alternatives considered

- **A native iOS app**: a store or a developer account, signing, a second code base to keep in step with Clank's API,
  for no capability the design needs beyond what a Home Screen web app has.
- **The Safari page as it is**: the owner's words rule it out.
- **A messaging app or ntfy** for alerts: decided against in decision 0012 (a third party would read the text).

## Consequences

- Design 0025 describes the app; its first step is the shell and the stream (plan s57).
- Web push needs P-256 and AES-GCM, which the standard library lacks: a dependency decision comes with that step.
- iOS keeps a Home Screen app's storage apart from Safari's, so the pairing is carried into the installed app by a
  one-time install claim in the icon's start link.
