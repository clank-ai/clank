// Design 0008 §6, in a real browser: the annotator page (media/annotator.html, as VS Code's webview shows it) in
// headless Edge, driven by mouse and keyboard events through the browser's debugging protocol. The box tool is chosen
// on the toolbar and a box dragged on the figure: the mark is kept in the image's own pixels; a message typed and
// Enter pressed sends the marks, the message and the marked-up copy (a PNG); a reply that it went clears the marks and
// says where it went. A note written near the figure's corner opens as a bubble that stays on the figure, its words
// wrapped; dragged, only its bubble moves (its pin stays where it was clicked); a click on it opens it to edit. Skipped
// where no Edge is installed (the Linux runs); screenshots of the page are left in out/test/ to look at.

import assert from "node:assert/strict";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { test } from "node:test";

import { Browser, EDGE, webviewPage } from "./browser";

/** The annotator page as the extension fills it in. */
function page(folder: string): string {
  return webviewPage(folder, "annotator.html", { css: "annotator.css", marks: "marks.js", script: "annotator.js" });
}


/** The page with an 800 by 500 figure in it (a curve on white), once it says it is ready. */
async function showFigure(browser: Browser): Promise<void> {
  await browser.until("document.readyState === 'complete' && Array.isArray(window.posted) && window.posted.length > 0");
  assert.deepEqual(await browser.evaluate("window.posted[0]"), { type: "ready" });
  await browser.evaluate(`(() => {
    const c = document.createElement("canvas"); c.width = 800; c.height = 500;
    const g = c.getContext("2d"); g.fillStyle = "#ffffff"; g.fillRect(0, 0, 800, 500);
    g.strokeStyle = "#1f77b4"; g.lineWidth = 3; g.beginPath(); g.moveTo(60, 440);
    for (let x = 60; x <= 760; x += 10) g.lineTo(x, 440 - ((x - 60) / 700) ** 2 * 380); g.stroke();
    window.postMessage({ type: "figure", src: c.toDataURL("image/png"), name: "figs/msd.png" }, "*");
  })()`);
  await browser.until("document.getElementById('canvas').style.display === 'block'");
}

/** Where a point of the figure (in its own pixels) is on the page, once the figure is still: the page fits it again a
 * frame after its room changes (a chip added under it), and a drag measured before that, under load, moved the bubble
 * 17 pixels too far (2026-10-16). */
async function onPage(browser: Browser): Promise<(x: number, y: number) => [number, number]> {
  const shown = await browser.evaluate<{ x: number; y: number; width: number }>(`(async () => {
    const read = () => { const r = document.getElementById('canvas').getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width }; };
    const frame = () => new Promise((done) => requestAnimationFrame(() => done(read())));
    // a frame runs its animation callbacks before its resize observers: compare from the next frame on
    let [before, after] = [await frame(), await frame()];
    for (let frames = 0; frames < 60 && JSON.stringify(before) !== JSON.stringify(after); frames++) {
      [before, after] = [after, await frame()];
    }
    return after;
  })()`);
  const scale = shown.width / 800;
  return (x, y) => [shown.x + x * scale, shown.y + y * scale];
}

/** A key pressed and released. */
async function key(browser: Browser, name: string, virtual: number): Promise<void> {
  const text = name === "Enter" ? "\r" : name.length === 1 ? name : undefined;
  const code = name.length === 1 ? `Key${name.toUpperCase()}` : name;
  await browser.send("Input.dispatchKeyEvent", { type: "keyDown", key: name, code, windowsVirtualKeyCode: virtual, text });
  await browser.send("Input.dispatchKeyEvent", { type: "keyUp", key: name, code, windowsVirtualKeyCode: virtual });
}

