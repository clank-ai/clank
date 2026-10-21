// The Notion changes in VS Code (design 0010 §6): the batches of proposals the local agent submitted for Notion, in a
// view of their own (each batch waiting, its databases, their entries marked new, changed or removed; the batches
// written or rejected under "Earlier"), the count of the proposals waiting in the status bar and on the view's icon, and
// the review page of a batch (`notion.ts` beside `extension.ts` shows it): the tables of its databases (`GET
// notion/batches/<id>/tables`), each entry's fields and page. The owner approves all of a batch, or the rows and
// fields they checked on the page (`parts`); what is unchecked stays staged. A rejection asks for the reason. The owner
// comments on the batch, an entry, a property or a block of a page (§7), takes back a comment not sent, and sends the
// batch back to its agent with the comments; a batch sent back stays in the view, waiting for the agent's revision.
// Approving while comments are unanswered asks first. The view and the page follow the service's events, so a batch
// submitted, written, rejected, commented on or answered anywhere shows here at once.
// Like the review of changes (`review.ts`), it speaks to VS Code only through its presenter, so it is tested without
// VS Code; a service without Notion (`GET notion/batches` refused) shows nothing.

import type { Api } from "./controller";
import type { ServerEvent } from "./events";

/** A batch in brief, as `GET /api/v1/notion/batches` gives it. */
export interface BatchBrief {
  id: string;
  workspace: string;
  state: string;
  summary: string;
  revision: number;
  created: string;
  updated: string;
  counts: { new: number; changed: number; removed: number };
  databases: string[];
  left?: number;
  comment_counts?: { all: number; open: number; unsent: number };
}

/** The owner's comment on a batch, and the agent's answers. */
export interface Comment {
  id: string;
  proposal: string | null;
  field: string | null;
  block: number | null;
  block_text: string | null;
  text: string;
  by: string;
  at: string;
  revision: number;
  sent: boolean;
  state: "open" | "answered";
  replies: Array<{ text: string; by: string; at: string }>;
}

/** What a comment is on: the batch (nothing given), a proposal, a property of it, or a block of its page. */
export interface Place {
  proposal?: string;
  field?: string;
  block?: number;
}

/** A property a proposal sets: what it was and what it would be, as text. */
export interface Field {
  name: string;
  was: string;
  now: string;
}

/** A block of a changed page against the page now (`writing.page_changes`). */
export interface PageChange {
  op: "keep" | "remove" | "add" | "update";
  markdown: string;
  was?: string;
}

/** A proposal of a batch, as the service keeps it. */
export interface Proposal {
  id: string;
  kind: "entry" | "change" | "removal";
  database: string;
  database_name: string;
  page: string | null;
  title: string;
  fields: Field[];
  notes: string[];
  markdown: string | null;
  changes: PageChange[] | null;
  base: { properties: Record<string, string>; markdown: string; edited: string } | null;
  why: string;
  sources: string[];
  done?: { parts: string[]; id: string; url: string; edited: string } | null;
  result: { written: boolean; partly?: boolean; error?: string; url?: string; at: string } | null;
  revision?: number;
  previous?: { fields?: Field[]; markdown?: string | null } | null;
}

/** A batch, whole, as `GET /api/v1/notion/batches/<id>` gives it. */
export interface Batch extends BatchBrief {
  proposals: Proposal[];
  reason?: string;
  comments?: Comment[];
}

/** A cell of a table: the value as text, and what it was when the proposal sets it. */
export interface Cell {
  text: string;
  was?: string;
}

/** A row of a table: an entry, marked with the proposal about it. */
export interface Row {
  id: string | null;
  title: string;
  url: string;
  mark: "same" | "added" | "changed" | "removed";
  proposal: string | null;
  cells: Record<string, Cell>;
}

/** A database of a batch as a table, as `GET /api/v1/notion/batches/<id>/tables` gives it. */
export interface Table {
  database: string;
  name: string;
  columns: string[];
  rows: Row[];
  shared: boolean;
}

