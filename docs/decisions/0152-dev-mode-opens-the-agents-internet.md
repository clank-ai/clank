# 0152. Dev mode opens the agent's internet: every public host at once, no question; private addresses still never

- Status: Accepted (the owner's request of 2026-10-29: "In dev mode, these types of restrictions should be completely
  lifted"); extends [0149](0149-dev-mode-asks-any-provider-for-testing.md); lifts
  [0141](0141-the-internet-through-clanks-proxy-by-allowance.md)'s allowances while dev mode is on, its refusal of
  private addresses kept
- Date: 2026-10-29
- Decided by: the owner (the request quoted below); how it is built, Claude (design 0024 §1, §3, §4, §6 and §7 and
  design 0016 §4, §15 and §16, revised after approval; [plan s64](../plans/s64-dev-mode-opens-the-internet.md))

## Context

- Decision 0141: the agent reaches the internet only through Clank's proxy, by the owner's allowances per workspace and
  host. A host not allowed is held up to a minute while the owner is asked in the console, refused otherwise, and not
  asked for again for ten minutes. Private addresses are never reached.
- On 2026-10-29 the owner gave the agent a benchmark that needs `git clone`. The clone's host was not allowed for the
  workspace; the owner was in OpenCode's window and never saw the question; the clone failed. The owner: "the model is
  having trouble doing the benchmark that I have assigned it because it has no ability to git clone and the network is
  blocked. In dev mode, these types of restrictions should be completely lifted."
- Dev mode (decision 0149) is the owner's switch for testing, and relaxed only the cloud's data policy. OpenCode's own
  web tools (`webfetch`, `websearch`) were denied in its configuration, and the agent's instructions said a host not
  allowed waits for the owner.

## Decision

- **Dev mode opens the agent's internet.** While it is on, the proxy lets every public host out at once, for every
  workspace, whatever its allowances: nothing is held, nothing asked, no quiet period. A connection held while the
  owner is asked goes out once dev mode is turned on.
- **Private addresses stay refused**, dev mode or not, before resolving and after: this machine, the local networks,
  the tailnet's range, other containers. That keeps the agent from Clank's own service and the owner's network; the
  gateway is still reached only on the edge's gateway port.
- **Recorded as always.** Every exchange stays in the network log (host, bytes each way, time; never a body); one that
  dev mode let out says why: `dev mode`.
- **When it applies**: from the next connection, for running workspaces too, with no container restarted (the gateway
  reads it with its routes, every second, beside the allowances). Turned off, it applies to the next connection; one
  already open finishes. The allowances are never rewritten, and apply again once it is off.
- **OpenCode may fetch and search.** In dev mode its configuration allows `webfetch` and `websearch`; the configuration
  is written when OpenCode next starts in a folder, so a window already open gets it when it starts again.
- **The agent is told.** In dev mode its network instructions say every public host answers at once, with no question
  and no wait, and private addresses still never. They are one file (`network.md`), written as dev mode says at each
  start of the agent and again in every running container whenever dev mode changes: no dev mode instruction outlives
  dev mode.
- **Said wherever dev mode is**: the header's pill reads "dev mode: any provider, any host", whatever providers there
  are; `D` on Providers and models asks first in words that say both halves and when each applies, and works without a
  provider; `clank dev` says both; This folder says the agent reaches every public host.
- Still one setting, `runtime.json`'s `dev_mode`, off by default, turned on or off as decision 0149 says.

## Alternatives considered

- **A setting of its own for the internet**, beside dev mode: the owner asked for dev mode to lift these restrictions;
  two switches for one testing state is one more to forget to turn off.
- **Allowing the hosts the benchmark needs** (the Code set: `clank workspace allow FOLDER --set code`): it lets `git
  clone` reach GitHub, but the owner asked for the restrictions lifted, and each other host a benchmark reaches would
  wait for a question again.
- **Showing the question in OpenCode's window**: the ask stays the normal mode's way; seeing it sooner is not lifting
  it.
- **Opening private addresses too**: the agent could then reach Clank's own service (guarded by its local token alone),
  the owner's network and the tailnet. Not asked for, and nothing a benchmark from the internet needs.
- **Writing every host into the workspaces' records**: turning dev mode off could not then restore what the owner had
  allowed, as decision 0149 says of the data policy.

## Consequences

- With dev mode on, a workspace's agent can download anything, and can send what it reads to any public host. The
  owner turns it on for testing and off after; the header says it is on.
- The network log is the record of what dev mode let out (`clank network log`, Requests · F7's `n`).
- A private address is still refused: a test that needs this machine or the owner's network fails, by design.
- Dev mode matters without a cloud provider now, so the console reads it on its own (`GET /runtime/dev`).
- Any further relaxation for testing joins dev mode only with a decision of its own, as decision 0149 said.
