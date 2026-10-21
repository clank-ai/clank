// Design 0007 §6: a change the agent asks for, in the window's folder, opens as a diff beside the files instead of a
// notification (one in another folder does not), and closes when its question is settled anywhere; Accept and Reject
// answer its question (a reject with the words given, none when Escape is pressed); a change settled while it is
// being opened never opens, and a tab left from before whose question no longer waits closes on loading; in auto mode a
// change made opens after it is made, unless the setting says not to; the status bar shows the mode and a click
// switches it.

import assert from "node:assert/strict";
import { test } from "node:test";

import { Controller, type Api } from "../src/core/controller";
import type { ServerEvent } from "../src/core/events";
import type { Question } from "../src/core/kinds";
import type { Presenter } from "../src/core/presenter";
import {
  type ChangeView,
  changeTitle,
  modeItem,
  type ReviewPresenter,
  Reviews,
  type ReviewView,
  within,
} from "../src/core/review";

const FOLDER = "C:\\Work\\MyProject";

function change(id: string, folder = FOLDER, extra: Partial<ChangeView> = {}): ChangeView {
  return {
    id,
    workspace: "myproject",
    relative: "src/sim.py",
    path: `${folder}\\src\\sim.py`,
    folder,
    before: "x = 1\n",
    after: "x = 2\n",
    made: null,
    diff: "--- a/src/sim.py\n+++ b/src/sim.py\n@@ -1 +1 @@\n-x = 1\n+x = 2\n",
    additions: 1,
    deletions: 1,
    created: false,
    exact: true,
    state: "waiting",
    mode: "review",
    problem: "",
    ...extra,
  };
}

function question(id: string, about: string | null): Question {
  return {
    id,
    type: "approval",
    title: "The agent of myproject wants to change src/sim.py (+1 -1)",
    detail: "",
    options: [
      { id: "accept", label: "Accept", effect: "", key: "y", asks: null },
      { id: "reject", label: "Reject", effect: "", key: "n", asks: null },
    ],
    default: null,
    expires: null,
    urgency: "normal",
    about: about ? { kind: "change", id: about } : null,
    status: "waiting",
    asked: "2026-10-15T15:00:00.000Z",
    asked_by: { kind: "clank", via: "review" },
    operation_id: null,
    answer: null,
    reason: "",
  };
}

/** The API, as a test sets it: the mode, the changes, the questions; the posts it received; events fed by hand. */
class FakeApi implements Api {
  view: ReviewView = { workspace: "myproject", mode: "review", waiting: 0, watching: true, problem: "" };
  changes = new Map<string, ChangeView>();
  questions: Question[] = [];
  note = "";
  posts: Array<{ path: string; body: unknown }> = [];
  /** When set, a change is read only once it resolves (a slow service). */
  hold: Promise<void> | undefined;
  private queue: ServerEvent[] = [];
  private wake: (() => void) | undefined;

  async get<T>(path: string, parameters?: Record<string, unknown>): Promise<T> {
    if (path === "agents/review") {
      assert.equal(String(parameters?.["folder"]).toLowerCase(), FOLDER.toLowerCase());
      return this.view as T;
    }
    if (path.startsWith("agents/changes/")) {
      await this.hold;
      return this.changes.get(decodeURIComponent(path.slice("agents/changes/".length))) as T;
    }
    const answers: Record<string, unknown> = {
      service: { version: "0.3.0", url: "http://127.0.0.1:7720", started: "", clients: [] },
      docker: { label: "Docker Desktop", state: "running", summary: "", containers: [] },
      questions: this.questions,
      history: [{ id: 41 }],
      "runtime/slots": [],
      "runtime/presets": [],
    };
    return answers[path] as T;
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    this.posts.push({ path, body });
    if (path === "agents/mode") {
      const mode = (body as { mode: "plan" | "review" | "auto" }).mode;
      this.view = {
        ...this.view,
        mode: mode === "plan" ? this.view.mode : mode,
        agent: mode === "plan" ? "planner" : "build",
        shown: mode,
      };
      return { ...this.view, ...(this.note ? { note: this.note } : {}) } as T;
    }
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

  send(event: ServerEvent): void {
    this.queue.push(event);
    this.wake?.();
  }
}

/** VS Code as the review sees it, recording what it was told. */
class FakeReviewPresenter implements ReviewPresenter {
  modeText = "";
  modeTip = "";
  shown = false;
  reviewing: Array<{ question: string; title: string }> = [];
  closed: string[] = [];
  restored: string[] = [];
  made: string[] = [];
  told: string[] = [];
  notes: Array<string | undefined> = [];

  mode(text: string, tooltip: string, shown: boolean): void {
    [this.modeText, this.modeTip, this.shown] = [text, tooltip, shown];
  }

  review(_change: ChangeView, question: string, title: string): void {
    this.reviewing.push({ question, title });
  }

  reviewed(question: string): void {
    this.closed.push(question);
  }

  openReviews(): string[] {
    return this.restored;
  }

