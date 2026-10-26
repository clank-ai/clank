// Design 0022 §3, in a real browser: the board's page (media/board.html, as VS Code's board editor shows it, with the
// board's core compiled from core/board.ts, and marked and KaTeX) in headless Edge, driven by real mouse and keys. A
// board sent to it is drawn: a figure from its file, LaTeX as math, a note's Markdown, a frame with its name, a slot
// with Fill, a pin with its comment, a pen stroke and an arrow. A note dragged moves and its move is sent as one edit
// snapped (to another item's edge, or the grid); a box dragged on the empty canvas selects what it touches and the selection's bar aligns it; Delete
// removes; a double click edits a note in place; the pen draws a stroke; Ctrl and the wheel zoom; the selection is
// asked about, a slot is filled, and Clank Night is drawn when the extension says so. A screenshot is left in out/test/.
// The view follows what the agent places until the owner pans or zooms (fitting follows again), and fits only once
// the editor has a size (a tab behind another has none: it opened at 10 % before). A compiled LaTeX item shows that it
// builds, then its drawing inline, with the error of a source that does not build under the last drawing (§6).

import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { test } from "node:test";

import type { Board } from "../src/core/board";
import { Browser, EDGE, removeFolder, webviewPage } from "./browser";

const LIB = "../../clank/components/agents/artifact_lib";
const PNG = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAQAAAADCAIAAAA7ljmRAAAAEklEQVR4nGP4z8AARwzEcQAAk8kE/O3UP3AAAAAASUVORK5CYII=";
const BOARD: Board = {
  board: 1,
  title: "Fig 3",
  settings: { grid: 20, preamble: "" },
  items: [
    { id: "frame-5", kind: "frame", x: 60, y: 40, w: 760, h: 520, name: "Figure 3" },
    { id: "fig-1", kind: "figure", x: 80, y: 80, w: 360, h: 298, file: "figures/amp.png", caption: "(a) Amplitude" },
    { id: "latex-2", kind: "latex", x: 80, y: 420, w: 290, h: 80, source: "A(f) = \\frac{F_0}{\\sqrt{x}}", mode: "math" },
    { id: "slot-3", kind: "slot", x: 480, y: 80, w: 320, h: 220, label: "phase", state: "open" },
    { id: "note-4", kind: "note", x: 900, y: 80, w: 280, h: 120, text: "**Why** $Q \\approx 25$" },
    { id: "pen-6", kind: "pen", points: [[230, 100], [290, 110], [260, 150]] },
    { id: "pin-7", kind: "pin", x: 400, y: 300, text: "Mark Q", open: true },
    { id: "arrow-8", kind: "arrow", from: { item: "note-4" }, to: { item: "fig-1" } },
  ],
};

const lastPost = "JSON.stringify(window.posted[window.posted.length - 1])";

async function center(browser: Browser, selector: string): Promise<{ x: number; y: number }> {
  return browser.evaluate<{ x: number; y: number }>(
    `(() => { const r = document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`,
  );
}

async function drag(browser: Browser, from: { x: number; y: number }, to: { x: number; y: number }): Promise<void> {
  await browser.mouse("mousePressed", from.x, from.y);
  for (let step = 1; step <= 6; step++) {
    await browser.mouse("mouseMoved", from.x + ((to.x - from.x) * step) / 6, from.y + ((to.y - from.y) * step) / 6);
  }
  await browser.mouse("mouseReleased", to.x, to.y);
}

async function key(browser: Browser, name: string, code: string, modifiers = 0): Promise<void> {
  await browser.send("Input.dispatchKeyEvent", { type: "keyDown", key: name, code, modifiers, windowsVirtualKeyCode: name.length === 1 ? name.toUpperCase().charCodeAt(0) : name === "Delete" ? 46 : 0 });
  await browser.send("Input.dispatchKeyEvent", { type: "keyUp", key: name, code, modifiers });
}