/** What the review page is given: the batch, its tables, whether every row is shown, and what to show first. */
export interface NotionReview {
  batch: Batch;
  tables: Table[];
  everything: boolean;
  select?: { database?: string; proposal?: string };
}

/** Where a node of the view opens the review: a batch, maybe one of its databases or proposals. */
export interface Opening {
  batch: string;
  database?: string;
  proposal?: string;
}

/** A node of the Notion changes view. */
export interface TreeNode {
  id: string;
  label: string;
  description: string;
  tooltip: string;
  icon: "batch" | "database" | "added" | "changed" | "removed" | "written" | "failed" | "earlier" | "done" | "rejected";
  context: "notion.batch" | "notion.database" | "notion.entry" | "notion.earlier" | "notion.done";
  open?: Opening;
  children: TreeNode[];
  expanded: boolean;
}

/** VS Code, as the Notion review sees it. */
export interface NotionPresenter {
  /** The status bar's item and the view's badge: their text and tooltip, or hidden (a count of 0). */
  count(count: number, text: string, tooltip: string): void;
  /** The Notion changes view's nodes. */
  tree(nodes: TreeNode[]): void;
  /** Show a batch's review: its page opened (`reveal`), or the page already open brought up to date. */
  review(review: NotionReview, reveal: boolean): void;
  /** The batch the review page shows, when it is open. */
  reviewing(): string | undefined;
  /** Ask why a batch is rejected: the words, or undefined to keep it waiting. */
  reason(): Promise<string | undefined>;
  /** Ask before doing something to Notion: whether the owner chose the action. */
  confirm(text: string, action: string): Promise<boolean>;
  info(text: string): void;
  warn(text: string): void;
}

const WAITING = new Set(["ready", "partly written"]);
const SHOWN = new Set([...WAITING, "returned"]); // a batch sent back waits for the agent, shown with the others
const EARLIER = 20; // the batches written or rejected the view keeps under "Earlier"
const FOLLOWED = new Set([
  "notion.submitted",
  "notion.written",
  "notion.rejected",
  "notion.commented",
  "notion.uncommented",
  "notion.returned",
  "notion.replied",
]);
const MARKS = { entry: "added", change: "changed", removal: "removed" } as const;
const KINDS = { entry: "new", change: "changed", removal: "removed" } as const;

/** Whether a batch waits for the owner. */
export function waits(batch: BatchBrief): boolean {
  return WAITING.has(batch.state);
}

/** Whether a batch is shown with those waiting: waiting for the owner, or sent back to the agent. */
export function listed(batch: BatchBrief): boolean {
  return SHOWN.has(batch.state);
}

/** How many proposals of these batches wait for the owner. */
export function waitingCount(batches: BatchBrief[]): number {
  return batches.filter(waits).reduce((sum, batch) => sum + (batch.left ?? 0), 0);
}

/** The status bar's item for a count of proposals waiting. */
export function countItem(count: number, batches: number): { text: string; tooltip: string } {
  const changes = count === 1 ? "1 change" : `${count} changes`;
  const from = batches === 1 ? "one batch" : `${batches} batches`;
  return {
    text: `$(database) Notion: ${changes} waiting`,
    tooltip: `The local agent proposes ${changes} to your Notion, in ${from}. Nothing is written until you approve it: click to review.`,
  };
}

/** A batch's counts, as words: "1 new · 2 changed · 1 removed". */
export function countsText(counts: { new: number; changed: number; removed: number }): string {
  const named = [
    counts.new ? `${counts.new} new` : "",
    counts.changed ? `${counts.changed} changed` : "",
    counts.removed ? `${counts.removed} removed` : "",
  ];
  return named.filter(Boolean).join(" · ") || "nothing";
}

