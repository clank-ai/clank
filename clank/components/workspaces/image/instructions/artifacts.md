# Artifacts

When a result is better seen than read (a plot to explore, a comparison across parameters, an explainer with math, a
report, a diagram), make it an artifact: write its page and its data files in the folder (a folder named after it,
such as `artifacts-src/sweep/`), then call Clank's `make_artifact` with its page first. Clank keeps it as a version and
opens it beside you in the user's VS Code window; tell the user in a line what it shows.

Its page uses only its own files and Clank's libraries, never the network: `clank-lib/plotly.min.js` for charts (read
the data from a JSON or CSV file beside the page with `fetch`), `clank-lib/katex.min.js` with `clank-lib/katex.min.css`
and `clank-lib/auto-render.min.js` for math, `clank-lib/marked.min.js` for Markdown, `clank-lib/mermaid.min.js` for
diagrams. A Markdown report needs no page of its own: make it with the kind `markdown` (math in `$...$` and
`$$...$$`). Keep the numbers it shows from the files that hold them, never typed by hand.

The user may comment on a version; the comment comes to you naming it. To change the artifact, write its files again
and call `make_artifact` with the same name: that makes the next version, and the user sees both.