test("the board's page draws a board and turns the owner's mouse and keys into edits", { skip: EDGE ? false : "no Edge here" }, async () => {
  const folder = mkdtempSync(path.join(tmpdir(), "clank-board-"));
  const files = {
    css: "board.css", script: "board.js", core: "../out/src/core/board.js", marked: `${LIB}/marked.min.js`,
    katex: `${LIB}/katex.min.js`, katexCss: `${LIB}/katex.min.css`,
  };  // prettier-ignore
  const browser = await Browser.open(webviewPage(folder, "board.html", files), path.join(folder, "profile"));
  const post = (message: unknown): Promise<unknown> => browser.evaluate(`window.postMessage(${JSON.stringify(message)}, "*")`);
  try {
    await browser.until("document.readyState === 'complete' && Array.isArray(window.posted) && window.posted.length > 0");
    assert.deepEqual(await browser.evaluate("window.posted[0]"), { type: "ready" });
    await post({ type: "board", board: BOARD, path: "figures/fig3.board", uris: { "figures/amp.png": PNG } });
    await browser.until("document.querySelectorAll('#items .item').length === 6");
    assert.deepEqual(await browser.evaluate("[...document.querySelectorAll('#items .item')].map((each) => each.className.trim())"),
      ["item frame", "item figure", "item latex", "item slot", "item note", "item pin"]);  // prettier-ignore
    assert.equal(await browser.evaluate("document.querySelectorAll('#mark-paths path, #mark-paths line').length"), 2, "the pen stroke and the arrow");
    assert.equal(await browser.evaluate("document.querySelectorAll('.item.latex .katex').length"), 1, "the LaTeX drawn by KaTeX");
    assert.equal(await browser.evaluate("document.querySelectorAll('.item.note .katex').length"), 1, "the note's math too");
    assert.equal(await browser.evaluate("document.querySelector('.item.figure img').getAttribute('src').startsWith('data:image/png')"), true);
    assert.equal(await browser.evaluate("document.querySelector('.frame-name').textContent"), "Figure 3 · frame");
    assert.equal(await browser.evaluate("document.querySelector('.pin-text').textContent"), "Mark Q");
    assert.equal(await browser.evaluate("document.getElementById('send-pins').hidden"), false, "an open pin to send");

    const note = await center(browser, '[data-id="note-4"]');
    await drag(browser, note, { x: note.x + 60, y: note.y + 140 });
    const moved = JSON.parse(await browser.evaluate<string>(lastPost));
    assert.equal(moved.type, "ops");
    const set = moved.ops.find((op: { id: string }) => op.id === "note-4");
    assert.ok(set.fields.y > 80, "it moved down");
    assert.equal(Number.isInteger(set.fields.x) && Number.isInteger(set.fields.y), true, "in whole pixels, snapped");

    const empty = await browser.evaluate<{ x: number; y: number }>("(() => { const r = document.querySelector('[data-id=\"fig-1\"]').getBoundingClientRect(); return { x: r.left - 30, y: r.bottom + 160 }; })()");
    const corner = await center(browser, '[data-id="fig-1"]');
    await drag(browser, empty, { x: corner.x + 10, y: corner.y });
    assert.equal(await browser.evaluate("document.getElementById('bar').hidden"), false, "the selection's bar");
    assert.deepEqual(await browser.evaluate("document.querySelectorAll('#selection .outline').length >= 2"), true);
    await browser.evaluate("document.querySelector('#bar [data-align=\"left\"]').click()");
    const aligned = JSON.parse(await browser.evaluate<string>(lastPost));
    assert.deepEqual(aligned.ops.filter((op: { op: string }) => op.op === "set").map((op: { fields: { x: number } }) => op.fields.x), [80, 80]);

    await browser.click(note.x + 60, note.y + 140);
    await key(browser, "Delete", "Delete");
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "ops", ops: [{ op: "remove", ids: ["note-4", "arrow-8"] }] }, "its arrow goes with it");

    await post({ type: "board", board: BOARD, path: "figures/fig3.board", uris: { "figures/amp.png": PNG } });
    await browser.until("document.querySelectorAll('#items .item').length === 6");
    const again = await center(browser, '[data-id="note-4"]');
    for (const count of [1, 2]) {
      await browser.send("Input.dispatchMouseEvent", { type: "mousePressed", x: again.x, y: again.y, button: "left", buttons: 1, clickCount: count });
      await browser.send("Input.dispatchMouseEvent", { type: "mouseReleased", x: again.x, y: again.y, button: "left", buttons: 0, clickCount: count });
    }
    await browser.until("!!document.querySelector('.editor textarea')");
    await browser.evaluate("document.querySelector('.editor textarea').value = 'Checked against the decay'");
    await browser.evaluate("[...document.querySelectorAll('.editor button')].find((b) => b.textContent === 'Done').click()");
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)).ops[0], { op: "set", id: "note-4", fields: { text: "Checked against the decay" } });

    await browser.evaluate("document.querySelector('[data-tool=\"pen\"]').click()");
    const slot = await center(browser, '[data-id="slot-3"]');
    await drag(browser, { x: slot.x - 40, y: slot.y }, { x: slot.x + 40, y: slot.y + 20 });
    const drawn = JSON.parse(await browser.evaluate<string>(lastPost)).ops[0];
    assert.equal(drawn.op, "add");
    assert.equal(drawn.item.kind, "pen");
    assert.ok(drawn.item.points.length > 2);

    await browser.evaluate("document.querySelector('[data-tool=\"select\"]').click()");
    const before = await browser.evaluate<string>("document.getElementById('zoom-level').textContent");
    await browser.send("Input.dispatchMouseEvent", { type: "mouseWheel", x: slot.x, y: slot.y, deltaX: 0, deltaY: -240, modifiers: 2 });
    await browser.until(`document.getElementById('zoom-level').textContent !== ${JSON.stringify(before)}`);

    const figure = await center(browser, '[data-id="fig-1"]');
    await browser.click(figure.x, figure.y);
    await browser.evaluate("document.querySelector('#bar [data-act=\"ask\"]').click()");
    await browser.until("!document.getElementById('ask').hidden");
    await browser.evaluate("document.getElementById('ask-text').value = 'Mark the peak'");
    await browser.evaluate("document.getElementById('ask-send').click()");
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "ask", ids: ["fig-1"], text: "Mark the peak" });
    assert.equal(await browser.evaluate("getComputedStyle(document.getElementById('ask')).display"), "none", "the question closes once sent");

    await browser.evaluate("document.querySelector('[data-act=\"fill\"]').click()");
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "fill", id: "slot-3" });

    await post({ type: "theme", theme: "clank-night" });
    await browser.until("document.body.className === 'theme-clank-night'");
    await browser.evaluate("document.getElementById('zoom-level').click()");
    const screenshot = (await browser.send("Page.captureScreenshot", { format: "png" })) as { data: string };
    writeFileSync(path.join(__dirname, "board.png"), Buffer.from(screenshot.data, "base64"));
  } finally {
    await browser.close();
    removeFolder(folder);
  }
});

