// Design 0010 §6, in a real browser: the review page (media/notion.html, as VS Code's webview shows it) in headless
// Edge. A batch sent to it shows its database as a table: the changed row with what a cell was struck above what it
// would be, the removed and the added rows marked, a neighbor left as it is; the first change is chosen. Everything not
// written is checked at first; unchecking a row leaves it out of the approval, and unchecking a field of a change sends
// only the rest of it; a new entry's title cannot be left out while other parts of it go (unchecking it unchecks them,
// checking a part checks it). The page view shows the page block by block, the unchanged ones folded; As in Notion
// shows the entry as it will look. Shown again after an approval, the page keeps what the owner checked and marks what
// was written. A batch written whole cannot be approved again. Comments (§7): each thread shows under what it is on
// (the batch, a property, a block of the page), with the agent's answer; a comment is written there and sent to the
// extension, one not sent yet is taken back, and the batch is sent back with them; a proposal revised for them says
// what changed since the last revision. Screenshots of the page are left in out/test/.

import assert from "node:assert/strict";
import { mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import * as path from "node:path";
import { test } from "node:test";

import type { Batch, Comment, NotionReview, Proposal, Table } from "../src/core/notion";
import { Browser, EDGE, removeFolder, webviewPage } from "./browser";

const text = (value: string): Record<string, unknown> => ({ type: "text", text: { content: value } });

function proposals(): Proposal[] {
  const base = { database: "ds-lit", database_name: "Papers (test)", notes: [], why: "a test", sources: [], result: null };
  return [
    {
      ...base,
      id: "p1",
      kind: "entry",
      page: null,
      title: "A third made-up paper",
      fields: [
        { name: "Title", was: "", now: "A third made-up paper" },
        { name: "Authors", was: "", now: "Who, Ever" },
      ],
      markdown: "## Summary\n\nWhat it **shows**, with $x^2$.",
      changes: null,
      base: null,
      payload: { Title: { title: [text("A third made-up paper")] }, Authors: { rich_text: [text("Who, Ever")] } },
      blocks: [{ type: "heading_2" }, { type: "paragraph" }],
    } as Proposal,
    {
      ...base,
      id: "p2",
      kind: "change",
      page: "lit-1",
      title: "A made-up paper on sampling",
      fields: [
        { name: "Year", was: "2001", now: "2002" },
        { name: "Reading", was: "Notes written", now: "To read" },
      ],
      markdown: "## Summary\n\nRewritten.",
      changes: [
        { op: "keep", markdown: "## Summary" },
        { op: "update", was: "A made-up result.", markdown: "Rewritten." },
        { op: "remove", markdown: "- ▸ Details" },
        { op: "keep", markdown: "$$\nP(m) = m / n\n$$" },
      ],
      base: { properties: {}, markdown: "", edited: "2026-10-17T12:00:00.000Z" },
      why: "The published version.",
      sources: ["plan.md"],
      notes: [],
    } as Proposal,
    {
      ...base,
      id: "p3",
      kind: "removal",
      page: "lit-2",
      title: "Another made-up paper",
      fields: [],
      markdown: null,
      changes: null,
      base: { properties: {}, markdown: "", edited: "2026-10-17T12:00:00.000Z" },
      why: "A duplicate.",
    } as Proposal,
  ];
}

function batch(state = "ready", changed: Partial<Record<string, Partial<Proposal>>> = {}): Batch {
  return {
    id: "nb-1",
    workspace: "paper",
    state,
    summary: "Three things for the literature.",
    revision: 1,
    created: "2026-10-17T18:00:00Z",
    updated: "2026-10-17T18:00:00Z",
    counts: { new: 1, changed: 1, removed: 1 },
    databases: ["Papers (test)"],
    proposals: proposals().map((each) => ({ ...each, ...(changed[each.id] ?? {}) })),
  };
}

const TABLE: Table = {
  database: "ds-lit",
  name: "Papers (test)",
  columns: ["Title", "Authors", "Year", "Reading"],
  shared: true,
  rows: [
    {
      id: "lit-1", title: "A made-up paper on sampling", url: "https://www.notion.so/lit-1", mark: "changed", proposal: "p2",
      cells: { Title: { text: "A made-up paper on sampling" }, Authors: { text: "Someone, Else" },
        Year: { text: "2002", was: "2001" }, Reading: { text: "To read", was: "Notes written" } },
    },
    {
      id: "lit-2", title: "Another made-up paper", url: "https://www.notion.so/lit-2", mark: "removed", proposal: "p3",
      cells: { Title: { text: "Another made-up paper" }, Authors: { text: "Nobody, In Particular" }, Year: { text: "2003" },
        Reading: { text: "To read" } },
    },
    {
      id: "lit-3", title: "A far paper", url: "https://www.notion.so/lit-3", mark: "same", proposal: null,
      cells: { Title: { text: "A far paper" }, Authors: { text: "" }, Year: { text: "" }, Reading: { text: "" } },
    },
    {
      id: null, title: "A third made-up paper", url: "", mark: "added", proposal: "p1",
      cells: { Title: { text: "A third made-up paper", was: "" }, Authors: { text: "Who, Ever", was: "" },
        Year: { text: "" }, Reading: { text: "" } },
    },
  ],
};

async function send(browser: Browser, review: NotionReview): Promise<void> {
  await browser.evaluate(`window.postMessage(${JSON.stringify({ type: "review", review })}, "*")`);
}

async function shot(browser: Browser, name: string): Promise<void> {
  const screenshot = (await browser.send("Page.captureScreenshot", { format: "png", captureBeyondViewport: true })) as { data: string };
  writeFileSync(path.join(__dirname, name), Buffer.from(screenshot.data, "base64"));
}

const click = (selector: string): string => `document.querySelector(${JSON.stringify(selector)}).click()`;
const lastPost = "JSON.stringify(window.posted[window.posted.length - 1])";

test("the review page shows the table, sends what is checked, and keeps the choices when shown again", { skip: EDGE ? false : "no Edge here" }, async () => {
  const folder = mkdtempSync(path.join(tmpdir(), "clank-notion-"));
  const browser = await Browser.open(webviewPage(folder, "notion.html", { css: "notion.css", script: "notion.js" }), path.join(folder, "profile"));
  try {
    await browser.until("document.readyState === 'complete' && Array.isArray(window.posted) && window.posted.length > 0");
    assert.deepEqual(await browser.evaluate("window.posted[0]"), { type: "ready" });
    await send(browser, { batch: batch(), tables: [TABLE], everything: false });
    await browser.until("document.querySelectorAll('#rows tr').length === 4");
    assert.deepEqual(await browser.evaluate("[...document.querySelectorAll('#rows tr')].map((row) => row.className)"), [
      "changed selected", "removed", "same", "added",
    ]);
    assert.deepEqual(await browser.evaluate("[...document.querySelectorAll('#rows tr')[0].querySelectorAll('td')[3].children].map((each) => each.className + ':' + each.textContent)"),
      ["was:2001", "now:2002"]);
    assert.equal(await browser.evaluate("document.getElementById('approve').textContent"), "Approve 3 checked");
    assert.equal(await browser.evaluate("document.querySelector('#rows tr.same input')"), null, "a neighbor has nothing to check");
    assert.equal(await browser.evaluate("getComputedStyle(document.getElementById('databases')).display"), "none", "one database, no tabs");
    assert.match(await browser.evaluate<string>("document.getElementById('why').textContent"), /Why: The published version\.Sources: plan\.md/);
    await shot(browser, "notion-review.png");

    await browser.evaluate(click("#rows tr.removed input"));
    assert.equal(await browser.evaluate("document.getElementById('approve').textContent"), "Approve 2 checked");
    await browser.evaluate(click("input[aria-label='Include Year']"));
    assert.equal(await browser.evaluate("document.querySelector('#rows tr.changed input').indeterminate"), true);
    await browser.evaluate(click("#approve"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), {
      type: "approve", batch: "nb-1", parts: { p1: ["Title", "Authors", "page"], p2: ["Reading", "page"] },
    });

    const row = await browser.evaluate<{ x: number; y: number }>(
      "(() => { const r = document.querySelector('#rows tr.added td:nth-child(3)').getBoundingClientRect(); return { x: r.x + 5, y: r.y + r.height / 2 }; })()",
    );
    await browser.click(row.x, row.y);
    await browser.until("document.getElementById('title').textContent === 'A third made-up paper'");
    await browser.evaluate(click("input[aria-label='Include Title']"));
    assert.equal(await browser.evaluate("document.querySelector('#rows tr.added input').checked"), false, "no entry without its title");
    await browser.evaluate(click("input[aria-label='Include Authors']"));
    assert.deepEqual(await browser.evaluate("['Title', 'Authors'].map((name) => document.querySelector(`input[aria-label='Include ${name}']`).checked)"),
      [true, true], "a part checked checks the title");

    await browser.evaluate(click("[data-view=notion]"));
    assert.deepEqual(await browser.evaluate("[...document.querySelectorAll('.notion .md > *')].map((each) => each.className + ':' + each.textContent)"),
      ["md-h2:Summary", "md-p:What it shows, with x^2."]);
    assert.equal(await browser.evaluate("document.querySelector('.notion .md-p strong').textContent"), "shows");
    await browser.evaluate(click("#rows tr.changed td:nth-child(2)"));
    await browser.evaluate(click("[data-view=page]"));
    assert.deepEqual(await browser.evaluate("[...document.querySelectorAll('.blocks .block')].map((each) => each.className + ':' + each.textContent)"), [
      "block kept:⋯ ## Summary", "block update:A made-up result.Rewritten.", "block remove:- ▸ Details", "block kept:⋯ P(m) = m / n",
    ]);
    await shot(browser, "notion-review-page.png");
    await browser.evaluate(click("#open"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "open", url: "https://www.notion.so/lit-1" });
    await browser.evaluate(click("#all"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "rows", batch: "nb-1", everything: true });

    const done = { parts: ["Year"], id: "lit-1", url: "https://www.notion.so/lit-1", edited: "x" };
    await send(browser, { batch: batch("partly written", { p2: { done, result: { written: false, partly: true, at: "x" } } }), tables: [TABLE], everything: false });
    await browser.until("!document.getElementById('banner').hidden");
    assert.equal(await browser.evaluate("document.getElementById('banner').textContent"), "Partly written: 3 of 3 proposals wait for you.");
    assert.equal(await browser.evaluate("document.querySelector('#rows tr.removed input').checked"), false, "the owner's choice is kept");
    await browser.evaluate(click("[data-view=fields]"));
    assert.equal(await browser.evaluate("document.querySelector('.fields .written') !== null"), true, "Year is marked written");
    assert.match(await browser.evaluate<string>("document.getElementById('result').textContent"), /Written in part \(Year\)/);

    const whole = { result: { written: true, at: "x" } };
    const writtenBatch = batch("written", {
      p1: { ...whole, done: { parts: ["Title", "Authors", "page"], id: "new-1", url: "", edited: "x" } },
      p2: { ...whole, done: { ...done, parts: ["Year", "Reading", "page"] } },
      p3: { ...whole, done: { parts: ["removal"], id: "lit-2", url: "", edited: "x" } },
    });
    await send(browser, { batch: writtenBatch, tables: [TABLE], everything: false });
    await browser.until("document.getElementById('banner').textContent.startsWith('Written to Notion')");
    assert.deepEqual(await browser.evaluate("['approve', 'reject'].map((id) => document.getElementById(id).disabled)"), [true, true]);
    assert.equal(await browser.evaluate("document.querySelectorAll('#rows input').length"), 0, "nothing is left to check");
  } finally {
    await browser.close();
    removeFolder(folder);
  }
});

function comment(id: string, extra: Partial<Comment>): Comment {
  return {
    id, proposal: null, field: null, block: null, block_text: null, text: "", by: "you", at: "2026-10-17T18:06:00Z",
    revision: 1, sent: false, state: "open", replies: [], ...extra,
  };
}

test("comments show under what they are on, are written and taken back there, and the batch is sent back", { skip: EDGE ? false : "no Edge here" }, async () => {
  const folder = mkdtempSync(path.join(tmpdir(), "clank-notion-"));
  const browser = await Browser.open(webviewPage(folder, "notion.html", { css: "notion.css", script: "notion.js" }), path.join(folder, "profile"));
  try {
    await browser.until("document.readyState === 'complete' && Array.isArray(window.posted) && window.posted.length > 0");
    const commented = batch("ready", {
      p2: { revision: 2, previous: { fields: [{ name: "Year", was: "2001", now: "2003" }], markdown: "## Summary\n\nRewritten." } },
    });
    commented.revision = 2;
    commented.comments = [
      comment("c1", { text: "Fewer at a time.", sent: true, state: "answered", replies: [{ text: "Split it in two.", by: "the agent", at: "x" }] }),
      comment("c2", { proposal: "p2", field: "Year", text: "Which year is right?" }),
      comment("c3", { proposal: "p1", block: 1, block_text: "What it shows.", text: "In numbers." }),
    ];
    await send(browser, { batch: commented, tables: [TABLE], everything: false });
    await browser.until("document.querySelectorAll('#rows tr').length === 4");
    assert.match(await browser.evaluate<string>("document.getElementById('batch-comments').textContent"),
      /Comments on the batch.*Fewer at a time\..*The agent: Split it in two\./);
    assert.equal(await browser.evaluate("document.querySelector('#rows tr.changed .comment-count').textContent"), "1");
    assert.deepEqual(await browser.evaluate("[document.getElementById('send-back').textContent, document.getElementById('send-back').disabled]"),
      ["Send back with 2 comments", false]);
    assert.match(await browser.evaluate<string>("document.getElementById('why').textContent"), /^Revised in revision 2: Year was 2003; Reading is changed now\./);
    assert.match(await browser.evaluate<string>("document.querySelector('.fields .thread-row').textContent"), /c2, not sent yet.*Which year is right\?/);
    await shot(browser, "notion-review-comments.png");

    await browser.evaluate(click("button[aria-label='Comment on Reading']"));
    await browser.until("document.querySelector('.composer textarea') !== null");
    await browser.evaluate("(() => { const area = document.querySelector('.composer textarea'); area.value = 'Not read yet?'; area.dispatchEvent(new Event('input')); })()");
    await browser.evaluate("[...document.querySelectorAll('.composer button')].find((each) => each.textContent === 'Add comment').click()");
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), {
      type: "comment", batch: "nb-1", proposal: "p2", field: "Reading", text: "Not read yet?",
    });
    assert.equal(await browser.evaluate("document.querySelector('.composer')"), null, "the composer closes");
    await browser.evaluate(click("[data-comment=c2] .take-back"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "uncomment", batch: "nb-1", comment: "c2" });
    assert.equal(await browser.evaluate("document.querySelector('[data-comment=c1] .take-back')"), null, "a sent comment stays");

    await browser.evaluate(click("#rows tr.added td:nth-child(2)"));
    await browser.evaluate(click("[data-view=page]"));
    assert.match(await browser.evaluate<string>("document.querySelector('.blocks').textContent"), /What it \*\*shows\*\*.*c3, not sent yet.*In numbers\./);
    await browser.evaluate(click("[data-block='0'] .comment-button"));
    await browser.evaluate("(() => { const area = document.querySelector('.composer textarea'); area.value = 'A better heading.'; area.dispatchEvent(new Event('input')); })()");
    await browser.evaluate("[...document.querySelectorAll('.composer button')].find((each) => each.textContent === 'Add comment').click()");
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), {
      type: "comment", batch: "nb-1", proposal: "p1", block: 0, text: "A better heading.",
    });
    await browser.evaluate(click("#entry-comments .comment-button"));
    await browser.until("document.querySelector('#entry-comments textarea') !== null");
    await browser.evaluate(click("#entry-comments .composer .secondary"));
    assert.equal(await browser.evaluate("document.querySelector('#entry-comments textarea')"), null, "Cancel closes it");
    await shot(browser, "notion-review-block-comments.png");
    await browser.evaluate(click("#send-back"));
    assert.deepEqual(JSON.parse(await browser.evaluate<string>(lastPost)), { type: "sendBack", batch: "nb-1" });

    const returned = { ...commented, state: "returned", comments: commented.comments.map((each) => ({ ...each, sent: true })) };
    await send(browser, { batch: returned, tables: [TABLE], everything: false });
    await browser.until("document.getElementById('banner').textContent.startsWith('Sent back')");
    assert.deepEqual(await browser.evaluate("['approve', 'send-back'].map((id) => document.getElementById(id).disabled)"), [true, true]);
  } finally {
    await browser.close();
    removeFolder(folder);
  }
});
