// Design 0021 §4, in a real browser: the agent panel's page (media/agent.html, as VS Code's webview shows it, with
// marked and KaTeX from Clank's libraries) in headless Edge, drawn as the owner chose it (direction A, 2026-10-26). A
// conversation sent to it is drawn: the owner's message (and a relayed comment's "on" line), Clank's notice that a job
// ended with its log to open, the thinking folded, three calls or more folded under "N steps · T s" with each call's
// verb and what it was done to, the model's Markdown with its math drawn by KaTeX (raw HTML in it shown as text), an
// artifact card whose Open says which version, and what waits with its buttons. A fold the owner opened stays open when
// the conversation is drawn again. While the agent works the send button stops it. Enter sends the message, Shift+Enter
// does not; @ asks for the folder's files and the one chosen is put as the agent sees it. The colors follow the VS Code
// theme's variables (a light one shows its owner bubble apart from its ground), or Clank Night when the extension says
// so. Screenshots are left in out/test/.

import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { test } from "node:test";

import { type Block, blocks, conversationItems, type PageMessage, splitMath, waitingItems } from "../src/core/conversation";
import { Browser, EDGE, removeFolder, webviewPage } from "./browser";

const LIB = "../../clank/components/agents/artifact_lib";
const click = (selector: string): string => `document.querySelector(${JSON.stringify(selector)}).click()`;
const lastPost = "JSON.stringify(window.posted[window.posted.length - 1])";
const JOB = "Job 1 (Pendulum simulation) exited 0 after 2 minutes. The last lines of its log, .clank/jobs/agent/1/log:\n```\ndone\n```\nFiles written in the folder while it ran, newest first: data/simulated.csv.\nGo on from here.";

function call(id: string, tool: string, input: unknown, start: number, end: number): PageMessage["parts"][number] {
  return { id, type: "tool", tool, status: "completed", title: "", input, output: "done", time: { start, end } };
}

const PAGE: PageMessage[] = [
  { info: { id: "msg_1", role: "user" }, parts: [{ id: "prt_1", type: "text", text: "Run the simulation as a job." }] },
  { info: { id: "msg_2", role: "user" }, parts: [{ id: "prt_2", type: "text", text: JOB }] },
  {
    info: { id: "msg_3", role: "assistant" },
    parts: [
      { id: "prt_3", type: "reasoning", text: "The results are in data/simulated.csv." },
      call("prt_4", "read", { filePath: "/workspace/data/simulated.csv" }, 1000, 1200),
      call("prt_5", "edit", { filePath: "/workspace/pendulum.html" }, 1200, 2000),
      call("prt_6", "clank_make_artifact", { name: "pendulum", title: "Pendulum period" }, 2000, 13000),
      {
        id: "prt_7", type: "text",
        text: "## Result\n\nThe period is $T_0 = 2\\pi\\sqrt{L/g}$ for $x_1$ and <b>bold</b> stays text.\n\n| a | b |\n|---|---|\n| 1 | 2 |",
      },
    ],
  },
];
PAGE[2].parts[3].output = "Artifact Pendulum period (pendulum), version 3, made.";

function drawn(): unknown[] {
  const waiting = {
    permissions: [{ id: "per_1", session: "ses_1", permission: "bash", patterns: ["rm -r out"], metadata: {} }],
    questions: [],
  };
  const ready = (block: Block): unknown =>
    block.kind === "text" ? { ...block, split: splitMath(block.text) }
    : block.kind === "steps" ? { ...block, steps: block.steps.map(ready) }
    : block;  // prettier-ignore
  return blocks([...conversationItems(PAGE), ...waitingItems(waiting)]).map(ready);
}

async function shot(browser: Browser, name: string): Promise<void> {
  const screenshot = (await browser.send("Page.captureScreenshot", { format: "png" })) as { data: string };
  writeFileSync(path.join(__dirname, name), Buffer.from(screenshot.data, "base64"));
}

const LIGHT = {
  "--vscode-editor-background": "#ffffff", "--vscode-foreground": "#3b3b3b", "--vscode-editor-foreground": "#1f1f1f",
  "--vscode-descriptionForeground": "#616161", "--vscode-button-background": "#005fb8", "--vscode-button-foreground": "#ffffff",
  "--vscode-input-background": "#ffffff", "--vscode-textLink-foreground": "#005fb8",
};  // prettier-ignore

