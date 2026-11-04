// Design 0021 §5: artifacts in VS Code. The service's `agents.artifact_made` names the workspace, its folder on this
// machine, the artifact, its title, kind, version and page, and a window on that folder opens it. A page is shown as
// the agent wrote it, with Clank's content security policy first in its head (nothing from the network: only the
// webview's own files, inline scripts and styles), a <base> at its version's folder (so its relative paths work), its
// `clank-lib/` names pointed at the extension's copy of the libraries, and Clank's bar (versions, Comment, Open in
// browser) in a shadow root of its own at the end of its body, so neither's styles touch the other's.
//
// Revised 2026-11-04 (decision 0156): a version opens in the browser only once the owner answers a question VS Code
// asks, naming the artifact: a message from the page alone (the bar's, or one its own scripts send) opens nothing.
// A panel asks one question at a time, and none for a moment after each answer.

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  artifactBar,
  artifactMade,
  artifactPage,
  BrowserQuestions,
  type BrowserSteps,
  OPEN_IN_BROWSER,
  openInBrowser,
  QUIET_MS,
  versionsSaid,
} from "../src/core/artifacts";

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

/** The steps of opening a version in the browser, each one kept as it happens; the owner answers `answer`. */
function browserSteps(answer: string | undefined): BrowserSteps & { done: string[] } {
  const done: string[] = [];
  return {
    done,
    async confirm(question, detail, button) {
      done.push(`asked: ${question} | ${detail} | ${button}`);
      return answer;
    },
    async exported() {
      done.push("exported");
      return "D:\work\paper\.clank\artifacts\sweep\export\sweep-v2.html";
    },
    async open(file) {
      done.push(`opened ${file}`);
    },
  };
}

test("a 'browser' message alone opens nothing: the owner is asked first, naming the artifact, and only Open opens it", async () => {
  const declined = browserSteps(undefined);
  assert.equal(await openInBrowser("Sweep results", "sweep", 2, declined), undefined);
  assert.equal(declined.done.length, 1, "asked, then nothing exported and nothing opened");
  assert.match(declined.done[0], /^asked: Open the artifact "Sweep results" \(sweep, version 2\) in your browser\?/);
  assert.match(declined.done[0], new RegExp(`\| ${OPEN_IN_BROWSER}$`));
  const other = browserSteps("Cancel");
  assert.equal(await openInBrowser("Sweep results", "sweep", 2, other), undefined, "any other answer opens nothing");
  assert.equal(other.done.length, 1);
  const confirmed = browserSteps(OPEN_IN_BROWSER);
  const file = "D:\work\paper\.clank\artifacts\sweep\export\sweep-v2.html";
  assert.equal(await openInBrowser("Sweep results", "sweep", 2, confirmed), file);
  assert.deepEqual(confirmed.done.slice(1), ["exported", `opened ${file}`], "exported once confirmed, then opened");
});

test("a panel asks one question at a time, and none for a moment after each answer", async () => {
  let now = 1_000;
  const questions = new BrowserQuestions(() => now);
  let answer: (said: string | undefined) => void = () => undefined;
  const asked: string[] = [];
  const slow: BrowserSteps = {
    confirm: (question) => {
      asked.push(question);
      return new Promise((done) => {
        answer = done;
      });
    },
    exported: async () => "x.html",
    open: async () => undefined,
  };
  const first = questions.open("Sweep", "sweep", 1, slow);
  assert.equal(await questions.open("Sweep", "sweep", 1, slow), undefined, "a second message while it is asked");
  answer(undefined);
  assert.equal(await first, undefined);
  assert.equal(asked.length, 1, "asked once");
  now += QUIET_MS - 1;
  assert.equal(await questions.open("Sweep", "sweep", 1, slow), undefined, "just after the answer: not asked");
  assert.equal(asked.length, 1);
  now += 1;
  const later = questions.open("Sweep", "sweep", 1, slow);
  answer(OPEN_IN_BROWSER);
  assert.equal(await later, "x.html", "asked again once the moment has passed");
  assert.equal(asked.length, 2);
});
