# Plan s55: network access for the agent, steps 3 and 5: the named sets, and the instructions

Design 0024 §5 (the named sets), §6's first paragraph (literature through the public APIs, without a provider) and §8
steps 3 and 5, decision 0141, approved 2026-10-26, on the proxy and the ask ([plan s53](s53-the-proxy.md),
[plan s54](s54-the-ask.md)): the owner allows a named set of hosts with one word, each set listing what it opens; the
sets live in a readable file the owner can change; the agent is told how it reaches the internet, that it may ask
once in words, and how to search the literature with the public APIs.

## What exists

- The allowances (`Workspace.hosts`, `Workspaces.allow_host`, `POST /workspaces/{name}/hosts`, `clank workspace allow
  FOLDER --host NAME`), the proxy and the ask.
- Clank's instructions to every agent: `clank/components/workspaces/image/instructions/*.md`, copied into the agent's
  home when its program starts (`agent_files`); OpenCode reads them all (`CURRENT_INSTRUCTIONS`, design 0020 §13).
- Readable configuration files in `CLANK_HOME/config` (the gateway's, the runtime's, the MCP servers').

## Choices made here

- **The sets file** is `CLANK_HOME/config/network-sets.json`: `{"<set>": {"hosts": [...], "for": "<what it opens>"}}`,
  written with design 0024 §5's five sets when it is missing, read each time it is used (the owner edits it, nothing
  need restart); a set that is not there is refused with the sets that are.
- **A set is sugar**: allowing it writes its hosts into the record one by one, each marked `(set <name>)` in its note;
  taking it back removes those hosts (and only those still marked with the set, so a host the owner also allowed
  by name stays).
- **The instructions** are one file, `network.md`, in the words the agent needs: the proxy, the hosts allowed and
  the ask (once, in words), what to use (`curl`, `pip`, Python's `requests` and `httpx`; not Node's own `fetch`), the
  rate limits, and the four literature calls (arXiv, Semantic Scholar, Crossref, OpenAlex) as URLs with their query
  parameters; the console's and VS Code's keys for the sets come with the views (the next plan).

## Tasks

- [x] 1. **The sets** (`workspaces/network.py`): `DEFAULT_SETS`, `sets(home)` (the file read, written with the defaults
  when missing; a malformed file said in a `WorkspaceError`), `Workspaces.allow_set(name, set, allow, *, actor)`
  (each host through `allow_host`, the note marked with the set; taking back removes the set's hosts still so
  marked), `Workspaces.network_sets()`. Tests (`test_network_sets.py`): the file written and read back after the
  owner changes it; a set allowed and taken back; a host also allowed by name stays.
- [x] 2. **The route and the command** (`workspaces/api.py`, `workspaces/cli.py`): `GET /workspaces/network-sets`;
  `POST /workspaces/{name}/sets` (`{"set", "allow"}`); `clank workspace allow FOLDER --set papers` and `--no-set
  papers`; `clank workspace sets` lists the sets with their hosts and what each opens. Tests in `test_network_sets.py`
  and `test_workspace_commands.py`.
- [x] 3. **The instructions** (`image/instructions/network.md`): as the choices say; a test holds the instructions to
  the sets (every literature host the instructions name is in the Papers set) and to the proxy's words (the agent is
  told it may ask once, in words).
- [x] 4. **Docs**: design 0024 §5, §6 (the literature part) and §8 steps 3 and 5 built; getting started (`--set`);
  the roadmap, the plan index, the API page, the code map and the tests page.

## Progress

Written 2026-10-26, after steps 1 and 2 were built and live-tested.

- All four tasks built 2026-10-26. The sets file is written on first use with the five sets; `clank workspace sets`
  lists them; the agent's instructions (`network.md`) reach every container with the next start of its program.
