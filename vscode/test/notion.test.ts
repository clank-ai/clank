// Design 0010 §6: the Notion changes view lists each batch waiting with its databases and their entries (marked new,
// changed or removed, a result said beside each) and the batches written or rejected under "Earlier"; the status bar
// and the view's badge count the proposals waiting; a batch submitted, written or rejected reads the batches again,
// and the review open shows the batch as it is now. The review opens on a database or an entry, with the tables of
// changes and their neighbors, or every row when asked. Approving all asks first; approving what is checked sends the
// parts; nothing checked sends nothing. A rejection sends the reason; Escape keeps the batch waiting. A service without
// Notion shows nothing. Comments (§7): the owner comments on a property, takes a comment back and sends the batch back
// (the view keeps it, sent back, without counting it); approving while comments are unanswered asks first. Through the
// controller: the batches are read on connecting and followed with the events, and the
// view and the page act on them.

import assert from "node:assert/strict";
import { test } from "node:test";

import { type Api, Controller } from "../src/core/controller";
import type { ServerEvent } from "../src/core/events";
import type { Presenter } from "../src/core/presenter";
import {
  approvedText,
  type Batch,
  type Comment,
  type BatchBrief,
  countItem,
  countsText,
  type NotionPresenter,
  type NotionReview,
  NotionReviews,
  type Proposal,
  type Table,
  type TreeNode,
  treeOf,
  when,
} from "../src/core/notion";

const NOW = Date.parse("2026-10-17T18:10:00Z");

function proposal(id: string, kind: Proposal["kind"], title: string, extra: Partial<Proposal> = {}): Proposal {
  return {
    id,
    kind,
    database: "ds-lit",
    database_name: "Papers (test)",
    page: kind === "entry" ? null : `lit-${id}`,
    title,
    fields: kind === "removal" ? [] : [{ name: "Year", was: kind === "entry" ? "" : "2001", now: "2002" }],
    notes: [],
    markdown: null,
    changes: null,
    base: null,
    why: "a test",
    sources: [],
    result: null,
    ...extra,
  };
}

function batch(id: string, state: string, proposals: Proposal[], extra: Partial<Batch> = {}): Batch {
  return {
    id,
    workspace: "paper",
    state,
    summary: `Batch ${id}'s summary.`,
    revision: 1,
    created: "2026-10-17T18:00:00Z",
    updated: "2026-10-17T18:05:00Z",
    counts: {
      new: proposals.filter((each) => each.kind === "entry").length,
      changed: proposals.filter((each) => each.kind === "change").length,
      removed: proposals.filter((each) => each.kind === "removal").length,
    },
    databases: ["Papers (test)"],
    left: proposals.filter((each) => !each.result?.written).length,
    proposals,
    ...extra,
  };
}

function brief(whole: Batch): BatchBrief {
  const { proposals: _, ...rest } = whole;
  return rest;
}

const TABLE: Table = { database: "ds-lit", name: "Papers (test)", columns: ["Title", "Year"], rows: [], shared: true };

/** The API, as a test sets it: the batches, the posts it received. */
class FakeApi implements Api {
  batches: Batch[] = [];
  posts: Array<{ path: string; body: unknown }> = [];
  deleted: string[] = [];
  asked: Array<{ path: string; parameters?: Record<string, unknown> }> = [];
  noNotion = false;
  answer: unknown = { written: 1, failed: 0, left: 0 };
  private queue: ServerEvent[] = [];
  private wake: (() => void) | undefined;

  async get<T>(path: string, parameters?: Record<string, unknown>): Promise<T> {
    this.asked.push({ path, parameters });
    const service: Record<string, unknown> = {
      service: { version: "0.7.0", url: "http://127.0.0.1:7720", started: "", clients: [] },
      docker: { label: "Docker Desktop", state: "running", summary: "", containers: [] },
      questions: [],
      history: [{ id: 41 }],
      "runtime/slots": [],
      "runtime/presets": [],
    };
    if (path in service) {
      return service[path] as T;
    }
    if (this.noNotion) {
      throw new Error("404 not_found");
    }
    if (path === "notion/batches") {
      return { batches: this.batches.map(brief) } as T;
    }
    const tables = /^notion\/batches\/([^/]+)\/tables$/.exec(path);
    if (tables) {
      return { tables: [TABLE] } as T;
    }
    const found = this.batches.find((each) => path === `notion/batches/${each.id}`);
    if (found) {
      const { left: _, ...whole } = found;
      return whole as T;
    }
    throw new Error(`no ${path}`);
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    this.posts.push({ path, body });
    return (path.endsWith("/return") ? { sent_to: { session: "ses_1", new: false } } : this.answer) as T;
  }

