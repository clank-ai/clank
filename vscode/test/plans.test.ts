// Design 0009 §7, §8: a Markdown file whose header says `kind: plan` (the same cases as Clank's own `is_plan` and
// `plan_path`) gets Implement with Review and Implement with Auto, and Continue when some of its checklist is done;
// the requests that hand the plan to the agent name the workspace, the plan's path in its folder with `/`, and the mode;
// a plan that is not saved is saved first; no OpenCode in a window offers to open the agent and tries once more.

import assert from "node:assert/strict";
import { test } from "node:test";

import { ClankError } from "../src/core/client";
import {
  implement,
  isPlan,
  lenses,
  type ImplementPresenter,
  planPath,
  relativePlan,
  stepCounts,
} from "../src/core/plans";

test("a header that says kind: plan makes a plan, and anything else is not one", () => {
  for (const text of [
    "---\nkind: plan\n---\n# A study\n",
    "---\ntitle: Walk scan\nkind: plan\nstatus: draft\n---\n\n## Question\n",
    "---\r\nkind: plan\r\nstatus: ready\r\n---\r\n# On Windows\r\n",
    "---\nkind:   plan  \n---\n",
    "---\nkind: plan\n---",
    "--- \nkind: plan\n---  \n",
  ]) {
    assert.equal(isPlan(text), true, JSON.stringify(text));
  }
  for (const text of [
    null,
    undefined,
    "",
    "# Notes\n\nkind: plan\n",
    "---\nkind: plan\n# the header never closes\n",
    "---\nkind: plans\n---\n",
    "---\nkind: study\n---\n",
    "---\ntitle: x\n---\n\n---\nkind: plan\n---\n",
    "\n---\nkind: plan\n---\n",
    "----\nkind: plan\n----\n",
  ]) {
    assert.equal(isPlan(text), false, JSON.stringify(text));
  }
});

test("no file is a plan outside the folder, in a settings folder, or among the files that instruct agents", () => {
  for (const relative of ["plan.md", "studies/2026-10-20-sweep/plan.md", "notes/Draft.MD"]) {
    assert.equal(planPath(relative), true, relative);
  }
  for (const relative of [
    "",
    "a.py",
    "plan.md.py",
    "/plan.md",
    "../plan.md",
    "a/../../plan.md",
    ".opencode/agent/helper.md",
    "sub/.opencode/command/go.md",
    ".claude/skills/s/SKILL.md",
    ".git/description.md",
    ".github/pull_request_template.md",
    ".vscode/notes.md",
    "AGENTS.md",
    "sub/agents.md",
    "CLAUDE.md",
  ]) {
    assert.equal(planPath(relative), false, relative);
  }
});

test("the checklist counts - [x] and - [X] as done and - [ ] as not, and Continue needs some done", () => {
  const plan = "---\nkind: plan\n---\n- [x] one\n- [X] two\n  - [ ] three\n* [ ] four\nnot a - [x] item\n- [] five\n";
  assert.deepEqual(stepCounts(plan), { done: 2, total: 4 });
  assert.deepEqual(
    lenses(plan).map((each) => [each.title, each.command]),
    [
      ["\u25B6 Implement with Review", "clank.implementReview"],
      ["\u25B6 Implement with Auto", "clank.implementAuto"],
      ["\u21BB Continue (2 of 4 steps done)", "clank.implementContinue"],
    ],
  );
  const fresh = "---\nkind: plan\n---\n- [ ] one\n- [ ] two\n";
  assert.deepEqual(
    lenses(fresh).map((each) => each.command),
    ["clank.implementReview", "clank.implementAuto"],
    "nothing done: no Continue",
  );
  assert.equal(lenses("---\r\nkind: plan\r\n---\r\n").length, 2, "no checklist: no Continue");
  assert.deepEqual(lenses("# Not a plan\n- [x] done\n"), []);
});

test("the plan's path is relative to the workspace folder with / between parts", () => {
  assert.equal(relativePlan("C:\\Projects\\Paper\\studies\\x\\plan.md", "c:\\projects\\paper", true), "studies/x/plan.md");
  assert.equal(relativePlan("/srv/work/paper/plan.md", "/srv/work/paper/", false), "plan.md");
  assert.equal(relativePlan("/srv/work/paper-old/plan.md", "/srv/work/paper", false), undefined);
  assert.equal(relativePlan("/srv/work/Paper/plan.md", "/srv/work/paper", false), undefined);
});

/** The service, as implementing a plan sees it. */
class FakeService {
  posts: Array<{ path: string; body: unknown }> = [];
  gets: Array<{ path: string; parameters: unknown }> = [];
  failures: Error[] = [];
  view = { problem: "", workspace: "paper" as string | null };
  /** What each look at the workspace's OpenCode servers finds, in turn; once they are used up, a window. */
  servers: Array<Array<{ port: number; terminal: boolean }>> = [];

  async get<T>(path: string, parameters?: Record<string, unknown>): Promise<T> {
    this.gets.push({ path, parameters });
    if (path === "agents/sessions") {
      return { servers: this.servers.shift() ?? [{ port: 4096, terminal: true }] } as T;
    }
    return this.view as T;
  }

  async post<T>(path: string, body?: unknown): Promise<T> {
    this.posts.push({ path, body });
    const failure = this.failures.shift();
    if (failure) {
      throw failure;
    }
    return { workspace: "paper", port: 4096, session: "s1" } as T;
  }
}

class FakePresenter implements ImplementPresenter {
  said: string[] = [];
  steps: string[] = [];
  agree = true;

