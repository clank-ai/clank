// Design 0002 §2.5, §2.7 and §3.2: the extension's controller keeps the status bar current (the service and the
// questions waiting, Docker's state), says when the service is not running and connects once one answers, shows a
// question asked, or one already waiting when VS Code opens, as a notification (each once) and answers it with the
// option chosen, says who answered when the question was answered elsewhere first, answers a question picked from the
// list, starts and stops Docker with a request key, and sends presence while the user types, at most once a minute.
// Design 0003 §8.3: the status bar shows what the main slot runs (or its state and why, in the tooltip), a slot's events
// keep it current, and Switch model picks a preset and switches the main slot with a request key; clicking the Clank
// item answers the questions when some wait, else switches the model. Design 0013 §7: when a flow's box switched the main
// slot, the window is told its model changed, once, as a notification in the service's words. Design 0016 §17: with a
// cloud model in the main slot, the Clank item says "cloud" and its tooltip today's and this month's spending in the
// service's words, and the pause; Switch model lists a cloud preset as its provider and model, with its price as the
// service says it.

import assert from "node:assert/strict";
import { test } from "node:test";

import { ClankError } from "../src/core/client";
import { Controller, type Api } from "../src/core/controller";
import type { ServerEvent } from "../src/core/events";
import type { Question, SlotRecord } from "../src/core/kinds";
import type { Presenter } from "../src/core/presenter";
import type { PresetView } from "../src/core/state";

const SERVICE = { version: "0.1.0", url: "http://127.0.0.1:7720", started: "2026-10-11T11:40:00.000Z", clients: [] };
const DOCKER = {
  label: "Docker Desktop",
  state: "running",
  version: "4.85.0",
  engine: "29.6.2",
  summary: "Docker Desktop · running · 2 containers running, none of them Clank's",
  detail: "",
  containers: [],
};

function slot(status: SlotRecord["status"], preset: string | null, reason: string): SlotRecord {
  return {
    name: "main",
    status,
    since: "2026-10-13T05:15:00.000Z",
    reason,
    preset,
    launch_id: preset ? 4 : null,
    host: preset ? "ubuntu" : null,
    pid: preset ? 971 : null,
    started: null,
    command: null,
    port: preset ? 18200 : null,
    last_good: null,
  };
}

function preset(id: string, title: string, problems: string[] = []): PresetView {
  return {
    id,
    title,
    engine: "kvmem-llamacpp",
    engine_version: "v0.16.0-rc1",
    endpoint: "",
    model: "qwen3.8-27b",
    options: {},
    slot: "main",
    host: "",
    notes: "",
    source: "default",
    file: "/clank/defaults/presets/" + id + ".json",
    problems,
  };
}

function question(id: string, title: string): Question {
  return {
    id,
    type: "approval",
    title,
    detail: "2 containers that Clank did not start are running.",
    options: [
      { id: "stop", label: "Stop them and Docker", effect: "", key: "y", asks: null },
      { id: "cancel", label: "Cancel", effect: "", key: "n", asks: null },
    ],
    default: "cancel",
    expires: null,
    urgency: "normal",
    about: null,
    status: "waiting",
    asked: "2026-10-11T11:40:00.000Z",
    asked_by: { kind: "clank", via: "docker.stop" },
    operation_id: null,
    answer: null,
    reason: "",
  };
}

/** The API as a test sets it: what each route answers, the posts it received, and an event stream fed by hand. */
class FakeApi implements Api {
  questions: Question[] = [];
  slots: SlotRecord[] = [];
  presets: PresetView[] = [];
  cost: unknown = undefined;
  questionReads = 0;
  posts: Array<{ path: string; body: unknown; key: string | undefined }> = [];
  refuse: ClankError | undefined;
  private queue: ServerEvent[] = [];
  private wake: (() => void) | undefined;

  async get<T>(path: string): Promise<T> {
    if (path.startsWith("questions")) {
      this.questionReads += 1;
    }
    const answers: Record<string, unknown> = {
      service: SERVICE,
      docker: DOCKER,
      questions: this.questions,
      history: [{ id: 41 }],
      "runtime/slots": this.slots,
      "runtime/presets": this.presets,
      "gateway/cost": this.cost,
    };
    return answers[path.split("?")[0]!] as T;
  }