test("a box drawn on the figure and a message sent leave the page with the marks, the words and the marked-up copy", { skip: EDGE ? false : "no Edge here" }, async () => {
  const folder = mkdtempSync(path.join(tmpdir(), "clank-annotator-"));
  const browser = await Browser.open(page(folder), path.join(folder, "profile"));
  try {
    await showFigure(browser);
    const button = await browser.evaluate<{ x: number; y: number }>(
      "(() => { const r = document.querySelector('[data-tool=box]').getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()",
    );
    await browser.click(button.x, button.y);
    assert.equal(await browser.evaluate("document.body.dataset.tool"), "box");
    const shown = await browser.evaluate<{ x: number; y: number; width: number }>(
      "(() => { const r = document.getElementById('canvas').getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width }; })()",
    );
    const scale = shown.width / 800;
    const at = (x: number, y: number): [number, number] => [shown.x + x * scale, shown.y + y * scale];
    await browser.mouse("mousePressed", ...at(500, 120));
    await browser.mouse("mouseMoved", ...at(600, 200));
    await browser.mouse("mouseMoved", ...at(700, 300));
    await browser.mouse("mouseReleased", ...at(700, 300));
    await browser.until("document.querySelectorAll('#chips .chip').length === 1");
    const box = await browser.evaluate<{ x: number; y: number }>(
      "(() => { const r = document.getElementById('message').getBoundingClientRect(); return { x: r.x + 20, y: r.y + r.height / 2 }; })()",
    );
    await browser.click(box.x, box.y);
    await browser.send("Input.insertText", { text: "Use a log scale for this part." });
    const screenshot = (await browser.send("Page.captureScreenshot", { format: "png" })) as { data: string };
    writeFileSync(path.join(__dirname, "annotator.png"), Buffer.from(screenshot.data, "base64"));
    await browser.send("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13, text: "\r" });
    await browser.send("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
    await browser.until("window.posted.some((message) => message.type === 'send')");
    const sent = await browser.evaluate<{ marks: Array<{ n: number; kind: string; points: number[][] }>; message: string; image: string }>(
      "window.posted.find((message) => message.type === 'send')",
    );
    assert.equal(sent.message, "Use a log scale for this part.");
    assert.equal(sent.marks.length, 1);
    const [mark] = sent.marks;
    assert.deepEqual([mark!.n, mark!.kind], [1, "box"]);
    for (const [got, wanted] of [[mark!.points[0]!, [500, 120]], [mark!.points[1]!, [700, 300]]] as const) {
      assert.ok(Math.abs(got[0]! - wanted[0]) <= 2 && Math.abs(got[1]! - wanted[1]) <= 2, `in the image's pixels: ${got} for ${wanted}`);
    }
    assert.match(sent.image, /^data:image\/png;base64,/);
    await browser.evaluate("window.postMessage({ type: 'sent', text: 'Sent to the agent of paper, with the marked-up figure.' }, '*')");
    await browser.until("document.getElementById('status').textContent.startsWith('Sent to the agent of paper')");
    assert.equal(await browser.evaluate("document.querySelectorAll('#chips .chip').length"), 0, "the marks are cleared");
    assert.equal(await browser.evaluate("document.getElementById('message').value"), "");
  } finally {
    await browser.close();
    try {
      rmSync(folder, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
    } catch {
      // Edge's helpers may hold a file a little longer: the temporary folder is left for the system to clear
    }
  }
});

test("a note opens as a bubble that stays on the figure; dragged, only the bubble moves; a click edits it", { skip: EDGE ? false : "no Edge here" }, async () => {
  const folder = mkdtempSync(path.join(tmpdir(), "clank-annotator-"));
  const browser = await Browser.open(page(folder), path.join(folder, "profile"));
  try {
    await showFigure(browser);
    const at = await onPage(browser);
    await key(browser, "t", 84);
    assert.equal(await browser.evaluate("document.body.dataset.tool"), "text");
    await browser.click(...at(770, 20));
    await browser.until("document.activeElement !== null && document.activeElement.closest('.note-editor') !== null");
    const long = "Add an inset that zooms on this crossing, with a dashed vertical line at your estimate of the critical point.";
    await browser.send("Input.insertText", { text: long });
    const placed = await browser.evaluate<{ inside: boolean; lines: number }>(`(() => {
      const editor = document.querySelector(".note-editor").getBoundingClientRect();
      const figure = document.getElementById("canvas").getBoundingClientRect();
      const input = document.querySelector(".note-editor textarea");
      const inside = editor.left >= figure.left - 1 && editor.right <= figure.right + 1 && editor.top >= figure.top - 1
        && editor.bottom <= figure.bottom + 1;
      return { inside, lines: Math.round(input.scrollHeight / parseFloat(input.style.lineHeight)) };
    })()`);
    assert.ok(placed.inside, "the bubble being written stays on the figure");
    assert.ok(placed.lines > 1, "its words wrap");
    const written = (await browser.send("Page.captureScreenshot", { format: "png" })) as { data: string };
    writeFileSync(path.join(__dirname, "annotator-note-writing.png"), Buffer.from(written.data, "base64"));
    await key(browser, "Enter", 13);
    await browser.until("document.querySelector('.note-editor') === null && document.querySelectorAll('#chips .chip').length === 1");
    const bubble = await browser.evaluate<number[]>(`(() => {
      const m = window.ClankMarks;
      const measure = m.measurer(document.createElement("canvas").getContext("2d"));
      return m.noteLayout({ points: [[770, 20]], text: ${JSON.stringify(long)} }, measure, 800, 500).box;
    })()`);
    assert.ok(bubble[0]! >= 0 && bubble[2]! <= 800 && bubble[1]! >= 0 && bubble[3]! <= 500, `kept on the figure: ${bubble}`);
    const middle: [number, number] = [(bubble[0]! + bubble[2]!) / 2, (bubble[1]! + bubble[3]!) / 2];
    const dropped: [number, number] = [middle[0] - 400, middle[1] + 250];
    const now = await onPage(browser); // the note's chip took room under the figure: it was fit again
    await browser.mouse("mousePressed", ...now(...middle));
    for (const step of [0.25, 0.5, 0.75, 1]) {
      await browser.mouse("mouseMoved", ...now(middle[0] - 400 * step, middle[1] + 250 * step));
    }
    await browser.mouse("mouseReleased", ...now(...dropped));
    assert.equal(await browser.evaluate("document.querySelector('.note-editor')"), null, "a drag is not a click");
    await browser.click(...now(...dropped));
    // the editor takes the keys once it has the focus, a moment after it opens: a key sent sooner goes to the page
    await browser.until("document.activeElement !== null && document.activeElement.closest('.note-editor') !== null");
    assert.equal(await browser.evaluate("document.querySelector('.note-editor textarea').value"), long, "a click opens it to edit");
    await key(browser, "Escape", 27);
    await browser.until("document.querySelector('.note-editor') === null");
    const moved = (await browser.send("Page.captureScreenshot", { format: "png" })) as { data: string };
    writeFileSync(path.join(__dirname, "annotator-note-moved.png"), Buffer.from(moved.data, "base64"));
    await browser.evaluate("document.getElementById('send').click()");
    await browser.until("window.posted.some((message) => message.type === 'send')");
    const [note] = await browser.evaluate<Array<{ kind: string; points: number[][]; text: string; bubble: number[] }>>(
      "window.posted.find((message) => message.type === 'send').marks",
    );
    assert.equal(note!.kind, "text");
    assert.equal(note!.text, long);
    const [pin] = note!.points;
    assert.ok(Math.abs(pin![0]! - 770) <= 2 && Math.abs(pin![1]! - 20) <= 2, `its pin stays where it was clicked: ${pin}`);
    assert.ok(Math.abs(note!.bubble[0]! - (bubble[0]! - 400)) <= 3, `its bubble moved: ${note!.bubble} from ${bubble}`);
  } finally {
    await browser.close();
    try {
      rmSync(folder, { recursive: true, force: true, maxRetries: 10, retryDelay: 300 });
    } catch {
      // Edge's helpers may hold a file a little longer: the temporary folder is left for the system to clear
    }
  }
});