test("the board's view follows what the agent places until the owner zooms, and waits for a size to fit", { skip: EDGE ? false : "no Edge here" }, async () => {
  const folder = mkdtempSync(path.join(tmpdir(), "clank-board-"));
  const files = {
    css: "board.css", script: "board.js", core: "../out/src/core/board.js", marked: `${LIB}/marked.min.js`,
    katex: `${LIB}/katex.min.js`, katexCss: `${LIB}/katex.min.css`,
  };  // prettier-ignore
  const browser = await Browser.open(webviewPage(folder, "board.html", files), path.join(folder, "profile"));
  const post = (message: unknown): Promise<unknown> => browser.evaluate(`window.postMessage(${JSON.stringify(message)}, "*")`);
  const zoom = (): Promise<string> => browser.evaluate<string>("document.getElementById('zoom-level').textContent");
  const note = (id: string, x: number): Board["items"][number] => ({ id, kind: "note", x, y: 80, w: 280, h: 120, text: id });
  const board = (...items: Board["items"]): Board => ({ board: 1, title: "t", settings: { grid: 20, preamble: "" }, items });
  try {
    await browser.until("document.readyState === 'complete' && Array.isArray(window.posted) && window.posted.length > 0");
    await browser.evaluate("document.getElementById('viewport').style.maxWidth = '40px'");
    await post({ type: "board", board: board(note("note-1", 80)), path: "b.board" });
    await browser.until("document.querySelectorAll('#items .item').length === 1");
    assert.equal(await zoom(), "100 %", "no fit while the editor has no size (a tab behind another)");
    await browser.evaluate("document.getElementById('viewport').style.maxWidth = ''");
    await browser.until("document.getElementById('zoom-level').textContent !== '100 %'");
    const near = await zoom();
    assert.notEqual(near, "10 %", "fitted once it has a size");

    await post({ type: "board", board: board(note("note-1", 80), note("note-2", 3000)), path: "b.board" });
    await browser.until(`document.getElementById('zoom-level').textContent !== ${JSON.stringify(near)}`);
    const far = await zoom();
    assert.ok(Number.parseInt(far) < Number.parseInt(near), "the agent's far note brought into view");

    const middle = await center(browser, "#viewport");
    await browser.send("Input.dispatchMouseEvent", { type: "mouseWheel", x: middle.x, y: middle.y, deltaX: 0, deltaY: -240, modifiers: 2 });
    await browser.until(`document.getElementById('zoom-level').textContent !== ${JSON.stringify(far)}`);
    const chosen = await zoom();
    await post({ type: "board", board: board(note("note-1", 80), note("note-2", 3000), note("note-3", 6000)), path: "b.board" });
    await browser.until("document.querySelectorAll('#items .item').length === 3");
    assert.equal(await zoom(), chosen, "the owner's zoom is kept");
    await browser.evaluate("document.getElementById('zoom-level').click()");
    assert.ok(Number.parseInt(await zoom()) < Number.parseInt(far), "fitting follows again");

    const tikz = { id: "latex-4", kind: "latex", x: 80, y: 300, w: 200, h: 100, source: "\\tikz\\draw (0,0)--(1,0);", mode: "compiled" };
    await post({ type: "board", board: board(tikz), path: "b.board", compiled: { "latex-4": {} } });
    await browser.until("document.querySelector('.item.latex .missing')?.textContent === 'Compiling with TeX…'");
    const svg = '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="27" viewBox="0 0 72 20"><path d="M 0 5 L 72 5" stroke="currentColor"></path></svg>';
    await post({ type: "board", board: board(tikz), path: "b.board", compiled: { "latex-4": { svg, error: "Too many }'s." } } });
    await browser.until("!!document.querySelector('.item.latex .drawing svg path')");
    assert.equal(await browser.evaluate("document.querySelector('.item.latex .problem').textContent"), "Too many }'s.", "the last drawing, and why the source does not build");
  } finally {
    await browser.close();
    removeFolder(folder);
  }
});