test("the agent panel draws the conversation as the owner chose it, in each theme, and sends what the owner does", { skip: EDGE ? false : "no Edge here" }, async () => {
  const folder = mkdtempSync(path.join(tmpdir(), "clank-agent-"));
  const files = {
    css: "agent.css", script: "agent.js", marked: `${LIB}/marked.min.js`, katex: `${LIB}/katex.min.js`,
    katexCss: `${LIB}/katex.min.css`,
  };  // prettier-ignore
  const browser = await Browser.open(webviewPage(folder, "agent.html", files), path.join(folder, "profile"));
  const conversation = {
    type: "conversation", title: "Pendulum period vs amplitude", subtitle: "Waits for you · frontier 262K · paper",
    state: "waiting", model: "frontier 262K", older: true, empty: "",
    foot: { speed: "34 tok/s", used: "22K", window: "262K", share: 0.084, drafts: "drafts 57 %", gpu: "GPU 15.7 / 15.9 GB", model: "frontier 262K", phase: "Thinking" },
    blocks: drawn(),
  };  // prettier-ignore
  const post = (message: unknown): Promise<unknown> => browser.evaluate(`window.postMessage(${JSON.stringify(message)}, "*")`);
  try {
    await browser.until("document.readyState === 'complete' && Array.isArray(window.posted) && window.posted.length > 0");
    assert.deepEqual(await browser.evaluate("window.posted[0]"), { type: "ready" });
    await post(conversation);
    await browser.until("document.querySelectorAll('#items > .item').length === 6");
    assert.deepEqual(await browser.evaluate("[...document.querySelectorAll('#items > .item')].map((each) => each.className)"), [
      "item owner", "item notice", "item steps", "item card", "item prose", "item ask",
    ]);
    assert.equal(await browser.evaluate("document.getElementById('title').textContent"), "Pendulum period vs amplitude");
    assert.equal(await browser.evaluate("document.getElementById('dot').className"), "dot waiting");
    assert.match(await browser.evaluate<string>("document.querySelector('.notice').textContent"), /Job 1 ended · Pendulum simulation · exited 0 after 2 minutes · wrote data\/simulated\.csv/);
    assert.equal(await browser.evaluate("document.querySelector('.steps > summary').textContent"), "3 steps · 12 s");
    assert.equal(await browser.evaluate("document.querySelector('.steps').open"), false, "steps that ended are folded");
    assert.deepEqual(
      await browser.evaluate("[...document.querySelectorAll('.steps .call summary')].map((each) => each.querySelector('.verb').textContent + ' ' + (each.querySelector('.detail')?.textContent ?? ''))"),
      ["Read data/simulated.csv", "Edited pendulum.html", "Made an artifact pendulum"],
    );
    const prose = "document.querySelector('#items .prose')";
    assert.equal(await browser.evaluate(`${prose}.querySelectorAll('.katex').length`), 2, "the math drawn by KaTeX");
    assert.equal(await browser.evaluate(`${prose}.querySelector('b')`), null, "raw HTML is shown as text");
    assert.match(await browser.evaluate<string>(`${prose}.textContent`), /<b>bold<\/b> stays text/);
    assert.equal(await browser.evaluate("document.getElementById('used').textContent"), "22K / 262K");
    await shot(browser, "agent-panel-dark.png");

    await browser.evaluate(click(".steps > summary"));
    await post({ ...conversation, title: "Again" });
    await browser.until("document.getElementById('title').textContent === 'Again'");
    assert.equal(await browser.evaluate("document.querySelector('.steps').open"), true, "a fold opened stays open");

    await browser.evaluate(click(".notice .link"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "open", path: ".clank/jobs/agent/1/log" });
    await browser.evaluate(click(".card .primary"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "artifact", name: "pendulum", title: "Pendulum period", version: 3 });
    await browser.evaluate(click(".ask .primary"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "permission", id: "per_1", reply: "once" });
    await browser.evaluate(click(".tools button[data-act='terminal']"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "act", act: "terminal" });

    await post({ ...conversation, state: "working" });
    await browser.until("document.getElementById('send').className === 'send stop'");
    await browser.evaluate(click("#send"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "act", act: "stop" }, "the send button stops the agent at work");

    const key = (name: string, shift = false): string =>
      `document.getElementById('input').dispatchEvent(new KeyboardEvent('keydown', { key: ${JSON.stringify(name)}, shiftKey: ${shift}, bubbles: true }))`;
    await browser.evaluate("document.getElementById('input').value = 'Use a log scale.'");
    await browser.evaluate(key("Enter", true));
    assert.notEqual(JSON.parse(await browser.evaluate<string>(lastPost)).type, "send", "Shift+Enter is a new line");
    await browser.evaluate(key("Enter"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "send", text: "Use a log scale." });
    await post({ type: "sent" });
    await browser.until("document.getElementById('input').value === ''");

    await browser.evaluate("const box = document.getElementById('input'); box.value = 'Read @sim'; box.selectionStart = box.selectionEnd = 9; box.dispatchEvent(new Event('input'))");
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "files", query: "sim" });
    await post({ type: "files", files: ["simulate.py", "data/sim.csv"] });
    await browser.until("!document.getElementById('files').hidden");
    await browser.evaluate(key("ArrowDown"));
    await browser.evaluate(key("Enter"));
    assert.equal(await browser.evaluate("document.getElementById('input').value"), "Read /workspace/data/sim.csv ");
    await browser.evaluate("document.getElementById('input').value = ''");

    await browser.evaluate(`Object.entries(${JSON.stringify(LIGHT)}).forEach(([name, value]) => document.documentElement.style.setProperty(name, value))`);
    await post({ ...conversation, state: "idle", title: "Light" });
    await browser.until("document.getElementById('title').textContent === 'Light'");
    const colors = await browser.evaluate<string[]>("[getComputedStyle(document.body).backgroundColor, getComputedStyle(document.querySelector('.bubble')).backgroundColor]");
    assert.equal(colors[0], "rgb(255, 255, 255)", "the light theme's ground");
    assert.notEqual(colors[1], colors[0], "the owner's bubble stands apart from it");
    await shot(browser, "agent-panel-light.png");

    await post({ type: "theme", theme: "clank-night" });
    await browser.until("document.body.className === 'theme-clank-night'");
    assert.equal(await browser.evaluate("getComputedStyle(document.body).backgroundColor"), "rgb(26, 27, 38)");
    await shot(browser, "agent-panel-clank-night.png");
  } finally {
    await browser.close();
    removeFolder(folder);
  }
});

