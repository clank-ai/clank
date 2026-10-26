# The internet

Your container reaches the internet only through Clank's proxy, and only the hosts the owner allowed for this
workspace. The proxy is already set for you (`HTTP_PROXY`, `HTTPS_PROXY`, `ALL_PROXY`): `curl`, `pip`, `uv`, `git`
over HTTPS, and Python's `requests` and `httpx` use it without being told. Node's own `fetch` does not: use `curl` or
Python for the web. Clank's gateway (`edge`) is reached directly, as always.

- **A host that is allowed** answers as it would anywhere.
- **A host that is not allowed** holds your request while the owner is asked, for up to a minute: the request may take
  that long, then it goes through (the owner allowed it once, or always for this workspace) or fails with `403` and
  words that say the host was refused. A refused host is not asked for again for ten minutes: do not retry it. If you
  need it, ask the user once, in words, naming the host and why; otherwise work without it.
- **Private addresses** (this machine, the local network) are never reached, whatever is allowed.
- Every exchange is logged by host, size and time, never by content. Keep requests few and purposeful.

## The literature, without a search engine

These public APIs answer without a key. Each host is in the owner's **Papers** set (`clank workspace allow FOLDER --set
papers`); if one is not allowed yet, the owner is asked on your first request.

- **arXiv**: `https://export.arxiv.org/api/query?search_query=all:%22kinetic+inductance%22&max_results=5` (Atom XML;
  `search_query` takes `ti:`, `au:`, `abs:`, `cat:` and boolean `AND`/`OR`; `id_list=2401.01234` fetches one). Wait
  three seconds between arXiv requests: it answers `429` and holds the connection when hurried.
- **Semantic Scholar**: `https://api.semanticscholar.org/graph/v1/paper/search?query=kinetic+inductance&limit=5&fields=title,year,authors,externalIds,citationCount`
  (JSON; `/graph/v1/paper/DOI:10.1103/...` or `/graph/v1/paper/arXiv:2401.01234` for one paper, `?fields=references,citations` for its graph). About one request a second without a key.
- **Crossref**: `https://api.crossref.org/works?query=kinetic+inductance&rows=5` (JSON; `/works/10.1103/...` resolves a
  DOI to its metadata; add `&mailto=` with the user's address only if they give it).
- **OpenAlex**: `https://api.openalex.org/works?search=kinetic+inductance&per-page=5` (JSON; `/works/doi:10.1103/...`
  for one; `filter=publication_year:2024,cited_by_count:>10` narrows).

Resolve a reference by its DOI first (Crossref or OpenAlex), then read the paper itself from arXiv when it is there
(`https://arxiv.org/pdf/2401.01234`); say which source each fact came from.