/** When something happened, said from now: "just now", "5 minutes ago", "3 hours ago", else its day. */
export function when(at: string, now: number): string {
  const moment = Date.parse(at);
  if (Number.isNaN(moment)) {
    return "";
  }
  const minutes = Math.round((now - moment) / 60_000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return minutes === 1 ? "a minute ago" : `${minutes} minutes ago`;
  }
  const hours = Math.round(minutes / 60);
  if (hours < 24) {
    return hours === 1 ? "an hour ago" : `${hours} hours ago`;
  }
  return new Date(moment).toISOString().slice(0, 10);
}

/** What a proposal's result says, for the view: written, written in part, why not, or nothing yet. */
export function resultText(proposal: Proposal): string {
  const result = proposal.result;
  if (!result) {
    return "";
  }
  if (result.error) {
    return `not written: ${result.error}`;
  }
  return result.written ? "written to Notion" : `written in part (${(proposal.done?.parts ?? []).join(", ")})`;
}

/** The view's nodes: each batch waiting (its databases, their entries), then "Earlier" with those written or
 * rejected. */
export function treeOf(waiting: Batch[], earlier: BatchBrief[], now: number): TreeNode[] {
  const nodes = waiting.map((batch) => batchNode(batch, now));
  if (earlier.length) {
    nodes.push({
      id: "earlier",
      label: "Earlier",
      description: String(earlier.length),
      tooltip: "Batches written to Notion or rejected.",
      icon: "earlier",
      context: "notion.earlier",
      expanded: false,
      children: earlier.map((batch) => ({
        id: `done:${batch.id}`,
        label: batch.summary || batch.id,
        description: `${batch.state} · ${when(batch.updated, now)}`,
        tooltip: `${batch.summary}\n${batch.id}, from ${batch.workspace}: ${countsText(batch.counts)}; ${batch.state}.`,
        icon: batch.state === "rejected" ? "rejected" : "done",
        context: "notion.done",
        open: { batch: batch.id },
        children: [],
        expanded: false,
      })),
    });
  }
  return nodes;
}

function batchNode(batch: Batch, now: number): TreeNode {
  const databases = [...new Set(batch.proposals.map((proposal) => proposal.database))];
  const left = batch.left ?? batch.proposals.length;
  const state =
    batch.state === "returned"
      ? `sent back, revision ${batch.revision}`
      : batch.state === "partly written"
        ? `partly written, ${left} left`
        : `${left} waiting`;
  const open = (batch.comments ?? []).filter((each) => each.state === "open").length;
  const comments = open === 1 ? " · 1 comment open" : open ? ` · ${open} comments open` : "";
  return {
    id: `batch:${batch.id}`,
    label: batch.summary || `Batch ${batch.id}`,
    description: `${state}${comments} · ${when(batch.created, now)}`,
    tooltip:
      `${batch.summary}\n\nStaged by the agent of ${batch.workspace}, ${when(batch.created, now)} ` +
      `(${batch.id}, revision ${batch.revision}): ${countsText(batch.counts)}. Nothing reaches Notion until you approve it.`,
    icon: "batch",
    context: "notion.batch",
    open: { batch: batch.id },
    expanded: true,
    children: databases.map((database) => {
      const proposals = batch.proposals.filter((proposal) => proposal.database === database);
      const counts = {
        new: proposals.filter((each) => each.kind === "entry").length,
        changed: proposals.filter((each) => each.kind === "change").length,
        removed: proposals.filter((each) => each.kind === "removal").length,
      };
      const name = proposals[0]?.database_name ?? database;
      return {
        id: `database:${batch.id}:${database}`,
        label: name,
        description: countsText(counts),
        tooltip: `${name}: ${countsText(counts)}. Click to review its table.`,
        icon: "database" as const,
        context: "notion.database" as const,
        open: { batch: batch.id, database },
        expanded: true,
        children: proposals.map((proposal) => entryNode(batch, proposal)),
      };
    }),
  };
}