test("the page redraws only the blocks that changed, keeps the scroll, shows a pending message and stops on Escape", { skip: EDGE ? false : "no Edge here" }, async () => {
  const folder = mkdtempSync(path.join(tmpdir(), "clank-agent-"));
  const files = {
    css: "agent.css", script: "agent.js", marked: `${LIB}/marked.min.js`, katex: `${LIB}/katex.min.js`,
    katexCss: `${LIB}/katex.min.css`,
  };  // prettier-ignore
  const browser = await Browser.open(webviewPage(folder, "agent.html", files), path.join(folder, "profile"));
  const post = (message: unknown): Promise<unknown> => browser.evaluate(`window.postMessage(${JSON.stringify(message)}, "*")`);
  const text = (id: string, words: string): unknown => ({ kind: "text", id, text: words, split: splitMath(words) });
  const shown = (blocks: unknown[], state = "working"): unknown => ({
    type: "conversation", title: "A session", subtitle: "", state, model: "", foot: null, older: false, empty: "", blocks,
  });  // prettier-ignore
  try {
    await browser.until("document.readyState === 'complete' && Array.isArray(window.posted) && window.posted.length > 0");
    const many = Array.from({ length: 30 }, (_, n) => text(`t${n}`, `Paragraph ${n} of the answer, long enough to need room on the page as it is drawn.`));
    await post(shown([{ kind: "owner", id: "msg_1", text: "Plot it." }, ...many]));
    await browser.until("document.querySelectorAll('#items .item').length === 31");
    await browser.evaluate("document.querySelector('[data-id=\"msg_1\"]').dataset.mark = 'kept'");
    await browser.evaluate("document.querySelector('[data-id=\"t3\"]').dataset.mark = 'kept'");
    assert.equal(await browser.evaluate("(() => { const m = document.getElementById('conversation'); return m.scrollHeight - m.scrollTop - m.clientHeight < 48; })()"), true, "drawn at the bottom");

    await browser.evaluate("document.getElementById('conversation').scrollTop = 0");
    await browser.until("document.getElementById('conversation').scrollTop === 0");
    const changed = [...many];
    changed[3] = text("t3", "Paragraph 3, said again with more words as the model writes on.");
    await post(shown([{ kind: "owner", id: "msg_1", text: "Plot it." }, ...changed, text("t30", "One more.")]));
    await browser.until("document.querySelectorAll('#items .item').length === 32");
    assert.equal(await browser.evaluate("document.querySelector('[data-id=\"msg_1\"]').dataset.mark"), "kept", "an unchanged block keeps its element");
    assert.equal(await browser.evaluate("document.querySelector('[data-id=\"t3\"]').dataset.mark"), undefined, "a changed block is drawn again");
    assert.ok((await browser.evaluate<string>("document.querySelector('[data-id=\"t3\"]').textContent")).includes("said again"));
    assert.equal(await browser.evaluate("document.getElementById('new').hidden"), false, "more came while the owner read above");
    assert.equal(await browser.evaluate("document.getElementById('conversation').scrollTop"), 0, "and the page did not jump");
    await browser.evaluate("document.getElementById('new').click()");
    await browser.until("document.getElementById('new').hidden");
    assert.equal(await browser.evaluate("(() => { const m = document.getElementById('conversation'); return m.scrollHeight - m.scrollTop - m.clientHeight < 48; })()"), true);

    await post(shown([{ kind: "owner", id: "msg_1", text: "Plot it." }, ...changed, { kind: "owner", id: "p1", text: "And a log scale.", pending: true }]));
    await browser.until("!!document.querySelector('.item.owner.pending')");
    assert.equal(await browser.evaluate("document.querySelector('.item.owner.pending .sending').textContent"), "sending…");

    await browser.evaluate("document.getElementById('input').focus()");
    await browser.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape", windowsVirtualKeyCode: 27 });
    await browser.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape" });
    await browser.until(`${lastPost} === '{"type":"act","act":"stop"}'`);
  } finally {
    await browser.close();
    removeFolder(folder);
  }
});
