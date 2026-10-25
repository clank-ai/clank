# 0135. The artifact libraries: Plotly, KaTeX, marked and Mermaid, pinned, kept in Clank

- Status: Accepted (with design 0021 §5, approved by the owner on 2026-10-25)
- Date: 2026-10-25
- Decided by: the owner (artifacts, nothing leaving the PC), Claude (the libraries and how they are kept)

## Context
- Artifacts (design 0021 §5) are pages the agent makes for the owner: interactive plots of results, explainers with
  math, reports, diagrams. A page that loads its libraries from the network would leak that a page is open and break
  offline, and the owner's research stays on the PC.
- Clank adds no dependency without a decision record. These are front-end files a page loads, not Python packages: they
  are not imported by Clank, only served to its pages and copied into its VS Code extension.

## Decision
- Clank keeps four libraries, each at a pinned version, in `clank/components/artifacts/lib/`: **Plotly** (`plotly.js-dist-min`
  2.35.2, MIT: charts, heatmaps, 3D, sliders), **KaTeX** 0.16.11 (MIT: math, with its auto-render and its fonts),
  **marked** 14.1.3 (MIT: Markdown) and **Mermaid** 11.4.0 (MIT: diagrams). `LIBRARIES.json` lists each file with its
  version, the URL it was fetched from (jsDelivr's copy of the npm package) and its SHA-256; their license texts are
  kept beside them.
- `tools/artifact_libs.py` fetches them again and checks every file against its checksum; a page names a file as
  `clank-lib/<file>`, which Clank points at its copy (in VS Code, the extension's, made from this folder when the
  extension is built).
- The folder is vendored: Clank's spelling check does not read it (its words are its authors'); the secrets check does.

## Alternatives considered
- **Loading them from a CDN in the page**: the network on every open, offline broken, and a page's opening visible to a
  third party.
- **The libraries as npm dependencies of the extension**: the service, which shows artifacts on the phone and exports
  them, would need its own copy; one folder serves both.
- **Fewer libraries** (Chart.js in place of Plotly): smaller, but no 3D, no contour or heatmap sliders, which research
  plots need.
- **Vega-Lite**: declarative and smaller, but models write Plotly more reliably, and Plotly covers more plot types.

## Consequences
- The repository and the extension grow by about 7 MB; the libraries change only by a new decision.
- A page using a library outside this set must carry it in its own folder, or is refused when it names the network.
