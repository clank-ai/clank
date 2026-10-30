# Security

Clank runs an AI agent on your computer, with your files and, if you add one, your API key. A problem in how it
guards them matters; please report it privately first.

## Reporting a problem

Use GitHub's private vulnerability reporting: on [the repository](https://github.com/clank-ai/clank), open
**Security**, then **Report a vulnerability**. Say what you found, how to reproduce it, and what it lets someone do.
Please do not open a public issue for it. You will get an answer, and a fix is released with a note in
[CHANGELOG.md](CHANGELOG.md) once it is ready.

Clank is in beta: fixes go into the newest version only.

## What Clank guards

- **The local API** listens on `127.0.0.1` only, and every request needs the local token, a file in Clank's own folder
  (`CLANK_HOME`, `%USERPROFILE%\.clank` by default) readable only by you. The console, the `clank` command and the
  VS Code extension read it each time they connect.
- **Keys and tokens** (a cloud provider's API key, Notion's secret, an MCP server's keys) are kept one file each in
  `CLANK_HOME/secrets`, readable only by you, and nowhere else: no record, event or log holds them, and clients see only
  their last four characters.
- **The phone page** is served only on your tailnet, through Tailscale, never the open internet: Clank refuses to
  publish it while Tailscale Funnel is on for its port, checks Tailscale's verified login on every request, and lets in
  only a device paired with a code made on the computer. Remote access is off until you turn it on.
- **The sandbox.** The agent runs in a container per workspace, which sees only that folder (as `/workspace`), runs
  as an ordinary user with no added capabilities and limits on CPU, memory and processes, and is on an internal
  network of its own: it reaches the model through Clank's gateway, and the internet only through Clank's proxy, to
  the hosts you allowed for that workspace (`clank network`; a host it asks for waits for your answer, and every
  exchange is in `clank network log`). Dev mode, which you turn on for testing (`clank dev on`, shown in the
  console's header), lets every public host out at once instead; a private address (your computer, your network,
  your tailnet) is refused in dev mode too. Installing a folder's software runs in a separate container Clank
  starts, asking first.
- **The gateway** records every request, and sends a workspace's work to a cloud provider only after you agreed to
  that provider once and allowed that workspace; content marked local (Notion, and the MCP servers you mark) is kept
  from the cloud.
- **Changes to your files** wait for your review unless you switch a workspace to auto, and nothing the agent proposes
  for your Notion is written before you approve it.

## What it does not guard yet

- Commands the agent runs in its container change files in that folder without asking, in either mode: keep the
  folder under version control.
- Linux and macOS are untested. On Linux with Docker Engine, the container reaches the gateway through a socket only
  you and the edge can open (`~/.cache/clank/<home id>`), but the container tests have not run there yet: among them,
  whether a workspace's container reaches the computer's own address on its network, where a server listening on every
  address would answer it. Docker Engine's own adapter is still being built.
