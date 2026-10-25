// Design 0021 §5: artifacts in VS Code. The service's `agents.artifact_made` names the workspace, its folder on this
// machine, the artifact, its title, kind, version and page, and a window on that folder opens it. A page is shown as
// the agent wrote it, with Clank's content security policy first in its head (nothing from the network: only the
// webview's own files, inline scripts and styles), a <base> at its version's folder (so its relative paths work), its
// `clank-lib/` names pointed at the extension's copy of the libraries, and Clank's bar (versions, Comment, Open in
// browser) in a shadow root of its own at the end of its body, so neither's styles touch the other's.

import assert from "node:assert/strict";
import { test } from "node:test";

import { artifactBar, artifactMade, artifactPage, versionsSaid } from "../src/core/artifacts";

const MADE = {
  name: "agents.artifact_made",
  id: 50,
  data: {
    id: 50, type: "agents.artifact_made", summary: "paper: the artifact Sweep results (sweep), version 2",
    data: { workspace: "paper", folder: "D:\\work\\paper", name: "sweep", title: "Sweep results", kind: "html",
            version: 2, entry: ".clank/artifacts/sweep/v2/report/index.html" },
  },
};

test("an artifact made is read from its event, and nothing else is", () => {
  assert.deepEqual(artifactMade(MADE), {
    workspace: "paper", folder: "D:\\work\\paper", name: "sweep", title: "Sweep results", kind: "html", version: 2,
    entry: ".clank/artifacts/sweep/v2/report/index.html",
  });
  assert.equal(artifactMade({ name: "agents.shown", id: 1, data: {} }), undefined);
});

test("a page gets the policy, its base, the libraries' place and the bar, and keeps the agent's own", () => {
  const page = `<!doctype html><html><head><title>Sweep</title><script src="clank-lib/plotly.min.js"></script>
<link rel="stylesheet" href='clank-lib/katex.min.css'></head><body><div id="plot"></div></body></html>`;
  const shown = artifactPage(page, {
    base: "https://file+.vscode-resource.vscode-cdn.net/d%3A/work/paper/.clank/artifacts/sweep/v2/report/",
    lib: "https://file+.vscode-resource.vscode-cdn.net/x/media/lib",
    source: "https://*.vscode-cdn.net",
    nonce: "abc",
    bar: "<div>bar</div>",
  });
  const head = shown.slice(shown.indexOf("<head>"), shown.indexOf("<title>"));
  assert.match(head, /http-equiv="Content-Security-Policy"/, "the policy comes first in the head");
  assert.match(head, /default-src 'none'/);
  assert.match(head, /connect-src https:\/\/\*\.vscode-cdn\.net;/, "data files of its own, and nothing else");
  assert.match(head, /<base href="https:\/\/file\+\.vscode-resource\.vscode-cdn\.net\/d%3A\/work\/paper\/\.clank\/artifacts\/sweep\/v2\/report\/">/);
  assert.match(shown, /src="https:\/\/file\+\.vscode-resource\.vscode-cdn\.net\/x\/media\/lib\/plotly\.min\.js"/);
  assert.match(shown, /href='https:\/\/file\+\.vscode-resource\.vscode-cdn\.net\/x\/media\/lib\/katex\.min\.css'/);
  assert.ok(shown.includes('<div id="plot"></div>'), "the agent's page as it wrote it");
  assert.ok(shown.indexOf("<div>bar</div>") > shown.indexOf('<div id="plot">'), "the bar after its content");
  assert.ok(shown.trimEnd().endsWith("</body></html>"));
});

test("a page without a head or a body still gets them", () => {
  const shown = artifactPage("<p>just text</p>", { base: "b/", lib: "l", source: "s", nonce: "n", bar: "<i>bar</i>" });
  assert.match(shown, /^<!doctype html><html><head><meta http-equiv="Content-Security-Policy"/);
  assert.ok(shown.includes("<p>just text</p>"));
  assert.ok(shown.includes("<i>bar</i>"));
});

test("the versions are said newest first, the one shown marked", () => {
  assert.deepEqual(versionsSaid(3, 2), [
    { version: 3, label: "version 3 (newest)", shown: false },
    { version: 2, label: "version 2", shown: true },
    { version: 1, label: "version 1", shown: false },
  ]);
});

test("the bar names the artifact, lists its versions and asks for a comment or a browser, its words escaped", () => {
  const shown = artifactBar("Sweep <results>", versionsSaid(2, 1), "n0nce");
  assert.ok(shown.includes('nonce="n0nce"'));
  assert.ok(shown.includes("Sweep &lt;results&gt;"), "the title is the page's text, not its markup");
  assert.ok(shown.includes('<option value="2">version 2 (newest)</option>'));
  assert.ok(shown.includes('<option value="1" selected>version 1</option>'));
  assert.ok(shown.includes('data-act="comment"') && shown.includes('data-act="browser"'));
  assert.ok(shown.includes("attachShadow"), "in a shadow root: its styles and the page's never meet");
});