function entryNode(batch: Batch, proposal: Proposal): TreeNode {
  const result = resultText(proposal);
  const icon = proposal.result?.error ? "failed" : proposal.result?.written ? "written" : MARKS[proposal.kind];
  return {
    id: `entry:${batch.id}:${proposal.id}`,
    label: proposal.title,
    description: result ? `${KINDS[proposal.kind]}, ${result}` : KINDS[proposal.kind],
    tooltip: `${proposal.title} (${KINDS[proposal.kind]}, ${proposal.id}): ${proposal.why}${result ? `\n${result}` : ""}`,
    icon,
    context: "notion.entry",
    open: { batch: batch.id, database: proposal.database, proposal: proposal.id },
    children: [],
    expanded: false,
  };
}

/** The approval's words: what was written, what is left, and what could not be. */
export function approvedText(answer: { written: number; failed: number; left: number }): string {
  const written = answer.written === 1 ? "1 proposal written" : `${answer.written} proposals written`;
  const left = answer.left ? `, ${answer.left} left staged` : "";
  const failed = answer.failed ? `; ${answer.failed} could not be (the review says why)` : "";
  return `Notion: ${written}${left}${failed}.`;
}

/** The Notion review in this window. */
export class NotionReviews {
  private waiting: Batch[] = [];
  private earlier: BatchBrief[] = [];
  private readonly everything = new Map<string, boolean>();

  constructor(
    private readonly presenter: NotionPresenter,
    private readonly now: () => number = Date.now,
  ) {}

  /** On connecting: the batches read, the view and the count drawn, an open review brought up to date. */
  async load(api: Api): Promise<void> {
    await this.refresh(api);
  }

  /** An event: a batch submitted, written or rejected reads the batches again (and the review showing it). */
  async event(api: Api, message: ServerEvent): Promise<void> {
    if (FOLLOWED.has(message.name)) {
      await this.refresh(api);
    }
  }

  /** Not connected: nothing to show. */
  disconnected(): void {
    this.waiting = [];
    this.earlier = [];
    this.draw();
  }

  /** Open a batch's review, showing a database or a proposal first. */
  async open(api: Api, opening: Opening): Promise<void> {
    const review = await this.read(api, opening.batch, opening);
    if (review) {
      this.presenter.review(review, true);
    }
  }

  /** Show every row of a batch's tables, or only the changed ones and their neighbors. */
  async rows(api: Api, batch: string, everything: boolean): Promise<void> {
    this.everything.set(batch, everything);
    const review = await this.read(api, batch);
    if (review) {
      this.presenter.review(review, false);
    }
  }

  /** Approve a batch: every proposal not written (asked first), or the parts checked on its page; with comments not
   * answered, asked first either way. */
  async approve(api: Api, batch: string, parts?: Record<string, string[]>): Promise<void> {
    const found = this.waiting.find((each) => each.id === batch);
    const open = (found?.comments ?? []).filter((each) => each.state === "open").length;
    if (open && (parts === undefined || Object.keys(parts).length)) {
      const said = open === 1 ? "1 comment is not answered" : `${open} comments are not answered`;
      if (!(await this.presenter.confirm(`${said} yet. Approve anyway?`, "Approve anyway"))) {
        return;
      }
    } else if (parts === undefined) {
      const found = this.waiting.find((each) => each.id === batch);
      const left = found?.left ?? found?.proposals.length ?? 0;
      const what = left === 1 ? "its proposal" : `its ${left} proposals`;
      if (!(await this.presenter.confirm(`Write ${what} to Notion now?`, "Approve all"))) {
        return;
      }
    } else if (!Object.keys(parts).length) {
      this.presenter.info("Nothing is checked: check the rows or fields to write.");
      return;
    }
    try {
      const answer = await api.post<{ written: number; failed: number; left: number }>(
        `notion/batches/${encodeURIComponent(batch)}/approve`,
        parts === undefined ? {} : { parts },
      );
      (answer.failed ? this.presenter.warn : this.presenter.info).call(this.presenter, approvedText(answer));
    } catch (error) {
      this.presenter.warn(words(error));
    }
    await this.refresh(api);
  }