  async save(): Promise<void> {
    this.steps.push("save");
  }
  reveal(): void {
    this.steps.push("reveal");
  }
  async openAgent(): Promise<void> {
    this.steps.push("open");
  }
  async offer(text: string, button: string): Promise<boolean> {
    this.steps.push(`offer ${button}`);
    this.said.push(`? ${text}`);
    return this.agree;
  }
  info(text: string): void {
    this.said.push(text);
  }
  warn(text: string): void {
    this.said.push(`! ${text}`);
  }
  waited = 0;

  async wait(ms: number): Promise<void> {
    this.waited += ms;
    this.steps.push("wait");
  }
}

const PLAN = { folder: "C:\\Work\\paper", file: "C:\\Work\\paper\\studies\\x\\plan.md", caseless: true };

test("implementing saves the plan, finds the workspace of its folder, and posts the plan's path and the mode", async () => {
  const [service, presenter] = [new FakeService(), new FakePresenter()];
  assert.equal(await implement(service, presenter, PLAN, "auto"), true);
  assert.deepEqual(service.gets, [{ path: "workspaces/folder", parameters: { folder: "C:\\Work\\paper" } }]);
  assert.deepEqual(service.posts, [
    { path: "agents/implement", body: { workspace: "paper", plan: "studies/x/plan.md", mode: "auto" } },
  ]);
  assert.deepEqual(presenter.steps, ["save", "reveal"]);
  assert.deepEqual(presenter.said, ["Implementing studies/x/plan.md with Auto: the agent's window shows it"]);
  await implement(service, presenter, PLAN, "review");
  assert.deepEqual((service.posts[1]!.body as { mode: string }).mode, "review");
  assert.match(presenter.said[1]!, /with Review/);
});

test("a folder without a workspace, or a plan outside the folder, is said and nothing is posted", async () => {
  const [service, presenter] = [new FakeService(), new FakePresenter()];
  service.view = { problem: "", workspace: null };
  assert.equal(await implement(service, presenter, PLAN, "review"), false);
  service.view = { problem: "inside another workspace", workspace: null };
  assert.equal(await implement(service, presenter, PLAN, "review"), false);
  service.view = { problem: "", workspace: "paper" };
  assert.equal(await implement(service, presenter, { ...PLAN, file: "C:\\Other\\plan.md" }, "review"), false);
  assert.deepEqual(service.posts, []);
  assert.equal(presenter.said.length, 3);
  assert.ok(presenter.said.every((each) => each.startsWith("! ")));
});

test("with no OpenCode in a window, the agent is offered, opened, and the plan handed over once its window runs", async () => {
  const [service, presenter] = [new FakeService(), new FakePresenter()];
  service.failures = [new ClankError("no OpenCode runs in a window of paper", 409, "conflict")];
  service.servers = [[], [{ port: 4097, terminal: false }], [{ port: 4097, terminal: true }]];
  assert.equal(await implement(service, presenter, PLAN, "review"), true);
  assert.equal(service.posts.length, 2);
  assert.deepEqual(presenter.steps, ["save", "offer Open the agent", "open", "wait", "wait", "wait", "save", "reveal"]);
  const looks = service.gets.filter((each) => each.path === "agents/sessions");
  assert.deepEqual(looks.map((each) => each.parameters), [{ workspace: "paper" }, { workspace: "paper" }, { workspace: "paper" }]);
});

test("a window that never comes is waited for half a minute, then the plan is offered once more and the refusal said", async () => {
  const [service, presenter] = [new FakeService(), new FakePresenter()];
  const none = (): ClankError => new ClankError("no OpenCode runs in a window of paper", 409, "conflict");
  service.failures = [none(), none()];
  service.servers = Array.from({ length: 100 }, () => []);
  assert.equal(await implement(service, presenter, PLAN, "auto"), false);
  assert.equal(presenter.waited, 30_000);
  assert.equal(service.posts.length, 2);
  assert.match(presenter.said.at(-1)!, /^! no OpenCode runs/);
});

test("a look at the servers that fails is one more look, not the end of the wait", async () => {
  const [service, presenter] = [new FakeService(), new FakePresenter()];
  service.failures = [new ClankError("no OpenCode runs in a window of paper", 409, "conflict")];
  const get = service.get.bind(service);
  let looks = 0;
  service.get = async <T>(path: string, parameters?: Record<string, unknown>): Promise<T> => {
    if (path === "agents/sessions" && ++looks === 1) {
      throw new ClankError("the bridge did not answer", 409, "refused");
    }
    return get<T>(path, parameters);
  };
  assert.equal(await implement(service, presenter, PLAN, "review"), true);
  assert.equal(looks, 2);
  assert.equal(service.posts.length, 2);
});

test("the retry happens once, a declined offer stops, and other refusals are said as they come", async () => {
  const none = (): ClankError => new ClankError("no OpenCode runs in a window of paper", 409, "conflict");
  let [service, presenter] = [new FakeService(), new FakePresenter()];
  service.failures = [none(), none()];
  assert.equal(await implement(service, presenter, PLAN, "auto"), false);
  assert.equal(service.posts.length, 2);
  assert.match(presenter.said.at(-1)!, /^! no OpenCode runs/);
  [service, presenter] = [new FakeService(), new FakePresenter()];
  service.failures = [none()];
  presenter.agree = false;
  assert.equal(await implement(service, presenter, PLAN, "auto"), false);
  assert.equal(service.posts.length, 1);
  assert.ok(!presenter.steps.includes("open"));
  [service, presenter] = [new FakeService(), new FakePresenter()];
  service.failures = [new ClankError("the workspace has no container running", 409, "conflict")];
  assert.equal(await implement(service, presenter, PLAN, "auto"), false);
  assert.deepEqual(presenter.said, ["! the workspace has no container running"]);
});
