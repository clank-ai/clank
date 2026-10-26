# Design 0024: Network access for the agent (M7)

The agent reaches the internet only through Clank, and only where the owner allowed, workspace by workspace.

A workspace's container joins an internal network where nothing answers but the edge, and the edge forwards one
port to the gateway (design 0004 §3). So the agent cannot fetch a paper, read a package's documentation, download a
data set or `pip install` a library while it works (only a workspace's setup runs with the internet, design 0004
§10). For research this is the largest gap the review of 2026-10-26 found (the inspection that led to design 0023).
This design opens the network the way Clank opens everything: visibly, by the owner's word, recorded.

## Sections

| § | Section | Status |
| --- | --- | --- |
| 1 | The rule: through Clank, by allowance | Approved 2026-10-26; built 2026-10-26 ([plan s53](../plans/s53-the-proxy.md)): the allowances, `clank workspace allow --host`; the console's and VS Code's keys with §4 |
| 2 | The way out: a forward proxy at the gateway | Approved 2026-10-26; built 2026-10-26 ([plan s53](../plans/s53-the-proxy.md)) |
| 3 | A host the agent asks for | Approved 2026-10-26; built 2026-10-26 ([plan s54](../plans/s54-the-ask.md)) |
| 4 | What the owner sees | Approved 2026-10-26 |
| 5 | Packages, papers, data: the named sets | Approved 2026-10-26 |
| 6 | Search | Approved 2026-10-26 |
| 7 | What is never reached | Approved 2026-10-26; built 2026-10-26 ([plan s53](../plans/s53-the-proxy.md)) |
| 8 | Order of work | Approved 2026-10-26 |

## 1. The rule: through Clank, by allowance

- **Nothing leaves a workspace's container except through Clank's proxy**, and the proxy lets a request out only to a
  host the owner allowed for that workspace. The container's network stays internal; no second network, no route out.
- **Allowances are per workspace and per host**, kept in the workspace's record (`hosts`: a list of host names, each
  exact (`pypi.org`) or a suffix (`.arxiv.org`, which allows `arxiv.org` and every name under it)), with when and how
  each was allowed. Every workspace starts with none, as it starts on this machine only (design 0016 §9).
- **The owner allows** from the console's This folder page, `clank workspace allow --host NAME`, VS Code, and the
  phone later; takes an allowance back the same way; and sees every allowance in the workspace's record.
- **Deny wins** (decision 0018): a host both allowed and denied is denied; a host in §7 is denied whatever the record
  says.

## 2. The way out: a forward proxy at the gateway

- **The proxy** is a part of the gateway component (`gateway/proxy.py`, the standard library's `asyncio`, no new
  dependency): an HTTP/1.1 forward proxy on the host's loopback beside the gateway, `CONNECT` for TLS (a tunnel, bytes
  both ways, never opened) and plain HTTP forwarded as it is. **The edge forwards its port** to the host as it forwards
  the gateway's (`edge.py` takes several port pairs), so a container reaches it as `edge:<port>`.
