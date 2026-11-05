// Design 0021 §5, in a real browser (decision 0165): an artifact's panel as `artifactPanel` writes it, in headless Edge
// with a stand-in for VS Code's API, holding a page of several megabytes built as the service builds one (Plotly
// inlined, the export's content policy first, its own script and style sheet as data). In its sandboxed frame the page
// draws its plot and runs its own script and style; it has an origin of its own, so it reaches neither the panel's
// document nor VS Code's API; it reaches nothing on the network, opens no window and moves no window. What it posts
// reaches nothing: only the bar's clicks and its version reach VS Code. A screenshot is left in out/test/.

import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { test } from "node:test";
import { pathToFileURL } from "node:url";

import { artifactPanel, PANEL_POLICY, versionsSaid } from "../src/core/artifacts";
import { Browser, EDGE, MEDIA, removeFolder } from "./browser";

const PLOTLY = path.join(MEDIA, "..", "..", "clank", "components", "agents", "artifact_lib", "plotly.min.js");

/** The panel as VS Code's webview holds it: its API defined before anything else (VS Code prepends its own script the
 * same way), acquired once at most, keeping what is posted in `window.posted`; and, for the test alone, every message
 * the panel's window receives kept in `window.heard`. */
function inVsCode(panel: string): string {
  const api =
    "<script>window.posted = []; window.heard = []; let acquired = false;" +
    "window.acquireVsCodeApi = () => { if (acquired) throw new Error('already acquired'); acquired = true;" +
    " return { postMessage: (message) => window.posted.push(message), getState: () => undefined, setState: () => {} }; };" +
    "window.addEventListener('message', (event) => window.heard.push(event.data));</script>";
  return panel.replace("<head>", `<head>${api}`);
}

/** A page as the service builds one, which tries every way out of its frame and says what it found. */
function page(network: string): string {
  const plotly = readFileSync(PLOTLY, "utf-8").replace(/<\/script/gi, "<\\/script");
  const own = Buffer.from("document.documentElement.dataset.own = 'ran';").toString("base64");
  const style = Buffer.from("#plot { width: 600px; height: 400px; }").toString("base64");
  const tries = `<script>
(async () => {
  await new Promise((done) => addEventListener("load", done));
  const said = {};
  try { said.panel = String(parent.document.title); } catch (error) { said.panel = error.name; }
  try { said.api = typeof parent.acquireVsCodeApi; } catch (error) { said.api = error.name; }
  said.own_api = typeof window.acquireVsCodeApi;
  said.origin = self.origin;
  document.addEventListener("securitypolicyviolation", (event) => { said.refused = event.effectiveDirective; });
  try { await fetch(${JSON.stringify(network)}); said.network = "reached"; } catch (error) { said.network = error.name; }
  for (let tries = 0; tries < 100 && !said.refused; tries++) await new Promise((done) => setTimeout(done, 20));
  said.window = String(window.open("about:blank"));
  try { top.location.href = "about:blank#moved"; said.top = "moved"; } catch (error) { said.top = error.name; }
  await Plotly.newPlot("plot", [{ x: [1, 2, 3], y: [3, 1, 2] }]);
  said.traces = document.querySelectorAll(".scatterlayer .trace").length;
  said.own = document.documentElement.dataset.own;
  said.width = getComputedStyle(document.getElementById("plot")).width;
  parent.postMessage({ type: "browser" }, "*");
  parent.postMessage({ type: "said", said }, "*");
})();
</script>`;
  return `<!doctype html><meta http-equiv="Content-Security-Policy" content="${PANEL_POLICY}"><html><head>` +
    `<title>Sweep</title><link rel="stylesheet" href="data:text/css;base64,${style}"><script>${plotly}</script>` +
    `<script defer src="data:text/javascript;base64,${own}"></script></head>` +
    `<body><div id="plot"></div>${tries}</body></html>`;
}

async function center(browser: Browser, selector: string): Promise<{ x: number; y: number }> {
  return browser.evaluate<{ x: number; y: number }>(
    `(() => { const r = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`,
  );
}

test("the page runs in its sandboxed frame, reaches nothing outside it, and only the bar reaches VS Code", { skip: EDGE ? false : "no Edge here" }, async () => {
  const folder = mkdtempSync(path.join(tmpdir(), "clank-artifact-"));
  let reached = 0;
  const server = createServer((_request, answer) => {
    reached += 1;
    answer.writeHead(200, { "Access-Control-Allow-Origin": "*" }).end("the network");
  });
  await new Promise<void>((done) => server.listen(0, "127.0.0.1", done));
  const address = server.address();
  const network = `http://127.0.0.1:${typeof address === "object" && address ? address.port : 0}/secret`;
  const shown = page(network);
  assert.ok(shown.length > 4_000_000, "a page of several megabytes, as Plotly makes it");
  const file = path.join(folder, "panel.html");
  writeFileSync(file, inVsCode(artifactPanel(shown, "Sweep results", versionsSaid(2, 2))), "utf-8");
  const browser = await Browser.open(pathToFileURL(file).toString(), path.join(folder, "profile"));
  try {
    await browser.until("window.heard?.some((each) => each?.type === 'said')");
    const said = await browser.evaluate<Record<string, unknown>>("window.heard.find((each) => each.type === 'said').said");
    assert.equal(said.traces, 1, "Plotly drew the plot, inlined in a page of megabytes");
    assert.equal(said.own, "ran", "its own script, as data");
    assert.equal(said.width, "600px", "its own style sheet, as data");
    assert.equal(said.origin, "null", "an origin of its own");
    assert.equal(said.panel, "SecurityError", "the panel's document out of its reach");
    assert.equal(said.api, "SecurityError", "VS Code's API out of its reach");
    assert.equal(said.own_api, "undefined", "and none of its own");
    assert.equal(said.network, "TypeError", "the network refused");
    assert.equal(said.refused, "connect-src", "by the content policy");
    assert.equal(reached, 0, "nothing reached the address");
    assert.equal(said.window, "null", "no window opened");
    assert.equal(said.top, "SecurityError", "the window not moved");
    assert.equal(await browser.evaluate("location.hash"), "");
    assert.deepEqual(await browser.evaluate("window.posted"), [], "its 'browser' message reached nothing");

    const browse = await center(browser, '#clank-artifact-bar [data-act="browser"]');
    assert.equal(await browser.evaluate(`document.elementFromPoint(${browse.x}, ${browse.y}).dataset.act`), "browser", "the bar over the frame");
    await browser.click(browse.x, browse.y);
    const comment = await center(browser, '#clank-artifact-bar [data-act="comment"]');
    await browser.click(comment.x, comment.y);
    await browser.evaluate("(() => { const versions = document.querySelector('#clank-artifact-bar select'); versions.value = '1'; versions.dispatchEvent(new Event('change')); })()");
    assert.deepEqual(await browser.evaluate("window.posted"), [{ type: "browser" }, { type: "comment" }, { type: "version", version: 1 }]);
    const screenshot = (await browser.send("Page.captureScreenshot", { format: "png" })) as { data: string };
    writeFileSync(path.join(__dirname, "artifact.png"), Buffer.from(screenshot.data, "base64"));
  } finally {
    await browser.close();
    server.close();
    removeFolder(folder);
  }
});
