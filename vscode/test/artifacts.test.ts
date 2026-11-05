// Design 0021 §5: artifacts in VS Code. The service's `agents.artifact_made` names the workspace, its folder on this
// machine, the artifact, its title, kind, version and page, and a window on that folder opens it. The panel's document
// is Clank's alone (decision 0165): its content policy first (the one the page carries, read here from the service's
// code, since the frame takes the panel's policy as well), Clank's bar (the title, the versions, Comment, Open in
// browser), the one call to VS Code's API, and the page the service built, whole, as the `srcdoc` of an
// `<iframe sandbox="allow-scripts">`; a page whose markup looks like Clank's stays inside the frame, and the panel
// listens to no message.
//
// Revised 2026-11-04 (decision 0156): a version opens in the browser only once the owner answers a question VS Code
// asks, naming the artifact: a message from the page alone (the bar's, or one its own scripts send) opens nothing.
// A panel asks one question at a time, and none for a moment after each answer.
//
// Revised 2026-11-04 (decision 0165): the page left the panel's document for the sandboxed frame; before, it shared
// the document with the bar, its paths and libraries pointed at the webview's files.

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import * as path from "node:path";
import { test } from "node:test";

import {
  artifactBar,
  artifactMade,
  artifactPanel,
  BrowserQuestions,
  type BrowserSteps,
  FRAME_SANDBOX,
  OPEN_IN_BROWSER,
  openInBrowser,
  PANEL_POLICY,
  QUIET_MS,
  versionsSaid,
} from "../src/core/artifacts";

const ROOT = path.join(__dirname, "..", "..", "..");

/** The content policy a version's page carries, as the service's code writes it (`EXPORT_POLICY`). */
function exportPolicy(): string {
  const code = readFileSync(path.join(ROOT, "clank", "components", "agents", "artifacts.py"), "utf-8");
  const written = /^EXPORT_POLICY = \(\n([\s\S]*?)\n\)/m.exec(code);
  assert.ok(written, "agents/artifacts.py writes EXPORT_POLICY");
  return [...written[1].matchAll(/"([^"]*)"/g)].map((each) => each[1]).join("");
}

/** The panel's frame and what lies outside it: the frame's attributes, its page as the frame reads it (the attribute's
 * value unescaped), and the rest of the panel's document. */
function framed(panel: string): { frame: string; page: string; outside: string } {
  const found = /<iframe\b([^>]*?)\ssrcdoc="([^"]*)"([^>]*)><\/iframe>/.exec(panel);
  assert.ok(found, "the panel holds a frame with its page as srcdoc");
  return {
    frame: `${found[1]} ${found[3]}`,
    page: found[2].replace(/&quot;/g, '"').replace(/&amp;/g, "&"),
    outside: panel.slice(0, found.index) + panel.slice(found.index + found[0].length),
  };
}

function count(text: string, part: string): number {
  return text.split(part).length - 1;
}

const PAGE = `<!doctype html><meta http-equiv="Content-Security-Policy" content="${PANEL_POLICY}"><html><head>
<title>Sweep</title><script>window.fetch = () => "answered inside";</script></head>
<body><div id="plot" data-note='a "quoted" note &amp; more'></div><script>Plotly.newPlot("plot", []);</script></body></html>`;

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

