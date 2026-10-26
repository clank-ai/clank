# Plan s54: network access for the agent, step 2: a host the agent asks for

Design 0024 §3 (and §8 step 2), decision 0141, approved 2026-10-26, on the proxy of step 1 ([plan s53](s53-the-proxy.md)):
when the agent reaches a host that is not allowed, the proxy holds the connection and the owner is asked, once, always
for this workspace, or not; answered *always*, the host joins the record and the request goes out; *once*, it goes out
this time; *no* or unanswered, the request is refused and the host is not asked again for a while, so a retrying
program does not flood the owner.

## What exists

- The proxy (`gateway/proxy.py`) refuses a host not allowed with 403 and the words; its allowances come from the
  routes; it runs in the gateway's process, which reaches the service as the client `gateway` (`cloud_wanted` in
  `server.py`'s `main`).
- The kernel's questions (`kernel/questions.py`): `ask(QuestionDraft)`, `answer`, `on_resolved`, expiry; the cloud
  question (`workspaces/cloud.py`) as the pattern: a `choice` with options and keys, `about` the workspace, withdrawn
  when answered from a client.
- The allowances (`Workspaces.allow_host`, the record's `hosts`, the event `workspaces.host_allowed`).

## Choices made here

- **The hold is the proxy's; the question is the service's.** The gateway process asks the service
  (`POST /workspaces/{name}/hosts/wanted`), which allows at once when the record does, refuses at once in a quiet
  period, else asks the owner and names the question; the proxy then reads the question's decision
  (`GET /workspaces/hosts/wanted/{question}`) every half second until it is decided or `HOLD_SECONDS` (60) pass, the
  connection held meanwhile. No new channel: the service's API, as every other part uses it.
- **The quiet period is the service's** (`QUIET_MINUTES`, 10, per workspace and host), so every retrying program
  of the workspace meets the same answer, and the next ask after it is a new question.
- **Keys**: `y` allows always, `o` once, `n` refuses (the default when the question expires).

## Tasks

- [x] 1. **The asks** (`workspaces/network.py`, `HostAsks`): `wanted(workspace, host)` → `allowed` when the record
  allows; `quiet` (and no question) within the quiet period; else the open question of that pair, or a new one
  ("Let paper's agent reach api.semanticscholar.org?", the three options, expiring in `HOLD_SECONDS`, urgency high,
  about the workspace); `decision(question)` → `waiting`, or `always`, `once`, `no`; on resolution, *always* writes
  the allowance (`allow_host`, the answerer the actor), *no* and expiry start the quiet period. Tests with the kernel
  and its fake clock (`test_host_asks.py`).
- [x] 2. **The routes** (`workspaces/api.py`): `POST /workspaces/{name}/hosts/wanted` (`{"host"}`) and
  `GET /workspaces/hosts/wanted/{question}`; `Workspaces.network` holds the asks. Tests in `test_host_asks.py` over the
  service's test client.
- [x] 3. **The proxy asks** (`gateway/proxy.py`, `server.py`): `Proxy(ask=)`, an awaitable of the decision; a host
  not allowed is asked for when `ask` is given, the connection held; *always* and *once* let the request out (logged
  `why: asked, once` or `asked, always`); *no* refuses with words that say the owner was asked and did not allow it
  (and when it is asked again); `main` wires `ask` to the service's routes with the half-second reads and the
  60-second wait. Tests with a fake `ask` (`test_proxy.py`).
- [x] 4. **Docs**: design 0024 §3 and §8 step 2 built; getting started: the agent may ask, and you answer under
  Waiting for you; the roadmap, the plan index, the generated pages. Live: a `curl` to a host not allowed from the
  throwaway workspace, the question answered in the console (or `clank questions`), the request through.

## Progress

Written 2026-10-26, after step 1 was built and live-tested.

- All four tasks built 2026-10-26. Live on the owner's machine: a `curl` from the throwaway workspace's container to
  `export.arxiv.org` (not allowed) raised the question at once (`clank questions` showed it with its three keys);
  answered once, the held request got its 200 some six seconds after it began (the time the answer took); asked
  again and answered always, the record gained the host and the next request went through with no question; a
  host answered no was refused, and the next request to it was refused at once, quiet, with no new question.
  Seen on the way: arXiv's API answered 429 and then held a connection when asked three times in a few seconds (its
  own rate limit, not Clank's); a tunnel whose client gave up while the upstream still held it was logged without a
  status, so such an end is logged as status 0, `ended`, now.