  /** Comment on a batch, an entry, a property or a block, for its agent. */
  async comment(api: Api, batch: string, place: Place, text: string): Promise<void> {
    if (!text.trim()) {
      return;
    }
    await this.act(api, () => api.post(`notion/batches/${encodeURIComponent(batch)}/comments`, { ...place, text }));
  }

  /** Take back a comment not sent to the agent yet. */
  async uncomment(api: Api, batch: string, comment: string): Promise<void> {
    await this.act(api, async () => {
      if (!api.delete) {
        throw new Error("this connection cannot take back a comment");
      }
      await api.delete(`notion/batches/${encodeURIComponent(batch)}/comments/${encodeURIComponent(comment)}`);
    });
  }

  /** Send a batch back to its agent with the comments not sent yet. */
  async sendBack(api: Api, batch: string): Promise<void> {
    await this.act(api, async () => {
      const answer = await api.post<{ sent_to: { session: string; new: boolean } }>(
        `notion/batches/${encodeURIComponent(batch)}/return`,
      );
      const where = answer.sent_to.new ? "a new session in OpenCode's window" : "the session that staged it";
      this.presenter.info(`Notion: the batch is sent back to the agent (${where}); its revision comes back here.`);
    });
  }

  /** Reject a batch with the reason asked for (Escape keeps it waiting). */
  async reject(api: Api, batch: string): Promise<void> {
    const reason = await this.presenter.reason();
    if (reason === undefined) {
      return;
    }
    try {
      await api.post(`notion/batches/${encodeURIComponent(batch)}/reject`, { reason: reason.trim() });
      this.presenter.info("Notion: the batch is rejected, and nothing of it is written.");
    } catch (error) {
      this.presenter.warn(words(error));
    }
    await this.refresh(api);
  }

  private async refresh(api: Api): Promise<void> {
    let briefs: BatchBrief[];
    try {
      briefs = (await api.get<{ batches: BatchBrief[] }>("notion/batches")).batches;
    } catch {
      this.disconnected(); // a service without Notion
      return;
    }
    const waiting: Batch[] = [];
    for (const brief of briefs.filter(listed)) {
      try {
        waiting.push({ ...(await api.get<Batch>(`notion/batches/${encodeURIComponent(brief.id)}`)), left: brief.left });
      } catch {
        // gone since it was listed
      }
    }
    this.waiting = waiting;
    this.earlier = briefs.filter((brief) => !listed(brief) && brief.state !== "open").slice(0, EARLIER);
    this.draw();
    const shown = this.presenter.reviewing();
    if (shown !== undefined) {
      const review = await this.read(api, shown);
      if (review) {
        this.presenter.review(review, false);
      }
    }
  }

  private async act(api: Api, work: () => Promise<unknown>): Promise<void> {
    try {
      await work();
    } catch (error) {
      this.presenter.warn(words(error));
    }
    await this.refresh(api);
  }

  private async read(api: Api, batch: string, select?: Opening): Promise<NotionReview | undefined> {
    const everything = this.everything.get(batch) ?? false;
    try {
      const whole = await api.get<Batch>(`notion/batches/${encodeURIComponent(batch)}`);
      const tables = await api.get<{ tables: Table[] }>(`notion/batches/${encodeURIComponent(batch)}/tables`, {
        everything,
      });
      const chosen = select && { database: select.database, proposal: select.proposal };
      return { batch: whole, tables: tables.tables, everything, ...(chosen ? { select: chosen } : {}) };
    } catch (error) {
      this.presenter.warn(words(error));
      return undefined;
    }
  }

  private draw(): void {
    const count = waitingCount(this.waiting);
    const { text, tooltip } = countItem(count, this.waiting.length);
    this.presenter.count(count, text, tooltip);
    this.presenter.tree(treeOf(this.waiting, this.earlier, this.now()));
  }
}

function words(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