  async delete<T>(path: string): Promise<T> {
    this.deleted.push(path);
    return {} as T;
  }

  async *events(_after: number | undefined, signal: AbortSignal): AsyncGenerator<ServerEvent> {
    while (!signal.aborted) {
      const next = this.queue.shift();
      if (next) {
        yield next;
        continue;
      }
      await new Promise<void>((resolve) => {
        this.wake = resolve;
        signal.addEventListener("abort", () => resolve(), { once: true });
      });
    }
  }

  send(message: ServerEvent): void {
    this.queue.push(message);
    this.wake?.();
  }
}

/** VS Code, as the Notion review sees it: what it was told, and the owner's answers set beforehand. */
class FakePresenter implements NotionPresenter {
  counted: Array<{ count: number; text: string }> = [];
  nodes: TreeNode[] = [];
  reviews: Array<{ review: NotionReview; reveal: boolean }> = [];
  open: string | undefined;
  said: string[] = [];
  warned: string[] = [];
  reasonGiven: string | undefined = "Not these papers.";
  confirms = true;
  confirmed: string[] = [];

  count(count: number, text: string): void {
    this.counted.push({ count, text });
  }
  tree(nodes: TreeNode[]): void {
    this.nodes = nodes;
  }
  review(review: NotionReview, reveal: boolean): void {
    this.reviews.push({ review, reveal });
    this.open = review.batch.id;
  }
  reviewing(): string | undefined {
    return this.open;
  }
  async reason(): Promise<string | undefined> {
    return this.reasonGiven;
  }
  async confirm(text: string): Promise<boolean> {
    this.confirmed.push(text);
    return this.confirms;
  }
  info(text: string): void {
    this.said.push(text);
  }
  warn(text: string): void {
    this.warned.push(text);
  }
}

function setUp(): { api: FakeApi; presenter: FakePresenter; notion: NotionReviews } {
  const api = new FakeApi();
  const presenter = new FakePresenter();
  return { api, presenter, notion: new NotionReviews(presenter, () => NOW) };
}

function event(name: string, id = "nb-1"): ServerEvent {
  return { id: 7, name, data: { type: name, subject: { kind: "notion-batch", id } } } as ServerEvent;
}

test("the view lists each batch waiting, its databases and their entries, then the earlier ones", () => {
  const waiting = batch("nb-2", "partly written", [
    proposal("p1", "entry", "A third made-up paper"),
    proposal("p2", "change", "A made-up paper", {
      result: { written: false, partly: true, at: "x" },
      done: { parts: ["Year"], id: "lit-p2", url: "", edited: "" },
    }),
    proposal("p3", "removal", "Another made-up paper", { result: { written: false, error: "edited in Notion", at: "x" } }),
  ]);
  const nodes = treeOf([waiting], [brief(batch("nb-1", "written", [proposal("p1", "removal", "Gone")]))], NOW);
  assert.deepEqual(nodes.map((node) => [node.label, node.description]), [
    ["Batch nb-2's summary.", "partly written, 3 left · 10 minutes ago"],
    ["Earlier", "1"],
  ]);
  const [database] = nodes[0]!.children;
  assert.deepEqual([database!.label, database!.description, database!.open], [
    "Papers (test)", "1 new · 1 changed · 1 removed", { batch: "nb-2", database: "ds-lit" },
  ]);
  assert.deepEqual(database!.children.map((node) => [node.label, node.icon, node.description]), [
    ["A third made-up paper", "added", "new"],
    ["A made-up paper", "changed", "changed, written in part (Year)"],
    ["Another made-up paper", "failed", "removed, not written: edited in Notion"],
  ]);
  assert.deepEqual(database!.children[1]!.open, { batch: "nb-2", database: "ds-lit", proposal: "p2" });
  assert.deepEqual(nodes[1]!.children.map((node) => [node.label, node.icon, node.expanded]), [
    ["Batch nb-1's summary.", "done", false],
  ]);
  assert.equal(nodes[1]!.expanded, false);
});