test("the panel's document is Clank's: its policy, its bar, the one call to VS Code's API, and the page in a frame sandboxed to scripts alone", () => {
  const panel = artifactPanel(PAGE, "Sweep results", versionsSaid(2, 2));
  const { frame, page, outside } = framed(panel);
  assert.equal(FRAME_SANDBOX, "allow-scripts");
  assert.match(frame, /\bsandbox="allow-scripts"/, "scripts, and no other flag: no same origin, forms, popups, top navigation or modals");
  assert.equal(count(frame, "sandbox="), 1, "one sandbox, nothing to widen it");
  assert.ok(!/\ballow=/.test(frame), "no feature allowed to it");
  assert.equal(page, PAGE, "the page whole, as the service built it, inside the frame");
  assert.equal(count(panel, "<iframe"), 1, "one frame");
  assert.ok(!outside.includes("Plotly"), "nothing of the page outside its frame");
  assert.match(outside, /^<!doctype html><html lang="en"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="([^"]+)">/);
  assert.equal(/content="([^"]+)"/.exec(outside)?.[1], PANEL_POLICY, "the panel's policy first in its head");
  assert.equal(count(outside, "acquireVsCodeApi()"), 1, "the one call to VS Code's API, in Clank's own script");
  assert.ok(outside.includes('data-act="comment"') && outside.includes('data-act="browser"'), "the bar, outside the frame");
  assert.ok(panel.indexOf('id="clank-artifact-bar"') < panel.indexOf("<iframe"), "the bar first, for the keyboard");
  assert.ok(!/addEventListener\(\s*["']message|onmessage/.test(outside), "the panel listens to no message from the frame");
  assert.match(frame, /\btitle="Sweep results"/, "the frame named for a screen reader");
});

test("a page whose markup looks like Clank's stays inside the frame, whole", () => {
  const hostile = `<p title="x">"quoted" &amp; &quot;escaped&quot;</p></iframe><div id="clank-artifact-bar"></div>` +
    '<script>acquireVsCodeApi().postMessage({ type: "browser" }); addEventListener("message", () => {});</script>';
  const panel = artifactPanel(hostile, 'A "title" & <b>more</b>', versionsSaid(1, 1));
  const { page, outside } = framed(panel);
  assert.equal(page, hostile, "the frame reads exactly the page, its quotes and ampersands included");
  assert.equal(count(panel, "<iframe"), 1);
  assert.ok(!outside.includes("</iframe>"), "its </iframe> is text of the frame's page, closing nothing of the panel");
  assert.equal(count(outside, "acquireVsCodeApi()"), 1, "its call to VS Code's API is the frame's, which has none");
  assert.equal(count(outside, 'id="clank-artifact-bar"'), 1);
  assert.ok(!/addEventListener\(\s*["']message/.test(outside));
  assert.ok(outside.includes("A &quot;title&quot; &amp; &lt;b&gt;more&lt;/b&gt;"), "the title is text, not markup");
});

test("the panel holds itself to the page's own content policy, which the frame takes as well", () => {
  assert.equal(PANEL_POLICY, exportPolicy(), "the policy the service writes first in every page");
  const directives = new Map(PANEL_POLICY.split(";").map((each) => each.trim().split(/\s+/)).map(([name, ...rest]) => [name, rest]));
  assert.deepEqual(directives.get("default-src"), ["'none'"]);
  assert.ok(directives.get("script-src")?.includes("'unsafe-inline'"), "the page's inline scripts run: a nonce would stop them");
  assert.ok(![...directives.values()].flat().some((each) => /^https?:|\*|'self'/.test(each)), "no address of any kind");
  assert.ok(!directives.has("frame-src"), "a srcdoc frame needs none");
});

test("the versions are said newest first, the one shown marked", () => {
  assert.deepEqual(versionsSaid(3, 2), [
    { version: 3, label: "version 3 (newest)", shown: false },
    { version: 2, label: "version 2", shown: true },
    { version: 1, label: "version 1", shown: false },
  ]);
});

test("the bar names the artifact, lists its versions and asks for a comment or a browser, its words escaped", () => {
  const shown = artifactBar("Sweep <results>", versionsSaid(2, 1));
  assert.ok(shown.includes("Sweep &lt;results&gt;"), "the title is the page's text, not its markup");
  assert.ok(shown.includes('<option value="2">version 2 (newest)</option>'));
  assert.ok(shown.includes('<option value="1" selected>version 1</option>'));
  assert.ok(shown.includes('data-act="comment"') && shown.includes('data-act="browser"'));
  assert.ok(!shown.includes("<script"), "its script is the panel's");
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
