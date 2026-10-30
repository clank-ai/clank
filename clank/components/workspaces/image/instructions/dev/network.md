# The internet

**Dev mode is on.** The owner turned it on for testing: your container reaches every public host at once through
Clank's proxy, with no question and no wait, whether or not the host was allowed for this workspace. The proxy is
already set for you (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`): `curl`, `pip`, `uv`, `git` over HTTPS, and Python's
`requests` and `httpx` use it without being told. Node's own `fetch` does not: use `curl` or Python for the web.
Clank's gateway (`edge`) is reached directly, as always.

- **Every public host** answers as it would anywhere: clone, install and download what the task needs. Clone over
  HTTPS (`git clone https://github.com/OWNER/REPO`): SSH (`git@github.com:...`) does not go through the proxy. Where
  the literature's calls below say a host is asked for, in dev mode it is not.
- **OpenCode's `webfetch` and `websearch`** may be used in a window started while dev mode is on; one started before
  refuses them: use `curl`.
- **Private addresses** (this machine, the local network, the tailnet) are still never reached.
- Every exchange is logged by host, size and time, never by content. Keep requests few and purposeful.
- When the owner turns dev mode off, only the hosts allowed for this workspace answer again; a refused request says so
  in plain words.
