// Design 0013 §10 and §14 step 7 (design 0007 §6): a question about a flow shows in VS Code as a gate, a notification
// with its answers and, for the files it shows, Open and Diff. The answer chosen is sent; one that takes words (send
// back's note, try again's) asks for them first, and Escape keeps the gate waiting and shows it again. Open opens the
// file in the folder, and the gate comes back once that file is saved (edit, then approve); Diff opens the last two
// tries' copies in VS Code's diff, and the gate comes back. A gate with one try offers no Diff; a question about a flow
// that no run names shows with its options alone. The controller gives every question about a flow to the gates, the
// Questions command's too, and never shows it as a plain notification; the Questions command (the status bar's count)
// shows a gate again even while its first notification waits unclicked in the notification center, and the gate is
// answered once, from whichever of them is clicked first. Design 0002 §2.5: a gate answered on another
// client is never shown again here, its diffs close, a save of its file brings nothing back, and a click on its
// notification still on screen (VS Code cannot close one), or a note written meanwhile, sends nothing and says who
// answered it; one answered while VS Code was not connected is closed when it connects again.

import assert from "node:assert/strict";
import { test } from "node:test";

import { Controller, type Api } from "../src/core/controller";
import type { ServerEvent } from "../src/core/events";
import {
  type GateAction,
  type GateButton,
  type GatePresenter,
  Gates,
  type Side,
  type Waited,
  type WaitedFile,
} from "../src/core/gates";
import type { Question } from "../src/core/kinds";
import type { Presenter } from "../src/core/presenter";

const FOLDER = "C:\\Work\\MyProject";
const PLAN = `${FOLDER}\\PLAN.md`;

function gateQuestion(id = "q-1"): Question {
  return {
    id,
    type: "choice",
    title: "Study: You approve the plan",
    detail: "The flow Study waits at You approve the plan.\n- PLAN.md",
    options: [
      { id: "approve", label: "Approve and go on", effect: "The next box starts.", key: "y", asks: null },
      { id: "back", label: "Send back with a note", effect: "plan runs try 3 of 3, its last,", key: "b", asks: null },
      { id: "stop", label: "Stop the flow", effect: "The run ends here.", key: "s", asks: null },
    ],
    default: null,
    expires: null,
    urgency: "normal",
    about: { kind: "flow", id: "myproject/study" },
    status: "waiting",
    asked: "2026-10-20T01:00:00.000Z",
    asked_by: { kind: "clank", via: "flow runner" },
    operation_id: null,
    answer: null,
    reason: "",
  };
}

function plainQuestion(id: string): Question {
  return { ...gateQuestion(id), title: "Stop Docker Desktop?", about: null };
}

function planFile(tries: number[] = [1, 2]): WaitedFile {
  return { path: "PLAN.md", file: PLAN, box: "plan", tries, exists: true };
}

function waited(id = "q-1", files: WaitedFile[] = [planFile()]): Waited {
  return {
    question: id,
    flow: "myproject/study",
    workspace: "myproject",
    name: "study",
    title: "Study",
    run: 1,
    box: "approve",
    box_title: "You approve the plan",
    type: "gate",
    kind: "gate",
    folder: FOLDER,
    files,
    notes: { back: "Your note for plan's next try: what to change (optional)." },
  };
}

/** The API, as a test sets it: what the flows wait for, the tries' copies, the questions; the posts it received. */
class FakeApi implements Api {
  waiting: Waited[] = [];
  copies = new Map<string, string>();
  questions: Question[] = [];
  copyReads: Array<Record<string, unknown>> = [];
  posts: Array<{ path: string; body: unknown }> = [];
  private queue: ServerEvent[] = [];
  private wake: (() => void) | undefined;

