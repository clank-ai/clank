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
  `CLANK_HOME/secrets`, readable only by you: no record, event or log holds them, and clients see only their last four
  characters.
- **Your MCP servers' keys** go where such a server runs, beside the agent in a workspace's container, and only to the
  workspaces you give that server to (`clank mcp allow` in the folder, `m` on its page, `s` on the MCP servers page): a
  server of yours with secrets goes to no workspace until you do, and giving it to one that may use a cloud model asks
  first; allowing a workspace the cloud names first each such server its agent gets, so either way you are asked
  knowing the values can reach a model at a provider. There the values are in OpenCode's own environment alone, named from its configuration, never written in a
  file in the container, and never on a command line: every `docker exec` Clank makes names each variable alone, its
  value in the environment of the process that runs it (the console, the `clank` command and VS Code receive the values
  of the servers given to a workspace when they start its agent, to hand them to `docker exec`). **The agent of a
  workspace can read the values of the servers given to it**, as those servers can, and a cloud model the workspace
  uses can read what the agent reads.
- **Your secrets and state folders** (`CLANK_HOME/secrets` and `CLANK_HOME/state`, which holds the local token) can be
  opened only by you, whatever the folder above them allows, set each time Clank's service starts. On Linux and macOS
  each is mode 0700. On Windows each has an access list of its own: inheritance from the folder above is turned off,
  and only your account and SYSTEM (Windows itself) have access, full control, passed to every file inside; Clank reads
  the list at each start and rewrites it only when it differs. `clank doctor` (and `clank setup`, while it applies)
  names anyone else on those lists, with the `icacls` command that removes them (`chmod 700` elsewhere), for you to
  run; it changes nothing itself.
- **The phone page** is served only on your tailnet, through Tailscale, never the open internet: Clank refuses to
  publish it while Tailscale Funnel is on for its port, checks Tailscale's verified login on every request, and lets in
  only a device paired with a code made on the computer. Remote access is off until you turn it on.
- **The sandbox.** The agent runs in a container per workspace, which sees only that folder (as `/workspace`), runs
  as an ordinary user with no added capabilities and limits on CPU, memory and processes, and is on an internal
  network of its own: it reaches the model through Clank's gateway, and the internet only through Clank's proxy, to
  the hosts you allowed for that workspace (`clank network`; a host it asks for waits for your answer, and every
  exchange is in `clank network log`). Dev mode, which you turn on for testing (`clank dev on`, shown in the
  console's header), lets every public host out at once instead; a private address (your computer, your network,
  your tailnet) is refused in dev mode too.
- **Installing a folder's software** (its setup) runs in a separate container Clank starts, asking first and saying
  what runs: the folder's own install steps, which can run code from the folder. That container is on the
  workspace's network and reaches only the package indexes (`pypi.org` and `files.pythonhosted.org`: the set `setup`
  in `config/network-sets.json`, yours to change, `clank workspace sets` lists it), through Clank's proxy and only
  while it runs, each exchange in `clank network log`; a host not in the set is refused, dev mode or not. It runs with
  a clean home of its own and pip reading no configuration file, and Clank makes the workspace's `~/.venv` afresh
  first, so nothing written into the workspace's home changes what the setup runs.
- **A folder's own MCP servers** (its `.mcp.json`) are offered, never trusted: the agent gets one only after you allow
  it for that workspace, and only as its entry was when you allowed it (a changed command, argument or environment
  needs allowing again). Clank starts one only in the folder's workspace container, never on your computer: checking
  it (`clank mcp check`, or `c` on the MCP servers page) is refused, saying how, until the folder is a workspace whose
  container runs, and the check says whether the agent may use it as it is now. Your own servers (`clank mcp add`)
  are checked on your computer, or in the workspace with `--workspace`; one with secrets only in a workspace you gave
  it to, so a check never puts its values in the container of another.
- **The gateway** records every request, and sends a workspace's work to a cloud provider only after you agreed to
  that provider once and allowed that workspace; content marked local (Notion, and the MCP servers you mark) is kept
  from the cloud.
- **Changes to your files** wait for your review unless you switch a workspace to auto, and nothing the agent proposes
  for your Notion is written before you approve it.

## What it does not guard yet

- Commands the agent runs in its container change files in that folder without asking, in either mode: keep the
  folder under version control.
- macOS is untested. On Linux with Docker Engine the container tests run in continuous integration (GitHub's Ubuntu
  runner, Docker Engine from Docker's own packages): a container sees its folder and nothing else of the machine,
  nothing answers from inside but the edge, the computer's own address on a workspace's network answers nothing, and
  the container reaches the gateway through a socket only you and the edge can open (`~/.cache/clank/<home id>`).
