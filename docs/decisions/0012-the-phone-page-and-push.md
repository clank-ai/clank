# 0012. Clank reaches its user's phone through its own page and push alerts, a service the user switches on and off

- Status: Accepted
- Date: 2026-10-11
- Decided by: the owner's answer to "How should Clank reach you on your phone first? (Other ways can be added later
  as adapters.)": "Clank's phone page + push, together with the ability to run this service on and off from Clank."

## Context
The user is often away from the computer while the agent works. The agent may need an approval or an answer; the user
wants to watch the work and to start tasks from the phone (to ask the model, away from the computer, to find a
figure and send it). A proven pattern exists for such pages: served to the phone over Tailscale, with Tailscale's
verified login checked on every request, and each device paired once with a code created on the computer (a second
factor).

The options were: Clank's own page with push alerts; a messaging app (Telegram, Signal, Discord, Slack) through a bot;
the ntfy app; email.

## Decision
- **The phone page.** Clank serves a small page for the phone over the user's tailnet, never the open internet. On it
  the user approves or rejects, answers the agent's questions, watches the work, starts tasks, and receives files.
- **Pairing.** A device gets access only by pairing, which is started on the computer (never from a device): the
  tailnet's verified login, plus a token of the device's own.
- **Push alerts.** Alerts use Web Push: the phone's own push service (Apple's or Google's) carries each one encrypted
  end to end (RFC 8291), so that service sees only that a message arrived, not what it says.
- **On and off.** Reaching the phone is a service the user switches on and off from Clank (the console, VS Code, the
  command line). While it is off, nothing listens on the tailnet and no alert is sent.
- **More ways later.** Each way of reaching the user is a channel adapter, so a messaging app, ntfy or email can be
  added without changing the rest.

## Alternatives considered
- **A messaging app.** Buttons and replies in a chat the user already uses, but messages pass through that company's
  servers (Signal excepted), and it needs a bot account.
- **ntfy.** Good alert buttons, but another app and another server to run.
- **Email.** Works everywhere; the slowest, with links instead of buttons.

## Consequences
- Clank's API is built for remote clients from the skeleton on: devices, scopes, tokens and the tailnet's identity
  check (design 0002).
- Clank's push key pair is kept with the user's secrets (`CLANK_HOME/secrets/`).
- On an iPhone, alerts need the page added to the home screen (iOS 16.4 or later).
- Clank contacts the push services' hosts; Clank's own list of the hosts it contacts says so.
- Whether the service is on, which devices are paired, and every alert sent are shown in the console and recorded.