  async post<T>(path: string, body?: unknown, key?: string): Promise<T> {
    this.posts.push({ path, body, key });
    if (this.refuse) {
      throw this.refuse;
    }
    return {} as T;
  }

  async *events(_after: number | undefined, signal: AbortSignal): AsyncGenerator<ServerEvent> {
    yield { name: "connected", id: undefined, data: {} };
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

/** A presenter that records what it was told and answers as a test says. */
class FakePresenter implements Presenter {
  clankText = "";
  clankTip = "";
  dockerText = "";
  told: string[] = [];
  asked: Question[] = [];
  chosen: string | undefined;
  picks: unknown[] = [];

  clank(text: string, tooltip: string): void {
    this.clankText = text;
    this.clankTip = tooltip;
  }

  docker(text: string): void {
    this.dockerText = text;
  }

  async ask(asked: Question): Promise<string | undefined> {
    this.asked.push(asked);
    return this.chosen;
  }

  offered: Array<{ label: string; detail?: string }> = [];

  async pick<T>(items: Array<{ label: string; detail?: string; value: T }>): Promise<T | undefined> {
    this.offered = items;
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

async function until(holds: () => boolean, ms = 2000): Promise<void> {
  const deadline = Date.now() + ms;
  while (!holds()) {
    if (Date.now() > deadline) {
      throw new Error("never got there");
    }
    await new Promise((resolve) => setTimeout(resolve, 5));
  }
}

function controller(api: FakeApi | undefined, presenter: FakePresenter, now = () => 0): Controller {
  return new Controller(presenter, () => api, { home: "/folders/me/.clank", retryMs: 10, now, newKey: () => "key-1" });
}

test("the status bar shows the service and the questions waiting, and Docker's state", async () => {
  const api = new FakeApi();
  api.questions = [question("q-1", "Stop Docker Desktop?")];
  const presenter = new FakePresenter();
  const running = controller(api, presenter);
  running.start();
  try {
    await until(() => presenter.clankText.includes("1 question"));
    assert.match(presenter.dockerText, /Docker: running/);
  } finally {
    running.stop();
  }
});

test("with no service it says not running, and connects once one answers", async () => {
  const presenter = new FakePresenter();
  let api: FakeApi | undefined;
  const running = new Controller(presenter, () => api, { home: "/h", retryMs: 10, now: () => 0, newKey: () => "k" });
  running.start();
  try {
    await until(() => presenter.clankText.includes("not running"));
    api = new FakeApi();
    await until(() => presenter.clankText.includes("Clank") && !presenter.clankText.includes("not running"));
  } finally {
    running.stop();
  }
});

test("a question asked shows as a notification, and the option chosen answers it", async () => {
  const api = new FakeApi();
  const presenter = new FakePresenter();
  presenter.chosen = "stop";
  const running = controller(api, presenter);
  running.start();
  try {
    await until(() => presenter.clankText.includes("Clank"));
    api.questions = [question("q-2", "Stop Docker Desktop?")];
    api.send({
      name: "question.asked",
      id: 42,
      data: { id: 42, type: "question.asked", subject: { kind: "question", id: "q-2" } },
    });
    await until(() => api.posts.length === 1);
    assert.deepEqual(api.posts[0], { path: "questions/q-2/answer", body: { option: "stop" }, key: undefined });
    assert.equal(presenter.asked[0]?.id, "q-2");
  } finally {
    running.stop();
  }
});

test("questions already waiting when VS Code opens are each shown once, not again on reconnecting", async () => {
  const api = new FakeApi();
  api.questions = [question("q-6", "Stop Docker Desktop?"), question("q-7", "Switch to fast 128K?")];
  const presenter = new FakePresenter();
  const running = controller(api, presenter);
  running.start();
  try {
    await until(() => presenter.asked.length === 2);
    api.send({
      name: "question.asked",
      id: 44,
      data: { id: 44, type: "question.asked", subject: { kind: "question", id: "q-6" } },
    });
    running.reconnect();
    await until(() => api.questionReads >= 2);
    await new Promise((resolve) => setTimeout(resolve, 50));
    assert.deepEqual(
      presenter.asked.map((asked) => asked.id),
      ["q-6", "q-7"],
    );
  } finally {
    running.stop();
  }
});

test("an option chosen after the question was answered elsewhere says who answered", async () => {
  const api = new FakeApi();
  api.refuse = new ClankError("q-3 was already answered by you (console)", 409, "refused");
  const presenter = new FakePresenter();
  presenter.chosen = "stop";
  const running = controller(api, presenter);
  running.start();
  try {
    await until(() => presenter.clankText.includes("Clank"));
    api.questions = [question("q-3", "Stop Docker Desktop?")];
    api.send({
      name: "question.asked",
      id: 43,
      data: { id: 43, type: "question.asked", subject: { kind: "question", id: "q-3" } },
    });
    await until(() => presenter.told.some((said) => said.includes("already answered by you (console)")));
  } finally {
    running.stop();
  }
});

test("the questions command lists them and answers the one picked", async () => {
  const api = new FakeApi();
  api.questions = [question("q-4", "Stop Docker Desktop?"), question("q-5", "Switch to fast 128K?")];
  const presenter = new FakePresenter();
  presenter.picks = ["Switch to fast 128K?", "Cancel"];
  const running = controller(api, presenter);
  running.start();
  try {
    await until(() => presenter.clankText.includes("2 questions"));
    await running.questions();
    assert.deepEqual(api.posts, [{ path: "questions/q-5/answer", body: { option: "cancel" }, key: undefined }]);
  } finally {
    running.stop();
  }
});

test("Docker is started and stopped with a request key", async () => {
  const api = new FakeApi();
  const presenter = new FakePresenter();
  const running = controller(api, presenter);
  await running.docker("start");
  await running.docker("stop");
  assert.deepEqual(
    api.posts.map((post) => [post.path, post.key]),
    [
      ["docker/start", "key-1"],
      ["docker/stop", "key-1"],
    ],
  );
  assert.ok(presenter.told.some((said) => said.includes("start")));
});

test("typing sends presence at most once a minute", async () => {
  const api = new FakeApi();
  let now = 0;
  const running = controller(api, new FakePresenter(), () => now);
  running.typing();
  running.typing();
  now = 59_000;
  running.typing();
  now = 61_000;
  running.typing();
  await until(() => api.posts.length === 2);
  assert.deepEqual(
    api.posts.map((post) => post.path),
    ["presence", "presence"],
  );
});


test("the status bar shows what the main slot runs, or the slot's state and why in its tooltip", async () => {
  const api = new FakeApi();
  api.slots = [slot("ready", "small-32k", "small 32K answered in 11 s")];
  api.presets = [preset("small-32k", "small 32K")];
  const presenter = new FakePresenter();
  const running = controller(api, presenter);
  running.start();
  await until(() => presenter.clankText === "$(server) Clank · small 32K");
  assert.match(presenter.clankTip, /main: ready since .*: small 32K answered in 11 s\./);
  api.slots = [slot("failed", "small-32k", "small 32K ended while it started: out of memory")];
  api.send({ name: "runtime.slot", id: 42, data: {} });
  await until(() => presenter.clankText === "$(server) Clank");
  assert.match(presenter.clankTip, /main: failed since .*: small 32K ended while it started: out of memory\./);
  running.stop();
});

test("Switch model picks a preset and switches the main slot with a request key", async () => {
  const api = new FakeApi();
  api.slots = [slot("stopped", null, "never started")];
  api.presets = [preset("daily-262k", "daily 262K"), preset("small-32k", "small 32K", ["too big"])];
  const presenter = new FakePresenter();
  const running = controller(api, presenter);
  running.start();
  await until(() => presenter.clankText === "$(server) Clank");
  presenter.picks.push("daily 262K");
  await running.switchModel();
  assert.deepEqual(api.posts, [{ path: "runtime/slots/main/switch", body: { preset: "daily-262k" }, key: "key-1" }]);
  assert.deepEqual(presenter.told, ["Switching main to daily 262K; the status bar follows it."]);
  running.stop();
});

test("clicking the Clank item answers the questions when some wait, else switches the model", async () => {
  const api = new FakeApi();
  api.presets = [preset("daily-262k", "daily 262K")];
  const presenter = new FakePresenter();
  const running = controller(api, presenter);
  running.start();
  await until(() => presenter.clankText.startsWith("$(server) Clank"));
  presenter.picks.push("daily 262K");
  await running.clicked();
  assert.equal(api.posts[0]?.path, "runtime/slots/main/switch");
  api.questions = [question("q-1", "Stop Docker Desktop?")];
  api.send({ name: "question.asked", id: 43, data: { subject: { kind: "question", id: "q-1" } } });
  await until(() => presenter.clankText.includes("1 question"));
  presenter.picks.push("Stop Docker Desktop?", "Cancel");
  await running.clicked();
  assert.deepEqual(api.posts[1], { path: "questions/q-1/answer", body: { option: "cancel" }, key: undefined });
  running.stop();
});

test("a window told its model changed shows it once, in the service's words", async () => {
  const api = new FakeApi();
  const presenter = new FakePresenter();
  const running = controller(api, presenter);
  running.start();
  try {
    await until(() => presenter.clankText.includes("Clank"));
    const said =
      "The flow Study, for its box T1, switched the main slot to fast 4K (4,096 tokens of context, 1,024 out): " +
      "your OpenCode window in paper talks to it from its next step, with the limits it started with until it next starts";
    api.send({
      name: "agents.model_changed",
      id: 44,
      data: { id: 44, type: "agents.model_changed", summary: said, subject: { kind: "workspace", id: "paper" } },
    });
    await until(() => presenter.told.length === 1);
    assert.deepEqual(presenter.told, [said]);
  } finally {
    running.stop();
  }
});


function cloudPreset(): PresetView {
  return {
    ...preset("cloud-example-coder", "cloud: Example Coder"),
    engine: "",
    engine_version: "",
    model: "example-vendor/example-coder",
    provider: "cloud openrouter",
    endpoint: "openrouter",
    price_said: "$0.30 in, $1.20 out per million tokens",
  };
}

test("a cloud model's item says cloud, its tooltip the spending in the service's words, and the pause", async () => {
  const api = new FakeApi();
  api.presets = [cloudPreset()];
  api.slots = [slot("ready", "cloud-example-coder", "cloud: Example Coder answered in 1 s")];
  api.cost = { said: "cloud $0.42 today · $3.10 this month", paused: null };
  const presenter = new FakePresenter();
  const running = controller(api, presenter);
  running.start();
  try {
    await until(() => presenter.clankText.includes("cloud"));
    assert.equal(presenter.clankText, "$(server) Clank · cloud: Example Coder · cloud");
    assert.match(presenter.clankTip, /Cloud: cloud \$0\.42 today · \$3\.10 this month\./);
    const paused = "cloud paused: today's limit of $5.00 reached ($5.02 spent)";
    api.cost = { said: "cloud $5.02 today · $6.00 this month", paused: { said: paused } };
    api.send({ name: "gateway.limit_reached", id: 42, data: { type: "gateway.limit_reached" } });
    await until(() => presenter.clankText.includes("paused"));
    assert.equal(presenter.clankText, "$(debug-pause) Clank · cloud paused");
    assert.match(presenter.clankTip, /cloud paused: today's limit of \$5\.00 reached \(\$5\.02 spent\)/);
  } finally {
    running.stop();
  }
});

test("Switch model lists a cloud preset as its provider and model, with its price", async () => {
  const api = new FakeApi();
  api.presets = [preset("daily-262k", "daily 262K"), cloudPreset()];
  api.slots = [slot("stopped", null, "never started")];
  const presenter = new FakePresenter();
  const running = controller(api, presenter);
  running.start();
  try {
    await until(() => presenter.clankText.includes("Clank"));
    presenter.picks.push("cloud: Example Coder");
    await running.switchModel();
    const cloud = presenter.offered.find((item) => item.label === "cloud: Example Coder");
    const priced = "cloud openrouter · example-vendor/example-coder · $0.30 in, $1.20 out per million tokens";
    assert.equal(cloud?.detail, priced);
    const switched = { path: "runtime/slots/main/switch", body: { preset: "cloud-example-coder" }, key: "key-1" };
    assert.deepEqual(api.posts.at(-1), switched);
  } finally {
    running.stop();
  }
});
