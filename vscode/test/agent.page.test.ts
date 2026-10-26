// Design 0021 §4, in a real browser: the agent panel's page (media/agent.html, as VS Code's webview shows it, with
// marked and KaTeX from Clank's libraries) in headless Edge. A conversation sent to it is drawn: the owner's message,
// the model's Markdown with its math drawn by KaTeX (underscores kept), raw HTML in it shown as text, the thinking and
// each call folded, an image, an artifact card whose Open says which version, and what waits with its buttons. A fold
// the owner opened stays open when the conversation is drawn again. Enter sends the message, Shift+Enter does not; @
// asks for the folder's files and the one chosen is put as the agent sees it. A screenshot is left in out/test/.

import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { test } from "node:test";

import { conversationItems, type PageMessage, splitMath, waitingItems } from "../src/core/conversation";
import { Browser, EDGE, removeFolder, webviewPage } from "./browser";

const LIB = "../../clank/components/agents/artifact_lib";
const click = (selector: string): string => `document.querySelector(${JSON.stringify(selector)}).click()`;
const lastPost = "JSON.stringify(window.posted[window.posted.length - 1])";

const PAGE: PageMessage[] = [
  { info: { id: "msg_1", role: "user" }, parts: [{ id: "prt_1", type: "text", text: "Plot the sweep, please." }] },
  {
    info: { id: "msg_2", role: "assistant" },
    parts: [
      { id: "prt_2", type: "reasoning", text: "The data is in data/sweep.csv." },
      {
        id: "prt_3", type: "tool", tool: "bash", status: "completed", title: "",
        input: { command: "python3 simulate.py" }, output: "done",
      },
      {
        id: "prt_4", type: "tool", tool: "clank_make_artifact", status: "completed", title: "",
        input: { name: "sweep", title: "Sweep results" }, output: "Artifact Sweep results (sweep), version 2, made.",
      },
      {
        id: "prt_5", type: "text",
        text: "## Result\n\nThe period is $T_0 = 2\\pi\\sqrt{L/g}$ for $x_1$ and <b>bold</b> stays text.\n\n| a | b |\n|---|---|\n| 1 | 2 |",
      },
    ],
  },
];

function drawn(): unknown[] {
  const waiting = {
    permissions: [{ id: "per_1", session: "ses_1", permission: "bash", patterns: ["rm -r out"], metadata: {} }],
    questions: [],
  };
  const image = { kind: "image" as const, id: "img_1", path: "figures/sweep.png", src: "data:image/png;base64,iVBORw0KGgo=" };
  return [...conversationItems(PAGE), image, ...waitingItems(waiting)].map((item) =>
    item.kind === "text" ? { ...item, split: splitMath(item.text) } : item,
  );
}

async function shot(browser: Browser, name: string): Promise<void> {
  const screenshot = (await browser.send("Page.captureScreenshot", { format: "png" })) as { data: string };
  writeFileSync(path.join(__dirname, name), Buffer.from(screenshot.data, "base64"));
}

test("the agent panel draws the conversation, keeps the folds opened, and sends what the owner does", { skip: EDGE ? false : "no Edge here" }, async () => {
  const folder = mkdtempSync(path.join(tmpdir(), "clank-agent-"));
  const files = {
    css: "agent.css", script: "agent.js", marked: `${LIB}/marked.min.js`, katex: `${LIB}/katex.min.js`,
    katexCss: `${LIB}/katex.min.css`,
  };  // prettier-ignore
  const browser = await Browser.open(webviewPage(folder, "agent.html", files), path.join(folder, "profile"));
  const conversation = { type: "conversation", title: "Plot the sweep", state: "writing", busy: true, older: true,
                         items: drawn() };  // prettier-ignore
  try {
    await browser.until("document.readyState === 'complete' && Array.isArray(window.posted) && window.posted.length > 0");
    assert.deepEqual(await browser.evaluate("window.posted[0]"), { type: "ready" });
    await browser.evaluate(`window.postMessage(${JSON.stringify(conversation)}, "*")`);
    await browser.until("document.querySelectorAll('#items .item').length === 8");
    assert.deepEqual(await browser.evaluate("[...document.querySelectorAll('#items .item')].map((each) => each.className)"), [
      "item owner", "item thinking", "item call completed", "item call completed", "item card", "item text",
      "item image", "item wait",
    ]);
    assert.equal(await browser.evaluate("document.getElementById('title').textContent"), "Plot the sweep");
    assert.equal(await browser.evaluate("document.getElementById('state').className"), "state busy");
    assert.equal(await browser.evaluate("document.getElementById('older').hidden"), false);
    const text = "document.querySelector('#items .text')";
    assert.equal(await browser.evaluate(`${text}.querySelectorAll('.katex').length`), 2, "the math drawn by KaTeX");
    assert.equal(await browser.evaluate(`${text}.querySelector('h2').textContent`), "Result");
    assert.equal(await browser.evaluate(`${text}.querySelectorAll('td').length`), 2, "a table");
    assert.equal(await browser.evaluate(`${text}.querySelector('b')`), null, "raw HTML is shown as text");
    assert.match(await browser.evaluate<string>(`${text}.textContent`), /<b>bold<\/b> stays text/);
    assert.equal(await browser.evaluate("document.querySelector('.thinking').open"), false, "the thinking folded");
    assert.match(await browser.evaluate<string>("document.querySelectorAll('.call summary')[0].textContent"), /✓ bash: python3 simulate\.py/);

    await browser.evaluate(click(".call summary"));
    await browser.evaluate(`window.postMessage(${JSON.stringify(conversation)}, "*")`);
    await browser.until("document.querySelectorAll('#items .item').length === 8");
    assert.equal(await browser.evaluate("document.querySelector('.call').open"), true, "a fold opened stays open");

    await browser.evaluate(click(".card button"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "artifact", name: "sweep", title: "Sweep results", version: 2 });
    await browser.evaluate(click(".wait button"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "permission", id: "per_1", reply: "once" });
    await browser.evaluate(click("header button[data-act='stop']"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "act", act: "stop" });

    const type = (key: string, shift = false): string =>
      `document.getElementById('input').dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(key)}, shiftKey: ${shift}, bubbles: true }))`;
    await browser.evaluate("document.getElementById('input').value = 'Use a log scale.'");
    await browser.evaluate(type("Enter", true));
    assert.notEqual(JSON.parse(await browser.evaluate<string>(lastPost)).type, "send", "Shift+Enter is a new line");
    await browser.evaluate(type("Enter"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "send", text: "Use a log scale." });
    await browser.evaluate(`window.postMessage({ type: "sent" }, "*")`);
    await browser.until("document.getElementById('input').value === ''");

    await browser.evaluate("const box = document.getElementById('input'); box.value = 'Read @sim'; box.selectionStart = box.selectionEnd = 9; box.dispatchEvent(new Event('input'))");
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "files", query: "sim" });
    await browser.evaluate(`window.postMessage({ type: "files", files: ["simulate.py", "data/sim.csv"] }, "*")`);
    await browser.until("!document.getElementById('files').hidden");
    await browser.evaluate(type("ArrowDown"));
    await browser.evaluate(type("Enter"));
    assert.equal(await browser.evaluate("document.getElementById('input').value"), "Read /workspace/data/sim.csv ");
    assert.equal(await browser.evaluate("document.getElementById('files').hidden"), true);
    await shot(browser, "agent-panel.png");
  } finally {
    await browser.close();
    removeFolder(folder);
  }
});