test("the words of counts, times, the status bar and an approval", () => {
  assert.equal(countsText({ new: 2, changed: 0, removed: 1 }), "2 new · 1 removed");
  assert.equal(countsText({ new: 0, changed: 0, removed: 0 }), "nothing");
  assert.equal(when("2026-10-17T18:09:40Z", NOW), "just now");
  assert.equal(when("2026-10-17T17:10:00Z", NOW), "an hour ago");
  assert.equal(when("2026-10-15T08:00:00Z", NOW), "2026-10-15");
  assert.deepEqual(countItem(1, 1).text, "$(database) Notion: 1 change waiting");
  assert.match(countItem(3, 2).tooltip, /3 changes to your Notion, in 2 batches\. Nothing is written until you approve/);
  assert.equal(approvedText({ written: 2, failed: 1, left: 1 }),
    "Notion: 2 proposals written, 1 left staged; 1 could not be (the review says why).");
});

test("loading counts the proposals waiting and a batch submitted reads them again", async () => {
  const { api, presenter, notion } = setUp();
  api.batches = [batch("nb-1", "ready", [proposal("p1", "entry", "A paper"), proposal("p2", "change", "B paper")]),
    batch("nb-0", "open", [proposal("p1", "entry", "Staging")])];
  await notion.load(api);
  assert.deepEqual(presenter.counted.at(-1), { count: 2, text: "$(database) Notion: 2 changes waiting" });
  assert.deepEqual(presenter.nodes.map((node) => node.label), ["Batch nb-1's summary."], "an open batch is not shown");
  api.batches.unshift(batch("nb-2", "ready", [proposal("p1", "removal", "C paper")]));
  await notion.event(api, event("notion.staged", "nb-2"));
  assert.equal(presenter.counted.at(-1)?.count, 2, "staging is the agent's, not yet the owner's");
  await notion.event(api, event("notion.submitted", "nb-2"));
  assert.equal(presenter.counted.at(-1)?.count, 3);
  notion.disconnected();
  assert.deepEqual([presenter.counted.at(-1)?.count, presenter.nodes], [0, []]);
});

test("the review opens on an entry, shows every row when asked, and follows the batch while open", async () => {
  const { api, presenter, notion } = setUp();
  api.batches = [batch("nb-1", "ready", [proposal("p1", "entry", "A paper")])];
  await notion.load(api);
  await notion.open(api, { batch: "nb-1", database: "ds-lit", proposal: "p1" });
  const opened = presenter.reviews.at(-1)!;
  assert.deepEqual([opened.reveal, opened.review.select, opened.review.everything], [
    true, { database: "ds-lit", proposal: "p1" }, false,
  ]);
  assert.deepEqual(opened.review.tables, [TABLE]);
  await notion.rows(api, "nb-1", true);
  assert.deepEqual(api.asked.at(-1), { path: "notion/batches/nb-1/tables", parameters: { everything: true } });
  assert.equal(presenter.reviews.at(-1)!.reveal, false, "brought up to date, not opened again");
  api.batches[0]!.state = "written";
  await notion.event(api, event("notion.written"));
  assert.equal(presenter.reviews.at(-1)!.review.batch.state, "written", "the open review follows the batch");
  assert.equal(presenter.reviews.at(-1)!.review.everything, true, "and keeps showing every row");
});

test("approving all asks first and approving the checked parts sends them", async () => {
  const { api, presenter, notion } = setUp();
  api.batches = [batch("nb-1", "ready", [proposal("p1", "entry", "A paper"), proposal("p2", "change", "B paper")])];
  await notion.load(api);
  presenter.confirms = false;
  await notion.approve(api, "nb-1");
  assert.deepEqual([presenter.confirmed, api.posts], [["Write its 2 proposals to Notion now?"], []]);
  presenter.confirms = true;
  await notion.approve(api, "nb-1");
  assert.deepEqual(api.posts.at(-1), { path: "notion/batches/nb-1/approve", body: {} });
  assert.equal(presenter.said.at(-1), "Notion: 1 proposal written.");
  await notion.approve(api, "nb-1", { p2: ["Year"] });
  assert.deepEqual(api.posts.at(-1), { path: "notion/batches/nb-1/approve", body: { parts: { p2: ["Year"] } } });
  assert.equal(presenter.confirmed.length, 2, "what the owner checked is not asked again");
  await notion.approve(api, "nb-1", {});
  assert.equal(api.posts.length, 2, "nothing checked sends nothing");
  api.answer = { written: 0, failed: 1, left: 2 };
  await notion.approve(api, "nb-1", { p1: ["Title"] });
  assert.match(presenter.warned.at(-1)!, /could not be/);
});

test("a rejection sends the reason, and Escape keeps the batch waiting", async () => {
  const { api, presenter, notion } = setUp();
  api.batches = [batch("nb-1", "ready", [proposal("p1", "entry", "A paper")])];
  presenter.reasonGiven = undefined;
  await notion.reject(api, "nb-1");
  assert.deepEqual(api.posts, []);
  presenter.reasonGiven = "  Not these papers. ";
  await notion.reject(api, "nb-1");
  assert.deepEqual(api.posts, [{ path: "notion/batches/nb-1/reject", body: { reason: "Not these papers." } }]);
});