  async get<T>(path: string, parameters?: Record<string, string | number | boolean | undefined>): Promise<T> {
    if (path === "flows/waiting") {
      return { waiting: this.waiting } as T;
    }
    if (path === "flows/myproject/study/copy") {
      this.copyReads.push({ ...parameters });
      const text = this.copies.get(`${parameters?.["box"]}/${parameters?.["try"]}/${parameters?.["file"]}`);
      return { path: parameters?.["file"], try: parameters?.["try"], text } as T;
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

/** VS Code as the gates see it: each notification shown and the button the test clicks on it, what opened. */
class FakeGatePresenter implements GatePresenter {
  shown: Array<{ question: string; text: string; buttons: GateButton[] }> = [];
  /** The buttons clicked on the next notifications, by label (undefined: dismissed); none left: left on screen. */
  clicks: Array<string | undefined> = [];
  opened: Array<{ file: string; exists: boolean }> = [];
  diffs: Array<{ question: string; before: Side; after: Side; title: string }> = [];
  closed: string[] = [];
  words: Array<string | undefined> = [];
  asked: Array<{ title: string; prompt: string }> = [];
  picks: unknown[] = [];
  told: string[] = [];
  private held: Array<(action: GateAction | undefined) => void> = [];

  async gate(question: string, text: string, buttons: GateButton[]): Promise<GateAction | undefined> {
    this.shown.push({ question, text, buttons });
    if (!this.clicks.length) {
      return new Promise((resolve) => this.held.push(resolve)); // on screen until the test clicks it
    }
    const label = this.clicks.shift();
    return buttons.find((button) => button.label === label)?.action;
  }

  /** Click a button of a notification still waiting: the oldest, or the newest. */
  click(label: string, which: "oldest" | "newest" = "oldest"): void {
    const last = this.shown[this.shown.length - 1];
    const resolve = which === "oldest" ? this.held.shift() : this.held.pop();
    resolve?.(last?.buttons.find((button) => button.label === label)?.action);
  }

  async open(file: string, exists: boolean): Promise<void> {
    this.opened.push({ file, exists });
  }

  diff(question: string, before: Side, after: Side, title: string): void {
    this.diffs.push({ question, before, after, title });
  }

  closeDiffs(question: string): void {
    this.closed.push(question);
  }

  /** When set, a note is given only once it resolves (the owner still writing it). */
  writing: Promise<void> | undefined;

  async note(title: string, prompt: string): Promise<string | undefined> {
    this.asked.push({ title, prompt });
    await this.writing;
    return this.words.shift();
  }

  async pick<T>(items: Array<{ label: string; value: T }>): Promise<T | undefined> {
    const wanted = this.picks.shift();
    return items.find((item) => item.label === wanted)?.value;
  }

  info(text: string): void {
    this.told.push(text);
  }

  warn(text: string): void {
    this.told.push(`! ${text}`);
  }
}

function labels(shown: { buttons: GateButton[] } | undefined): string[] {
  return (shown?.buttons ?? []).map((button) => button.label);
}

async function until(holds: () => boolean, ms = 2000): Promise<void> {
  const deadline = Date.now() + ms;
  while (!holds()) {
    if (Date.now() > deadline) {
      throw new Error("never got there");
    }
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

function gates(presenter: FakeGatePresenter): Gates {
  return new Gates(presenter, { caseless: true });
}

test("a question about a flow shows as a gate with its answers, Open and Diff", async () => {
  const api = new FakeApi();
  api.waiting = [waited()];
  const presenter = new FakeGatePresenter();
  const shown = gates(presenter);
  await shown.load(api, [gateQuestion(), plainQuestion("q-2")]);
  await until(() => presenter.shown.length === 1);
  assert.equal(presenter.shown[0]?.question, "q-1", "a question about no flow is not the gates'");
  assert.match(presenter.shown[0]?.text ?? "", /^Study: You approve the plan\. The flow Study waits at/);
  assert.deepEqual(labels(presenter.shown[0]), [
    "Approve and go on",
    "Send back with a note",
    "Stop the flow",
    "Open PLAN.md",
    "Diff PLAN.md: try 1 and try 2",
  ]);
});

test("the answer chosen is sent", async () => {
  const api = new FakeApi();
  api.waiting = [waited()];
  const presenter = new FakeGatePresenter();
  presenter.clicks = ["Approve and go on"];
  await gates(presenter).load(api, [gateQuestion()]);
  await until(() => api.posts.length === 1);
  assert.deepEqual(api.posts, [{ path: "questions/q-1/answer", body: { option: "approve" } }]);
});

test("send back asks for the note and sends it, and Escape keeps the gate waiting and shows it again", async () => {
  const api = new FakeApi();
  api.waiting = [waited()];
  const presenter = new FakeGatePresenter();
  presenter.clicks = ["Send back with a note", "Send back with a note"];
  presenter.words = [undefined, "  Fewer grid points, as the brief says.  "];
  await gates(presenter).load(api, [gateQuestion()]);
  await until(() => api.posts.length === 1);
  assert.equal(presenter.shown.length, 2, "Escape on the note: the gate again");
  assert.deepEqual(presenter.asked[0], {
    title: "Study: You approve the plan: Send back with a note",
    prompt: "Your note for plan's next try: what to change (optional).",
  });
  assert.deepEqual(api.posts, [
    { path: "questions/q-1/answer", body: { option: "back", text: "Fewer grid points, as the brief says." } },
  ]);
});

test("Open opens the file in the folder, and the gate comes back once it is saved", async () => {
  const api = new FakeApi();
  api.waiting = [waited()];
  const presenter = new FakeGatePresenter();
  presenter.clicks = ["Open PLAN.md"];
  const shown = gates(presenter);
  await shown.load(api, [gateQuestion()]);
  await until(() => presenter.opened.length === 1);
  assert.deepEqual(presenter.opened, [{ file: PLAN, exists: true }]);
  await shown.saved(api, `${FOLDER}\\BRIEF.md`);
  assert.equal(presenter.shown.length, 1, "another file saved: nothing");
  await shown.saved(api, PLAN.toLowerCase());
  await until(() => presenter.shown.length === 2);
  assert.match(presenter.shown[1]?.text ?? "", /^PLAN\.md saved\. Study: You approve the plan\./);
  await shown.saved(api, PLAN);
  assert.equal(presenter.shown.length, 2, "the gate comes back once, not on every save");
});

test("a file a YOU box asks for, not written yet, opens as a new file at its place", async () => {
  const api = new FakeApi();
  const brief: WaitedFile = { path: "BRIEF.md", file: `${FOLDER}\\BRIEF.md`, box: "brief", tries: [], exists: false };
  api.waiting = [{ ...waited("q-1", [brief]), box: "brief", type: "you", kind: "you", notes: {} }];
  const presenter = new FakeGatePresenter();
  presenter.clicks = ["Open BRIEF.md"];
  await gates(presenter).load(api, [{ ...gateQuestion(), title: "Study: Brief: write BRIEF.md, then say it is done" }]);
  await until(() => presenter.opened.length === 1);
  assert.deepEqual(presenter.opened, [{ file: `${FOLDER}\\BRIEF.md`, exists: false }]);
  assert.ok(!labels(presenter.shown[0]).some((label) => label.startsWith("Diff")), "nothing to diff yet");
});

test("Diff opens the last two tries' copies in VS Code's diff, and the gate comes back", async () => {
  const api = new FakeApi();
  api.waiting = [waited("q-1", [planFile([1, 2, 3])])];
  api.copies.set("plan/2/PLAN.md", "# 240 points\n");
  api.copies.set("plan/3/PLAN.md", "# 60 points\n");
  const presenter = new FakeGatePresenter();
  presenter.clicks = ["Diff PLAN.md: try 2 and try 3"];
  await gates(presenter).load(api, [gateQuestion()]);
  await until(() => presenter.shown.length === 2);
  assert.deepEqual(api.copyReads, [
    { run: 1, box: "plan", file: "PLAN.md", try: 2 },
    { run: 1, box: "plan", file: "PLAN.md", try: 3 },
  ]);
  const [diff] = presenter.diffs;
  assert.equal(diff?.question, "q-1");
  assert.deepEqual(diff?.before, { key: "myproject/study/run-1/plan/try-2/PLAN.md", text: "# 240 points\n" });
  assert.deepEqual(diff?.after, { key: "myproject/study/run-1/plan/try-3/PLAN.md", text: "# 60 points\n" });
  assert.equal(diff?.title, "PLAN.md: try 2 and try 3 (plan, Study)");
});

test("a gate whose file has one try offers no Diff", async () => {
  const api = new FakeApi();
  api.waiting = [waited("q-1", [planFile([1])])];
  const presenter = new FakeGatePresenter();
  await gates(presenter).load(api, [gateQuestion()]);
  await until(() => presenter.shown.length === 1);
  assert.deepEqual(labels(presenter.shown[0]), [
    "Approve and go on",
    "Send back with a note",
    "Stop the flow",
    "Open PLAN.md",
  ]);
});

test("a gate showing several files picks the one to open and the one to diff", async () => {
  const api = new FakeApi();
  const grid: WaitedFile = { path: "grid.json", file: `${FOLDER}\\grid.json`, box: "T1", tries: [1, 2], exists: true };
  api.waiting = [waited("q-1", [planFile([1, 2]), grid])];
  api.copies.set("T1/1/grid.json", "[]\n");
  api.copies.set("T1/2/grid.json", "[1]\n");
  const presenter = new FakeGatePresenter();
  presenter.clicks = ["Open a file…", "Diff two tries…"];
  presenter.picks = ["grid.json", "grid.json"];
  const shown = gates(presenter);
  await shown.load(api, [gateQuestion()]);
  await until(() => presenter.opened.length === 1);
  assert.deepEqual(labels(presenter.shown[0]).slice(3), ["Open a file…", "Diff two tries…"]);
  assert.deepEqual(presenter.opened, [{ file: `${FOLDER}\\grid.json`, exists: true }]);
  await shown.saved(api, `${FOLDER}\\grid.json`);
  await until(() => presenter.diffs.length === 1);
  assert.equal(presenter.diffs[0]?.title, "grid.json: try 1 and try 2 (T1, Study)");
});

test("a question about a flow that no run names shows with its options alone", async () => {
  const api = new FakeApi();
  const presenter = new FakeGatePresenter();
  const proposals: Question = {
    ...gateQuestion("q-5"),
    title: "Study: Break it into tasks proposes 4 boxes",
    options: [
      { id: "accept_all", label: "Accept them all", effect: "", key: "A", asks: null },
      { id: "reject_all", label: "Reject them all", effect: "", key: "x", asks: null },
    ],
  };
  presenter.clicks = ["Accept them all"];
  await gates(presenter).load(api, [proposals]);
  await until(() => api.posts.length === 1);
  assert.deepEqual(labels(presenter.shown[0]), ["Accept them all", "Reject them all"]);
  assert.deepEqual(api.posts, [{ path: "questions/q-5/answer", body: { option: "accept_all" } }]);
});

/** The controller's own presenter: a plain question's notification, and the Questions command's picks. */
class FakePresenter implements Presenter {
  asked: Question[] = [];
  picks: unknown[] = [];
  clank(): void {}
  docker(): void {}
  async ask(asked: Question): Promise<string | undefined> {
    this.asked.push(asked);
    return undefined;
  }
  async pick<T>(items: Array<{ label: string; value: T }>): Promise<T | undefined> {
    const wanted = this.picks.shift();
    return items.find((item) => item.label === wanted)?.value;
  }
  info(): void {}
  warn(): void {}
}

test("the controller gives a question about a flow to the gates, never as a plain notification", async () => {
  const api = new FakeApi();
  api.waiting = [waited()];
  api.questions = [gateQuestion(), plainQuestion("q-2")];
  const plain = new FakePresenter();
  const presenter = new FakeGatePresenter();
  presenter.clicks = [undefined]; // dismissed
  const running = new Controller(plain, () => api, {
    home: "/h",
    retryMs: 10,
    now: () => 0,
    newKey: () => "k",
    gates: gates(presenter),
  });
  running.start();
  try {
    await until(() => presenter.shown.length === 1 && plain.asked.length === 1);
    assert.deepEqual(
      plain.asked.map((each) => each.id),
      ["q-2"],
    );
    plain.picks = ["Study: You approve the plan"];
    await running.questions();
    await until(() => presenter.shown.length === 2);
    assert.equal(presenter.shown[1]?.question, "q-1", "picked from the list: the gate, with Open and Diff");
    const subject = { kind: "question", id: "q-1" };
    api.send({ name: "question.asked", id: 50, data: { id: 50, type: "question.asked", subject } });
    await new Promise((resolve) => setTimeout(resolve, 50));
    assert.equal(presenter.shown.length, 2, "a gate asked again is not offered twice");
  } finally {
    running.stop();
  }
});

test("the status bar's count shows a gate again while its first notification still waits, unclicked", async () => {
  const api = new FakeApi();
  api.waiting = [waited()];
  api.questions = [gateQuestion()];
  const plain = new FakePresenter();
  const presenter = new FakeGatePresenter(); // no click: the notification waits, hidden in the notification center
  const running = new Controller(plain, () => api, {
    home: "/h",
    retryMs: 10,
    now: () => 0,
    newKey: () => "k",
    gates: gates(presenter),
  });
  running.start();
  try {
    await until(() => presenter.shown.length === 1);
    plain.picks = ["Study: You approve the plan"];
    await running.clicked();
    await until(() => presenter.shown.length === 2);
    assert.equal(presenter.shown[1]?.question, "q-1", "picked from the list: the gate again, with Open and Diff");
  } finally {
    running.stop();
  }
});

test("a gate shown again while its first notification waits is answered once, from either", async () => {
  const api = new FakeApi();
  api.waiting = [waited()];
  const presenter = new FakeGatePresenter();
  const shown = gates(presenter);
  await shown.load(api, [gateQuestion()]);
  await until(() => presenter.shown.length === 1);
  await shown.show(api, gateQuestion()); // the Questions command
  await until(() => presenter.shown.length === 2);
  presenter.click("Approve and go on", "newest");
  await until(() => api.posts.length === 1);
  await shown.event(api, answered("q-1", "you (vscode)"));
  presenter.click("Stop the flow", "oldest");
  await until(() => presenter.told.length === 1);
  assert.deepEqual(api.posts, [{ path: "questions/q-1/answer", body: { option: "approve" } }]);
  assert.deepEqual(presenter.told, ["you (vscode) answered q-1: Approve and go on: nothing was sent from here."]);
});

test("Diff brings the gate back even while an older notification of it still waits", async () => {
  const api = new FakeApi();
  api.waiting = [waited()];
  api.copies.set("plan/1/PLAN.md", "a\n");
  api.copies.set("plan/2/PLAN.md", "b\n");
  const presenter = new FakeGatePresenter();
  const shown = gates(presenter);
  await shown.load(api, [gateQuestion()]);
  await until(() => presenter.shown.length === 1);
  await shown.show(api, gateQuestion());
  await until(() => presenter.shown.length === 2);
  presenter.click("Diff PLAN.md: try 1 and try 2", "newest");
  await until(() => presenter.diffs.length === 1 && presenter.shown.length === 3);
  assert.equal(presenter.shown[2]?.question, "q-1");
});

function answered(id: string, by: string): ServerEvent {
  const summary = `${by} answered ${id}: Approve and go on`;
  const subject = { kind: "question", id };
  return { name: "question.answered", id: 60, data: { id: 60, type: "question.answered", summary, subject } };
}

test("a gate answered on the phone is never shown again here, and its notification says who answered it", async () => {
  const api = new FakeApi();
  api.waiting = [waited()];
  api.copies.set("plan/1/PLAN.md", "# 240 points\n");
  api.copies.set("plan/2/PLAN.md", "# 60 points\n");
  const presenter = new FakeGatePresenter();
  presenter.clicks = ["Diff PLAN.md: try 1 and try 2", "Open PLAN.md"];
  const shown = gates(presenter);
  await shown.load(api, [gateQuestion()]);
  await until(() => presenter.opened.length === 1 && presenter.diffs.length === 1);
  await shown.show(api, gateQuestion()); // the Questions command: on screen, not clicked yet
  await until(() => presenter.shown.length === 3);

  await shown.event(api, answered("q-1", "device (my phone)"));
  assert.deepEqual(presenter.closed, ["q-1"], "its diffs close");
  await shown.saved(api, PLAN);
  await shown.offer(api, gateQuestion());
  await shown.load(api, [gateQuestion()]);
  assert.equal(presenter.shown.length, 3, "never shown again: not after a save, nor when it is read again");

  presenter.click("Approve and go on");
  await until(() => presenter.told.length === 1);
  assert.deepEqual(presenter.told, ["device (my phone) answered q-1: Approve and go on: nothing was sent from here."]);
  assert.deepEqual(api.posts, [], "nothing sent");
});

test("a note written while the gate was answered elsewhere sends nothing", async () => {
  const api = new FakeApi();
  api.waiting = [waited()];
  const presenter = new FakeGatePresenter();
  let done = (): void => undefined;
  presenter.writing = new Promise<void>((resolve) => {
    done = resolve;
  });
  presenter.clicks = ["Send back with a note"];
  presenter.words = ["Fewer points."];
  const shown = gates(presenter);
  await shown.load(api, [gateQuestion()]);
  await until(() => presenter.asked.length === 1);
  await shown.event(api, answered("q-1", "you (console)"));
  done();
  await until(() => presenter.told.length === 1);
  assert.match(presenter.told[0] ?? "", /^you \(console\) answered q-1/);
  assert.deepEqual(api.posts, []);
});

test("a gate answered while VS Code was not connected is closed when it connects again", async () => {
  const api = new FakeApi();
  api.waiting = [waited()];
  api.copies.set("plan/1/PLAN.md", "a\n");
  api.copies.set("plan/2/PLAN.md", "b\n");
  const presenter = new FakeGatePresenter();
  presenter.clicks = ["Diff PLAN.md: try 1 and try 2"];
  const shown = gates(presenter);
  await shown.load(api, [gateQuestion()]);
  await until(() => presenter.diffs.length === 1 && presenter.shown.length === 2);
  await shown.load(api, []);
  assert.deepEqual(presenter.closed, ["q-1"]);
  presenter.click("Stop the flow");
  await until(() => presenter.told.length === 1);
  assert.deepEqual(api.posts, []);
  assert.match(presenter.told[0] ?? "", /was answered while VS Code was not connected/);
});
