# Plan s47: artifacts

Builds [design 0021](../design/0021-all-llm-work-in-clank.md) §5, approved by the owner on 2026-10-25: pages the agent
makes for the owner, as Claude makes artifacts (an interactive plot of results, a parameter explorer, an explainer, a
report, a diagram), kept as versions in the folder, shown in VS Code, the owner's comments sent back to the agent, and
nothing leaving the PC. Each task starts with a failing test; each ends with a commit pushed to `main`.

## How it works

- **An artifact is files in the folder.** `.clank/artifacts/<name>/artifact.json` (its title, kind, versions and what
  made each) and one folder per version, `v1/`, `v2/`, each a copy of the files the agent named when it made it, its
  entry page first. A Markdown artifact gets an `index.html` of Clank's beside it that renders it, math included.
- **Libraries, offline.** A page may use the libraries Clank keeps (Plotly for charts, KaTeX for math, marked for
  Markdown, Mermaid for diagrams), named `clank-lib/<file>` in its page; nothing else outside its own version folder.
  They are files of Clank's (`clank/components/artifacts/lib/`), pinned with their checksums and licenses, copied into
  the VS Code extension when it is built (decision 0135, a new dependency).
- **Shown in VS Code** in the files' group, a webview of its own per artifact: its entry page, with a `<base>` at its
  version folder, `clank-lib/` pointed at the extension's copy, and a content security policy that allows nothing from
  the network; a bar above it with its title, its versions (the newest shown), Comment and Open in browser.
- **Comments back.** A comment names the artifact and its version, and goes to the session that made it as one message.

## Tasks

- [x] 1. **The libraries** (decision 0135): Plotly, KaTeX (with its fonts and auto-render), marked and Mermaid, at pinned
  versions, in `clank/components/artifacts/lib/` with `LIBRARIES.json` (each file's version, source URL, SHA-256 and
  license) and their license texts; `tools/artifact_libs.py` fetches them again and checks them; `tools.vsix` copies them
  into the extension. Tests: every file listed is there with its checksum; the extension's copy is made at build.
- [ ] 2. **The artifacts in the service** (a component, `artifacts`): make (a name, a title, a kind, the files, a note;
  the next version, the files copied, refused when a file is not the folder's, too large, or the entry page names
  anything outside its folder but `clank-lib/`), list, one (its versions), a comment (to the session that made the
  version), and `artifacts.made` and `artifacts.commented`. Routes: `POST /artifacts` (the agent's, through the gateway),
  `GET /artifacts?workspace=`, `GET /artifacts/{workspace}/{name}`, `POST /artifacts/{workspace}/{name}/comment`.
- [ ] 3. **The agent's tool**: `make_artifact(name, title, kind, files, note)` in Clank's MCP server, and its
  instructions (`artifacts.md`): when to make one, the libraries, data files beside the page, no network.
- [ ] 4. **In VS Code**: an artifact made in the window's folder opens in the files' group; `Clank: Open an artifact`
  lists the folder's; its bar's versions, Comment (sent) and Open in browser (an exported copy).
- [ ] 5. **Export**: `clank artifact list` and `clank artifact export NAME [--version N]`: one self-contained HTML file,
  its libraries and data inlined.
- [ ] 6. **Live**: the real model makes an artifact from a small dataset in a throwaway folder; it opens in VS Code,
  is seen working (a screenshot of that window only), is commented on, and a second version comes back.

## Progress

Written 2026-10-25.