test("a service without Notion shows nothing", async () => {
  const { api, presenter, notion } = setUp();
  api.noNotion = true;
  await notion.load(api);
  assert.deepEqual([presenter.counted.at(-1)?.count, presenter.nodes, presenter.warned], [0, [], []]);
});

test("through the controller, the batches are read on connecting, followed with the events, and acted on", async () => {
  const { api, presenter: shown, notion } = setUp();
  api.batches = [batch("nb-1", "ready", [proposal("p1", "entry", "A paper")])];
  const presenter: Presenter = {
    clank: () => undefined,
    docker: () => undefined,
    ask: async () => undefined,
    pick: async () => undefined,
    info: () => undefined,
    warn: () => undefined,
  };
  const running = new Controller(presenter, () => api, { home: "/h", retryMs: 10, notion });
  const until = async (done: () => boolean): Promise<void> => {
    const deadline = Date.now() + 2000;
    while (!done() && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    assert.ok(done(), "never happened");
  };
  running.start();
  try {
    await until(() => shown.counted.at(-1)?.count === 1);
    api.batches.unshift(batch("nb-2", "ready", [proposal("p1", "removal", "B paper")]));
    api.send(event("notion.submitted", "nb-2"));
    await until(() => shown.counted.at(-1)?.count === 2);
    await running.notion((reviews, connected) => reviews.approve(connected, "nb-2", { p1: ["removal"] }));
    assert.deepEqual(api.posts.at(-1), { path: "notion/batches/nb-2/approve", body: { parts: { p1: ["removal"] } } });
  } finally {
    running.stop();
  }
});

function comment(id: string, extra: Partial<Comment> = {}): Comment {
  return {
    id, proposal: "p1", field: "Year", block: null, block_text: null, text: "Is it 2002?", by: "you",
    at: "2026-10-17T18:06:00Z", revision: 1, sent: false, state: "open", replies: [], ...extra,
  };
}

test("the owner comments, takes a comment back and sends the batch back, which stays listed but not counted", async () => {
  const { api, presenter, notion } = setUp();
  api.batches = [batch("nb-1", "ready", [proposal("p1", "change", "A paper")])];
  await notion.load(api);
  await notion.comment(api, "nb-1", { proposal: "p1", field: "Year" }, "Is it 2002?");
  assert.deepEqual(api.posts.at(-1), {
    path: "notion/batches/nb-1/comments", body: { proposal: "p1", field: "Year", text: "Is it 2002?" },
  });
  await notion.comment(api, "nb-1", {}, "   ");
  assert.equal(api.posts.length, 1, "a comment that says nothing is not sent");
  await notion.uncomment(api, "nb-1", "c1");
  assert.deepEqual(api.deleted, ["notion/batches/nb-1/comments/c1"]);
  await notion.sendBack(api, "nb-1");
  assert.equal(api.posts.at(-1)?.path, "notion/batches/nb-1/return");
  assert.match(presenter.said.at(-1)!, /sent back to the agent \(the session that staged it\)/);
  api.batches[0]!.state = "returned";
  api.batches[0]!.comments = [comment("c1", { sent: true })];
  await notion.event(api, event("notion.returned"));
  assert.equal(presenter.counted.at(-1)?.count, 0, "it waits for the agent, not for the owner");
  assert.deepEqual(presenter.nodes.map((node) => node.description), ["sent back, revision 1 · 1 comment open · 10 minutes ago"]);
});

test("approving while comments are unanswered asks first", async () => {
  const { api, presenter, notion } = setUp();
  api.batches = [batch("nb-1", "ready", [proposal("p1", "change", "A paper")], {
    comments: [comment("c1", { sent: true }), comment("c2", { state: "answered", sent: true })],
  })];
  await notion.load(api);
  presenter.confirms = false;
  await notion.approve(api, "nb-1", { p1: ["Year"] });
  assert.deepEqual([presenter.confirmed, api.posts], [["1 comment is not answered yet. Approve anyway?"], []]);
  presenter.confirms = true;
  await notion.approve(api, "nb-1");
  assert.deepEqual(presenter.confirmed.length, 2, "asked once, not again for approving all");
  assert.deepEqual(api.posts.at(-1), { path: "notion/batches/nb-1/approve", body: {} });
});