  changed(_change: ChangeView, title: string): void {
    this.made.push(title);
  }

  async note(): Promise<string | undefined> {
    return this.notes.shift();
  }

  /** What the next mode pick chooses (by value); the items the last pick showed. */
  choose: string | undefined = undefined;
  shownItems: Array<{ label: string; detail?: string; value: unknown }> = [];

  async pick<T>(items: Array<{ label: string; detail?: string; value: T }>): Promise<T | undefined> {
    this.shownItems = items;
    if (this.choose !== undefined) {
      return items.find((each) => each.value === this.choose)?.value;
    }
    return items[0]?.value;
  }

  info(text: string): void {
    this.told.push(text);
  }

  warn(text: string): void {
    this.told.push(`! ${text}`);
  }
}

function reviews(presenter: FakeReviewPresenter, showInAuto = true): Reviews {
  return new Reviews(presenter, { folders: () => [FOLDER.toLowerCase()], showInAuto: () => showInAuto, caseless: true });
}

function event(name: string, data: unknown): ServerEvent {
  return { name, id: 50, data };
}

test("a change waiting in this window's folder opens beside the files, and closes when it is settled", async () => {
  const api = new FakeApi();
  api.changes.set("per_1", change("per_1"));
  api.changes.set("per_2", change("per_2", "C:\\Projects\\Other"));
  const presenter = new FakeReviewPresenter();
  const review = reviews(presenter);
  await review.load(api, [question("q-1", "per_1"), question("q-2", "per_2"), question("q-3", null)]);
  assert.deepEqual(presenter.reviewing, [{ question: "q-1", title: "Review: src/sim.py (+1 -1)" }]);
  assert.equal(presenter.modeText, "$(eye) Review");
  assert.equal(presenter.shown, true);
  await review.event(api, event("question.answered", { subject: { kind: "question", id: "q-1" } }));
  assert.deepEqual(presenter.closed, ["q-1"]);
  await review.event(api, event("question.withdrawn", { subject: { kind: "question", id: "q-2" } }));
  assert.deepEqual(presenter.closed, ["q-1"], "only what this window opened");
});

test("a change settled while it is being opened never opens: a quick answer leaves no tab", async () => {
  const api = new FakeApi();
  api.changes.set("per_1", change("per_1"));
  let release = (): void => undefined;
  api.hold = new Promise<void>((resolve) => {
    release = resolve;
  });
  const presenter = new FakeReviewPresenter();
  const review = reviews(presenter);
  const offered = review.offer(api, question("q-1", "per_1"));
  await review.event(api, event("question.answered", { subject: { kind: "question", id: "q-1" } }));
  release();
  await offered;
  assert.deepEqual(presenter.reviewing, []);
  await review.offer(api, question("q-1", "per_1"));
  assert.deepEqual(presenter.reviewing.length, 1, "a question asked again opens");
});

test("on loading, a change's tab left open whose question no longer waits closes", async () => {
  const api = new FakeApi();
  api.changes.set("per_1", change("per_1"));
  const presenter = new FakeReviewPresenter();
  presenter.restored = ["q-9", "q-1"];
  await reviews(presenter).load(api, [question("q-1", "per_1")]);
  assert.deepEqual(presenter.closed, ["q-9"]);
  assert.deepEqual(
    presenter.reviewing.map((each) => each.question),
    ["q-1"],
  );
});

test("accept answers the change's question; reject says why, and Escape keeps it waiting", async () => {
  const api = new FakeApi();
  api.changes.set("per_1", change("per_1"));
  const presenter = new FakeReviewPresenter();
  const review = reviews(presenter);
  await review.load(api, [question("q-1", "per_1")]);
  await review.accept(api);
  presenter.notes = [undefined, " keep the old name "];
  await review.reject(api, "q-1");
  await review.reject(api, "q-1");
  assert.deepEqual(api.posts, [
    { path: "questions/q-1/answer", body: { option: "accept" } },
    { path: "questions/q-1/answer", body: { option: "reject", text: "keep the old name" } },
  ]);
});

test("in auto mode a change made in this folder opens after it is made, unless the setting says not to", async () => {
  const api = new FakeApi();
  api.changes.set("per_7", change("per_7", FOLDER, { mode: "auto", made: "x = 3\n", state: "accepted" }));
  const made = (mode: string, folder = FOLDER): ServerEvent =>
    event("agents.change_made", { data: { change: "per_7", mode, folder, file: "src/sim.py" } });
  const presenter = new FakeReviewPresenter();
  await reviews(presenter).event(api, made("auto"));
  await reviews(presenter).event(api, made("review"));
  await reviews(presenter).event(api, made("auto", "C:\\Projects\\Other"));
  assert.deepEqual(presenter.made, ["Changed: src/sim.py (+1 -1)"]);
  const quiet = new FakeReviewPresenter();
  await reviews(quiet, false).event(api, made("auto"));
  assert.deepEqual(quiet.made, []);
});

test("a click on the mode offers Plan, Review and Auto with the current one marked, and the pick is posted", async () => {
  const api = new FakeApi();
  const presenter = new FakeReviewPresenter();
  const review = reviews(presenter);
  presenter.choose = "auto";
  await review.switchMode(api);
  assert.deepEqual(
    presenter.shownItems.map((each) => [each.label, each.detail]),
    [
      ["Plan", "the Planner: writes plans in Markdown, no code, no runs"],
      ["$(check) Review", "Build; you accept or reject each change"],
      ["Auto", "Build; changes are made without asking"],
    ],
  );
  assert.deepEqual(api.posts, [{ path: "agents/mode", body: { workspace: "myproject", mode: "auto" } }]);
  assert.equal(presenter.modeText, "$(zap) Auto");
  assert.match(presenter.modeTip, /changes files without asking/);
  assert.match(presenter.modeTip, /Tab in OpenCode switches Build and Planner too/);
  assert.deepEqual(presenter.told, [], "no note, nothing said");
  presenter.choose = "plan";
  api.note = "No OpenCode runs in a window: the change rule is set anyway.";
  await review.switchMode(api);
  assert.equal(presenter.modeText, "$(note) Plan");
  assert.deepEqual(presenter.told, [api.note]);
  assert.equal(review.view?.mode, "auto", "the mode stays what it was while the Planner shows");
  presenter.choose = "review";
  await review.switchMode(api);
  assert.match(presenter.shownItems[0]!.label, /check/, "Plan is marked while the Planner shows");
  assert.equal(presenter.modeText, "$(eye) Review");
});

test("a pick dismissed posts nothing, and the status bar shows Plan only when the service says shown is plan", async () => {
  const api = new FakeApi();
  const presenter = new FakeReviewPresenter();
  presenter.choose = "nothing";
  await reviews(presenter).switchMode(api);
  assert.deepEqual(api.posts, []);
  for (const [shown, text] of [
    ["plan", "$(note) Plan"],
    ["review", "$(eye) Review"],
    ["auto", "$(zap) Auto"],
  ] as const) {
    const view: ReviewView = { workspace: "w", mode: "auto", agent: null, shown, waiting: 0, watching: true, problem: "" };
    assert.equal(modeItem(view).text, text);
  }
  assert.equal(modeItem({ workspace: "w", mode: "auto", waiting: 0, watching: true, problem: "" }).text, "$(zap) Auto");
});

test("the status bar follows the mode, agent and review events of the service", async () => {
  const api = new FakeApi();
  const presenter = new FakeReviewPresenter();
  const review = reviews(presenter);
  await review.load(api, []);
  assert.equal(presenter.modeText, "$(eye) Review");
  for (const name of ["agents.mode_switched", "agents.agent_seen"]) {
    api.view = { ...api.view, agent: "planner", shown: "plan" };
    await review.event(api, event(name, { data: { workspace: "myproject" } }));
    assert.equal(presenter.modeText, "$(note) Plan", name);
    api.view = { ...api.view, agent: "build", shown: "review" };
    await review.event(api, event(name, {}));
    assert.equal(presenter.modeText, "$(eye) Review", name);
  }
  api.view = { workspace: null, mode: "review", waiting: 0, watching: false, problem: "" };
  await review.event(api, event("agents.review_switched", {}));
  assert.equal(presenter.shown, false, "a folder without a workspace shows no mode");
});

test("the mode's tooltip says what waits and why the agent is not followed", () => {
  const view: ReviewView = { workspace: "paper", mode: "review", waiting: 2, watching: false, problem: "older image" };
  assert.match(modeItem(view).tooltip, /asks before it changes a file.*2 changes wait\. Not followed here now: older image\./);
  assert.equal(changeTitle(change("per_1", FOLDER, { created: true }), false), "Review: src/sim.py (new file)");
  assert.equal(changeTitle(change("per_1", FOLDER, { deletions: 0 }), true), "Changed: src/sim.py (+1)");
  assert.equal(within("C:\\Work\\MyProject\\src\\a.py", "c:/work/myproject/", true), true);
  assert.equal(within("C:\\Work\\MyProject-old", "C:\\Work\\MyProject", true), false);
});

test("the controller gives a question about a change to the review, not to a notification", async () => {
  const api = new FakeApi();
  api.changes.set("per_1", change("per_1"));
  api.questions = [question("q-1", "per_1")];
  const asked: Question[] = [];
  const presenter: Presenter = {
    clank: () => undefined,
    docker: () => undefined,
    ask: async (each) => {
      asked.push(each);
      return undefined;
    },
    pick: async () => undefined,
    info: () => undefined,
    warn: () => undefined,
  };
  const shown = new FakeReviewPresenter();
  const running = new Controller(presenter, () => api, { home: "/h", retryMs: 10, reviews: reviews(shown) });
  running.start();
  try {
    const deadline = Date.now() + 2000;
    while (!shown.reviewing.length && Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 5));
    }
    assert.deepEqual(shown.reviewing.map((each) => each.question), ["q-1"]);
    assert.deepEqual(asked, []);
  } finally {
    running.stop();
  }
});