- **The container is told**: `HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY` and `NO_PROXY=edge,localhost,127.0.0.1` in its
  environment (`run_arguments`), with the workspace's own token in the proxy's URL (`http://<token>@edge:<port>`),
  as the gateway's token is given today; the token names the workspace to the proxy, so each request meets its
  workspace's allowances and no other's. `pip`, `uv`, `curl`, `wget`, `git` over HTTPS, Python's `requests` and
  `httpx`, and Bun's `fetch` (OpenCode's `webfetch` tool) honor these variables; Node's own `fetch` does not, and the
  instructions say to use `curl` or Python (to measure: which of the agent's usual programs need telling otherwise).
- **Names are resolved at the proxy** (the container has no way to the internet's DNS): a `CONNECT host:443` carries
  the name, and the proxy checks it against the allowances before resolving it.
- **A refused request** is answered `403` with a body in plain words: the host, that it is not allowed for this
  workspace, and how it is allowed (`clank workspace allow --host NAME`, or the ask of §3). The agent reads it in its
  tool's error and can say so, or ask.
- **Recorded** (§4): every exchange's time, workspace, host, method, status, bytes each way and duration; for plain
  HTTP the path too; never the bodies, never the bytes of a tunnel.

## 3. A host the agent asks for

- When the agent reaches a host that is not allowed, the proxy **holds the connection** for up to `ASK_SECONDS` (60)
  and raises a question to the owner through the kernel (as a permission is raised): "readout-check's agent wants
  `api.semanticscholar.org`: allow once, always for this workspace, or not?". Answered *always*, the host joins the
  record and the request goes out; *once*, it goes out this time; *no* or unanswered, `403` with the words of §2, and
  the same host is not asked again for `QUIET_MINUTES` (10) in that workspace, so a retrying program does not flood
  the owner.
- The question shows in the console (Waiting for you), in VS Code (as a permission does) and on the phone later; the
  agent's instructions (`network.md`) say that a refused host may be asked for once, in words, and otherwise to work
  without it.
- The hold costs the agent a wait, not a failure: a `pip install` or a `curl` that the owner allows within the minute
  simply succeeds.

## 4. What the owner sees

- **Requests · F7** gains a **Network** view beside the model's requests: one line an exchange (when, workspace, host,
  status, bytes, time), the day's bytes by host, and the hosts allowed per workspace; the same from `clank network
  log` and `clank network hosts`.
- **The Monitor's Now panel** says when the session's agent is fetching ("fetching `export.arxiv.org` · 1.2 MB · 3 s"),
  from the proxy's exchanges in flight, joined to the session as its model requests are (design 0012 §3).
- **This folder** lists the workspace's allowed hosts under its software, with `h` to allow or take one back.
- The log is a file a day under `logs/network/`, kept `KEEP_DAYS` (30) as the gateway's records are; the phone's log
  shows it later.

## 5. Packages, papers, data: the named sets

Clank offers named sets the owner allows with one key, each listing what it opens:

| Set | Hosts | For |
| --- | --- | --- |
| Python packages | `pypi.org`, `files.pythonhosted.org` | `pip install` into the workspace's environment while it works |
| Papers | `arxiv.org`, `export.arxiv.org`, `api.semanticscholar.org`, `api.crossref.org`, `doi.org`, `api.openalex.org` | finding and reading papers, resolving references |
| Code | `github.com`, `raw.githubusercontent.com`, `codeload.github.com`, `api.github.com`, `gitlab.com` | reading and cloning public code |
| Data and models | `zenodo.org`, `huggingface.co`, `cdn-lfs.huggingface.co`, `osf.io` | data sets and model files |
| Documentation | `docs.python.org`, `numpy.org`, `scipy.org`, `matplotlib.org`, `pandas.pydata.org` | the documentation of what the container has |

A set is sugar over §1's allowances: allowing it writes its hosts into the record, each marked with the set's name;
the sets live in a readable file (`config/network-sets.json`) the owner can change. With the Python set allowed, a
workspace's `~/.venv` takes `pip install` directly (it already sees the image's scientific packages, decision 0138);
the setup command stays for the reproducible install.

## 6. Search

Search is not a host but a provider, and a choice of the owner's:

- **Literature first, without a provider**: with the Papers set, the agent searches arXiv, Semantic Scholar, Crossref
  and OpenAlex through their public APIs; the instructions give the four calls. For research this covers most of what
  "search" means, without a key or a third party reading the queries.
- **A web search API later**, as the cloud model is (design 0016): a provider record with a key (Brave Search, Tavily or
  another), an MCP tool `search_web` served by the gateway, each query recorded with its cost; the owner adds it if the
  literature APIs are not enough. A self-hosted search engine in a container is the other way, heavier and keyless;
  **Choice**: the owner decides which, when the need shows.

## 7. What is never reached

- **Private addresses**: the machine (`host.docker.internal`, the host's own addresses), the local networks (the RFC
  1918 ranges, link-local, the tailnet's range), other containers; the proxy refuses them before resolving and after
  (a public name that resolves to a private address is refused too).
- **The gateway and the service**: reached only on the edge's gateway port as today, never through the proxy.
- **Plain HTTP to a host allowed for HTTPS** is allowed (the allowance is the host's), but recorded with its path.
- The proxy never opens a tunnel's bytes, keeps no body, and holds no credential of the owner's: a site that needs a
  key gets it from the agent's own request (a token in the folder's `.env`, the owner's), as it would without Clank.

## 8. Order of work

1. **Built 2026-10-26** ([plan s53](../plans/s53-the-proxy.md)). The proxy, the edge's second port, the container's
   environment, the record's `hosts`, `clank workspace allow --host`, the `403` words, the log file; tests against a
   fake upstream on this machine and the forwarding tests of the edge (design 0004 §3). The workspace's token in the
   proxy's URL is derived from the service's local token (the SHA-256 HMAC over the workspace's name), so the
   gateway checks it without being handed anything; the allowances ride on the routes the gateway fetches.
2. **Built 2026-10-26** ([plan s54](../plans/s54-the-ask.md)). The ask of §3: the hold, the question, its answers,
   the quiet period; tested with a fake ask on the proxy and the kernel's questions on the service.
3. The named sets, their file, the console's key.
4. Requests · F7's Network view, the Now panel's fetching line, This folder's hosts.
5. The instructions (`network.md`) and the literature calls; getting started: how to let the agent fetch.
6. Search, when the owner chooses a way.

Decisions this design asks for, written when it is approved: the agent reaches the internet only through Clank's proxy,
by the owner's allowances per workspace and host; private addresses are refused always. No new dependency.
